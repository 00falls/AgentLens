from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, StrictBool, model_validator


class TimeWindow(BaseModel):
    service: str = Field(min_length=1)
    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        return self


class LogQuery(TimeWindow):
    level: Literal["INFO", "WARN", "ERROR"] | None = None
    limit: int = Field(default=50, ge=1, le=200)


class MetricQuery(TimeWindow):
    metric_name: str | None = None
    limit: int = Field(default=100, ge=1, le=300)


class Diagnosis(BaseModel):
    status: Literal["diagnosed", "insufficient_evidence"]
    cause_summary: str = Field(min_length=1)
    evidence_ids: list[str]
    unknowns: list[str]
    next_steps: list[str]


class RunbookQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)


class AnalysisQuery(BaseModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    python_code: str = Field(min_length=1, max_length=6000)


class InvokeRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=50)
    prompt: str = Field(min_length=1, max_length=8000)


class ExperienceContext(TimeWindow):
    service: str = Field(min_length=1, max_length=80)
    applicability: str = Field(min_length=1, max_length=2000)


class ThreadRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    experience: ExperienceContext | None = None


class ResumeRequest(BaseModel):
    checkpoint_id: str = Field(min_length=1, max_length=100)
    approved: StrictBool | None = None


class ExperienceQuery(BaseModel):
    service: str = Field(min_length=1, max_length=80)
    limit: int = Field(default=5, ge=1, le=20)


class RunListQuery(BaseModel):
    thread_id: str | None = Field(default=None, min_length=1, max_length=36)
    status: (
        Literal[
            "running",
            "diagnosed",
            "insufficient_evidence",
            "interrupted",
            "failed",
            "cancelled",
            "replay_mismatch",
        ]
        | None
    ) = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class EvaluationCase(TimeWindow):
    case_id: str
    scenario_id: str
    project_id: str
    input: str
    expected_status: Literal["diagnosed", "insufficient_evidence"]
    expected_cause: str
    cause_terms: list[list[str]]
    required_tools: list[str]
    required_evidence: list[str]
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    scenario_group: str | None = None
    split: Literal["dev", "holdout"] | None = None
    synthetic: bool = True
    critical: bool = False
    forbidden_tools: list[str] = Field(default_factory=list)
    tool_parameters: dict[str, dict] = Field(default_factory=dict)
    tool_order: list[tuple[str, str]] = Field(default_factory=list)


class ReplayRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=100)


class FreezeRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=120)
    source_run_id: str | None = Field(default=None, min_length=1, max_length=36)
