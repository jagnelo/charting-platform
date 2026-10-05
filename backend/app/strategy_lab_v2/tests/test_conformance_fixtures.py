from __future__ import annotations

import stat
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
    NautilusForwardParityResolution,
    NautilusRcConformanceResolution,
    build_conformance_evidence,
    build_event_tape_parity_observation,
    build_nautilus_backtest_compatibility_binding,
    build_nautilus_backtest_execution_binding,
    execute_conformance_suite,
    require_complete_conformance_suite,
    require_rc_fixture_binding,
    require_runtime_probe_binding,
    resolve_nautilus_forward_parity,
    resolve_nautilus_rc_conformance,
)
from app.strategy_lab_v2.contracts import ProductClass
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.local_conformance_source import (
    LOCAL_NAUTILUS_RC_EVIDENCE_ENV,
    LOCAL_NAUTILUS_RC_EVIDENCE_SCHEMA,
    LocalNautilusRcConformanceEvidencePublisher,
    LocalNautilusRcConformanceEvidenceSource,
)
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventTape,
    NautilusForwardDeliveryBinding,
    NautilusForwardEventParityReceipt,
    materialize_nautilus_event,
    materialize_nautilus_forward_tape,
    verify_nautilus_event_tape_parity,
    verify_nautilus_forward_event_tape_parity,
)
from app.strategy_lab_v2.nautilus_runtime import (
    NautilusRcCompatibilityRuntime,
    NautilusRcFixtureReceipt,
    NautilusRuntimeProbeEvidence,
)
from app.strategy_lab_v2.sdk import MarketEvent

