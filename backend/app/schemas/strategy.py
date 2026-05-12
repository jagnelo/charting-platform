from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.strategy import (
    StrategyDefinitionType,
    StrategySourceType,
    StrategyTestMode,
)


class StrategyVersionSeed(BaseModel):
    definition_snapshot: dict = Field(default_factory=dict)
    parameter_schema: dict = Field(default_factory=dict)
    default_parameters: dict = Field(default_factory=dict)
    universe_config: dict = Field(default_factory=dict)
    benchmark_config: dict = Field(default_factory=dict)
    execution_model: dict = Field(default_factory=dict)
    notes: str | None = None


class StrategyDefinitionCreate(BaseModel):
    name: str
    description: str | None = None
    source_type: StrategySourceType = StrategySourceType.CUSTOM
    definition_type: StrategyDefinitionType = StrategyDefinitionType.RULES
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    initial_version: StrategyVersionSeed = Field(default_factory=StrategyVersionSeed)


class StrategyDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    source_type: StrategySourceType | None = None
    definition_type: StrategyDefinitionType | None = None
    is_active: bool | None = None
    tags: list[str] | None = None
    metadata: dict | None = None


class StrategyVersionCreate(StrategyVersionSeed):
    pass


class StrategyRunCreate(BaseModel):
    test_mode: StrategyTestMode = StrategyTestMode.BACKTEST
    timeframe: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    parameter_values: dict = Field(default_factory=dict)
    universe_config: dict | None = None
    benchmark_config: dict | None = None
    execution_assumptions: dict = Field(default_factory=dict)


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    version_number: int
    definition_snapshot: dict
    parameter_schema: dict
    default_parameters: dict
    universe_config: dict
    benchmark_config: dict
    execution_model: dict
    notes: str | None
    is_current: bool
    created_at: datetime
    updated_at: datetime


class StrategyRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    strategy_version_id: int
    requested_by_user_id: int
    test_mode: str
    status: str
    timeframe: str | None
    started_at: datetime | None
    completed_at: datetime | None
    date_from: datetime | None
    date_to: datetime | None
    parameter_values: dict
    universe_config: dict
    benchmark_config: dict
    execution_assumptions: dict
    engine_run_ref: str | None
    result_summary: dict
    artifact_manifest: dict
    warning_log: list
    error_log: str | None
    created_at: datetime
    updated_at: datetime


class StrategyDefinitionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str | None
    source_type: str
    definition_type: str
    is_active: bool
    tags: list
    metadata: dict = Field(validation_alias="metadata_json")
    versions: list[StrategyVersionOut] = Field(default_factory=list)
    runs: list[StrategyRunOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class StrategyDefinitionDetailOut(StrategyDefinitionSummaryOut):
    pass


class StrategyRunSubmitOut(StrategyRunOut):
    pass
