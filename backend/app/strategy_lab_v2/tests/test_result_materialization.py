from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationDecision,
    materialize_run_result,
)
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _inputs():
    result, *_ = result_fixture()
    evidence = EngineResultEvidence(
        result.trial_id,
        result.attempt_id,
        result.engine_name,
        result.engine_version,
        result.engine_build_digest,
        result.allocation_definition_version,
        result.dependency_catalog_digest,
        result.assumptions_digest,
        result.metric_set.fingerprint,
        tuple(item.content_digest for item in result.output_artifacts),
        NOW,
    )
    return result, evidence


def test_result_materialization_builds_reproducible_manifest_and_replays() -> None:
    result, evidence = _inputs()
    materialized = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
    )
    assert materialized.decision is ResultMaterializationDecision.MATERIALIZE
    assert materialized.manifest == result

    replay = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
        existing=result,
    )
    assert replay.decision is ResultMaterializationDecision.REPLAY_EXISTING
    assert replay.manifest == result


def test_result_materialization_rejects_provenance_drift_and_failed_attempts() -> None:
    result, evidence = _inputs()
    drifted = replace(evidence, metric_set_fingerprint=content_digest("other-metrics"))
    rejected = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        drifted,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
    )
    assert rejected.decision is ResultMaterializationDecision.REJECT
    assert "result_metric_evidence_mismatch" in (rejected.rejection_reason or "")

    failed_attempt = replace(result.attempt, state=AttemptState.FAILED)
    failed = materialize_run_result(
        result.trial,
        failed_attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
    )
    assert failed.decision is ResultMaterializationDecision.REJECT
    assert "result_attempt_not_succeeded" in (failed.rejection_reason or "")


def test_result_materialization_conflicts_with_changed_existing_content() -> None:
    result, evidence = _inputs()
    changed = replace(result, assumptions_digest=content_digest("changed"))
    conflict = materialize_run_result(
        result.trial,
        result.attempt,
        result.strategy_packages,
        result.portfolio,
        result.snapshot,
        evidence,
        result.metric_set,
        result.output_artifacts,
        created_at=NOW,
        existing=changed,
    )
    assert conflict.decision is ResultMaterializationDecision.CONFLICT
    assert conflict.rejection_reason == "attempt is already bound to different result content"


def test_result_materialization_validates_types_and_time() -> None:
    result, evidence = _inputs()
    with pytest.raises(TypeError, match="trial"):
        materialize_run_result("bad", result.attempt, result.strategy_packages, result.portfolio, result.snapshot, evidence, result.metric_set, result.output_artifacts, created_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        materialize_run_result(result.trial, result.attempt, result.strategy_packages, result.portfolio, result.snapshot, evidence, result.metric_set, result.output_artifacts, created_at=datetime(2024, 1, 1))


def test_engine_evidence_canonicalizes_artifact_order() -> None:
    result, _ = _inputs()
    first = content_digest("first-artifact")
    second = content_digest("second-artifact")
    evidence = EngineResultEvidence(
        result.trial_id,
        result.attempt_id,
        result.engine_name,
        result.engine_version,
        result.engine_build_digest,
        result.allocation_definition_version,
        result.dependency_catalog_digest,
        result.assumptions_digest,
        result.metric_set.fingerprint,
        (second, first),
        NOW,
    )
    assert evidence.artifact_content_digests == tuple(sorted((first, second)))
