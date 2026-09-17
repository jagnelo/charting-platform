from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.resource_domains import normalize_resource_attributes

SOURCE_DIGEST = content_digest("strategy-source")
ARTIFACT_DIGEST = content_digest("dependency-wheel")


def _attributes() -> dict:
    return {
        "strategy_id": "momentum",
        "version_id": "2026-09-17",
        "sdk_version": "strategy-sdk.v2",
        "source_digest": SOURCE_DIGEST,
        "dependencies": [
            {
                "distribution": "numpy",
                "version": "2.0.0",
                "artifact_digest": ARTIFACT_DIGEST,
            }
        ],
        "parameter_schema": {"lookback": {"type": "integer"}},
        "default_parameters": {"lookback": 20},
    }


def test_strategy_attributes_are_normalized_and_domain_fingerprinted() -> None:
    result = normalize_resource_attributes(ApiResourceType.STRATEGY, _attributes())

    assert result.domain_fingerprint is not None
    assert result.attributes["strategy_id"] == "momentum"
    assert result.attributes["dependencies"][0]["distribution"] == "numpy"
    assert result.attributes["dependencies"][0]["version"] == "2.0.0"
    assert result.attributes["parameter_schema"]["lookback"]["type"] == "integer"

    reordered = _attributes()
    reordered["dependencies"] = list(reversed(reordered["dependencies"]))
    assert normalize_resource_attributes(ApiResourceType.STRATEGY, reordered) == result


def test_strategy_resource_id_aliases_must_agree() -> None:
    attributes = _attributes()
    attributes.update({"id": "one", "resource_id": "two"})

    try:
        normalize_resource_attributes(ApiResourceType.STRATEGY, attributes)
    except ValueError as error:
        assert "must agree" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("conflicting strategy resource IDs should be rejected")


def test_strategy_rejects_unknown_or_invalid_dependency_fields() -> None:
    unknown = _attributes()
    unknown["network"] = True
    try:
        normalize_resource_attributes(ApiResourceType.STRATEGY, unknown)
    except ValueError as error:
        assert "unsupported fields" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("unknown strategy fields should be rejected")

    malformed = _attributes()
    malformed["dependencies"] = [{"distribution": "numpy"}]
    try:
        normalize_resource_attributes(ApiResourceType.STRATEGY, malformed)
    except ValueError as error:
        assert "distribution" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("malformed strategy dependencies should be rejected")


def test_non_domain_resources_remain_frozen_until_their_domain_adapter_exists() -> None:
    attributes = {"name": "artifact", "nested": {"values": [1, 2]}}

    result = normalize_resource_attributes(ApiResourceType.ARTIFACT, attributes)

    assert result.domain_fingerprint is None
    assert result.attributes["nested"]["values"] == (1, 2)


def test_package_attributes_are_normalized_and_domain_fingerprinted() -> None:
    attributes = {
        "package_id": "momentum-package",
        "strategy_fingerprint": content_digest("strategy-version"),
        "package_format": "source_archive",
        "archive_digest": content_digest("strategy-archive"),
        "manifest_digest": content_digest("strategy-manifest"),
        "dependency_lock_digest": content_digest("dependency-lock"),
        "archive_byte_length": 128,
        "entrypoint": "strategy.main:run",
        "sdk_version": "strategy-sdk.v2",
        "runtime_abi": "python3.12-linux-arm64",
    }

    result = normalize_resource_attributes(ApiResourceType.PACKAGE, attributes)

    assert result.domain_fingerprint is not None
    assert result.attributes["package_format"] == "source_archive"
    assert result.attributes["archive_byte_length"] == 128


