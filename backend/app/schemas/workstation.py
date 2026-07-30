"""API contracts for the persisted TC2000-style workstation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceWindowInput(BaseModel):
    instance_key: str = Field(min_length=1, max_length=80)
    tool_type: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=160)
    link_group: str = Field(default="blue", max_length=24)
    configuration: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)
    state_schema_version: int = Field(default=1, ge=1)
    position: int = Field(default=0, ge=0)


class WorkspaceWindowOut(WorkspaceWindowInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tab_id: int
    created_at: datetime
    updated_at: datetime


class WorkspaceTabInput(BaseModel):
    stable_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    position: int = Field(default=0, ge=0)
    layout_config: dict = Field(default_factory=dict)
    active_window_key: str | None = Field(default=None, max_length=80)
    windows: list[WorkspaceWindowInput] = Field(default_factory=list)


class WorkspaceTabOut(WorkspaceTabInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    windows: list[WorkspaceWindowOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(default="US Top Down", min_length=1, max_length=120)
    is_default: bool = False
    position: int = Field(default=0, ge=0)
    schema_version: int = Field(default=1, ge=1)
    settings: dict = Field(default_factory=dict)
    tabs: list[WorkspaceTabInput] = Field(default_factory=list)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_default: bool | None = None
    position: int | None = Field(default=None, ge=0)
    schema_version: int | None = Field(default=None, ge=1)
    settings: dict | None = None


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    is_default: bool
    position: int
    revision: int
    schema_version: int
    settings: dict
    tabs: list[WorkspaceTabOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkspaceSnapshotWrite(BaseModel):
    base_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    settings: dict = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1)
    tabs: list[WorkspaceTabInput] = Field(default_factory=list)


class WorkspaceLibraryItemCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=48)
    stable_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    payload: dict = Field(default_factory=dict)
    dependency_metadata: dict = Field(default_factory=dict)


class WorkspaceLibraryItemOut(WorkspaceLibraryItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    version: int
    created_at: datetime
    updated_at: datetime


class InstrumentNoteWrite(BaseModel):
    content: str = Field(default="", max_length=100_000)


class InstrumentNoteOut(InstrumentNoteWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    instrument_id: int
    created_at: datetime
    updated_at: datetime


class InstrumentReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    is_active: bool


class MarketGroupMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    relationship_type: str
    weight: float | None
    position: int
    source: str
    verification_state: str
    effective_at: datetime | None
    known_at: datetime | None
    provenance: dict
    instrument: InstrumentReferenceOut


class MarketGroupProxyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    relationship_type: str
    source: str
    verification_state: str
    effective_at: datetime | None
    known_at: datetime | None
    provenance: dict
    instrument: InstrumentReferenceOut


class MarketGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stable_key: str
    group_type: str
    name: str
    parent_id: int | None
    representative_instrument_id: int | None
    equal_weight_instrument_id: int | None
    source: str
    provenance: dict
    effective_at: datetime | None
    known_at: datetime | None
    members: list[MarketGroupMemberOut] = Field(default_factory=list)
    proxies: list[MarketGroupProxyOut] = Field(default_factory=list)


class ETFIndustryOut(BaseModel):
    """A classification derived from a dated, source-labelled ETF composition."""

    industry: str
    constituent_count: int
    resolved_count: int


class ETFIndustryProxyOut(BaseModel):
    """A holdings-evidence-verified ETF proxy for one classified industry."""

    symbol: str
    name: str
    composition_date: str
    known_at: datetime | None = None
    provenance: str
    source_provider: str
    matching_constituent_count: int
    classified_constituent_count: int
    classification_coverage: float = Field(ge=0, le=1)
    source: str = "curated_industry_proxy_registry_v1"
    verification_state: str = "holdings_classification_verified"


class ETFIndustryProxyListOut(BaseModel):
    etf_symbol: str
    industry: str
    candidate_symbols: list[str] = Field(default_factory=list)
    proxies: list[ETFIndustryProxyOut] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ETFIndustryCompositionOut(BaseModel):
    etf_symbol: str
    composition_date: str
    known_at: datetime | None = None
    provenance: str
    source_provider: str
    completeness_status: str
    industries: list[ETFIndustryOut] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ETFIndustryConstituentsOut(BaseModel):
    etf_symbol: str
    industry: str
    composition_date: str
    known_at: datetime | None = None
    provenance: str
    source_provider: str
    constituents: list[InstrumentReferenceOut] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
