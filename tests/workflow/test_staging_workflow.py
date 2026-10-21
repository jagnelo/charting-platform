from __future__ import annotations

import importlib.util
import io
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text()


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "jobs_mode", ["success", "skipped", "missing", "duplicate", "run_failure"]
)
def test_public_ci_watch_fetches_jobs_only_at_terminal_and_polls_conservatively(
    monkeypatch: pytest.MonkeyPatch,
    jobs_mode: str,
) -> None:
    staging = load_script("staging")
    sha = "a" * 40
    monkeypatch.setattr(staging, "shutil_which", lambda name: None)
    monkeypatch.setattr(staging, "github_repository", lambda: "example/repo")
    monkeypatch.setattr(staging, "CI_RETRY_DISCOVERY_ATTEMPTS", 0)
    calls: list[str] = []
    sleeps: list[float] = []
    details = iter(["in_progress", "completed"])

    def urlopen(request, timeout):
        assert timeout == 20
        url = request.full_url
        calls.append(url)
        if "/actions/runs?" in url:
            payload = {
                "workflow_runs": [
                    {
                        "id": 123,
                        "head_sha": sha,
                        "head_branch": "staging",
                        "status": "in_progress",
                        "conclusion": None,
                    }
                ]
            }
        elif url.endswith("/jobs?per_page=100"):
            payload = {
                "jobs": [
                    {
                        "name": "Exhaustive Integration Gate",
                        "conclusion": "skipped"
                        if jobs_mode == "skipped"
                        else "success",
                    }
                ]
            }
            if jobs_mode == "missing":
                payload["jobs"] = []
            elif jobs_mode == "duplicate":
                payload["jobs"] *= 2
        else:
            status = next(details)
            payload = {
                "id": 123,
                "status": status,
                "head_sha": sha,
                "head_branch": "staging",
                "run_attempt": 1,
                "html_url": "https://github.com/example/repo/actions/runs/123",
                "conclusion": "success" if status == "completed" else None,
            }
            if status == "completed" and jobs_mode == "run_failure":
                payload["conclusion"] = "failure"
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(staging.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(staging.time, "sleep", sleeps.append)
    if jobs_mode == "success":
        result = staging.github_run("staging", sha, exhaustive=True)
        assert result["conclusion"] == "success"
    else:
        with pytest.raises(SystemExit, match="not green|Exhaustive Integration Gate"):
            staging.github_run("staging", sha, exhaustive=True)
    assert len(calls) == 4  # discovery, two run reads, one terminal jobs read
    assert sum("/jobs?" in url for url in calls) == 1
    assert sleeps == [120.0]
    assert staging.CI_API_WATCH_ATTEMPTS * staging.CI_API_POLL_SECONDS == 3600


@pytest.mark.parametrize(
    "code,remaining,message",
    [
        (403, "0", "rate limit exhausted"),
        (429, "0", "rate limit exhausted"),
        (403, "45", "request denied"),
    ],
)
def test_public_api_errors_never_manufacture_ci_evidence(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    remaining: str,
    message: str,
) -> None:
    staging = load_script("staging")
    monkeypatch.setattr(staging, "shutil_which", lambda name: None)
    monkeypatch.setattr(staging, "github_repository", lambda: "example/repo")

    def denied(request, timeout):
        raise staging.urllib.error.HTTPError(
            request.full_url,
            code,
            "denied",
            {"X-RateLimit-Remaining": remaining, "X-RateLimit-Reset": "1792138791"},
            None,
        )

    monkeypatch.setattr(staging.urllib.request, "urlopen", denied)
    with pytest.raises(SystemExit, match=message):
        staging.github_run("staging", "a" * 40, exhaustive=True)


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "missing_marker",
        "invalid_json",
        "non_mapping_marker",
        "wrong_commit",
        "advanced_before",
        "bad_start",
        "empty_sources",
        "bad_source_record",
        "protected_source",
        "duplicate_source",
        "bad_source_sha",
        "non_ancestor",
        "gate_failure",
        "advanced_after",
        "marker_changed",
        "receipt_failure",
    ],
)
def test_interrupted_watch_reconciliation_is_exact_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    staging = load_script("staging")
    sha, start, source = "a" * 40, "b" * 40, "c" * 40
    monkeypatch.setattr(staging, "ROOT", tmp_path / "staging")
    monkeypatch.setattr(staging, "STAGING_PATH", tmp_path / "staging")
    marker_path = tmp_path / "staging-degraded.json"
    marker = {
        "staging_sha": sha,
        "starting_staging_sha": start,
        "sources": [{"branch": "feat/example", "sha": source}],
        "reason": "HTTP403 public API rate exhaustion",
    }
    if case == "wrong_commit":
        marker["staging_sha"] = "d" * 40
    elif case == "bad_start":
        marker["starting_staging_sha"] = "not-a-sha"
    elif case == "empty_sources":
        marker["sources"] = []
    elif case == "bad_source_record":
        marker["sources"] = [None]
    elif case == "protected_source":
        marker["sources"][0]["branch"] = "master"
    elif case == "duplicate_source":
        marker["sources"] *= 2
    elif case == "bad_source_sha":
        marker["sources"][0]["sha"] = "bad"
    if case != "missing_marker":
        marker_path.write_text(
            "broken"
            if case == "invalid_json"
            else "[]"
            if case == "non_mapping_marker"
            else json.dumps(marker)
        )
    monkeypatch.setattr(staging, "DEGRADED", marker_path)
    monkeypatch.setattr(staging, "root_master_ready", lambda: None)
    monkeypatch.setattr(staging, "integration_lock", nullcontext)
    monkeypatch.setattr(
        staging,
        "ensure_staging",
        lambda remediate: ("d" * 40 if case == "advanced_before" else sha),
    )
    monkeypatch.setattr(
        staging,
        "synchronized",
        lambda path, branch: ("d" * 40 if case == "advanced_after" else sha),
    )
    monkeypatch.setattr(staging, "fetch_branch", lambda *args, **kwargs: None)
    attempts: list[dict] = []
    ancestry_calls: list[str] = []

    def run(*args, **kwargs):
        # Recovery must never merge, reset, delete a ref or push anything.
        assert args[:3] == ("git", "merge-base", "--is-ancestor")
        assert args[4] == sha
        ancestry_calls.append(args[3])
        return SimpleNamespace(returncode=1 if case == "non_ancestor" else 0)

    def gate(branch, commit, *, exhaustive):
        assert (branch, commit, exhaustive) == ("staging", sha, True)
        if case == "gate_failure":
            raise SystemExit("actual exhaustive gate not green")
        if case == "marker_changed":
            marker_path.write_text(json.dumps({**marker, "reason": "changed"}))
        return {"url": "https://github.com/example/repo/actions/runs/123"}

    def record(payload):
        assert marker_path.exists()  # Persist success before releasing the guard.
        if case == "receipt_failure":
            raise OSError("receipt write failed")
        attempts.append(payload)

    monkeypatch.setattr(staging, "run", run)
    monkeypatch.setattr(staging, "github_run", gate)
    monkeypatch.setattr(staging, "record_attempt", record)
    if case == "success":
        staging.reconcile(sha)
        assert not marker_path.exists()
        assert ancestry_calls == [start, source]
        assert len(attempts) == 1
        assert attempts[0]["state"] == "green"
        assert attempts[0]["sources"] == marker["sources"]
        assert attempts[0]["reconciled_interrupted_watch"] is True
    else:
        with pytest.raises((SystemExit, OSError)):
            staging.reconcile(sha)
        assert marker_path.exists() == (case != "missing_marker")
        assert attempts == []