NOW = datetime(2024, 1, 1, tzinfo=UTC)
PIN = NautilusReleasePin(
    package_version="2.0.0",
    release_tag="v2.0.0",
    source_digest=content_digest("nautilus-source-v2.0.0"),
    wheel_digest=content_digest("nautilus-wheel-v2.0.0"),
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


def test_forward_event_tape_parity_receipt_projects_into_conformance_observation() -> None:
    event = MarketEvent(
        "daily-bars",
        "bar-1",
        "US.AAPL",
        NOW,
        0,
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
    )
    canonical = CanonicalForwardEvent(
        event.event_id,
        event.sequence,
        event.event_time,
        NOW,
        content_digest("provider-source"),
    )
    tape = materialize_nautilus_forward_tape(
        "forward-instance-1",
        (canonical,),
        (event,),
        event_type_by_dependency={"daily-bars": "ohlcv"},
        delivery_bindings=(
            NautilusForwardDeliveryBinding(
                instance_id="forward-instance-1",
                event_fingerprint=content_digest(canonical),
                redis_stream_id="1704067200000-0",
                redis_entry_fingerprint=content_digest("redis-entry"),
                dispatch_record_fingerprint=content_digest("dispatch-record"),
                request_fingerprint=content_digest("dispatch-request"),
                pre_event_checkpoint_fingerprint=content_digest("checkpoint"),
                warmup_receipt_fingerprint=content_digest("warmup"),
                admission_decision="enqueue",
            ),
        ),
    )
    observed = (
        {
            "dependency_id": "daily-bars",
            "event_id": "bar-1",
            "instrument_id": "US.AAPL",
            "event_type": "ohlcv",
            "event_time_ns": 1_704_067_200_000_000_000,
            "sequence": 0,
            "values": dict(event.values),
        },
    )
    expected_receipt = verify_nautilus_forward_event_tape_parity(tape, observed)
    resolution = resolve_nautilus_forward_parity(
        tape,
        observed,
        expected_digest=content_digest(expected_receipt),
    )

    assert isinstance(resolution, NautilusForwardParityResolution)
    assert resolution.observation.check is ConformanceCheck.FORWARD_EVENT_TAPE_PARITY
    assert resolution.observation.passed is True
    assert resolution.observation.observed_digest == resolution.observation.expected_digest
    assert resolution.fingerprint.startswith("sha256:")


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


def _rc_partial_resolution(
    runtime: NautilusRcCompatibilityRuntime,
) -> ConformanceExecutionResolution:
    expected = {
        check: content_digest({"check": check.value, "fixture": "rc5"})
        for check in ConformanceCheck
    }

    def runner(check: ConformanceCheck):
        fixture = "deferred" if check is ConformanceCheck.FORWARD_EVENT_TAPE_PARITY else "rc5"
        return {"check": check.value, "fixture": fixture}

    return execute_conformance_suite(
        expected,
        runner,
        suite_id="rc5-partial-fixture",
        engine_id="nautilus",
        engine_version=runtime.package_version,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        release_channel=runtime.release_channel,
        tested_at=NOW,
        release_pin=runtime.release_pin,
    )


def _rc_accounting_run(instrument_count: int) -> dict[str, Any]:
    quantity = 1000 * instrument_count
    commission = 2 * instrument_count
    account_total = "98897.79" if instrument_count == 1 else "97795.58"
    return {
        "account_total": account_total,
        "instrument_count": instrument_count,
        "total_orders": instrument_count,
        "total_positions": instrument_count,
        "orders_total": str(instrument_count),
        "positions_total": str(instrument_count),
        "native_reports": {
            "commission_total": f"{commission:.2f}",
            "commissions": ["2.00 USD"] * instrument_count,
            "expected_commission_per_fill": "2.00",
            "expected_quantity_per_instrument": "1000",
            "expected_quantity_total": str(quantity),
            "execution_prices": ["1.10021"] * instrument_count,
            "fee_currency": "USD",
            "fill_instrument_ids": [f"INSTRUMENT-{i}" for i in range(instrument_count)],
            "fill_quantities": ["1000"] * instrument_count,
            "filled_quantity": str(quantity),
            "fills_report_rows": instrument_count,
            "initial_account_total": "100000.00",
            "best_ask": "1.10020",
            "orders_report_rows": instrument_count,
            "price_increment": "0.00001",
            "total_fills": instrument_count,
        },
    }


def _rc_receipt_payload() -> dict[str, Any]:
    native_order_run = _rc_accounting_run(1)
    native_order_run["target_allocation_probe"] = {
        "instrument_id": "AAPL.SIM",
        "requested_target_fraction": "0.5",
        "total_orders": 1,
        "total_positions": 1,
        "initial_cash": "100000",
        "remaining_cash": "50000",
        "observed_deployment": "50000",
        "account_base_currency": "USD",
        "authoritative": False,
    }
    native_order_run["raw_order_risk_probe"] = {
        "instrument_id": "AAPL.SIM",
        "requested_order_quantity": "100",
        "estimated_signed_base_notional": "10001",
        "total_orders": 1,
        "total_positions": 1,
        "initial_cash": "100000",
        "remaining_cash": "89997",
        "observed_deployment": "10003",
        "account_base_currency": "USD",
        "authoritative": False,
    }
    component_pnl = {
        "authoritative": False,
        "archived_snapshot_cycles": 1,
        "base_currency": "USD",
        "closed_position_cycles": 2,
        "component_gross_pnl": "4.00",
        "component_id": "core",
        "component_net_pnl": "3.00",
        "component_order_count": 4,
        "exact_account_reconciliation": True,
        "fill_count": 4,
        "native_trade_id_join_count": 4,
        "portfolio_gross_pnl": "4.00",
        "portfolio_net_pnl": "3.00",
        "reported_cost_deductions": "1.50",
        "reported_rebates": "0.50",
        "snapshot_index_differs_from_fill_position_id": True,
        "total_orders": 4,
    }
    return {
        "authoritative": False,
        "deterministic_replay": {"equal": True},
        "engine_lifecycle": "passed",
        "forward_event_tape_parity": "deferred_authoritative_fixture",
        "forward_native_session": {
            "account_event_fingerprint": content_digest("forward-account-event"),
            "authoritative": False,
            "non_empty_prefix_runtime_reconstruction": True,
            "reconstructed_account_event_fingerprint": content_digest(
                "forward-account-event-after-runtime-rebuild"
            ),
            "passed": True,
            "result_fingerprint": content_digest("forward-native-result"),
            "runtime_session_fingerprint": content_digest("forward-native-session"),
        },
        "forward_streaming_session": {
            "equal": True,
            "first": {
                "account_total": "100000.00",
                "authoritative": False,
                "batch_count": 2,
                "batch_event_counts": [1, 1],
                "fill_count": 1,
                "order_count": 1,
                "position_count": 1,
                "strategy_submitted_instrument_count": 1,
            },
            "second": {
                "account_total": "100000.00",
                "authoritative": False,
                "batch_count": 2,
                "batch_event_counts": [1, 1],
                "fill_count": 1,
                "order_count": 1,
                "position_count": 1,
                "strategy_submitted_instrument_count": 1,
            },
        },
        "multi_instrument_accounting": _rc_accounting_run(2),
        "native_component_pnl_attribution": component_pnl,
        "native_signed_fee_reconciliation": {
            "authoritative": False,
            "positive_fee": {
                **component_pnl,
                "component_net_pnl": "3.00",
                "portfolio_net_pnl": "3.00",
                "reported_cost_deductions": "1.00",
                "reported_rebates": "0.00",
            },
            "rebate": {
                **component_pnl,
                "component_net_pnl": "5.00",
                "portfolio_net_pnl": "5.00",
                "reported_cost_deductions": "0.00",
                "reported_rebates": "1.00",
            },
        },
        "native_order_fill_cost": native_order_run,
        "portfolio_rebalance_schedule": {
            "authoritative": False,
            "session_open": {
                "audit_fingerprint": content_digest("rc-open-schedule-audit"),
                "execution_status": "orders_submitted",
                "submitted_order_count": 1,
                "total_orders": 1,
                "total_positions": 1,
                "authoritative": False,
            },
            "session_close": {
                "audit_fingerprint": content_digest("rc-close-schedule-audit"),
                "execution_status": "orders_submitted",
                "submitted_order_count": 1,
                "total_orders": 1,
                "total_positions": 1,
                "authoritative": False,
            },
            "multi_component_shared_account": {
                "audit_fingerprint": content_digest("rc-multi-schedule-audit"),
                "execution_status": "orders_submitted",
                "submitted_order_count": 2,
                "total_orders": 2,
                "total_positions": 1,
                "remaining_cash": "50000",
                "authoritative": False,
            },
            "component_priority_contention": {
                "audit_fingerprint": content_digest("rc-priority-schedule-audit"),
                "execution_status": "orders_submitted",
                "submitted_order_count": 1,
                "total_orders": 1,
                "total_positions": 1,
                "remaining_cash": "90000",
                "component_order_tag": "strategy-lab-v2:component:satellite",
                "component_fill_attribution": {
                    "component_id": "satellite",
                    "venue_order_id": "SIM-1-1",
                    "instrument_id": "AAPL.SIM",
                    "quantity": "99",
                    "execution_price": "100.03",
                    "commission": "0.00 USD",
                    "currency": "USD",
                },
                "authoritative": False,
            },
            "shared_risk_rejection": {
                "risk_rejected": True,
                "risk_gate": "shared_portfolio",
                "submission_prevented": True,
                "total_orders": 0,
                "total_positions": 0,
                "authoritative": False,
            },
            "fail_on_misfire": {
                "audit_fingerprint": content_digest("rc-misfire-schedule-audit"),
                "execution_status": "failed_misfire",
                "submitted_order_count": 0,
                "total_orders": 0,
                "total_positions": 0,
                "authoritative": False,
            },
        },
    }


def _rc_receipt(runtime: NautilusRcCompatibilityRuntime) -> NautilusRcFixtureReceipt:
    return NautilusRcFixtureReceipt.from_mapping(_rc_receipt_payload(), runtime)


def _rc_complete_receipt(runtime: NautilusRcCompatibilityRuntime) -> NautilusRcFixtureReceipt:
    payload = _rc_receipt_payload()
    parity = NautilusForwardEventParityReceipt(
        instance_id="fixture-forward-instance",
        forward_tape_fingerprint=content_digest("fixture-forward-tape"),
        expected_event_count=3,
        observed_event_count=3,
        expected_wire_digest=content_digest("fixture-forward-wire"),
        observed_wire_digest=content_digest("fixture-forward-wire"),
        passed=True,
    )
    payload["forward_event_tape_parity"] = {
        "authoritative": False,
        "event_count": 3,
        "event_types": ["ohlcv", "quote", "trade"],
        "expected_wire_digest": parity.expected_wire_digest,
        "forward_tape_fingerprint": parity.forward_tape_fingerprint,
        "instance_id": parity.instance_id,
        "mismatches": [],
        "observed_event_count": 3,
        "observed_wire_digest": parity.observed_wire_digest,
        "passed": True,
        "receipt_fingerprint": parity.fingerprint,
        "unexpected_callback_count": 0,
    }
    return NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def _rc_evidence_artifact(runtime: NautilusRcCompatibilityRuntime) -> dict[str, Any]:
    return {
        "artifact_schema": LOCAL_NAUTILUS_RC_EVIDENCE_SCHEMA,
        "build_digest": runtime.runtime_image_digest,
        "probe": {
            "engine_lifecycle": "passed",
            "implementation": "cpython",
            "nautilus_package_version": runtime.package_version,
            "platform": "Linux-x86_64",
            "python_version": runtime.python_version,
        },
        "receipt": _rc_receipt_payload(),
        "runtime": {
            "python_version": runtime.python_version,
            "runtime_image_digest": runtime.runtime_image_digest,
            "rust_version": runtime.rust_version,
            "source_digest": runtime.source_digest,
        },
        "tested_at": NOW.isoformat(),
    }


def _write_local_evidence_artifact(directory: Any, runtime: NautilusRcCompatibilityRuntime) -> str:
    payload = _rc_evidence_artifact(runtime)
    return (
        LocalNautilusRcConformanceEvidencePublisher(directory)
        .publish(
            runtime=runtime,
            probe_payload=payload["probe"],
            fixture_payload=payload["receipt"],
            build_digest=payload["build_digest"],
            tested_at=NOW,
        )
        .artifact_digest
    )


def test_local_conformance_publisher_retries_atomically_without_overwrite(tmp_path: Any) -> None:
    runtime = _rc_runtime()
    payload = _rc_evidence_artifact(runtime)
    publisher = LocalNautilusRcConformanceEvidencePublisher(tmp_path)

    first = publisher.publish(
        runtime=runtime,
        probe_payload=payload["probe"],
        fixture_payload=payload["receipt"],
        build_digest=payload["build_digest"],
        tested_at=NOW,
    )
    second = publisher.publish(
        runtime=runtime,
        probe_payload=payload["probe"],
        fixture_payload=payload["receipt"],
        build_digest=payload["build_digest"],
        tested_at=NOW,
    )

    assert first.artifact_digest == second.artifact_digest
    assert first.resolution.fingerprint == second.resolution.fingerprint
    assert stat.S_IMODE(first.source.artifact_path.stat().st_mode) == 0o600


def test_local_conformance_publisher_rejects_failed_fixtures_before_writing(
    tmp_path: Any,
) -> None:
    runtime = _rc_runtime()
    payload = _rc_evidence_artifact(runtime)
    failed_fixture = dict(payload["receipt"])
    failed_fixture["engine_lifecycle"] = "failed"
    publisher = LocalNautilusRcConformanceEvidencePublisher(tmp_path)

    with pytest.raises(ValueError, match="lifecycle must pass"):
        publisher.publish(
            runtime=runtime,
            probe_payload=payload["probe"],
            fixture_payload=failed_fixture,
            build_digest=payload["build_digest"],
            tested_at=NOW,
        )

    assert not tuple(tmp_path.iterdir())


def test_local_conformance_source_verifies_content_and_exact_rc5_runtime_pins(
    tmp_path: Any,
) -> None:
    runtime = _rc_runtime()
    artifact_digest = _write_local_evidence_artifact(tmp_path, runtime)
    source = LocalNautilusRcConformanceEvidenceSource(
        artifact_directory=tmp_path,
        artifact_digest=artifact_digest,
        expected_source_digest=runtime.source_digest,
        expected_runtime_image_digest=runtime.runtime_image_digest,
    )

    resolution = source.load()

    assert resolution.evidence.release_pin == runtime.release_pin
    assert not resolution.report.authoritative
    binding = build_nautilus_backtest_compatibility_binding(
        resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"market"}),
        account_models=frozenset({"cash"}),
    )
    assert not binding.authoritative


