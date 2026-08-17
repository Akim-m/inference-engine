import io
import httpx
import pytest
from PIL import Image
from unittest.mock import MagicMock, patch
from worker.inference import (
    parse_radiology, parse_dermatology,
    parse_pathology, parse_ophthalmology, parse_dentistry, parse_query,
    parse_general, run_inference,
    parse_orthopedics, parse_pulmonology, parse_neurology, parse_gastroenterology,
    parse_cardiology, parse_hematology, parse_rheumatology,
)


def _img_bytes(fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format=fmt)
    return buf.getvalue()


def test_parse_radiology_valid():
    raw = "FINDINGS: Opacity left lower lobe\nIMPRESSION: Possible pneumonia\nSEVERITY: moderate\nCONFIDENCE: high\n"
    r = parse_radiology(raw)
    assert r["findings"] == "Opacity left lower lobe"
    assert r["impression"] == "Possible pneumonia"
    assert r["severity"] == "moderate"
    assert r["confidence"] == "high"


def test_parse_radiology_invalid_returns_none():
    assert parse_radiology("This is unstructured text.") is None


def test_parse_radiology_unknown_severity():
    # model sometimes returns values outside the expected enum (e.g. "unknown")
    raw = "FINDINGS: Opacity\nIMPRESSION: Unclear\nSEVERITY: unknown\nCONFIDENCE: low\n"
    r = parse_radiology(raw)
    assert r is not None
    assert r["severity"] == "unknown"
    assert r["confidence"] == "low"


def test_parse_dermatology_new_format():
    raw = (
        "CONDITION: Melanocytic Nevus\n"
        "SEVERITY: low\n"
        "RECOMMENDATION: Annual skin check; monitor for changes in size, shape, or color\n"
        "CONFIDENCE: 0.82\n"
    )
    d = parse_dermatology(raw)
    assert d is not None
    assert d["condition"] == "Melanocytic Nevus"
    assert d["severity"] == "low"
    assert d["recommendation"] == "Annual skin check; monitor for changes in size, shape, or color"
    assert d["confidence"] == pytest.approx(0.82)
    assert isinstance(d["confidence"], float)


def test_parse_dermatology_rejects_old_word_confidence():
    # Old format CONFIDENCE: high must NOT parse under new regex
    raw = (
        "CONDITION: Eczema\n"
        "SEVERITY: low\n"
        "RECOMMENDATION: Apply moisturizer\n"
        "CONFIDENCE: high\n"
    )
    assert parse_dermatology(raw) is None


def test_parse_dermatology_high_severity():
    raw = (
        "CONDITION: Melanoma\n"
        "SEVERITY: high\n"
        "RECOMMENDATION: Urgent dermatology referral required; excisional biopsy indicated\n"
        "CONFIDENCE: 0.74\n"
    )
    d = parse_dermatology(raw)
    assert d is not None
    assert d["severity"] == "high"
    assert d["confidence"] == pytest.approx(0.74)


def test_parse_dermatology_moderate_severity():
    raw = (
        "CONDITION: Actinic Keratosis\n"
        "SEVERITY: moderate\n"
        "RECOMMENDATION: Dermatology evaluation recommended\n"
        "CONFIDENCE: 0.74\n"
    )
    d = parse_dermatology(raw)
    assert d is not None
    assert d["severity"] == "moderate"


def test_parse_dermatology_invalid_returns_none():
    assert parse_dermatology("No format here") is None


def test_parse_pathology_valid():
    raw = "DIAGNOSIS: Adenocarcinoma\nTISSUE_TYPE: Lung\nSEVERITY: severe\nCONFIDENCE: high\n"
    p = parse_pathology(raw)
    assert p["diagnosis"] == "Adenocarcinoma"
    assert p["tissue_type"] == "Lung"
    assert p["severity"] == "severe"
    assert p["confidence"] == "high"


def test_parse_pathology_invalid_returns_none():
    assert parse_pathology("No format here") is None


def test_parse_ophthalmology_valid():
    raw = "FINDING: Macular degeneration\nAFFECTED_STRUCTURE: Macula\nSEVERITY: moderate\nCONFIDENCE: medium\n"
    o = parse_ophthalmology(raw)
    assert o["finding"] == "Macular degeneration"
    assert o["affected_structure"] == "Macula"
    assert o["severity"] == "moderate"
    assert o["confidence"] == "medium"


def test_parse_ophthalmology_invalid_returns_none():
    assert parse_ophthalmology("No format here") is None


