#!/usr/bin/env python3
"""Guard one Codex implementation session and its worktree-owned resources."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PREFIXES = ("feat/", "fix/", "chore/", "docs/", "test/")
TERMINAL = {"integrated", "closed", "superseded", "blocked"}
DOCKER_LIMIT_BYTES = 5_000_000_000
DOCKER_READY_TIMEOUT_SECONDS = 180
DOCKER_READY_POLL_SECONDS = 3


def run(
    *args: str, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise SystemExit(
            result.stderr.strip() or result.stdout.strip() or "command failed"
        )
    return result


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    return run("git", *args, cwd=cwd, check=check).stdout.strip()


def dirty_paths(path: Path) -> list[str]:
    """Return porcelain paths without the two-column status prefix."""
    return [
        line[3:] if len(line) >= 3 else line
        for line in git("status", "--porcelain", cwd=path).splitlines()
    ]


def root() -> Path:
    return Path(git("rev-parse", "--show-toplevel")).resolve()


def common_root() -> Path:
    common = Path(git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root() / common
    return common.resolve().parent


def slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or "detached-head"


def authorized_goal_budget(plan: dict[str, str]) -> int | None:
    """Extract a budget only from an explicit human authorization field."""
    authorization = plan.get("human_goal_budget_authorization", "")
    if not authorization or authorization.strip().lower() in {"none", "pending"}:
        return None
    match = re.fullmatch(
        r"\s*(?:authorized|human-authorized)\s*:\s*([1-9][0-9]*)\s*",
        authorization,
        re.I,
    )
    return int(match.group(1)) if match else None


def make_goal_request(
    objective: str, plan: dict[str, Any], *, ready: bool = True
) -> dict[str, Any]:
    """Build the actual Codex request; metadata stays in durable session state."""
    request: dict[str, Any] = {"objective": objective}
    if ready:
        budget = authorized_goal_budget(plan)
        if budget is not None:
            request["token_budget"] = budget
    return request


def worktree_id(path: Path, branch: str) -> str:
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:10]
    return f"{slug(branch)}-{digest}"


def worktree_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in git("worktree", "list", "--porcelain").splitlines() + [""]:
        if not line:
            if current:
                records.append(current)
                current = {}
        elif line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ")
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch ").removeprefix("refs/heads/")
        elif line == "detached":
            current["branch"] = "(detached)"
    return records


def branch_and_path(*, allow_protected: bool = False) -> tuple[str, Path]:
    path = root()
    branch = git("branch", "--show-current", cwd=path)
    if not branch:
        raise SystemExit("agent sessions cannot start from detached HEAD")
    if branch in {"master", "staging"} and not allow_protected:
        raise SystemExit(
            f"agent implementation sessions cannot run on protected branch {branch}"
        )
    if not branch.startswith(PREFIXES) and not (
        allow_protected and branch in {"master", "staging"}
    ):
        raise SystemExit(f"unsupported work branch: {branch}")
    expected = (common_root() / ".ai" / "worktrees" / slug(branch)).resolve()
    if path != expected:
        raise SystemExit(
            f"assigned worktree mismatch: expected {expected}, found {path}"
        )
    registered = {
        Path(item["path"]).resolve(): item.get("branch") for item in worktree_records()
    }
    if registered.get(path) != branch:
        raise SystemExit("Git does not register this path as the assigned worktree")
    return branch, path


def parse_plan(path: Path) -> dict[str, Any]:
    try:
        values = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise SystemExit(f"invalid workstream YAML: {path}: {exc}") from exc
    if not isinstance(values, dict):
        raise SystemExit(f"invalid workstream plan: {path} must contain a mapping")
    return values


def plan_ready(plan: dict[str, Any]) -> bool:
    if str(plan.get("schema")) != "4":
        return True
    if plan.get("planning_state") != "ready":
        return False
    if not all(
        isinstance(plan.get(key), list) and plan.get(key)
        for key in ("scope", "owned_paths", "acceptance_criteria")
    ):
        return False
    profile = plan.get("local_validation_profile")
    if profile not in {"none", "unit", "docker_integration", "full_stack_browser"}:
        return False
    tests = plan.get("branch_tests")
    return bool(tests) or bool(str(plan.get("branch_tests_reason", "")).strip())


def acceptance_criteria(plan: dict[str, Any]) -> list[dict[str, str]]:
    values = plan.get("acceptance_criteria") or []
    result: list[dict[str, str]] = []
    for index, item in enumerate(values, 1):
        if isinstance(item, dict):
            result.append(
                {
                    "id": str(item.get("id", f"AC{index}")),
                    "text": str(item.get("text", "")),
                }
            )
        else:
            result.append({"id": f"AC{index}", "text": str(item)})
    return result


def plan_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workstream(branch: str, path: Path) -> tuple[Path, dict[str, Any]]:
    stream = path / "ops" / "workstreams" / slug(branch)
    files = [stream / "plan.yaml", stream / "handoff.md", stream / "validation.jsonl"]
    missing = [str(item) for item in files if not item.exists()]
    if missing:
        raise SystemExit(
            "missing branch-owned workstream file(s): " + ", ".join(missing)
        )
    plan = parse_plan(files[0])
    if str(plan.get("schema")) not in {"2", "3", "4"} or plan.get("branch") != branch:
        raise SystemExit("workstream does not match a supported schema or branch")
    if not plan.get("human_intent_authorization") or plan[
        "human_intent_authorization"
    ].lower().startswith("pending"):
        raise SystemExit("workstream has no explicit human intent authorization")
    if plan.get("status") in TERMINAL:
        raise SystemExit(f"workstream status {plan.get('status')} is terminal")
    if not plan.get("goal") or "replace me" in plan["goal"].lower():
        raise SystemExit("workstream goal must be derived from the human request")
    if str(plan.get("schema")) in {"3", "4"} and not (stream / "session.json").exists():
        raise SystemExit(
            f"missing branch-owned session state: {stream / 'session.json'}"
        )
    return stream, plan


def claim_path(identifier: str) -> Path:
    directory = common_root() / ".ai" / "session-claims"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{identifier}.json"


@contextlib.contextmanager
def claim_lock():
    lock = common_root() / ".ai" / "session-claims" / ".lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_claim(identifier: str) -> dict[str, Any] | None:
    path = claim_path(identifier)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid session claim {path}: {exc}") from exc
    return value if isinstance(value, dict) else None


def verify_claim(identifier: str, session_id: str) -> dict[str, Any]:
    claim = read_claim(identifier)
    if not claim:
        raise SystemExit("no active session claim for this worktree")
    if claim.get("session_id") != session_id:
        raise SystemExit(
            "session claim belongs to another session; use explicit takeover"
        )
    return claim


def validate_retained(identifier: str) -> list[str]:
    """Validate retained-volume records and return the current worktree's names."""
    retained = retained_records()
    names: list[str] = []
    required = (
        "reason",
        "next_use",
        "recreate_impact",
        "review",
        "approximate_size_bytes",
    )
    for name, item in retained.items():
        if item.get("worktree_id") != identifier:
            continue
        if not name or any(not str(item.get(key, "")).strip() for key in required):
            raise SystemExit(f"retained volume record is incomplete: {name}")
        names.append(str(name))
    return sorted(names)