def test_reconciliation_refuses_a_feature_or_root_control_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = load_script("staging")
    monkeypatch.setattr(staging, "ROOT", tmp_path / "not-staging")
    monkeypatch.setattr(staging, "STAGING_PATH", tmp_path / "staging")
    with pytest.raises(SystemExit, match="exact persistent staging checkout"):
        staging.reconcile("a" * 40)


def test_ci_uses_staging_and_master_without_emulation() -> None:
    workflow_text = text(".github/workflows/ci.yml")
    workflow = yaml.safe_load(workflow_text)
    pushes = workflow[True]["push"]["branches"]
    assert "staging" in pushes
    assert "master" in pushes
    assert "docker/setup-qemu-action" not in workflow_text
    assert "platforms: arm64" not in workflow_text
    assert "name: Exhaustive Integration Gate" in workflow_text
    assert "refs/heads/staging" in workflow_text
    assert "refs/heads/master" in workflow_text


def test_normal_integration_gate_is_architecture_neutral() -> None:
    makefile = text("Makefile")
    target = makefile.split("validate-integration:", 1)[1].split(
        "validate-focused-integration:", 1
    )[0]
    assert "validate-arm64" not in makefile
    assert "qemu" not in target.lower()
    assert not (ROOT / "scripts" / "validate-arm64-images.py").exists()


