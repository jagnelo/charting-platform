"""Revisioned persistence and library APIs for the primary workstation."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.workstation import Workspace, WorkspaceLibraryItem, WorkspaceTab, WorkspaceWindow
from app.schemas.workstation import (
    WorkspaceCreate,
    WorkspaceLibraryItemCreate,
    WorkspaceLibraryItemOut,
    WorkspaceOut,
    WorkspaceSnapshotWrite,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class ConditionAssetWrite(BaseModel):
    """A reusable visual-condition AST stored in the workstation library."""

    name: str = Field(min_length=1, max_length=160)
    condition: dict = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=2_000)
    dependency_metadata: dict = Field(default_factory=dict)


def _factory_layout(windows: list[tuple[str, str, str, dict]], factory_id: str) -> dict:
    """Return a serialisable Golden Layout virtual-component tree.

    The component state is deliberately only an instance key/type/title.  Runtime
    Vue instances, chart canvases and request caches are created by the browser
    tool registry and are never persisted in a workspace snapshot.
    """

    def component(item: tuple[str, str, str, dict]) -> dict:
        instance_key, tool_type, title, _ = item
        return {
            "type": "component",
            "componentType": "workstation-tool",
            "title": title,
            "componentState": {
                "instance_key": instance_key,
                "tool_type": tool_type,
                "title": title,
            },
        }

    if factory_id == "us-top-down":
        return {
            "factory_id": factory_id,
            "version": 3,
            "root": {
                "type": "row",
                "content": [
                    {
                        "type": "column",
                        "width": 22,
                        "content": [component(windows[0]), component(windows[3])],
                    },
                    {
                        "type": "column",
                        "width": 23,
                        "content": [component(windows[1]), component(windows[4])],
                    },
                    {
                        "type": "column",
                        "width": 55,
                        "content": [
                            component(windows[2]),
                            component(windows[5]),
                            component(windows[6]),
                            component(windows[7]),
                            component(windows[8]),
                            component(windows[9]),
                            component(windows[10]),
                        ],
                    },
                ],
            },
        }
    return {
        "factory_id": factory_id,
        "version": 2,
        "root": {"type": "row", "content": [component(item) for item in windows]},
    }


def _factory_tabs() -> list[WorkspaceTab]:
    """The immutable default is a top-down workspace, not an empty shell."""
    tab = WorkspaceTab(
        stable_key="us-top-down",
        name="US Top Down",
        position=0,
        layout_config={},
        active_window_key="benchmark-list",
    )
    default_windows = [
        ("benchmark-list", "watchlist", "Benchmarks", {"market_group": "us-benchmarks"}),
        ("sector-list", "watchlist", "S&P 500 Sectors", {"market_group": "sp500-sectors"}),
        (
            "industry-list",
            "watchlist",
            "Industries",
            {"market_group": "selected-sector-industries"},
        ),
        (
            "constituent-list",
            "watchlist",
            "Constituents",
            {"market_group": "selected-industry-constituents"},
        ),
        ("primary-chart", "chart", "Chart", {"symbol": "SPY", "timeframe": "D1"}),
        (
            "ratio-chart",
            "chart",
            "Relative Strength",
            {"expression": "=SPY/RSP", "timeframe": "D1"},
        ),
        ("technical-summary", "analysis", "Technicals", {"scope": "selected"}),
        ("breadth-summary", "breadth", "Breadth", {"scope": "selected-sector"}),
        ("coverage-summary", "coverage", "Coverage", {"scope": "selected"}),
        ("notes", "notes", "Notes", {"scope": "active-instrument"}),
        ("alerts", "alerts", "Alerts", {"scope": "active-instrument"}),
    ]
    tab.layout_config = _factory_layout(default_windows, "us-top-down")
    for position, (instance_key, tool_type, title, configuration) in enumerate(default_windows):
        tab.windows.append(
            WorkspaceWindow(
                instance_key=instance_key,
                tool_type=tool_type,
                title=title,
                link_group="blue",
                configuration=configuration,
                style={},
                position=position,
            )
        )
    tabs = [tab]
    for position, (stable_key, name, windows) in enumerate(
        [
            (
                "tc-classic",
                "TC Classic",
                [("chart", "chart", "Chart"), ("watchlist", "watchlist", "WatchList")],
            ),
            (
                "drill-down",
                "Drill Down",
                [
                    ("sectors", "watchlist", "Sector Indexes"),
                    ("industries", "watchlist", "Industry Indexes"),
                    ("components", "watchlist", "Components"),
                    ("chart", "chart", "Chart"),
                ],
            ),
            (
                "sector-by-year",
                "Sector by Year",
                [
                    ("sectors", "watchlist", "Sector Indexes"),
                    ("industries", "watchlist", "Industry Indexes"),
                    ("components", "watchlist", "Components"),
                    ("chart", "chart", "Chart"),
                ],
            ),
            ("one-chart", "1 Chart", [("chart", "chart", "Chart")]),
            (
                "four-timeframe",
                "4 Timeframe",
                [
                    ("m15", "chart", "15 Minute"),
                    ("daily", "chart", "Daily"),
                    ("weekly", "chart", "Weekly"),
                    ("monthly", "chart", "Monthly"),
                ],
            ),
            (
                "fundamentals",
                "Fundamentals",
                [
                    ("watchlist", "watchlist", "Fundamentals WatchList"),
                    ("chart", "chart", "Chart"),
                    ("report", "report", "Supported Symbol Report"),
                ],
            ),
            (
                "study-lab",
                "Study Lab",
                [
                    ("study", "study_lab", "Study Lab"),
                    ("chart", "chart", "Chart"),
                    ("results", "research_results", "Study Results"),
                ],
            ),
        ],
        start=1,
    ):
        layout_windows = [
            (instance_key, tool_type, title, {"symbol": "SPY"})
            for instance_key, tool_type, title in windows
        ]
        factory_tab = WorkspaceTab(
            stable_key=stable_key,
            name=name,
            position=position,
            layout_config=_factory_layout(layout_windows, stable_key),
            active_window_key=windows[0][0],
        )
        for window_position, (instance_key, tool_type, title) in enumerate(windows):
            factory_tab.windows.append(
                WorkspaceWindow(
                    instance_key=instance_key,
                    tool_type=tool_type,
                    title=title,
                    link_group="blue",
                    configuration={"symbol": "SPY"},
                    style={},
                    position=window_position,
                )
            )
        tabs.append(factory_tab)
    return tabs


def _workspace_query():
    return select(Workspace).options(
        selectinload(Workspace.tabs).selectinload(WorkspaceTab.windows)
    )


async def _load_workspace(db: AsyncSession, workspace_id: int, user_id: int) -> Workspace:
    workspace = (
        await db.execute(
            _workspace_query()
            .where(Workspace.id == workspace_id, Workspace.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


async def _ensure_default_workspace(db: AsyncSession, user: User) -> Workspace:
    existing = (
        await db.execute(
            _workspace_query()
            .where(Workspace.user_id == user.id, Workspace.is_default.is_(True))
            .order_by(Workspace.position, Workspace.created_at)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    existing = (
        await db.execute(
            _workspace_query().where(Workspace.user_id == user.id).order_by(Workspace.position)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.is_default = True
        await db.flush()
        return await _load_workspace(db, existing.id, user.id)

    workspace = Workspace(
        user_id=user.id,
        name="US Top Down",
        is_default=True,
        position=0,
        schema_version=1,
        settings={"factory_id": "us-top-down", "factory_version": 1},
        tabs=_factory_tabs(),
    )
    db.add(workspace)
    await db.flush()
    return await _load_workspace(db, workspace.id, user.id)


def _replace_tabs(workspace: Workspace, tabs: list) -> None:
    workspace.tabs.clear()
    for tab_input in tabs:
        tab = WorkspaceTab(
            stable_key=tab_input.stable_key,
            name=tab_input.name.strip(),
            position=tab_input.position,
            layout_config=tab_input.layout_config,
            active_window_key=tab_input.active_window_key,
        )
        for window_input in tab_input.windows:
            tab.windows.append(
                WorkspaceWindow(
                    instance_key=window_input.instance_key,
                    tool_type=window_input.tool_type,
                    title=window_input.title,
                    link_group=window_input.link_group,
                    configuration=window_input.configuration,
                    style=window_input.style,
                    state_schema_version=window_input.state_schema_version,
                    position=window_input.position,
                )
            )
        workspace.tabs.append(tab)


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    await _ensure_default_workspace(db, current_user)
    result = await db.execute(
        _workspace_query().where(Workspace.user_id == current_user.id).order_by(Workspace.position)
    )
    return result.scalars().unique().all()


@router.get("/default", response_model=WorkspaceOut)
async def get_default_workspace(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return await _ensure_default_workspace(db, current_user)


@router.get("/{workspace_id:int}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _load_workspace(db, workspace_id, current_user.id)


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.is_default:
        existing = await db.execute(select(Workspace).where(Workspace.user_id == current_user.id))
        for workspace in existing.scalars():
            workspace.is_default = False

    position = body.position
    if position == 0:
        max_position = (
            await db.execute(
                select(func.max(Workspace.position)).where(Workspace.user_id == current_user.id)
            )
        ).scalar_one()
        position = (max_position or 0) + 1

    workspace = Workspace(
        user_id=current_user.id,
        name=body.name.strip(),
        is_default=body.is_default,
        position=position,
        schema_version=body.schema_version,
        settings=body.settings,
    )
    _replace_tabs(workspace, body.tabs or _factory_tabs())
    db.add(workspace)
    await db.flush()
    return await _load_workspace(db, workspace.id, current_user.id)


@router.patch("/{workspace_id:int}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: int,
    body: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = await _load_workspace(db, workspace_id, current_user.id)
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default") is True:
        existing = await db.execute(select(Workspace).where(Workspace.user_id == current_user.id))
        for other in existing.scalars():
            other.is_default = other.id == workspace.id
        data.pop("is_default")
    for field, value in data.items():
        setattr(workspace, field, value.strip() if field == "name" else value)
    await db.flush()
    return await _load_workspace(db, workspace.id, current_user.id)


@router.put("/{workspace_id:int}/snapshot", response_model=WorkspaceOut)
async def save_workspace_snapshot(
    workspace_id: int,
    body: WorkspaceSnapshotWrite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = await _load_workspace(db, workspace_id, current_user.id)
    if workspace.revision != body.base_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workspace_revision_conflict", "current_revision": workspace.revision},
        )
    if body.name is not None:
        workspace.name = body.name.strip()
    workspace.settings = body.settings
    workspace.schema_version = body.schema_version
    _replace_tabs(workspace, body.tabs)
    workspace.revision += 1
    await db.flush()
    return await _load_workspace(db, workspace.id, current_user.id)


@router.post(
    "/{workspace_id:int}/clone", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED
)
async def clone_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _load_workspace(db, workspace_id, current_user.id)
    clone = Workspace(
        user_id=current_user.id,
        name=f"{source.name} Copy",
        is_default=False,
        position=source.position + 1,
        schema_version=source.schema_version,
        settings=dict(source.settings),
    )
    for source_tab in source.tabs:
        tab = WorkspaceTab(
            stable_key=f"{source_tab.stable_key}-{uuid4().hex[:8]}",
            name=source_tab.name,
            position=source_tab.position,
            layout_config=dict(source_tab.layout_config),
            active_window_key=source_tab.active_window_key,
        )
        for source_window in source_tab.windows:
            tab.windows.append(
                WorkspaceWindow(
                    instance_key=f"{source_window.instance_key}-{uuid4().hex[:8]}",
                    tool_type=source_window.tool_type,
                    title=source_window.title,
                    link_group=source_window.link_group,
                    configuration=dict(source_window.configuration),
                    style=dict(source_window.style),
                    state_schema_version=source_window.state_schema_version,
                    position=source_window.position,
                )
            )
        clone.tabs.append(tab)
    db.add(clone)
    await db.flush()
    return await _load_workspace(db, clone.id, current_user.id)


@router.post("/{workspace_id:int}/reset-factory", response_model=WorkspaceOut)
async def reset_factory_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = await _load_workspace(db, workspace_id, current_user.id)
    if workspace.settings.get("factory_id") != "us-top-down":
        raise HTTPException(status_code=409, detail={"code": "not_factory_workspace"})
    _replace_tabs(workspace, _factory_tabs())
    workspace.revision += 1
    await db.flush()
    return await _load_workspace(db, workspace.id, current_user.id)


@router.delete("/{workspace_id:int}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = await _load_workspace(db, workspace_id, current_user.id)
    if workspace.is_default:
        raise HTTPException(
            status_code=400, detail="Set another workspace as default before deleting this one"
        )
    await db.delete(workspace)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/library/items", response_model=list[WorkspaceLibraryItemOut])
async def list_library_items(
    kind: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = select(WorkspaceLibraryItem).where(WorkspaceLibraryItem.user_id == current_user.id)
    if kind:
        statement = statement.where(WorkspaceLibraryItem.kind == kind)
    result = await db.execute(
        statement.order_by(WorkspaceLibraryItem.kind, WorkspaceLibraryItem.name)
    )
    return result.scalars().all()


@router.put("/library/items/{kind}/{stable_key}", response_model=WorkspaceLibraryItemOut)
async def upsert_library_item(
    kind: str,
    stable_key: str,
    body: WorkspaceLibraryItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if kind != body.kind or stable_key != body.stable_key:
        raise HTTPException(status_code=400, detail="Path and payload library identity must match")
    item = (
        await db.execute(
            select(WorkspaceLibraryItem).where(
                WorkspaceLibraryItem.user_id == current_user.id,
                WorkspaceLibraryItem.kind == kind,
                WorkspaceLibraryItem.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = WorkspaceLibraryItem(user_id=current_user.id, **body.model_dump())
        db.add(item)
    else:
        item.name = body.name
        item.payload = body.payload
        item.dependency_metadata = body.dependency_metadata
        item.version += 1
    await db.flush()
    return item


@router.get("/library/conditions", response_model=list[WorkspaceLibraryItemOut])
async def list_condition_assets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List reusable condition ASTs without exposing generic library internals to tools."""
    result = await db.execute(
        select(WorkspaceLibraryItem)
        .where(
            WorkspaceLibraryItem.user_id == current_user.id,
            WorkspaceLibraryItem.kind == "condition",
        )
        .order_by(WorkspaceLibraryItem.name)
    )
    return result.scalars().all()


