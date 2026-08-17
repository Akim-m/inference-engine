import asyncio
import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from app.auth import (
    require_api_key, require_api_key_read, hash_key,
    enforce_submit_limits, enforce_read_limit,
)
from app.deps import get_redis


def make_app(fake_redis):
    app = FastAPI()
    app.dependency_overrides[get_redis] = lambda: fake_redis

    @app.get("/protected")
    async def protected(key_hash: str = Depends(require_api_key)):
        return {"key_hash": key_hash}

    return app


def make_read_app(fake_redis):
    app = FastAPI()
    app.dependency_overrides[get_redis] = lambda: fake_redis

    @app.get("/poll")
    async def poll(key_hash: str = Depends(require_api_key_read)):
        return {"key_hash": key_hash}

    return app


def test_valid_key_passes(seeded_redis, valid_key):
    client = TestClient(make_app(seeded_redis))
    resp = client.get("/protected", headers={"X-API-Key": valid_key})
    assert resp.status_code == 200
    assert resp.json()["key_hash"] == hash_key(valid_key)


def test_invalid_key_returns_401(seeded_redis):
    client = TestClient(make_app(seeded_redis))
    resp = client.get("/protected", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_key"


def test_rate_limit_returns_429(seeded_redis, valid_key):
    from config import settings
    client = TestClient(make_app(seeded_redis))
    for _ in range(settings.rate_limit_per_minute):
        client.get("/protected", headers={"X-API-Key": valid_key})
    resp = client.get("/protected", headers={"X-API-Key": valid_key})
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"


def test_hash_is_deterministic_and_not_plaintext(valid_key):
    h = hash_key(valid_key)
    assert h == hash_key(valid_key)
    assert h != valid_key


def test_reads_have_separate_budget_from_writes(seeded_redis, valid_key):
    """Exhausting the write budget must NOT block status polling (reads)."""
    from config import settings
    write_client = TestClient(make_app(seeded_redis))
    read_client = TestClient(make_read_app(seeded_redis))
    for _ in range(settings.rate_limit_per_minute):
        write_client.get("/protected", headers={"X-API-Key": valid_key})
    assert write_client.get("/protected", headers={"X-API-Key": valid_key}).status_code == 429
    assert read_client.get("/poll", headers={"X-API-Key": valid_key}).status_code == 200


def test_read_budget_exceeds_write_limit(seeded_redis, valid_key):
    """Polling well past the write limit stays OK — clients poll many times per job."""
    from config import settings
    client = TestClient(make_read_app(seeded_redis))
    for _ in range(settings.rate_limit_per_minute + 10):
        assert client.get("/poll", headers={"X-API-Key": valid_key}).status_code == 200


def test_read_rate_limit_enforced_at_its_own_limit(seeded_redis, valid_key, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "read_rate_limit_per_minute", 5)
    client = TestClient(make_read_app(seeded_redis))
    for _ in range(5):
        assert client.get("/poll", headers={"X-API-Key": valid_key}).status_code == 200
    resp = client.get("/poll", headers={"X-API-Key": valid_key})
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"] == "rate_limited"


# --- Header-free limit helpers (used by the key-less /chat proxy) ---

def test_enforce_submit_limits_over_rate_raises(seeded_redis, valid_key_hash):
    from config import settings
    for _ in range(settings.rate_limit_per_minute):
        asyncio.run(enforce_submit_limits(seeded_redis, valid_key_hash))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(enforce_submit_limits(seeded_redis, valid_key_hash))
    assert exc.value.status_code == 429
    assert exc.value.detail["error"] == "rate_limited"


def test_enforce_submit_limits_queue_full(seeded_redis, valid_key_hash):
    from config import settings
    for i in range(settings.max_pending_jobs_per_key):
        jid = f"job{i}"
        seeded_redis.sadd(f"pending:{valid_key_hash}", jid)
        seeded_redis.set(f"job_owner:{jid}", valid_key_hash)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(enforce_submit_limits(seeded_redis, valid_key_hash))
    assert exc.value.status_code == 429
    assert exc.value.detail["error"] == "queue_full"


def test_enforce_read_limit_uses_read_budget(seeded_redis, valid_key_hash, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "read_rate_limit_per_minute", 3)
    for _ in range(3):
        asyncio.run(enforce_read_limit(seeded_redis, valid_key_hash))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(enforce_read_limit(seeded_redis, valid_key_hash))
    assert exc.value.status_code == 429
    assert exc.value.detail["error"] == "rate_limited"
