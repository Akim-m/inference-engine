from config import Settings


def test_vllm_client_settings_defaults():
    s = Settings(_env_file=None)
    assert s.vllm_url == "http://vllm:8001/v1"
    assert s.vllm_model == ""
    assert s.max_output_tokens == 1536
    assert s.request_timeout_s == 240


def test_chat_api_key_defaults_empty():
    # Empty means the /chat proxy is disabled (opt-in).
    assert Settings(_env_file=None).chat_api_key == ""


def test_chat_memory_defaults():
    s = Settings(_env_file=None)
    assert s.chat_memory_char_budget == 8000
    assert s.chat_memory_max_turns == 12
    assert s.chat_memory_ttl_seconds == 1800


def test_settings_ignores_unknown_env_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ADMIN_KEY=abc\nQUANTIZATION=fp8\nMAX_MODEL_LEN=4096\n")
    # Must not raise on compose-only keys; must ignore them, not absorb them as fields.
    s = Settings(_env_file=str(env))
    assert s.admin_key == "abc"
    assert not hasattr(s, "quantization")
    assert not hasattr(s, "max_model_len")
