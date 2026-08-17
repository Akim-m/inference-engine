import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.deps import get_redis
from config import settings


@pytest.fixture
def client(seeded_redis):
    app.dependency_overrides[get_redis] = lambda: seeded_redis
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def chat_enabled(monkeypatch):
    monkeypatch.setattr(settings, "chat_api_key", "chat-shared-secret-key")


def test_chat_page_served(client):
    resp = client.get("/chat")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "troke" in resp.text.lower()


def test_chat_page_has_conversation_memory_controls(client):
    resp = client.get("/chat")
    assert "crypto.randomUUID" in resp.text
    assert "New chat" in resp.text
    assert "conversation_id" in resp.text


def test_chat_page_has_department_selector(client):
    resp = client.get("/chat")
    assert 'id="dept"' in resp.text            # the dropdown element
    assert "/chat/api/domains" in resp.text    # populated from the live list
    assert "domain" in resp.text               # sent with each request


def test_chat_page_renders_markdown_and_downscales_images(client):
    resp = client.get("/chat")
    assert "renderMarkdown" in resp.text   # bot answers rendered as formatted markdown
    assert "toBlob" in resp.text           # images downscaled in-browser before upload


def test_chat_page_streams_tokens(client):
    resp = client.get("/chat")
    assert "EventSource" in resp.text                 # live token streaming
    assert "/chat/api/stream/" in resp.text


def test_chat_page_has_status_bar_and_progress(client):
    resp = client.get("/chat")
    assert "/chat/api/status" in resp.text            # readiness polling
    assert 'id="statusbar"' in resp.text
    assert 'id="progfill"' in resp.text               # warmup progress bar


def test_chat_page_has_stats_and_dicom(client):
    resp = client.get("/chat")
    assert 'id="statsBtn"' in resp.text               # response-speed panel toggle
    assert "tok/s" in resp.text
    assert ".dcm" in resp.text                         # DICOM upload accepted


def test_chat_query_proxies_without_key(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "chat-q-1"
        mock_q.return_value.enqueue.return_value = mock_job
        # No X-API-Key header — the server supplies the shared identity.
        resp = client.post("/chat/api/query", json={"question": "what is this?"})
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "chat-q-1"


def test_chat_analyze_proxies_without_key(client, chat_enabled, sample_jpeg):
    with patch("app.routes._analyze.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "chat-a-1"
        mock_q.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/chat/api/analyze",
            files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "chat-a-1"


def test_chat_jobs_proxies_without_key(client, chat_enabled):
    job = MagicMock()
    job.get_status.return_value = "started"
    job.result = None
    with patch("app.routes.jobs.Job.fetch", return_value=job):
        resp = client.get("/chat/api/jobs/abc")
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"


def test_chat_disabled_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "chat_api_key", "")
    resp = client.post("/chat/api/query", json={"question": "hi"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "chat_disabled"


CID = "33333333-3333-4333-8333-333333333333"


def test_chat_query_passes_conversation_id(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        resp = client.post("/chat/api/query", json={"question": "hi", "conversation_id": CID})
    assert resp.status_code == 202
    assert mock_q.return_value.enqueue.call_args.args[6] == CID


def test_chat_analyze_passes_conversation_id(client, chat_enabled, sample_jpeg):
    with patch("app.routes._analyze.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="a1")
        resp = client.post(
            "/chat/api/analyze",
            files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
            data={"question": "what is this?", "conversation_id": CID},
        )
    assert resp.status_code == 202
    assert mock_q.return_value.enqueue.call_args.args[6] == CID


def test_chat_query_invalid_conversation_id_falls_back_stateless(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        resp = client.post("/chat/api/query", json={"question": "hi", "conversation_id": "not-a-uuid"})
    assert resp.status_code == 202  # never an error
    assert mock_q.return_value.enqueue.call_args.args[6] is None


def test_chat_query_missing_conversation_id_is_stateless(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        resp = client.post("/chat/api/query", json={"question": "hi"})
    assert resp.status_code == 202
    assert mock_q.return_value.enqueue.call_args.args[6] is None


def test_chat_domains_endpoint_lists_registered_domains(client):
    resp = client.get("/chat/api/domains")
    assert resp.status_code == 200
    domains = resp.json()["domains"]
    for d in ("general", "cardiology", "hematology", "rheumatology"):
        assert d in domains


def test_chat_query_uses_selected_domain(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        client.post("/chat/api/query", json={"question": "hi", "domain": "cardiology"})
    assert mock_q.return_value.enqueue.call_args.args[2] == "cardiology"


def test_chat_analyze_uses_selected_domain(client, chat_enabled, sample_jpeg):
    with patch("app.routes._analyze.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="a1")
        client.post(
            "/chat/api/analyze",
            files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
            data={"question": "what is this?", "domain": "rheumatology"},
        )
    assert mock_q.return_value.enqueue.call_args.args[2] == "rheumatology"


def test_chat_query_invalid_domain_falls_back_general(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        resp = client.post("/chat/api/query", json={"question": "hi", "domain": "bogus"})
    assert resp.status_code == 202  # never an error
    assert mock_q.return_value.enqueue.call_args.args[2] == "general"


def test_chat_query_default_domain_is_general(client, chat_enabled):
    with patch("app.routes._query.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="j1")
        client.post("/chat/api/query", json={"question": "hi"})
    assert mock_q.return_value.enqueue.call_args.args[2] == "general"


def test_chat_analyze_accepts_dicom(client, chat_enabled, sample_dicom):
    # A .dcm upload is transcoded to PNG server-side, then enqueued like any image.
    with patch("app.routes._analyze.Queue") as mock_q:
        mock_q.return_value.enqueue.return_value = MagicMock(id="dcm-1")
        resp = client.post(
            "/chat/api/analyze",
            files={"image": ("scan.dcm", io.BytesIO(sample_dicom), "application/dicom")},
            data={"domain": "radiology"},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "dcm-1"


def test_chat_status_reports_model_readiness(client):
    resp = client.get("/chat/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["model_ready"], bool)
    assert "detail" in body


def test_chat_stream_relays_worker_frames(client, chat_enabled, seeded_redis):
    # Seed the token-relay list the worker would populate, then drain it via SSE.
    import json as _json
    seeded_redis.rpush("chat:stream:jT", _json.dumps({"t": "delta", "text": "Hello"}))
    seeded_redis.rpush("chat:stream:jT", _json.dumps({"t": "done", "stats": {"tokens_per_second": 12.0}}))
    resp = client.get("/chat/api/stream/jT")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert '"t": "delta"' in resp.text and "Hello" in resp.text
    assert '"t": "done"' in resp.text


def test_chat_stream_disabled_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "chat_api_key", "")
    resp = client.get("/chat/api/stream/whatever")
    assert resp.status_code == 503
