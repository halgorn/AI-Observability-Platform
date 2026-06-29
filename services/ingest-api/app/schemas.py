from __future__ import annotations

import pathlib
import re
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


EventType = Literal[
    "llm.call", "tool.invoke", "handoff", "checkpoint",
    "error", "judge.result", "run.start", "run.end",
    "step.start", "step.end", "artifact.link",
]

ErrorCode = Literal[
    "LLM_TIMEOUT", "LLM_RATE_LIMIT", "LLM_INVALID_OUTPUT",
    "TOOL_TIMEOUT", "TOOL_NOT_FOUND", "TOOL_INVALID_ARGS",
    "HANDOFF_REJECTED", "CHECKPOINT_MISSING", "REPLAY_DIVERGED",
    "JUDGE_DISAGREEMENT", "INGEST_REJECTED", "SCHEMA_INVALID",
    "AUTH_MISSING", "AUTH_FORBIDDEN", "AUTH_ROLE_INSUFFICIENT",
    "AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_INVALID",
    "BUDGET_EXCEEDED", "PII_DETECTED",
    "GDPR_ERASURE_PENDING", "GDPR_ERASURE_FAILED", "GDPR_EXPORT_FORBIDDEN",
    "SANDBOX_BOOT_FAILED", "SANDBOX_SECCOMP_VIOLATION",
    "SANDBOX_NETWORK_VIOLATION", "SANDBOX_TIMEOUT", "SANDBOX_OOM",
    "SPEC_VERSION_UNSUPPORTED", "RATE_LIMITED",
    "RUN_NOT_FOUND", "RUN_ALREADY_TERMINAL",
    "INTERNAL_ERROR", "DEPENDENCY_DOWN", "UNKNOWN",
]

SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
AGENT_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
TOOL_RE = re.compile(r"^[a-z0-9_.-]{1,64}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RunStartPayload(_Strict):
    input_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    input_size: int | None = Field(default=None, ge=0)
    input_ref: str | None = None
    agent: Annotated[str, Field(pattern=AGENT_RE.pattern)]
    thread_id: str | None = None
    prompt_version: Annotated[str | None, Field(default=None, pattern=r"^v\d+\.\d+\.\d+$")]
    parent_run_id: str | None = None
    squad: list[str] | None = None


class RunEndPayload(_Strict):
    status: Literal["succeeded", "failed", "timeout", "cancelled"]
    output_hash: Annotated[str | None, Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")]
    output_size: int | None = Field(default=None, ge=0)
    output_ref: str | None = None
    total_steps: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0)
    failure_step: int | None = Field(default=None, ge=0)


class StepStartPayload(_Strict):
    step: int = Field(ge=0)
    agent: Annotated[str | None, Field(default=None, pattern=AGENT_RE.pattern)]
    intent: str | None = Field(default=None, max_length=200)


class StepEndPayload(_Strict):
    step: int = Field(ge=0)
    status: Literal["succeeded", "failed", "timeout", "cancelled", "skipped"]
    state_hash: Annotated[str | None, Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")]


class LlmCallPayload(_Strict):
    model: Annotated[str, Field(pattern=r"^[a-z0-9_-]+/[a-z0-9._:-]+$")]
    messages_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    messages_size: int = Field(ge=0)
    messages_ref: str | None = None
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "error"]
    system_prompt_version: Annotated[str | None, Field(default=None, pattern=r"^v\d+\.\d+\.\d+$")]
    cache_hit: bool = False
    stream: bool = False


class ToolInvokePayload(_Strict):
    tool: Annotated[str, Field(pattern=TOOL_RE.pattern)]
    args_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    args_ref: str | None = None
    result_hash: Annotated[str | None, Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")]
    result_size: int | None = Field(default=None, ge=0)
    result_ref: str | None = None
    cache_hit: bool = False
    retry_count: int = Field(default=0, ge=0, le=10)
    side_effect: bool = False


class HandoffPayload(_Strict):
    from_: Annotated[str, Field(alias="from", pattern=AGENT_RE.pattern)]
    to: Annotated[str, Field(pattern=AGENT_RE.pattern)]
    reason: Literal["delegation", "escalation", "fallback", "retry"]
    payload_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    payload_ref: str | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CheckpointPayload(_Strict):
    step: int = Field(ge=0)
    state_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    state_size: int | None = Field(default=None, ge=0)
    state_ref: str | None = None
    thread_id: str | None = None


class ErrorPayload(_Strict):
    code: ErrorCode
    message: str = Field(max_length=2000)
    retryable: bool = False
    stack: str | None = None
    cause: str | None = None


class JudgeResultPayload(_Strict):
    model: Annotated[str, Field(pattern=r"^[a-z0-9_-]+/[a-z0-9._:-]+$")]
    dimension: Literal["factuality", "relevance", "harmfulness", "coherence", "completeness"]
    score: float = Field(ge=0, le=1)
    rationale: str | None = Field(default=None, max_length=1000)
    cache_hit: bool = False
    prompt_version: Annotated[str | None, Field(default=None, pattern=r"^v\d+\.\d+\.\d+$")]


class ArtifactLinkPayload(_Strict):
    artifact_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    kind: Literal["prompt", "agent_code", "tool_io", "llm_io", "embedding"]
    ref: str
    size_bytes: int = Field(ge=0)


Payload = Union[
    RunStartPayload, RunEndPayload, StepStartPayload, StepEndPayload,
    LlmCallPayload, ToolInvokePayload, HandoffPayload, CheckpointPayload,
    ErrorPayload, JudgeResultPayload, ArtifactLinkPayload,
]


PAYLOAD_MODELS: dict[EventType, type[_Strict]] = {
    "run.start": RunStartPayload,
    "run.end": RunEndPayload,
    "step.start": StepStartPayload,
    "step.end": StepEndPayload,
    "llm.call": LlmCallPayload,
    "tool.invoke": ToolInvokePayload,
    "handoff": HandoffPayload,
    "checkpoint": CheckpointPayload,
    "error": ErrorPayload,
    "judge.result": JudgeResultPayload,
    "artifact.link": ArtifactLinkPayload,
}


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    run_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    parent_span_id: str | None = Field(default=None, pattern=SPAN_ID_RE.pattern)
    span_id: str = Field(pattern=SPAN_ID_RE.pattern)
    type: EventType
    agent: str | None = Field(default=None, pattern=AGENT_RE.pattern)
    tool: str | None = Field(default=None, pattern=TOOL_RE.pattern)
    llm_model: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    error_code: ErrorCode | None = None
    payload: dict[str, Any]
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ended_at")
    @classmethod
    def ended_after_started(cls, v: datetime | None, info: Any) -> datetime | None:
        if v is not None and "started_at" in info.data:
            if v < info.data["started_at"]:
                raise ValueError("ended_at must be >= started_at")
        return v

    def validated_payload(self) -> _Strict:
        model = PAYLOAD_MODELS[self.type]
        return model.model_validate(self.payload)


class IngestRequest(BaseModel):
    events: list[Event] = Field(min_length=1, max_length=1000)


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    rejected_details: list[dict[str, Any]] = Field(default_factory=list)
