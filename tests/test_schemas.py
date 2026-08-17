import pytest
from app.schemas import (
    JobSubmitted, JobResponse, InferenceResult,
    RadiologyStructured, DermatologyStructured,
    PathologyStructured, OphthalmologyStructured,
    TextQueryRequest, TextQueryStructured,
    ErrorResponse, CreateKeyResponse,
)


def test_job_submitted():
    assert JobSubmitted(job_id="abc").job_id == "abc"


def test_job_response_pending():
    j = JobResponse(status="pending")
    assert j.result is None and j.error is None


def test_job_response_completed():
    result = InferenceResult(raw="text", structured={"findings": "opacity"})
    j = JobResponse(status="completed", result=result)
    assert j.result.raw == "text"


def test_job_response_failed():
    assert JobResponse(status="failed", error="inference_failed").error == "inference_failed"


def test_radiology_structured_invalid_severity():
    with pytest.raises(Exception):
        RadiologyStructured(findings="x", impression="y", severity="unknown", confidence="high")


def test_dermatology_structured_valid_new_format():
    d = DermatologyStructured(
        condition="Melanocytic Nevus",
        severity="low",
        recommendation="Annual skin check",
        confidence=0.82,
    )
    assert d.condition == "Melanocytic Nevus"
    assert d.confidence == pytest.approx(0.82)


def test_dermatology_structured_rejects_mild_severity():
    with pytest.raises(Exception):
        DermatologyStructured(
            condition="Eczema", severity="mild",
            recommendation="moisturize", confidence=0.80
        )


def test_dermatology_structured_rejects_word_confidence():
    with pytest.raises(Exception):
        DermatologyStructured(
            condition="Eczema", severity="low",
            recommendation="moisturize", confidence="high"  # type: ignore
        )


def test_dermatology_structured_rejects_confidence_above_1():
    with pytest.raises(Exception):
        DermatologyStructured(
            condition="Eczema", severity="low",
            recommendation="moisturize", confidence=1.5
        )


def test_pathology_structured_valid():
    p = PathologyStructured(diagnosis="Adenocarcinoma", tissue_type="Lung", severity="severe", confidence="high")
    assert p.diagnosis == "Adenocarcinoma"
    assert p.tissue_type == "Lung"


def test_pathology_structured_invalid_severity():
    with pytest.raises(Exception):
        PathologyStructured(diagnosis="x", tissue_type="y", severity="unknown", confidence="high")


def test_ophthalmology_structured_valid():
    o = OphthalmologyStructured(finding="Drusen", affected_structure="Macula", severity="mild", confidence="medium")
    assert o.finding == "Drusen"
    assert o.affected_structure == "Macula"


def test_text_query_request_valid():
    r = TextQueryRequest(question="What is pneumothorax?")
    assert r.question == "What is pneumothorax?"


def test_text_query_request_rejects_empty():
    with pytest.raises(Exception):
        TextQueryRequest(question="")


def test_text_query_request_rejects_over_max_length():
    with pytest.raises(Exception):
        TextQueryRequest(question="x" * 501)


def test_text_query_structured_valid():
    t = TextQueryStructured(answer="It is air in the pleural space.", confidence="high")
    assert t.answer == "It is air in the pleural space."
    assert t.confidence == "high"


def test_text_query_structured_invalid_confidence():
    with pytest.raises(Exception):
        TextQueryStructured(answer="answer", confidence="very_high")


def test_error_response():
    assert ErrorResponse(error="invalid_key", message="bad key").error == "invalid_key"


def test_create_key_response():
    assert CreateKeyResponse(key="abc123").key == "abc123"
