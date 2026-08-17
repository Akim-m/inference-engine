from fastapi import APIRouter, Depends, File, Form, UploadFile
from app.auth import check_job_quota
from app.deps import get_redis
from app.routes._analyze import submit_analysis
from app.routes._query import submit_query
from app.schemas import JobSubmitted, TextQueryRequest


def make_domain_router(domain: str) -> APIRouter:
    """Build the analyze + query endpoints for one medical domain.

    Every domain exposes the identical surface; only the domain string differs
    (the per-domain prompt lives in worker/prompts.py and the parser in
    worker/inference.py). Endpoint names are pinned to analyze_<domain> /
    query_<domain> so the generated OpenAPI operationIds are byte-for-byte the
    same as the original per-domain route modules.
    """
    router = APIRouter()

    @router.post(
        f"/{domain}/analyze",
        response_model=JobSubmitted,
        status_code=202,
        name=f"analyze_{domain}",
    )
    async def analyze(
        image: UploadFile = File(...),
        question: str = Form(default="", max_length=500),
        key_hash: str = Depends(check_job_quota),
        r=Depends(get_redis),
    ):
        return await submit_analysis(domain, image, question, key_hash, r)

    @router.post(
        f"/{domain}/query",
        response_model=JobSubmitted,
        status_code=202,
        name=f"query_{domain}",
    )
    async def query(
        body: TextQueryRequest,
        key_hash: str = Depends(check_job_quota),
        r=Depends(get_redis),
    ):
        return await submit_query(domain, body.question, key_hash, r)

    return router
