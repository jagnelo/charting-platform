"""Authenticated durable inputs for application-owned worker evidence resolvers."""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.result_publication import ResultPublicationPlan
from app.strategy_lab_v2.submissions import SubmissionReceipt


@dataclass(frozen=True, slots=True)
class WorkerTerminalEvidenceInputs:
    """Owner-authenticated durable state supplied to one terminal resolver.

    Each field is loaded through the shared persistence bundle. Missing state
    is represented explicitly so the application resolver can return a retry
    instead of inventing terminal evidence. This value is a lookup snapshot,
    not a cross-table transaction; callers must preserve the attempt binding
    when combining it with the immutable worker completion context.
    """

    attempt_id: str
    submission: SubmissionReceipt | None
    execution: ExecutionCommandContext | None
    manifest: RunResultManifest | None
    publications: tuple[ResultPublicationPlan, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if self.submission is not None:
            if not isinstance(self.submission, SubmissionReceipt):
                raise TypeError("submission must be a SubmissionReceipt or None")
            if self.submission.request.attempt_id != self.attempt_id:
                raise ValueError("submission references a different attempt")
        if self.execution is not None:
            if not isinstance(self.execution, ExecutionCommandContext):
                raise TypeError("execution must be an ExecutionCommandContext or None")
            if self.execution.outcome.attempt_id != self.attempt_id:
                raise ValueError("execution references a different attempt")
        if self.manifest is not None:
            if not isinstance(self.manifest, RunResultManifest):
                raise TypeError("manifest must be a RunResultManifest or None")
            if self.manifest.attempt_id != self.attempt_id:
                raise ValueError("manifest references a different attempt")
        publications = tuple(self.publications)
        if any(not isinstance(item, ResultPublicationPlan) for item in publications):
            raise TypeError("publications must contain ResultPublicationPlan values")
        ordered = tuple(sorted(publications, key=lambda item: item.fingerprint))
        if publications != ordered:
            raise ValueError("publications must be ordered by fingerprint")
        if any(item.attempt_id != self.attempt_id for item in publications):
            raise ValueError("publication references a different attempt")
        object.__setattr__(self, "publications", publications)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


__all__ = ["WorkerTerminalEvidenceInputs"]
