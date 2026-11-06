from app.services.workstation_tool_catalogue import (
    default_maintenance_request_specs,
    default_maintenance_tool_dependencies,
    factory_tool_configuration,
    maintenance_request_specs,
    tool_catalogue,
)


def test_catalogue_exposes_all_stable_tool_definitions_and_detached_defaults():
    first = tool_catalogue()
    second = tool_catalogue()

    assert first["version"] == 1
    tools = first["tools"]
    assert len(tools) == 21
    assert len({tool["key"] for tool in tools}) == 21
    assert all(
        set(tool) == {"key", "tool_type", "title", "instance_prefix", "configuration"}
        for tool in tools
    )
    assert {tool["key"] for tool in tools} >= {
        "benchmark-list",
        "sector-list",
        "industry-list",
        "constituent-list",
        "ratio-chart",
    }
    first["tools"][0]["configuration"]["symbol"] = "MUTATED"
    assert second["tools"][0]["configuration"]["symbol"] == "SPY"


def test_factory_and_maintenance_project_the_same_semantic_defaults():
    catalogue = {tool["key"]: tool for tool in tool_catalogue()["tools"]}
    maintenance = {item["key"]: item for item in default_maintenance_tool_dependencies()}

    assert set(maintenance) == set(catalogue)
    assert (
        maintenance["relative-rotation"]["configuration"]
        == catalogue["relative-rotation"]["configuration"]
    )
    assert (
        factory_tool_configuration("relative-rotation", "relative_rotation")
        == catalogue["relative-rotation"]["configuration"]
    )
    assert factory_tool_configuration(
        "relative-rotation", "relative_rotation", {"timeframe": "MN"}
    ) == {**catalogue["relative-rotation"]["configuration"], "timeframe": "MN"}
    assert factory_tool_configuration(
        "constituent-list", "watchlist", {"market_group": "custom"}
    ) == {"market_group": "custom"}


def test_default_maintenance_projects_ratio_and_rrg_inputs_from_catalogue_config():
    specs = default_maintenance_request_specs()
    ratio = next(spec for spec in specs if (spec.get("analysis") or {}).get("kind") == "ratio")
    rrg = next(spec for spec in specs if (spec.get("analysis") or {}).get("kind") == "rrg")

    assert ratio["analysis"]["legs"] == [{"symbol": "SPY"}, {"symbol": "RSP"}]
    assert rrg["target"] == {"kind": "market_group", "group_key": "sp500-sectors"}
    assert rrg["analysis"]["benchmark_symbol"] == "SPY"
    assert {spec["target"].get("group_key") for spec in specs} >= {
        "sp500-sectors",
        "us-benchmarks",
    }
    assert maintenance_request_specs("chart", {"expression": "=SPY/RSP"})[0]["analysis"] == {
        "kind": "ratio",
        "legs": [{"symbol": "SPY"}, {"symbol": "RSP"}],
    }
