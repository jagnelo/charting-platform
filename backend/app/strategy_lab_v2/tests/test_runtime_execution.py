from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionDecision,
    RuntimeExecutionPhase,
    RuntimeExecutionUpdate,
    StrategyRuntimeDecision,
    StrategyRuntimeRequest,
    apply_runtime_execution_update,
    new_runtime_execution_state,
    preflight_strategy_runtime,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _profile() -> RuntimeIsolationProfile:
    return RuntimeIsolationProfile(
        runtime_image_digest=content_digest("image"),
        runtime_abi="python-3.12",
        allowed_dependency_digests=frozenset({content_digest("dep")}),
        output_limit_bytes=100,
    )


def _request(profile: RuntimeIsolationProfile | None = None) -> StrategyRuntimeRequest:
    profile = profile or _profile()
    return StrategyRuntimeRequest(
        content_digest("request"), "attempt-1", content_digest("package"),
        content_digest("source"), content_digest("inputs"), profile.fingerprint,
        "strategy.main:run",
        RuntimeIsolationRequest("attempt-1", (content_digest("dep"),)), NOW,
    )


def test_allowed_request_binds_profile_and_creates_accepted_state() -> None:
    profile = _profile()
    preflight = preflight_strategy_runtime(_request(profile), profile)
    assert preflight.decision is StrategyRuntimeDecision.ALLOW
    state = new_runtime_execution_state(
        preflight, attempt_id="attempt-1", output_limit_bytes=100, accepted_at=NOW
    )
    assert state.phase is RuntimeExecutionPhase.ACCEPTED
    assert state.sequence == 0


def test_runtime_lifecycle_times_normalize_to_utc_for_identity() -> None:
    offset = timezone(timedelta(hours=2))
    profile = _profile()
    request = replace(
        _request(profile),
        submitted_at=(NOW + timedelta(hours=2)).replace(tzinfo=offset),
    )
    assert request.submitted_at == NOW
    preflight = preflight_strategy_runtime(request, profile)
    state = new_runtime_execution_state(
        preflight,
        attempt_id="attempt-1",
        output_limit_bytes=100,
        accepted_at=(NOW + timedelta(hours=2)).replace(tzinfo=offset),
    )
    assert state.updated_at == NOW
    update = RuntimeExecutionUpdate(
        preflight.request_fingerprint,
        "attempt-1",
        1,
        RuntimeExecutionPhase.RUNNING,
        (NOW + timedelta(hours=2, seconds=1)).replace(tzinfo=offset),
    )
    canonical = replace(update, observed_at=NOW + timedelta(seconds=1))
    assert update.observed_at == canonical.observed_at
    assert update.fingerprint == canonical.fingerprint


def test_profile_identity_mismatch_rejects_without_starting_runtime() -> None:
    request = _request()
    other = RuntimeIsolationProfile(content_digest("other-image"), "python-3.12")
    rejected = preflight_strategy_runtime(request, other)
    assert rejected.decision is StrategyRuntimeDecision.REJECT
    assert "runtime_profile_identity_mismatch" in rejected.rejection_reasons


def test_isolation_rejection_propagates_and_state_creation_fails_closed() -> None:
    profile = RuntimeIsolationProfile(
        content_digest("image"), "python-3.12", network_disabled=False
    )
    request = _request(profile)
    preflight = preflight_strategy_runtime(request, profile)
    assert preflight.decision is StrategyRuntimeDecision.REJECT
    assert "network_must_be_disabled" in preflight.rejection_reasons
    with pytest.raises(ValueError, match="allowed preflight"):
        new_runtime_execution_state(preflight, attempt_id="attempt-1", output_limit_bytes=100, accepted_at=NOW)


