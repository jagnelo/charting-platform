"""Regression coverage for the streaming screener's connection ownership."""

import inspect

import pytest
from fastapi.routing import APIRoute

from app.auth.dependencies import get_current_user_detached
from app.database import get_db, get_stream_session_factory
from app.routers.screener import router, stream_screener_run


def test_stream_route_owns_a_dedicated_session_with_explicit_body_cleanup():
    """The stream must close its dedicated session when its body ends/cancels."""
    route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/screeners/{screener_id}/run/stream"
    )

    dependencies = {dependency.call for dependency in route.dependant.dependencies}
    assert get_current_user_detached in dependencies
    assert get_db not in dependencies
    assert get_stream_session_factory in dependencies

    source = inspect.getsource(stream_screener_run)
    assert "finally:" in source
    assert "rollback_session_safely(db)" in source
    assert "close_session_safely(db)" in source
    assert "db = session_factory()" in source


@pytest.mark.asyncio
async def test_database_cleanup_helpers_finish_inside_a_cancelled_scope():
    """Cancellation must not interrupt rollback or close before pool return."""
    import anyio

    from app.database import close_session_safely, rollback_session_safely

    class Session:
        def __init__(self):
            self.rollback_calls = 0
            self.close_calls = 0

        async def rollback(self):
            self.rollback_calls += 1

        async def close(self):
            self.close_calls += 1

    session = Session()
    with anyio.CancelScope() as scope:
        scope.cancel()
        await rollback_session_safely(session)
        await close_session_safely(session)

    assert session.rollback_calls == 1
    assert session.close_calls == 1
