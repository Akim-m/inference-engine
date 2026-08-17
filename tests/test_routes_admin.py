import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.deps import get_redis
from config import settings


@pytest.fixture
def client(fake_redis):
    app.dependency_overrides[get_redis] = lambda: fake_redis
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def set_admin_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "test-admin-key")


def test_create_key_returns_64_char_hex(client):
    resp = client.post("/v1/admin/keys", headers={"X-API-Key": "test-admin-key"})
    assert resp.status_code == 201
    assert len(resp.json()["key"]) == 64


def test_create_key_rejects_wrong_admin_key(client):
    resp = client.post("/v1/admin/keys", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_revoke_key_removes_hash_from_redis(client, fake_redis):
    from app.auth import hash_key
    key = "a" * 64
    fake_redis.sadd("api_keys", hash_key(key))
    resp = client.delete(f"/v1/admin/keys/{key}", headers={"X-API-Key": "test-admin-key"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Key revoked"
    assert not fake_redis.sismember("api_keys", hash_key(key))


def test_revoke_nonexistent_key_returns_404(client):
    resp = client.delete("/v1/admin/keys/doesnotexist", headers={"X-API-Key": "test-admin-key"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "key_not_found"


def test_create_key_503_when_admin_key_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "")
    resp = client.post("/v1/admin/keys", headers={"X-API-Key": "anything"})
    assert resp.status_code == 503
