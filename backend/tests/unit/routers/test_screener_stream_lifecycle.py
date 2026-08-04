"""Regression coverage for the streaming screener's connection ownership."""

import inspect
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute

from app.auth.dependencies import get_current_user_detached
from app.database import get_auth_session_factory, get_db, get_stream_session_factory
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
    assert get_auth_session_factory in {
        dependency.call
        for dependency in next(
            dependency for dependency in route.dependant.dependencies
            if dependency.call is get_current_user_detached
        ).dependencies
    }
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


@pytest.mark.asyncio
async def test_detached_auth_user_survives_rollback_cleanup(monkeypatch):
    """The short auth lookup must return a usable identity after rollback."""
    from fastapi.security import HTTPAuthorizationCredentials

    import app.auth.dependencies as dependencies

    monkeypatch.setattr(dependencies, "decode_token", lambda _token: {"type": "access", "sub": "7"})

    user = SimpleNamespace(id=7, is_active=True, display_name="Test user")

    class Session:
        def __init__(self):
            self.expunge_calls = 0
            self.rollback_calls = 0
            self.close_calls = 0

        async def get(self, _model, _user_id):
            return user

        def expunge(self, value):
            assert value is user
            self.expunge_calls += 1

        async def rollback(self):
            self.rollback_calls += 1

        async def close(self):
            self.close_calls += 1

    session = Session()
    result = await get_current_user_detached(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
        lambda: session,
    )

    assert result is user
    assert result.display_name == "Test user"
    assert session.expunge_calls == 1
    assert session.rollback_calls == 1
    assert session.close_calls == 1
