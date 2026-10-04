from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    ConformanceDecision,
    EngineConformanceEvidence,
    EngineReleaseChannel,
    NautilusReleasePin,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.conformance_fixtures import resolve_nautilus_rc_conformance
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionScope,
    plan_nautilus_execution,
)
from app.strategy_lab_v2.nautilus_runtime import (
    NautilusRcCompatibilityRuntime,
    NautilusRcFixtureReceipt,
    NautilusRuntimeProbeEvidence,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimeRequest,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.tests.test_execution import _execution_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _rc_accounting_run(instrument_count: int) -> dict[str, object]:
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


def _runtime():
    profile = RuntimeIsolationProfile(
        content_digest("runtime-image"),
        "python-3.12",
        allowed_dependency_digests=frozenset({content_digest("dep")}),
    )
    request = StrategyRuntimeRequest(
        content_digest("runtime-request"),
        "attempt-1",
        content_digest("package"),
        content_digest("source"),
        content_digest("inputs"),
        profile.fingerprint,
        "strategy.main:run",
        RuntimeIsolationRequest("attempt-1", (content_digest("dep"),)),
        NOW,
    )
    return request, preflight_strategy_runtime(request, profile)


def _conformance(
    *,
    engine_id: str = "nautilus",
    channel: EngineReleaseChannel = EngineReleaseChannel.STABLE,
    checks: frozenset[ConformanceCheck] = frozenset(ConformanceCheck),
):
    version = "2.0.0" if channel is EngineReleaseChannel.STABLE else "2.0.0rc5"
    evidence = EngineConformanceEvidence(
        engine_id,
        version,
        content_digest("engine-build"),
        channel,
        content_digest("fixture"),
        checks,
        NOW,
        NautilusReleasePin(
            package_version=version,
            release_tag="v2.0.0" if channel is EngineReleaseChannel.STABLE else "v2.0.0rc5",
            source_digest=content_digest("nautilus-source"),
            wheel_digest=content_digest("nautilus-wheel"),
            runtime_image_digest=content_digest("runtime-image"),
            python_version="3.12.11",
            rust_version="1.88.0",
            legacy_runtime_isolated=True,
        ),
    )
    return evidence, evaluate_engine_conformance(evidence)


def _plan(request: StrategyRuntimeRequest) -> SandboxCommandPlan:
    return SandboxCommandPlan(
        request.fingerprint,
        content_digest("profile"),
        (
            "docker",
            "run",
            "--rm",
            "--init",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--user=65532:65532",
            "--workdir=/workspace",
            "--memory=536870912",
            "--ulimit=cpu=300",
            "--ulimit=fsize=1024",
            "--pids-limit=256",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864",
            "--mount=type=bind,src=/tmp/strategy-input,dst=/inputs/bundle,readonly",
            "--mount=type=bind,src=/tmp/strategy-output,dst=/outputs/result",
            "--env=STRATEGY_ATTEMPT_ID=attempt-1",
            f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={content_digest('inputs')}",
            f"runtime@{content_digest('runtime-image')}",
            "python",
            "runner",
        ),
        10,
        1024,
    )


def test_complete_stable_nautilus_gate_is_ready_and_authoritative() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance()
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert result.decision is EngineExecutionDecision.READY
    assert result.authoritative
    assert result.engine_id == "nautilus"
    assert result.fingerprint.startswith("sha256:")


def test_authoritative_nautilus_gate_rejects_runtime_image_drift() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance()
    plan = _plan(request)
    drifted = SandboxCommandPlan(
        plan.request_fingerprint,
        plan.profile_fingerprint,
        (*plan.argv[:19], f"runtime@{content_digest('different-nautilus-image')}", *plan.argv[20:]),
        plan.wall_timeout_seconds,
        plan.output_limit_bytes,
    )
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        drifted,
        data_snapshot_fingerprint=content_digest("snapshot"),
    )

    assert result.decision is EngineExecutionDecision.REJECT
    assert "nautilus_runtime_image_mismatch" in result.rejection_reasons


