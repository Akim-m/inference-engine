import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.deps import get_redis


@pytest.fixture
def client(seeded_redis):
    app.dependency_overrides[get_redis] = lambda: seeded_redis
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _mock_job(status, result=None):
    job = MagicMock()
    job.get_status.return_value = status
    job.result = result
    return job


def test_queued_job_returns_pending(client, valid_key):
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("queued")):
        resp = client.get("/v1/jobs/abc", headers={"X-API-Key": valid_key})
    assert resp.json()["status"] == "pending"


def test_started_job_returns_processing(client, valid_key):
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("started")):
        resp = client.get("/v1/jobs/abc", headers={"X-API-Key": valid_key})
    assert resp.json()["status"] == "processing"


def test_finished_job_returns_completed_with_result(client, valid_key):
    result = {"raw": "findings text", "structured": {"findings": "opacity"}}
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("finished", result=result)):
        resp = client.get("/v1/jobs/abc", headers={"X-API-Key": valid_key})
    data = resp.json()
    assert data["status"] == "completed"
    assert data["result"]["raw"] == "findings text"


def test_failed_job_returns_failed(client, valid_key):
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("failed")):
        resp = client.get("/v1/jobs/abc", headers={"X-API-Key": valid_key})
    assert resp.json()["status"] == "failed"
    assert resp.json()["error"] == "inference_failed"


def test_unknown_job_returns_404(client, valid_key):
    from rq.exceptions import NoSuchJobError
    with patch("app.routes.jobs.Job.fetch", side_effect=NoSuchJobError("x")):
        resp = client.get("/v1/jobs/nonexistent", headers={"X-API-Key": valid_key})
    assert resp.status_code == 404
    assert resp.json()["error"] == "job_not_found"


def test_cannot_poll_other_tenants_job(client, seeded_redis, valid_key):
    seeded_redis.set("job_owner:other-job-id", "some-other-key-hash", ex=3600)
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("queued")):
        resp = client.get("/v1/jobs/other-job-id", headers={"X-API-Key": valid_key})
    assert resp.status_code == 404


# --- fetch_job_status: the extracted core reused by the /chat proxy ---

def test_fetch_job_status_completed(seeded_redis, valid_key_hash):
    from app.routes.jobs import fetch_job_status
    result = {"raw": "findings text", "structured": {"findings": "opacity"}}
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("finished", result=result)):
        resp = fetch_job_status("job1", valid_key_hash, seeded_redis)
    assert resp.status == "completed"
    assert resp.result.raw == "findings text"


def test_fetch_job_status_rejects_other_owner(seeded_redis, valid_key_hash):
    from app.routes.jobs import fetch_job_status
    seeded_redis.set("job_owner:job2", "some-other-key-hash", ex=3600)
    with patch("app.routes.jobs.Job.fetch", return_value=_mock_job("queued")):
        with pytest.raises(HTTPException) as exc:
            fetch_job_status("job2", valid_key_hash, seeded_redis)
    assert exc.value.status_code == 404
