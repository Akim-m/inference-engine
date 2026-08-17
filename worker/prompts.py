from typing import Optional

# One voice + image description per department. Both prompt families (image analysis
# and text Q&A) are built from shared rich-Markdown templates below, so the chat renders
# every reply the way ChatGPT/Claude would — and adding a department is a single line here
# (plus a parser in worker/inference.py and the entry in app/domains.py).
_SPECIALIST = {
    "radiology": ("a board-certified radiologist",
                  "radiological image such as an X-ray, CT, MRI, or ultrasound"),
    "dermatology": ("a board-certified dermatologist",
                    "dermatological image of skin, hair, or nails (e.g. a lesion, rash, or dermoscopy view)"),
    "pathology": ("a board-certified pathologist",
                  "histopathology or cytology image (e.g. a stained tissue slide or blood film)"),
    "ophthalmology": ("a board-certified ophthalmologist",
                      "ocular image such as a fundus photograph, OCT scan, or slit-lamp view"),
    "dentistry": ("an experienced dentist",
                  "dental image such as a periapical, panoramic (OPG), or intraoral photograph"),
    "general": ("a knowledgeable general medical AI assistant",
                "clinical image of any type (a radiograph, skin photo, histology slide, retinal "
                "image, dental film, or any other medical image)"),
    "orthopedics": ("a board-certified orthopedic surgeon",
                    "musculoskeletal image such as a bone or joint X-ray, CT, or MRI"),
    "pulmonology": ("a board-certified pulmonologist",
                    "respiratory image such as a chest X-ray or chest CT"),
    "neurology": ("a board-certified neurologist with neuroradiology expertise",
                  "neuroimaging study such as a brain CT or MRI"),
    "gastroenterology": ("a board-certified gastroenterologist",
                         "gastrointestinal image such as an endoscopy, colonoscopy, or abdominal study"),
    "cardiology": ("a board-certified cardiologist",
                   "cardiac image such as a chest X-ray, ECG tracing, echocardiogram, or coronary angiogram"),
    "hematology": ("a board-certified hematologist",
                   "hematology image such as a peripheral blood smear or bone marrow aspirate"),
    "rheumatology": ("a board-certified rheumatologist",
                     "musculoskeletal image such as a joint X-ray or MRI showing inflammatory or degenerative change"),
    "oncology": ("a board-certified medical oncologist",
                 "oncologic image such as a staging CT, PET-CT, or MRI showing a tumor or mass"),
    "endocrinology": ("a board-certified endocrinologist",
                      "endocrine image such as a thyroid ultrasound, adrenal CT, or pituitary MRI"),
    "nephrology": ("a board-certified nephrologist",
                   "renal image such as a kidney ultrasound, CT urogram, or renal angiogram"),
    "urology": ("a board-certified urologist",
                "urologic image such as a KUB radiograph, CT urogram, or scrotal/renal ultrasound"),
    "gynecology": ("a board-certified gynecologist",
                   "gynecologic image such as a pelvic ultrasound, transvaginal scan, or mammogram"),
    "pediatrics": ("a board-certified pediatrician",
                   "pediatric clinical image such as a child's radiograph, skin finding, or growth study"),
    "otolaryngology": ("a board-certified otolaryngologist (ENT surgeon)",
                       "ear, nose, or throat image such as an otoscopic, laryngoscopic, or sinus CT view"),
    "emergency": ("a board-certified emergency medicine physician",
                  "acute-care image such as a trauma radiograph, CT, or point-of-care ultrasound (FAST/eFAST)"),
}

# Image analysis → a rich, sectioned Markdown assessment.
_ANALYZE_TEMPLATE = (
    "You are {who}. Carefully analyze the provided {desc} and respond as well-structured "
    "Markdown, the way a specialist would explain it:\n\n"
    "- Open with a one- to two-sentence **overview** of what the image shows.\n"
    "- Then use `##` sections as relevant — for example **Findings** (what you observe), "
    "**Interpretation** (what it means), **Assessment** (severity and differential), and "
    "**Recommendation** — each with bullet points.\n"
    "- Be thorough, precise, and educational; define key terms.\n"
    "- If the image is low quality, cropped, or a finding is uncertain, say so plainly "
    "rather than over-reading it.\n"
    "- End with a short **Impression** line.\n\n"
    "This is an AI assessment for research and education only, not a diagnosis."
)

# Text question → a rich, sectioned Markdown answer.
_QUERY_TEMPLATE = (
    "You are {who}. Answer the user's medical question clearly and in depth, the way an "
    "expert clinician would teach it.\n\n"
    "Write the answer as well-structured Markdown: begin with a 1-2 sentence direct "
    "summary, then organize the details under `##` section headings with bullet points "
    "for the relevant aspects (for example: cause, clinical features, classification, "
    "diagnosis, management) — include only the sections that fit the question. When "
    "relevant, note any warning signs (\"red flags\") that warrant urgent medical "
    "attention. Be comprehensive but precise, define key terms, and finish with a short "
    "**Key point** line."
)

_ANALYZE = {d: _ANALYZE_TEMPLATE.format(who=who, desc=desc) for d, (who, desc) in _SPECIALIST.items()}
_QUERY = {d: _QUERY_TEMPLATE.format(who=who) for d, (who, _desc) in _SPECIALIST.items()}


def build_messages(
    domain: str,
    image_url: Optional[str],
    question: str,
    history: Optional[list[dict]] = None,
) -> list[dict]:
    messages: list[dict] = []
    # Prior turns (text-only) go before the current turn. With no history the
    # return value is byte-identical to the original single-turn shape.
    for entry in history or []:
        messages.append(
            {"role": entry["role"], "content": [{"type": "text", "text": entry["text"]}]}
        )
    system = _ANALYZE[domain] if image_url is not None else _QUERY[domain]
    content = []
    if image_url is not None:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    content.append({"type": "text", "text": f"{system}\n\n{question}"})
    messages.append({"role": "user", "content": content})
    return messages