def test_local_conformance_source_rejects_modified_artifact_bytes(tmp_path: Any) -> None:
    runtime = _rc_runtime()
    artifact_digest = _write_local_evidence_artifact(tmp_path, runtime)
    artifact_path = tmp_path / f"{artifact_digest.removeprefix('sha256:')}.json"
    artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
    source = LocalNautilusRcConformanceEvidenceSource(
        artifact_directory=tmp_path,
        artifact_digest=artifact_digest,
        expected_source_digest=runtime.source_digest,
        expected_runtime_image_digest=runtime.runtime_image_digest,
    )

    with pytest.raises(ValueError, match="digest does not match"):
        source.load()


def test_local_conformance_source_rejects_operator_pin_mismatch(tmp_path: Any) -> None:
    runtime = _rc_runtime()
    artifact_digest = _write_local_evidence_artifact(tmp_path, runtime)
    source = LocalNautilusRcConformanceEvidenceSource(
        artifact_directory=tmp_path,
        artifact_digest=artifact_digest,
        expected_source_digest=content_digest("different-source"),
        expected_runtime_image_digest=runtime.runtime_image_digest,
    )

    with pytest.raises(ValueError, match="source digest differs"):
        source.load()


def test_local_conformance_source_loads_only_complete_operator_environment(
    tmp_path: Any,
) -> None:
    runtime = _rc_runtime()
    artifact_digest = _write_local_evidence_artifact(tmp_path, runtime)
    environment = {
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_directory"]: str(tmp_path),
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_digest"]: artifact_digest,
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["source_digest"]: runtime.source_digest,
        LOCAL_NAUTILUS_RC_EVIDENCE_ENV["runtime_image_digest"]: runtime.runtime_image_digest,
    }

    assert LocalNautilusRcConformanceEvidenceSource.from_environment({}) is None
    with pytest.raises(ValueError, match="configuration is incomplete"):
        LocalNautilusRcConformanceEvidenceSource.from_environment(
            {LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_digest"]: artifact_digest}
        )
    source = LocalNautilusRcConformanceEvidenceSource.from_environment(environment)

    assert source is not None
    resolution = source.load()
    assert resolution.evidence.release_pin == runtime.release_pin
    assert resolution.report.authoritative is False


def test_executable_rc_suite_binds_to_the_probed_image_and_qualifies_full_scope() -> None:
    runtime = _rc_runtime()
    resolution = _rc_resolution(runtime)

    require_runtime_probe_binding(resolution, runtime, _rc_probe(runtime))

    assert resolution.report.execution_eligible
    assert resolution.report.authoritative


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


def test_partial_rc_fixture_receipt_binds_to_probe_and_conformance_suite() -> None:
    runtime = _rc_runtime()
    resolution = _rc_partial_resolution(runtime)
    receipt = _rc_receipt(runtime)

    require_rc_fixture_binding(resolution, runtime, _rc_probe(runtime), receipt)

    assert resolution.suite.missing_checks == receipt.deferred_checks
    assert resolution.evidence.passed_checks == receipt.passed_checks
    assert not receipt.authoritative


def test_partial_rc_fixture_receipt_rejects_suite_check_drift() -> None:
    runtime = _rc_runtime()
    resolution = _rc_resolution(runtime)
    receipt = _rc_receipt(runtime)

    with pytest.raises(ValueError, match="passed checks"):
        require_rc_fixture_binding(resolution, runtime, _rc_probe(runtime), receipt)


def test_rc_conformance_resolver_emits_non_authoritative_partial_evidence() -> None:
    runtime = _rc_runtime()
    probe = _rc_probe(runtime)
    receipt = _rc_receipt(runtime)

    result = resolve_nautilus_rc_conformance(
        runtime,
        probe,
        receipt,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        tested_at=NOW,
    )

    assert isinstance(result, NautilusRcConformanceResolution)
    assert result.evidence.fixture_digest == receipt.fixture_digest
    assert result.evidence.passed_checks == receipt.passed_checks
    assert result.report.missing_checks == receipt.deferred_checks
    assert result.report.release_pin_valid
    assert not result.report.compatible
    assert not result.report.authoritative
    assert result.fingerprint.startswith("sha256:")


def test_rc_conformance_resolver_accepts_complete_native_forward_parity() -> None:
    runtime = _rc_runtime()
    receipt = _rc_complete_receipt(runtime)

    result = resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        receipt,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        tested_at=NOW,
    )

    assert isinstance(result, NautilusRcConformanceResolution)
    assert result.report.compatible
    assert result.report.authoritative
    assert not result.report.missing_checks
    assert not receipt.deferred_checks
    assert not receipt.authoritative


