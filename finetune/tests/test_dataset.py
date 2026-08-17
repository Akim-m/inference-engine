import pytest
from finetune.dataset import LABEL_META, label_to_target_text

class TestLabelMeta:
    _EXPECTED = {"NV", "MEL", "BCC", "AK", "BKL", "DF", "VASC", "SCC", "UNK"}

    def test_all_nine_classes_present(self):
        assert set(LABEL_META.keys()) == self._EXPECTED

    def test_each_entry_has_required_keys(self):
        required = {"full_name", "severity", "confidence", "recommendation"}
        for code, meta in LABEL_META.items():
            assert required <= meta.keys(), f"{code} missing keys"

    def test_all_confidences_in_valid_range(self):
        for code, meta in LABEL_META.items():
            assert 0.0 < meta["confidence"] <= 1.0


class TestLabelToTargetText:
    def test_nv_produces_low_severity(self):
        assert "SEVERITY: low" in label_to_target_text("NV")

    def test_mel_produces_high_severity(self):
        assert "SEVERITY: high" in label_to_target_text("MEL")

    def test_ak_produces_moderate_severity(self):
        assert "SEVERITY: moderate" in label_to_target_text("AK")

    def test_confidence_is_float(self):
        for code in LABEL_META:
            text = label_to_target_text(code)
            for line in text.splitlines():
                if line.startswith("CONFIDENCE:"):
                    val = float(line.split(":", 1)[1].strip())
                    assert 0.0 <= val <= 1.0

    def test_all_labels_have_four_fields(self):
        required = {"CONDITION:", "SEVERITY:", "RECOMMENDATION:", "CONFIDENCE:"}
        for code in LABEL_META:
            text = label_to_target_text(code)
            for field in required:
                assert field in text

    def test_case_insensitive_input(self):
        assert label_to_target_text("nv") == label_to_target_text("NV")

    def test_unknown_label_raises_key_error(self):
        with pytest.raises(KeyError):
            label_to_target_text("NOTACLASS")

    def test_df_vasc_confidence_is_0_91(self):
        for code in ("DF", "VASC"):
            text = label_to_target_text(code)
            for line in text.splitlines():
                if line.startswith("CONFIDENCE:"):
                    assert float(line.split(":", 1)[1].strip()) == pytest.approx(0.91)

    def test_severity_values_are_low_moderate_high_only(self):
        valid = {"low", "moderate", "high"}
        for code in LABEL_META:
            text = label_to_target_text(code)
            for line in text.splitlines():
                if line.startswith("SEVERITY:"):
                    assert line.split(":", 1)[1].strip() in valid
