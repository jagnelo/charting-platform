"""Canonical serializable workstation tools and their safe default state."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field

TOOL_CATALOGUE_VERSION = 1


class WorkstationToolDefinition(BaseModel):
    key: str
    tool_type: str
    title: str
    instance_prefix: str
    configuration: dict[str, Any] = Field(default_factory=dict)


class WorkstationToolCatalogue(BaseModel):
    version: Literal[1] = TOOL_CATALOGUE_VERSION
    tools: list[WorkstationToolDefinition]


# Stable keys distinguish useful variants that share a rendered tool type.  The
# factory and maintenance projection consume these same definitions; layout
# titles and geometry remain owned by the immutable factory layouts.
_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "key": "chart",
        "tool_type": "chart",
        "title": "Chart",
        "instance_prefix": "chart",
        "configuration": {"symbol": "SPY", "timeframe": "D1"},
    },
    {
        "key": "watchlist",
        "tool_type": "watchlist",
        "title": "WatchList",
        "instance_prefix": "watchlist",
        "configuration": {"personal": True, "watchlist_id": None},
    },
    {
        "key": "favorites",
        "tool_type": "watchlist",
        "title": "My Favorites",
        "instance_prefix": "favorites",
        "configuration": {"personal": True, "favorites": True},
    },
    {
        "key": "notes",
        "tool_type": "notes",
        "title": "Notes",
        "instance_prefix": "notes",
        "configuration": {"scope": "active-instrument"},
    },
    {
        "key": "alerts",
        "tool_type": "alerts",
        "title": "Alerts",
        "instance_prefix": "alerts",
        "configuration": {"scope": "active-instrument"},
    },
    {
        "key": "easy-scan",
        "tool_type": "scan",
        "title": "EasyScan",
        "instance_prefix": "easy-scan",
        "configuration": {"scope": "saved-conditions"},
    },
    {
        "key": "market-gauge",
        "tool_type": "gauge",
        "title": "Market Gauge",
        "instance_prefix": "market-gauge",
        "configuration": {"scope": "saved-scans"},
    },
    {
        "key": "study-lab",
        "tool_type": "study_lab",
        "title": "Study Lab",
        "instance_prefix": "study-lab",
        "configuration": {"symbol": "SPY"},
    },
    {
        "key": "research-results",
        "tool_type": "research_results",
        "title": "Study Results",
        "instance_prefix": "research-results",
        "configuration": {},
    },
    {
        "key": "relative-rotation",
        "tool_type": "relative_rotation",
        "title": "Relative Rotation",
        "instance_prefix": "relative-rotation",
        "configuration": {
            "group_key": "sp500-sectors",
            "benchmark": "SPY",
            "timeframe": "D1",
            "sampling": 1,
            "lookback": 20,
            "tail_length": 10,
            "adjusted": True,
        },
    },
    {
        "key": "breadth",
        "tool_type": "breadth",
        "title": "Market Breadth",
        "instance_prefix": "breadth",
        "configuration": {"group_key": "sp500-sectors"},
    },
    {
        "key": "market-map",
        "tool_type": "market_map",
        "title": "Market Map",
        "instance_prefix": "market-map",
        "configuration": {
            "group_by": "sector_industry",
            "period": "1D",
            "area_metric": "market_cap",
            "color_metric": "return",
        },
    },
    {
        "key": "technical-summary",
        "tool_type": "technical_summary",
        "title": "Technicals",
        "instance_prefix": "technical-summary",
        "configuration": {"scope": "selected"},
    },
    {
        "key": "coverage",
        "tool_type": "coverage",
        "title": "Coverage",
        "instance_prefix": "coverage",
        "configuration": {"scope": "selected"},
    },
    {
        "key": "report",
        "tool_type": "report",
        "title": "Instrument Report",
        "instance_prefix": "report",
        "configuration": {},
    },
    {
        "key": "code-library",
        "tool_type": "code_library",
        "title": "Python Library",
        "instance_prefix": "code-library",
        "configuration": {},
    },
    {
        "key": "benchmark-list",
        "tool_type": "watchlist",
        "title": "Benchmarks",
        "instance_prefix": "benchmark-list",
        "configuration": {"market_group": "us-benchmarks"},
    },
    {
        "key": "sector-list",
        "tool_type": "watchlist",
        "title": "S&P 500 Sectors",
        "instance_prefix": "sector-list",
        "configuration": {"market_group": "sp500-sectors"},
    },
    {
        "key": "industry-list",
        "tool_type": "watchlist",
        "title": "Industries",
        "instance_prefix": "industry-list",
        "configuration": {"market_group": "selected-sector-industries"},
    },
    {
        "key": "constituent-list",
        "tool_type": "watchlist",
        "title": "Constituents",
        "instance_prefix": "constituent-list",
        "configuration": {"market_group": "selected-industry-constituents"},
    },
    {
        "key": "ratio-chart",
        "tool_type": "chart",
        "title": "Relative Strength",
        "instance_prefix": "ratio-chart",
        "configuration": {"expression": "=SPY/RSP", "timeframe": "D1", "auto_ratio": True},
    },
)


def tool_catalogue() -> dict[str, Any]:
    """Return a detached wire-safe catalogue for the authenticated read route."""

    return {"version": TOOL_CATALOGUE_VERSION, "tools": deepcopy(list(_TOOLS))}


def factory_tool_configuration(
    instance_key: str, tool_type: str, override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Project canonical defaults plus a factory layout's explicit override."""

    definition = next(
        (tool for tool in _TOOLS if tool["key"] == instance_key),
        next((tool for tool in _TOOLS if tool["tool_type"] == tool_type), None),
    )
    if definition is None or definition["tool_type"] != tool_type:
        defaults: dict[str, Any] = {}
    else:
        defaults = deepcopy(definition["configuration"])
    defaults.update(deepcopy(override or {}))
    return defaults


def default_maintenance_tool_dependencies() -> list[dict[str, Any]]:
    """Return the canonical semantic projection used by default maintenance."""

    return [
        {"key": item["key"], "tool_type": item["tool_type"], "configuration": item["configuration"]}
        for item in tool_catalogue()["tools"]
    ]
