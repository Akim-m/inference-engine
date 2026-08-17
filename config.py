from pathlib import Path
import tempfile
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://127.0.0.1:6379"
    redis_password: str = ""
    admin_key: str = ""
    chat_api_key: str = ""  # shared key the /chat proxy attaches server-side; empty = disabled
    model_id: str = "google/medgemma-4b-it"
    model_revision: str = ""
    hf_token: str = ""
    adapter_path: str = ""
    vllm_url: str = "http://vllm:8001/v1"
    vllm_model: str = ""
    max_output_tokens: int = 1536
    # A long rich-Markdown answer generates for ~90s on the serial fp8 GPU; vLLM is
    # non-streaming, so the whole generation must fit inside this single read timeout.
    # Keep it comfortably above the worst case or long answers fail with ReadTimeout.
    request_timeout_s: int = 240
    worker_replicas: int = 1
    temp_dir: Path = Path(tempfile.gettempdir()) / "troke"
    job_ttl_seconds: int = 3600
    max_pending_jobs_per_key: int = 10
    rate_limit_per_minute: int = 60          # write budget: job submissions
    read_rate_limit_per_minute: int = 600    # read budget: status polling (separate)
    # /chat conversation memory: bound how much prior history is threaded into the
    # model (char_budget) and how long it lives in Redis (max_turns entries, ttl).
    chat_memory_char_budget: int = 8000
    chat_memory_max_turns: int = 12
    chat_memory_ttl_seconds: int = 1800

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )


settings = Settings()

from redis import Redis as _Redis


def make_redis(decode_responses: bool = True) -> _Redis:
    return _Redis.from_url(
        settings.redis_url,
        password=settings.redis_password or None,
        decode_responses=decode_responses,
    )
