from worker.prompts import build_messages

_IMG = "data:image/png;base64,QUJD"

_ALL_DOMAINS = (
    "radiology", "dermatology", "pathology", "ophthalmology", "dentistry", "general",
    "orthopedics", "pulmonology", "neurology", "gastroenterology",
    "cardiology", "hematology", "rheumatology",
    "oncology", "endocrinology", "nephrology", "urology",
    "gynecology", "pediatrics", "otolaryngology", "emergency",
)


def _text(msgs) -> str:
    """Extract the text content from the single (final) user message."""
    return next(p["text"] for p in msgs[0]["content"] if p["type"] == "text")


def _image_parts(msgs):
    return [p for p in msgs[0]["content"] if p["type"] == "image_url"]


def test_analyze_prompts_are_rich_markdown():
    # Image analysis returns a sectioned Markdown assessment, not FINDINGS:/SEVERITY: labels.
    for domain in _ALL_DOMAINS:
        text = _text(build_messages(domain, _IMG, ""))
        assert "Markdown" in text
        assert "Findings" in text        # rich section heading
        assert "FINDINGS:" not in text   # old terse label gone


def test_query_prompts_are_rich_markdown():
    # Text answers likewise. Also guards the KeyError trap — build_messages subscripts
    # _QUERY[domain] / _ANALYZE[domain] directly, so every registered domain must resolve.
    for domain in _ALL_DOMAINS:
        text = _text(build_messages(domain, None, ""))
        assert "Markdown" in text and "##" in text
        assert "ANSWER:" not in text


def test_query_mode_no_image_in_content():
    assert len(_image_parts(build_messages("radiology", None, "What causes pneumonia?"))) == 0


def test_image_in_content_when_provided():
    msgs = build_messages("radiology", _IMG, "")
    parts = _image_parts(msgs)
    assert len(parts) == 1
    assert parts[0]["image_url"]["url"] == _IMG


def test_question_in_content():
    assert "Is there a fracture?" in _text(build_messages("radiology", _IMG, "Is there a fracture?"))


def test_analyze_uses_domain_specific_prompt():
    assert _text(build_messages("radiology", _IMG, "")) != _text(build_messages("dermatology", _IMG, ""))


def test_query_uses_domain_specific_prompt():
    assert _text(build_messages("radiology", None, "")) != _text(build_messages("ophthalmology", None, ""))


_HISTORY = [
    {"role": "user", "text": "What is this rash?"},
    {"role": "assistant", "text": "It looks like eczema."},
]


def test_history_absent_is_single_message():
    assert len(build_messages("general", None, "q")) == 1
    assert len(build_messages("general", None, "q", history=None)) == 1
    assert len(build_messages("general", None, "q", history=[])) == 1


def test_history_prepended_before_current_turn():
    msgs = build_messages("general", None, "Is it serious?", history=_HISTORY)
    assert len(msgs) == 3
    assert msgs[0] == {"role": "user", "content": [{"type": "text", "text": "What is this rash?"}]}
    assert msgs[1] == {"role": "assistant", "content": [{"type": "text", "text": "It looks like eczema."}]}


def test_current_turn_shape_unchanged_with_history():
    # The final message still carries the system prompt + question.
    msgs = build_messages("general", None, "Is it serious?", history=_HISTORY)
    final_text = msgs[-1]["content"][-1]["text"]
    assert "Markdown" in final_text and "Is it serious?" in final_text
    assert msgs[-1]["role"] == "user"


def test_history_with_image_current_turn():
    # Image only on the current turn; history entries are text-only.
    msgs = build_messages("general", _IMG, "And this one?", history=_HISTORY)
    assert len(msgs) == 3
    assert all(p["type"] == "text" for m in msgs[:-1] for p in m["content"])
    assert any(p["type"] == "image_url" for p in msgs[-1]["content"])
