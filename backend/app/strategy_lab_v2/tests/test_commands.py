from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.commands import (
    CommandEffect,
    ExecutionCommand,
    ExecutionCommandDecision,
    ExecutionCommandKind,
    ExecutionCommandLedger,
    resolve_execution_command,
)
from app.strategy_lab_v2.outcomes import (
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
    new_execution_outcome,
)
from app.strategy_lab_v2.progress import (
    ExecutionProgressUpdate,
    ProgressPhase,
    apply_progress_update,
    new_progress_state,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
ATTEMPT = "attempt-1"


def _command(value: str, kind: ExecutionCommandKind, *, requested_at: datetime = NOW) -> ExecutionCommand:
    return ExecutionCommand(content_digest({"command": value}), ATTEMPT, kind, requested_at, "operator request")


def _states(status: OutcomeStatus = OutcomeStatus.RUNNING, phase: ProgressPhase = ProgressPhase.RUNNING):
    submission_id = content_digest("submission")
    outcome = new_execution_outcome(submission_id, ATTEMPT, accepted_at=NOW)
    if status is not OutcomeStatus.ACCEPTED:
        outcome = apply_outcome_update(
            outcome,
            OutcomeUpdate(
                submission_id,
                ATTEMPT,
                1,
                status,
                NOW + timedelta(seconds=1),
                result_digest=content_digest("result")
                if status is OutcomeStatus.SUCCEEDED
                else None,
            ),
        ).state
    progress = new_progress_state(ATTEMPT, total_units=10, now=NOW)
    if phase is not ProgressPhase.QUEUED:
        progress = apply_progress_update(
            progress,
            ExecutionProgressUpdate(
                ATTEMPT,
                1,
                phase,
                10 if phase is ProgressPhase.SUCCEEDED else 1,
                10,
                NOW + timedelta(seconds=1),
            ),
        )
    return outcome, progress


def test_cancel_command_accepts_and_exact_retry_replays() -> None:
    outcome, progress = _states()
    command = _command("cancel", ExecutionCommandKind.CANCEL)
    accepted = resolve_execution_command(ExecutionCommandLedger(), command, outcome, progress, accepted_at=NOW)
    assert accepted.decision is ExecutionCommandDecision.ACCEPT
    assert accepted.receipt is not None
    assert accepted.receipt.effect is CommandEffect.CANCELLATION_REQUESTED
    replay = resolve_execution_command(accepted.ledger, command, outcome, progress, accepted_at=NOW + timedelta(seconds=1))
    assert replay.decision is ExecutionCommandDecision.REPLAY_EXISTING
    assert replay.receipt == accepted.receipt


def test_changed_command_content_conflicts() -> None:
    outcome, progress = _states()
    command = _command("cancel", ExecutionCommandKind.CANCEL)
    accepted = resolve_execution_command(ExecutionCommandLedger(), command, outcome, progress, accepted_at=NOW)
    changed = ExecutionCommand(command.command_id, ATTEMPT, ExecutionCommandKind.RETRY, NOW, "different")
    conflict = resolve_execution_command(accepted.ledger, changed, outcome, progress, accepted_at=NOW)
    assert conflict.decision is ExecutionCommandDecision.CONFLICT


def test_cancel_terminal_and_retry_nonfailed_are_rejected() -> None:
    succeeded, succeeded_progress = _states(OutcomeStatus.SUCCEEDED, ProgressPhase.SUCCEEDED)
    cancelled = resolve_execution_command(
        ExecutionCommandLedger(), _command("cancel", ExecutionCommandKind.CANCEL), succeeded, succeeded_progress, accepted_at=NOW
    )
    assert cancelled.decision is ExecutionCommandDecision.REJECT
    running, running_progress = _states()
    retry = resolve_execution_command(
        ExecutionCommandLedger(), _command("retry", ExecutionCommandKind.RETRY), running, running_progress, accepted_at=NOW
    )
    assert retry.decision is ExecutionCommandDecision.REJECT


def test_retry_failed_execution_is_accepted() -> None:
    failed, progress = _states(OutcomeStatus.FAILED, ProgressPhase.FAILED)
    resolved = resolve_execution_command(
        ExecutionCommandLedger(), _command("retry", ExecutionCommandKind.RETRY), failed, progress, accepted_at=NOW
    )
    assert resolved.decision is ExecutionCommandDecision.ACCEPT
    assert resolved.receipt is not None
    assert resolved.receipt.effect is CommandEffect.RETRY_REQUESTED


def test_identity_mismatch_fails_closed_without_ledger_mutation() -> None:
    outcome, progress = _states()
    wrong = ExecutionCommand(content_digest("wrong"), "other-attempt", ExecutionCommandKind.CANCEL, NOW, "request")
    resolved = resolve_execution_command(ExecutionCommandLedger(), wrong, outcome, progress, accepted_at=NOW)
    assert resolved.decision is ExecutionCommandDecision.REJECT
    assert resolved.ledger.receipts == ()


def test_command_acceptance_and_ledger_ordering_are_deterministic() -> None:
    outcome, progress = _states()
    first = resolve_execution_command(ExecutionCommandLedger(), _command("b", ExecutionCommandKind.CANCEL), outcome, progress, accepted_at=NOW)
    second = resolve_execution_command(first.ledger, _command("a", ExecutionCommandKind.CANCEL), outcome, progress, accepted_at=NOW)
    assert [item.command_id for item in second.ledger.receipts] == sorted(item.command_id for item in second.ledger.receipts)


def test_command_contract_rejects_invalid_digest_and_time() -> None:
    with pytest.raises(ValueError, match="command_id"):
        ExecutionCommand("bad", ATTEMPT, ExecutionCommandKind.CANCEL, NOW, "request")
    with pytest.raises(ValueError, match="precede"):
        resolve_execution_command(
            ExecutionCommandLedger(), _command("cancel", ExecutionCommandKind.CANCEL, requested_at=NOW + timedelta(seconds=1)), *_states(), accepted_at=NOW
        )