def test_pinned_browser_uses_egress_bridge_and_strict_acceptance() -> None:
    makefile = text("Makefile")
    runner = next(
        line for line in makefile.splitlines() if line.startswith("PLAYWRIGHT_DOCKER =")
    )
    assert '--network "$${STACK_COMPOSE_PROJECT}_host-access"' in runner
    assert "-e STACK_URL=http://host-port-relay" in runner
    assert "--memory $(PLAYWRIGHT_DOCKER_MEMORY)" in runner
    assert "--cpus $(PLAYWRIGHT_DOCKER_CPUS)" in runner
    assert "_charting" not in runner
    assert "--network host" not in runner
    assert "/usr/share/fonts" not in runner
    functional = makefile.split("test-e2e:\n", 1)[1].split("test-e2e-headed:", 1)[0]
    visual = makefile.split("stage=e2e-visual;", 1)[1].split("; \\\n", 1)[0]
    assert "npx playwright test --retries=0" in functional
    assert "tc2000_visual.spec.ts --retries=0" in visual
    compose = yaml.safe_load(text("docker-compose.e2e.yml"))
    assert compose["networks"]["charting"]["internal"] is True
    assert compose["networks"]["host-access"]["driver"] == "bridge"
    for service in ("backend", "worker"):
        environment = compose["services"][service]["environment"]
        assert environment["PROVIDER_ROUTING_ENABLED"] == "false"
        assert environment["HTTPS_PROXY"] == "http://provider-egress-deny:3128"


def test_staging_helper_never_creates_local_integration_candidates() -> None:
    helper = text("scripts/staging.py")
    assert 'AI / "worktrees" / "staging"' in helper
    assert '".ai" / "integration"' not in helper
    assert 'worktree", "add", "--detach' not in helper
    assert '"--no-ff"' in helper
    assert '"--ff-only"' in helper
    ignore = text(".gitignore")
    assert ".ai/staging-attempts/" in ignore
    assert ".ai/locks/" in ignore
    assert ".ai/staging-degraded.json" in ignore


def test_staging_helper_refetches_remote_heads_after_github_gates() -> None:
    helper = text("scripts/staging.py")
    assert helper.count('fetch_branch("staging", cwd=STAGING_PATH)') >= 3
    post_master_gate = helper.split(
        'master_ci = github_run("master", commit, exhaustive=True)', 1
    )[1]
    assert 'fetch_branch("master")' in post_master_gate
    assert 'git("rev-parse", "origin/master") != commit' in post_master_gate