def test_release_candidate_authority_is_scope_gated_by_conformance_checks() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    backtest_checks = NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks
    partial_evidence, partial_report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=backtest_checks,
    )
    partial_full = plan_nautilus_execution(
        authorization,
        runtime,
        partial_evidence,
        partial_report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert partial_full.decision is EngineExecutionDecision.REJECT
    assert not partial_full.authoritative
    assert "required_engine_conformance_failed" in partial_full.rejection_reasons
    assert "authoritative_conformance_required" in partial_full.rejection_reasons

    full_evidence, full_report = _conformance(channel=EngineReleaseChannel.RELEASE_CANDIDATE)
    full = plan_nautilus_execution(
        authorization,
        runtime,
        full_evidence,
        full_report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert full.decision is EngineExecutionDecision.READY
    assert full.authoritative
    assert full.execution_scope is NautilusExecutionScope.FULL

    backtest_evidence, backtest_report = partial_evidence, partial_report
    backtest = plan_nautilus_execution(
        authorization,
        runtime,
        backtest_evidence,
        backtest_report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )
    assert backtest.decision is EngineExecutionDecision.READY
    assert backtest.authoritative

    foreign, foreign_report = _conformance(engine_id="other-engine")
    non_nautilus = plan_nautilus_execution(
        authorization,
        runtime,
        foreign,
        foreign_report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert non_nautilus.decision is EngineExecutionDecision.REJECT
    assert "only_nautilus_engine_is_supported" in non_nautilus.rejection_reasons


def test_backtest_authority_does_not_wait_for_forward_event_tape_parity() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    checks = NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks
    evidence, report = _conformance(
        channel=EngineReleaseChannel.STABLE,
        checks=checks,
    )

    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )

    assert report.compatible is False
    assert report.authoritative is False
    assert report.missing_checks == {ConformanceCheck.FORWARD_EVENT_TAPE_PARITY}
    assert result.decision is EngineExecutionDecision.READY
    assert result.authoritative is True
    assert result.execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE


def test_backtest_authority_still_requires_every_simulator_check() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    checks = NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks - {
        ConformanceCheck.NATIVE_ORDER_FILL_COST
    }
    evidence, report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=frozenset(checks),
    )

    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )

    assert result.decision is EngineExecutionDecision.REJECT
    assert result.authoritative is False
    assert "required_engine_conformance_failed" in result.rejection_reasons


def test_execution_gate_rejects_conformance_report_not_derived_from_evidence() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    checks = NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks
    evidence, report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=checks,
    )
    forged_report = replace(
        report,
        decision=ConformanceDecision.PASS,
        missing_checks=frozenset(),
        authoritative=False,
    )

    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        forged_report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )

    assert result.decision is EngineExecutionDecision.REJECT
    assert "conformance_evidence_report_mismatch" in result.rejection_reasons


def test_non_authoritative_compatible_run_can_be_ready_but_is_not_authoritative() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=False)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance(channel=EngineReleaseChannel.RELEASE_CANDIDATE)
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        requested_authoritative=False,
    )
    assert result.decision is EngineExecutionDecision.READY
    assert not result.authoritative


def test_rc_backtest_compatibility_scope_runs_without_forward_parity() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=False)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    checks = frozenset(
        {
            ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING,
            ConformanceCheck.NATIVE_ORDER_FILL_COST,
            ConformanceCheck.DETERMINISTIC_REPLAY,
            ConformanceCheck.ENGINE_LIFECYCLE,
        }
    )
    evidence, report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=checks,
    )

    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        requested_authoritative=False,
        execution_scope=NautilusExecutionScope.BACKTEST_COMPATIBILITY,
    )

    assert result.decision is EngineExecutionDecision.READY
    assert result.authoritative is False
    assert result.execution_scope is NautilusExecutionScope.BACKTEST_COMPATIBILITY


def test_rc_forward_scope_still_requires_forward_parity() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=False)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    checks = NautilusExecutionScope.BACKTEST_COMPATIBILITY.required_checks
    evidence, report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=checks,
    )

    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        requested_authoritative=False,
        execution_scope=NautilusExecutionScope.FORWARD_COMPATIBILITY,
    )

    assert result.decision is EngineExecutionDecision.REJECT
    assert "required_engine_conformance_failed" in result.rejection_reasons