def docker_json(*args: str) -> list[dict[str, Any]] | None:
    if shutil.which("docker") is None:
        return None
    result = run("docker", *args, check=False)
    if result.returncode:
        return None
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def docker_system_df() -> dict[str, Any] | None:
    """Return Docker's detailed disk report, preserving unknown values.

    Docker emits one JSON object per resource class when ``--format`` is used;
    older versions may emit a single object containing Images/Volumes arrays.
    Normalize both forms so accounting never silently treats an unreported
    component as zero.
    """
    if shutil.which("docker") is None:
        return None
    result = run("docker", "system", "df", "-v", "--format", "{{json .}}", check=False)
    if result.returncode:
        return None
    records: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    if not records:
        return None
    if any(key in records[0] for key in ("Images", "Volumes", "Containers")):
        return records[0]
    normalized: dict[str, Any] = {}
    for value in records:
        kind = str(value.get("Type", "")).lower()
        if kind == "images":
            normalized.setdefault("Images", []).append(value)
        elif kind == "containers":
            normalized.setdefault("Containers", []).append(value)
        elif kind in {"local volumes", "volumes"}:
            normalized.setdefault("Volumes", []).append(value)
        elif kind == "build cache":
            normalized.setdefault("BuildCache", []).append(value)
    return normalized


