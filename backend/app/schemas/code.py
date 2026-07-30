"""Unified Python authoring validation contracts."""

from pydantic import BaseModel, ConfigDict, Field


class CodeValidationRequest(BaseModel):
    source: str = Field(min_length=1, max_length=500_000)


class CodeDiagnosticOut(BaseModel):
    code: str
    message: str
    line: int
    column: int


class CodeValidationOut(BaseModel):
    valid: bool
    diagnostics: list[CodeDiagnosticOut]
    dependencies: list[str]
    lookback_hint: int | None
    output_contracts: list[str] = Field(default_factory=list)
    execution_policy: str = "validation_only_isolated_runner_required"


class CodeVersionCreate(BaseModel):
    source: str = Field(min_length=1, max_length=500_000)
    output_contract: str = Field(pattern="^(scalar|series|boolean|events|study)$")
    parameter_schema: dict = Field(default_factory=dict)
    default_parameters: dict = Field(default_factory=dict)


class CodeAssetCreate(BaseModel):
    stable_key: str = Field(min_length=1, max_length=80, pattern="^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(pattern="^(plot|column|condition|signal|study)$")
    initial_version: CodeVersionCreate


class CodeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    source: str
    output_contract: str
    parameter_schema: dict
    default_parameters: dict
    sdk_version: str
    runtime_version: str
    dependencies: list
    lookback: int | None
    diagnostics: list


class CodeAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stable_key: str
    name: str
    kind: str
    is_archived: bool
    versions: list[CodeVersionOut]


class ResearchRunCreate(BaseModel):
    code_version_id: int
    run_config: dict = Field(default_factory=dict)
    dataset_manifest: dict = Field(default_factory=dict)


class ResearchArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    artifact_type: str
    name: str
    payload: dict


class ResearchRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code_version_id: int
    status: str
    run_config: dict
    dataset_manifest: dict
    reproducibility_hash: str | None
    diagnostics: list
    warnings: list
    resource_usage: dict
    logs: str
    artifacts: list[ResearchArtifactOut] = Field(default_factory=list)