def test_package_rejects_unknown_fields_and_invalid_runtime_identity() -> None:
    unknown = {
        "package_id": "pkg",
        "unexpected": True,
    }
    try:
        normalize_resource_attributes(ApiResourceType.PACKAGE, unknown)
    except ValueError as error:
        assert "unsupported fields" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("unknown package fields should be rejected")

    invalid = {
        "package_id": "pkg",
        "strategy_fingerprint": "sha256:bad",
        "package_format": "wheel",
        "archive_digest": ARTIFACT_DIGEST,
        "manifest_digest": ARTIFACT_DIGEST,
        "dependency_lock_digest": ARTIFACT_DIGEST,
        "archive_byte_length": 0,
        "entrypoint": "not-an-entrypoint",
        "sdk_version": "sdk",
        "runtime_abi": "abi",
    }
    try:
        normalize_resource_attributes(ApiResourceType.PACKAGE, invalid)
    except ValueError as error:
        assert "invalid" in str(error) or "digest" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("invalid package identity should be rejected")


def test_portfolio_attributes_are_normalized_with_risk_and_rebalance_contracts() -> None:
    attributes = {
        "portfolio_id": "balanced",
        "version_id": "v1",
        "initial_capital": "100000.00",
        "base_currency": "usd",
        "components": [
            {
                "component_id": "momentum",
                "strategy_fingerprint": content_digest("momentum-strategy"),
                "instrument_ids": ["US.AAPL", "US.MSFT"],
                "capital_weight": "0.60",
                "priority": 2,
            },
            {
                "component_id": "defensive",
                "strategy_fingerprint": content_digest("defensive-strategy"),
                "instrument_ids": ["US.TLT"],
                "capital_weight": "0.40",
            },
        ],
        "rebalance_policy": {
            "calendar_id": "nyse",
            "calendar_fingerprint": content_digest("nyse-calendar"),
            "cadence": "monthly",
            "trigger": "session_close_after_events",
            "selection": "last_session",
            "misfire_policy": "fail_run",
        },
        "shared_risk_policy": {
            "max_gross_exposure_fraction": "1.25",
            "max_net_exposure_fraction": "0.80",
            "max_component_leverage": "1.25",
            "allow_short_positions": False,
            "target_conflict_policy": "reject",
            "risk_models": [
                {
                    "product_class": "equity",
                    "exposure_measure": "signed_base_notional",
                    "definition_digest": content_digest("equity-risk"),
                }
            ],
        },
    }

    result = normalize_resource_attributes(ApiResourceType.PORTFOLIO, attributes)

    assert result.domain_fingerprint is not None
    assert result.attributes["base_currency"] == "USD"
    assert result.attributes["initial_capital"] == Decimal("100000.00")
    assert result.attributes["components"][0]["capital_weight"] == Decimal("0.60")
    assert result.attributes["rebalance_policy"]["cadence"] == "monthly"
    assert result.attributes["shared_risk_policy"]["risk_models"][0]["product_class"] == "equity"


def test_portfolio_rejects_unknown_fields_and_overweight_components() -> None:
    attributes = {
        "portfolio_id": "balanced",
        "version_id": "v1",
        "initial_capital": "1000",
        "base_currency": "USD",
        "components": [
            {
                "component_id": "one",
                "strategy_fingerprint": content_digest("one"),
                "instrument_ids": ["US.AAPL"],
                "capital_weight": "0.75",
            },
            {
                "component_id": "two",
                "strategy_fingerprint": content_digest("two"),
                "instrument_ids": ["US.MSFT"],
                "capital_weight": "0.50",
            },
        ],
    }

    with pytest.raises(ValueError, match="must not exceed one"):
        normalize_resource_attributes(ApiResourceType.PORTFOLIO, attributes)

    unknown: dict[str, Any] = dict(attributes)
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        normalize_resource_attributes(ApiResourceType.PORTFOLIO, unknown)