@router.put("/library/conditions/{stable_key}", response_model=WorkspaceLibraryItemOut)
async def upsert_condition_asset(
    stable_key: str,
    body: ConditionAssetWrite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Version a reusable condition with a stable identity for scans and filters."""
    if not body.condition:
        raise HTTPException(status_code=422, detail="Condition AST must not be empty")
    item = (
        await db.execute(
            select(WorkspaceLibraryItem).where(
                WorkspaceLibraryItem.user_id == current_user.id,
                WorkspaceLibraryItem.kind == "condition",
                WorkspaceLibraryItem.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    payload = {"condition": body.condition, "description": body.description}
    if item is None:
        item = WorkspaceLibraryItem(
            user_id=current_user.id,
            kind="condition",
            stable_key=stable_key,
            name=body.name,
            payload=payload,
            dependency_metadata=body.dependency_metadata,
        )
        db.add(item)
    else:
        item.name = body.name
        item.payload = payload
        item.dependency_metadata = body.dependency_metadata
        item.version += 1
    await db.flush()
    return item


@router.delete("/library/conditions/{stable_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_condition_asset(
    stable_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        await db.execute(
            select(WorkspaceLibraryItem).where(
                WorkspaceLibraryItem.user_id == current_user.id,
                WorkspaceLibraryItem.kind == "condition",
                WorkspaceLibraryItem.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Condition not found")
    await db.delete(item)
