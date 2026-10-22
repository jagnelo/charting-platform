from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    DataSeriesManifest,
    EventGranularity,
)
from app.strategy_lab_v2.coverage import (
    CoverageAttestation,
    CoverageVerificationDecision,
    verify_coverage_attestation,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
END = NOW + timedelta(days=1)


def _manifest() -> DataSeriesManifest:
    return DataSeriesManifest(
        "AAPL", "ohlcv", EventGranularity.BAR, "1d", "regular", "sip",
        NOW, END, AdjustmentMode.SPLIT_ADJUSTED, "split-only",
        content_digest("evidence"), content_digest("series"), 100,
    )


def _attestation(manifest: DataSeriesManifest, **changes: object) -> CoverageAttestation:
    values: dict[str, object] = {
        "evidence_digest": manifest.coverage_evidence_digest,
        "series_content_digest": manifest.content_digest,
        "instrument_id": manifest.instrument_id,
        "event_type": manifest.event_type,
        "event_granularity": manifest.event_granularity,
        "timeframe": manifest.timeframe,
        "session": manifest.session,
        "feed": manifest.feed,
        "adjustment": manifest.adjustment,
        "corporate_action_semantics": manifest.corporate_action_semantics,
        "start": manifest.start,
        "end": manifest.end,
        "row_count": manifest.row_count,
        "calendar_digest": content_digest("calendar"),
        "complete": True,
        "gap_free": True,
        "provider_adapter": "market-data-adapter",
        "attested_at": END,
    }
    values.update(changes)
    return CoverageAttestation(**values)  # type: ignore[arg-type]


def test_matching_attestation_verifies_every_series_dimension() -> None:
    report = verify_coverage_attestation(_manifest(), _attestation(_manifest()))
    assert report.decision is CoverageVerificationDecision.VERIFIED
    assert report.verified
    assert report.mismatches == ()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evidence_digest", content_digest("other-evidence")),
        ("series_content_digest", content_digest("other-series")),
        ("instrument_id", "MSFT"),
        ("event_type", "quote"),
        ("event_granularity", EventGranularity.TRADE),
        ("timeframe", "5m"),
        ("session", "extended"),
        ("feed", "iex"),
        ("adjustment", AdjustmentMode.RAW),
        ("corporate_action_semantics", "total-return"),
        ("start", NOW - timedelta(days=1)),
        ("end", END + timedelta(days=1)),
        ("row_count", 99),
    ),
)
def test_semantic_or_content_mismatch_rejects(field: str, value: object) -> None:
    manifest = _manifest()
    report = verify_coverage_attestation(manifest, _attestation(manifest, **{field: value}))
    assert report.decision is CoverageVerificationDecision.REJECTED
    assert field in report.mismatches
    assert not report.verified


def test_incomplete_or_gapped_claims_reject() -> None:
    manifest = _manifest()
    report = verify_coverage_attestation(
        manifest, _attestation(manifest, complete=False, gap_free=False)
    )
    assert report.mismatches == ("coverage_contains_gaps", "coverage_not_complete")


def test_report_identity_is_deterministic_and_manifest_bound() -> None:
    manifest = _manifest()
    first = verify_coverage_attestation(manifest, _attestation(manifest))
    second = verify_coverage_attestation(manifest, _attestation(manifest))
    assert first == second
    assert first.manifest_fingerprint == content_digest(manifest)
    assert first.fingerprint.startswith("sha256:")


def test_attestation_requires_digest_time_and_claim_types() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="evidence_digest"):
        _attestation(manifest, evidence_digest="bad")
    with pytest.raises(ValueError, match="coverage start"):
        _attestation(manifest, start=END, end=END)
    with pytest.raises(TypeError, match="complete"):
        _attestation(manifest, complete=1)


def test_verifier_requires_typed_inputs() -> None:
    manifest = _manifest()
    with pytest.raises(TypeError, match="manifest"):
        verify_coverage_attestation("bad", _attestation(manifest))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="attestation"):
        verify_coverage_attestation(manifest, "bad")  # type: ignore[arg-type]
