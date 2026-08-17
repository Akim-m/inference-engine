import random
from typing import Optional
from datasets import load_dataset, DatasetDict
from PIL import Image as PILImage

LABEL_META: dict[str, dict[str, str | float]] = {
    "NV":   {"full_name": "Melanocytic Nevus",       "severity": "low",      "confidence": 0.82,
              "recommendation": "Annual skin check; monitor for changes in size, shape, or color"},
    "MEL":  {"full_name": "Melanoma",                "severity": "high",     "confidence": 0.74,
              "recommendation": "Urgent dermatology referral required; excisional biopsy indicated"},
    "BCC":  {"full_name": "Basal Cell Carcinoma",    "severity": "high",     "confidence": 0.87,
              "recommendation": "Dermatology referral required; surgical excision indicated"},
    "AK":   {"full_name": "Actinic Keratosis",       "severity": "moderate", "confidence": 0.74,
              "recommendation": "Dermatology evaluation recommended; consider treatment (cryotherapy or topical)"},
    "BKL":  {"full_name": "Benign Keratosis",        "severity": "low",      "confidence": 0.82,
              "recommendation": "No immediate action required; periodic monitoring recommended"},
    "DF":   {"full_name": "Dermatofibroma",          "severity": "low",      "confidence": 0.91,
              "recommendation": "Benign; excision if symptomatic or cosmetically concerning"},
    "VASC": {"full_name": "Vascular Lesion",         "severity": "low",      "confidence": 0.91,
              "recommendation": "Monitor for changes; vascular specialist referral if symptomatic"},
    "SCC":  {"full_name": "Squamous Cell Carcinoma", "severity": "high",     "confidence": 0.87,
              "recommendation": "Urgent dermatology referral required; biopsy and treatment indicated"},
    "UNK":  {"full_name": "Unknown",                 "severity": "moderate", "confidence": 0.50,
              "recommendation": "Clinical evaluation required; cannot determine diagnosis from image alone"},
}

_USER_PROMPT = "Analyze this skin lesion and provide a structured clinical assessment."


def label_to_target_text(label: str) -> str:
    meta = LABEL_META[label.upper().strip()]
    return (
        f"CONDITION: {meta['full_name']}\n"
        f"SEVERITY: {meta['severity']}\n"
        f"RECOMMENDATION: {meta['recommendation']}\n"
        f"CONFIDENCE: {meta['confidence']:.2f}"
    )


def format_example(example: dict, processor) -> dict:
    label: str = example["dx"]
    image: PILImage.Image = example["image"]
    if image.mode != "RGB":
        image = image.convert("RGB")

    messages = [
        {"role": "user", "content": [
            {"type": "image"},
            {"type": "text", "text": _USER_PROMPT},
        ]},
        {"role": "assistant", "content": label_to_target_text(label)},
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return {"text": text, "image": image}


def load_isic_splits(
    hf_path: str = "marmal88/skin_cancer",
    val_fraction: float = 0.10,
    seed: int = 42,
    hf_token: Optional[str] = None,
) -> DatasetDict:
    """Stratified train/val split from the single 'train' split in marmal88/skin_cancer."""
    raw = load_dataset(hf_path, token=hf_token)
    full = raw["train"]

    class_indices: dict[str, list[int]] = {}
    labels = full["dx"]  # reads only the dx column, avoids image decode
    for idx, label in enumerate(labels):
        class_indices.setdefault(label, []).append(idx)

    rng = random.Random(seed)
    val_idx, train_idx = [], []
    for label, indices in sorted(class_indices.items()):
        rng.shuffle(indices)
        n_val = max(1, min(int(len(indices) * val_fraction), len(indices) - 1))
        val_idx.extend(indices[:n_val])
        train_idx.extend(indices[n_val:])

    return DatasetDict({"train": full.select(train_idx), "val": full.select(val_idx)})
