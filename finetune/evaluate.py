from __future__ import annotations
import argparse, json, re, torch
from pathlib import Path
from transformers import AutoModelForImageTextToText, AutoProcessor
from peft import PeftModel
from sklearn.metrics import classification_report
from finetune.dataset import LABEL_META, load_isic_splits

_EVAL_RE = re.compile(
    r"CONDITION:\s*(.+?)\s*\n"
    r"SEVERITY:\s*(low|moderate|high)\s*\n"
    r"RECOMMENDATION:\s*(.+?)\s*\n"
    r"CONFIDENCE:\s*(\d+\.\d+)",
    re.IGNORECASE,
)
_FULLNAME_TO_CODE = {meta["full_name"].lower(): code for code, meta in LABEL_META.items()}
_USER_PROMPT = "Analyze this skin lesion and provide a structured clinical assessment."


def load_finetuned(base_id: str, adapter_dir: str, use_4bit: bool):
    if use_4bit:
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
        base = AutoModelForImageTextToText.from_pretrained(base_id, quantization_config=bnb,
                                                           device_map="auto", trust_remote_code=True)
    else:
        base = AutoModelForImageTextToText.from_pretrained(base_id, torch_dtype=torch.bfloat16,
                                                           device_map="auto", trust_remote_code=True)
    model = PeftModel.from_pretrained(base, adapter_dir)
    model.eval()
    processor = AutoProcessor.from_pretrained(adapter_dir)
    return processor, model


def run_single(processor, model, image) -> str:
    inputs = processor.apply_chat_template(
        [{"role": "user", "content": [{"type": "image", "image": image},
                                       {"type": "text", "text": _USER_PROMPT}]}],
        add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt",
    ).to(model.device, dtype=torch.bfloat16)
    input_len = inputs["input_ids"].shape[-1]
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=128, do_sample=False)
    return processor.decode(out[0][input_len:], skip_special_tokens=True)


def parse_prediction(raw: str) -> dict | None:
    m = _EVAL_RE.search(raw)
    if not m:
        return None
    return {
        "code": _FULLNAME_TO_CODE.get(m.group(1).strip().lower()),
        "severity": m.group(2).lower(),
        "confidence": float(m.group(4)),
    }


def evaluate(adapter_dir: str, base_id: str, use_4bit: bool, max_samples: int | None):
    processor, model = load_finetuned(base_id, adapter_dir, use_4bit)
    val_ds = load_isic_splits()["val"]
    if max_samples:
        val_ds = val_ds.select(range(min(max_samples, len(val_ds))))

    y_true, y_pred, format_hits = [], [], 0
    for i, row in enumerate(val_ds):
        img = row["image"].convert("RGB")
        true = row["dx"].upper()
        raw = run_single(processor, model, img)
        parsed = parse_prediction(raw)
        y_true.append(true)
        if parsed is None:
            y_pred.append("PARSE_FAIL")
        else:
            format_hits += 1
            y_pred.append(parsed["code"] or "UNKNOWN")
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(val_ds)}] compliance={format_hits/(i+1):.3f}")

    label_order = sorted(LABEL_META.keys())
    report = classification_report(
        y_true, y_pred, labels=label_order,
        target_names=[LABEL_META[l]["full_name"] for l in label_order],
        output_dict=True, zero_division=0,
    )
    return {
        "n_samples": len(y_true),
        "format_compliance_rate": round(format_hits / len(y_true), 4),
        "classification_report": report,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter_dir", required=True)
    parser.add_argument("--base_id", default="google/medgemma-4b-it")
    parser.add_argument("--no_4bit", action="store_true")
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument("--output_json", default="finetune/eval_results.json")
    args = parser.parse_args()

    results = evaluate(args.adapter_dir, args.base_id, not args.no_4bit, args.max_samples)
    print(f"\nFormat compliance: {results['format_compliance_rate']:.2%}")
    print(f"Macro F1:          {results['classification_report']['macro avg']['f1-score']:.4f}")
    print(f"Weighted F1:       {results['classification_report']['weighted avg']['f1-score']:.4f}")
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Full results: {args.output_json}")


if __name__ == "__main__":
    main()
