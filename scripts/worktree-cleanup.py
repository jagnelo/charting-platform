#!/usr/bin/env python3
"""Report, then safely remove only proven-published integration candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)


def root() -> Path:
    result = git("rev-parse", "--show-toplevel", cwd=Path.cwd())
    if result.returncode:
        raise SystemExit(result.stderr)
    return Path(result.stdout.strip()).resolve()


def common(repo: Path) -> Path:
    result = git("rev-parse", "--git-common-dir", cwd=repo)
    value = Path(result.stdout.strip())
    return (value if value.is_absolute() else repo / value).resolve().parent


def size_bytes(path: Path) -> int:
    result = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True)
    return (
        int(result.stdout.split()[0]) * 1024
        if result.returncode == 0 and result.stdout
        else 0
    )


def registered(repo: Path) -> set[Path]:
    result = git("worktree", "list", "--porcelain", cwd=repo)
    return {
        Path(line[9:]).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    }


def candidate(repo: Path, path: Path, known: set[Path]) -> dict[str, object]:
    row: dict[str, object] = {"path": str(path), "action": "retain"}
    ledger_root = common(repo) / ".ai" / "integration" / "ledger"
    ledgers = []
    if ledger_root.exists():
        for ledger in ledger_root.glob("*.json"):
            try:
                data = json.loads(ledger.read_text())
            except json.JSONDecodeError:
                continue
            if data.get("candidate") == str(path):
                ledgers.append(
                    {
                        "path": str(ledger),
                        "state": data.get("state"),
                        "updated_at": data.get("updated_at", data.get("recorded_at")),
                    }
                )
    if ledgers:
        row["lifecycle_records"] = ledgers
    else:
        row["lifecycle_records"] = []
        row["historical_state"] = "unaccounted_legacy_candidate"
    if path.resolve() not in known or not (path / ".git").exists():
        row["reason"] = "not a registered usable Git worktree"
        return row
    head = git("rev-parse", "HEAD", cwd=path)
    dirty = git("status", "--porcelain", cwd=path)
    merge = git("rev-parse", "--verify", "MERGE_HEAD", cwd=path)
    if head.returncode or dirty.returncode:
        row["reason"] = "Git state cannot be proven"
        return row
    sha = head.stdout.strip()
    row["head"] = sha
    if dirty.stdout.strip() or merge.returncode == 0:
        row["reason"] = "dirty or merge in progress"
        return row
    reachable = git("merge-base", "--is-ancestor", sha, "master", cwd=repo)
    if reachable.returncode:
        row["reason"] = "candidate HEAD is not published on master"
        return row
    if not ledgers:
        row["reason"] = (
            "legacy candidate has no lifecycle record; reconcile before removal"
        )
        return row
    row["action"] = "eligible_remove"
    row["reason"] = "clean detached candidate already reachable from master"
    return row


def report(repo: Path) -> dict[str, object]:
    integration = common(repo) / ".ai" / "integration"
    known = registered(repo)
    candidates = (
        [
            candidate(repo, path, known)
            for path in sorted(integration.iterdir())
            if path.is_dir() and path.name != "ledger"
        ]
        if integration.exists()
        else []
    )
    eligible = [item for item in candidates if item["action"] == "eligible_remove"]
    return {
        "integration_root": str(integration),
        "candidates": candidates,
        "eligible_count": len(eligible),
    }


def reconcile_legacy(repo: Path) -> dict[str, object]:
    """Give every pre-policy candidate an explicit non-destructive ledger record."""
    integration = common(repo) / ".ai" / "integration"
    known = registered(repo)
    reconciled: list[str] = []
    if not integration.exists():
        return {"reconciled": reconciled}
    ledger_root = integration / "ledger"
    ledger_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(
        item
        for item in integration.iterdir()
        if item.is_dir() and item.name != "ledger"
    ):
        row = candidate(repo, path, known)
        if row.get("historical_state") != "unaccounted_legacy_candidate":
            continue
        head = str(row.get("head", "unresolved"))
        token = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        ledger = ledger_root / f"legacy-{token}.json"
        recorded_at = datetime.now(timezone.utc).isoformat()
        ledger.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "candidate": str(path),
                    "candidate_head": head,
                    "state": "legacy_needs_reconciliation",
                    "disposition": "retain_until_named_source_or_explicit_discard_decision",
                    "reason": "predates the candidate lifecycle policy; exact manual merge resolution may be locally unique",
                    "recorded_at": recorded_at,
                    "updated_at": recorded_at,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        reconciled.append(str(path))
    return {"reconciled": reconciled, "count": len(reconciled)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("report", "reconcile", "cleanup"))
    parser.add_argument("--confirm")
    args = parser.parse_args()
    repo = root()
    data = report(repo)
    if args.command == "report":
        print(json.dumps(data, indent=2))
        return 0
    if args.command == "reconcile":
        print(json.dumps(reconcile_legacy(repo), indent=2))
        return 0
    if args.confirm != "published-integration-candidates":
        raise SystemExit("cleanup requires --confirm published-integration-candidates")
    for item in data["candidates"]:
        if item["action"] == "eligible_remove":
            result = git("worktree", "remove", item["path"], cwd=repo)
            if result.returncode:
                raise SystemExit(result.stderr)
    print(json.dumps(report(repo), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
