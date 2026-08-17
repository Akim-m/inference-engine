import time
import httpx
import structlog
from multiprocessing import Process
from typing import Optional
from rq import Queue
from rq.worker import SimpleWorker
from config import make_redis, settings

log = structlog.get_logger()


def wait_for_vllm(base_url: str, retries: int = 60, delay: float = 5.0) -> None:
    """Block until the vLLM server's /health returns 200, or raise after retries."""
    health_url = base_url.rsplit("/v1", 1)[0] + "/health"
    for attempt in range(retries):
        try:
            resp = httpx.get(health_url, timeout=5.0)
            if resp.status_code == 200:
                log.info("vllm_ready", url=health_url)
                return
        except Exception as exc:
            log.debug("vllm_health_check_error", url=health_url, error=str(exc))
        log.info("vllm_waiting", url=health_url, attempt=attempt + 1)
        if attempt < retries - 1:
            time.sleep(delay)
    raise RuntimeError(f"vLLM not ready after {retries} attempts at {health_url}")


def _run_single_worker() -> None:
    """One blocking RQ worker. Each replica gets its own Redis connection."""
    conn = make_redis(decode_responses=False)
    q = Queue("troke-jobs", connection=conn)
    SimpleWorker([q], connection=conn).work()


def main(replicas: Optional[int] = None) -> None:
    """Start `replicas` worker processes (default: settings.worker_replicas).

    The workers are stateless HTTP clients with no GPU/model. Running several keeps
    that many requests in flight so the single vLLM server's continuous batcher stays
    fed — the cheap throughput win. vLLM itself remains exactly one process.
    """
    n = settings.worker_replicas if replicas is None else replicas
    wait_for_vllm(settings.vllm_url)
    if n <= 1:
        log.info("worker_starting", queue="troke-jobs", replicas=1)
        _run_single_worker()
        return
    log.info("worker_pool_starting", queue="troke-jobs", replicas=n)
    procs = [Process(target=_run_single_worker) for _ in range(n)]
    for p in procs:
        p.start()
    try:
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
