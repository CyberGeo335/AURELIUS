"""Module 3 response boundary; raw evidence remains inside PostgreSQL snapshots."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['PG-EVIDENCE-V1']
    mode: Literal['DEMO']
    case_id: str
    revision: int = Field(ge=1)
    borrower_id: str
    company_id: int = Field(gt=0)
    decision_at: datetime
    product_selection_ref: str
    requirements_ref: str
    features: dict[str, Any]
    baseline_feature_names: list[str]
    dynamic_feature_names: list[str]
    verified_facts: list[dict[str, Any]]
    data_quality: dict[str, Any]
    model_readiness: Literal['INSUFFICIENT_DATA']
    features_ready: Literal[False]
    next_module: None
    status: Literal['SNAPSHOT_READY']
    application_ids: dict[str, int]
    snapshot_ids: dict[str, int]
    unsupported_routes: list[str]
    questionnaire: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator('decision_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Snapshot cutoff requires timezone')
        return value
