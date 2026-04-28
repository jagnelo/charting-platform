from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.dashboard import Dashboard, DashboardTab, DashboardWidget
from app.models.user import User
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardOut,
    DashboardTabCreate,
    DashboardTabOut,
    DashboardTabUpdate,
    DashboardUpdate,
    DashboardWidgetCreate,
    DashboardWidgetOut,
    DashboardWidgetUpdate,
    ReorderBody,
    WidgetLayoutBulkPatch,
)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _default_tab() -> DashboardTab:
    return DashboardTab(name="Home", position=0, layout_settings={})


async def _ensure_dashboard_has_tab(db: AsyncSession, dashboard: Dashboard) -> Dashboard:
    if dashboard.tabs:
        return dashboard
    dashboard.tabs.append(_default_tab())
    await db.flush()
    return await _load_dashboard(db, dashboard.id, dashboard.user_id)


async def _load_dashboard(db: AsyncSession, dashboard_id: int, user_id: int) -> Dashboard:
    dashboard = (
        await db.execute(
            select(Dashboard)
            .where(Dashboard.id == dashboard_id, Dashboard.user_id == user_id)
            .execution_options(populate_existing=True)
            .options(selectinload(Dashboard.tabs).selectinload(DashboardTab.widgets))
        )
    ).scalar_one_or_none()
    if dashboard is None:
        raise HTTPException(404, "Dashboard not found")
    return dashboard


async def _load_tab(db: AsyncSession, tab_id: int, user_id: int) -> DashboardTab:
    tab = (
        await db.execute(
            select(DashboardTab)
            .join(Dashboard, Dashboard.id == DashboardTab.dashboard_id)
            .where(DashboardTab.id == tab_id, Dashboard.user_id == user_id)
            .execution_options(populate_existing=True)
            .options(selectinload(DashboardTab.widgets))
        )
    ).scalar_one_or_none()
    if tab is None:
        raise HTTPException(404, "Dashboard tab not found")
    return tab