def test_rc_conformance_can_bind_authoritative_local_backtests() -> None:
    runtime = _rc_runtime()
    receipt = _rc_receipt(runtime)
    resolution = resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        receipt,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        tested_at=NOW,
    )

    assert not resolution.report.compatible
    assert not resolution.report.authoritative
    binding = build_nautilus_backtest_execution_binding(
        resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
    )

    assert binding.engine_name == "nautilus"
    assert binding.engine_version == "2.0.0rc5"
    assert binding.conformance_fingerprint == resolution.evidence.fingerprint
    assert binding.authoritative


def test_stable_v2_conformance_can_bind_authoritative_local_backtests() -> None:
    pin = NautilusReleasePin(
        package_version="2.0.0",
        release_tag="v2.0.0",
        source_digest=content_digest("nautilus-stable-source"),
        wheel_digest=content_digest("nautilus-stable-wheel"),
        runtime_image_digest=content_digest("nautilus-stable-image"),
        python_version="3.12.11",
        rust_version="1.88.0",
        legacy_runtime_isolated=True,
    )
    expected = {
        check: content_digest({"check": check.value, "fixture": "stable-v2"})
        for check in ConformanceCheck
    }
    resolution = execute_conformance_suite(
        expected,
        lambda check: {"check": check.value, "fixture": "stable-v2"},
        suite_id="stable-v2-authoritative-backtest",
        engine_id="nautilus",
        engine_version="2.0.0",
        build_digest=content_digest("nautilus-stable-build"),
        release_channel=EngineReleaseChannel.STABLE,
        tested_at=NOW,
        release_pin=pin,
    )

    binding = build_nautilus_backtest_execution_binding(
        resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
    )

    assert resolution.report.authoritative
    assert binding.authoritative


