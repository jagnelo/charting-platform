import importlib.util
from pathlib import Path


def text(path: str) -> str:
    return (Path(__file__).parents[2] / path).read_text()


def test_schema_four_and_unbounded_goal_are_recorded() -> None:
    helper = text("scripts/worktree.py")
    session = text("scripts/agent-session.py")
    assert '"schema: 4\\n"' in helper
    assert "planning_state: draft" in helper
    assert "local_validation_profile: pending_agent_assessment" in helper
    assert "goal_budget_policy: unbounded_unless_human_authorized" in helper
    assert '"goal_request"' in session
    assert '"token_budget"' in session
    assert "authorized_goal_budget" in session
    assert "planning_required" in session


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


def test_automatic_entry_does_not_require_human_prompt_boilerplate() -> None:
    entry = text("AGENTS.md")
    orchestration = text("docs/agent-orchestration.md")
    assert "automatically" in entry.lower()
    assert "human is not expected to repeat" in entry
    assert "fallback wrapper" in orchestration
    assert "recommended orchestrator prompt shape" not in orchestration.lower()


def test_dev_launcher_uses_uv_runtime_and_docker_readiness() -> None:
    launcher = text("dev.sh")
    assert 'WORKFLOW_PYTHON=(uv run --project "$BACKEND" python)' in launcher
    assert 'scripts/agent-session.py" docker-ready' in launcher
    assert 'python3 "$RUNTIME_HELPER"' not in launcher


def test_automatic_role_context_is_repository_native() -> None:
    context = text("scripts/agent-context.py")
    assert '"control"' in context
    assert '"staging_coordinator"' in context
    assert '"implementation"' in context
    assert '"automatic_entry": "AGENTS.md"' in context


def test_schema_four_plan_readiness_and_profiles() -> None:
    session = importlib.util.spec_from_file_location(
        "agent_session_plan", Path(__file__).parents[2] / "scripts" / "agent-session.py"
    )
    assert session and session.loader
    module = importlib.util.module_from_spec(session)
    session.loader.exec_module(module)
    draft = {"schema": 4, "planning_state": "draft"}
    assert module.plan_ready(draft) is False
    ready = {
        "schema": 4,
        "planning_state": "ready",
        "scope": ["workflow"],
        "owned_paths": ["scripts/"],
        "acceptance_criteria": [{"id": "AC1", "text": "works"}],
        "branch_tests": ["make test"],
        "local_validation_profile": "unit",
    }
    assert module.plan_ready(ready) is True
    assert module.profile_requires_docker("docker_integration") is True
    assert module.profile_requires_docker("unit") is False


def test_goal_budget_and_current_validation_are_explicit() -> None:
    session = importlib.util.spec_from_file_location(
        "agent_session_budget",
        Path(__file__).parents[2] / "scripts" / "agent-session.py",
    )
    assert session and session.loader
    module = importlib.util.module_from_spec(session)
    session.loader.exec_module(module)
    assert (
        module.authorized_goal_budget({"human_goal_budget_authorization": "none"})
        is None
    )
    assert (
        module.authorized_goal_budget(
            {"human_goal_budget_authorization": "authorized: 50000"}
        )
        == 50000
    )
    assert module.numeric_size("1.5GiB") == int(1.5 * 1024**3)
    request = module.make_goal_request(
        "do the work", {"human_goal_budget_authorization": "none"}
    )
    assert request == {"objective": "do the work"}
    authorized = module.make_goal_request(
        "do the work", {"human_goal_budget_authorization": "authorized: 1200"}
    )
    assert authorized == {"objective": "do the work", "token_budget": 1200}


def test_cleanup_and_readiness_are_scoped_to_the_current_worktree() -> None:
    session = text("scripts/agent-session.py")
    assert "def branch_and_path" in session
    assert "docker system prune" not in session
    assert "unknown_components" in session
    assert "validation_evidence_current" in session


def test_goal_request_is_objective_only_and_validation_can_be_profile_scoped(
    tmp_path: Path,
) -> None:
    session = importlib.util.spec_from_file_location(
        "agent_session_evidence",
        Path(__file__).parents[2] / "scripts" / "agent-session.py",
    )
    assert session and session.loader
    module = importlib.util.module_from_spec(session)
    session.loader.exec_module(module)
    assert module.make_goal_request("objective", {}) == {"objective": "objective"}
    journal = tmp_path / "validation.jsonl"
    journal.write_text(
        '{"sha":"abc","profile":"docker_integration","result":"passed"}\n'
    )
    assert module.validation_evidence_current(tmp_path, "abc", "docker_integration")
    assert not module.validation_evidence_current(tmp_path, "abc", "unit")


def test_validation_profile_classifier_cannot_weaken_runtime_boundaries() -> None:
    profile = importlib.util.spec_from_file_location(
        "validation_profile",
        Path(__file__).parents[2] / "scripts" / "validation_profile.py",
    )
    assert profile and profile.loader
    module = importlib.util.module_from_spec(profile)
    profile.loader.exec_module(module)
    assert module.classify_paths(["docs/agent-orchestration.md"]) == "none"
    assert module.classify_paths(["scripts/agent-session.py"]) == "unit"
    assert (
        module.classify_paths(["backend/tests/integration/test_api.py"])
        == "docker_integration"
    )
    assert (
        module.classify_paths(["frontend/src/views/Workstation.vue"])
        == "full_stack_browser"
    )
    assert not module.profile_is_sufficient(
        "unit", {"owned_paths": ["frontend/src/views/Workstation.vue"]}
    )