def test_parse_dentistry_valid():
    raw = "FINDING: Periapical abscess\nAFFECTED_AREA: Lower left molar\nSEVERITY: moderate\nCONFIDENCE: high\n"
    d = parse_dentistry(raw)
    assert d["finding"] == "Periapical abscess"
    assert d["affected_area"] == "Lower left molar"
    assert d["severity"] == "moderate"
    assert d["confidence"] == "high"


def test_parse_dentistry_invalid_returns_none():
    assert parse_dentistry("No format here") is None


def test_parse_orthopedics_valid():
    raw = "FINDING: Distal radius fracture\nAFFECTED_BONE: Right radius\nSEVERITY: moderate\nCONFIDENCE: high\n"
    r = parse_orthopedics(raw)
    assert r["finding"] == "Distal radius fracture"
    assert r["affected_bone"] == "Right radius"
    assert r["severity"] == "moderate"
    assert r["confidence"] == "high"


def test_parse_orthopedics_invalid_returns_none():
    assert parse_orthopedics("No format here") is None


def test_parse_pulmonology_valid():
    raw = "FINDING: Consolidation\nAFFECTED_REGION: Left lower lobe\nSEVERITY: moderate\nCONFIDENCE: medium\n"
    r = parse_pulmonology(raw)
    assert r["finding"] == "Consolidation"
    assert r["affected_region"] == "Left lower lobe"
    assert r["severity"] == "moderate"
    assert r["confidence"] == "medium"


def test_parse_pulmonology_invalid_returns_none():
    assert parse_pulmonology("No format here") is None


def test_parse_neurology_valid():
    raw = "FINDING: Acute infarct\nAFFECTED_REGION: Left MCA territory\nSEVERITY: severe\nCONFIDENCE: high\n"
    r = parse_neurology(raw)
    assert r["finding"] == "Acute infarct"
    assert r["affected_region"] == "Left MCA territory"
    assert r["severity"] == "severe"
    assert r["confidence"] == "high"


def test_parse_neurology_invalid_returns_none():
    assert parse_neurology("No format here") is None


def test_parse_gastroenterology_valid():
    raw = "FINDING: Gastric ulcer\nLOCATION: Antrum\nSEVERITY: moderate\nCONFIDENCE: medium\n"
    r = parse_gastroenterology(raw)
    assert r["finding"] == "Gastric ulcer"
    assert r["location"] == "Antrum"
    assert r["severity"] == "moderate"
    assert r["confidence"] == "medium"


def test_parse_gastroenterology_invalid_returns_none():
    assert parse_gastroenterology("No format here") is None


def test_parse_cardiology_valid():
    raw = "FINDING: Cardiomegaly\nAFFECTED_STRUCTURE: Left ventricle\nSEVERITY: moderate\nCONFIDENCE: high\n"
    r = parse_cardiology(raw)
    assert r["finding"] == "Cardiomegaly"
    assert r["affected_structure"] == "Left ventricle"
    assert r["severity"] == "moderate"
    assert r["confidence"] == "high"


def test_parse_cardiology_invalid_returns_none():
    assert parse_cardiology("No format here") is None


def test_parse_hematology_valid():
    raw = "FINDING: Blast cells present\nCELL_LINE: myeloid\nSEVERITY: severe\nCONFIDENCE: medium\n"
    r = parse_hematology(raw)
    assert r["finding"] == "Blast cells present"
    assert r["cell_line"] == "myeloid"
    assert r["severity"] == "severe"
    assert r["confidence"] == "medium"


def test_parse_hematology_invalid_returns_none():
    assert parse_hematology("No format here") is None


def test_parse_rheumatology_valid():
    raw = "FINDING: Joint space narrowing\nAFFECTED_JOINT: Right knee\nSEVERITY: moderate\nCONFIDENCE: high\n"
    r = parse_rheumatology(raw)
    assert r["finding"] == "Joint space narrowing"
    assert r["affected_joint"] == "Right knee"
    assert r["severity"] == "moderate"
    assert r["confidence"] == "high"


def test_parse_rheumatology_invalid_returns_none():
    assert parse_rheumatology("No format here") is None


def test_run_inference_cardiology_registered_in_parsers():
    # Guards _ANALYZE_PARSERS registration (.get(domain) silently yields None if unwired).
    expected_raw = "FINDING: Cardiomegaly\nAFFECTED_STRUCTURE: Left ventricle\nSEVERITY: moderate\nCONFIDENCE: high\n"
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)):
        result = run_inference("cardiology", _img_bytes(), "")
    assert result["structured"]["finding"] == "Cardiomegaly"
    assert result["structured"]["affected_structure"] == "Left ventricle"


