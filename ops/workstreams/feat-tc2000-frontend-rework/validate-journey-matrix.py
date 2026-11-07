#!/usr/bin/env python3
"""Fail closed when a current frontend route/tool/factory action lacks journey mapping."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "ops/workstreams/feat-tc2000-frontend-rework/journey-matrix.json"
ALLOWED_STATES = {
    "focused_route_contract",
    "pending_full_semantic_journey",
    "focused_units_browser_pending",
    "focused_units_combined_browser_pending",
    "focused_component_combined_browser_pending",
    "pending_provider_contract_and_browser",
    "focused_store_browser_pending",
    "pending_route_action_matrix",
    "pending_combined_browser",
    "pending_shared_search_and_secondary_route_browser",
    "pending_combined_backend_browser",
    "pending_full_pair_browser",
    "pending_provider_catalogue_and_browser",
    "pending_browser_roundtrip",
    "pending_secondary_route_action_journeys",
    "pending_secondary_route_visual_review",
    "focused_negative_assertion_combined_browser_pending",
    "owner_mapped_browser_pending",
    "source_mapped_browser_pending",
}


def _control_surfaces() -> list[dict[str, Any]]:
    excluded = {
        "frontend/src/views/BasketsView.vue",
        "frontend/src/views/ETFHoldingsView.vue",
        "frontend/src/views/StrategyLabView.vue",
        "frontend/src/views/StrategyLabV2View.vue",
        "frontend/src/views/StudyLabView.vue",
        "frontend/src/components/workstation/CodeLibraryTool.vue",
        "frontend/src/components/workstation/ResearchResultsTool.vue",
        "frontend/src/components/workstation/StudyLabTool.vue",
    }
    roots = [ROOT / "frontend/src/views", ROOT / "frontend/src/components"]
    surfaces: list[dict[str, Any]] = []
    pattern = re.compile(r"<([a-z][\w.-]*)\b([^>]*)>", re.IGNORECASE)
    for source_root in roots:
        for path in sorted(source_root.rglob("*.vue")):
            relative = path.relative_to(ROOT).as_posix()
            if relative in excluded or "/components/etf/" in relative or "/components/strategy/" in relative:
                continue
            text = path.read_text()
            match = re.search(r"<template>(.*?)</template>", text, re.DOTALL)
            if not match:
                continue
            controls = []
            for tag, attributes in pattern.findall(match.group(1)):
                attrs = " ".join(attributes.split())
                native_control = tag.lower() in {"button", "a", "input", "select", "textarea"}
                bound_action = bool(re.search(r"(?:@|v-on:)(?:click|submit|change|input|keydown|keyup|pointerdown|pointerup)\b", attrs))
                semantic_action = bool(re.search(r"\brole=(?:\"|')?(?:button|menuitem|menuitemradio|option|tab)(?:\"|')?", attrs))
                if native_control or bound_action or semantic_action:
                    controls.append(f"<{tag.lower()} {attrs}>")
            if not controls:
                continue
            normalized = json.dumps(controls, ensure_ascii=False, separators=(",", ":"))
            journeys = ["TC09"]
            if relative.endswith("WorkstationView.vue"):
                journeys = ["TC01", "TC02", "TC06", "TC07", "TC08"]
            elif relative.endswith("SearchBar.vue") or relative.endswith("DashboardInstrumentSearch.vue"):
                journeys = ["TC02"]
            elif any(token in relative for token in ("RelativeRotationTool", "RatioUPlot")):
                journeys = ["TC05"]
            elif any(token in relative for token in ("ChartPanel", "HistoryAcquisitionControl", "TimeframeSelector", "UPlotChart")):
                journeys = ["TC03", "TC04"]
            elif any(token in relative for token in ("WorkspaceLayoutHost", "ToolWindow", "LayoutPicker")):
                journeys = ["TC06", "TC07"]
            elif "/components/workstation/" in relative or relative.endswith("ChartView.vue"):
                journeys = ["TC04", "TC06", "TC08"]
            surfaces.append({
                "source": relative,
                "control_count": len(controls),
                "signature_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
                "journeys": journeys,
            })
    return surfaces


def _source_inventory() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], set[tuple[str, str, str]], str]:
    router = (ROOT / "frontend/src/router/index.ts").read_text()
    routes: dict[str, dict[str, str]] = {}
    for line in router.splitlines():
        if "{ path:" not in line:
            continue
        component_match = re.search(r"\{ path: '([^']+)', component: (\w+)", line)
        redirect_match = re.search(r"\{ path: '([^']+)', redirect: (.+?)(?: \},?$)", line.strip())
        if component_match:
            routes[component_match.group(1)] = {"component": component_match.group(2)}
        elif redirect_match:
            routes[redirect_match.group(1)] = {"component": "redirect", "redirect": redirect_match.group(2)}
    navigation = router.split("export const sharedShellNavigation = [", 1)[1].split("] as const", 1)[0]
    shell_actions = set(re.findall(
        r"\{ key: '([^']+)', label: '([^']+)', icon: '[^']*', path: '([^']+)'",
        navigation,
    ))
    catalogue_module = ROOT / "backend/app/services/workstation_tool_catalogue.py"
    catalogue_tree = ast.parse(catalogue_module.read_text())
    catalogue_assignment = next(
        node for node in catalogue_tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_TOOLS"
    )
    catalogue_tools = ast.literal_eval(catalogue_assignment.value)
    tools = {str(item["key"]): item for item in catalogue_tools}

    source = (ROOT / "backend/app/routers/workspaces.py").read_text()
    tree = ast.parse(source)
    factory = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_factory_tabs"
    )
    default_windows = next(
        ast.literal_eval(node.value)
        for node in fn_body(factory)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "default_windows" for target in node.targets)
    )
    timeframe_node = next(
        node.value for node in ast.walk(factory)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "timeframe_configurations" for target in node.targets)
    )
    timeframe_configurations = ast.literal_eval(timeframe_node.body) if isinstance(timeframe_node, ast.IfExp) else {}

    def panels_for(windows: list[Any], special_timeframes: bool = False) -> list[dict[str, Any]]:
        result = []
        for item in windows:
            key, tool_type, title = item[:3]
            override = item[3] if len(item) == 4 else {}
            definition = tools.get(key) or next(
                (candidate for candidate in catalogue_tools if candidate["tool_type"] == tool_type),
                None,
            )
            if definition is None or definition["tool_type"] != tool_type:
                raise ValueError(f"factory panel has no canonical catalogue definition: {key}")
            configuration = dict(definition["configuration"])
            if special_timeframes and not override:
                override = timeframe_configurations.get(key, {})
            configuration.update(override)
            result.append({
                "instance_key": key,
                "catalogue_key": definition["key"],
                "tool_type": tool_type,
                "title": title,
                "configuration": configuration,
            })
        return result

    layouts: dict[str, dict[str, Any]] = {
        "us-top-down": {"name": "US Top Down", "panels": panels_for(default_windows)}
    }
    for node in ast.walk(factory):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "enumerate"
            and node.args
            and isinstance(node.args[0], ast.List)
        ):
            continue
        try:
            rows = ast.literal_eval(node.args[0])
        except (ValueError, TypeError):
            continue
        for key, title, windows in rows:
            layouts[key] = {"name": title, "panels": panels_for(windows, key == "four-timeframe")}
    return routes, tools, layouts, _control_surfaces(), shell_actions, "backend/app/routers/workspaces.py:_factory_tabs"


def fn_body(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    return function.body


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    journeys = data.get("journeys", [])
    journey_ids = [row.get("id") for row in journeys if isinstance(row, dict)]
    if len(journey_ids) != len(set(journey_ids)):
        errors.append("journey IDs must be unique")
    journey_set = set(journey_ids)
    mapped_groups = (
        ("route", data.get("routes", []), "path"),
        ("shell action", data.get("shell_actions", []), "key"),
        ("Add-tool definition", data.get("add_tool_definitions", []), "key"),
        ("factory layout", data.get("factory_layouts", []), "key"),
        ("control surface", data.get("control_surfaces", []), "source"),
        ("action", data.get("actions", []), "id"),
        ("journey", journeys, "id"),
    )
    for label, rows, key in mapped_groups:
        if not isinstance(rows, list):
            errors.append(f"{label} inventory must be a list")
            continue
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"{label} row must be an object")
                continue
            identity = row.get(key)
            if not isinstance(identity, str) or not identity.strip():
                errors.append(f"{label} is missing {key}")
                continue
            if identity in seen:
                errors.append(f"duplicate {label} mapping: {identity}")
            seen.add(identity)
            state = row.get("evidence_status")
            evidence = row.get("evidence")
            pending_reason = row.get("pending_reason")
            if state not in ALLOWED_STATES:
                errors.append(f"{label} {identity} has unknown evidence_status")
            if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item for item in evidence):
                errors.append(f"{label} {identity} is missing evidence mapping")
            if str(state).startswith("pending") and (not isinstance(pending_reason, str) or not pending_reason.strip()):
                errors.append(f"{label} {identity} is pending without a reason")
            refs = row.get("journeys", []) if label == "control surface" else row.get("journey_refs", [])
            if label != "journey" and not row.get("journey") and not refs:
                errors.append(f"{label} {identity} is missing its journey mapping")
            if row.get("journey") and row["journey"] not in journey_set:
                errors.append(f"{label} {identity} references missing journey {row['journey']}")
            if label == "control surface" and any(ref not in journey_set for ref in refs):
                errors.append(f"control surface {identity} references an unknown journey")
            for item in evidence if isinstance(evidence, list) else []:
                if row.get("owner", data.get("owner")) == data.get("owner") and not (ROOT / item).is_file():
                    errors.append(f"{label} {identity} evidence path is missing: {item}")

    try:
        actual_routes, actual_tools, actual_layouts, actual_controls, actual_shell_actions, factory_source = _source_inventory()
    except (OSError, StopIteration, IndexError, SyntaxError, ValueError) as exc:
        return errors + [f"cannot read current route/tool/factory inventory: {exc}"]
    rows = data.get("routes", [])
    matrix_routes = {
        row.get("path"): {key: row[key] for key in ("component", "redirect") if key in row}
        for row in rows if isinstance(row, dict)
    }
    if matrix_routes != actual_routes:
        errors.append(
            "route mapping mismatch; "
            f"missing={sorted(set(actual_routes) - set(matrix_routes))}, stale={sorted(set(matrix_routes) - set(actual_routes))}, "
            f"changed={sorted(key for key in set(matrix_routes) & set(actual_routes) if matrix_routes[key] != actual_routes[key])}"
        )
    matrix_shell_actions = {
        (row.get("key"), row.get("label"), row.get("path"))
        for row in data.get("shell_actions", []) if isinstance(row, dict)
    }
    if matrix_shell_actions != actual_shell_actions:
        errors.append("shell navigation mapping differs from the actual shared navigation controls")
    matrix_tools = {
        row.get("key"): {
            "key": row.get("key"),
            "tool_type": row.get("tool_type"),
            "title": row.get("title"),
            "instance_prefix": row.get("instance_prefix"),
            "configuration": row.get("configuration"),
        }
        for row in data.get("add_tool_definitions", []) if isinstance(row, dict)
    }
    if matrix_tools != actual_tools:
        errors.append(
            "Add-tool mapping mismatch; missing="
            f"{sorted(set(actual_tools) - set(matrix_tools))}, stale={sorted(set(matrix_tools) - set(actual_tools))}, "
            f"changed={sorted(key for key in set(actual_tools) & set(matrix_tools) if actual_tools[key] != matrix_tools[key])}"
        )
    matrix_layouts = {
        row.get("key"): {
            "name": row.get("name"),
            "panels": [
                {key: panel.get(key) for key in ("instance_key", "catalogue_key", "tool_type", "title", "configuration")}
                for panel in row.get("panels", []) if isinstance(panel, dict)
            ],
        }
        for row in data.get("factory_layouts", []) if isinstance(row, dict)
    }
    if matrix_layouts != actual_layouts:
        errors.append("factory layout/panel identity or configuration mapping differs from current factory definitions")
    for layout in data.get("factory_layouts", []):
        if not isinstance(layout, dict):
            continue
        for panel in layout.get("panels", []):
            if not isinstance(panel, dict) or panel.get("journey") not in journey_set:
                errors.append(f"factory layout {layout.get('key')} contains a panel without a declared journey")
            elif not panel.get("evidence") or not panel.get("instance_key") or not panel.get("catalogue_key"):
                errors.append(f"factory layout {layout.get('key')} contains an unmapped panel identity")

    matrix_controls = {
        row.get("source"): (row.get("control_count"), row.get("signature_sha256"))
        for row in data.get("control_surfaces", []) if isinstance(row, dict)
    }
    expected_controls = {
        row["source"]: (row["control_count"], row["signature_sha256"])
        for row in actual_controls
    }
    if matrix_controls != expected_controls:
        errors.append(
            f"exposed control mapping mismatch; missing={sorted(set(expected_controls) - set(matrix_controls))}, "
            f"stale={sorted(set(matrix_controls) - set(expected_controls))}, "
            f"changed={sorted(key for key in set(matrix_controls) & set(expected_controls) if matrix_controls[key] != expected_controls[key])}"
        )

    control_sources = set(expected_controls)
    for label, rows in (("shell action", data.get("shell_actions", [])), ("action", data.get("actions", []))):
        for row in rows:
            if label == "action" and isinstance(row, dict) and row.get("owner", data.get("owner")) != data.get("owner"):
                continue
            refs = row.get("control_surface_refs", []) if isinstance(row, dict) else []
            if not refs or any(ref not in control_sources for ref in refs):
                errors.append(f"{label} {row.get('key', row.get('id')) if isinstance(row, dict) else row} lacks a current control-surface mapping")

    for owner in data.get("cross_owner_journeys", []):
        if not isinstance(owner, dict) or not owner.get("owner") or not owner.get("matrix"):
            errors.append("cross-owner matrix reference is incomplete")
        elif not (owner.get("journey_ids") or owner.get("journey_refs")) or not owner.get("status"):
            errors.append(f"cross-owner matrix {owner.get('owner')} lacks journey mapping/status")
        else:
            allowed_refs = set(owner.get("journey_ids", [])) | set(owner.get("journey_refs", []))
            external_path = (ROOT / owner["matrix"]).resolve()
            try:
                external = json.loads(external_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"cross-owner matrix {owner.get('owner')} cannot be read: {exc}")
                continue
            if owner["owner"] == "feat-etf-holdings-constituents":
                external_refs = set((external.get("approved_journey_ids") or {}).keys())
            else:
                external_refs = {
                    ref
                    for row in external.get("journeys", []) if isinstance(row, dict)
                    for ref in row.get("approved_journey", []) if isinstance(ref, str)
                }
            declared_external = set(owner.get("journey_ids", [])) | set(owner.get("journey_refs", []))
            if not external_refs or not declared_external.issubset(external_refs):
                errors.append(f"cross-owner matrix {owner.get('owner')} references absent owner journeys")
            for action in data.get("actions", []):
                if action.get("owner") != owner.get("owner"):
                    continue
                refs = action.get("journey_refs", [])
                if not refs or any(ref not in allowed_refs for ref in refs):
                    errors.append(f"cross-owner action {action.get('id')} references an undeclared owner journey")
    analysis = data.get("analysis_coverage", {})
    required_ratios = {"XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"}
    if set(analysis.get("daily_weekly_monthly", [])) != {"D1", "W1", "MN"}:
        errors.append("analysis journey must map D1, W1, and MN")
    if set(analysis.get("ratio_symbols", [])) != required_ratios:
        errors.append("analysis journey must map all eleven ratio symbols")
    if analysis.get("monthly_warmup_bars") != 50:
        errors.append("analysis journey must retain the fifty-bar monthly warmup")
    if analysis.get("journey") != "TC03/TC05" or not analysis.get("pending_reason"):
        errors.append("analysis depth/pair mapping is missing its journey or pending status explanation")
    counts = data.get("counts", {})
    if counts.get("routes_and_aliases") != len(actual_routes):
        errors.append("route count summary is stale")
    if counts.get("add_tool_definitions") != len(actual_tools):
        errors.append("Add-tool count summary is stale")
    if counts.get("factory_layouts") != len(actual_layouts):
        errors.append("factory layout count summary is stale")
    if counts.get("factory_instances") != sum(len(layout["panels"]) for layout in actual_layouts.values()):
        errors.append("factory instance count summary is stale")
    return errors


def self_test(data: dict[str, Any]) -> None:
    errors = validate(data)
    _require(not errors, "valid journey inventory failed: " + "; ".join(errors))
    mutated = json.loads(json.dumps(data))
    mutated["add_tool_definitions"][0].pop("journey")
    _require(any("missing its journey mapping" in error for error in validate(mutated)), "missing journey alone was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["add_tool_definitions"][0].pop("evidence")
    _require(any("missing evidence mapping" in error for error in validate(mutated)), "missing Add-tool evidence was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["routes"].pop()
    _require(any("route mapping mismatch" in error for error in validate(mutated)), "unmapped route was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["routes"][0]["component"] = "WrongRouteComponent"
    _require(any("route mapping mismatch" in error for error in validate(mutated)), "route component drift was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["factory_layouts"][0]["panels"].pop()
    _require(any("factory layout/panel identity or configuration mapping" in error for error in validate(mutated)), "factory panel drift was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["factory_layouts"][0]["panels"][0]["configuration"]["market_group"] = "wrong-universe"
    _require(any("factory layout/panel identity or configuration mapping" in error for error in validate(mutated)), "factory panel configuration drift was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["actions"][0].pop("evidence")
    _require(any("action TC-A-" in error and "missing evidence mapping" in error for error in validate(mutated)), "missing action mapping was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["control_surfaces"].pop()
    _require(any("exposed control mapping mismatch" in error for error in validate(mutated)), "unmapped exposed control surface was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["control_surfaces"][0]["signature_sha256"] = "0" * 64
    _require(any("exposed control mapping mismatch" in error for error in validate(mutated)), "changed exposed control surface was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["actions"][0]["control_surface_refs"] = []
    _require(any("lacks a current control-surface mapping" in error for error in validate(mutated)), "unconnected action surface was accepted")
    print("PASS: current route, shell, canonical Add-tool, factory panel, and action-control mapping fail closed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    data = json.loads(MATRIX.read_text())
    if args.self_test:
        self_test(data)
    errors = validate(data)
    if errors:
        print("FAIL: " + "\nFAIL: ".join(errors))
        return 1
    counts = data["counts"]
    print(
        "PASS: mapped "
        f"{counts['routes_and_aliases']} routes/aliases, {counts['shell_actions']} shell actions, "
        f"{counts['add_tool_definitions']} Add-tool definitions, {counts['factory_layouts']} factory layouts/"
        f"{counts['factory_instances']} instances, {counts['owned_actions']} TC actions, "
        f"{counts['etf_actions']} ETF actions, {counts['strategy_actions']} Strategy actions, "
        f"and {len(data['journeys'])} TC journeys; pending gaps remain explicit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