def test_rc_backtest_binding_rejects_missing_required_fixture_check() -> None:
    runtime = _rc_runtime()
    receipt = _rc_receipt(runtime)
    missing_check = ConformanceCheck.NATIVE_ORDER_FILL_COST
    incomplete_receipt = NautilusRcFixtureReceipt(
        runtime_fingerprint=receipt.runtime_fingerprint,
        runtime_image_digest=receipt.runtime_image_digest,
        fixture_digest=receipt.fixture_digest,
        passed_checks=receipt.passed_checks - {missing_check},
        deferred_checks=receipt.deferred_checks | {missing_check},
    )
    resolution = resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        incomplete_receipt,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        tested_at=NOW,
    )

    with pytest.raises(ValueError, match="native_order_fill_cost"):
        build_nautilus_backtest_compatibility_binding(
            resolution,
            product_classes=frozenset({ProductClass.EQUITY}),
            execution_models=frozenset({"bar-close"}),
            account_models=frozenset({"cash-equity"}),
        )


def test_rc_conformance_resolver_rejects_probe_identity_drift() -> None:
    runtime = _rc_runtime()
    receipt = _rc_receipt(runtime)
    drifted_probe = NautilusRuntimeProbeEvidence(
        runtime_fingerprint=runtime.fingerprint,
        runtime_image_digest=content_digest("different-image"),
        package_version=runtime.package_version,
        python_version=runtime.python_version,
        platform="Linux-x86_64",
        implementation="cpython",
        engine_lifecycle="passed",
    )

    with pytest.raises(ValueError, match="image digest"):
        resolve_nautilus_rc_conformance(
            runtime,
            drifted_probe,
            receipt,
            build_digest=content_digest("nautilus-v2-rc5-build"),
            tested_at=NOW,
        )
