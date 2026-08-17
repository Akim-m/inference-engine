import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.deps import get_redis


@pytest.fixture
def client(seeded_redis):
    app.dependency_overrides[get_redis] = lambda: seeded_redis
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_submit_returns_job_id(client, valid_key, sample_jpeg):
    with patch("app.routes._analyze.Queue") as mock_q_cls:
        mock_job = MagicMock()
        mock_job.id = "gen-job-123"
        mock_q_cls.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/v1/general/analyze",
            files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
            headers={"X-API-Key": valid_key},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "gen-job-123"


def test_requires_auth_missing_header(client, sample_jpeg):
    resp = client.post(
        "/v1/general/analyze",
        files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
    )
    assert resp.status_code == 422  # missing required header


def test_requires_auth_invalid_key(client, sample_jpeg):
    resp = client.post(
        "/v1/general/analyze",
        files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        headers={"X-API-Key": "invalid-key"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_key"


def test_rejects_invalid_mime(client, valid_key):
    resp = client.post(
        "/v1/general/analyze",
        files={"image": ("scan.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_file"


def test_query_returns_job_id(client, valid_key):
    with patch("app.routes._query.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "gen-query-001"
        mock_q.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/v1/general/query",
            json={"question": "What could this rash be?"},
            headers={"X-API-Key": valid_key},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "gen-query-001"


def test_query_rejects_empty_question(client, valid_key):
    resp = client.post(
        "/v1/general/query",
        json={"question": ""},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422


def test_v1_query_enqueues_stateless(client, valid_key):
    # /v1 must never carry a conversation_id — the trailing enqueue arg stays None.
    with patch("app.routes._query.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "j1"
        mock_q.return_value.enqueue.return_value = mock_job
        client.post("/v1/general/query", json={"question": "hi"},
                    headers={"X-API-Key": valid_key})
    assert mock_q.return_value.enqueue.call_args.args[6] is None


def test_v1_analyze_enqueues_stateless(client, valid_key, sample_jpeg):
    with patch("app.routes._analyze.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "j2"
        mock_q.return_value.enqueue.return_value = mock_job
        client.post(
            "/v1/general/analyze",
            files={"image": ("scan.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
            headers={"X-API-Key": valid_key},
        )
    assert mock_q.return_value.enqueue.call_args.args[6] is None
