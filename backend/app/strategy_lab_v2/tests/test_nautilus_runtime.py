from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    NAUTILUS_V2_RC_WHEEL_SHA256,
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.nautilus_runtime import (
    NautilusRcCompatibilityRuntime,
    NautilusRcFixtureReceipt,
    NautilusRuntimeProbeEvidence,
)


def _runtime() -> NautilusRcCompatibilityRuntime:
    return NautilusRcCompatibilityRuntime(
        source_digest=content_digest("nautilus-v2-rc5-source"),
        runtime_image_digest=content_digest("nautilus-v2-rc5-image"),
        python_version="3.12.11",
        rust_version="1.88.0",
    )


def _native_fill_report(instrument_count: int = 1) -> dict[str, Any]:
    total_fee = Decimal("2.00") * instrument_count
    total_quantity = Decimal("1000") * instrument_count
    account_total = Decimal("100000.00") - (Decimal("1.10021") * total_quantity) - total_fee
    return {
        "account_total": str(account_total),
        "instrument_count": instrument_count,
        "total_orders": instrument_count,
        "total_positions": instrument_count,
        "orders_total": str(instrument_count),
        "positions_total": str(instrument_count),
        "native_reports": {
            "commission_total": str(total_fee),
            "commissions": ["2.00 USD"] * instrument_count,
            "expected_commission_per_fill": "2.00",
            "expected_quantity_per_instrument": "1000",
            "expected_quantity_total": str(total_quantity),
            "execution_prices": ["1.10021"] * instrument_count,
            "fee_currency": "USD",
            "fill_instrument_ids": [f"INSTRUMENT-{i}" for i in range(instrument_count)],
            "fill_quantities": ["1000"] * instrument_count,
            "filled_quantity": str(total_quantity),
            "fills_report_rows": instrument_count,
            "initial_account_total": "100000.00",
            "best_ask": "1.10020",
            "orders_report_rows": instrument_count,
            "price_increment": "0.00001",
            "total_fills": instrument_count,
        },
    }


