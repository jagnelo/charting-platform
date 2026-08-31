from pathlib import Path


def text(path: str) -> str:
    return (Path(__file__).parents[2] / path).read_text()


def test_schema_three_and_unbounded_goal_are_recorded() -> None:
    helper = text("scripts/worktree.py")
    session = text("scripts/agent-session.py")
    assert '"schema: 3\\n"' in helper
    assert "goal_budget_policy: unbounded_unless_human_authorized" in helper
    assert '"goal_request"' in session
    assert "token_budget" not in session


def test_claims_are_locked_and_written_atomically() -> None:
    session = text("scripts/agent-session.py")
    assert "fcntl.flock" in session
    assert "os.replace" in session
    assert ".ai" in session and "session-claims" in session


def test_docker_policy_is_scoped_and_never_host_prunes() -> None:
    session = text("scripts/agent-session.py")
    assert "DOCKER_LIMIT_BYTES = 5_000_000_000" in session
    assert "docker system prune" not in session
    assert "unique_image_bytes" in session


def test_queue_has_single_coordinator_selection_path() -> None:
    queue = text("scripts/integration_queue.py")
    makefile = text("Makefile")
    assert "def integrate_ready" in queue
    assert "--integrate-ready" in queue
    assert "integrate-ready requires a clean root master coordinator checkout" in queue
    assert "scripts/integration_queue.py --integrate-ready" in makefile
