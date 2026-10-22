#!/usr/bin/env python3
"""Fail when changes since the TC scope checkpoint leave the approved ownership boundary."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "ops/workstreams/feat-tc2000-frontend-rework/plan.yaml"
LEDGER_PATH = ROOT / "ops/workstreams/feat-tc2000-frontend-rework/ownership-reconciliation.yaml"
FROZEN_MANIFEST_PREFIX = (
    "ops/workstreams/feat-tc2000-frontend-rework/frozen-upstream-imports/"
)
RELEASE_RECEIPT_PREFIX = (
    "ops/workstreams/feat-tc2000-frontend-rework/released-staging-receipts/"
)
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


def git(*args: str) -> str:
    return git_at(ROOT, *args)


def git_at(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def exact_repo_path(value: object, *, label: str) -> str:
    path = str(value)
    if (
        not path
        or path.startswith("/")
        or path.endswith("/")
        or "//" in path
        or any(character in path for character in "*?[]")
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(ord(character) < 32 for character in path)
    ):
        raise ValueError(f"{label} must be one exact repository file path: {path!r}")
    return path


def tree_entry(root: Path, revision: str, path: str) -> tuple[str, str] | None:
    output = git_at(root, "ls-tree", "-z", revision, "--", path)
    if not output:
        return None
    records = [record for record in output.split("\0") if record]
    if len(records) != 1:
        raise ValueError(f"snapshot path must resolve to one entry: {path}")
    header, actual_path = records[0].split("\t", 1)
    mode, object_type, blob = header.split(" ", 2)
    if actual_path != path or object_type != "blob":
        raise ValueError(f"snapshot path is not an exact regular blob: {path}")
    return mode, blob


def index_entry(root: Path, path: str) -> tuple[str, str] | None:
    output = git_at(root, "ls-files", "--stage", "-z", "--", path)
    if not output:
        return None
    records = [record for record in output.split("\0") if record]
    if len(records) != 1:
        raise ValueError(f"index path is unmerged or ambiguous: {path}")
    header, actual_path = records[0].split("\t", 1)
    mode, blob, stage = header.split(" ", 2)
    if actual_path != path or stage != "0":
        raise ValueError(f"index path is not a stage-zero exact file: {path}")
    return mode, blob


def has_import_adoption_provenance(root: Path, baseline: str, source: str) -> bool:
    try:
        git_at(root, "merge-base", "--is-ancestor", baseline, "HEAD")
    except RuntimeError:
        return False
    try:
        merge_head = git_at(root, "rev-parse", "--verify", "MERGE_HEAD")
    except RuntimeError:
        merge_head = ""
    if merge_head == source:
        return True
    try:
        git_at(root, "merge-base", "--is-ancestor", source, "HEAD")
    except RuntimeError:
        return False
    first_parent_commits = git_at(
        root, "rev-list", "--first-parent", f"{baseline}..HEAD"
    ).splitlines()
    if source in first_parent_commits:
        # A coordinator-approved staging release may be consumed by the
        # explicitly authorized fast-forward workflow. The release receipt is
        # validated separately; this proves the exact release lies on the
        # branch's adopted first-parent history after the fixed scope baseline.
        return True
    for line in git_at(
        root, "rev-list", "--merges", "--parents", f"{baseline}..HEAD"
    ).splitlines():
        fields = line.split()
        if source in fields[2:]:
            return True
    return False


def approved_frozen_snapshots(
    plan: dict[str, Any], *, root: Path
) -> dict[str, tuple[str, str, dict[str, Any]]]:
    approvals = plan.get("approved_frozen_upstream_snapshots", [])
    if not isinstance(approvals, list):
        raise ValueError("approved_frozen_upstream_snapshots must be a list")
    approved: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for entry in approvals:
        if not isinstance(entry, dict) or set(entry) != {
            "source_sha",
            "receipt",
            "receipt_sha256",
        }:
            raise ValueError("approved frozen snapshot entries must use the exact schema")
        source = str(entry.get("source_sha", ""))
        digest = str(entry.get("receipt_sha256", ""))
        receipt = exact_repo_path(entry.get("receipt"), label="release receipt")
        if not HEX40.fullmatch(source) or not HEX64.fullmatch(digest):
            raise ValueError("approved frozen snapshot SHA or receipt digest is malformed")
        if source in approved:
            raise ValueError(f"approved frozen snapshot is duplicated: {source}")
        if (
            not receipt.startswith(RELEASE_RECEIPT_PREFIX)
            or not receipt.endswith(".json")
            or Path(receipt).stem != source
        ):
            raise ValueError(f"approved release receipt path is not source-pinned: {receipt}")
        receipt_path = root / receipt
        try:
            receipt_path.resolve(strict=False).relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"release receipt escapes the repository: {receipt}") from exc
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError(f"approved release receipt is missing: {receipt}")
        payload_bytes = receipt_path.read_bytes()
        if hashlib.sha256(payload_bytes).hexdigest() != digest:
            raise ValueError(f"approved release receipt digest drifted: {receipt}")
        try:
            payload = json.loads(payload_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"approved release receipt is not valid JSON: {receipt}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"approved release receipt is not an object: {receipt}")
        if payload.get("state") != "green" or payload.get("staging_sha") != source:
            raise ValueError(f"approved release receipt is not green for {source}")
        starting = str(payload.get("starting_staging_sha", ""))
        if not HEX40.fullmatch(starting) or starting == source:
            raise ValueError(f"approved release receipt has invalid staging lineage: {receipt}")
        git_at(root, "cat-file", "-e", f"{source}^{{commit}}")
        try:
            git_at(root, "merge-base", "--is-ancestor", starting, source)
        except RuntimeError as exc:
            raise ValueError(
                f"approved release source does not descend from recorded staging: {source}"
            ) from exc
        parents = git_at(root, "rev-list", "--parents", "-n", "1", source).split()
        if len(parents) < 3:
            raise ValueError(f"approved staging release is not a merge commit: {source}")
        receipt_sources = payload.get("sources")
        if not isinstance(receipt_sources, list) or not receipt_sources:
            raise ValueError(f"approved release receipt has no source records: {receipt}")
        for receipt_source in receipt_sources:
            if (
                not isinstance(receipt_source, dict)
                or not isinstance(receipt_source.get("branch"), str)
                or not receipt_source["branch"]
                or not HEX40.fullmatch(str(receipt_source.get("sha", "")))
            ):
                raise ValueError(f"approved release source record is malformed: {receipt}")
            imported_sha = str(receipt_source["sha"])
            try:
                git_at(root, "merge-base", "--is-ancestor", imported_sha, source)
            except RuntimeError as exc:
                raise ValueError(
                    f"receipt source is not in released staging history: {imported_sha}"
                ) from exc
            try:
                git_at(root, "merge-base", "--is-ancestor", imported_sha, starting)
            except RuntimeError:
                pass
            else:
                raise ValueError(
                    f"receipt source was already in starting staging: {imported_sha}"
                )
        approved[source] = (receipt, digest, payload)
    return approved


def validate_frozen_imports(
    plan: dict[str, Any], *, root: Path = ROOT
) -> dict[str, str]:
    """Validate immutable imported blobs without changing ordinary ownership."""

    baseline = str(plan.get("scope_guard_baseline_sha", "")).strip()
    if not HEX40.fullmatch(baseline):
        raise ValueError("scope_guard_baseline_sha must be a full lowercase commit SHA")
    references = plan.get("frozen_upstream_import_manifests", [])
    if not isinstance(references, list):
        raise ValueError("frozen_upstream_import_manifests must be a list")
    frozen: dict[str, str] = {}
    seen_manifests: set[str] = set()
    approved = approved_frozen_snapshots(plan, root=root)
    for raw_reference in references:
        reference = exact_repo_path(raw_reference, label="frozen manifest reference")
        if not reference.startswith(FROZEN_MANIFEST_PREFIX) or not reference.endswith(
            ".yaml"
        ):
            raise ValueError(
                "frozen manifests must be exact YAML files in the TC workstream import directory"
            )
        if reference in seen_manifests:
            raise ValueError(f"duplicate frozen manifest reference: {reference}")
        seen_manifests.add(reference)
        manifest_path = root / reference
        try:
            manifest_path.resolve(strict=False).relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"frozen manifest escapes the repository: {reference}") from exc
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError(f"frozen manifest is missing or not a regular file: {reference}")
        manifest = yaml.safe_load(manifest_path.read_text())
        if not isinstance(manifest, dict):
            raise ValueError(f"frozen manifest is not a YAML mapping: {reference}")
        expected_keys = {
            "schema_version",
            "source_sha",
            "release",
            "limitations",
            "paths",
        }
        if set(manifest) != expected_keys or manifest.get("schema_version") != 1:
            raise ValueError(f"frozen manifest has an unsupported or malformed schema: {reference}")
        source = str(manifest.get("source_sha", ""))
        if not HEX40.fullmatch(source):
            raise ValueError(f"frozen manifest source must be a full lowercase SHA: {reference}")
        if Path(reference).stem != source:
            raise ValueError(f"frozen manifest filename must equal its source SHA: {reference}")
        if source not in approved:
            raise ValueError(f"frozen source is not an approved staging snapshot: {source}")
        approved_receipt, approved_digest, receipt_payload = approved[source]
        release = manifest.get("release")
        release_keys = {
            "state",
            "run_id",
            "approved_by",
            "approval_scope",
            "receipt",
            "receipt_sha256",
        }
        if not isinstance(release, dict) or set(release) != release_keys:
            raise ValueError(f"frozen manifest release provenance is malformed: {reference}")
        if (
            release.get("state") != "green"
            or release.get("approved_by") != "staging-coordinator"
            or release.get("approval_scope") != "frozen_upstream_import_only"
            or not isinstance(release.get("run_id"), int)
            or isinstance(release.get("run_id"), bool)
            or release["run_id"] <= 0
            or release.get("receipt") != approved_receipt
            or release.get("receipt_sha256") != approved_digest
        ):
            raise ValueError(
                f"frozen manifest lacks approved green-release provenance: {reference}"
            )
        expected_run = (
            "https://github.com/jagnelo/charting-platform/actions/runs/"
            f"{release['run_id']}"
        )
        if receipt_payload.get("github_run") != expected_run:
            raise ValueError(f"release receipt run does not match manifest: {reference}")
        if not isinstance(manifest.get("limitations"), str) or not manifest[
            "limitations"
        ].strip():
            raise ValueError(f"frozen manifest must state its limitations: {reference}")
        if not has_import_adoption_provenance(root, baseline, source):
            raise ValueError(
                f"frozen source is not an approved fast-forward or non-first-parent import after {baseline}: {source}"
            )
        entries = manifest.get("paths")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"frozen manifest must list explicit paths: {reference}")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"frozen manifest path entries must be mappings: {reference}")
            state = entry.get("state")
            required_keys = {"path", "state", "mode", "blob"}
            if state == "deleted":
                required_keys = {"path", "state"}
            if set(entry) != required_keys or state not in {"present", "deleted"}:
                raise ValueError(f"malformed frozen path entry in {reference}")
            path = exact_repo_path(entry.get("path"), label="frozen import path")
            if path in frozen:
                raise ValueError(f"frozen import path appears more than once: {path}")
            if authorized(path, plan)[0]:
                raise ValueError(
                    f"frozen import path overlaps ordinary TC/shared write authority: {path}"
                )
            snapshot_entry = tree_entry(root, source, path)
            staged_entry = index_entry(root, path)
            target = root / path
            try:
                target.resolve(strict=False).relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(f"frozen import escapes the repository: {path}") from exc
            if state == "deleted":
                if snapshot_entry is not None or staged_entry is not None:
                    raise ValueError(f"frozen deletion is present in snapshot or index: {path}")
                if target.exists() or target.is_symlink():
                    raise ValueError(f"frozen deletion is present in the worktree: {path}")
            else:
                mode = str(entry.get("mode", ""))
                blob = str(entry.get("blob", ""))
                if mode not in {"100644", "100755"} or not HEX40.fullmatch(blob):
                    raise ValueError(f"frozen import supports only pinned regular files: {path}")
                if snapshot_entry != (mode, blob):
                    raise ValueError(f"frozen manifest does not match its source snapshot: {path}")
                if staged_entry != (mode, blob):
                    raise ValueError(f"frozen import index bytes or mode drifted: {path}")
                if not target.is_file() or target.is_symlink():
                    raise ValueError(
                        f"frozen import is missing or not a regular worktree file: {path}"
                    )
                worktree_blob = git_at(root, "hash-object", "--no-filters", "--", path)
                worktree_mode = "100755" if target.stat().st_mode & 0o111 else "100644"
                if (worktree_mode, worktree_blob) != (mode, blob):
                    raise ValueError(f"frozen import worktree bytes or mode drifted: {path}")
            frozen[path] = f"immutable import from approved green staging {source}"
    return frozen


def validate_provider_contract_adaptations(
    plan: dict[str, Any], *, frozen: dict[str, str], root: Path = ROOT
) -> dict[str, str]:
    """Admit only coordinator-pinned additive TC adaptations of Provider files.

    These exact files stay excluded from ordinary TC ownership and are omitted
    from immutable-import manifests. The record binds each adaptation to the
    accepted source blob; the staged index and worktree must agree so review
    never mistakes an unstaged variant for the recorded adaptation.
    """

    entries = plan.get("approved_provider_contract_adaptations", [])
    if not isinstance(entries, list):
        raise ValueError("approved_provider_contract_adaptations must be a list")
    approved = approved_frozen_snapshots(plan, root=root)
    baseline = str(plan.get("scope_guard_baseline_sha", "")).strip()
    adaptations: dict[str, str] = {}
    expected_keys = {"path", "source_sha", "accepted_blob", "delta", "rationale"}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            raise ValueError("Provider contract adaptation entries must use the exact schema")
        path = exact_repo_path(entry.get("path"), label="Provider adaptation path")
        source = str(entry.get("source_sha", ""))
        accepted_blob = str(entry.get("accepted_blob", ""))
        delta = str(entry.get("delta", "")).strip()
        rationale = str(entry.get("rationale", "")).strip()
        if path in adaptations:
            raise ValueError(f"Provider adaptation path appears more than once: {path}")
        if path in frozen:
            raise ValueError(f"adapted Provider path also appears in immutable imports: {path}")
        if authorized(path, plan)[0]:
            raise ValueError(f"Provider adaptation overlaps ordinary TC write authority: {path}")
        if source not in approved or not HEX40.fullmatch(accepted_blob):
            raise ValueError(f"Provider adaptation lacks an approved pinned source: {path}")
        if not delta or not rationale:
            raise ValueError(f"Provider adaptation must state its exact delta and rationale: {path}")
        if not has_import_adoption_provenance(root, baseline, source):
            raise ValueError(f"Provider adaptation source is not merged from approved staging: {path}")
        source_entry = tree_entry(root, source, path)
        if source_entry is None or source_entry[1] != accepted_blob:
            raise ValueError(f"Provider adaptation accepted blob does not match source: {path}")
        staged_entry = index_entry(root, path)
        target = root / path
        if (
            staged_entry is None
            or not target.is_file()
            or target.is_symlink()
        ):
            raise ValueError(f"Provider adaptation must remain a regular staged file: {path}")
        worktree_blob = git_at(root, "hash-object", "--no-filters", "--", path)
        worktree_mode = "100755" if target.stat().st_mode & 0o111 else "100644"
        if staged_entry != (worktree_mode, worktree_blob):
            raise ValueError(f"Provider adaptation index/worktree drifted: {path}")
        adaptations[path] = f"approved TC contract adaptation from {source}: {delta}"
    return adaptations


def matches(path: str, pattern: str) -> bool:
    normalized = pattern.rstrip("/")
    if pattern.endswith("/"):
        return path == normalized or path.startswith(normalized + "/")
    return fnmatch.fnmatchcase(path, pattern)


def authorized(path: str, plan: dict[str, Any]) -> tuple[bool, str]:
    if any(matches(path, str(item)) for item in plan.get("excluded_paths", [])):
        return False, "excluded upstream or adjacent ownership"
    exceptions = {
        str(item.get("path")): str(item.get("reason", "shared path exception"))
        for item in plan.get("shared_path_exceptions", [])
        if isinstance(item, dict)
    }
    if path in exceptions:
        return True, f"documented shared-path exception: {exceptions[path]}"
    if any(matches(path, str(item)) for item in plan.get("owned_paths", [])):
        return True, "TC-owned path"
    return False, "not in the TC owned_paths allowlist or shared-path exceptions"


def changed_paths(baseline: str) -> set[str]:
    values: set[str] = set()
    for output in (
        git("diff", "--name-only", baseline, "--"),
        git("diff", "--cached", "--name-only", "--"),
        git("ls-files", "--others", "--exclude-standard"),
    ):
        values.update(line for line in output.splitlines() if line)
    return values


def validate_ledger() -> None:
    ledger = yaml.safe_load(LEDGER_PATH.read_text())
    if not isinstance(ledger, dict):
        raise ValueError(f"{LEDGER_PATH} is not a YAML mapping")
    intersections = ledger
    valid_dispositions = {
        "tc_owned",
        "upstream_duplicate",
        "upstream_transfer_required",
        "shared_reconciliation",
    }
    for owner, expected_count in (
        ("market_data_provider_platform", 78),
        ("etf_holdings_constituents", 35),
    ):
        group = intersections.get(owner)
        if not isinstance(group, dict) or not isinstance(group.get("paths"), list):
            raise ValueError(f"ownership ledger is missing {owner} path list")
        entries = group["paths"]
        if len(entries) != expected_count or group.get("measured_count") != expected_count:
            raise ValueError(
                f"{owner} overlap count changed: expected {expected_count}, got {len(entries)}"
            )
        names: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{owner} paths must be mappings with disposition")
            path = str(entry.get("path", ""))
            if not path or path in names:
                raise ValueError(f"{owner} path missing or duplicated: {path!r}")
            names.add(path)
            if entry.get("disposition") not in valid_dispositions:
                raise ValueError(f"invalid {owner} disposition for {path}")
    if ledger.get("snapshot", {}).get("strategy_lab_overlap_count") != 0:
        raise ValueError("the ignored Strategy Lab branch must remain a zero-overlap record")


def self_test() -> int:
    plan = {
        "owned_paths": ["frontend/src/components/workstation/", "docs/tc2000-roadmap.md"],
        "excluded_paths": ["frontend/src/components/etf/", "docs/project-todos.md"],
        "shared_path_exceptions": [
            {"path": "frontend/src/types/index.ts", "reason": "consumer types only"}
        ],
    }
    checks = {
        "TC owned directory": authorized(
            "frontend/src/components/workstation/MarketMapTool.vue", plan
        )[0],
        "TC owned exact file": authorized("docs/tc2000-roadmap.md", plan)[0],
        "documented shared seam": authorized("frontend/src/types/index.ts", plan)[0],
        "ETF exclusion overrides broad ownership": not authorized(
            "frontend/src/components/etf/ETFHoldingsPanel.vue", plan
        )[0],
        "project todos remains outside scope": not authorized(
            "docs/project-todos.md", plan
        )[0],
        "unknown path fails closed": not authorized("backend/app/providers/new.py", plan)[0],
    }
    with tempfile.TemporaryDirectory(prefix="tc-scope-frozen-") as directory:
        root = Path(directory)

        def fixture_git(*args: str) -> str:
            return git_at(root, *args)

        def deep_copy(value: Any) -> Any:
            return yaml.safe_load(yaml.safe_dump(value))

        def write_yaml(reference: str, value: dict[str, Any]) -> None:
            path = root / reference
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(value, sort_keys=False))

        def write_receipt(reference: str, value: dict[str, Any]) -> str:
            path = root / reference
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = (json.dumps(value, indent=2) + "\n").encode()
            path.write_bytes(payload)
            return hashlib.sha256(payload).hexdigest()

        def validation_error(
            candidate: dict[str, Any], candidate_plan: dict[str, Any] | None = None
        ) -> str:
            active_plan = candidate_plan or fixture_plan
            write_yaml(active_plan["frozen_upstream_import_manifests"][0], candidate)
            try:
                validate_frozen_imports(active_plan, root=root)
            except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
                return str(exc)
            return ""

        fixture_git("init", "-b", "main")
        fixture_git("config", "user.name", "TC scope self-test")
        fixture_git("config", "user.email", "tc-scope@example.invalid")
        (root / "gone.txt").write_text("remove me\n")
        fixture_git("add", "gone.txt")
        fixture_git("commit", "-m", "baseline")
        baseline = fixture_git("rev-parse", "HEAD")
        fixture_git("checkout", "-b", "released-change")
        (root / "foreign.txt").write_text("released bytes\n")
        (root / "gone.txt").unlink()
        fixture_git("add", "--all")
        fixture_git("commit", "-m", "released change")
        imported_change = fixture_git("rev-parse", "HEAD")
        fixture_git("checkout", "-b", "released-staging", baseline)
        fixture_git("merge", "--no-ff", "-m", "green staging release", imported_change)
        source = fixture_git("rev-parse", "HEAD")
        foreign_blob = fixture_git("rev-parse", f"{source}:foreign.txt")
        reference = FROZEN_MANIFEST_PREFIX + source + ".yaml"
        receipt_reference = RELEASE_RECEIPT_PREFIX + source + ".json"
        receipt_payload: dict[str, Any] = {
            "state": "green",
            "created_at": "2026-10-20T00:00:00+00:00",
            "starting_staging_sha": baseline,
            "staging_sha": source,
            "sources": [{"branch": "released-change", "sha": imported_change}],
            "github_run": "https://github.com/jagnelo/charting-platform/actions/runs/1",
        }
        receipt_digest = write_receipt(receipt_reference, receipt_payload)
        fixture_plan = {
            "scope_guard_baseline_sha": baseline,
            "owned_paths": [FROZEN_MANIFEST_PREFIX],
            "excluded_paths": ["foreign.txt", "gone.txt"],
            "shared_path_exceptions": [],
            "frozen_upstream_import_manifests": [reference],
            "approved_frozen_upstream_snapshots": [
                {
                    "source_sha": source,
                    "receipt": receipt_reference,
                    "receipt_sha256": receipt_digest,
                }
            ],
        }
        valid_manifest: dict[str, Any] = {
            "schema_version": 1,
            "source_sha": source,
            "release": {
                "state": "green",
                "run_id": 1,
                "approved_by": "staging-coordinator",
                "approval_scope": "frozen_upstream_import_only",
                "receipt": receipt_reference,
                "receipt_sha256": receipt_digest,
            },
            "limitations": "Synthetic immutable-import fixture only.",
            "paths": [
                {
                    "path": "foreign.txt",
                    "state": "present",
                    "mode": "100644",
                    "blob": foreign_blob,
                },
                {"path": "gone.txt", "state": "deleted"},
            ],
        }
        write_yaml(reference, valid_manifest)
        fixture_git("checkout", "-b", "fast-forward-import", baseline)
        fixture_git("merge", "--ff-only", source)
        checks["approved fast-forward release accepts exact imported blobs"] = set(
            validate_frozen_imports(fixture_plan, root=root)
        ) == {"foreign.txt", "gone.txt"}
        fixture_git("checkout", "main")
        fixture_git("merge", "--no-ff", "-m", "import released", source)
        frozen = validate_frozen_imports(fixture_plan, root=root)
        checks["approved merged snapshot accepts exact present and deleted paths"] = (
            set(frozen) == {"foreign.txt", "gone.txt"}
        )
        checks["ordinary authorization still rejects frozen upstream paths"] = not authorized(
            "foreign.txt", fixture_plan
        )[0]
        checks["unknown path is not admitted by a frozen manifest"] = (
            "unknown.txt" not in frozen
            and not authorized("unknown.txt", fixture_plan)[0]
        )

        adapted_manifest = deep_copy(valid_manifest)
        adapted_manifest["paths"] = [
            entry for entry in adapted_manifest["paths"] if entry["path"] != "foreign.txt"
        ]
        write_yaml(reference, adapted_manifest)
        adaptation = {
            "path": "foreign.txt",
            "source_sha": source,
            "accepted_blob": foreign_blob,
            "delta": "add a TC-owned typed contract field without changing Provider governance",
            "rationale": "synthetic exact-path adaptation proof",
        }
        adaptation_plan = deep_copy(fixture_plan)
        adaptation_plan["approved_provider_contract_adaptations"] = [adaptation]
        adapted_frozen = validate_frozen_imports(adaptation_plan, root=root)
        adapted_paths = validate_provider_contract_adaptations(
            adaptation_plan, frozen=adapted_frozen, root=root
        )
        checks["exact approved Provider adaptation accepts pinned source blob"] = (
            set(adapted_paths) == {"foreign.txt"} and not authorized("foreign.txt", adaptation_plan)[0]
        )

        wrong_adaptation = deep_copy(adaptation_plan)
        wrong_adaptation["approved_provider_contract_adaptations"][0]["accepted_blob"] = "b" * 40
        try:
            validate_provider_contract_adaptations(
                wrong_adaptation, frozen=adapted_frozen, root=root
            )
        except (OSError, RuntimeError, ValueError):
            checks["adaptation with wrong accepted blob fails closed"] = True
        else:
            checks["adaptation with wrong accepted blob fails closed"] = False

        broad_adaptation = deep_copy(adaptation_plan)
        broad_adaptation["approved_provider_contract_adaptations"][0]["path"] = "foreign*.txt"
        try:
            validate_provider_contract_adaptations(
                broad_adaptation, frozen=adapted_frozen, root=root
            )
        except (OSError, RuntimeError, ValueError):
            checks["broad Provider adaptation path fails closed"] = True
        else:
            checks["broad Provider adaptation path fails closed"] = False

        (root / "foreign.txt").write_text("worktree-only adaptation drift\n")
        try:
            validate_provider_contract_adaptations(
                adaptation_plan, frozen=adapted_frozen, root=root
            )
        except (OSError, RuntimeError, ValueError) as exc:
            checks["Provider adaptation worktree drift fails closed"] = "drifted" in str(exc)
        else:
            checks["Provider adaptation worktree drift fails closed"] = False
        fixture_git("restore", "--worktree", "foreign.txt")

        overlap_plan = deep_copy(adaptation_plan)
        overlap_plan["approved_provider_contract_adaptations"][0]["path"] = "gone.txt"
        try:
            validate_provider_contract_adaptations(
                overlap_plan, frozen=adapted_frozen, root=root
            )
        except (OSError, RuntimeError, ValueError) as exc:
            checks["adaptation cannot overlap immutable import manifest"] = "also appears" in str(exc)
        else:
            checks["adaptation cannot overlap immutable import manifest"] = False

        (root / "foreign.txt").write_text("index drift\n")
        fixture_git("add", "foreign.txt")
        (root / "foreign.txt").write_text("released bytes\n")
        checks["staged index drift fails closed"] = bool(validation_error(valid_manifest))
        fixture_git("restore", "--staged", "--worktree", "foreign.txt")

        (root / "foreign.txt").write_text("worktree drift\n")
        checks["unstaged worktree drift fails closed"] = bool(validation_error(valid_manifest))
        fixture_git("restore", "--worktree", "foreign.txt")

        (root / "foreign.txt").unlink()
        checks["imported addition missing from worktree fails closed"] = bool(
            validation_error(valid_manifest)
        )
        fixture_git("restore", "--worktree", "foreign.txt")

        (root / "foreign.txt").unlink()
        fixture_git("add", "--update", "foreign.txt")
        checks["imported addition deleted from index fails closed"] = bool(
            validation_error(valid_manifest)
        )
        fixture_git("restore", "--staged", "--worktree", "foreign.txt")

        (root / "gone.txt").write_text("undeleted\n")
        checks["deleted-path worktree drift fails closed"] = bool(
            validation_error(valid_manifest)
        )
        (root / "gone.txt").unlink()

        fixture_git("update-index", "--chmod=+x", "foreign.txt")
        checks["staged mode drift fails closed"] = bool(validation_error(valid_manifest))
        fixture_git("restore", "--staged", "foreign.txt")

        (root / "foreign.txt").chmod(0o755)
        checks["worktree mode drift fails closed"] = bool(validation_error(valid_manifest))
        (root / "foreign.txt").chmod(0o644)

        (root / "same-bytes.txt").write_text("released bytes\n")
        (root / "foreign.txt").unlink()
        (root / "foreign.txt").symlink_to("same-bytes.txt")
        checks["worktree symlink substitution fails closed"] = bool(
            validation_error(valid_manifest)
        )
        (root / "foreign.txt").unlink()
        (root / "foreign.txt").write_text("released bytes\n")
        (root / "same-bytes.txt").unlink()

        broad_manifest = deep_copy(valid_manifest)
        broad_manifest["paths"][0]["path"] = "foreign*.txt"
        checks["wildcard manifest fails closed"] = bool(validation_error(broad_manifest))

        traversal_manifest = deep_copy(valid_manifest)
        traversal_manifest["paths"][0]["path"] = "../foreign.txt"
        checks["traversal manifest path fails closed"] = bool(
            validation_error(traversal_manifest)
        )

        missing_approval = deep_copy(valid_manifest)
        del missing_approval["release"]["approval_scope"]
        checks["missing approval provenance fails closed"] = bool(
            validation_error(missing_approval)
        )

        tampered_receipt = deep_copy(receipt_payload)
        tampered_receipt["created_at"] = "2026-10-20T00:00:09+00:00"
        write_receipt(receipt_reference, tampered_receipt)
        checks["canonical receipt byte drift fails closed"] = (
            "receipt digest drifted" in validation_error(valid_manifest)
        )
        write_receipt(receipt_reference, receipt_payload)

        wrong_blob = deep_copy(valid_manifest)
        wrong_blob["paths"][0]["blob"] = "b" * 40
        checks["snapshot blob mismatch fails closed"] = bool(validation_error(wrong_blob))

        missing_reference_plan = dict(fixture_plan)
        missing_reference_plan["frozen_upstream_import_manifests"] = [
            FROZEN_MANIFEST_PREFIX + "missing.yaml"
        ]
        try:
            validate_frozen_imports(missing_reference_plan, root=root)
        except (OSError, RuntimeError, ValueError, yaml.YAMLError):
            checks["unknown manifest reference fails closed"] = True
        else:
            checks["unknown manifest reference fails closed"] = False

        for field, value, expected in (
            ("state", "red", "not green"),
            ("staging_sha", baseline, "not green"),
            (
                "github_run",
                "https://github.com/jagnelo/charting-platform/actions/runs/2",
                "run does not match",
            ),
        ):
            bad_receipt = deep_copy(receipt_payload)
            bad_receipt[field] = value
            bad_digest = write_receipt(receipt_reference, bad_receipt)
            bad_plan = deep_copy(fixture_plan)
            bad_plan["approved_frozen_upstream_snapshots"][0][
                "receipt_sha256"
            ] = bad_digest
            bad_manifest = deep_copy(valid_manifest)
            bad_manifest["release"]["receipt_sha256"] = bad_digest
            error = validation_error(bad_manifest, bad_plan)
            checks[f"wrong receipt {field} fails its semantic check"] = expected in error
        write_receipt(receipt_reference, receipt_payload)

        committed_import_head = fixture_git("rev-parse", "HEAD")
        fixture_git("checkout", "-b", "rogue-change")
        (root / "rogue.txt").write_text("rogue bytes\n")
        fixture_git("add", "rogue.txt")
        fixture_git("commit", "-m", "rogue change")
        rogue_change = fixture_git("rev-parse", "HEAD")
        fixture_git("checkout", "-b", "rogue-staging", committed_import_head)
        fixture_git("merge", "--no-ff", "-m", "self-asserted release", rogue_change)
        rogue_source = fixture_git("rev-parse", "HEAD")
        fixture_git("checkout", "main")
        fixture_git("merge", "--no-ff", "-m", "merge unapproved source", rogue_source)
        rogue_reference = FROZEN_MANIFEST_PREFIX + rogue_source + ".yaml"
        rogue_receipt_reference = RELEASE_RECEIPT_PREFIX + rogue_source + ".json"
        rogue_receipt = {
            "state": "green",
            "created_at": "2026-10-20T00:00:01+00:00",
            "starting_staging_sha": committed_import_head,
            "staging_sha": rogue_source,
            "sources": [{"branch": "rogue-change", "sha": rogue_change}],
            "github_run": "https://github.com/jagnelo/charting-platform/actions/runs/2",
        }
        rogue_digest = write_receipt(rogue_receipt_reference, rogue_receipt)
        rogue_manifest = {
            "schema_version": 1,
            "source_sha": rogue_source,
            "release": {
                "state": "green",
                "run_id": 2,
                "approved_by": "staging-coordinator",
                "approval_scope": "frozen_upstream_import_only",
                "receipt": rogue_receipt_reference,
                "receipt_sha256": rogue_digest,
            },
            "limitations": "Synthetic unapproved merged fixture.",
            "paths": [
                {
                    "path": "rogue.txt",
                    "state": "present",
                    "mode": "100644",
                    "blob": fixture_git("rev-parse", f"{rogue_source}:rogue.txt"),
                }
            ],
        }
        rogue_plan = deep_copy(fixture_plan)
        rogue_plan["frozen_upstream_import_manifests"] = [rogue_reference]
        rogue_plan["excluded_paths"].append("rogue.txt")
        checks["unapproved but merged foreign source fails closed"] = (
            "not an approved staging snapshot"
            in validation_error(rogue_manifest, rogue_plan)
        )

        tree = fixture_git("rev-parse", f"{source}^{{tree}}")
        unmerged_change = fixture_git(
            "commit-tree", tree, "-p", source, "-m", "unmerged release change"
        )
        unmerged_source = fixture_git(
            "commit-tree",
            tree,
            "-p",
            source,
            "-p",
            unmerged_change,
            "-m",
            "approved but unmerged staging",
        )
        unmerged_reference = FROZEN_MANIFEST_PREFIX + unmerged_source + ".yaml"
        unmerged_receipt_reference = RELEASE_RECEIPT_PREFIX + unmerged_source + ".json"
        unmerged_receipt = {
            "state": "green",
            "created_at": "2026-10-20T00:00:02+00:00",
            "starting_staging_sha": source,
            "staging_sha": unmerged_source,
            "sources": [{"branch": "unmerged-change", "sha": unmerged_change}],
            "github_run": "https://github.com/jagnelo/charting-platform/actions/runs/3",
        }
        unmerged_digest = write_receipt(unmerged_receipt_reference, unmerged_receipt)
        unmerged_manifest = deep_copy(valid_manifest)
        unmerged_manifest["source_sha"] = unmerged_source
        unmerged_manifest["release"].update(
            {
                "run_id": 3,
                "receipt": unmerged_receipt_reference,
                "receipt_sha256": unmerged_digest,
            }
        )
        unmerged_plan = deep_copy(fixture_plan)
        unmerged_plan["frozen_upstream_import_manifests"] = [unmerged_reference]
        unmerged_plan["approved_frozen_upstream_snapshots"] = [
            {
                "source_sha": unmerged_source,
                "receipt": unmerged_receipt_reference,
                "receipt_sha256": unmerged_digest,
            }
        ]
        checks["consistent approved but unmerged snapshot fails ancestry check"] = (
            "not an approved fast-forward or non-first-parent import"
            in validation_error(unmerged_manifest, unmerged_plan)
        )

        final_head = fixture_git("rev-parse", "HEAD")
        fixture_git("reset", "--hard", baseline)
        fixture_git("merge", "--no-ff", "--no-commit", source)
        write_yaml(reference, valid_manifest)
        checks["active MERGE_HEAD accepts the approved exact snapshot"] = set(
            validate_frozen_imports(fixture_plan, root=root)
        ) == {"foreign.txt", "gone.txt"}
        fixture_git("merge", "--abort")
        fixture_git("reset", "--hard", final_head)
        write_yaml(reference, valid_manifest)

    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 1 if failed else 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    try:
        plan = yaml.safe_load(PLAN_PATH.read_text())
        if not isinstance(plan, dict):
            raise ValueError(f"{PLAN_PATH} is not a YAML mapping")
        if git("rev-parse", "--abbrev-ref", "HEAD") != "feat/tc2000-frontend-rework":
            raise ValueError("scope validation must run inside feat/tc2000-frontend-rework")
        baseline = str(plan.get("scope_guard_baseline_sha", "")).strip()
        if not baseline:
            raise ValueError("plan.yaml must declare scope_guard_baseline_sha")
        git("cat-file", "-e", f"{baseline}^{{commit}}")
        validate_ledger()
        frozen_imports = validate_frozen_imports(plan)
        contract_adaptations = validate_provider_contract_adaptations(
            plan, frozen=frozen_imports
        )
        paths = sorted(changed_paths(baseline))
        rejected: list[tuple[str, str]] = []
        for path in paths:
            allowed, reason = authorized(path, plan)
            if not allowed and path in frozen_imports:
                allowed, reason = True, frozen_imports[path]
            if not allowed and path in contract_adaptations:
                allowed, reason = True, contract_adaptations[path]
            if not allowed:
                rejected.append((path, reason))
        if rejected:
            print("TC scope guard rejected changed paths:", file=sys.stderr)
            for path, reason in rejected:
                print(f"  {path}: {reason}", file=sys.stderr)
            return 1
        print(
            f"TC scope guard passed: {len(paths)} changed paths since {baseline}; "
            f"all are TC-owned, documented shared seams, or one of "
            f"{len(frozen_imports)} byte-verified immutable imports and "
            f"{len(contract_adaptations)} exact approved Provider contract adaptations."
        )
        return 0
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"TC scope guard error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
