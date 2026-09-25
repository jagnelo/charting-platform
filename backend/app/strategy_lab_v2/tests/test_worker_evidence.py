from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outcomes import new_execution_outcome
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.progress import new_progress_state
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    ResultPublicationPlan,
)
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_result_publication import _result
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _submission() -> SubmissionReceipt:
    body = {"attempt": "attempt-1"}
    request = SubmissionRequest(
        "idempotency-key",
        "backtest",
        "attempt-1",
        content_digest(body),
        NOW,
    )
    return SubmissionReceipt(request, NOW)


def _publication(attempt_id: str = "attempt-1", seed: str = "publication") -> ResultPublicationPlan:
    return ResultPublicationPlan(
        content_digest(seed),
        content_digest(f"{seed}-reproduction"),
        attempt_id,
        content_digest(f"{seed}-engine"),
        ResultPublicationDecision.PUBLISH,
    )


def _execution() -> ExecutionCommandContext:
    submission = _submission()
    return ExecutionCommandContext(
        new_execution_outcome(submission.submission_id, "attempt-1", accepted_at=NOW),
        new_progress_state("attempt-1", total_units=10, now=NOW),
    )


def test_terminal_evidence_inputs_bind_every_record_to_attempt() -> None:
    manifest, *_ = _result()
    inputs = WorkerTerminalEvidenceInputs(
        "attempt-1",
        _submission(),
        _execution(),
        manifest,
        (_publication(),),
    )

    assert inputs.fingerprint.startswith("sha256:")
    assert inputs.publications[0].attempt_id == inputs.attempt_id


@pytest.mark.parametrize("field", ("submission", "execution", "manifest"))
def test_terminal_evidence_inputs_reject_cross_attempt_records(field: str) -> None:
    manifest, *_ = _result()
    with pytest.raises(ValueError, match="different attempt"):
        if field == "submission":
            WorkerTerminalEvidenceInputs("attempt-2", _submission(), None, None)
        elif field == "execution":
            WorkerTerminalEvidenceInputs("attempt-2", None, _execution(), None)
        else:
            WorkerTerminalEvidenceInputs("attempt-2", None, None, manifest)


def test_terminal_evidence_inputs_require_deterministic_publication_order() -> None:
    first = _publication(seed="a")
    second = _publication(seed="b")
    ordered = tuple(sorted((first, second), key=lambda item: item.fingerprint))
    with pytest.raises(ValueError, match="ordered"):
        WorkerTerminalEvidenceInputs("attempt-1", None, None, None, tuple(reversed(ordered)))


def test_terminal_evidence_lookup_binds_owner_and_submission() -> None:
    receipt = _submission()
    inputs = WorkerTerminalEvidenceInputs("attempt-1", receipt, _execution(), None)
    lookup = WorkerTerminalEvidenceLookup(WorkerSubmissionBinding("alice", receipt), inputs)

    assert lookup.owner_id == "alice"
    assert lookup.fingerprint.startswith("sha256:")

    with pytest.raises(ValueError, match="binding and evidence submission"):
        WorkerTerminalEvidenceLookup(
            WorkerSubmissionBinding("alice", receipt),
            WorkerTerminalEvidenceInputs("attempt-1", None, None, None),
        )
