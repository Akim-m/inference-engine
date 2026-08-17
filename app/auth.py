import hashlib
from fastapi import Depends, Header, HTTPException
from redis import Redis
from app.deps import get_redis
from config import settings


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _authenticate(x_api_key: str, r: Redis) -> str:
    key_hash = hash_key(x_api_key)
    if not r.sismember("api_keys", key_hash):
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_key", "message": "Invalid or missing API key"},
        )
    return key_hash


def _enforce_rate(r: Redis, key_hash: str, bucket: str, limit: int) -> None:
    rate_key = f"{bucket}:{key_hash}"
    count = r.incr(rate_key)
    if count == 1:
        r.expire(rate_key, 60)
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "message": "Rate limit exceeded"},
        )


async def require_api_key(
    x_api_key: str = Header(...),
    r: Redis = Depends(get_redis),
) -> str:
    # Write path (job submission): the stricter per-minute budget.
    key_hash = _authenticate(x_api_key, r)
    _enforce_rate(r, key_hash, "rate", settings.rate_limit_per_minute)
    return key_hash


async def require_api_key_read(
    x_api_key: str = Header(...),
    r: Redis = Depends(get_redis),
) -> str:
    # Read path (status polling): a separate, generous budget. A client polls a job many
    # times before it finishes, so reads must not drain the submit budget (or vice versa).
    key_hash = _authenticate(x_api_key, r)
    _enforce_rate(r, key_hash, "read_rate", settings.read_rate_limit_per_minute)
    return key_hash


def _check_pending_quota(r: Redis, key_hash: str) -> None:
    # Reconcile: remove stale job IDs whose job_owner key has expired. Batch the
    # existence checks into one pipeline instead of one round-trip per pending job,
    # then compute the active count locally rather than a follow-up SCARD.
    pending_key = f"pending:{key_hash}"
    members = list(r.smembers(pending_key))
    active = 0
    if members:
        pipe = r.pipeline()
        for jid in members:
            pipe.exists(f"job_owner:{jid}")
        alive_flags = pipe.execute()
        stale = [jid for jid, alive in zip(members, alive_flags) if not alive]
        if stale:
            r.srem(pending_key, *stale)
        active = len(members) - len(stale)

    if active >= settings.max_pending_jobs_per_key:
        raise HTTPException(
            status_code=429,
            detail={"error": "queue_full", "message": "Too many pending jobs for this key"},
        )


async def check_job_quota(
    key_hash: str = Depends(require_api_key),
    r: Redis = Depends(get_redis),
) -> str:
    _check_pending_quota(r, key_hash)
    return key_hash


async def enforce_submit_limits(r: Redis, key_hash: str) -> None:
    # Header-free write path for the /chat proxy: same write budget + pending quota as
    # require_api_key + check_job_quota, but the identity comes from the server, not a header.
    _enforce_rate(r, key_hash, "rate", settings.rate_limit_per_minute)
    _check_pending_quota(r, key_hash)


async def enforce_read_limit(r: Redis, key_hash: str) -> None:
    # Header-free read path for the /chat proxy: the separate, generous poll budget.
    _enforce_rate(r, key_hash, "read_rate", settings.read_rate_limit_per_minute)


async def require_admin_key(x_api_key: str = Header(...)) -> None:
    if not settings.admin_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "admin_disabled", "message": "Admin operations not configured"},
        )
    if x_api_key != settings.admin_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_key", "message": "Invalid admin key"},
        )
