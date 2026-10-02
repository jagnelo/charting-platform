from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineReleaseChannel,
    NautilusReleasePin,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.conformance_fixtures import (
    ConformanceExecutionResolution,
    ConformanceFixtureObservation,
    ConformanceFixtureSuite,
    build_conformance_evidence,
    build_event_tape_parity_observation,
    execute_conformance_suite,
    require_complete_conformance_suite,
    require_runtime_probe_binding,
)
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventTape,
    materialize_nautilus_event,
    verify_nautilus_event_tape_parity,
)
from app.strategy_lab_v2.nautilus_runtime import (
    NautilusRcCompatibilityRuntime,
    NautilusRuntimeProbeEvidence,
)
from app.strategy_lab_v2.sdk import MarketEvent

NOW = datetime(2024, 1, 1, tzinfo=UTC)
PIN = NautilusReleasePin(
    package_version="2.0.0",
    release_tag="v2.0.0",
    source_digest=content_digest("nautilus-source-v2.0.0"),
    runtime_image_digest=content_digest("nautilus-runtime-v2.0.0"),
    python_version="3.12.11",
    rust_version="1.88.0",
    legacy_runtime_isolated=True,
)


def _suite(*, failed: ConformanceCheck | None = None) -> ConformanceFixtureSuite:
    observations = []
    for check in ConformanceCheck:
        expected = content_digest({"check": check.value, "expected": True})
        observed = (
            expected
            if check is not failed
            else content_digest({"check": check.value, "observed": False})
        )
        observations.append(
            ConformanceFixtureObservation(
                check, expected, observed, check is not failed, "fixture evidence"
            )
        )
    return ConformanceFixtureSuite("nautilus-v2-suite", tuple(observations))


def test_complete_suite_builds_evidence_and_authoritative_report_when_stable() -> None:
    suite = _suite()
    require_complete_conformance_suite(suite)
    evidence = build_conformance_evidence(
        "nautilus",
        "2.0.0",
        content_digest("build"),
        EngineReleaseChannel.STABLE,
        suite,
        tested_at=NOW,
        release_pin=PIN,
    )
    report = evaluate_engine_conformance(evidence)
    assert report.authoritative is True
    assert report.missing_checks == frozenset()
    assert evidence.fixture_digest == suite.fingerprint


def test_failed_fixture_is_compatible_evidence_but_not_a_pass() -> None:
    suite = _suite(failed=ConformanceCheck.NATIVE_ORDER_FILL_COST)
    evidence = build_conformance_evidence(
        "nautilus",
        "2.0.0-rc1",
        content_digest("build"),
        EngineReleaseChannel.RELEASE_CANDIDATE,
        suite,
        tested_at=NOW,
    )
    report = evaluate_engine_conformance(evidence)
    assert report.authoritative is False
    assert report.compatible is False
    assert ConformanceCheck.NATIVE_ORDER_FILL_COST in report.missing_checks


def test_incomplete_suite_fails_closed_before_evidence_creation() -> None:
    suite = ConformanceFixtureSuite(
        "partial",
        (
            ConformanceFixtureObservation(
                ConformanceCheck.DETERMINISTIC_REPLAY,
                content_digest("expected"),
                content_digest("expected"),
                True,
            ),
        ),
    )
    with pytest.raises(ValueError, match="incomplete"):
        require_complete_conformance_suite(suite)
    with pytest.raises(ValueError, match="incomplete"):
        build_conformance_evidence(
            "nautilus",
            "2.0.0",
            content_digest("build"),
            EngineReleaseChannel.STABLE,
            suite,
            tested_at=NOW,
        )


def test_fixture_observation_rejects_untruthful_pass_claims() -> None:
    with pytest.raises(ValueError, match="matching"):
        ConformanceFixtureObservation(
            ConformanceCheck.ENGINE_LIFECYCLE,
            content_digest("expected"),
            content_digest("observed"),
            True,
        )
    with pytest.raises(ValueError, match="differing"):
        ConformanceFixtureObservation(
            ConformanceCheck.ENGINE_LIFECYCLE,
            content_digest("same"),
            content_digest("same"),
            False,
        )


def test_suite_order_and_identity_are_deterministic() -> None:
    first = _suite()
    second = ConformanceFixtureSuite("nautilus-v2-suite", tuple(reversed(first.observations)))
    assert first == second
    assert first.fingerprint == second.fingerprint
    assert tuple(item.check.value for item in first.observations) == tuple(
        sorted(item.check.value for item in first.observations)
    )


