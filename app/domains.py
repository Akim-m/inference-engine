"""The registered medical domains — single source of truth.

Every domain exposes the identical analyze + query surface (only the domain string
differs). Adding a domain: add it here, plus a prompt (worker/prompts.py) and a
parser (worker/inference.py). Both app/main.py (route registration) and
app/routes/chat.py (the /chat department selector) import this list, so they can
never drift.
"""

DOMAINS = [
    "radiology", "dermatology", "pathology", "ophthalmology", "dentistry", "general",
    "orthopedics", "pulmonology", "neurology", "gastroenterology",
    "cardiology", "hematology", "rheumatology",
    # Second wave of specialties.
    "oncology", "endocrinology", "nephrology", "urology",
    "gynecology", "pediatrics", "otolaryngology", "emergency",
]
