import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()

app = FastAPI(title="MedGemma API", version="1.0.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": str(exc)},
    )


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.error("unhandled_exception", exc_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred"},
    )


from app.routes import jobs, admin, chat  # noqa: E402
from app.routes._domain import make_domain_router  # noqa: E402
from app.domains import DOMAINS  # noqa: E402  (single source of truth; see app/domains.py)

for _domain in DOMAINS:
    app.include_router(make_domain_router(_domain), prefix="/v1")

app.include_router(jobs.router, prefix="/v1")
app.include_router(admin.router, prefix="/v1")
app.include_router(chat.router)  # /chat + key-less /chat/api/* proxy (no /v1 prefix)
