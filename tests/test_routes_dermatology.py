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
        mock_job.id = "derm-job-456"
        mock_q_cls.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/v1/dermatology/analyze",
            files={"image": ("skin.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
            headers={"X-API-Key": valid_key},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "derm-job-456"


def test_requires_auth_missing_header(client, sample_jpeg):
    resp = client.post(
        "/v1/dermatology/analyze",
        files={"image": ("skin.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
    )
    assert resp.status_code == 422  # missing required header


def test_requires_auth_invalid_key(client, sample_jpeg):
    resp = client.post(
        "/v1/dermatology/analyze",
        files={"image": ("skin.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        headers={"X-API-Key": "invalid-key"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_key"


def test_rejects_invalid_mime(client, valid_key):
    resp = client.post(
        "/v1/dermatology/analyze",
        files={"image": ("skin.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_file"


def test_rejects_oversized_file(client, valid_key):
    big = b"\xff\xd8" + b"\x00" * (10 * 1024 * 1024)  # > 10MB, starts with JPEG magic
    resp = client.post(
        "/v1/dermatology/analyze",
        files={"image": ("big.jpg", io.BytesIO(big), "image/jpeg")},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_file"


def test_query_returns_job_id(client, valid_key):
    with patch("app.routes._query.Queue") as mock_q:
        mock_job = MagicMock()
        mock_job.id = "derm-query-001"
        mock_q.return_value.enqueue.return_value = mock_job
        resp = client.post(
            "/v1/dermatology/query",
            json={"question": "What does eczema look like?"},
            headers={"X-API-Key": valid_key},
        )
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "derm-query-001"


def test_query_rejects_empty_question(client, valid_key):
    resp = client.post(
        "/v1/dermatology/query",
        json={"question": ""},
        headers={"X-API-Key": valid_key},
    )
    assert resp.status_code == 422
