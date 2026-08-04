"""Regression coverage for the streaming screener's connection ownership."""

import inspect

from fastapi.routing import APIRoute

from app.database import get_db
from app.routers.screener import router, stream_screener_run


def test_stream_route_uses_request_session_with_explicit_body_cleanup():
    """The stream must close the shared session when its body ends/cancels."""
    route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/screeners/{screener_id}/run/stream"
    )

    dependencies = {dependency.call for dependency in route.dependant.dependencies}
    assert get_db in dependencies

    source = inspect.getsource(stream_screener_run)
    assert "finally:" in source
    assert "db.close()" in source
