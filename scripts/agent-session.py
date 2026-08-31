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
import uuid
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PREFIXES = ("feat/", "fix/", "chore/", "docs/", "test/")
TERMINAL = {"integrated", "closed", "superseded", "blocked"}
DOCKER_LIMIT_BYTES = 5_000_000_000


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


def branch_and_path() -> tuple[str, Path]:
    path = root()
    branch = git("branch", "--show-current", cwd=path)
    if not branch:
        raise SystemExit("agent sessions cannot start from detached HEAD")
    if branch in {"master", "staging"}:
        raise SystemExit(
            f"agent implementation sessions cannot run on protected branch {branch}"
        )
    if not branch.startswith(PREFIXES):
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


def parse_plan(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("'\"")
    return values


def workstream(branch: str, path: Path) -> tuple[Path, dict[str, str]]:
    stream = path / "ops" / "workstreams" / slug(branch)
    files = [stream / "plan.yaml", stream / "handoff.md", stream / "validation.jsonl"]
    missing = [str(item) for item in files if not item.exists()]
    if missing:
        raise SystemExit(
            "missing branch-owned workstream file(s): " + ", ".join(missing)
        )
    plan = parse_plan(files[0])
    if plan.get("schema") not in {"2", "3"} or plan.get("branch") != branch:
        raise SystemExit("workstream does not match a supported schema or branch")
    if not plan.get("human_intent_authorization") or plan[
        "human_intent_authorization"
    ].lower().startswith("pending"):
        raise SystemExit("workstream has no explicit human intent authorization")
    if plan.get("status") in TERMINAL:
        raise SystemExit(f"workstream status {plan.get('status')} is terminal")
    if not plan.get("goal") or "replace me" in plan["goal"].lower():
        raise SystemExit("workstream goal must be derived from the human request")
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


def numeric_size(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def owned_containers(
    identifier: str, projects: set[str]
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
    containers = owned_containers(identifier, projects) or []
    bytes_known = sum(numeric_size(item.get("SizeRw")) for item in containers)
    image_rows = docker_json("image", "ls", "--format", "{{json .}}") or []
    owned_images = [row for row in image_rows if identifier in json.dumps(row)]
    unique_image_bytes = sum(numeric_size(row.get("Size")) for row in owned_images)
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
    return {
        "available": True,
        "worktree_id": identifier,
        "projects": sorted(projects),
        "containers": [item.get("Name", "").lstrip("/") for item in containers],
        "container_count": len(containers),
        "volume_count": len(volumes),
        "known_bytes": bytes_known,
        "unique_image_bytes": unique_image_bytes,
        "threshold_bytes": DOCKER_LIMIT_BYTES,
        "over_budget": bytes_known > DOCKER_LIMIT_BYTES,
        "unattributed_shared_layers_excluded": True,
    }


def project_names(branch: str) -> set[str]:
    suffix = hashlib.sha256(str(root()).encode()).hexdigest()[:8]
    return {
        f"charting-dev-{slug(branch)}-{suffix}",
        f"charting-stack-{slug(branch)}-{suffix}",
    }


def builder_name(branch: str) -> str:
    suffix = hashlib.sha256(str(root()).encode()).hexdigest()[:8]
    return f"charting-builder-{slug(branch)}-{suffix}"


def session_record(
    branch: str, path: Path, plan: dict[str, str], identifier: str, session_id: str
) -> dict[str, Any]:
    head = git("rev-parse", "HEAD", cwd=path)
    remote = git("rev-parse", f"origin/{branch}", cwd=path, check=False)
    return {
        "session_id": session_id,
        "branch": branch,
        "worktree": str(path),
        "worktree_id": identifier,
        "head": head,
        "remote": remote,
        "remote_synchronized": bool(remote and remote == head),
        "dirty_paths": git("status", "--porcelain", cwd=path).splitlines(),
        "workstream": str(path / "ops" / "workstreams" / slug(branch)),
        "validation_tier": plan.get("validation_tier"),
        "goal_objective": f"Advance {branch}: {plan['goal']} Stop at ready_for_human_review; do not integrate, promote, deploy, or modify another worktree.",
        "docker": docker_status(identifier, project_names(branch)),
    }


def start(expected_branch: str | None) -> None:
    branch, path = branch_and_path()
    if expected_branch and expected_branch != branch:
        raise SystemExit(
            f"assigned branch mismatch: expected {expected_branch}, found {branch}"
        )
    stream, plan = workstream(branch, path)
    if git("status", "--porcelain", cwd=path):
        raise SystemExit(
            "implementation session requires a clean bootstrap boundary; use explicit takeover for interrupted dirty work"
        )
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
    record["workstream_files"] = [
        str(stream / name) for name in ("plan.yaml", "handoff.md", "validation.jsonl")
    ]
    record["goal_request"] = {
        "objective": record["goal_objective"],
        "budget_policy": plan.get(
            "goal_budget_policy", "unbounded_unless_human_authorized"
        ),
    }
    state = stream / "session.json"
    atomic_json(state, {"schema": 1, **record, "active_session_id": session_id})
    print(json.dumps(record, indent=2))


def current() -> tuple[str, Path, Path, dict[str, str], str, dict[str, Any]]:
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
    atomic_json(
        stream / "session.json",
        {"schema": 1, **record, "active_session_id": claim["session_id"]},
    )
    print(json.dumps(record, indent=2))


def resources() -> None:
    branch, _ = branch_and_path()
    identifier = worktree_id(root(), branch)
    print(json.dumps(docker_status(identifier, project_names(branch)), indent=2))


def checkpoint(session_id: str) -> None:
    branch, path, stream, plan, identifier, _ = current()
    verify_claim(identifier, session_id)
    record = session_record(branch, path, plan, identifier, session_id)
    if record["docker"].get("over_budget"):
        raise SystemExit(
            "worktree exceeds 5 GB attributable Docker threshold; clean at a safe boundary"
        )
    atomic_json(
        stream / "session.json",
        {
            "schema": 1,
            **record,
            "state": "checkpointed",
            "active_session_id": session_id,
        },
    )
    print(json.dumps(record, indent=2))


def finish(session_id: str, interrupted: bool, next_action: str) -> None:
    branch, path, stream, plan, identifier, _ = current()
    verify_claim(identifier, session_id)
    dirty = git("status", "--porcelain", cwd=path).splitlines()
    if dirty and not interrupted:
        raise SystemExit(
            "worktree is dirty; use --interrupted with --next-action to record an explicit handoff"
        )
    if interrupted and not next_action.strip():
        raise SystemExit("interrupted finish requires --next-action")
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
    }
    atomic_json(
        stream / "session.json",
        {
            "schema": 1,
            **result,
            "state": "interrupted" if interrupted else "finished",
            "active_session_id": None,
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
    old = read_claim(identifier)
    if not old:
        raise SystemExit("no existing claim to take over")
    if confirm != old.get("session_id"):
        raise SystemExit("CONFIRM must exactly match the existing session ID")
    session_id = str(uuid.uuid4())
    audit = common_root() / ".ai" / "session-claims" / "takeovers.jsonl"
    with audit.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "old": old,
                    "new": session_id,
                    "reason": "explicit human-authorized takeover command",
                }
            )
            + "\n"
        )
    atomic_json(
        claim_path(identifier),
        {
            **old,
            "session_id": session_id,
            "taken_over_at": datetime.now(UTC).isoformat(),
            "takeover_request": request.strip(),
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
    branch, path = branch_and_path()
    _, _, _, _, identifier, _ = current()
    inspected = run("docker", "volume", "inspect", volume, check=False)
    if inspected.returncode:
        raise SystemExit("volume does not exist or Docker is unavailable")
    labels = json.loads(inspected.stdout)[0].get("Labels") or {}
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
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    record_path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    print(json.dumps(records[volume], indent=2))


def cleanup() -> None:
    branch, path = branch_and_path()
    _, _, _, _, identifier, _ = current()
    projects = project_names(branch)
    if shutil.which("docker") is None:
        raise SystemExit("Docker is unavailable; refusing resource cleanup")
    containers = owned_containers(identifier, projects)
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
    networks = run("docker", "network", "ls", "-q", check=False)
    if networks.returncode == 0:
        for network in networks.stdout.splitlines():
            inspect = run(
                "docker",
                "network",
                "inspect",
                network,
                "--format",
                "{{json .}}",
                check=False,
            )
            if inspect.returncode and not inspect.stdout:
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
    print(
        json.dumps(
            {
                "cleaned": True,
                "worktree_id": identifier,
                "projects": sorted(projects),
                "containers_removed": len(containers),
                "images_removed": removed_images,
                "host_wide_prune": False,
                "retained_volumes": sorted(
                    [
                        name
                        for name in retained
                        if retained[name].get("worktree_id") == identifier
                    ]
                ),
            },
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("--branch")
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
    args = parser.parse_args()
    if args.command == "start":
        start(args.branch)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
