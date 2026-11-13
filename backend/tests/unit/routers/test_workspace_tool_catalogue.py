import pytest

from app.auth.dependencies import get_current_user
from app.routers.workspaces import _factory_tabs, get_workspace_tool_catalogue, router
from app.services.workstation_tool_catalogue import tool_catalogue


@pytest.mark.asyncio
async def test_tool_catalogue_route_is_authenticated_and_returns_canonical_wire_shape():
    route = next(route for route in router.routes if route.path == "/workspaces/tool-catalogue")
    assert route.methods == {"GET"}
    assert any(dependency.call is get_current_user for dependency in route.dependant.dependencies)

    response = await get_workspace_tool_catalogue(current_user=object())
    assert response == tool_catalogue()
    assert response["version"] == 1
    assert all(
        set(tool) == {"key", "tool_type", "title", "instance_prefix", "configuration"}
        for tool in response["tools"]
    )

    tabs = _factory_tabs()
    assert len(tabs) == 8
    assert sum(len(tab.windows) for tab in tabs) == 38
    assert [window.instance_key for window in tabs[0].windows] == [
        "benchmark-list",
        "sector-list",
        "industry-list",
        "constituent-list",
        "primary-chart",
        "ratio-chart",
        "technical-summary",
        "breadth-summary",
        "coverage-summary",
        "notes",
        "alerts",
        "easy-scan",
        "market-gauge",
        "relative-rotation",
    ]