def _fixture_payload() -> dict[str, Any]:
    native_order_run = _native_fill_report()
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
    return {
        "authoritative": False,
        "deterministic_replay": {"equal": True},
        "engine_lifecycle": "passed",
        "forward_event_tape_parity": "deferred_authoritative_fixture",
        "multi_instrument_accounting": _native_fill_report(2),
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


def test_rc_runtime_declaration_binds_exact_pin_and_non_authority() -> None:
    runtime = _runtime()

    assert runtime.package_version == NAUTILUS_V2_RC_PACKAGE_VERSION
    assert runtime.release_tag == NAUTILUS_V2_RC_RELEASE_TAG
    assert runtime.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE
    assert runtime.authoritative is False
    assert runtime.release_pin.package_version == runtime.package_version
    assert runtime.release_pin.wheel_digest == NAUTILUS_V2_RC_WHEEL_SHA256
    assert runtime.release_pin.fingerprint.startswith("sha256:")
    assert runtime.fingerprint.startswith("sha256:")


def test_complete_rc_conformance_can_qualify_a_pinned_build() -> None:
    runtime = _runtime()
    evidence = EngineConformanceEvidence(
        engine_id="nautilus",
        engine_version=runtime.package_version,
        build_digest=content_digest("nautilus-v2-rc5-build"),
        release_channel=runtime.release_channel,
        fixture_digest=content_digest("nautilus-v2-rc5-fixture"),
        passed_checks=frozenset(ConformanceCheck),
        tested_at=datetime(2026, 10, 2, tzinfo=UTC),
        release_pin=runtime.release_pin,
    )

    report = evaluate_engine_conformance(evidence)

    assert report.compatible
    assert report.execution_eligible
    assert report.authoritative


def test_rc_runtime_rejects_shared_legacy_environment() -> None:
    with pytest.raises(ValueError, match="isolated"):
        NautilusRcCompatibilityRuntime(
            source_digest=content_digest("nautilus-v2-rc5-source"),
            runtime_image_digest=content_digest("nautilus-v2-rc5-image"),
            python_version="3.12.11",
            rust_version="1.88.0",
            legacy_runtime_isolated=False,
        )


def test_rc_runtime_rejects_a_different_wheel_digest() -> None:
    with pytest.raises(ValueError, match="cannot be overridden"):
        NautilusRcCompatibilityRuntime(
            source_digest=content_digest("nautilus-v2-rc5-source"),
            runtime_image_digest=content_digest("nautilus-v2-rc5-image"),
            python_version="3.12.11",
            rust_version="1.88.0",
            wheel_digest=content_digest("different-wheel"),
        )


def test_probe_evidence_binds_exact_runtime_and_is_non_authoritative() -> None:
    runtime = _runtime()
    evidence = NautilusRuntimeProbeEvidence.from_mapping(
        {
            "engine_lifecycle": "passed",
            "implementation": "cpython",
            "nautilus_package_version": "2.0.0rc5",
            "platform": "Linux-x86_64",
            "python_version": "3.12.11",
        },
        runtime,
    )

    assert evidence.runtime_fingerprint == runtime.fingerprint
    assert evidence.runtime_image_digest == runtime.runtime_image_digest
    assert evidence.authoritative is False
    assert evidence.fingerprint == content_digest(evidence)


def test_probe_evidence_rejects_schema_version_and_runtime_mismatches() -> None:
    runtime = _runtime()
    payload = {
        "engine_lifecycle": "passed",
        "implementation": "cpython",
        "nautilus_package_version": "2.0.0rc5",
        "platform": "Linux-x86_64",
        "python_version": "3.12.11",
    }
    with pytest.raises(ValueError, match="exact runtime schema"):
        NautilusRuntimeProbeEvidence.from_mapping({**payload, "unexpected": "x"}, runtime)
    with pytest.raises(ValueError, match="package version"):
        NautilusRuntimeProbeEvidence.from_mapping(
            {**payload, "nautilus_package_version": "2.0.0rc4"}, runtime
        )
    with pytest.raises(ValueError, match="Python version"):
        NautilusRuntimeProbeEvidence.from_mapping({**payload, "python_version": "3.13.0"}, runtime)
    with pytest.raises(ValueError, match="lifecycle"):
        NautilusRuntimeProbeEvidence.from_mapping(
            {**payload, "engine_lifecycle": "failed"}, runtime
        )


def test_real_rc_fixture_receipt_preserves_deferred_forward_parity() -> None:
    runtime = _runtime()
    payload = _fixture_payload()

    receipt = NautilusRcFixtureReceipt.from_mapping(payload, runtime)

    assert receipt.runtime_fingerprint == runtime.fingerprint
    assert receipt.runtime_image_digest == runtime.runtime_image_digest
    assert receipt.fixture_digest == content_digest(payload)
    assert receipt.compatible
    assert receipt.authoritative is False
    assert receipt.deferred_checks == frozenset({ConformanceCheck.FORWARD_EVENT_TAPE_PARITY})


@pytest.mark.parametrize(
    ("mutations", "message"),
    [
        ({"execution_prices": ["1.10020"]}, "one-tick slippage"),
        ({"commissions": ["0.00 USD"]}, "fixed fee"),
        ({"filled_quantity": "999"}, "quantity does not reconcile"),
    ],
)
def test_real_rc_fixture_receipt_rejects_unproven_fill_cost_claims(
    mutations: dict[str, object], message: str
) -> None:
    runtime = _runtime()
    report = _native_fill_report()
    report["native_reports"] = {**report["native_reports"], **mutations}
    payload = _fixture_payload()
    payload["native_order_fill_cost"] = report

    with pytest.raises(ValueError, match=message):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_unreconciled_multi_instrument_accounting() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    multi_run = payload["multi_instrument_accounting"]
    multi_run["native_reports"]["fill_instrument_ids"] = ["SAME.SIM", "SAME.SIM"]

    with pytest.raises(ValueError, match="report rows do not reconcile"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_unreconciled_account_cash() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    payload["native_order_fill_cost"]["account_total"] = "98897.78 USD"

    with pytest.raises(ValueError, match="account report does not reconcile"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_unreconciled_target_allocation() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    target_probe = payload["native_order_fill_cost"]["target_allocation_probe"]
    target_probe["observed_deployment"] = "1000"

    with pytest.raises(ValueError, match="target allocation order and account state"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_unreconciled_raw_order_risk() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    payload["native_order_fill_cost"]["raw_order_risk_probe"]["estimated_signed_base_notional"] = (
        "10002"
    )

    with pytest.raises(ValueError, match="raw-order risk submission and account state"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_multi_component_netting_mismatch() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    multi_component = payload["portfolio_rebalance_schedule"]["multi_component_shared_account"]
    multi_component["total_positions"] = 2

    with pytest.raises(ValueError, match="multi_component_shared_account schedule callbacks"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_component_attribution_drift() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    priority_case = payload["portfolio_rebalance_schedule"]["component_priority_contention"]
    priority_case["component_order_tag"] = "strategy-lab-v2:component:core"

    with pytest.raises(ValueError, match="priority selection or component attribution"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_component_fill_attribution_drift() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    fill = payload["portfolio_rebalance_schedule"]["component_priority_contention"][
        "component_fill_attribution"
    ]
    fill["component_id"] = "core"

    with pytest.raises(ValueError, match="native component fill attribution does not reconcile"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)


def test_real_rc_fixture_receipt_rejects_false_authority_or_parity_claim() -> None:
    runtime = _runtime()
    payload = _fixture_payload()
    payload["authoritative"] = True
    payload["forward_event_tape_parity"] = "passed"

    with pytest.raises(ValueError, match="cannot be authoritative"):
        NautilusRcFixtureReceipt.from_mapping(payload, runtime)