def test_invalid_types_and_timestamp_fail_closed() -> None:
    with pytest.raises(TypeError, match="suite"):
        build_conformance_evidence(
            "nautilus",
            "2",
            content_digest("build"),
            EngineReleaseChannel.STABLE,
            "bad",  # type: ignore[arg-type]
            tested_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_conformance_evidence(
            "nautilus",
            "2",
            content_digest("build"),
            EngineReleaseChannel.STABLE,
            _suite(),
            tested_at=datetime(2024, 1, 1),
        )


def test_executable_suite_runs_all_checks_and_binds_the_report() -> None:
    expected = {
        check: content_digest({"check": check.value, "fixture": "ok"}) for check in ConformanceCheck
    }
    calls: list[ConformanceCheck] = []

    def runner(check: ConformanceCheck):
        calls.append(check)
        return {"check": check.value, "fixture": "ok"}

    resolved = execute_conformance_suite(
        expected,
        runner,
        suite_id="executable-v2",
        engine_id="nautilus",
        engine_version="2.0.0",
        build_digest=content_digest("build"),
        release_channel=EngineReleaseChannel.STABLE,
        tested_at=NOW,
        release_pin=PIN,
    )
    assert isinstance(resolved, ConformanceExecutionResolution)
    expected_order = tuple(cast(Any, ConformanceCheck))
    assert calls == list(sorted(expected_order, key=lambda item: item.value))
    assert resolved.report.authoritative
    assert resolved.suite.missing_checks == frozenset()


def test_executable_suite_reduces_runner_errors_to_failed_digest_evidence() -> None:
    expected = {
        check: content_digest({"check": check.value, "fixture": "ok"}) for check in ConformanceCheck
    }

    def runner(check: ConformanceCheck):
        if check is ConformanceCheck.ENGINE_LIFECYCLE:
            raise RuntimeError("engine unavailable")
        return {"check": check.value, "fixture": "ok"}

    resolved = execute_conformance_suite(
        expected,
        runner,
        suite_id="error-v2",
        engine_id="nautilus",
        engine_version="2.0.0-rc1",
        build_digest=content_digest("build"),
        release_channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        tested_at=NOW,
    )
    assert not resolved.report.compatible
    failed = next(
        item
        for item in resolved.suite.observations
        if item.check is ConformanceCheck.ENGINE_LIFECYCLE
    )
    assert not failed.passed
    assert failed.detail == "runner failed: RuntimeError"


def test_event_tape_parity_receipt_projects_into_conformance_observation() -> None:
    event = MarketEvent(
        "daily-bars",
        "bar-1",
        "US.AAPL",
        NOW,
        0,
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
    )
    record = materialize_nautilus_event(event, event_type="ohlcv")
    tape = NautilusEventTape(content_digest("source"), (record,))
    observed = {
        "dependency_id": record.dependency_id,
        "event_id": record.event_id,
        "instrument_id": record.instrument_id,
        "event_type": record.event_type,
        "event_time_ns": record.event_time_ns,
        "sequence": record.sequence,
        "values": dict(record.values),
    }
    receipt = verify_nautilus_event_tape_parity(tape, (observed,))
    expected = content_digest(receipt)

    observation = build_event_tape_parity_observation(expected, receipt)

    assert observation.check is ConformanceCheck.FORWARD_EVENT_TAPE_PARITY
    assert observation.passed is True
    assert observation.observed_digest == expected


def test_failed_event_tape_parity_receipt_cannot_become_a_pass() -> None:
    event = MarketEvent(
        "daily-bars",
        "bar-1",
        "US.AAPL",
        NOW,
        0,
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
    )
    record = materialize_nautilus_event(event, event_type="ohlcv")
    tape = NautilusEventTape(content_digest("source"), (record,))
    observed = {
        "dependency_id": record.dependency_id,
        "event_id": record.event_id,
        "instrument_id": record.instrument_id,
        "event_type": record.event_type,
        "event_time_ns": record.event_time_ns,
        "sequence": record.sequence,
        "values": {**record.values, "close": 999},
    }
    receipt = verify_nautilus_event_tape_parity(tape, (observed,))

    observation = build_event_tape_parity_observation(receipt.fingerprint, receipt)

    assert observation.passed is False


def test_executable_suite_requires_exact_expected_checks() -> None:
    expected = {check: content_digest({"check": check.value}) for check in ConformanceCheck}
    expected.pop(ConformanceCheck.ENGINE_LIFECYCLE)
    with pytest.raises(ValueError, match="exact"):
        execute_conformance_suite(
            expected,
            lambda _check: None,
            suite_id="partial",
            engine_id="nautilus",
            engine_version="2.0.0",
            build_digest=content_digest("build"),
            release_channel=EngineReleaseChannel.STABLE,
            tested_at=NOW,
        )


def _rc_runtime() -> NautilusRcCompatibilityRuntime:
    return NautilusRcCompatibilityRuntime(
        source_digest=content_digest("nautilus-v2-rc5-source"),
        runtime_image_digest=content_digest("nautilus-v2-rc5-image"),
        python_version="3.12.11",
        rust_version="1.88.0",
    )


def _rc_resolution(runtime: NautilusRcCompatibilityRuntime) -> ConformanceExecutionResolution:
    expected = {
        check: content_digest({"check": check.value, "fixture": "rc5"})
        for check in ConformanceCheck
    }
    return execute_conformance_suite(
        expected,
        lambda check: {"check": check.value, "fixture": "rc5"},
        suite_id="rc5-probed-runtime",
        engine_id="nautilus",
        engine_version=runtime.package_version,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        release_channel=runtime.release_channel,
        tested_at=NOW,
        release_pin=runtime.release_pin,
    )


def _rc_probe(runtime: NautilusRcCompatibilityRuntime) -> NautilusRuntimeProbeEvidence:
    return NautilusRuntimeProbeEvidence.from_mapping(
        {
            "engine_lifecycle": "passed",
            "implementation": "cpython",
            "nautilus_package_version": "2.0.0rc5",
            "platform": "Linux-x86_64",
            "python_version": "3.12.11",
        },
        runtime,
    )


def test_executable_rc_suite_binds_to_the_probed_runtime_image() -> None:
    runtime = _rc_runtime()
    resolution = _rc_resolution(runtime)

    require_runtime_probe_binding(resolution, runtime, _rc_probe(runtime))

    assert resolution.report.execution_eligible
    assert not resolution.report.authoritative


def test_runtime_probe_binding_rejects_a_different_image_digest() -> None:
    runtime = _rc_runtime()
    resolution = _rc_resolution(runtime)
    probe = NautilusRuntimeProbeEvidence(
        runtime_fingerprint=runtime.fingerprint,
        runtime_image_digest=content_digest("different-image"),
        package_version=runtime.package_version,
        python_version=runtime.python_version,
        platform="Linux-x86_64",
        implementation="cpython",
        engine_lifecycle="passed",
    )

    with pytest.raises(ValueError, match="image digest"):
        require_runtime_probe_binding(resolution, runtime, probe)