def test_experiment_attributes_are_normalized_and_strategy_order_is_canonical() -> None:
    first = content_digest("strategy-one")
    second = content_digest("strategy-two")
    attributes = {
        "experiment_id": "momentum-search",
        "portfolio_fingerprint": content_digest("portfolio-v1"),
        "strategy_fingerprints": [second, first],
        "snapshot_fingerprint": content_digest("snapshot-v1"),
        "capability_contract_digest": content_digest("capability-v1"),
        "seed": 42,
        "metric_definition_version": "strategy-lab.metrics.v1",
        "engine_contract": {"engine": "nautilus", "version": "v2"},
    }

    result = normalize_resource_attributes(ApiResourceType.EXPERIMENT, attributes)

    assert result.domain_fingerprint is not None
    assert result.attributes["strategy_fingerprints"] == tuple(sorted((first, second)))
    assert result.attributes["seed"] == 42
    assert result.attributes["engine_contract"]["version"] == "v2"


def test_experiment_rejects_non_integer_seed_and_unknown_fields() -> None:
    attributes = {
        "experiment_id": "search",
        "portfolio_fingerprint": content_digest("portfolio"),
        "strategy_fingerprints": [content_digest("strategy")],
        "snapshot_fingerprint": content_digest("snapshot"),
        "capability_contract_digest": content_digest("capability"),
        "seed": "42",
        "metric_definition_version": "metrics.v1",
    }

    with pytest.raises(ValueError, match="seed must be an integer"):
        normalize_resource_attributes(ApiResourceType.EXPERIMENT, attributes)

    unknown: dict[str, Any] = dict(attributes)
    unknown["unexpected"] = True
    unknown["seed"] = 42
    with pytest.raises(ValueError, match="unsupported fields"):
        normalize_resource_attributes(ApiResourceType.EXPERIMENT, unknown)


def test_attempt_attributes_are_normalized_with_utc_lifecycle_timestamps() -> None:
    created_at = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    result = normalize_resource_attributes(
        ApiResourceType.ATTEMPT,
        {
            "attempt_id": content_digest("attempt-1"),
            "trial_id": content_digest("trial-1"),
            "ordinal": 1,
            "state": "queued",
            "created_at": "2026-09-17T12:00:00Z",
            "updated_at": created_at,
            "resource_id": "attempt-1",
        },
    )

    assert result.domain_fingerprint is not None
    assert result.attributes["state"] == "queued"
    assert result.attributes["created_at"] == created_at
    assert result.attributes["updated_at"] == created_at
    assert result.attributes["resource_id"] == "attempt-1"


def test_attempt_rejects_naive_timestamps_and_invalid_state() -> None:
    attributes = {
        "attempt_id": content_digest("attempt-1"),
        "trial_id": content_digest("trial-1"),
        "ordinal": 1,
        "state": "not-a-state",
        "created_at": "2026-09-17T12:00:00",
    }

    with pytest.raises(ValueError, match="invalid"):
        normalize_resource_attributes(ApiResourceType.ATTEMPT, attributes)

    attributes["state"] = "queued"
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_resource_attributes(ApiResourceType.ATTEMPT, attributes)


def _preflight_payload() -> dict:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 1, tzinfo=UTC)
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=start,
        end=end,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash-equity",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close"}),
        account_models=frozenset({"cash-equity"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=start,
        history_end=end,
        evidence_digest=content_digest("capability-evidence"),
    )
    return asdict(preflight_capabilities((requirement,), (cell,)))


def test_snapshot_attributes_rehydrate_preflight_and_series_contracts() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 1, tzinfo=UTC)
    result = normalize_resource_attributes(
        ApiResourceType.SNAPSHOT,
        {
            "snapshot_id": "snapshot-v1",
            "provider_snapshot_id": "provider-v1",
            "preflight_report": _preflight_payload(),
            "series": [
                {
                    "instrument_id": "US.AAPL",
                    "event_type": "ohlcv",
                    "event_granularity": "bar",
                    "timeframe": "1d",
                    "session": "regular",
                    "feed": "consolidated",
                    "start": start,
                    "end": end,
                    "adjustment": "split_adjusted",
                    "corporate_action_semantics": "split-adjusted-v1",
                    "coverage_evidence_digest": content_digest("coverage"),
                    "content_digest": content_digest("series"),
                    "row_count": 500,
                }
            ],
            "created_at": "2026-09-17T12:00:00Z",
            "resource_id": "snapshot-1",
        },
    )

    assert result.domain_fingerprint is not None
    assert result.attributes["snapshot_id"] == "snapshot-v1"
    assert result.attributes["preflight_report"]["fingerprint"] == _preflight_payload()[
        "fingerprint"
    ]
    assert result.attributes["series"][0]["adjustment"] == "split_adjusted"
    assert result.attributes["created_at"] == datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def test_snapshot_rejects_tampered_preflight_or_series_fields() -> None:
    preflight = _preflight_payload()
    preflight["fingerprint"] = content_digest("tampered")
    base = {
        "snapshot_id": "snapshot-v1",
        "provider_snapshot_id": "provider-v1",
        "preflight_report": preflight,
        "series": [],
        "created_at": "2026-09-17T12:00:00Z",
    }
    with pytest.raises(ValueError, match="fingerprint"):
        normalize_resource_attributes(ApiResourceType.SNAPSHOT, base)

    unknown: dict[str, Any] = dict(base)
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        normalize_resource_attributes(ApiResourceType.SNAPSHOT, unknown)