@pytest.mark.parametrize(
    ("location", "branch", "dirty", "master_synced", "failure"),
    [
        ("staging", "staging", False, True, None),
        ("staging", "staging", True, True, "staging coordinator checkout is dirty"),
        ("staging", "staging", False, False, "master is not synchronized"),
        ("feature", "feat/example", False, True, "persistent staging coordinator"),
        ("feature", "staging", False, True, "persistent staging coordinator"),
        ("root", "master", True, True, "root master checkout is dirty"),
        ("root", "master", False, True, None),
    ],
)
def test_coordinator_guard_checks_its_own_checkout_without_mutating_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    location: str,
    branch: str,
    dirty: bool,
    master_synced: bool,
    failure: str | None,
) -> None:
    staging = load_script("staging")
    common = tmp_path / "repo"
    staging_path = common / ".ai" / "worktrees" / "staging"
    current = {
        "root": common,
        "staging": staging_path,
        "feature": common / ".ai" / "worktrees" / "feat-example",
    }[location]
    monkeypatch.setattr(staging, "ROOT", current)
    monkeypatch.setattr(staging, "COMMON_ROOT", common)
    monkeypatch.setattr(staging, "STAGING_PATH", staging_path)
    fetched: list[tuple[str, Path]] = []

    def fake_git(*args: str, **kwargs: object) -> str:
        assert kwargs.get("cwd", current) == current
        if args == ("branch", "--show-current"):
            return branch
        if args == ("status", "--porcelain"):
            return " M unrelated.txt" if dirty else ""
        if args == ("rev-parse", "origin/master"):
            return "a" * 40
        if args in {("rev-parse", "master"), ("rev-parse", "HEAD")}:
            return ("a" if master_synced else "b") * 40
        raise AssertionError(f"unexpected Git operation: {args}")

    def fake_fetch(name: str, *, cwd: Path | None = None) -> None:
        fetched.append((name, cwd or current))

    monkeypatch.setattr(staging, "git", fake_git)
    monkeypatch.setattr(staging, "fetch_branch", fake_fetch)
    if failure:
        with pytest.raises(SystemExit, match=failure):
            staging.root_master_ready()
    else:
        staging.root_master_ready()
        assert fetched == [("master", current)]


def test_github_gate_waits_for_asynchronous_push_run_registration() -> None:
    helper = text("scripts/staging.py")
    github_body = helper.split("def github_run", 1)[1].split("def shutil_which", 1)[0]
    assert "CI_DISCOVERY_ATTEMPTS" in github_body
    assert "CI_DISCOVERY_DELAY_SECONDS" in github_body
    assert "time.sleep(CI_DISCOVERY_DELAY_SECONDS)" in github_body


@pytest.mark.parametrize(
    ("location", "branch", "dirty", "master_synced", "staging_synced", "failure"),
    [
        ("staging", "staging", False, True, True, None),
        ("staging", "staging", True, True, True, "operator checkout is dirty"),
        ("staging", "staging", False, False, True, "master is not synchronized"),
        ("staging", "staging", False, True, False, "staging is not synchronized"),
        (
            "feature",
            "feat/example",
            False,
            True,
            True,
            "persistent staging coordinator",
        ),
        ("feature", "staging", False, True, True, "persistent staging coordinator"),
        ("feature", "master", False, True, True, "persistent staging coordinator"),
        ("root", "master", True, True, True, "operator checkout is dirty"),
        ("root", "master", False, True, True, None),
    ],
)
def test_worktree_bootstrap_accepts_only_the_exact_clean_coordinator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    location: str,
    branch: str,
    dirty: bool,
    master_synced: bool,
    staging_synced: bool,
    failure: str | None,
) -> None:
    helper = load_script("worktree")
    common = tmp_path / "repo"
    staging = common / ".ai" / "worktrees" / "staging"
    current = {
        "root": common,
        "staging": staging,
        "feature": common / ".ai" / "worktrees" / "feat-example",
    }[location]
    monkeypatch.setattr(helper, "repo_root", lambda: current)
    monkeypatch.setattr(helper, "common_root", lambda: common)
    monkeypatch.setattr(helper, "branch_path", lambda name: staging)
    monkeypatch.setattr(helper, "git_succeeds", lambda *args: True)

    def fake_git(*args: str, **kwargs: object) -> str:
        cwd = kwargs.get("cwd", current)
        assert cwd in {current, staging}
        if location == "staging":
            assert cwd != common
        if args == ("branch", "--show-current"):
            return branch
        if args == ("status", "--porcelain"):
            return " M unrelated.txt" if dirty else ""
        if args == ("diff", "--check") or args[0] == "fetch":
            return ""
        if args == ("rev-parse", "--verify", "origin/master"):
            return "a" * 40
        if args == ("rev-parse", "master") or (
            cwd == common and args == ("rev-parse", "HEAD")
        ):
            return ("a" if master_synced else "b") * 40
        if args == ("rev-parse", "origin/staging"):
            return "c" * 40
        if cwd == staging and args == ("rev-parse", "HEAD"):
            return ("c" if staging_synced else "d") * 40
        raise AssertionError(f"unexpected Git operation: {args}")

    monkeypatch.setattr(helper, "git", fake_git)
    if failure:
        with pytest.raises(SystemExit, match=failure):
            helper.ensure_operator_ready()
    else:
        helper.ensure_operator_ready()


