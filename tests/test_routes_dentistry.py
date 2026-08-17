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


def test_analyze_returns_job_id(client, valid_key, sample_jpeg):
    with patch("app.routes._analyze.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "dent-job-001"
        mock_q.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/v1/dentistry/analyze",
            files={"image": ("xray.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
            headers={"X-API-Key": valid_key},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "dent-job-001"


def test_query_returns_job_id(client, valid_key):
    with patch("app.routes._query.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "dent-query-001"
        mock_q.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/v1/dentistry/query",
            json={"question": "What are early signs of periodontitis?"},
            headers={"X-API-Key": valid_key},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "dent-query-001"


def test_query_requires_auth(client):
    resp = client.post("/v1/dentistry/query", json={"question": "test"})
    assert resp.status_code == 422


def test_query_rejects_invalid_key(client):
    resp = client.post(
        "/v1/dentistry/query",
        json={"question": "test"},
        headers={"X-API-Key": "invalid"},
    )
    assert resp.status_code == 401


def test_query_rejects_empty_question(client, valid_key):
    resp = client.post(
        "/v1/dentistry/query",
        json={"question": ""},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422


def test_analyze_rejects_invalid_file(client, valid_key):
    resp = client.post(
        "/v1/dentistry/analyze",
        files={"image": ("report.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_file"