def test_trial_attributes_generate_and_bind_reproducible_trial_identity() -> None:
    result = normalize_resource_attributes(
        ApiResourceType.TRIAL,
        {
            "experiment_fingerprint": content_digest("experiment-v1"),
            "snapshot_fingerprint": content_digest("snapshot-v1"),
            "preflight_report": _preflight_payload(),
            "parameter_set": {"lookback": 20, "threshold": "0.03"},
            "scenario": {"slippage_bps": 2},
            "seed": 19,
            "evaluation_window": {
                "start": "2021-01-01T00:00:00Z",
                "end": "2021-12-31T00:00:00Z",
                "purpose": "out_of_sample",
                "warmup_start": "2020-12-01T00:00:00Z",
            },
            "resource_id": "trial-1",
        },
    )

    assert result.domain_fingerprint == result.attributes["trial_id"]
    assert result.attributes["randomization"]["policy"] == "per_candidate"
    assert result.attributes["evaluation_window"]["purpose"] == "out_of_sample"
    assert result.attributes["parameter_set"]["lookback"] == 20


def test_trial_rejects_mismatched_identity_and_invalid_randomization() -> None:
    attributes = {
        "trial_id": content_digest("not-the-derived-id"),
        "experiment_fingerprint": content_digest("experiment-v1"),
        "snapshot_fingerprint": content_digest("snapshot-v1"),
        "preflight_report": _preflight_payload(),
        "parameter_set": {},
        "scenario": {},
        "seed": 19,
    }

    with pytest.raises(ValueError, match="trial_id"):
        normalize_resource_attributes(ApiResourceType.TRIAL, attributes)

    attributes.pop("trial_id")
    attributes["randomization"] = {"policy": "not-a-policy"}
    with pytest.raises(ValueError, match="required|invalid"):
        normalize_resource_attributes(ApiResourceType.TRIAL, attributes)


def test_metric_set_attributes_are_normalized_with_calculation_and_evidence() -> None:
    definition_version = "strategy-lab.metrics.v1"
    result = normalize_resource_attributes(
        ApiResourceType.METRIC_SET,
        {
            "metric_set_id": "metric-set-1",
            "trial_id": content_digest("trial-1"),
            "attempt_id": content_digest("attempt-1"),
            "definition_version": definition_version,
            "values": [
                {
                    "name": "annual_return",
                    "value": "0.1234",
                    "unit": "fraction",
                    "definition_version": definition_version,
                    "basis": "net",
                    "sample_size": 252,
                    "annualization_basis": "trading_sessions_252",
                    "calculation_basis": "equity_curve",
                    "calculation_definition": {
                        "formula_id": "annualized-return",
                        "contract_version": "metrics-formula.v1",
                        "parameters": {"sessions_per_year": 252},
                    },
                    "evidence_references": [
                        {"role": "equity-curve", "digest": content_digest("equity-curve")}
                    ],
                },
                {
                    "name": "sortino",
                    "value": None,
                    "unit": "ratio",
                    "definition_version": definition_version,
                    "basis": "net",
                    "sample_size": 0,
                    "null_reason": "insufficient downside observations",
                },
            ],
            "created_at": "2026-09-17T12:00:00Z",
            "resource_id": "metric-set-1",
        },
    )

    assert result.domain_fingerprint is not None
    assert result.attributes["values"][0]["name"] == "annual_return"
    assert result.attributes["values"][0]["value"] == Decimal("0.1234")
    assert result.attributes["values"][0]["calculation_definition"]["formula_id"] == (
        "annualized-return"
    )
    assert result.attributes["values"][1]["null_reason"] == "insufficient downside observations"