async def _load_widget(db: AsyncSession, widget_id: int, user_id: int) -> DashboardWidget:
    widget = (
        await db.execute(
            select(DashboardWidget)
            .join(DashboardTab, DashboardTab.id == DashboardWidget.tab_id)
            .join(Dashboard, Dashboard.id == DashboardTab.dashboard_id)
            .where(DashboardWidget.id == widget_id, Dashboard.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if widget is None:
        raise HTTPException(404, "Dashboard widget not found")
    return widget


async def _ensure_default_dashboard(db: AsyncSession, user: User) -> Dashboard:
    existing = (
        await db.execute(
            select(Dashboard)
            .where(Dashboard.user_id == user.id, Dashboard.is_default.is_(True))
            .execution_options(populate_existing=True)
            .options(selectinload(Dashboard.tabs).selectinload(DashboardTab.widgets))
            .order_by(Dashboard.position, Dashboard.created_at)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await _ensure_dashboard_has_tab(db, existing)

    any_dashboard = (
        await db.execute(
            select(Dashboard)
            .where(Dashboard.user_id == user.id)
            .execution_options(populate_existing=True)
            .options(selectinload(Dashboard.tabs).selectinload(DashboardTab.widgets))
            .order_by(Dashboard.position, Dashboard.created_at)
        )
    ).scalar_one_or_none()
    if any_dashboard is not None:
        any_dashboard.is_default = True
        await db.flush()
        return await _ensure_dashboard_has_tab(db, any_dashboard)

    dashboard = Dashboard(
        user_id=user.id,
        name="Dashboard",
        is_default=True,
        position=0,
        settings={},
        tabs=[_default_tab()],
    )
    db.add(dashboard)
    await db.flush()
    return await _load_dashboard(db, dashboard.id, user.id)


@router.get("", response_model=list[DashboardOut])
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_default_dashboard(db, current_user)
    dashboards = (
        await db.execute(
            select(Dashboard)
            .where(Dashboard.user_id == current_user.id)
            .execution_options(populate_existing=True)
            .options(selectinload(Dashboard.tabs).selectinload(DashboardTab.widgets))
            .order_by(Dashboard.position, Dashboard.created_at)
        )
    ).scalars().all()
    return dashboards


@router.get("/default", response_model=DashboardOut)
async def get_default_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _ensure_default_dashboard(db, current_user)


@router.post("", response_model=DashboardOut, status_code=201)
async def create_dashboard(
    body: DashboardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.is_default:
        result = await db.execute(select(Dashboard).where(Dashboard.user_id == current_user.id))
        for dashboard in result.scalars().all():
            dashboard.is_default = False
    position = body.position
    if position == 0:
        max_position = (
            await db.execute(select(func.max(Dashboard.position)).where(Dashboard.user_id == current_user.id))
        ).scalar_one()
        position = (max_position or 0) + 1
    dashboard = Dashboard(
        user_id=current_user.id,
        name=body.name.strip() or "Dashboard",
        is_default=body.is_default,
        position=position,
        settings=body.settings,
        tabs=[_default_tab()],
    )
    db.add(dashboard)
    await db.flush()
    return await _load_dashboard(db, dashboard.id, current_user.id)


@router.patch("/{dashboard_id}", response_model=DashboardOut)
async def update_dashboard(
    dashboard_id: int,
    body: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboard = await _load_dashboard(db, dashboard_id, current_user.id)
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default") is True:
        result = await db.execute(select(Dashboard).where(Dashboard.user_id == current_user.id))
        for other in result.scalars().all():
            other.is_default = other.id == dashboard.id
        data.pop("is_default")
    for field, value in data.items():
        if field == "name" and isinstance(value, str):
            value = value.strip() or dashboard.name
        setattr(dashboard, field, value)
    await db.flush()
    return await _load_dashboard(db, dashboard_id, current_user.id)


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboard = await _load_dashboard(db, dashboard_id, current_user.id)
    await db.delete(dashboard)


@router.post("/{dashboard_id}/tabs", response_model=DashboardTabOut, status_code=201)
async def create_tab(
    dashboard_id: int,
    body: DashboardTabCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboard = await _load_dashboard(db, dashboard_id, current_user.id)
    tab = DashboardTab(
        dashboard_id=dashboard.id,
        name=body.name.strip() or "Tab",
        position=body.position,
        layout_settings=body.layout_settings,
    )
    db.add(tab)
    await db.flush()
    return await _load_tab(db, tab.id, current_user.id)


@router.patch("/tabs/{tab_id}", response_model=DashboardTabOut)
async def update_tab(
    tab_id: int,
    body: DashboardTabUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tab = await _load_tab(db, tab_id, current_user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and isinstance(value, str):
            value = value.strip() or tab.name
        setattr(tab, field, value)
    await db.flush()
    return await _load_tab(db, tab.id, current_user.id)


@router.delete("/tabs/{tab_id}", status_code=204)
async def delete_tab(
    tab_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tab = await _load_tab(db, tab_id, current_user.id)
    sibling_count = (
        await db.execute(
            select(func.count(DashboardTab.id)).where(DashboardTab.dashboard_id == tab.dashboard_id)
        )
    ).scalar_one()
    if sibling_count <= 1:
        raise HTTPException(400, "Cannot delete the last dashboard tab")
    await db.delete(tab)


@router.post("/{dashboard_id}/tabs/reorder")
async def reorder_tabs(
    dashboard_id: int,
    body: ReorderBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _load_dashboard(db, dashboard_id, current_user.id)
    tabs = (
        await db.execute(
            select(DashboardTab).where(
                DashboardTab.dashboard_id == dashboard_id,
                DashboardTab.id.in_(body.ids),
            )
        )
    ).scalars().all()
    by_id = {tab.id: tab for tab in tabs}
    for pos, tab_id in enumerate(body.ids):
        if tab_id in by_id:
            by_id[tab_id].position = pos
    await db.flush()
    return {"ok": True}


@router.post("/tabs/{tab_id}/widgets", response_model=DashboardWidgetOut, status_code=201)
async def create_widget(
    tab_id: int,
    body: DashboardWidgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tab = await _load_tab(db, tab_id, current_user.id)
    widget = DashboardWidget(tab_id=tab.id, **body.model_dump())
    db.add(widget)
    await db.flush()
    return await _load_widget(db, widget.id, current_user.id)


@router.patch("/widgets/{widget_id}", response_model=DashboardWidgetOut)
async def update_widget(
    widget_id: int,
    body: DashboardWidgetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    widget = await _load_widget(db, widget_id, current_user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(widget, field, value)
    await db.flush()
    await db.refresh(widget)
    return widget


@router.delete("/widgets/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    widget = await _load_widget(db, widget_id, current_user.id)
    await db.delete(widget)


@router.patch("/tabs/{tab_id}/widgets/layout")
async def update_widget_layouts(
    tab_id: int,
    body: WidgetLayoutBulkPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _load_tab(db, tab_id, current_user.id)
    widgets = (
        await db.execute(
            select(DashboardWidget).where(
                DashboardWidget.tab_id == tab_id,
                DashboardWidget.id.in_([w.id for w in body.widgets]),
            )
        )
    ).scalars().all()
    by_id = {widget.id: widget for widget in widgets}
    for patch in body.widgets:
        if patch.id in by_id:
            by_id[patch.id].layout = patch.layout
    await db.flush()
    return {"ok": True}
