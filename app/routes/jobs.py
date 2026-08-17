from fastapi import APIRouter, Depends, HTTPException
from rq.exceptions import NoSuchJobError
from rq.job import Job
from app.auth import require_api_key_read
from app.deps import get_redis
from app.schemas import InferenceResult, JobResponse
from config import make_redis
import structlog

router = APIRouter()
log = structlog.get_logger()

# Separate connection without decode_responses — RQ stores results as binary pickle
_rq_redis = None
def _get_rq_redis():
    global _rq_redis
    if _rq_redis is None:
        _rq_redis = make_redis(decode_responses=False)
    return _rq_redis

_STATUS = {
    "queued": "pending", "deferred": "pending", "scheduled": "pending",
    "started": "processing",
    "finished": "completed",
    "failed": "failed", "stopped": "failed", "canceled": "failed",
}


def fetch_job_status(job_id: str, key_hash: str, r) -> JobResponse:
    """Load a job's status/result, scoped to `key_hash`. Shared by the authed
    `/v1/jobs/{id}` route and the key-less `/chat/api/jobs/{id}` proxy."""
    try:
        job = Job.fetch(job_id, connection=_get_rq_redis())
    except NoSuchJobError:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"Job {job_id} not found"},
        )

    owner = r.get(f"job_owner:{job_id}")
    if owner is not None and owner != key_hash:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"Job {job_id} not found"},
        )

    # Job.fetch already loaded the hash; reuse the cached status (no extra round-trip)
    raw_status = str(job.get_status(refresh=False))
    status = _STATUS.get(raw_status)
    if status is None:
        log.warning("unknown_job_status", job_id=job_id, raw_status=raw_status)
        status = "pending"

    if status == "completed" and job.result:
        return JobResponse(status="completed", result=InferenceResult(**job.result))

    if status == "failed":
        return JobResponse(status="failed", error="inference_failed")

    return JobResponse(status=status)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    key_hash: str = Depends(require_api_key_read),
    r=Depends(get_redis),
):
    return fetch_job_status(job_id, key_hash, r)
