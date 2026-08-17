from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class JobSubmitted(BaseModel):
    job_id: str


class RadiologyStructured(BaseModel):
    findings: str
    impression: str
    severity: Literal["normal", "mild", "moderate", "severe"]
    confidence: Literal["low", "medium", "high"]


class DermatologyStructured(BaseModel):
    condition: str
    severity: Literal["low", "moderate", "high"]
    recommendation: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class PathologyStructured(BaseModel):
    diagnosis: str
    tissue_type: str
    severity: Literal["normal", "mild", "moderate", "severe"]
    confidence: Literal["low", "medium", "high"]


class OphthalmologyStructured(BaseModel):
    finding: str
    affected_structure: str
    severity: Literal["normal", "mild", "moderate", "severe"]
    confidence: Literal["low", "medium", "high"]


class TextQueryStructured(BaseModel):
    answer: str
    confidence: Literal["low", "medium", "high"]


class TextQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    # Optional /chat conversation thread. The /chat proxy validates + forwards it;
    # /v1 callers may send it but the route never forwards it (stays stateless).
    conversation_id: Optional[str] = None
    # Optional /chat department selector. Validated against DOMAINS in the proxy
    # (unknown → general). Ignored by /v1 routes (their domain is in the path).
    domain: Optional[str] = None


class InferenceStats(BaseModel):
    completion_tokens: Optional[int] = None
    inference_ms: Optional[int] = None
    tokens_per_second: Optional[float] = None


class InferenceResult(BaseModel):
    raw: str
    structured: Optional[dict[str, Any]] = None
    stats: Optional[InferenceStats] = None


class JobResponse(BaseModel):
    status: Literal["pending", "processing", "completed", "failed"]
    result: Optional[InferenceResult] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    message: str


class CreateKeyResponse(BaseModel):
    key: str