def numeric_size(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.fullmatch(
            r"\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?i?B)?\s*", value, re.I
        )
        if match:
            number = float(match.group(1))
            unit = (match.group(2) or "B").upper()
            factors = {
                "B": 1,
                "KB": 1000,
                "MB": 1000**2,
                "GB": 1000**3,
                "TB": 1000**4,
                "PB": 1000**5,
                "KIB": 1024,
                "MIB": 1024**2,
                "GIB": 1024**3,
                "TIB": 1024**4,
                "PIB": 1024**5,
            }
            return int(number * factors.get(unit, 1))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def retained_records() -> dict[str, Any]:
    path = common_root() / ".ai" / "runtime" / "retained-volumes.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def recorded_testcontainer_sessions(identifier: str) -> set[str]:
    path = (
        common_root() / ".ai" / "runtime" / identifier / "testcontainers-sessions.json"
    )
    if not path.exists():
        return set()
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    sessions = value.get(identifier, []) if isinstance(value, dict) else []
    return {str(item) for item in sessions if item}


def owned_containers(
    identifier: str, projects: set[str], session_ids: set[str] | None = None
) -> list[dict[str, Any]] | None:
    ids_result = run("docker", "ps", "-aq", check=False)
    if ids_result.returncode:
        return None
    rows: list[dict[str, Any]] = []
    for container in ids_result.stdout.splitlines():
        inspected = run(
            "docker",
            "inspect",
            "--size",
            "--format",
            "{{json .}}",
            container,
            check=False,
        )
        if inspected.returncode:
            continue
        try:
            item = json.loads(inspected.stdout)
        except json.JSONDecodeError:
            continue
        labels = item.get("Config", {}).get("Labels") or {}
        if (
            labels.get("com.docker.compose.project") in projects
            or labels.get("charting.worktree.id") == identifier
            or labels.get("org.testcontainers.session-id") in (session_ids or set())
        ):
            rows.append(item)
    return rows


def docker_status(identifier: str, projects: set[str]) -> dict[str, Any]:
    if shutil.which("docker") is None:
        return {"available": False, "reason": "docker CLI unavailable"}
    info = run("docker", "info", check=False)
    if info.returncode:
        return {
            "available": False,
            "reason": info.stderr.strip() or "Docker daemon unavailable",
        }
    sessions = recorded_testcontainer_sessions(identifier)
    container_inventory = owned_containers(identifier, projects, sessions)
    containers = container_inventory or []
    bytes_known = sum(numeric_size(item.get("SizeRw")) for item in containers)
    image_inventory = docker_json("image", "ls", "--format", "{{json .}}")
    image_rows = image_inventory or []
    image_ids: set[str] = set()
    for row in image_rows:
        image_id = str(row.get("ID") or row.get("Id") or "")
        if not image_id:
            continue
        inspected = run(
            "docker",
            "image",
            "inspect",
            image_id,
            "--format",
            "{{json .}}",
            check=False,
        )
        if inspected.returncode == 0:
            try:
                labels = (json.loads(inspected.stdout).get("Config") or {}).get(
                    "Labels"
                ) or {}
            except json.JSONDecodeError:
                labels = {}
            if labels.get("charting.worktree.id") == identifier:
                image_ids.add(image_id)
        elif identifier in json.dumps(row):
            # Keep a conservative compatibility fallback for older Docker JSON
            # output that included labels directly in `image ls`.
            image_ids.add(image_id)
    volume_result = run(
        "docker",
        "volume",
        "ls",
        "-q",
        "--filter",
        f"label=charting.worktree.id={identifier}",
        check=False,
    )
    volumes = volume_result.stdout.splitlines() if volume_result.returncode == 0 else []
    disk = docker_system_df()
    unique_image_bytes = 0
    volume_bytes: int | None = None
    build_cache_bytes: int | None = None
    if disk:
        image_detail = disk.get("Images") or []
        unique_image_bytes = sum(
            numeric_size(item.get("UniqueSize"))
            for item in image_detail
            if str(item.get("ID") or item.get("Id")) in image_ids
        )
        volume_detail = disk.get("Volumes") or []
        owned_names = set(volumes)
        volume_bytes = sum(
            numeric_size(item.get("Size"))
            for item in volume_detail
            if str(item.get("Name")) in owned_names
        )
    builder = builder_name_from_projects(projects)
    if builder and run("docker", "buildx", "inspect", builder, check=False).returncode:
        builder = ""
    builder_result = (
        run("docker", "buildx", "du", "--builder", builder, "--verbose", check=False)
        if builder
        else None
    )
    if builder_result and builder_result.returncode == 0:
        values = re.findall(
            r"(?:Total|Size)\s*[: ]\s*([0-9.]+)\s*([KMGTP]?B)",
            builder_result.stdout,
            re.I,
        )
        if values:
            factors = {
                "B": 1,
                "KB": 1000,
                "MB": 1000**2,
                "GB": 1000**3,
                "TB": 1000**4,
                "PB": 1000**5,
            }
            number, unit = values[-1]
            build_cache_bytes = int(float(number) * factors[unit.upper()])
    components = [bytes_known, unique_image_bytes]
    if volume_bytes is not None:
        components.append(volume_bytes)
    if build_cache_bytes is not None:
        components.append(build_cache_bytes)
    known_total = sum(components)
    unknown_components: list[str] = []
    if container_inventory is None:
        unknown_components.append("container-inventory")
    if volume_result.returncode:
        unknown_components.append("volume-inventory")
    if image_inventory is None:
        unknown_components.append("image-inventory")
    if disk is None:
        unknown_components.append("docker-system-df")
    if volumes and volume_bytes is None:
        unknown_components.append("volume-usage")
    if builder and build_cache_bytes is None:
        unknown_components.append("build-cache")
    return {
        "available": True,
        "worktree_id": identifier,
        "projects": sorted(projects),
        "containers": [item.get("Name", "").lstrip("/") for item in containers],
        "container_count": len(containers),
        "testcontainer_sessions": sorted(sessions),
        "volume_count": len(volumes),
        "known_bytes": known_total,
        "unique_image_bytes": unique_image_bytes,
        "volume_bytes": volume_bytes,
        "build_cache_bytes": build_cache_bytes,
        "threshold_bytes": DOCKER_LIMIT_BYTES,
        "accounting_complete": disk is not None
        and (not builder or build_cache_bytes is not None),
        "unknown_components": unknown_components,
        "over_budget": known_total > DOCKER_LIMIT_BYTES,
        "unattributed_shared_layers_excluded": True,
    }


def profile_requires_docker(profile: str | None) -> bool:
    return profile in {"docker_integration", "full_stack_browser"}


def docker_ready(timeout: float = DOCKER_READY_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Ensure the existing Docker daemon is usable without installing/restarting it."""
    if shutil.which("docker") is None:
        raise SystemExit(
            "Docker CLI is unavailable; cannot run the required local validation"
        )
    initial = run("docker", "info", check=False)
    if initial.returncode == 0:
        return {"ready": True, "started_desktop": False, "wait_seconds": 0}
    started_desktop = False
    if sys.platform == "darwin" and Path("/Applications/Docker.app").exists():
        opener = shutil.which("open")
        if opener:
            launch = run(opener, "-a", "Docker", check=False)
            if launch.returncode == 0:
                started_desktop = True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(min(DOCKER_READY_POLL_SECONDS, max(0, deadline - time.monotonic())))
        probe = run("docker", "info", check=False)
        if probe.returncode == 0:
            return {
                "ready": True,
                "started_desktop": started_desktop,
                "wait_seconds": round(timeout - max(0, deadline - time.monotonic()), 1),
            }
    reason = initial.stderr.strip() or "Docker daemon did not become ready"
    raise SystemExit(
        f"Docker local validation is blocked after {int(timeout)} seconds: {reason}"
    )


def record_validation(stream: Path, payload: dict[str, Any]) -> None:
    journal = stream / "validation.jsonl"
    with journal.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def validation_evidence_current(
    stream: Path, head: str, profile: str | None = None
) -> bool:
    journal = stream / "validation.jsonl"
    if not journal.exists():
        return False
    for line in journal.read_text().splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        evidence_sha = (
            value.get("sha") or value.get("head_sha") or value.get("implementation_sha")
        )
        result = str(value.get("result", "")).lower()
        evidence_profile = str(value.get("profile", ""))
        if profile and evidence_profile and evidence_profile != profile:
            continue
        if (
            evidence_sha == head
            and result in {"pass", "passed", "green", "success"}
            and (not profile or evidence_profile == profile)
        ):
            return True
    return False


def project_names(branch: str) -> set[str]:
    suffix = hashlib.sha256(str(root()).encode()).hexdigest()[:8]
    return {
        f"charting-dev-{slug(branch)}-{suffix}",
        f"charting-stack-{slug(branch)}-{suffix}",
    }


def builder_name_from_projects(projects: set[str]) -> str:
    suffix = next(
        (
            item.rsplit("-", 1)[-1]
            for item in projects
            if item.startswith("charting-dev-")
        ),
        "",
    )
    branch = next(
        (
            item.removeprefix("charting-dev-").rsplit("-", 1)[0]
            for item in projects
            if item.startswith("charting-dev-")
        ),
        "worktree",
    )
    return f"charting-builder-{branch}-{suffix}" if suffix else ""


def builder_name(branch: str) -> str:
    suffix = hashlib.sha256(str(root()).encode()).hexdigest()[:8]
    return f"charting-builder-{slug(branch)}-{suffix}"


def session_record(
    branch: str, path: Path, plan: dict[str, Any], identifier: str, session_id: str
) -> dict[str, Any]:
    head = git("rev-parse", "HEAD", cwd=path)
    remote = git("rev-parse", f"origin/{branch}", cwd=path, check=False)
    criteria = acceptance_criteria(plan)
    criteria_text = "; ".join(
        f"{item['id']}: {item['text']}" for item in criteria if item["text"]
    )
    profile = str(plan.get("local_validation_profile", "pending_agent_assessment"))
    objective = (
        f"Advance {branch}: {plan['goal']}. "
        f"Acceptance criteria: {criteria_text or 'complete the durable branch plan first'}. "
        f"Required local profile: {profile}. "
        "Stop at ready_for_human_review; do not integrate, promote, deploy, "
        "or modify another worktree."
    )
    return {
        "session_id": session_id,
        "branch": branch,
        "worktree": str(path),
        "worktree_id": identifier,
        "head": head,
        "remote": remote,
        "remote_synchronized": bool(remote and remote == head),
        "dirty_paths": dirty_paths(path),
        "workstream": str(path / "ops" / "workstreams" / slug(branch)),
        "validation_tier": plan.get("validation_tier"),
        "planning_state": plan.get("planning_state", "legacy_ready"),
        "local_validation_profile": profile,
        "acceptance_criteria": criteria,
        "plan_hash": plan_hash(
            path / "ops" / "workstreams" / slug(branch) / "plan.yaml"
        ),
        "goal_objective": objective,
        "docker": docker_status(identifier, project_names(branch)),
    }


def start(expected_branch: str | None) -> None:
    branch, path = branch_and_path()
    if expected_branch and expected_branch != branch:
        raise SystemExit(
            f"assigned branch mismatch: expected {expected_branch}, found {branch}"
        )
    stream, plan = workstream(branch, path)
    if dirty_paths(path):
        raise SystemExit(
            "implementation session requires a clean bootstrap boundary; use explicit takeover for interrupted dirty work"
        )
    profile = str(plan.get("local_validation_profile", ""))
    if profile_requires_docker(profile):
        try:
            docker_ready()
        except SystemExit as exc:
            record_validation(
                stream,
                {
                    "at": datetime.now(UTC).isoformat(),
                    "command": "make agent-docker-ready",
                    "profile": profile,
                    "result": "blocked_local_runtime",
                    "reason": str(exc),
                    "sha": git("rev-parse", "HEAD", cwd=path),
                },
            )
            raise
    identifier = worktree_id(path, branch)
    with claim_lock():
        existing = read_claim(identifier)
        if existing:
            raise SystemExit(
                f"worktree already claimed by session {existing.get('session_id')}; use explicit takeover"
            )
        session_id = str(uuid.uuid4())
        atomic_json(
            claim_path(identifier),
            {
                "session_id": session_id,
                "worktree_id": identifier,
                "branch": branch,
                "worktree": str(path),
                "started_at": datetime.now(UTC).isoformat(),
                "host": socket.gethostname(),
            },
        )
    record = session_record(branch, path, plan, identifier, session_id)
    state = stream / "session.json"
    previous_state: dict[str, Any] = {}
    if state.exists():
        try:
            loaded = json.loads(state.read_text())
            if isinstance(loaded, dict):
                previous_state = loaded
        except (OSError, json.JSONDecodeError):
            previous_state = {}
    previous_ids = list(previous_state.get("previous_session_ids") or [])
    previous_active = previous_state.get("active_session_id")
    if previous_active and previous_active not in previous_ids:
        previous_ids.append(previous_active)
    ready = plan_ready(plan)
    record["workstream_files"] = [
        str(stream / name)
        for name in ("plan.yaml", "handoff.md", "validation.jsonl", "session.json")
    ]
    record["planning_required"] = not ready
    record["goal_state"] = "planning_required" if not ready else "requested"
    record["goal_request"] = make_goal_request(
        record["goal_objective"], plan, ready=ready
    )
    record["goal_request_state"] = "planning_required" if not ready else "ready"
    record["goal_budget_policy"] = plan.get(
        "goal_budget_policy", "unbounded_unless_human_authorized"
    )
    progress = (
        previous_state.get("progress")
        or plan.get("progress")
        or {
            "completed": [],
            "total": len(record["acceptance_criteria"]),
            "current_phase": "plan" if not ready else "implementation",
            "current_blocker": "complete the branch-owned plan before creating a goal"
            if not ready
            else "none",
        }
    )
    atomic_json(
        state,
        {
            "schema": 2,
            **previous_state,
            **record,
            "previous_session_ids": previous_ids,
            "active_session_id": session_id,
            "progress": progress,
        },
    )
    print(json.dumps(record, indent=2))


def session_state(stream: Path) -> dict[str, Any]:
    path = stream / "session.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def plan_ready_command(session_id: str) -> None:
    branch, path, stream, plan, identifier, _ = current()
    with claim_lock():
        verify_claim(identifier, session_id)
    if not plan_ready(plan):
        raise SystemExit(
            "workstream plan is incomplete; fill scope, owned paths, acceptance criteria, "
            "tests, and local validation profile before creating a goal"
        )
    if dirty_paths(path):
        raise SystemExit("plan-ready requires the planning checkpoint to be committed")
    head = git("rev-parse", "HEAD", cwd=path)
    remote = git("rev-parse", f"origin/{branch}", cwd=path, check=False)
    if not remote or head != remote:
        raise SystemExit("plan-ready requires local and remote branch heads to match")
    validator = run(
        "uv",
        "run",
        "--project",
        "backend",
        "python",
        "scripts/validate-workstream.py",
        str(stream),
        cwd=path,
        check=False,
    )
    if validator.returncode:
        raise SystemExit(validator.stderr.strip() or "workstream validation failed")
    docker = None
    profile = str(plan.get("local_validation_profile", ""))
    if profile_requires_docker(profile):
        docker = docker_ready()
    state = session_state(stream)
    objective = session_record(branch, path, plan, identifier, session_id)[
        "goal_objective"
    ]
    request = make_goal_request(objective, plan)
    state.update(
        {
            "schema": 2,
            "branch": branch,
            "worktree": str(path),
            "active_session_id": session_id,
            "planning_state": "ready",
            "goal_state": "requested",
            "goal_request": request,
            "goal_budget_policy": plan.get(
                "goal_budget_policy", "unbounded_unless_human_authorized"
            ),
            "goal_objective": objective,
            "plan_hash": plan_hash(stream / "plan.yaml"),
            "implementation_sha": head,
            "remote_sha": remote,
            "docker_ready": docker,
            "next_action": "create the session-local Codex goal from goal_request, then record it as active",
        }
    )
    atomic_json(stream / "session.json", state)
    print(json.dumps(request, indent=2))


def goal_state(session_id: str, state_name: str, reason: str) -> None:
    branch, path, stream, plan, identifier, _ = current()
    with claim_lock():
        verify_claim(identifier, session_id)
    if state_name not in {"active", "unavailable"}:
        raise SystemExit("goal state must be active or unavailable")
    if state_name == "unavailable" and not reason.strip():
        raise SystemExit("an unavailable goal requires a reason")
    if not plan_ready(plan):
        raise SystemExit("complete the branch-owned plan before recording goal state")
    state = session_state(stream)
    state.update(
        {
            "schema": 2,
            "branch": branch,
            "worktree": str(path),
            "active_session_id": session_id,
            "goal_state": state_name,
            "goal_unavailable_reason": reason.strip()
            if state_name == "unavailable"
            else None,
            "goal_recorded_at": datetime.now(UTC).isoformat(),
            "next_action": "continue implementation from the branch workstream",
        }
    )
    atomic_json(stream / "session.json", state)
    print(json.dumps({"goal_state": state_name, "reason": reason.strip()}, indent=2))


def progress(
    session_id: str,
    completed: str,
    phase: str,
    blocker: str,
    next_action: str,
) -> None:
    branch, path, stream, plan, identifier, _ = current()
    with claim_lock():
        verify_claim(identifier, session_id)
    if not phase.strip() or not next_action.strip():
        raise SystemExit("progress requires a phase and next action")
    criteria = acceptance_criteria(plan)
    known = {item["id"] for item in criteria}
    completed_ids = [item.strip() for item in completed.split(",") if item.strip()]
    unknown = sorted(set(completed_ids) - known)
    if unknown:
        raise SystemExit("unknown acceptance criterion(s): " + ", ".join(unknown))
    state = session_state(stream)
    state["progress"] = {
        "completed": completed_ids,
        "total": len(criteria),
        "current_phase": phase.strip(),
        "current_blocker": blocker.strip() or "none",
        "next_action": next_action.strip(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    state["last_human_progress_update"] = datetime.now(UTC).isoformat()
    atomic_json(stream / "session.json", state)
    total = len(criteria)
    print(
        json.dumps(
            {
                "completed": len(completed_ids),
                "total": total,
                "progress": state["progress"],
            },
            indent=2,
        )
    )


def current() -> tuple[str, Path, Path, dict[str, Any], str, dict[str, Any]]:
    branch, path = branch_and_path()
    stream, plan = workstream(branch, path)
    identifier = worktree_id(path, branch)
    claim = read_claim(identifier)
    if not claim:
        raise SystemExit("no active session claim; run agent-session-start first")
    return branch, path, stream, plan, identifier, claim


def status() -> None:
    branch, path, stream, plan, identifier, claim = current()
    record = session_record(branch, path, plan, identifier, str(claim["session_id"]))
    record["claim"] = claim
    state = session_state(stream)
    record["goal_state"] = state.get("goal_state", "not_started")
    record["progress"] = state.get("progress", plan.get("progress", {}))
    atomic_json(
        stream / "session.json",
        {**state, "schema": 2, **record, "active_session_id": claim["session_id"]},
    )
    print(json.dumps(record, indent=2))


def resources() -> None:
    branch, _ = branch_and_path(allow_protected=True)
    identifier = worktree_id(root(), branch)
    print(json.dumps(docker_status(identifier, project_names(branch)), indent=2))


def checkpoint(session_id: str) -> None:
    branch, path, stream, plan, identifier, _ = current()
    with claim_lock():
        claim = verify_claim(identifier, session_id)
    record = session_record(branch, path, plan, identifier, session_id)
    state = session_state(stream)
    current_plan_hash = plan_hash(stream / "plan.yaml")
    recorded_plan_hash = state.get("plan_hash")
    if recorded_plan_hash and recorded_plan_hash != current_plan_hash:
        raise SystemExit(
            "workstream plan changed since the last session boundary; run plan-ready after committing the updated plan"
        )
    if str(plan.get("schema")) == "4" and state.get("goal_state") not in {
        "active",
        "unavailable",
    }:
        raise SystemExit(
            "schema-4 checkpoint requires an active goal or an explicit goal-unavailable record"
        )
    handoff = stream / "handoff.md"
    started = claim.get("started_at", "")
    if (
        started
        and handoff.stat().st_mtime < datetime.fromisoformat(started).timestamp()
    ):
        raise SystemExit(
            "handoff is stale; update the branch-owned handoff before checkpoint"
        )
    dirty = dirty_paths(path)
    if dirty:
        handoff_text = handoff.read_text()
        missing_paths = [path for path in dirty if path not in handoff_text]
        if missing_paths:
            raise SystemExit(
                "checkpoint requires every dirty path in handoff.md: "
                + ", ".join(missing_paths)
            )
    validate_retained(identifier)
    if record["docker"].get("over_budget"):
        raise SystemExit(
            "worktree exceeds 5 GB attributable Docker threshold; clean at a safe boundary"
        )
    if record["docker"].get("unknown_components") and record["docker"].get(
        "container_count", 0
    ) + record["docker"].get("volume_count", 0):
        raise SystemExit(
            "Docker ownership accounting is incomplete for active resources: "
            + ", ".join(record["docker"]["unknown_components"])
        )
    if profile_requires_docker(str(plan.get("local_validation_profile"))):
        if not record["docker"].get("available"):
            raise SystemExit(
                "Docker-backed validation is required but the daemon is unavailable; run agent-docker-ready"
            )
    with claim_lock():
        verify_claim(identifier, session_id)
        atomic_json(
            stream / "session.json",
            {
                **state,
                "schema": 2,
                **record,
                "state": "checkpointed",
                "active_session_id": session_id,
                "progress": state.get("progress", plan.get("progress", {})),
                "last_checkpoint": datetime.now(UTC).isoformat(),
            },
        )
    print(json.dumps(record, indent=2))


def finish(session_id: str, interrupted: bool, next_action: str) -> None:
    branch, path, stream, plan, identifier, _ = current()
    with claim_lock():
        verify_claim(identifier, session_id)
    state = session_state(stream)
    if str(plan.get("schema")) == "4":
        if not plan_ready(plan):
            raise SystemExit("cannot finish before the branch-owned plan is ready")
        if state.get("goal_state") not in {"active", "unavailable"}:
            raise SystemExit(
                "cannot finish before recording the goal as active or unavailable"
            )
        if not interrupted and plan.get("status") != "ready_for_human_review":
            raise SystemExit(
                "normal finish requires workstream status ready_for_human_review; use interrupted finish for a handoff"
            )
        if not interrupted:
            head = git("rev-parse", "HEAD", cwd=path)
            if not validation_evidence_current(
                stream, head, str(plan.get("local_validation_profile"))
            ):
                raise SystemExit(
                    "normal finish requires passing validation evidence for the current HEAD"
                )
    dirty = dirty_paths(path)
    if dirty and not interrupted:
        raise SystemExit(
            "worktree is dirty; use --interrupted with --next-action to record an explicit handoff"
        )
    if interrupted and not next_action.strip():
        raise SystemExit("interrupted finish requires --next-action")
    if interrupted and dirty:
        handoff_text = (stream / "handoff.md").read_text()
        missing_paths = [path for path in dirty if path not in handoff_text]
        if missing_paths:
            raise SystemExit(
                "interrupted finish requires every dirty path in handoff.md: "
                + ", ".join(missing_paths)
            )
    retained = validate_retained(identifier)
    docker = docker_status(identifier, project_names(branch))
    if docker.get("available"):
        cleanup()
    elif not interrupted:
        raise SystemExit(
            f"Docker cleanup is blocked: {docker.get('reason', 'unknown state')}"
        )
    result = {
        "finished": True,
        "branch": branch,
        "worktree": str(path),
        "dirty_paths": dirty,
        "interrupted": interrupted,
        "next_action": next_action,
        "retained_docker_resources": retained,
        "docker_before_cleanup": docker,
    }
    atomic_json(
        stream / "session.json",
        {
            **state,
            "schema": 2,
            **result,
            "state": "interrupted" if interrupted else "finished",
            "active_session_id": None,
            "goal_state": "finished" if not interrupted else state.get("goal_state"),
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )
    with claim_lock():
        verify_claim(identifier, session_id)
        claim_path(identifier).unlink(missing_ok=True)
    print(json.dumps(result, indent=2))


def takeover(confirm: str, request: str) -> None:
    branch, path = branch_and_path()
    if not request.strip():
        raise SystemExit("takeover requires explicit human authorization in --request")
    workstream(branch, path)
    identifier = worktree_id(path, branch)
    with claim_lock():
        old = read_claim(identifier)
        if not old:
            raise SystemExit("no existing claim to take over")
        if confirm != old.get("session_id"):
            raise SystemExit("CONFIRM must exactly match the existing session ID")
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        audit = common_root() / ".ai" / "session-claims" / "takeovers.jsonl"
        with audit.open("a") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": now,
                        "old": old,
                        "new": session_id,
                        "reason": request.strip(),
                    }
                )
                + "\n"
            )
        atomic_json(
            claim_path(identifier),
            {
                **old,
                "session_id": session_id,
                "taken_over_at": now,
                "takeover_request": request.strip(),
                "displaced_session_id": old.get("session_id"),
            },
        )
    state = path / "ops" / "workstreams" / slug(branch) / "session.json"
    prior: dict[str, Any] = {}
    if state.exists():
        try:
            prior = json.loads(state.read_text())
        except (OSError, json.JSONDecodeError):
            prior = {}
    previous = list(prior.get("previous_session_ids") or [])
    if old.get("session_id") and old["session_id"] not in previous:
        previous.append(old["session_id"])
    atomic_json(
        state,
        {
            **prior,
            "schema": 2,
            "branch": branch,
            "active_session_id": session_id,
            "previous_session_ids": previous,
            "goal_state": "resumed_after_takeover",
            "takeover_history": [
                *(prior.get("takeover_history") or []),
                {
                    "displaced_session_id": old.get("session_id"),
                    "new_session_id": session_id,
                    "reason": request.strip(),
                    "at": now,
                },
            ],
            "next_action": "resume from the durable handoff and inspect displaced session state",
        },
    )
    print(
        json.dumps(
            {
                "branch": branch,
                "worktree": str(path),
                "session_id": session_id,
                "displaced_session": old.get("session_id"),
            },
            indent=2,
        )
    )


def retain_volume(
    volume: str, reason: str, next_use: str, recreate: str, review: str
) -> None:
    if not all(item.strip() for item in (volume, reason, next_use, recreate, review)):
        raise SystemExit("VOLUME, REASON, NEXT_USE, RECREATE, and REVIEW are required")
    branch, path = branch_and_path(allow_protected=True)
    identifier = worktree_id(path, branch)
    inspected = run("docker", "volume", "inspect", volume, check=False)
    if inspected.returncode:
        raise SystemExit("volume does not exist or Docker is unavailable")
    details = json.loads(inspected.stdout)[0]
    labels = details.get("Labels") or {}
    if labels.get("charting.worktree.id") != identifier:
        raise SystemExit("volume is not labelled as owned by this worktree")
    record_path = common_root() / ".ai" / "runtime" / "retained-volumes.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    records = json.loads(record_path.read_text()) if record_path.exists() else {}
    records[volume] = {
        "worktree_id": identifier,
        "branch": branch,
        "worktree": str(path),
        "reason": reason.strip(),
        "next_use": next_use.strip(),
        "recreate_impact": recreate.strip(),
        "review": review.strip(),
        "approximate_size_bytes": numeric_size(
            (details.get("UsageData") or {}).get("Size")
        ),
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    record_path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    print(json.dumps(records[volume], indent=2))


def release_volume(volume: str, confirm: str) -> None:
    """Delete one retained volume after its recorded review condition is met."""
    if not volume or confirm != volume:
        raise SystemExit("release requires VOLUME and an exact matching CONFIRM")
    branch, path = branch_and_path(allow_protected=True)
    identifier = worktree_id(path, branch)
    record_path = common_root() / ".ai" / "runtime" / "retained-volumes.json"
    records = json.loads(record_path.read_text()) if record_path.exists() else {}
    record = records.get(volume)
    if not isinstance(record, dict) or record.get("worktree_id") != identifier:
        raise SystemExit("volume has no retained record owned by this worktree")
    result = run("docker", "volume", "rm", volume, check=False)
    if result.returncode:
        raise SystemExit(
            result.stderr.strip() or "retained volume could not be removed"
        )
    records.pop(volume, None)
    if records:
        atomic_json(record_path, records)
    else:
        record_path.unlink(missing_ok=True)
    print(json.dumps({"released": volume, "worktree_id": identifier}, indent=2))


def cleanup() -> dict[str, Any]:
    branch, path = branch_and_path(allow_protected=True)
    identifier = worktree_id(path, branch)
    projects = project_names(branch)
    if shutil.which("docker") is None:
        raise SystemExit("Docker is unavailable; refusing resource cleanup")
    sessions = recorded_testcontainer_sessions(identifier)
    containers = owned_containers(identifier, projects, sessions)
    if containers is None:
        raise SystemExit("Docker cannot be inspected; refusing resource cleanup")
    for item in containers:
        run("docker", "rm", "-f", item["Id"], check=False)
    images = run(
        "docker",
        "image",
        "ls",
        "-q",
        "--filter",
        f"label=charting.worktree.id={identifier}",
        check=False,
    )
    removed_images = 0
    if images.returncode == 0:
        for image in sorted(set(images.stdout.splitlines())):
            run("docker", "image", "rm", image, check=False)
            removed_images += 1
    retained_path = common_root() / ".ai" / "runtime" / "retained-volumes.json"
    retained = json.loads(retained_path.read_text()) if retained_path.exists() else {}
    volumes = run(
        "docker",
        "volume",
        "ls",
        "-q",
        "--filter",
        f"label=charting.worktree.id={identifier}",
        check=False,
    )
    if volumes.returncode == 0:
        for volume in volumes.stdout.splitlines():
            if volume not in retained:
                run("docker", "volume", "rm", volume, check=False)
    network_ids: set[str] = set()
    for filter_value in (
        f"label=charting.worktree.id={identifier}",
        *(f"label=com.docker.compose.project={project}" for project in projects),
    ):
        networks = run(
            "docker", "network", "ls", "-q", "--filter", filter_value, check=False
        )
        if networks.returncode == 0:
            network_ids.update(networks.stdout.splitlines())
    for network in sorted(network_ids):
        inspect = run(
            "docker",
            "network",
            "inspect",
            network,
            "--format",
            "{{json .}}",
            check=False,
        )
        if inspect.returncode or not inspect.stdout:
            continue
        try:
            data = json.loads(inspect.stdout)
        except json.JSONDecodeError:
            continue
        labels = data.get("Labels") or {}
        if (
            labels.get("com.docker.compose.project") in projects
            or labels.get("charting.worktree.id") == identifier
        ):
            run("docker", "network", "rm", network, check=False)
    run("docker", "buildx", "rm", builder_name(branch), check=False)
    state_path = (
        common_root() / ".ai" / "runtime" / identifier / "testcontainers-sessions.json"
    )
    state_path.unlink(missing_ok=True)
    remaining = owned_containers(identifier, projects, sessions) or []
    remaining_volumes = run(
        "docker",
        "volume",
        "ls",
        "-q",
        "--filter",
        f"label=charting.worktree.id={identifier}",
        check=False,
    )
    remaining_volume_names = (
        remaining_volumes.stdout.splitlines()
        if remaining_volumes.returncode == 0
        else []
    )
    retained_names = {
        name for name, item in retained.items() if item.get("worktree_id") == identifier
    }
    unexplained = sorted(set(remaining_volume_names) - retained_names)
    remaining_images = run(
        "docker",
        "image",
        "ls",
        "-q",
        "--filter",
        f"label=charting.worktree.id={identifier}",
        check=False,
    )
    remaining_image_ids = (
        sorted(set(remaining_images.stdout.splitlines()))
        if remaining_images.returncode == 0
        else ["unknown"]
    )
    if remaining or unexplained or remaining_image_ids:
        raise SystemExit(
            "scoped cleanup could not account for all owned resources: "
            f"containers={len(remaining)}, volumes={unexplained}, images={remaining_image_ids}"
        )
    result = {
        "cleaned": True,
        "worktree_id": identifier,
        "projects": sorted(projects),
        "containers_removed": len(containers),
        "images_removed": removed_images,
        "images_remaining": remaining_image_ids,
        "host_wide_prune": False,
        "retained_volumes": sorted(
            [
                name
                for name in retained
                if retained[name].get("worktree_id") == identifier
            ]
        ),
        "testcontainer_sessions": sorted(sessions),
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("--branch")
    p = sub.add_parser("plan-ready")
    p.add_argument("--session-id", required=True)
    p = sub.add_parser("goal-state")
    p.add_argument("--session-id", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--reason", default="")
    p = sub.add_parser("progress")
    p.add_argument("--session-id", required=True)
    p.add_argument("--completed", default="")
    p.add_argument("--phase", required=True)
    p.add_argument("--blocker", default="none")
    p.add_argument("--next-action", required=True)
    sub.add_parser("docker-ready")
    sub.add_parser("status")
    sub.add_parser("resources")
    p = sub.add_parser("checkpoint")
    p.add_argument("--session-id", required=True)
    p = sub.add_parser("finish")
    p.add_argument("--session-id", required=True)
    p.add_argument("--interrupted", action="store_true")
    p.add_argument("--next-action", default="")
    p = sub.add_parser("takeover")
    p.add_argument("--confirm", required=True)
    p.add_argument("--request", required=True)
    p = sub.add_parser("retain-volume")
    p.add_argument("volume")
    p.add_argument("--reason", required=True)
    p.add_argument("--next-use", required=True)
    p.add_argument("--recreate", required=True)
    p.add_argument("--review", required=True)
    sub.add_parser("cleanup")
    p = sub.add_parser("release-volume")
    p.add_argument("volume")
    p.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.command == "start":
        start(args.branch)
    elif args.command == "plan-ready":
        plan_ready_command(args.session_id)
    elif args.command == "goal-state":
        goal_state(args.session_id, args.state, args.reason)
    elif args.command == "progress":
        progress(
            args.session_id, args.completed, args.phase, args.blocker, args.next_action
        )
    elif args.command == "docker-ready":
        print(json.dumps(docker_ready(), indent=2))
    elif args.command == "status":
        status()
    elif args.command == "resources":
        resources()
    elif args.command == "checkpoint":
        checkpoint(args.session_id)
    elif args.command == "finish":
        finish(args.session_id, args.interrupted, args.next_action)
    elif args.command == "takeover":
        takeover(args.confirm, args.request)
    elif args.command == "retain-volume":
        retain_volume(
            args.volume, args.reason, args.next_use, args.recreate, args.review
        )
    elif args.command == "cleanup":
        cleanup()
    elif args.command == "release-volume":
        release_volume(args.volume, args.confirm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
