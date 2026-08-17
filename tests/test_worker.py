import json
import httpx
import pytest
from unittest.mock import MagicMock, patch

from worker.worker import process_job
from worker.memory import load_history

CID = "22222222-2222-4222-8222-222222222222"


def _fake_stream(content: str, completion_tokens: int = 3):
    """A fake vLLM streaming response: one delta chunk carrying the whole content,
    a usage chunk, then [DONE]. `process_job` always streams, so worker tests mock
    `_client.stream` (a context manager) rather than `_client.post`."""
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": content}}]}),
        "data: " + json.dumps({"choices": [], "usage": {"completion_tokens": completion_tokens}}),
        "data: [DONE]",
    ]
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.iter_lines.return_value = lines
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


def _stream_patch(content: str):
    return patch("worker.inference._client.stream", return_value=_fake_stream(content))


def _flatten_text(messages) -> str:
    return " ".join(
        p.get("text", "") for m in messages for p in m["content"] if isinstance(p, dict)
    )


@pytest.fixture(autouse=True)
def _redis(fake_redis, monkeypatch):
    # process_job pulls Redis from the module global via _get_redis().
    monkeypatch.setattr("worker.worker._redis", fake_redis)
    return fake_redis


def test_process_job_without_conversation_id_writes_no_memory(_redis):
    # The /v1-stays-stateless guard: no conversation_id => nothing stored.
    with _stream_patch("ANSWER: hi\nCONFIDENCE: low\n"):
        process_job("j1", "general", "", "hello", "kh")
    assert _redis.keys("chat:conv:*") == []


def test_second_turn_payload_contains_first_turn_context(_redis):
    with _stream_patch("ANSWER: eczema is a skin condition.\nCONFIDENCE: high\n"):
        process_job("j1", "general", "", "What is eczema?", "kh", conversation_id=CID)
    with patch("worker.inference._client.stream",
               return_value=_fake_stream("ANSWER: sometimes.\nCONFIDENCE: medium\n")) as mock_stream:
        process_job("j2", "general", "", "Is it serious?", "kh", conversation_id=CID)
    messages = mock_stream.call_args.kwargs["json"]["messages"]
    assert len(messages) == 3  # 2 history entries + current turn
    assert "What is eczema?" in _flatten_text(messages)


def test_failed_job_writes_no_history(_redis):
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    with patch("worker.inference._client.stream", return_value=cm):
        with pytest.raises(httpx.HTTPStatusError):
            process_job("j1", "general", "", "boom", "kh", conversation_id=CID)
    assert _redis.exists(f"chat:conv:{CID}") == 0


def test_failed_job_emits_stream_error_marker(_redis):
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    with patch("worker.inference._client.stream", return_value=cm):
        with pytest.raises(httpx.HTTPStatusError):
            process_job("jX", "general", "", "boom", "kh")
    frames = [json.loads(x) for x in _redis.lrange("chat:stream:jX", 0, -1)]
    assert frames and frames[-1]["t"] == "error"


def test_success_emits_delta_then_done_with_stats(_redis):
    with _stream_patch("ANSWER: yes.\nCONFIDENCE: high\n"):
        process_job("jS", "general", "", "hello?", "kh")
    frames = [json.loads(x) for x in _redis.lrange("chat:stream:jS", 0, -1)]
    assert frames[0]["t"] == "delta" and "yes." in frames[0]["text"]
    assert frames[-1]["t"] == "done"
    assert frames[-1]["stats"]["completion_tokens"] == 3


def test_image_turn_stores_placeholder_not_bytes(_redis, tmp_path):
    img = tmp_path / "j.img"
    img.write_bytes(b"\xff\xd8\xff" + b"x" * 32)  # JPEG magic + filler
    with _stream_patch("FINDINGS: none\nIMPRESSION: normal\nCONFIDENCE: high\n"):
        process_job("j4", "general", str(img), "what is this?", "kh", conversation_id=CID)
    stored = load_history(_redis, CID, 100000)
    assert stored[0]["text"] == "[shared a medical image] what is this?"
    raw = _redis.lrange(f"chat:conv:{CID}", 0, -1)
    assert all("base64" not in item for item in raw)
    assert not img.exists()  # temp file cleaned up (existing behavior)


def test_success_with_conversation_id_appends_trimmed_turn(_redis):
    with _stream_patch("ANSWER: yes.\nCONFIDENCE: high\n"):
        process_job("j1", "general", "", "hello?", "kh", conversation_id=CID)
    stored = load_history(_redis, CID, 100000)
    assert stored[0] == {"role": "user", "text": "hello?"}
    assert stored[1]["role"] == "assistant"
    assert "ANSWER: yes." in stored[1]["text"]
