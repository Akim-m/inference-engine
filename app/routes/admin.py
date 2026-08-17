import os
from fastapi import APIRouter, Depends, HTTPException
from app.auth import hash_key, require_admin_key
from app.deps import get_redis
from app.schemas import CreateKeyResponse

router = APIRouter()


@router.post("/admin/keys", response_model=CreateKeyResponse, status_code=201,
             dependencies=[Depends(require_admin_key)])
async def create_key(r=Depends(get_redis)):
    key = os.urandom(32).hex()
    r.sadd("api_keys", hash_key(key))
    return CreateKeyResponse(key=key)


@router.delete("/admin/keys/{key}", dependencies=[Depends(require_admin_key)])
async def revoke_key(key: str, r=Depends(get_redis)):
    removed = r.srem("api_keys", hash_key(key))
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={"error": "key_not_found", "message": "Key not found"},
        )
    return {"message": "Key revoked"}
