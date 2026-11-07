"""PostgreSQL regression for workspace reads racing snapshot replacement."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.models.user import User
from app.models.workstation import Workspace, WorkspaceTab, WorkspaceWindow
from app.routers.workspaces import (
    clone_workspace,
    get_default_workspace,
    get_workspace,
    list_workspaces,
)


def _tab(key: str, suffix: str, symbols: tuple[str, str]) -> WorkspaceTab:
    tab = WorkspaceTab(
        stable_key=key,
        name=f"{suffix} Layout",
        position=0,
        layout_config={"root": {"type": "row", "content": []}},
        active_window_key=f"chart-{suffix}-a",
    )
    for position, symbol in enumerate(symbols):
        tab.windows.append(
            WorkspaceWindow(
                instance_key=f"chart-{suffix}-{position}",
                tool_type="chart",
                title=f"{symbol} Chart",
                link_group="blue",
                configuration={"symbol": symbol, "timeframe": "D1"},
                style={"theme": "dark"},
                position=position,
            )
        )
    return tab


def _assert_complete(workspace, expected_revision: int, expected_symbols: set[str]) -> None:
    assert workspace.revision == expected_revision
    windows = [window for tab in workspace.tabs for window in tab.windows]
    assert len(windows) == 2
    assert {window.configuration["symbol"] for window in windows} == expected_symbols
    assert all(window.configuration["timeframe"] == "D1" for window in windows)
    assert all(window.style == {"theme": "dark"} for window in windows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workspace_readers_keep_one_snapshot_during_concurrent_replacement(db_engine):
    """A committed writer between eager-load phases must not erase returned windows."""
    suffix = uuid4().hex[:12]
    with Session(db_engine) as setup, setup.begin():
        user = User(
            username=f"workspace-read-{suffix}",
            email=f"workspace-read-{suffix}@example.test",
            hashed_password="test-only-not-authenticated",
        )
        setup.add(user)
        setup.flush()
        workspace = Workspace(
            user_id=user.id,
            name="Concurrent Snapshot",
            is_default=True,
            position=0,
            revision=2,
            schema_version=1,
            settings={"layout": "before"},
            tabs=[_tab("main", "before", ("SPY", "XLB"))],
        )
        setup.add(workspace)
        setup.flush()
        user_id = user.id
        workspace_id = workspace.id

    async_engine = create_async_engine(
        db_engine.url.set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
    )
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    replacement_committed = False

    def replace_after_read_rows(conn, cursor, statement, parameters, context, executemany):
        nonlocal replacement_committed
        sql = statement.lower()
        if replacement_committed or "select" not in sql or "workspace_tab" not in sql:
            return

        # With selectinload, this runs after tab IDs have been fetched but before
        # the separate window query. The writer follows the production lock and
        # replace/flush/insert/commit sequence using an independent connection.
        with Session(db_engine) as writer, writer.begin():
            current = writer.execute(
                select(Workspace).where(Workspace.id == workspace_id).with_for_update()
            ).scalar_one()
            current.tabs.clear()
            writer.flush()
            current.tabs.append(_tab("main", "after", ("QQQ", "IGV")))
            current.settings = {"layout": "after"}
            current.revision += 1
        replacement_committed = True

    event.listen(async_engine.sync_engine, "after_cursor_execute", replace_after_read_rows)
    user_ref = SimpleNamespace(id=user_id)
    try:
        async with sessions() as reader:
            first = await get_default_workspace(reader, user_ref)

        assert replacement_committed, "test did not interleave a snapshot commit with the read"
        # The in-flight response is revision 2 and must remain a complete revision
        # 2 graph even though revision 3 committed after its rowset was captured.
        _assert_complete(first, 2, {"SPY", "XLB"})

        async with sessions() as reader:
            by_id = await get_workspace(workspace_id, reader, user_ref)
            listed = await list_workspaces(reader, user_ref)
            clone = await clone_workspace(workspace_id, reader, user_ref)

        _assert_complete(by_id, 3, {"QQQ", "IGV"})
        assert len(listed) == 1
        _assert_complete(listed[0], 3, {"QQQ", "IGV"})
        _assert_complete(clone, 1, {"QQQ", "IGV"})
        assert clone.user_id == user_id
    finally:
        event.remove(async_engine.sync_engine, "after_cursor_execute", replace_after_read_rows)
        await async_engine.dispose()