def test_staging_bootstrap_refuses_degraded_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = load_script("staging")
    marker = tmp_path / "master-degraded.json"
    marker.write_text(
        '{"master_sha": "' + "a" * 40 + '", "reason": "master replay failed"}\n'
    )
    monkeypatch.setattr(staging, "MASTER_DEGRADED", marker)
    with pytest.raises(SystemExit, match="master is marked degraded"):
        staging.require_healthy_master()


def test_closed_workstream_may_use_integration_capture_for_its_own_closure_tip() -> (
    None
):
    helper = text("scripts/staging.py")
    assert "integration_capture: exact branch head" in helper.lower()


def test_new_worktree_creation_refuses_degraded_master() -> None:
    helper = text("scripts/worktree.py")
    assert '"master-degraded.json"' in helper
    assert "before creating new work" in helper


def test_staging_status_resolves_the_real_master_worktree() -> None:
    helper = text("scripts/staging.py")
    status_body = helper.split("def status() -> None:", 1)[1].split(
        "def main() -> int:", 1
    )[0]
    assert 'master_path = worktree_path("master")' in status_body
    assert '(("master", master_path), ("staging", STAGING_PATH))' in status_body


def test_worktree_defaults_and_closure_follow_staging() -> None:
    helper = text("scripts/worktree.py")
    assert 'p.add_argument("--base", default="staging")' in helper
    assert '"--is-ancestor", branch, "staging"' in helper
    assert "comparison_base = (" in helper
    assert 'f"{comparison_base}...{branch}"' in helper
    assert '"comparison_base": comparison_base' in helper
    assert "staging-degraded.json" in helper
    assert "+refs/heads/staging:refs/remotes/origin/staging" in helper


def test_pre_staging_archive_is_explicit_and_preserves_remote_history() -> None:
    helper = text("scripts/worktree.py")
    makefile = text("Makefile")
    lifecycle = text("docs/worktree-lifecycle.md")
    assert "def pre_staging_archive_reasons" in helper
    assert 'integration_path = branch_path("master")' in helper
    assert '"merge-base", "--is-ancestor", branch, "master"' in helper
    assert '"origin/{branch}"' in helper
    assert '"branch", "-d", branch' in helper
    assert "--pre-staging" in helper
    assert "--reason" in helper
    assert "worktree-archive-pre-staging" in makefile
    assert "remote branch and tracked workstream record" in lifecycle


def test_pre_staging_archive_does_not_weaken_normal_staging_close() -> None:
    helper = text("scripts/worktree.py")
    close_body = helper.split("def close(branch: str)", 1)[1].split(
        "def main() -> int:", 1
    )[0]
    assert '"--is-ancestor", branch, "staging"' in close_body
    assert "archive_pre_staging" not in close_body