def test_run_inference_orthopedics_registered_in_parsers():
    # Guards the _ANALYZE_PARSERS registration: .get(domain) silently yields
    # structured=None if the parser isn't wired in, so assert we get structure back.
    expected_raw = "FINDING: Hairline fracture\nAFFECTED_BONE: Left tibia\nSEVERITY: mild\nCONFIDENCE: high\n"
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)):
        result = run_inference("orthopedics", _img_bytes(), "")
    assert result["structured"]["finding"] == "Hairline fracture"
    assert result["structured"]["affected_bone"] == "Left tibia"


def test_parse_query_valid():
    raw = "ANSWER: Pneumothorax is the presence of air in the pleural space.\nCONFIDENCE: high\n"
    q = parse_query(raw)
    assert q["answer"] == "Pneumothorax is the presence of air in the pleural space."
    assert q["confidence"] == "high"


def test_parse_query_invalid_returns_none():
    assert parse_query("No format here") is None


def test_parse_general_valid():
    raw = "FINDINGS: Opacity in the left lung\nIMPRESSION: Possible infection\nCONFIDENCE: medium\n"
    g = parse_general(raw)
    assert g["findings"] == "Opacity in the left lung"
    assert g["impression"] == "Possible infection"
    assert g["confidence"] == "medium"


def test_parse_general_invalid_returns_none():
    assert parse_general("No structure here") is None


def test_run_inference_general_analyze_returns_structured():
    expected_raw = "FINDINGS: Skin lesion\nIMPRESSION: Benign nevus\nCONFIDENCE: high\n"
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)):
        result = run_inference("general", _img_bytes(), "")
    assert result["raw"] == expected_raw
    assert result["structured"]["findings"] == "Skin lesion"
    assert result["structured"]["impression"] == "Benign nevus"
    assert result["structured"]["confidence"] == "high"


def _fake_response(content: str):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def test_run_inference_returns_raw_and_structured():
    expected_raw = "FINDINGS: Test finding\nIMPRESSION: Test impression\nSEVERITY: mild\nCONFIDENCE: high\n"
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)) as mock_post:
        result = run_inference("radiology", _img_bytes(), "")
    assert result["raw"] == expected_raw
    assert result["structured"]["findings"] == "Test finding"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 1536
    content = payload["messages"][0]["content"]
    assert any(p["type"] == "image_url" for p in content)


def test_run_inference_structured_none_on_parse_failure():
    with patch("worker.inference._client.post", return_value=_fake_response("Unstructured response")):
        result = run_inference("radiology", _img_bytes(), "")
    assert result["raw"] == "Unstructured response"
    assert result["structured"] is None


def test_run_inference_text_query_no_image():
    expected_raw = "ANSWER: Pneumonia causes consolidation.\nCONFIDENCE: high\n"
    with patch("worker.inference._client.post", return_value=_fake_response(expected_raw)) as mock_post:
        result = run_inference("radiology", None, "What does pneumonia look like?")
    assert result["raw"] == expected_raw
    assert result["structured"]["answer"] == "Pneumonia causes consolidation."
    assert result["structured"]["confidence"] == "high"
    content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert all(p["type"] != "image_url" for p in content)


def test_run_inference_raises_on_http_error():
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    with patch("worker.inference._client.post", return_value=resp):
        with pytest.raises(httpx.HTTPStatusError):
            run_inference("radiology", _img_bytes(), "")


def test_run_inference_threads_history_into_payload():
    history = [
        {"role": "user", "text": "What is a fracture?"},
        {"role": "assistant", "text": "A break in bone."},
    ]
    with patch("worker.inference._client.post",
               return_value=_fake_response("ANSWER: yes\nCONFIDENCE: high\n")) as mock_post:
        run_inference("general", None, "Is it serious?", history=history)
    messages = mock_post.call_args.kwargs["json"]["messages"]
    assert len(messages) == 3
    assert messages[0]["content"][0]["text"] == "What is a fracture?"
    assert messages[1]["role"] == "assistant"


def test_run_inference_history_default_is_single_message():
    with patch("worker.inference._client.post",
               return_value=_fake_response("ANSWER: x\nCONFIDENCE: low\n")) as mock_post:
        run_inference("general", None, "q")
    assert len(mock_post.call_args.kwargs["json"]["messages"]) == 1
