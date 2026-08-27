from __future__ import annotations

import importlib.util
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
