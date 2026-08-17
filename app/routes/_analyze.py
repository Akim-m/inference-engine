import uuid
import structlog
from fastapi import HTTPException, UploadFile
from rq import Queue
from app.files import validate_image, is_dicom, dicom_to_png
from app.schemas import JobSubmitted
from config import settings

log = structlog.get_logger()

_MAX = 10 * 1024 * 1024


async def submit_analysis(
    domain: str,
    image: UploadFile,
    question: str,
    key_hash: str,
    r,
    conversation_id: str | None = None,
) -> JobSubmitted:
    content = await image.read(_MAX + 1)
    if len(content) > _MAX:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_file", "message": "File exceeds 10MB limit"},
        )
    # DICOM uploads are transcoded to PNG here so the worker/vLLM only ever see a
    # standard image; everything else must already be JPEG/PNG.
    if is_dicom(content):
        content = dicom_to_png(content)
    else:
        validate_image(content)

    job_id = str(uuid.uuid4())
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = settings.temp_dir / f"{job_id}.img"
    temp_path.write_bytes(content)

    try:
        q = Queue("troke-jobs", connection=r)
        job = q.enqueue(
            "worker.worker.process_job",
            job_id, domain, str(temp_path), question, key_hash, conversation_id,
            job_id=job_id,
            job_timeout=3600,  # 1h — covers model download on cold start
            result_ttl=settings.job_ttl_seconds,
            failure_ttl=settings.job_ttl_seconds,
        )
        r.sadd(f"pending:{key_hash}", job_id)
        r.set(f"job_owner:{job_id}", key_hash, ex=settings.job_ttl_seconds)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    log.info("job_enqueued", job_id=job_id, domain=domain,
             file_size_bytes=len(content), key_hash=key_hash)
    return JobSubmitted(job_id=job.id)
