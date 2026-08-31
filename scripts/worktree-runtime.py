#!/usr/bin/env python3
"""Allocate deterministic, path-scoped runtime resources for one worktree.

The allocator is intentionally small and dependency-free.  Its registry lives
next to Git's common directory so every linked worktree shares one lock and no
two worktrees can receive the same ports or Compose project names.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

PORT_KEYS = (
    "DEV_POSTGRES_HOST_PORT",
    "DEV_REDIS_HOST_PORT",
    "DEV_BACKEND_PORT",
    "VITE_PORT",
    "POSTGRES_HOST_PORT",
    "REDIS_HOST_PORT",
    "BACKEND_HOST_PORT",
    "FRONTEND_HOST_PORT",
)
PORT_BASES = {
    "DEV_POSTGRES_HOST_PORT": 15432,
    "DEV_REDIS_HOST_PORT": 16379,
    "DEV_BACKEND_PORT": 18000,
    "VITE_PORT": 19000,
    "POSTGRES_HOST_PORT": 25432,
    "REDIS_HOST_PORT": 26379,
    "BACKEND_HOST_PORT": 28000,
    "FRONTEND_HOST_PORT": 28080,
}


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def root() -> Path:
    return Path(run_git("rev-parse", "--show-toplevel")).resolve()


def common_root() -> Path:
    common = Path(run_git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root() / common
    return common.resolve().parent


def slug(value: str) -> str:
    clean = "".join(c.lower() if c.isalnum() else "-" for c in value)
    clean = "-".join(part for part in clean.split("-") if part)
    return clean or "detached-head"


def worktree_id(path: Path) -> str:
    return f"{slug(run_git('branch', '--show-current') or 'detached-head')}-{hashlib.sha256(str(path).encode()).hexdigest()[:10]}"


def registry_paths() -> tuple[Path, Path]:
    directory = common_root() / ".ai" / "runtime"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "allocations.json", directory / "allocations.lock"


@contextlib.contextmanager
def locked_registry() -> Any:
    registry_path, lock_path = registry_paths()
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if registry_path.exists():
                try:
                    data = json.loads(registry_path.read_text())
                except json.JSONDecodeError as exc:
                    raise SystemExit(
                        f"runtime registry is invalid: {registry_path}: {exc}"
                    ) from exc
            else:
                data = {"version": 1, "allocations": {}}
            if not isinstance(data, dict) or not isinstance(
                data.get("allocations"), dict
            ):
                raise SystemExit(
                    f"runtime registry has an invalid shape: {registry_path}"
                )
            yield data
            registry_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except PermissionError:
            # Some managed sandboxes forbid bind() even though connect() is
            # permitted.  A refused connect is sufficient evidence that no
            # listener owns the port; the preflight command performs the
            # stronger host check outside that restricted environment.
            return sock.connect_ex(("127.0.0.1", port)) != 0
        except OSError:
            return False
    return True


def managed_ports(data: dict[str, Any], current_id: str) -> set[int]:
    used: set[int] = set()
    for allocation_id, item in data["allocations"].items():
        if allocation_id == current_id:
            continue
        # Retain compatibility with pre-isolation registry entries: every
        # numeric port in an older allocation remains reserved until its
        # worktree/process proof allows reclamation.
        for value in (item.get("ports") or {}).values():
            if isinstance(value, int):
                used.add(value)
    return used


def active_worktree_paths() -> set[Path]:
    """Return paths Git still considers linked worktrees.

    A path disappearing from the filesystem is not enough evidence on its own:
    Git can retain a registered worktree after an interrupted cleanup.  The
    common Git worktree registry is the source of truth for that distinction.
    """
    lines = run_git("worktree", "list", "--porcelain").splitlines()
    return {
        Path(line.removeprefix("worktree ")).resolve()
        for line in lines
        if line.startswith("worktree ")
    }


def running_managed_projects(projects: set[str]) -> bool | None:
    """Check exact Compose projects, returning None when Docker is unavailable."""
    if not projects or shutil.which("docker") is None:
        return None
    result = subprocess.run(
        ["docker", "ps", "--format", '{{.Label "com.docker.compose.project"}}'],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        return None
    return any(line.strip() in projects for line in result.stdout.splitlines())


def reclaim_stale_allocations(data: dict[str, Any], current_id: str) -> None:
    """Drop only allocations proven detached from Git and managed processes."""
    active_paths = active_worktree_paths()
    for allocation_id, item in list(data["allocations"].items()):
        if allocation_id == current_id:
            continue
        worktree = Path(str(item.get("worktree", ""))).resolve()
        if worktree in active_paths:
            continue
        projects = {
            value
            for value in (item.get("projects") or {}).values()
            if isinstance(value, str) and value
        }
        running = running_managed_projects(projects)
        # Failure to inspect Docker is intentionally conservative: leave the
        # record in place rather than risk reusing resources owned by a process
        # that could not be observed.
        if running is not False:
            continue
        del data["allocations"][allocation_id]


def remove_unregistered_env_files(data: dict[str, Any]) -> None:
    """Remove only generated env files with no live allocator registration."""
    runtime_dir = common_root() / ".ai" / "runtime"
    if not runtime_dir.exists():
        return
    active_ids = {
        str(item.get("id", allocation_id))
        for allocation_id, item in data["allocations"].items()
    }
    for env_file in runtime_dir.glob("*.env"):
        if env_file.stem not in active_ids:
            env_file.unlink()


def allocate(data: dict[str, Any]) -> dict[str, Any]:
    path = root()
    branch = run_git("branch", "--show-current") or "detached-head"
    identifier = worktree_id(path)
    reclaim_stale_allocations(data, identifier)
    existing = data["allocations"].get(identifier)
    if (
        existing
        and Path(existing.get("worktree", "")).resolve() == path
        and set(PORT_KEYS).issubset((existing.get("ports") or {}).keys())
    ):
        existing["branch"] = branch
        existing.setdefault(
            "builder",
            f"charting-builder-{slug(branch)}-{hashlib.sha256(str(path).encode()).hexdigest()[:8]}",
        )
        return existing
    # Upgrade an older allocation for this same worktree in place.  Its old
    # ports are excluded from the managed set by identifier, while all other
    # allocations retain every numeric reservation until proven stale.
    data["allocations"].pop(identifier, None)

    used = managed_ports(data, identifier)
    ports: dict[str, int] = {}
    for key in PORT_KEYS:
        candidate = PORT_BASES[key]
        while candidate <= 65535 and (
            candidate in used or not port_available(candidate)
        ):
            candidate += 1
        if candidate > 65535:
            raise SystemExit(f"no available port found for {key}")
        ports[key] = candidate
        used.add(candidate)

    branch_slug = slug(branch)
    suffix = hashlib.sha256(str(path).encode()).hexdigest()[:8]
    allocation = {
        "worktree": str(path),
        "branch": branch,
        "id": identifier,
        "slug": branch_slug,
        "projects": {
            "dev": f"charting-dev-{branch_slug}-{suffix}",
            "stack": f"charting-stack-{branch_slug}-{suffix}",
        },
        "builder": f"charting-builder-{branch_slug}-{suffix}",
        "ports": ports,
    }
    data["allocations"][identifier] = allocation
    return allocation


def environment(allocation: dict[str, Any]) -> dict[str, str]:
    ports = allocation["ports"]
    backend = str(ports["DEV_BACKEND_PORT"])
    vite = str(ports["VITE_PORT"])
    stack_url = f"http://127.0.0.1:{ports['FRONTEND_HOST_PORT']}"
    cors = json.dumps(
        [
            f"http://localhost:{vite}",
            f"http://127.0.0.1:{vite}",
            stack_url,
            f"http://localhost:{ports['FRONTEND_HOST_PORT']}",
        ],
        separators=(",", ":"),
    )
    return {
        "WORKTREE_ROOT": allocation["worktree"],
        "WORKTREE_ID": allocation["id"],
        "WORKTREE_BRANCH": allocation["branch"],
        "WORKTREE_SLUG": allocation["slug"],
        "DEV_COMPOSE_PROJECT": allocation["projects"]["dev"],
        "STACK_COMPOSE_PROJECT": allocation["projects"]["stack"],
        "WORKTREE_BUILDER": allocation.get(
            "builder",
            f"charting-builder-{allocation['slug']}-{hashlib.sha256(allocation['worktree'].encode()).hexdigest()[:8]}",
        ),
        **{key: str(value) for key, value in ports.items()},
        "DEV_BACKEND_PORT": backend,
        "VITE_PORT": vite,
        "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{backend}",
        "STACK_URL": stack_url,
        "APP_PORT": backend,
        "DATABASE_URL": f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{ports['DEV_POSTGRES_HOST_PORT']}/chartingdb",
        "DATABASE_URL_SYNC": f"postgresql+psycopg2://postgres:postgres@127.0.0.1:{ports['DEV_POSTGRES_HOST_PORT']}/chartingdb",
        "REDIS_URL": f"redis://127.0.0.1:{ports['DEV_REDIS_HOST_PORT']}/0",
        "CORS_ORIGINS": cors,
    }


def env_file_path() -> Path:
    return common_root() / ".ai" / "runtime" / f"{worktree_id(root())}.env"


def ensure() -> tuple[dict[str, Any], dict[str, str], Path]:
    with locked_registry() as data:
        allocation = allocate(data)
        remove_unregistered_env_files(data)
        env = environment(allocation)
        path = env_file_path()
        path.write_text(
            "".join(
                f"{key}={shlex.quote(value)}\n" for key, value in sorted(env.items())
            )
        )
        path.chmod(0o600)
        return allocation, env, path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("ensure", "env-file", "shell", "json"))
    args = parser.parse_args()
    allocation, env, path = ensure()
    if args.command == "env-file":
        print(path)
    elif args.command == "shell":
        print(
            " ".join(
                f"{key}={shlex.quote(value)}" for key, value in sorted(env.items())
            )
        )
    elif args.command == "json":
        print(
            json.dumps(
                {"allocation": allocation, "environment": env, "env_file": str(path)},
                indent=2,
            )
        )
    else:
        print(f"runtime allocation ready: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
