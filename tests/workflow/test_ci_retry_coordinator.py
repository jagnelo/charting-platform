import importlib.util
import io
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "ci_retry_coordinator", ROOT / "scripts" / "ci-retry-coordinator.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_allowlisted_setup_steps_are_retryable():
    helper = load()
    assert (
        helper.classify_step_failure(
            "Install dependencies",
            "apt update failed with HTTP 403 from packages.microsoft.com",
        )
        == "dependency-host-http-403"
    )
    assert (
        helper.classify_step_failure(
            "Install frontend deps", "npm registry connection reset by peer"
        )
        == "dependency-transport"
    )
    assert (
        helper.classify_step_failure("Run unit tests", "connection reset by peer")
        is None
    )


def test_unknown_and_second_attempt_failures_are_not_retried(monkeypatch):
    helper = load()
    monkeypatch.setattr(helper, "failed_jobs", lambda *_: [])
    first = helper.evaluate("org/repo", "123", 1, "push", "staging")
    second = helper.evaluate("org/repo", "123", 2, "push", "staging")
    assert first["action"] == "skip"
    assert second["action"] == "skip"
    assert "allowlisted" in first["reason"]
    assert "consumed" in second["reason"]


def test_retry_helper_is_bounded_and_never_swallows_final_failure():
    helper = (ROOT / "scripts" / "ci-retry.sh").read_text()
    assert 'max_attempts="${CI_RETRY_MAX_ATTEMPTS:-3}"' in helper
    assert 'backoffs="${CI_RETRY_BACKOFF_SECONDS:-10 30}"' in helper
    assert 'exit "$status"' in helper
    assert "Test, build, migration," in helper
    assert "lint" in helper


def test_job_log_reader_handles_github_zip_payload(monkeypatch):
    helper = load()
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("job.txt", "Install dependencies\nHTTP 503")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args, 0, stdout=payload.getvalue(), stderr=b""
        )

    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    assert "HTTP 503" in helper.gh_job_logs("org/repo", "123")