def test_metric_set_rejects_null_values_without_reasons_or_unknown_fields() -> None:
    attributes: dict[str, Any] = {
        "metric_set_id": "metric-set-1",
        "trial_id": content_digest("trial-1"),
        "attempt_id": content_digest("attempt-1"),
        "definition_version": "metrics.v1",
        "values": [
            {
                "name": "sharpe",
                "value": None,
                "unit": "ratio",
                "definition_version": "metrics.v1",
                "basis": "net",
                "sample_size": 0,
            }
        ],
        "created_at": "2026-09-17T12:00:00Z",
    }
    with pytest.raises(ValueError, match="null_reason"):
        normalize_resource_attributes(ApiResourceType.METRIC_SET, attributes)

    attributes["values"][0]["null_reason"] = "not enough data"
    unknown: dict[str, Any] = dict(attributes)
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        normalize_resource_attributes(ApiResourceType.METRIC_SET, unknown)


def test_forward_instance_attributes_are_normalized_as_typed_state() -> None:
    result = normalize_resource_attributes(
        ApiResourceType.FORWARD_INSTANCE,
        {
            "instance_id": "forward-1",
            "portfolio_fingerprint": content_digest("portfolio-v1"),
            "warmup_snapshot_fingerprint": content_digest("snapshot-v1"),
            "carry_in_mode": "synthetic_historical",
            "state": "active",
            "last_event_id": "event-42",
            "last_event_sequence": 42,
            "correction_count": 2,
            "created_at": "2026-09-17T12:00:00+01:00",
            "updated_at": "2026-09-17T12:30:00+01:00",
            "resource_id": "forward-1",
            "id": "forward-1",
        },
    )

    assert result.domain_fingerprint is not None
    assert result.attributes["carry_in_mode"] == "synthetic_historical"
    assert result.attributes["state"] == "active"
    assert result.attributes["last_event_sequence"] == 42
    assert result.attributes["created_at"].isoformat() == "2026-09-17T11:00:00+00:00"


def test_forward_instance_rejects_invalid_progress_and_identity_fields() -> None:
    attributes: dict[str, Any] = {
        "instance_id": "forward-1",
        "portfolio_fingerprint": content_digest("portfolio-v1"),
        "warmup_snapshot_fingerprint": content_digest("snapshot-v1"),
        "carry_in_mode": "flat",
        "state": "created",
        "last_event_id": None,
        "last_event_sequence": 1,
        "correction_count": 0,
        "created_at": "2026-09-17T12:00:00Z",
        "updated_at": "2026-09-17T12:00:00Z",
    }
    with pytest.raises(ValueError, match="last_event_id"):
        normalize_resource_attributes(ApiResourceType.FORWARD_INSTANCE, attributes)

    attributes["last_event_sequence"] = 0
    attributes["state"] = "not-a-state"
    with pytest.raises(ValueError, match="forward_instance attributes are invalid"):
        normalize_resource_attributes(ApiResourceType.FORWARD_INSTANCE, attributes)

    attributes["state"] = "created"
    attributes["resource_id"] = "forward-1"
    attributes["id"] = "different-id"
    with pytest.raises(ValueError, match="must agree"):
        normalize_resource_attributes(ApiResourceType.FORWARD_INSTANCE, attributes)
