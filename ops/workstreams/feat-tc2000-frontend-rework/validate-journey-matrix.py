#!/usr/bin/env python3
"""Fail closed when a current frontend route/tool/factory action lacks journey mapping."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import tempfile
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


def _control_surfaces(root: Path = ROOT) -> list[dict[str, Any]]:
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
    roots = [root / "frontend/src/views", root / "frontend/src/components"]
    surfaces: list[dict[str, Any]] = []
    pattern = re.compile(r"<([a-z][\w.-]*)\b([^>]*)>", re.IGNORECASE)
    for source_root in roots:
        for path in sorted(source_root.rglob("*.vue")):
            relative = path.relative_to(root).as_posix()
            if relative in excluded or "/components/etf/" in relative or "/components/strategy/" in relative:
                continue
            text = path.read_text()
            template = _outer_sfc_template(text)
            if template is None:
                continue
            controls = []
            for tag, attributes in pattern.findall(_rendered_template_markup(template)):
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


def _control_mapping_error(matrix_controls: list[dict[str, Any]], actual_controls: list[dict[str, Any]]) -> str | None:
    matrix = {
        row.get("source"): (row.get("control_count"), row.get("signature_sha256"))
        for row in matrix_controls if isinstance(row, dict)
    }
    expected = {
        row["source"]: (row["control_count"], row["signature_sha256"])
        for row in actual_controls
    }
    if matrix == expected:
        return None
    return (
        f"exposed control mapping mismatch; missing={sorted(set(expected) - set(matrix))}, "
        f"stale={sorted(set(matrix) - set(expected))}, "
        f"changed={sorted(key for key in set(matrix) & set(expected) if matrix[key] != expected[key])}"
    )


def _tag_end(source: str, start: int) -> int | None:
    """Return the end of one HTML-like tag, ignoring `>` inside quotes."""
    quote: str | None = None
    index = start + 1
    while index < len(source):
        character = source[index]
        if quote:
            if character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == ">":
            return index + 1
        index += 1
    return None


def _skip_vue_interpolation(source: str, start: int) -> int:
    """Skip one `{{ ... }}` expression so template strings inside it are inert."""
    index = start + 2
    quote: str | None = None
    escaped = False
    braces = 0
    while index < len(source):
        character = source[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {"'", '"', "`"}:
            quote = character
        elif source.startswith("{{", index):
            braces += 1
            index += 1
        elif source.startswith("}}", index):
            if braces == 0:
                return index + 2
            braces -= 1
            index += 1
        index += 1
    return len(source)


def _rendered_template_markup(source: str) -> str:
    """Remove non-rendered comments/interpolations before scanning controls."""
    pieces: list[str] = []
    cursor = 0
    while cursor < len(source):
        if source.startswith("<!--", cursor):
            end = source.find("-->", cursor + 4)
            cursor = len(source) if end < 0 else end + 3
            continue
        if source.startswith("{{", cursor):
            cursor = _skip_vue_interpolation(source, cursor)
            continue
        pieces.append(source[cursor])
        cursor += 1
    return "".join(pieces)


def _outer_sfc_template(source: str) -> str | None:
    """Extract one complete Vue SFC template, including nested `<template>` blocks."""
    opening: int | None = None
    cursor = 0
    while cursor < len(source):
        start = source.find("<", cursor)
        if start < 0:
            return None
        if source.startswith("<!--", start):
            end = source.find("-->", start + 4)
            cursor = len(source) if end < 0 else end + 3
            continue
        end = _tag_end(source, start)
        if end is None:
            return None
        match = re.match(r"<\s*(/?)\s*([A-Za-z][\w.-]*)\b", source[start:end])
        cursor = end
        if not match or match.group(1):
            continue
        name = match.group(2).lower()
        if name == "template":
            opening = start
            break
        # SFC non-template blocks are raw text. Ignore their contents so a
        # template-looking string in script, style, or a custom block cannot
        # be mistaken for the rendered component template.
        close = re.search(rf"</\s*{re.escape(name)}\s*>", source[cursor:], re.IGNORECASE)
        if not close:
            return None
        cursor += close.end()
    if opening is None:
        return None
    opening_end = _tag_end(source, opening)
    if opening_end is None:
        return None
    depth = 1
    cursor = opening_end
    while cursor < len(source):
        if source.startswith("{{", cursor):
            cursor = _skip_vue_interpolation(source, cursor)
            continue
        start = source.find("<", cursor)
        interpolation = source.find("{{", cursor)
        if interpolation >= 0 and (start < 0 or interpolation < start):
            cursor = _skip_vue_interpolation(source, interpolation)
            continue
        if start < 0:
            return None
        if source.startswith("<!--", start):
            comment_end = source.find("-->", start + 4)
            cursor = len(source) if comment_end < 0 else comment_end + 3
            continue
        end = _tag_end(source, start)
        if end is None:
            return None
        match = re.match(r"<\s*(/?)\s*([A-Za-z][\w.-]*)\b", source[start:end])
        cursor = end
        if not match or match.group(2).lower() != "template":
            continue
        if match.group(1):
            depth -= 1
            if depth == 0:
                return source[opening_end:start]
        elif not source[start:end].rstrip().endswith("/>"):
            depth += 1
    return None


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
    if not isinstance(journeys, list) or not journeys:
        errors.append("journey inventory must be a non-empty list")
        journeys = []
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

    control_error = _control_mapping_error(data.get("control_surfaces", []), actual_controls)
    if control_error:
        errors.append(control_error)
    control_sources = {row["source"] for row in actual_controls}
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
            owner_sources = {
                "feat-etf-holdings-constituents": ("etf_matrix", "etf_matrix_provenance"),
                "feat-strategy-lab-v2": ("strategy_matrix", "strategy_matrix_provenance"),
            }
            source_keys = owner_sources.get(owner.get("owner"))
            if source_keys is None:
                errors.append(f"cross-owner matrix has an unknown owner: {owner.get('owner')}")
                continue
            frozen_key, provenance_key = source_keys
            frozen_path = data.get("sources", {}).get(frozen_key)
            provenance = data.get("sources", {}).get(provenance_key)
            if not isinstance(provenance, dict) or not isinstance(frozen_path, str):
                errors.append(f"cross-owner matrix {owner.get('owner')} lacks TC-owned frozen input provenance")
                continue
            if owner.get("matrix") != frozen_path or any(
                owner.get(field) != provenance.get(field)
                for field in ("canonical_matrix", "source_commit", "source_blob", "source_sha256")
            ):
                errors.append(f"cross-owner matrix {owner.get('owner')} disagrees with its frozen input provenance")
            allowed_refs = set(owner.get("journey_ids", [])) | set(owner.get("journey_refs", []))
            external_path = (ROOT / owner["matrix"]).resolve()
            try:
                external_path.relative_to(ROOT)
            except ValueError:
                errors.append(f"cross-owner journey input for {owner.get('owner')} must be a TC-owned frozen copy")
                continue
            source_hash = owner.get("source_sha256")
            if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
                errors.append(f"cross-owner matrix {owner.get('owner')} lacks a pinned source SHA256")
                continue
            if not re.fullmatch(r"[0-9a-f]{40}", str(owner.get("source_commit", ""))) or not re.fullmatch(r"[0-9a-f]{40}", str(owner.get("source_blob", ""))):
                errors.append(f"cross-owner matrix {owner.get('owner')} lacks canonical owner commit/blob provenance")
                continue
            try:
                external_bytes = external_path.read_bytes()
                external = json.loads(external_bytes)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"cross-owner frozen matrix {owner.get('owner')} cannot be read: {exc}")
                continue
            if hashlib.sha256(external_bytes).hexdigest() != source_hash:
                errors.append(f"cross-owner frozen matrix {owner.get('owner')} differs from its pinned source SHA256")
            canonical_relative = owner.get("canonical_matrix")
            if not isinstance(canonical_relative, str) or not canonical_relative:
                errors.append(f"cross-owner matrix {owner.get('owner')} omits its canonical owner record path")
            else:
                canonical_path = (ROOT / canonical_relative).resolve()
                if canonical_path.is_file():
                    canonical_root = next((parent for parent in canonical_path.parents if (parent / ".git").exists()), None)
                    if canonical_root is None:
                        errors.append(f"checked-out canonical journey matrix {owner.get('owner')} has no Git checkout provenance")
                    else:
                        canonical_file = canonical_path.relative_to(canonical_root).as_posix()
                        pinned_blob = subprocess.run(
                            ["git", "-C", str(canonical_root), "rev-parse", f"{owner['source_commit']}:{canonical_file}"],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        pinned_bytes = subprocess.run(
                            ["git", "-C", str(canonical_root), "show", f"{owner['source_commit']}:{canonical_file}"],
                            check=False,
                            capture_output=True,
                        )
                        if pinned_blob.returncode != 0 or pinned_blob.stdout.strip() != owner["source_blob"]:
                            errors.append(f"canonical journey source commit/blob for {owner.get('owner')} is unavailable or mismatched")
                        elif pinned_bytes.returncode != 0 or hashlib.sha256(pinned_bytes.stdout).hexdigest() != source_hash:
                            errors.append(f"canonical journey source bytes for {owner.get('owner')} differ from its reviewed frozen copy")
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
    nested_template = '''<template>
      <template v-if="ready"><button @click="first">First</button></template>
      <!-- <button @click="comment">not rendered</button> -->
      <section>{{ '<template><button @click="expression">ignored</button></template>' }}</section>
      <button @click="afterNested">After nested block</button>
    </template>
    <script setup>const example = "<template><button>not an SFC control</button></template>"</script>'''
    extracted = _outer_sfc_template(nested_template)
    _require(extracted is not None, "nested SFC template was not extracted")
    rendered_markup = _rendered_template_markup(extracted)
    _require(
        '<button @click="afterNested">' in rendered_markup
        and "comment" not in rendered_markup
        and "expression" not in rendered_markup
        and "not an SFC control" not in rendered_markup,
        "outer SFC extraction truncated nested controls or included non-template markup",
    )
    with tempfile.TemporaryDirectory(prefix="tc-journey-nested-template-") as temporary:
        root = Path(temporary)
        view = root / "frontend/src/views/Nested.vue"
        view.parent.mkdir(parents=True)
        view.write_text(nested_template)
        actual = _control_surfaces(root)
        _require(len(actual) == 1 and actual[0]["control_count"] == 2, "nested-template controls were not inventoried")
        _require(
            "Nested.vue" in (_control_mapping_error([], actual) or ""),
            "an unmapped control after a nested template was not rejected",
        )
    errors = validate(data)
    _require(not errors, "valid journey inventory failed: " + "; ".join(errors))
    mutated = json.loads(json.dumps(data))
    mutated["add_tool_definitions"][0].pop("journey")
    _require(any("missing its journey mapping" in error for error in validate(mutated)), "missing journey alone was accepted")
    mutated = json.loads(json.dumps(data))
    mutated.pop("journeys")
    _require(any("journey inventory must be a non-empty list" in error for error in validate(mutated)), "missing journey inventory was accepted")
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
    mutated = json.loads(json.dumps(data))
    mutated["cross_owner_journeys"][0]["journey_ids"] = ["missing-owner-journey"]
    _require(any("references absent owner journeys" in error for error in validate(mutated)), "missing cross-owner journey was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["cross_owner_journeys"][0]["source_sha256"] = "0" * 64
    _require(any("differs from its pinned source SHA256" in error for error in validate(mutated)), "changed frozen owner matrix was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["cross_owner_journeys"][0]["canonical_matrix"] = "../missing-owner-worktree/journey-matrix.json"
    _require(any("disagrees with its frozen input provenance" in error for error in validate(mutated)), "unreviewed canonical owner path was accepted")
    canonical_reference = data["cross_owner_journeys"][0].get("canonical_matrix")
    if isinstance(canonical_reference, str) and (ROOT / canonical_reference).resolve().is_file():
        mutated = json.loads(json.dumps(data))
        mutated["cross_owner_journeys"][0]["source_commit"] = "0" * 40
        _require(any("canonical journey source commit/blob" in error for error in validate(mutated)), "changed canonical owner provenance was accepted")
    mutated = json.loads(json.dumps(data))
    mutated["cross_owner_journeys"][0]["matrix"] = "../missing-owner-worktree/journey-matrix.json"
    _require(any("TC-owned frozen copy" in error or "frozen matrix" in error for error in validate(mutated)), "missing standalone owner matrix copy was accepted")
    print("PASS: route, shell, canonical Add-tool, factory panel, action-control and portable owner-journey mappings fail closed")


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
