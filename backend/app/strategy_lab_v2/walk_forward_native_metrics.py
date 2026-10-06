"""Verified portfolio-level metrics over selected native walk-forward OOS traces."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from decimal import Decimal, localcontext
from itertools import tee

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import MetricValue, RunResultManifest
from app.strategy_lab_v2.metrics import calculate_event_aligned_equity_metrics
from app.strategy_lab_v2.nautilus_equity_trace import (
    NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
    iter_verified_nautilus_account_equity_observations,
)
from app.strategy_lab_v2.nautilus_equity_trace_receipt import (
    NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE,
    decode_nautilus_equity_trace_receipt,
)


def _datetime_ns(value: object) -> int:
    from datetime import UTC, datetime

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("walk-forward OOS window timestamps must be timezone-aware")
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _verified_reference(manifest: RunResultManifest, store: LocalArtifactStore):
    if not manifest.engine_authoritative or manifest.engine_name.lower() != "nautilus":
        raise ValueError("walk-forward OOS metrics require authoritative Nautilus results")
    receipt_artifacts = tuple(
        item
        for item in manifest.output_artifacts
        if item.media_type == NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE
    )
    if len(receipt_artifacts) != 1:
        raise ValueError("each OOS manifest must reference exactly one equity trace receipt")
    receipt = receipt_artifacts[0]
    reference = decode_nautilus_equity_trace_receipt(receipt, store.read(receipt.storage_key))
    if reference.artifact not in manifest.output_artifacts:
        raise ValueError("equity trace receipt references an unlisted native trace artifact")
    window = manifest.trial.evaluation_window
    if window is None or reference.evaluation_window_fingerprint != window.fingerprint:
        raise ValueError("equity trace receipt differs from its OOS trial window")
    if (reference.scoring_start_ns, reference.scoring_end_ns) != (
        _datetime_ns(window.start),
        _datetime_ns(window.end),
    ):
        raise ValueError("equity trace scoring bounds differ from the OOS trial window")
    if (
        reference.trial_id != manifest.trial.trial_id
        or reference.attempt_id != manifest.attempt.attempt_id
        or reference.portfolio_fingerprint != manifest.portfolio.fingerprint
        or reference.snapshot_fingerprint != manifest.snapshot.fingerprint
        or reference.base_currency != manifest.portfolio.base_currency
        or reference.initial_capital != manifest.portfolio.initial_capital
    ):
        raise ValueError("equity trace receipt differs from its authoritative result manifest")
    if reference.artifact.media_type != NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE:
        raise ValueError("equity trace receipt references an unsupported trace artifact")
    return reference


def calculate_walk_forward_native_oos_metrics(
    manifests: Sequence[RunResultManifest],
    *,
    artifact_store: LocalArtifactStore,
    selection_fingerprint: str,
) -> tuple[MetricValue, ...]:
    """Compound fold returns into one OOS equity curve and derive native metrics.

    Fold-opening marks are used to rebase each isolated simulation onto the
    preceding OOS terminal equity; later fold openings are not counted as
    returns. Gaps between non-overlapping test windows are treated as inactive
    (no mark/no P&L). The curve remains streamed; only metric accumulators grow.
    """

    from app.strategy_lab_v2.canonical import require_sha256_digest

    require_sha256_digest(selection_fingerprint, field_name="selection_fingerprint")
    if not isinstance(artifact_store, LocalArtifactStore):
        raise TypeError("artifact_store must be a LocalArtifactStore")
    records = tuple(manifests)
    if not records or any(not isinstance(item, RunResultManifest) for item in records):
        raise ValueError("at least one authoritative OOS result manifest is required")
    references = tuple(_verified_reference(item, artifact_store) for item in records)
    first_manifest = records[0]
    first_reference = references[0]
    previous_end = -1
    for manifest, reference in zip(records, references, strict=True):
        if (
            manifest.portfolio.fingerprint != first_manifest.portfolio.fingerprint
            or manifest.snapshot.fingerprint != first_manifest.snapshot.fingerprint
            or reference.base_currency != first_reference.base_currency
            or reference.scoring_start_ns is None
            or reference.scoring_end_ns is None
            or reference.scoring_start_ns < previous_end
        ):
            raise ValueError("selected OOS traces do not form one ordered portfolio series")
        previous_end = reference.scoring_end_ns

    evidence_digest = content_digest(
        {
            "definition": "strategy-lab.walk-forward.native-oos-equity.v1",
            "selection_fingerprint": selection_fingerprint,
            "manifests": tuple(item.fingerprint for item in records),
            "receipts": tuple(item.fingerprint for item in references),
            "trace_artifacts": tuple(item.artifact.content_digest for item in references),
            "gap_policy": "inactive_no_pnl",
        }
    )

    def marks_and_times() -> Iterator[tuple[Decimal, int]]:
        carried_equity: Decimal | None = None
        for index, (reference, manifest) in enumerate(zip(references, records, strict=True)):
            observations = iter_verified_nautilus_account_equity_observations(
                reference,
                artifact_store.path_for(reference.artifact.storage_key),
                expected_events=None,
            )
            opening: Decimal | None = None
            with localcontext() as context:
                context.prec = 38
                scale = Decimal(1)
                for observation_index, observation in enumerate(observations):
                    if observation_index == 0:
                        opening = observation.account_equity
                        if opening != manifest.portfolio.initial_capital:
                            raise ValueError(
                                "fold-opening equity differs from portfolio initial capital"
                            )
                        if index == 0:
                            carried_equity = opening
                            yield carried_equity, observation.event_time_ns
                        else:
                            if carried_equity is None:
                                raise ValueError("prior OOS fold did not provide terminal equity")
                            if opening == 0 and carried_equity != 0:
                                raise ValueError("cannot rebase a zero-opening OOS fold")
                            scale = Decimal(0) if opening == 0 else carried_equity / opening
                        continue
                    if opening is None:
                        raise ValueError("native OOS equity trace omitted its opening valuation")
                    carried_equity = observation.account_equity * scale
                    yield carried_equity, observation.event_time_ns
                if opening is None or carried_equity is None:
                    raise ValueError("native OOS equity trace contains no observations")

    pair_stream, time_stream = tee(marks_and_times())
    metrics = calculate_event_aligned_equity_metrics(
        (item[0] for item in pair_stream),
        event_time_ns=(item[1] for item in time_stream),
        base_currency=first_reference.base_currency,
        evidence_digest=evidence_digest,
        expected_mark_count=sum(item.observation_count for item in references)
        - (len(references) - 1),
    )
    return tuple(metrics)


__all__ = ["calculate_walk_forward_native_oos_metrics"]
