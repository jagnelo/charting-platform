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
from app.models.research import CodeAsset, CodeVersion
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
from app.services.python_conditions import VisualConditionCompileError, compile_visual_condition

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
FACTORY_WORKSPACE_VERSION = 8


class ConditionAssetWrite(BaseModel):
    """A reusable visual-condition AST stored in the workstation library."""

    name: str = Field(min_length=1, max_length=160)
    condition: dict = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=2_000)
    dependency_metadata: dict = Field(default_factory=dict)


FactoryWindow = tuple[str, str, str] | tuple[str, str, str, dict]


def _factory_layout(windows: list[FactoryWindow], factory_id: str) -> dict:
    """Return a serialisable Golden Layout virtual-component tree.

    The component state is deliberately only an instance key/type/title.  Runtime
    Vue instances, chart canvases and request caches are created by the browser
    tool registry and are never persisted in a workspace snapshot.
    """

    def component(item: FactoryWindow) -> dict:
        instance_key, tool_type, title = item[:3]
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

    def by_key(key: str) -> FactoryWindow:
        return next(item for item in windows if item[0] == key)

    if factory_id == "us-top-down":
        return {
            "factory_id": factory_id,
            "version": FACTORY_WORKSPACE_VERSION,
            "root": {
                "type": "row",
                "content": [
                    {
                        "type": "column",
                        "size": 22,
                        "content": [component(windows[0]), component(windows[3])],
                    },
                    {
                        "type": "column",
                        "size": 23,
                        "content": [component(windows[1]), component(windows[2])],
                    },
                    {
                        "type": "column",
                        "size": 55,
                        "content": [
                            component(windows[4]),
                            component(windows[5]),
                            {
                                "type": "stack",
                                "content": [component(item) for item in windows[6:]],
                            },
                        ],
                    },
                ],
            },
        }
    if factory_id == "four-timeframe":
        return {
            "factory_id": factory_id,
            "version": FACTORY_WORKSPACE_VERSION,
            "root": {
                "type": "row",
                "content": [
                    {"type": "column", "size": 50, "content": [component(windows[0]), component(windows[1])]},
                    {"type": "column", "size": 50, "content": [component(windows[2]), component(windows[3])]},
                ],
            },
        }
    if factory_id == "drill-down":
        return {
            "factory_id": factory_id,
            "version": FACTORY_WORKSPACE_VERSION,
            "root": {
                "type": "row",
                "content": [
                    {
                        "type": "column",
                        "size": 24,
                        "content": [component(by_key("sectors")), component(by_key("industries"))],
                    },
                    {
                        "type": "column",
                        "size": 24,
                        "content": [component(by_key("components"))],
                    },
                    {
                        "type": "stack",
                        "size": 52,
                        "content": [component(by_key("selected-chart")), component(by_key("sector-comparison"))],
                    },
                ],
            },
        }
    if factory_id == "sector-by-year":
        return {
            "factory_id": factory_id,
            "version": FACTORY_WORKSPACE_VERSION,
            "root": {
                "type": "row",
                "content": [
                    {
                        "type": "column",
                        "size": 24,
                        "content": [component(by_key("sectors")), component(by_key("industries"))],
                    },
                    {
                        "type": "column",
                        "size": 24,
                        "content": [component(by_key("components"))],
                    },
                    {
                        "type": "column",
                        "size": 52,
                        "content": [component(by_key("selected-chart")), component(by_key("normalized-comparison"))],
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
            {"expression": "=SPY/RSP", "timeframe": "D1", "auto_ratio": True},
        ),
        ("technical-summary", "technical_summary", "Technicals", {"scope": "selected"}),
        ("breadth-summary", "breadth", "Breadth", {"scope": "selected-sector"}),
        ("coverage-summary", "coverage", "Coverage", {"scope": "selected"}),
        ("notes", "notes", "Notes", {"scope": "active-instrument"}),
        ("alerts", "alerts", "Alerts", {"scope": "active-instrument"}),
        ("easy-scan", "scan", "EasyScan", {"scope": "saved-conditions"}),
        ("market-gauge", "gauge", "Market Gauge", {"scope": "saved-scans"}),
        (
            "relative-rotation",
            "relative_rotation",
            "Relative Rotation",
            {
                "group_key": "sp500-sectors",
                "benchmark": "SPY",
                "timeframe": "D1",
                "sampling": 1,
                "lookback": 20,
                "tail_length": 10,
                "adjusted": True,
            },
        ),
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
                [
                    ("chart", "chart", "Chart"),
                    ("watchlist", "watchlist", "WatchList"),
                    ("notes", "notes", "Notes"),
                ],
            ),
            (
                "drill-down",
                "Drill Down",
                [
                    ("sectors", "watchlist", "Sector Indexes"),
                    ("industries", "watchlist", "Industry Indexes"),
                    ("components", "watchlist", "Components"),
                    ("selected-chart", "chart", "Selected Symbol", {"symbol": "SPY", "timeframe": "D1"}),
                    ("sector-comparison", "chart", "Sector Comparison", {"symbol": "SPY", "timeframe": "D1", "comparison_symbols": ["RSP"]}),
                ],
            ),
            (
                "sector-by-year",
                "Sector by Year",
                [
                    ("sectors", "watchlist", "Sector Indexes"),
                    ("industries", "watchlist", "Industry Indexes"),
                    ("components", "watchlist", "Components"),
                    ("selected-chart", "chart", "Selected Symbol", {"symbol": "SPY", "timeframe": "D1"}),
                    ("normalized-comparison", "chart", "Normalized Comparison", {"symbol": "SPY", "timeframe": "D1", "comparison_symbols": ["RSP"]}),
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
        timeframe_configurations = {
            "m15": {"symbol": "SPY", "timeframe": "M15", "timeframe_link_group": "red"},
            "daily": {"symbol": "SPY", "timeframe": "D1", "timeframe_link_group": "green"},
            "weekly": {"symbol": "SPY", "timeframe": "W1", "timeframe_link_group": "purple"},
            "monthly": {"symbol": "SPY", "timeframe": "MN", "timeframe_link_group": "orange"},
        } if stable_key == "four-timeframe" else {}
        layout_windows: list[tuple[str, str, str, dict]] = []
        for item in windows:
            instance_key, tool_type, title = item[:3]
            configuration = item[3] if len(item) == 4 else timeframe_configurations.get(instance_key, {"symbol": "SPY"})
            layout_windows.append((instance_key, tool_type, title, configuration))
        factory_tab = WorkspaceTab(
            stable_key=stable_key,
            name=name,
            position=position,
            layout_config=_factory_layout(layout_windows, stable_key),
            active_window_key=windows[0][0],
        )
        for window_position, (instance_key, tool_type, title, *configuration_override) in enumerate(windows):
            configuration = configuration_override[0] if configuration_override else timeframe_configurations.get(instance_key, {"symbol": "SPY"})
            factory_tab.windows.append(
                WorkspaceWindow(
                    instance_key=instance_key,
                    tool_type=tool_type,
                    title=title,
                    link_group="blue",
                    configuration=configuration,
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
    defaults = (
        await db.execute(
            _workspace_query()
            .where(Workspace.user_id == user.id, Workspace.is_default.is_(True))
            .order_by(Workspace.position, Workspace.created_at)
        )
    ).scalars().unique().all()
    if defaults:
        # Older snapshots or concurrent first-load requests can have left more than
        # one default. Keep the deterministic first workspace and repair the rest so
        # the authenticated workstation never fails with MultipleResultsFound.
        existing = defaults[0]
        if len(defaults) > 1:
            for duplicate in defaults[1:]:
                duplicate.is_default = False
            await db.flush()
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
        settings={"factory_id": "us-top-down", "factory_version": FACTORY_WORKSPACE_VERSION},
        tabs=_factory_tabs(),
    )
    db.add(workspace)
    await db.flush()
    return await _load_workspace(db, workspace.id, user.id)


async def _replace_tabs(db: AsyncSession, workspace: Workspace, tabs: list) -> None:
    """Replace a snapshot without transiently violating workspace tab uniqueness.

    PostgreSQL checks the `(workspace_id, stable_key)` constraint while SQLAlchemy may
    otherwise insert replacement tabs before its delete-orphan rows. Flush the clear
    first, then append the new serializable snapshot.
    """
    workspace.tabs.clear()
    await db.flush()
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
    await _replace_tabs(db, workspace, body.tabs or _factory_tabs())
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
    # Serialize writers for the optimistic revision check. Without a row lock,
    # two concurrent snapshots can both observe the same revision, both clear
    # the tab relationship, and then race to insert identical stable keys,
    # turning a normal 409 conflict into a PostgreSQL unique-key 500.
    workspace = (
        await db.execute(
            _workspace_query()
            .where(Workspace.id == workspace_id, Workspace.user_id == current_user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.revision != body.base_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workspace_revision_conflict", "current_revision": workspace.revision},
        )
    if body.name is not None:
        workspace.name = body.name.strip()
    workspace.settings = body.settings
    workspace.schema_version = body.schema_version
    await _replace_tabs(db, workspace, body.tabs)
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
    # Reset is also a full tab replacement; serialize it with snapshot writers
    # so a closing browser cannot race the factory rebuild into duplicate keys.
    workspace = (
        await db.execute(
            _workspace_query()
            .where(Workspace.id == workspace_id, Workspace.user_id == current_user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.settings.get("factory_id") != "us-top-down":
        raise HTTPException(status_code=409, detail={"code": "not_factory_workspace"})
    await _replace_tabs(db, workspace, _factory_tabs())
    workspace.settings = {**workspace.settings, "factory_version": FACTORY_WORKSPACE_VERSION}
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
    # `updated_at` is server-generated through an on-update expression. Refresh
    # the row before Pydantic reads it so an in-place rename/update never causes
    # async lazy IO during response serialization.
    await db.refresh(item)
    return item


@router.delete("/library/items/{kind}/{stable_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_item(
    kind: str,
    stable_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove one user-owned reusable item without exposing another user's library."""
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
        raise HTTPException(status_code=404, detail="Library item not found")
    await db.delete(item)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    try:
        generated_source = compile_visual_condition(body.condition)
    except VisualConditionCompileError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "path": exc.path},
        ) from exc

    # Every condition authored by the visual editor receives an immutable
    # Boolean CodeVersion.  Existing legacy condition records remain readable
    # and executable through the compatibility evaluator; new saves never
    # create a second condition language.
    python_stable_key = f"visual-condition-{stable_key}"[:80]
    python_asset = (
        await db.execute(
            select(CodeAsset).where(
                CodeAsset.user_id == current_user.id,
                CodeAsset.stable_key == python_stable_key,
            )
        )
    ).scalar_one_or_none()
    if python_asset is None:
        python_asset = CodeAsset(
            user_id=current_user.id,
            stable_key=python_stable_key,
            name=f"{body.name.strip()} (visual condition)",
            kind="condition",
        )
        db.add(python_asset)
        await db.flush()
    elif python_asset.kind != "condition":
        raise HTTPException(status_code=409, detail="Visual condition code asset key is already used by another asset kind")
    next_version = (
        await db.execute(
            select(func.max(CodeVersion.version_number)).where(
                CodeVersion.code_asset_id == python_asset.id
            )
        )
    ).scalar_one() or 0
    next_version += 1
    python_version = CodeVersion(
        code_asset_id=python_asset.id,
        version_number=next_version,
        source=generated_source,
        output_contract="boolean",
        parameter_schema={},
        default_parameters={},
        dependencies=["market", "np", "output", "ta"],
        lookback=None,
        diagnostics=[],
    )
    db.add(python_version)
    await db.flush()
    item = (
        await db.execute(
            select(WorkspaceLibraryItem).where(
                WorkspaceLibraryItem.user_id == current_user.id,
                WorkspaceLibraryItem.kind == "condition",
                WorkspaceLibraryItem.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    payload = {
        "condition": body.condition,
        "description": body.description,
        "python_code_version_id": python_version.id,
        "python_source": generated_source,
    }
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
    # Refresh server-generated timestamps before Pydantic reads the ORM object.
    # Without this, async SQLAlchemy can attempt an implicit lazy load during
    # response serialization and raise MissingGreenlet.
    await db.refresh(item)
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
