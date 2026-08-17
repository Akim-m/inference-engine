import uuid
import structlog
from rq import Queue
from app.schemas import JobSubmitted
from config import settings

log = structlog.get_logger()


async def submit_query(
    domain: str, question: str, key_hash: str, r, conversation_id: str | None = None
) -> JobSubmitted:
    job_id = str(uuid.uuid4())
    q = Queue("troke-jobs", connection=r)
    job = q.enqueue(
        "worker.worker.process_job",
        job_id, domain, "", question, key_hash, conversation_id,
        job_id=job_id,
        job_timeout=3600,
        result_ttl=settings.job_ttl_seconds,
        failure_ttl=settings.job_ttl_seconds,
    )
    r.sadd(f"pending:{key_hash}", job_id)
    r.set(f"job_owner:{job_id}", key_hash, ex=settings.job_ttl_seconds)
    log.info("query_enqueued", job_id=job_id, domain=domain, key_hash=key_hash)
    return JobSubmitted(job_id=job.id)
