from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DashboardWidgetBase(BaseModel):
    widget_type: str
    title: str | None = None
    layout: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)
    position: int = 0


class DashboardWidgetCreate(DashboardWidgetBase):
    pass


class DashboardWidgetUpdate(BaseModel):
    widget_type: str | None = None
    title: str | None = None
    layout: dict | None = None
    config: dict | None = None
    style: dict | None = None
    position: int | None = None


class DashboardWidgetOut(DashboardWidgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tab_id: int
    created_at: datetime
    updated_at: datetime


class DashboardTabBase(BaseModel):
    name: str
    position: int = 0
    layout_settings: dict = Field(default_factory=dict)


class DashboardTabCreate(DashboardTabBase):
    pass


class DashboardTabUpdate(BaseModel):
    name: str | None = None
    position: int | None = None
    layout_settings: dict | None = None


class DashboardTabOut(DashboardTabBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dashboard_id: int
    widgets: list[DashboardWidgetOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DashboardCreate(BaseModel):
    name: str = "Dashboard"
    is_default: bool = False
    position: int = 0
    settings: dict = Field(default_factory=dict)


class DashboardUpdate(BaseModel):
    name: str | None = None
    is_default: bool | None = None
    position: int | None = None
    settings: dict | None = None


class DashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    is_default: bool
    position: int
    settings: dict
    tabs: list[DashboardTabOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ReorderBody(BaseModel):
    ids: list[int]


class WidgetLayoutPatch(BaseModel):
    id: int
    layout: dict


class WidgetLayoutBulkPatch(BaseModel):
    widgets: list[WidgetLayoutPatch]