def test_running_and_success_receipts_enforce_output_budget_and_replay() -> None:
    preflight = preflight_strategy_runtime(_request(), _profile())
    state = new_runtime_execution_state(preflight, attempt_id="attempt-1", output_limit_bytes=100, accepted_at=NOW)
    running = apply_runtime_execution_update(
        state,
        RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 1, RuntimeExecutionPhase.RUNNING, NOW + timedelta(seconds=1)),
    )
    output = content_digest("output")
    succeeded = apply_runtime_execution_update(
        running.state,
        RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 2, RuntimeExecutionPhase.SUCCEEDED, NOW + timedelta(seconds=2), output, 25),
    )
    assert succeeded.decision is RuntimeExecutionDecision.APPLY
    replay = apply_runtime_execution_update(
        succeeded.state,
        RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 2, RuntimeExecutionPhase.SUCCEEDED, NOW + timedelta(seconds=2), output, 25),
    )
    assert replay.decision is RuntimeExecutionDecision.REPLAY_EXISTING
    with pytest.raises(ValueError, match="output exceeds"):
        apply_runtime_execution_update(
            running.state,
            RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 2, RuntimeExecutionPhase.SUCCEEDED, NOW + timedelta(seconds=2), output, 101),
        )


def test_failure_and_cancellation_are_terminal_and_conflicts_reject() -> None:
    preflight = preflight_strategy_runtime(_request(), _profile())
    state = new_runtime_execution_state(preflight, attempt_id="attempt-1", output_limit_bytes=100, accepted_at=NOW)
    failed = apply_runtime_execution_update(
        state,
        RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 1, RuntimeExecutionPhase.FAILED, NOW + timedelta(seconds=1), error_digest=content_digest("error")),
    )
    assert failed.state.phase is RuntimeExecutionPhase.FAILED
    with pytest.raises(ValueError, match="terminal runtime state"):
        apply_runtime_execution_update(
            failed.state,
            RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 2, RuntimeExecutionPhase.CANCELLED, NOW + timedelta(seconds=2)),
        )
    running = apply_runtime_execution_update(
        state,
        RuntimeExecutionUpdate(
            preflight.request_fingerprint,
            "attempt-1",
            1,
            RuntimeExecutionPhase.RUNNING,
            NOW + timedelta(seconds=1),
        ),
    )
    with pytest.raises(ValueError, match="conflicts"):
        apply_runtime_execution_update(
            running.state,
            RuntimeExecutionUpdate(
                preflight.request_fingerprint,
                "attempt-1",
                1,
                RuntimeExecutionPhase.CANCELLED,
                NOW + timedelta(seconds=2),
            ),
        )


def test_request_requires_attempt_binding_and_declared_digests() -> None:
    profile = _profile()
    with pytest.raises(ValueError, match="request_id"):
        StrategyRuntimeRequest("bad", "attempt-1", content_digest("package"), content_digest("source"), content_digest("inputs"), _profile().fingerprint, "strategy.main:run", RuntimeIsolationRequest("attempt-1"), NOW)
    with pytest.raises(ValueError, match="runtime attempt"):
        StrategyRuntimeRequest(content_digest("request"), "attempt-1", content_digest("package"), content_digest("source"), content_digest("inputs"), profile.fingerprint, "strategy.main:run", RuntimeIsolationRequest("other"), NOW)


def test_update_contract_requires_terminal_payloads_and_monotonic_time() -> None:
    request_fingerprint = content_digest("request")
    with pytest.raises(ValueError, match="successful runtime updates"):
        RuntimeExecutionUpdate(request_fingerprint, "attempt-1", 1, RuntimeExecutionPhase.SUCCEEDED, NOW)
    with pytest.raises(ValueError, match="failed runtime updates"):
        RuntimeExecutionUpdate(request_fingerprint, "attempt-1", 1, RuntimeExecutionPhase.FAILED, NOW)
    preflight = preflight_strategy_runtime(_request(), _profile())
    state = new_runtime_execution_state(preflight, attempt_id="attempt-1", output_limit_bytes=100, accepted_at=NOW)
    with pytest.raises(ValueError, match="time cannot move backwards"):
        apply_runtime_execution_update(
            state,
            RuntimeExecutionUpdate(preflight.request_fingerprint, "attempt-1", 1, RuntimeExecutionPhase.RUNNING, NOW - timedelta(seconds=1)),
        )
