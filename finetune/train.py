import argparse, os, yaml, torch
from transformers import (
    AutoModelForImageTextToText, AutoProcessor,
    BitsAndBytesConfig, TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
from finetune.dataset import load_isic_splits, format_example


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def apply_hardware_overrides(cfg: dict, hw: str) -> dict:
    for key, val in cfg.get("hardware_overrides", {}).get(hw, {}).items():
        if key == "load_in_4bit":
            cfg["quantization"]["load_in_4bit"] = val
        else:
            cfg["training"][key] = val
    return cfg


def load_model_and_processor(mcfg: dict, qcfg: dict, use_4bit: bool):
    token = mcfg.get("hf_token") or os.environ.get("HF_TOKEN")
    extra = {"token": token} if token else {}
    processor = AutoProcessor.from_pretrained(mcfg["base_id"], **extra)

    if use_4bit:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=qcfg["bnb_4bit_quant_type"],
            bnb_4bit_compute_dtype=getattr(torch, qcfg["bnb_4bit_compute_dtype"]),
            bnb_4bit_use_double_quant=qcfg["bnb_4bit_use_double_quant"],
        )
        model = AutoModelForImageTextToText.from_pretrained(
            mcfg["base_id"], quantization_config=bnb,
            device_map="auto", trust_remote_code=True, **extra
        )
        model = prepare_model_for_kbit_training(model)
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            mcfg["base_id"], torch_dtype=torch.bfloat16,
            device_map="auto", trust_remote_code=True, **extra
        )
    return processor, model


def apply_lora(model, lcfg: dict):
    return get_peft_model(model, LoraConfig(
        r=lcfg["r"], lora_alpha=lcfg["lora_alpha"],
        lora_dropout=lcfg["lora_dropout"],
        target_modules=lcfg["target_modules"],
        bias=lcfg["bias"], task_type=lcfg["task_type"],
    ))


class DermatologyCollator:
    """
    Multimodal collator for MedGemma instruction fine-tuning.
    Masks the instruction (user turn) in labels so loss is computed
    only on the assistant response.
    """

    # Gemma3 chat template wraps the assistant turn with this prefix
    # Used to find where the response starts in tokenized sequences
    _RESPONSE_PREFIX = "<start_of_turn>model\n"

    def __init__(self, processor, max_length: int):
        self.processor = processor
        self.max_length = max_length
        self._response_ids: list[int] | None = None

    def _get_response_token_ids(self) -> list[int]:
        if self._response_ids is None:
            self._response_ids = self.processor.tokenizer.encode(
                self._RESPONSE_PREFIX, add_special_tokens=False
            )
        return self._response_ids

    def __call__(self, examples: list[dict]) -> dict:
        batch = self.processor(
            text=[ex["text"] for ex in examples],
            images=[ex["image"] for ex in examples],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        )

        labels = batch["input_ids"].clone()
        response_ids = self._get_response_token_ids()
        n = len(response_ids)

        for i, seq in enumerate(labels):
            # Find the start of the assistant response in this sequence
            # by searching for the response prefix token IDs
            response_start = None
            for j in range(len(seq) - n + 1):
                if seq[j : j + n].tolist() == response_ids:
                    response_start = j + n  # mask up to but NOT including the response
                    break

            if response_start is not None:
                labels[i, :response_start] = -100  # mask user turn + system prefix
            # Always mask padding
            labels[i][batch["input_ids"][i] == self.processor.tokenizer.pad_token_id] = -100

        batch["labels"] = labels
        return batch


def prepare_datasets(cfg: dict, processor):
    token = cfg["model"].get("hf_token") or os.environ.get("HF_TOKEN")
    splits = load_isic_splits(
        hf_path=cfg["dataset"]["hf_path"],
        val_fraction=cfg["dataset"]["val_fraction"],
        seed=cfg["dataset"]["seed"],
        hf_token=token,
    )
    def _fmt(ex): return format_example(ex, processor)
    keep = {"text", "image"}
    train_ds = splits["train"].map(_fmt, remove_columns=[c for c in splits["train"].column_names if c not in keep])
    val_ds = splits["val"].map(_fmt, remove_columns=[c for c in splits["val"].column_names if c not in keep])
    return train_ds, val_ds


def build_training_args(tcfg: dict, output_dir: str) -> TrainingArguments:
    try:
        return TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=tcfg["num_epochs"],
            per_device_train_batch_size=tcfg["per_device_train_batch_size"],
            per_device_eval_batch_size=tcfg["per_device_eval_batch_size"],
            gradient_accumulation_steps=tcfg["gradient_accumulation_steps"],
            learning_rate=tcfg["learning_rate"],
            lr_scheduler_type=tcfg["lr_scheduler_type"],
            warmup_ratio=tcfg["warmup_ratio"],
            weight_decay=tcfg["weight_decay"],
            gradient_checkpointing=tcfg["gradient_checkpointing"],
            fp16=tcfg["fp16"], bf16=tcfg["bf16"],
            logging_steps=tcfg["logging_steps"],
            eval_strategy=tcfg["eval_strategy"],
            eval_steps=tcfg["eval_steps"],
            save_strategy=tcfg["save_strategy"],
            save_steps=tcfg["save_steps"],
            save_total_limit=tcfg["save_total_limit"],
            load_best_model_at_end=tcfg["load_best_model_at_end"],
            metric_for_best_model=tcfg["metric_for_best_model"],
            dataloader_num_workers=tcfg["dataloader_num_workers"],
            remove_unused_columns=tcfg["remove_unused_columns"],
            report_to=tcfg["report_to"],
        )
    except KeyError as e:
        raise KeyError(f"Missing training config key: {e}. Check finetune/config.yaml") from e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="finetune/config.yaml")
    parser.add_argument("--hardware", choices=["rtx4060", "t4", "a100"], default="rtx4060")
    parser.add_argument("--resume_from_checkpoint", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg = apply_hardware_overrides(cfg, args.hardware)

    use_4bit = cfg["quantization"]["load_in_4bit"]
    output_dir = cfg["model"]["adapter_output_dir"]
    print(f"[train] hardware={args.hardware}, 4bit={use_4bit}, output={output_dir}")

    processor, model = load_model_and_processor(cfg["model"], cfg["quantization"], use_4bit)
    model = apply_lora(model, cfg["lora"])
    model.print_trainable_parameters()

    train_ds, val_ds = prepare_datasets(cfg, processor)
    print(f"[train] train={len(train_ds)}, val={len(val_ds)}")

    trainer = SFTTrainer(
        model=model,
        args=build_training_args(cfg["training"], output_dir),
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=DermatologyCollator(processor, cfg["training"]["max_seq_length"]),
    )
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    model.save_pretrained(output_dir)
    processor.save_pretrained(output_dir)
    print(f"[train] Adapter saved to {output_dir}")


if __name__ == "__main__":
    main()