def test_subsumed_archive_requires_named_parent_and_retains_remote_history() -> None:
    helper = text("scripts/worktree.py")
    makefile = text("Makefile")
    lifecycle = text("docs/worktree-lifecycle.md")
    assert "def archive_subsumed" in helper
    assert '"merge-base", "--is-ancestor", branch, parent' in helper
    assert 'git("branch", "-d", branch, cwd=parent_path)' in helper
    assert "archive-subsumed" in helper
    assert "worktree-archive-subsumed" in makefile
    assert "cumulative parent" in lifecycle


def test_operational_tail_archive_is_record_only_and_guarded() -> None:
    helper = text("scripts/worktree.py")
    makefile = text("Makefile")
    lifecycle = text("docs/worktree-lifecycle.md")
    validator = text("scripts/validate-workstream.py")
    assert "def operational_tail_reasons" in helper
    assert (
        "staging is bootstrapped; use normal staging integration and close instead"
        in helper
    )
    assert "branch contains unmerged files outside its own workstream record" in helper
    assert 'values.get("status") not in {"closed", "superseded"}' in helper
    assert 'git("branch", "-D", branch)' in helper
    assert "archive-operational-tail" in helper
    assert "worktree-archive-operational-tail" in makefile
    assert "remote branch and" in lifecycle
    assert "tracked record remain the audit trail" in lifecycle
    assert '"superseded"' in validator


@pytest.mark.parametrize("platform", ["linux/arm/v7", "linux/arm64"])
def test_rpi_config_accepts_supported_target_platforms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    rpi = load_script("rpi")
    config = tmp_path / ".ai" / "deploy" / "rpi.env"
    config.parent.mkdir(parents=True)
    config.write_text(
        "RPI_SSH_TARGET=pi.local\n"
        "RPI_DEPLOY_ROOT=/opt/charting-platform\n"
        "RPI_HTTP_PORT=8080\n"
        f"RPI_DOCKER_PLATFORM={platform}\n"
    )
    config.chmod(0o600)
    monkeypatch.setattr(rpi, "ROOT", tmp_path)
    assert rpi.load_config()["RPI_DOCKER_PLATFORM"] == platform


def test_rpi_config_rejects_unreviewed_target_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rpi = load_script("rpi")
    config = tmp_path / ".ai" / "deploy" / "rpi.env"
    config.parent.mkdir(parents=True)
    config.write_text(
        "RPI_SSH_TARGET=pi.local\n"
        "RPI_DEPLOY_ROOT=/opt/charting-platform\n"
        "RPI_HTTP_PORT=8080\n"
        "RPI_DOCKER_PLATFORM=linux/amd64\n"
    )
    config.chmod(0o600)
    monkeypatch.setattr(rpi, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="linux/arm/v7 or linux/arm64"):
        rpi.load_config()


def test_legacy_integration_entry_points_delegate_to_staging() -> None:
    for name in ("integrate.py", "integrate-set.py"):
        helper = text(f"scripts/{name}")
        assert "import staging" in helper
        assert "staging.integrate" in helper
        assert "worktree add" not in helper