def test_parsed_rc_receipt_can_feed_backtest_execution_scope() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime_preflight = _runtime()
    runtime = NautilusRcCompatibilityRuntime(
        source_digest=content_digest("nautilus-v2-rc5-source"),
        runtime_image_digest=content_digest("runtime-image"),
        python_version="3.12.11",
        rust_version="1.88.0",
    )
    probe = NautilusRuntimeProbeEvidence.from_mapping(
        {
            "engine_lifecycle": "passed",
            "implementation": "cpython",
            "nautilus_package_version": runtime.package_version,
            "platform": "Linux-x86_64",
            "python_version": runtime.python_version,
        },
        runtime,
    )
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
    receipt = NautilusRcFixtureReceipt.from_mapping(
        {
            "authoritative": False,
            "deterministic_replay": {"equal": True},
            "engine_lifecycle": "passed",
            "forward_event_tape_parity": "deferred_authoritative_fixture",
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
        },
        runtime,
    )
    conformance = resolve_nautilus_rc_conformance(
        runtime,
        probe,
        receipt,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        tested_at=NOW,
    )

    result = plan_nautilus_execution(
        authorization,
        runtime_preflight,
        conformance.evidence,
        conformance.report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        requested_authoritative=False,
        execution_scope=NautilusExecutionScope.BACKTEST_COMPATIBILITY,
    )

    assert result.decision is EngineExecutionDecision.READY
    assert result.execution_scope is NautilusExecutionScope.BACKTEST_COMPATIBILITY

    authoritative_backtest = plan_nautilus_execution(
        authorization,
        runtime_preflight,
        conformance.evidence,
        conformance.report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )

    assert conformance.report.authoritative is False
    assert authoritative_backtest.decision is EngineExecutionDecision.READY
    assert authoritative_backtest.authoritative is True
    assert authoritative_backtest.execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE


def test_compatible_evidence_without_an_isolated_pin_cannot_execute() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=False)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence = EngineConformanceEvidence(
        "nautilus",
        "2.0.0rc5",
        content_digest("engine-build"),
        EngineReleaseChannel.RELEASE_CANDIDATE,
        content_digest("fixture"),
        frozenset(ConformanceCheck),
        NOW,
    )
    report = evaluate_engine_conformance(evidence)
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        requested_authoritative=False,
    )
    assert result.decision is EngineExecutionDecision.REJECT
    assert "isolated_v2_release_pin_required" in result.rejection_reasons


def test_mismatched_runtime_or_failed_conformance_rejects_before_invocation() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance(checks=frozenset({ConformanceCheck.DETERMINISTIC_REPLAY}))
    mismatched_plan = SandboxCommandPlan(
        content_digest("different-request"), content_digest("profile"), ("docker", "run"), 10, 1024
    )
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        mismatched_plan,
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert result.decision is EngineExecutionDecision.REJECT
    assert "sandbox_runtime_request_mismatch" in result.rejection_reasons
    assert "engine_conformance_failed" in result.rejection_reasons


def test_engine_gate_rejects_forged_unhardened_sandbox_plan() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance()
    forged = SandboxCommandPlan(
        request.fingerprint,
        content_digest("profile"),
        ("docker", "run", "--rm"),
        10,
        1024,
    )
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        forged,
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert result.decision is EngineExecutionDecision.REJECT
    assert result.authoritative is False
    assert "sandbox_plan_not_hardened" in result.rejection_reasons


def test_engine_plan_rejects_invalid_inputs_and_authority_shape() -> None:
    request, runtime = _runtime()
    evidence, report = _conformance()
    with pytest.raises(TypeError, match="authorization"):
        plan_nautilus_execution(
            "bad",  # type: ignore[arg-type]
            runtime,
            evidence,
            report,
            _plan(request),
            data_snapshot_fingerprint=content_digest("snapshot"),
        )
    with pytest.raises(ValueError, match="data_snapshot_fingerprint"):
        trial, attempt, source, capability, lease = _execution_fixture()
        from app.strategy_lab_v2.execution import authorize_execution

        authorization = authorize_execution(
            trial, attempt, source, capability, lease, now=NOW.replace(second=3)
        )
        plan_nautilus_execution(
            authorization,
            runtime,
            evidence,
            report,
            _plan(request),
            data_snapshot_fingerprint="bad",
        )