def test_conflict_aborts_and_restores_exact_staging_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = load_script("staging")
    staging_path = tmp_path / "staging"
    source_path = tmp_path / "source"
    staging_path.mkdir()
    source_path.mkdir()
    start = "1" * 40
    source = "2" * 40
    git_calls: list[tuple[str, ...]] = []
    attempts: list[dict[str, object]] = []

    monkeypatch.setattr(staging, "STAGING_PATH", staging_path)
    monkeypatch.setattr(staging, "root_master_ready", lambda: None)
    monkeypatch.setattr(staging, "integration_lock", nullcontext)
    monkeypatch.setattr(staging, "ensure_staging", lambda remediate: start)
    monkeypatch.setattr(staging, "worktree_path", lambda branch: source_path)
    monkeypatch.setattr(staging, "synchronized", lambda path, branch: source)
    monkeypatch.setattr(staging, "require_closed_workstream", lambda path, branch: None)
    monkeypatch.setattr(staging, "github_run", lambda branch, sha, exhaustive: {})
    monkeypatch.setattr(staging, "record_attempt", attempts.append)

    def fake_run(*args: str, **kwargs):
        assert args[:3] == ("git", "merge", "--no-ff")
        return SimpleNamespace(returncode=1, stdout="", stderr="conflict")

    def fake_git(*args: str, **kwargs) -> str:
        git_calls.append(args)
        if args[:3] == ("diff", "--name-only", "--diff-filter=U"):
            return "Makefile\nscripts/worktree.py"
        if args[:2] == ("status", "--porcelain"):
            return ""
        return ""

    monkeypatch.setattr(staging, "run", fake_run)
    monkeypatch.setattr(staging, "git", fake_git)

    with pytest.raises(SystemExit, match="restored unchanged"):
        staging.integrate(["feat/example"], remediate=False)

    assert ("merge", "--abort") in git_calls
    assert ("reset", "--hard", start) in git_calls
    assert attempts == [
        {
            "state": "conflict",
            "created_at": attempts[0]["created_at"],
            "starting_staging_sha": start,
            "source_branch": "feat/example",
            "source_sha": source,
            "conflicts": ["Makefile", "scripts/worktree.py"],
        }
    ]


def test_bootstrap_recovers_after_branch_and_remote_were_already_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = load_script("staging")
    current = "3" * 40
    target = tmp_path / "staging"
    git_calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(staging, "STAGING_PATH", target)
    monkeypatch.setattr(staging, "root_master_ready", lambda: None)
    monkeypatch.setattr(staging, "fetch_branch", lambda branch, cwd: None)
    monkeypatch.setattr(staging, "synchronized", lambda path, branch: current)

    def fake_git(*args: str, **kwargs) -> str:
        git_calls.append(args)
        if args == ("rev-parse", "HEAD"):
            return current
        if args == ("rev-parse", "--verify", "refs/heads/staging"):
            return current
        if args == ("ls-remote", "--heads", "origin", "staging"):
            return f"{current}\trefs/heads/staging"
        if args[:3] == ("worktree", "add", str(target)):
            target.mkdir()
        return ""

    monkeypatch.setattr(staging, "git", fake_git)
    staging.bootstrap(current)

    assert ("branch", "staging", current) not in git_calls
    assert ("push", "-u", "origin", "staging") not in git_calls
    assert ("worktree", "add", str(target), "staging") in git_calls


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("linux/arm/v7", "^armv7"), ("linux/arm64", "^(aarch64|arm64)$")],
)
def test_rpi_preflight_checks_configured_remote_architecture(
    monkeypatch: pytest.MonkeyPatch, platform: str, expected: str
) -> None:
    rpi = load_script("rpi")
    captured: list[str] = []

    def fake_remote(config, command, **kwargs):
        captured.append(command.decode())
        return ""

    monkeypatch.setattr(rpi, "remote", fake_remote)
    rpi.preflight(
        {
            "RPI_DEPLOY_ROOT": "/opt/charting-platform",
            "RPI_HTTP_PORT": "8080",
            "RPI_DOCKER_PLATFORM": platform,
        }
    )
    assert expected in captured[0]
    assert f"does not match {platform}" in captured[0]
    assert "required_name in SECRET_KEY POSTGRES_PASSWORD CORS_ORIGINS" in captured[0]
    assert "missing or empty deployment setting" in captured[0]
    assert 'grep -Eq "^$required_name=.+$" "$env_file"' in captured[0]
    assert "PROVIDER_QUOTA_LEDGER_DATABASE_URL must be PostgreSQL" in captured[0]
    assert (
        "ensure_provider_quota_coordinator(require_persistent_coordinator=True)"
        in text("scripts/rpi.py")
    )
