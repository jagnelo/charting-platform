from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


def _runner_module():
    path = Path(__file__).parents[3] / "scripts" / "run-live-provider-probes.py"
    spec = importlib.util.spec_from_file_location("run_live_provider_probes_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _live_provider_test_module():
    path = Path(__file__).parents[1] / "live" / "test_market_data_providers_live.py"
    spec = importlib.util.spec_from_file_location("live_market_data_tests_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tokenized_provider_test_module():
    path = Path(__file__).parents[1] / "live" / "test_tokenized_providers_live.py"
    spec = importlib.util.spec_from_file_location("live_tokenized_provider_tests_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finra_otc_complete_snapshot_has_case_scoped_live_operation_mapping():
    runner = _runner_module()

    assert runner.LIVE_CASE_OPERATIONS["finra_otc_directory"][
        "test_finra_otc_directory_credentialed_source"
    ] == {"discover_universe_page"}


def test_fmp_account_usage_bootstrap_is_in_full_live_manifest():
    runner = _runner_module()

    case = "test_fmp_credentialed_account_usage_snapshot"
    assert runner.LIVE_CASE_OPERATIONS["fmp"][case] == {"fetch_account_usage"}
    assert "fetch_account_usage" in runner.LIVE_REQUIRED_OPERATIONS["fmp"]
    assert "discover_universe_page" not in runner.LIVE_REQUIRED_OPERATIONS["fmp"]
    assert (
        "expected_entitlement_denial"
        in runner.LIVE_OPERATION_DISPOSITIONS["fmp"]["discover_universe_page"]
    )
    assert runner.live_matrix_inventory_errors() == []


@pytest.mark.parametrize(("value", "expected"), [("0", 0), ("12", 12)])
def test_live_http_transport_limit_parser_accepts_non_negative_decimal(value, expected):
    runner = _runner_module()
    assert runner._non_negative_integer(value) == expected


@pytest.mark.parametrize("value", ["", "-1", "+1", "1.0", " 2", "２"])
def test_live_http_transport_limit_parser_rejects_invalid_values(value):
    import argparse

    runner = _runner_module()
    with pytest.raises(argparse.ArgumentTypeError, match="non-negative base-10 integer"):
        runner._non_negative_integer(value)


def test_live_http_transport_counter_file_is_private_and_starts_at_zero(tmp_path):
    runner = _runner_module()
    counter = tmp_path / "run-counter"

    runner._create_transport_budget_file(counter)

    assert counter.read_text(encoding="ascii") == "0"
    assert counter.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        runner._create_transport_budget_file(counter)


def test_finra_short_interest_and_daily_list_have_case_scoped_operations():
    runner = _runner_module()

    assert runner.LIVE_CASE_OPERATIONS["finra"] == {
        "test_finra_credentialed_short_interest": {"fetch_short_interest"},
        "test_finra_credentialed_otc_daily_list": {"fetch_market_events"},
    }


def test_binance_history_case_inventory_includes_every_usage_refresh_transport():
    runner = _runner_module()
    cases_and_refresh_counts = {
        "test_binance_keyless_crypto_history": 3,
        "test_binance_keyless_bounded_daily_history": 1,
    }

    for case_name, refresh_count in cases_and_refresh_counts.items():
        assert runner.LIVE_CASE_OPERATIONS["binance"][case_name] == {
            "fetch_account_usage",
            *(
                {"fetch_latest_ohlcv", "get_current_price", "discover_universe_page"}
                if case_name == "test_binance_keyless_crypto_history"
                else {"fetch_ohlcv"}
            ),
        }
        assert (
            runner.LIVE_CASE_OPERATION_MULTIPLIERS["binance"][case_name]["fetch_account_usage"]
            == refresh_count
        )

        selected, transport_operations = runner.parse_live_case_selectors(
            [f"binance:{case_name}"], {"binance"}
        )
        assert transport_operations["binance"] == runner.LIVE_CASE_OPERATIONS["binance"][case_name]
        assert (
            runner.selected_case_operation_multipliers(selected)["binance"]["fetch_account_usage"]
            == refresh_count
        )

    # Provider/full-matrix mode also sees the implicit requests in addition to
    # the dedicated one-request account-usage snapshot case.
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["binance"]["fetch_account_usage"] == 5
    assert runner.live_matrix_inventory_errors() == []


def test_eodhd_compound_small_read_accounts_for_every_operation_and_repeat():
    runner = _runner_module()

    case = "test_optional_credentialed_provider_small_read"
    assert runner.LIVE_CASE_OPERATIONS["eodhd"][case] == {
        "fetch_ohlcv",
        "get_current_price",
        "discover_universe_page",
    }
    assert runner.LIVE_CASE_OPERATION_MULTIPLIERS["eodhd"][case] == {
        "fetch_ohlcv": 3,
    }
    cases, operations = runner.parse_live_case_selectors([f"eodhd:{case}"], {"eodhd"})
    assert operations == {"eodhd": {"fetch_ohlcv", "get_current_price", "discover_universe_page"}}
    assert runner.selected_case_operation_multipliers(cases) == {
        "eodhd": {"fetch_ohlcv": 3, "get_current_price": 1, "discover_universe_page": 1}
    }


def test_finnhub_expected_denial_is_preflighted_without_becoming_capability_evidence(
    monkeypatch,
):
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    case = "test_finnhub_credentialed_company_profile"
    selector = f"finnhub:{case}"

    assert "fetch_ohlcv" not in runner.LIVE_CASE_OPERATIONS["finnhub"][case]
    assert "fetch_ohlcv" not in runner.LIVE_REQUIRED_OPERATIONS["finnhub"]
    assert (
        "expected_entitlement_denial"
        in runner.LIVE_OPERATION_DISPOSITIONS["finnhub"]["fetch_ohlcv"]
    )
    assert runner.LIVE_CASE_TRANSPORT_ADDITIONS["finnhub"][case] == {"fetch_ohlcv"}

    selected, transport_operations = runner.parse_live_case_selectors([selector], {"finnhub"})
    assert transport_operations["finnhub"] == {
        *runner.LIVE_CASE_OPERATIONS["finnhub"][case],
        "fetch_ohlcv",
    }
    transport_counts = runner.selected_case_operation_multipliers(selected)
    assert transport_counts["finnhub"]["fetch_ohlcv"] == 1
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["finnhub"]["fetch_ohlcv"] == 1

    preflighted: list[str] = []

    def reservation_plan(
        provider_name,
        operation,
        usage_identity,
        now,
        operation_cost_override=None,
        dimension_cost_overrides=None,
    ):
        assert provider_name == "finnhub"
        preflighted.append(operation)
        return "rolling", {}, []

    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        reservation_plan,
    )

    assert (
        runner.live_operation_quota_preflight(
            {"finnhub"},
            operations_override=transport_operations,
            operation_multipliers=transport_counts,
        )
        == {}
    )
    assert set(preflighted) == transport_operations["finnhub"]


def test_full_matrix_cost_counts_are_derived_from_every_manifest_case():
    runner = _runner_module()

    assert runner.live_matrix_inventory_errors() == []
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["alpha_vantage"]["fetch_ohlcv"] == 3
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["eodhd"]["fetch_ohlcv"] == 3
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["twelve_data"]["fetch_ohlcv"] == 2
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["alpaca"]["get_instrument_profile"] == 2
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["coinbase"]["fetch_ohlcv"] == 2
    assert runner.LIVE_MATRIX_OPERATION_MULTIPLIERS["marketdata_app"]["fetch_option_chain"] == 2


def test_provider_quota_preflight_sums_shared_pool_costs_and_repeats(monkeypatch):
    from app import config
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "LIVE_REQUIRED_OPERATIONS",
        {"demo": {"fetch_ohlcv", "get_current_price"}},
    )
    monkeypatch.setattr(runner, "LIVE_MATRIX_OPERATION_MULTIPLIERS", {"demo": {"fetch_ohlcv": 3}})
    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "api_key",
            "quota_contract": {
                "reset": "calendar_day_utc",
                "dimensions": [
                    {
                        "name": "requests_per_day",
                        "limit": 20,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "shared-demo-pool",
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        lambda _provider, _operation, **_kwargs: (
            "calendar_day_utc",
            {"requests_per_day": 2},
            [
                {
                    "account_scope": "demo-key",
                    "quota_group": "shared-demo-pool",
                    "dimension": "requests_per_day",
                    "window_started_at": "2026-10-09T00:00:00+00:00",
                    "window_seconds": 86400,
                    "reset": "calendar_day_utc",
                    "unit": "requests",
                    "units": 2,
                    "release_only": False,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "provider_quota_baseline_status",
        lambda **_kwargs: {"status": "verified", "remaining_units": 7},
    )

    blockers = runner.live_operation_quota_preflight({"demo"})

    assert blockers == {
        "demo": [
            "demo/fetch_ohlcv: active requests_per_day headroom is below the combined live-matrix reservation (8 units)"
        ]
    }


def test_full_matrix_partitions_provider_local_admission_blockers():
    runner = _runner_module()

    eligible, blocked, global_blockers = runner.partition_live_provider_admission(
        {"alpaca", "eodhd", "dinari", "tiingo"},
        missing={"dinari": ["DINARI_API_KEY_ID"]},
        quota_blockers={"eodhd": ["daily headroom exhausted"]},
        safety_blockers={"tiingo": ["operation byte bounds missing"]},
        unresolved_operations=["dinari/fetch_tokenized_news: no live case"],
    )

    assert eligible == {"alpaca"}
    assert set(blocked) == {"eodhd", "dinari", "tiingo"}
    assert global_blockers == []


def test_full_matrix_global_admission_failure_stops_every_provider():
    runner = _runner_module()

    eligible, blocked, global_blockers = runner.partition_live_provider_admission(
        {"alpaca", "eodhd"},
        missing={"usage accounting": ["PROVIDER_LIVE_USAGE_SCOPE"]},
        quota_blockers={},
        safety_blockers={},
        unresolved_operations=[],
    )

    assert eligible == {"alpaca", "eodhd"}
    assert blocked == {}
    assert global_blockers == ["usage accounting: PROVIDER_LIVE_USAGE_SCOPE"]


def test_empty_provider_subset_is_not_misreported_as_full_matrix(tmp_path, monkeypatch):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_source_sha", lambda: "c" * 40)
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"demo": ()})

    assert runner.selected_live_test_arguments([]) == []
    result = runner._record_live_validation(
        providers=[],
        exit_code=2,
        missing={"demo": ["quota baseline is unknown"]},
        counts={
            "case_count": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "skipped_cases": 0,
        },
        approved_deferrals={},
        full_matrix_requested=True,
        requested_providers=["demo"],
        quarantined_providers=["demo"],
    )

    receipt = json.loads(validation_path.read_text().splitlines()[-1])
    assert result == "incomplete_preflight"
    assert receipt["scope"] == "full_matrix"
    assert receipt["providers_selected"] == ["demo"]
    assert receipt["providers_run"] == []
    assert receipt["providers_quarantined"] == ["demo"]


def test_full_matrix_preflight_receipt_records_admission_partition(tmp_path, monkeypatch):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_source_sha", lambda: "d" * 40)

    runner._record_live_preflight(
        providers=None,
        selected={"ready", "blocked"},
        blockers={"blocked": ["quota baseline is unknown"]},
        approved_deferrals={},
        quota_coordinator_ready=True,
        admitted_providers=["ready"],
        quarantined_providers={"blocked": ["quota baseline is unknown"]},
        global_admission_blockers=[],
    )

    receipt = json.loads(validation_path.read_text().splitlines()[-1])
    assert receipt["scope"] == "full_matrix"
    assert receipt["providers_requested"] == ["blocked", "ready"]
    assert receipt["provider_admission"] == {
        "eligible": ["ready"],
        "quarantined": {"blocked": ["quota baseline is unknown"]},
        "global_blockers": [],
    }
    assert receipt["live_acceptance"] is False
    assert receipt["provider_http_requests"] == 0


def test_default_matrix_batches_provider_native_usage_with_its_data_cases():
    runner = _runner_module()

    assert runner.live_test_provider_batches(
        ["alpaca", "openfigi"], isolate_provider_quota_windows=True
    ) == [["alpaca"], ["openfigi"]]
    assert runner.live_test_provider_batches(None, isolate_provider_quota_windows=False) == [None]


def test_eodhd_bounded_history_case_has_exact_case_scoped_operation():
    runner = _runner_module()

    selected, operations = runner.parse_live_case_selectors(
        ["eodhd:test_optional_credentialed_provider_small_read"], {"eodhd"}
    )

    assert selected == {"eodhd": {"test_optional_credentialed_provider_small_read"}}
    assert operations == {"eodhd": {"fetch_ohlcv", "get_current_price", "discover_universe_page"}}


def test_live_matrix_collection_orders_native_usage_before_metered_cases(monkeypatch):
    """Fixed-window providers bootstrap current usage before data operations."""

    path = Path(__file__).parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location(
        "charting_platform_tests_conftest_under_test", path
    )
    assert spec and spec.loader
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)

    items = [
        SimpleNamespace(nodeid="tests/live/test_provider.py::test_crypto_history"),
        SimpleNamespace(
            nodeid="tests/live/test_provider.py::test_credentialed_account_usage_snapshot"
        ),
    ]
    monkeypatch.setenv("PROVIDER_LIVE_MATRIX_RUN", "1")

    conftest.pytest_collection_modifyitems(None, items)

    assert items[0].nodeid.endswith("account_usage_snapshot")
    assert items[1].nodeid.endswith("crypto_history")


def test_live_matrix_collection_preserves_manifest_order_after_usage_bootstrap(monkeypatch):
    """Exhaustive pagination must not run before a provider's smaller probes."""

    path = Path(__file__).parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location(
        "charting_platform_tests_conftest_order_under_test", path
    )
    assert spec and spec.loader
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)

    reference = "tests/live/test_provider.py::test_reference"
    exhaustive = "tests/live/test_provider.py::test_full_universe"
    account_usage = "tests/live/test_provider.py::test_account_usage_snapshot"
    items = [
        SimpleNamespace(nodeid=reference),
        SimpleNamespace(nodeid=exhaustive),
        SimpleNamespace(nodeid=account_usage),
    ]
    monkeypatch.setenv("PROVIDER_LIVE_MATRIX_RUN", "1")
    monkeypatch.setenv("PROVIDER_LIVE_CASE_ORDER", json.dumps([reference, exhaustive]))

    conftest.pytest_collection_modifyitems(None, items)

    assert [item.nodeid for item in items] == [account_usage, reference, exhaustive]


def test_binance_live_probe_refreshes_native_usage_after_fixed_window_rollover(monkeypatch):
    live_tests = _live_provider_test_module()
    now = {"value": datetime(2026, 10, 4, 2, 30, tzinfo=UTC)}
    observed: list[tuple[str, str]] = []
    next_reset = {"value": now["value"] + timedelta(minutes=1)}

    monkeypatch.setattr(
        live_tests,
        "datetime",
        SimpleNamespace(now=lambda _timezone: now["value"]),
    )

    def observed_read(_call, provider, operation):
        observed.append((provider, operation))
        usage = SimpleNamespace(provider="binance", reset_at=next_reset["value"])
        return usage, SimpleNamespace(http_requests=1)

    monkeypatch.setattr(live_tests, "_observed_read", observed_read)
    monkeypatch.setattr(
        live_tests,
        "reconcile_native_account_usage",
        lambda _provider, _usage: [{"status": "reconciled"}],
    )
    monkeypatch.setattr(
        live_tests,
        "_BINANCE_LIVE_USAGE_RESET_AT",
        now["value"] + timedelta(seconds=10),
    )

    live_tests._ensure_binance_live_usage_baseline()
    assert observed == []

    now["value"] += timedelta(seconds=10)
    next_reset["value"] = now["value"] + timedelta(minutes=1)
    live_tests._ensure_binance_live_usage_baseline()
    assert observed == [("binance", "fetch_account_usage")]
    assert live_tests._BINANCE_LIVE_USAGE_RESET_AT == next_reset["value"]

    live_tests._ensure_binance_live_usage_baseline()
    assert len(observed) == 1


def test_only_plan_approved_live_deferrals_are_excluded_from_full_matrix(monkeypatch):
    runner = _runner_module()
    provider_plan = (
        runner.ROOT / "ops" / "workstreams" / "feat-market-data-provider-platform" / "plan.yaml"
    )

    def unexpected_branch_lookup(*args, **kwargs):
        raise AssertionError("explicit Provider-plan contract must not inspect the checkout")

    monkeypatch.setattr(runner.subprocess, "run", unexpected_branch_lookup)
    deferrals = runner.approved_live_deferrals(provider_plan)

    assert set(deferrals) == {"tradier", "ibkr", "ondo_global_markets"}
    arguments = runner.selected_live_test_arguments(None, deferred_providers=set(deferrals))
    selection = arguments[arguments.index("-k") + 1]
    assert "tradier" not in selection
    assert "ibkr" not in selection
    assert "ondo" not in selection
    assert not any(
        argument.endswith("test_market_data_providers_live.py") for argument in arguments
    )
    assert any("test_openfigi_keyless_mapping" in argument for argument in arguments)


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("feat/market-data-provider-platform", {"tradier"}),
        ("staging", set()),
        ("master", set()),
        ("fix/provider-deferral-contract-context", set()),
        ("feat/unrelated", set()),
    ],
)
def test_default_live_deferrals_use_only_current_branch_plan(
    monkeypatch, tmp_path, branch, expected
):
    runner = _runner_module()
    provider_plan = (
        tmp_path / "ops" / "workstreams" / "feat-market-data-provider-platform" / "plan.yaml"
    )
    provider_plan.parent.mkdir(parents=True)
    provider_plan.write_text(
        "approved_execution_decisions:\n"
        "  providers:\n"
        "    tradier: Deferred by user for this Provider plan only\n"
    )
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    calls = []

    def current_branch(command, **kwargs):
        assert command == ["git", "branch", "--show-current"]
        assert kwargs == {
            "cwd": tmp_path,
            "text": True,
            "capture_output": True,
            "check": False,
        }
        calls.append(branch)
        return SimpleNamespace(stdout=f"{branch}\n")

    monkeypatch.setattr(runner.subprocess, "run", current_branch)
    assert set(runner.approved_live_deferrals()) == expected
    assert calls == [branch]


def test_orf_source_requires_traqs_credentials_separately_from_gateway(monkeypatch):
    runner = _runner_module()
    monkeypatch.delenv("FINRA_OTC_SOURCE_KIND", raising=False)
    assert runner.provider_required_credentials("finra_otc_directory") == (
        "FINRA_OTC_SOURCE_KIND",
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "FINRA_ORF_USERNAME",
        "FINRA_ORF_REFRESH_TOKEN",
        "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
    )

    monkeypatch.setenv("FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    assert runner.provider_required_credentials("finra_otc_directory") == (
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "FINRA_ORF_USERNAME",
        "FINRA_ORF_REFRESH_TOKEN",
        "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
    )

    monkeypatch.setenv("FINRA_OTC_SOURCE_KIND", "legacy_candidate")
    assert runner.provider_required_credentials("finra_otc_directory") == (
        "FINRA_OTC_SOURCE_KIND",
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "FINRA_ORF_USERNAME",
        "FINRA_ORF_REFRESH_TOKEN",
        "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
    )


def test_dinari_sandbox_canary_controls_require_explicit_operator_budget(monkeypatch):
    runner = _runner_module()
    for name in (
        "DINARI_SANDBOX_CANARY_AUTHORIZED",
        "DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE",
        "DINARI_SANDBOX_CANARY_MAX_REQUESTS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert set(runner.dinari_sandbox_canary_controls_missing()) == {
        "DINARI_SANDBOX_CANARY_AUTHORIZED",
        "DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE",
        "DINARI_SANDBOX_CANARY_MAX_REQUESTS (must be exactly 1)",
    }

    monkeypatch.setenv("DINARI_SANDBOX_CANARY_AUTHORIZED", "true")
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE", "owner-approved-sandbox-check")
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "1")
    assert runner.dinari_sandbox_canary_controls_missing() == []
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "2")
    assert runner.dinari_sandbox_canary_controls_missing() == [
        "DINARI_SANDBOX_CANARY_MAX_REQUESTS (must be exactly 1)"
    ]


def test_dinari_sandbox_canary_requires_exact_provider_selection(monkeypatch):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            allow_staged_candidate=False,
            provider=["alpaca", "dinari"],
            account_usage_only=False,
            dinari_sandbox_canary=True,
        ),
    )
    assert runner.main() == 2


def test_dinari_canary_still_honors_non_routable_safety_status():
    runner = _runner_module()
    blockers = runner.live_required_safety_blockers(
        {"dinari"},
        {"dinari sandbox canary quota": "non-routable: canary authorization missing"},
    )
    assert blockers == {"dinari": ["non-routable: canary authorization missing"]}


def test_dinari_canary_runs_durable_quota_preflight_before_any_transport(monkeypatch, capsys):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            allow_staged_candidate=False,
            provider=["dinari"],
            account_usage_only=False,
            dinari_sandbox_canary=True,
        ),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_AUTHORIZED", "true")
    monkeypatch.setenv(
        "DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE", "unit-test canary authorization"
    )
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "1")
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "live_matrix_inventory_errors", lambda: [])
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"dinari": (("x", "y"),)})
    monkeypatch.setattr(runner, "CREDENTIALS", {"dinari": ("DINARI_API_KEY_ID",)})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    quota_calls = []
    monkeypatch.setattr(
        runner,
        "live_operation_quota_preflight",
        lambda providers, **kwargs: quota_calls.append((providers, kwargs))
        or {"dinari": ["active durable baseline is missing"]},
    )
    monkeypatch.setattr(
        runner,
        "routing_safety_preflight",
        lambda: {"dinari sandbox canary quota": "routable for test canary"},
    )
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("must not begin live run")),
    )

    assert runner.main() == 2
    assert quota_calls == [
        (
            {"dinari"},
            {
                "operations_override": {"dinari": {"discover_tokenized_assets"}},
                "local_operation_cost_overrides": {"dinari": {"discover_tokenized_assets": 1}},
            },
        )
    ]
    assert "provider-specific quota/cost/baseline admission" in capsys.readouterr().out


def test_dinari_canary_live_reads_use_durable_quota_reservations(monkeypatch):
    from app.services import provider_quota_coordinator as quota

    live_tests = _tokenized_provider_test_module()
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    measurement = SimpleNamespace(
        http_requests=1,
        response_bytes=7,
        response_headers={"x-ratelimit-remaining": "8"},
        response_metadata=[{"status_code": 200, "headers": {"x-ratelimit-remaining": "8"}}],
        response_payloads=["payload"],
    )
    reservation = SimpleNamespace(reservation_id="dinari-test-reservation")
    reserve_calls = []
    settled = []
    observations = []
    archived = []
    monkeypatch.setattr(
        quota,
        "reserve_live_provider_operation",
        lambda *args, **kwargs: reserve_calls.append((args, kwargs)) or reservation,
    )
    monkeypatch.setattr(
        quota,
        "settle_live_provider_operation",
        lambda value, **kwargs: settled.append((value, kwargs)),
    )
    monkeypatch.setattr(
        live_tests,
        "activate_provider_telemetry",
        lambda **_kwargs: (measurement, "token"),
    )
    monkeypatch.setattr(
        live_tests,
        "archive_response_payloads",
        lambda provider, operation, payloads, **kwargs: archived.append(
            (provider, operation, payloads, kwargs)
        ),
    )
    monkeypatch.setattr(live_tests, "deactivate_provider_telemetry", lambda _token: None)
    monkeypatch.setattr(live_tests, "activate_request_admission", lambda: "admission")
    monkeypatch.setattr(live_tests, "deactivate_request_admission", lambda _token: None)
    monkeypatch.setattr(
        live_tests, "record_observation", lambda *args, **kwargs: observations.append(kwargs)
    )

    result, observed = live_tests._observed_read(
        lambda: "provider response",
        "dinari",
        "discover_tokenized_assets",
    )

    assert result == "provider response"
    assert observed is measurement
    assert reserve_calls[0][0][:2] == ("dinari", "discover_tokenized_assets")
    assert reserve_calls[0][1]["operation_cost_override"] == 1
    assert reserve_calls[0][1]["require_persistent_coordinator"] is True
    assert settled == [(reservation, {"http_requests": 1, "response_bytes": 7})]
    assert observations[0]["reservation_id"] == "dinari-test-reservation"
    expected_archived_response = (
        "dinari",
        "discover_tokenized_assets",
        ["payload"],
        {
            "response_bytes": 7,
            "response_metadata": [{"status_code": 200, "headers": {"x-ratelimit-remaining": "8"}}],
        },
    )
    assert archived == [expected_archived_response]

    with pytest.raises(ValueError, match="sandbox failure"):
        live_tests._observed_read(
            lambda: (_ for _ in ()).throw(ValueError("sandbox failure")),
            "dinari",
            "discover_tokenized_assets",
        )
    assert len(settled) == 2
    assert archived == [expected_archived_response, expected_archived_response]


def test_unit_runner_does_not_persist_synthetic_receipts_to_workstream_by_default(
    monkeypatch, tmp_path
):
    """Runner unit tests must not pollute the durable branch validation ledger."""

    runner = _runner_module()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_live_provider_runner.py::unit")
    monkeypatch.delenv("PROVIDER_LIVE_VALIDATION_WRITE", raising=False)
    monkeypatch.setattr(runner, "_git_output", lambda *args: "feat/unit-runner")
    validation_path = tmp_path / "ops" / "workstreams" / "feat-unit-runner" / "validation.jsonl"
    validation_path.parent.mkdir(parents=True)
    validation_path.touch()

    assert runner._workstream_validation_path() is None
    assert validation_path.read_text(encoding="utf-8") == ""


def test_runner_validation_persistence_requires_explicit_unit_test_opt_in(monkeypatch, tmp_path):
    """A runner test may exercise persistence only through an explicit opt-in."""

    runner = _runner_module()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_live_provider_runner.py::unit")
    monkeypatch.setenv("PROVIDER_LIVE_VALIDATION_WRITE", "1")
    monkeypatch.setattr(runner, "_git_output", lambda *args: "feat/unit-runner")
    validation_path = tmp_path / "ops" / "workstreams" / "feat-unit-runner" / "validation.jsonl"
    validation_path.parent.mkdir(parents=True)
    validation_path.touch()

    assert runner._workstream_validation_path() == validation_path


def test_focused_parameterized_provider_selection_does_not_select_siblings():
    runner = _runner_module()
    arguments = runner.selected_live_test_arguments(["tiingo"])

    assert (
        "tests/live/test_market_data_providers_live.py::test_optional_credentialed_provider_small_read"
        in arguments
    )
    selection = arguments[arguments.index("-k") + 1]
    assert "tiingo" in selection
    assert "optional_credentialed_provider_small_read" not in selection


def test_dinari_canary_selects_only_the_single_read_case():
    runner = _runner_module()
    assert runner.selected_live_test_arguments(["dinari"], dinari_sandbox_canary=True) == [
        "tests/live/test_tokenized_providers_live.py::"
        "test_dinari_credentialed_stock_metadata_price_quote_history_and_news"
    ]


def test_exact_case_selection_pins_alpha_cases_to_quota_operations():
    runner = _runner_module()
    selectors = [
        "alpha_vantage:test_alpha_vantage_credentialed_current_price",
        "alpha_vantage:test_alpha_vantage_credentialed_search",
    ]
    selected, operations = runner.parse_live_case_selectors(selectors, {"alpha_vantage"})

    assert selected == {
        "alpha_vantage": {
            "test_alpha_vantage_credentialed_current_price",
            "test_alpha_vantage_credentialed_search",
        }
    }
    assert operations == {"alpha_vantage": {"get_current_price", "search_instruments"}}
    arguments = runner.selected_live_test_arguments(["alpha_vantage"], selected_cases=selected)
    assert arguments[:2] == [
        "tests/live/test_market_data_providers_live.py::test_alpha_vantage_credentialed_current_price",
        "tests/live/test_market_data_providers_live.py::test_alpha_vantage_credentialed_search",
    ]
    assert len(arguments) == 4


def test_exact_coinbase_case_selection_pins_history_quote_and_catalogue_costs():
    runner = _runner_module()
    selector = "coinbase:test_coinbase_keyless_history_quote_and_usd_products"

    selected, operations = runner.parse_live_case_selectors([selector], {"coinbase"})

    assert selected == {"coinbase": {"test_coinbase_keyless_history_quote_and_usd_products"}}
    assert operations == {
        "coinbase": {"fetch_ohlcv", "get_current_price", "discover_universe_page"}
    }
    assert runner.LIVE_OPERATION_COST_OVERRIDES["coinbase"]["fetch_ohlcv"] == 1
    arguments = runner.selected_live_test_arguments(["coinbase"], selected_cases=selected)
    assert arguments[0] == (
        "tests/live/test_market_data_providers_live.py::"
        "test_coinbase_keyless_history_quote_and_usd_products"
    )
    assert arguments[1] == "-k"
    assert "coinbase_keyless_history_quote_and_usd_products" in arguments[2]


def test_coingecko_catalogue_is_required_and_reserves_one_credit():
    runner = _runner_module()
    selector = "coingecko:test_coingecko_credentialed_universe_page"

    selected, operations = runner.parse_live_case_selectors([selector], {"coingecko"})

    assert selected == {"coingecko": {"test_coingecko_credentialed_universe_page"}}
    assert operations == {"coingecko": {"discover_universe_page"}}
    assert runner.LIVE_OPERATION_COST_OVERRIDES["coingecko"]["discover_universe_page"] == 1
    assert runner.LIVE_REQUIRED_OPERATIONS["coingecko"] >= {"discover_universe_page"}


def test_exact_marketdata_option_case_selection_pins_expiration_and_chain_operations():
    runner = _runner_module()
    selector = "marketdata_app:test_marketdata_app_credentialed_option_surface"

    selected, operations = runner.parse_live_case_selectors([selector], {"marketdata_app"})

    assert selected == {"marketdata_app": {"test_marketdata_app_credentialed_option_surface"}}
    assert operations == {"marketdata_app": {"list_option_expirations", "fetch_option_chain"}}
    assert runner.LIVE_OPERATION_COST_OVERRIDES["marketdata_app"]["fetch_option_chain"] == 20
    arguments = runner.selected_live_test_arguments(["marketdata_app"], selected_cases=selected)
    assert arguments[0] == (
        "tests/live/test_market_data_providers_live.py::"
        "test_marketdata_app_credentialed_option_surface"
    )
    assert arguments[1] == "-k"
    assert "marketdata_app_credentialed_option_surface" in arguments[2]


def test_case_focused_live_evidence_does_not_claim_full_provider_coverage(tmp_path, monkeypatch):
    runner = _runner_module()
    cases, operations = runner.parse_live_case_selectors(
        [
            "alpha_vantage:test_alpha_vantage_credentialed_current_price",
            "alpha_vantage:test_alpha_vantage_credentialed_search",
        ],
        {"alpha_vantage"},
    )
    ledger = tmp_path / "usage.jsonl"
    current_case = (
        "tests/live/test_market_data_providers_live.py::"
        "test_alpha_vantage_credentialed_current_price"
    )
    search_case = (
        "tests/live/test_market_data_providers_live.py::" "test_alpha_vantage_credentialed_search"
    )
    usage = {}
    operation_usage = {}
    for case, operation in (
        (current_case, "get_current_price"),
        (search_case, "search_instruments"),
    ):
        observed = {
            "http_requests": 1,
            "response_bytes": 20,
            "failed_operations": 0,
            "dispositions": {"observed": 1},
            "response_statuses": {"200": 1},
        }
        usage[case] = {
            "http_requests": 1,
            "response_bytes": 20,
            "operations": {operation: observed},
        }
        operation_usage[operation] = observed
    ledger.write_text(
        json.dumps(
            {
                "run_id": "case-run",
                "usage_scope": "unit-scope",
                "provider": "alpha_vantage",
                "http_requests": 2,
                "response_bytes": 40,
                "failed_operations": 0,
                "operation_usage": operation_usage,
                "case_usage": usage,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "unit-scope")
    junit = [
        {
            "module": "test_market_data_providers_live.py",
            "name": name,
            "outcome": "passed",
        }
        for name in (
            "test_alpha_vantage_credentialed_current_price",
            "test_alpha_vantage_credentialed_search",
        )
    ]

    focused = runner._provider_live_evidence(
        run_id="case-run",
        providers={"alpha_vantage"},
        junit_cases=junit,
        ledger_path=ledger,
        selected_cases=cases,
        required_operations_override=operations,
    )
    assert focused["complete"] is True
    assert focused["selection"] == "case_subset"
    assert focused["selected_cases"]["alpha_vantage"] == sorted(cases["alpha_vantage"])
    assert set(focused["providers"]["alpha_vantage"]["operations"]) == {
        "get_current_price",
        "search_instruments",
    }

    full_provider = runner._provider_live_evidence(
        run_id="case-run",
        providers={"alpha_vantage"},
        junit_cases=junit,
        ledger_path=ledger,
    )
    assert full_provider["complete"] is False


def test_dinari_canary_live_evidence_requires_one_measured_catalogue_read(tmp_path, monkeypatch):
    runner = _runner_module()
    case_name = runner.DINARI_CANARY_CASE[1]
    case_id = f"tests/live/{runner.DINARI_CANARY_CASE[0]}::{case_name}"
    operation = runner.DINARI_CANARY_OPERATION
    observation = {
        "http_requests": 1,
        "response_bytes": 100,
        "failed_operations": 0,
        "dispositions": {"observed": 1},
        "response_statuses": {"200": 1},
    }
    ledger = tmp_path / "dinari-usage.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "run_id": "dinari-canary-run",
                "usage_scope": "dinari-canary-test",
                "provider": "dinari",
                "http_requests": 1,
                "response_bytes": 100,
                "failed_operations": 0,
                "operation_usage": {operation: observation},
                "case_usage": {
                    case_id: {
                        "http_requests": 1,
                        "response_bytes": 100,
                        "operations": {operation: observation},
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "dinari-canary-test")

    evidence = runner._provider_live_evidence(
        run_id="dinari-canary-run",
        providers={"dinari"},
        junit_cases=[
            {
                "module": runner.DINARI_CANARY_CASE[0],
                "name": case_name,
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
        required_operations_override={"dinari": {operation}},
    )

    assert evidence["complete"] is True
    assert _runner_module()._dinari_candidate_canary_evidence_errors(evidence) == []


def test_account_usage_only_selection_keeps_only_the_dedicated_case():
    runner = _runner_module()
    arguments = runner.selected_live_test_arguments(["eodhd"], account_usage_only=True)

    assert arguments == [
        "tests/live/test_market_data_providers_live.py::test_eodhd_credentialed_account_usage_snapshot",
        "-k",
        "eodhd_credentialed_account_usage_snapshot",
    ]

    binance_arguments = runner.selected_live_test_arguments(["binance"], account_usage_only=True)
    assert binance_arguments == [
        "tests/live/test_market_data_providers_live.py::test_binance_keyless_account_usage_snapshot",
        "-k",
        "binance_keyless_account_usage_snapshot",
    ]

    alpaca_arguments = runner.selected_live_test_arguments(["alpaca"], account_usage_only=True)
    assert alpaca_arguments == [
        "tests/live/test_market_data_providers_live.py::test_alpaca_credentialed_account_usage_snapshot",
        "-k",
        "alpaca_credentialed_account_usage_snapshot",
    ]

    openfigi_arguments = runner.selected_live_test_arguments(["openfigi"], account_usage_only=True)
    assert openfigi_arguments == [
        "tests/live/test_market_data_providers_live.py::test_openfigi_keyless_account_usage_snapshot",
        "-k",
        "openfigi_keyless_account_usage_snapshot",
    ]


def test_account_usage_live_safety_uses_operation_scoped_provider_controls(monkeypatch):
    runner = _runner_module()
    from app.config import settings

    monkeypatch.setattr(settings, "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED", False)
    monkeypatch.setattr(settings, "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE", "")
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 0)
    statuses = {"eodhd": "non-routable: EODHD display/use authority has not been reviewed"}

    assert runner.live_required_safety_blockers({"eodhd"}, statuses, account_usage_only=True) == {}
    assert runner.live_required_safety_blockers({"eodhd"}, statuses) == {
        "eodhd": [statuses["eodhd"]]
    }

    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", -1)
    assert runner.live_required_safety_blockers({"eodhd"}, statuses, account_usage_only=True) == {
        "eodhd": ["non-routable for account usage: missing/invalid EODHD_REVIEWED_MINUTE_LIMIT"]
    }


def test_finra_live_safety_uses_operation_scoped_controls_not_storage_summary(monkeypatch):
    runner = _runner_module()
    from app.providers import registry

    statuses = {
        "finra short-interest and Daily List data use": (
            "no owner storage approval needed; FINRA credentials, quota, and source checks still apply"
        )
    }
    assert runner.live_required_safety_blockers({"finra"}, statuses) == {}

    monkeypatch.setattr(
        registry,
        "provider_missing_routing_controls",
        lambda provider, operation=None: ["FINRA_TEST_OPERATION_REVIEW"]
        if provider == "finra" and operation == "fetch_market_events"
        else [],
    )
    assert runner.live_required_safety_blockers({"finra"}, statuses) == {
        "finra": [
            "non-routable: missing/invalid FINRA operation controls: FINRA_TEST_OPERATION_REVIEW"
        ]
    }


def test_massive_live_safety_uses_one_stock_asset_class_bucket(monkeypatch):
    runner = _runner_module()
    from app.providers import registry

    monkeypatch.setattr(
        registry,
        "provider_missing_routing_controls",
        lambda provider, operation=None: [],
    )
    statuses = {"massive market-data use": "routable"}
    _cases, selected_reference_operations = runner.parse_live_case_selectors(
        ["massive:test_massive_credentialed_corporate_actions_complete"], {"massive"}
    )

    # Stock series, reference data, and corporate actions are all charged
    # against the documented Stocks asset-class request pool.
    assert (
        runner.live_required_safety_blockers(
            {"massive"},
            statuses,
            operations_by_provider={"massive": {"fetch_ohlcv"}},
        )
        == {}
    )
    assert (
        runner.live_required_safety_blockers(
            {"massive"},
            statuses,
            operations_by_provider=selected_reference_operations,
        )
        == {}
    )
    assert runner.live_required_safety_blockers({"massive"}, statuses) == {}


def test_manifest_account_usage_providers_are_explicit():
    runner = _runner_module()

    assert runner.manifest_account_usage_providers(
        {"binance", "twelve_data", "finnhub", "unknown"}
    ) == {"binance", "twelve_data", "finnhub"}
    assert runner.account_usage_only_provider_set() == {
        "alpaca",
        "binance",
        "eodhd",
        "fmp",
        "finnhub",
        "marketdata_app",
        "openfigi",
        "twelve_data",
        "xstocks",
    }


def test_live_quota_preflight_only_allows_explicit_bootstrap_unknown_baseline(
    monkeypatch,
):
    runner = _runner_module()
    from app import config
    from app.services import provider_quota_coordinator as coordinator

    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "shared-ip",
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "request_weight_per_minute",
                        "limit": 1200,
                        "unit": "request_weight",
                    }
                ],
                "account_usage_bootstrap": {
                    "enabled": True,
                    "reconciled_dimensions": ["request_weight_per_minute"],
                },
            },
        },
    )
    monkeypatch.setattr(
        coordinator,
        "_reservation_plan_for_live_probe",
        lambda *args, **kwargs: (
            "fixed_minute",
            {},
            [
                {
                    "dimension": "request_weight_per_minute",
                    "quota_group": "binance",
                    "units": 1,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "provider_quota_baseline_status",
        lambda **kwargs: {"status": "unknown", "remaining_units": None},
    )

    # Preserve the operation-level contract: data-only use stays blocked with
    # the exact diagnostic, while explicitly reviewed bootstrap stays allowed.
    assert runner.live_operation_quota_preflight(
        {"binance"},
        operations_override={"binance": {"fetch_ohlcv"}},
    ) == {
        "binance": [
            "binance/fetch_ohlcv: active request_weight_per_minute usage baseline is unknown"
        ]
    }
    assert (
        runner.live_operation_quota_preflight(
            {"binance"},
            operations_override={"binance": {"fetch_ohlcv"}},
            bootstrap_providers={"binance"},
        )
        == {}
    )

    selected_cases, selected_operations = runner.parse_live_case_selectors(
        ["binance:test_binance_keyless_bounded_daily_history"], {"binance"}
    )
    assert selected_operations == {"binance": {"fetch_account_usage", "fetch_ohlcv"}}
    assert runner.selected_case_bootstrap_providers({"binance"}, selected_operations) == {"binance"}
    multipliers = runner.selected_case_operation_multipliers(selected_cases)

    # This reproduces the actual CLI case-scoped path: the selected case's
    # canonical operation map contains its native usage helper, so preflight
    # permits that exact account snapshot to establish the mapped weight pool.
    assert (
        runner.live_case_quota_preflight(
            {"binance"},
            operations=selected_operations,
            operation_multipliers=multipliers,
        )
        == {}
    )

    # A data-only selection has no bootstrap authority and remains fail-closed.
    data_only = {"binance": {"fetch_ohlcv"}}
    assert runner.selected_case_bootstrap_providers({"binance"}, data_only) == set()
    assert runner.live_case_quota_preflight(
        {"binance"}, operations=data_only, operation_multipliers={"binance": {}}
    ) == {
        "binance": [
            "binance/fetch_ohlcv: active request_weight_per_minute usage baseline is unknown"
        ]
    }


def test_live_quota_preflight_blocks_bootstrap_dimensions_without_native_mapping(
    monkeypatch,
):
    runner = _runner_module()
    from app import config
    from app.services import provider_quota_coordinator as coordinator

    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "api_key",
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "credits_per_minute",
                        "limit": 8,
                        "window_seconds": 60,
                        "unit": "credits",
                    },
                    {
                        "name": "credits_per_day",
                        "limit": 800,
                        "window_seconds": 86400,
                        "unit": "credits",
                    },
                ],
                "account_usage_bootstrap": {
                    "enabled": True,
                    "reconciled_dimensions": ["credits_per_minute"],
                },
            },
        },
    )
    monkeypatch.setattr(
        coordinator,
        "_reservation_plan_for_live_probe",
        lambda *args, **kwargs: (
            "per_dimension",
            {"credits_per_minute": 1, "credits_per_day": 1},
            [
                {
                    "dimension": "credits_per_minute",
                    "quota_group": "api_key",
                    "units": 1,
                },
                {
                    "dimension": "credits_per_day",
                    "quota_group": "api_key",
                    "units": 1,
                },
            ],
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "provider_quota_baseline_status",
        lambda **kwargs: {"status": "unknown", "remaining_units": None},
    )

    assert runner.live_operation_quota_preflight(
        {"twelve_data"},
        operations_override={"twelve_data": {"fetch_ohlcv"}},
        bootstrap_providers={"twelve_data"},
    ) == {
        "twelve_data": ["twelve_data/fetch_ohlcv: active credits_per_day usage baseline is unknown"]
    }


def test_live_quota_preflight_requires_mapping_for_every_bootstrap_pool(monkeypatch):
    runner = _runner_module()
    from app import config
    from app.services import provider_quota_coordinator as coordinator

    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "api_key",
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_day",
                        "limit": 10,
                        "window_seconds": 86400,
                        "unit": "requests",
                    }
                ],
                "account_usage_bootstrap": {"enabled": True},
            },
        },
    )
    monkeypatch.setattr(
        coordinator,
        "_reservation_plan_for_live_probe",
        lambda *args, **kwargs: (
            "per_dimension",
            {"requests_per_day": 1},
            [{"dimension": "requests_per_day", "quota_group": "api_key", "units": 1}],
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "provider_quota_baseline_status",
        lambda **kwargs: {"status": "unknown", "remaining_units": None},
    )

    assert runner.live_operation_quota_preflight(
        {"fixture"},
        operations_override={"fixture": {"fetch_ohlcv"}},
        bootstrap_providers={"fixture"},
    ) == {"fixture": ["fixture/fetch_ohlcv: active requests_per_day usage baseline is unknown"]}


def test_manifest_has_exact_operation_evidence_for_every_provider():
    runner = _runner_module()

    assert set(runner.LIVE_REQUIRED_OPERATIONS) == set(runner.LIVE_PROVIDER_CASES)
    assert runner.LIVE_PROVIDER_CASES["nasdaq"] == (
        (
            "test_market_data_providers_live.py",
            "test_nasdaq_trader_full_directory_pagination_is_complete",
        ),
    )
    assert runner.LIVE_PROVIDER_CASES["finra_otc_directory"] == (
        (
            "test_market_data_providers_live.py",
            "test_finra_otc_directory_credentialed_source",
        ),
    )
    # ORF is an active source candidate: missing TRAQS credentials, terms, or
    # quota controls must block admission, not be mistaken for an approved
    # no-request disposition in the live acceptance matrix.
    assert "finra_otc_directory" not in runner.LIVE_PROVIDER_SAFETY_DISPOSITIONS
    assert runner.LIVE_REQUIRED_OPERATIONS["finnhub"] == {
        "fetch_account_usage",
        "search_instruments",
        "get_instrument_profile",
        "fetch_instrument_events",
        "fetch_market_events",
        "discover_universe_page",
        "get_current_price",
    }
    for provider, dispositions in runner.LIVE_OPERATION_DISPOSITIONS.items():
        assert provider in runner.LIVE_REQUIRED_OPERATIONS
        assert set(dispositions).isdisjoint(runner.LIVE_REQUIRED_OPERATIONS[provider])
    manifest_cases = {
        (provider, relative_path, function_name)
        for provider, cases in runner.LIVE_PROVIDER_CASES.items()
        for relative_path, function_name in cases
    }
    assert runner.LIVE_NO_REQUEST_CASES.keys() <= manifest_cases
    assert runner.LIVE_EXPECTED_ENTITLEMENT_DENIALS.keys() <= manifest_cases


def test_bounded_manifest_cost_overrides_cover_response_paged_cases():
    """Dynamic adapter estimates must be explicit in the safety preflight."""

    runner = _runner_module()

    assert runner.LIVE_OPERATION_COST_OVERRIDES == {
        "alpaca": {
            "fetch_ohlcv": 2,
            "fetch_instrument_events": 1,
        },
        "binance": {"fetch_latest_ohlcv": 2, "fetch_ohlcv": 2},
        "coinbase": {"fetch_latest_ohlcv": 1, "fetch_ohlcv": 1},
        "coingecko": {
            "discover_universe_page": 1,
        },
        "fred": {"get_current_price": 1},
        "kraken": {"fetch_ohlcv": 1, "fetch_latest_ohlcv": 1},
        "massive": {
            "fetch_instrument_events": 2,
            "fetch_market_events": 2,
            "fetch_ohlcv": 1,
        },
        "marketdata_app": {
            "fetch_ohlcv": 2,
            "fetch_option_chain": 20,
            "fetch_option_quote_history": 1,
        },
        "marketstack": {"fetch_ohlcv": 1},
    }


def test_live_matrix_inventory_is_structurally_exact_and_disposition_kinds_are_explicit():
    runner = _runner_module()

    assert runner.live_matrix_inventory_errors() == []
    assert runner.provider_method_inventory_errors() == []
    assert runner.LIVE_OPERATION_METHOD_ALIASES["fetch_latest_ohlcv"] == "fetch_ohlcv"
    assert (
        runner.LIVE_OPERATION_METHOD_ALIASES["fetch_instrument_events_page"]
        == "fetch_instrument_events"
    )
    assert runner.LIVE_SERVICE_OPERATION_ALIASES == {
        "fetch_rfr_ohlcv": "fetch_ohlcv",
        "bulk_fetch": "fetch_ohlcv",
        "reconcile_universe_page": "discover_universe_page",
    }
    assert (
        runner.live_operation_disposition_kind(
            "intentional_no_request_policy: legal/usage control is unresolved"
        )
        == "intentional_no_request_policy"
    )
    # Preserve compatibility with early redacted receipts without allowing
    # ``policy_block`` to become a second, ambiguous no-request category.
    assert (
        runner.live_operation_disposition_kind("policy_block: no request")
        == "intentional_no_request_policy"
    )
    assert runner.live_operation_disposition_kind("deferred by user: account") == ("human_deferred")
    assert "human_deferred" in runner.LIVE_COVERED_DISPOSITION_KINDS
    assert "blocked" not in runner.LIVE_COVERED_DISPOSITION_KINDS


def test_live_matrix_inventory_rejects_unknown_or_overlapping_dispositions():
    runner = _runner_module()
    original_cases = runner.LIVE_PROVIDER_CASES
    original_required = runner.LIVE_REQUIRED_OPERATIONS
    original_dispositions = runner.LIVE_OPERATION_DISPOSITIONS
    try:
        runner.LIVE_PROVIDER_CASES = {"demo": (("test.py", "test_demo"),)}
        runner.LIVE_REQUIRED_OPERATIONS = {"demo": {"fetch_ohlcv"}}
        runner.LIVE_OPERATION_DISPOSITIONS = {
            "demo": {
                "fetch_ohlcv": "deferred: overlaps a required operation",
                "search": "operator_typo: not a supported disposition",
            }
        }
        errors = runner.live_matrix_inventory_errors()
    finally:
        runner.LIVE_PROVIDER_CASES = original_cases
        runner.LIVE_REQUIRED_OPERATIONS = original_required
        runner.LIVE_OPERATION_DISPOSITIONS = original_dispositions

    assert any("overlap required operations" in error for error in errors)
    assert any("unknown disposition kind" in error for error in errors)


def test_unexercised_registered_surfaces_have_explicit_live_dispositions():
    runner = _runner_module()

    expected = {
        "edgar": set(),
        "fred": set(),
        "coingecko": {"fetch_account_usage"},
        "finra": {
            "submit_async_dataset",
            "poll_async_dataset",
            "download_async_result",
        },
        "massive": set(),
        "alpha_vantage": set(),
        "tiingo": set(),
        "twelve_data": set(),
        "finnhub": {"fetch_ohlcv"},
        "marketstack": set(),
        "eodhd": set(),
        "fmp": {"discover_universe_page"},
        "tradier": {"search_instruments", "get_current_price"},
        "marketdata_app": set(),
        "ibkr": {"search_instruments", "futures_history"},
        "binance": set(),
        "coinbase": set(),
        "kraken": set(),
        "ondo_global_markets": {"get_tokenized_asset"},
    }

    assert {
        provider: set(runner.LIVE_OPERATION_DISPOSITIONS.get(provider, {})) for provider in expected
    } == expected


def test_finra_generic_async_legs_are_not_independent_data_capabilities():
    runner = _runner_module()

    dispositions = runner.LIVE_OPERATION_DISPOSITIONS["finra"]

    assert set(dispositions) == {
        "submit_async_dataset",
        "poll_async_dataset",
        "download_async_result",
    }
    assert {runner.live_operation_disposition_kind(reason) for reason in dispositions.values()} == {
        "transport_not_applicable"
    }


def test_live_evidence_requires_current_run_case_and_operation_observations(tmp_path, monkeypatch):
    runner = _runner_module()
    ledger = tmp_path / "usage.jsonl"
    # This focused evaluator fixture intentionally supplies one operation. The
    # production manifest also requires OpenFIGI profile resolution; that
    # second case has its own live receipt and is tested separately.
    monkeypatch.setitem(runner.LIVE_REQUIRED_OPERATIONS, "openfigi", {"fetch_stable_identifiers"})
    monkeypatch.setitem(
        runner.LIVE_PROVIDER_CASES,
        "openfigi",
        (("test_market_data_providers_live.py", "test_openfigi_keyless_mapping"),),
    )
    case_id = "tests/live/test_market_data_providers_live.py::test_openfigi_keyless_mapping"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "unit-scope")
    ledger.write_text(
        json.dumps(
            {
                "run_id": "another-run",
                "usage_scope": "unit-scope",
                "provider": "openfigi",
                "http_requests": 1,
                "response_bytes": 10,
                "failed_operations": 0,
                "operation_usage": {"fetch_stable_identifiers": {"http_requests": 1}},
                "case_usage": {case_id: {"http_requests": 1}},
            }
        )
        + "\n"
        + json.dumps(
            {
                "run_id": "current-run",
                "usage_scope": "unit-scope",
                "provider": "openfigi",
                "http_requests": 1,
                "response_bytes": 10,
                "failed_operations": 0,
                "operation_usage": {
                    "fetch_stable_identifiers": {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "failed_operations": 0,
                        "dispositions": {"observed": 1},
                        "response_statuses": {"200": 1},
                    }
                },
                "case_usage": {
                    case_id: {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "operations": {
                            "fetch_stable_identifiers": {
                                "http_requests": 1,
                                "response_bytes": 10,
                                "failed_operations": 0,
                                "dispositions": {"observed": 1},
                                "response_statuses": {"200": 1},
                            }
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = runner._provider_live_evidence(
        run_id="current-run",
        providers={"openfigi"},
        junit_cases=[
            {
                "module": "test_market_data_providers_live.py",
                "name": "test_openfigi_keyless_mapping",
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
    )

    assert evidence["complete"] is True
    assert evidence["providers"]["openfigi"]["operations"]["fetch_stable_identifiers"]["passed"]
    assert evidence["cases"][0]["http_requests"] == 1


def test_live_evidence_rejects_duplicate_case_and_reservation_receipts(tmp_path, monkeypatch):
    runner = _runner_module()
    monkeypatch.setitem(runner.LIVE_REQUIRED_OPERATIONS, "openfigi", {"fetch_stable_identifiers"})
    monkeypatch.setitem(
        runner.LIVE_PROVIDER_CASES,
        "openfigi",
        (("test_market_data_providers_live.py", "test_openfigi_keyless_mapping"),),
    )
    ledger = tmp_path / "usage.jsonl"
    case_id = "tests/live/test_market_data_providers_live.py::test_openfigi_keyless_mapping"
    row = {
        "run_id": "duplicate-run",
        "usage_scope": "unit-scope",
        "provider": "openfigi",
        "http_requests": 1,
        "response_bytes": 10,
        "failed_operations": 0,
        "operation_usage": {
            "fetch_stable_identifiers": {
                "http_requests": 1,
                "response_bytes": 10,
                "failed_operations": 0,
                "dispositions": {"observed": 1},
                "response_statuses": {"200": 1},
            }
        },
        "case_usage": {
            case_id: {
                "http_requests": 1,
                "response_bytes": 10,
                "operations": {
                    "fetch_stable_identifiers": {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "failed_operations": 0,
                        "dispositions": {"observed": 1},
                        "response_statuses": {"200": 1},
                    }
                },
            }
        },
        "reservations": [
            {
                "reservation_id": "00000000-0000-0000-0000-000000000001",
                "operation": "fetch_stable_identifiers",
                "status": "observed",
            }
        ],
    }
    ledger.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    evidence = runner._provider_live_evidence(
        run_id="duplicate-run",
        providers={"openfigi"},
        junit_cases=[
            {
                "module": "test_market_data_providers_live.py",
                "name": "test_openfigi_keyless_mapping",
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
    )
    assert evidence["complete"] is False
    assert "duplicate" in str(evidence["ledger_error"])


def test_fred_policy_guard_pass_cannot_substitute_for_live_evidence(tmp_path, monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "false")
    ledger = tmp_path / "usage.jsonl"
    ledger.write_text("", encoding="utf-8")

    evidence = runner._provider_live_evidence(
        run_id="fred-no-call",
        providers={"fred"},
        junit_cases=[
            {
                "module": "test_market_data_providers_live.py",
                "name": "test_fred_series_requires_persisted_data_rights_before_network_access",
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
    )

    assert evidence["complete"] is False
    assert evidence["cases"][0]["disposition"] == "intentional_no_request_policy"
    assert any("fetch_ohlcv" in item for item in evidence["missing"])


def test_unresolved_operation_disposition_cannot_be_reported_as_complete(tmp_path, monkeypatch):
    runner = _runner_module()
    ledger = tmp_path / "usage.jsonl"
    monkeypatch.setitem(runner.LIVE_REQUIRED_OPERATIONS, "openfigi", {"fetch_stable_identifiers"})
    monkeypatch.setitem(
        runner.LIVE_PROVIDER_CASES,
        "openfigi",
        (("test_market_data_providers_live.py", "test_openfigi_keyless_mapping"),),
    )
    case_id = "tests/live/test_market_data_providers_live.py::test_openfigi_keyless_mapping"
    ledger.write_text(
        json.dumps(
            {
                "run_id": "disposition-run",
                "usage_scope": "unit-scope",
                "provider": "openfigi",
                "http_requests": 1,
                "response_bytes": 10,
                "failed_operations": 0,
                "operation_usage": {
                    "fetch_stable_identifiers": {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "failed_operations": 0,
                        "dispositions": {"observed": 1},
                        "response_statuses": {"200": 1},
                    }
                },
                "case_usage": {
                    case_id: {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "operations": {
                            "fetch_stable_identifiers": {
                                "http_requests": 1,
                                "response_bytes": 10,
                                "failed_operations": 0,
                                "dispositions": {"observed": 1},
                                "response_statuses": {"200": 1},
                            }
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(
        runner.LIVE_OPERATION_DISPOSITIONS,
        "openfigi",
        {"search_instruments": "test disposition"},
    )

    evidence = runner._provider_live_evidence(
        run_id="disposition-run",
        providers={"openfigi"},
        junit_cases=[
            {
                "module": "test_market_data_providers_live.py",
                "name": "test_openfigi_keyless_mapping",
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
    )

    assert evidence["complete"] is False
    assert any("search_instruments" in item for item in evidence["missing"])

    monkeypatch.setitem(
        runner.LIVE_OPERATION_DISPOSITIONS,
        "openfigi",
        {"search_instruments": "deferred by user: not part of this acceptance run"},
    )
    deferred_evidence = runner._provider_live_evidence(
        run_id="disposition-run",
        providers={"openfigi"},
        junit_cases=[
            {
                "module": "test_market_data_providers_live.py",
                "name": "test_openfigi_keyless_mapping",
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
    )
    assert deferred_evidence["complete"] is True
    assert (
        deferred_evidence["operation_dispositions"]["openfigi"]["search_instruments"]["kind"]
        == "human_deferred"
    )


def test_empty_kraken_xstocks_catalogue_does_not_prove_asset_or_price_reads(tmp_path):
    runner = _runner_module()
    ledger = tmp_path / "usage.jsonl"
    case_id = (
        "tests/live/test_tokenized_providers_live.py::"
        "test_kraken_public_xstocks_asset_and_ticker"
    )
    discovery = {
        "http_requests": 1,
        "response_bytes": 100,
        "failed_operations": 0,
        "dispositions": {"observed": 1},
        "response_statuses": {"200": 1},
    }
    ledger.write_text(
        json.dumps(
            {
                "run_id": "kraken-empty-catalogue",
                "usage_scope": "unit-scope",
                "provider": "kraken_xstocks",
                "http_requests": 1,
                "response_bytes": 100,
                "failed_operations": 0,
                "operation_usage": {"discover_tokenized_assets": discovery},
                "case_usage": {
                    case_id: {
                        "http_requests": 1,
                        "response_bytes": 100,
                        "operations": {"discover_tokenized_assets": discovery},
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = runner._provider_live_evidence(
        run_id="kraken-empty-catalogue",
        providers={"kraken_xstocks"},
        junit_cases=[
            {
                "module": "test_tokenized_providers_live.py",
                "name": "test_kraken_public_xstocks_asset_and_ticker",
                "outcome": "passed",
            }
        ],
        ledger_path=ledger,
    )

    assert evidence["cases"][0]["pytest"] == "passed"
    assert evidence["cases"][0]["http_requests"] == 1
    assert evidence["complete"] is False
    assert any("kraken_xstocks:get_tokenized_asset" in item for item in evidence["missing"])
    assert any("kraken_xstocks:get_tokenized_price" in item for item in evidence["missing"])


def test_expected_entitlement_denial_requires_explicit_receipt_disposition(tmp_path, monkeypatch):
    runner = _runner_module()
    ledger = tmp_path / "usage.jsonl"
    case_id = "tests/live/test_market_data_providers_live.py::test_openfigi_keyless_mapping"
    base_operation = {
        "http_requests": 1,
        "response_bytes": 10,
        "failed_operations": 0,
        "dispositions": {"observed": 1},
        "response_statuses": {"403": 1},
    }
    ledger.write_text(
        json.dumps(
            {
                "run_id": "entitlement-run",
                "usage_scope": "unit-scope",
                "provider": "demo",
                "http_requests": 1,
                "response_bytes": 10,
                "failed_operations": 0,
                "operation_usage": {"fetch_ohlcv": base_operation},
                "case_usage": {
                    case_id: {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "operations": {"fetch_ohlcv": base_operation},
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "LIVE_PROVIDER_CASES",
        {
            "demo": (
                (
                    "test_market_data_providers_live.py",
                    "test_openfigi_keyless_mapping",
                ),
            )
        },
    )
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"demo": {"fetch_ohlcv"}})
    monkeypatch.setattr(runner, "LIVE_NO_REQUEST_CASES", {})
    monkeypatch.setattr(
        runner,
        "LIVE_EXPECTED_ENTITLEMENT_DENIALS",
        {
            (
                "demo",
                "test_market_data_providers_live.py",
                "test_openfigi_keyless_mapping",
            ): {"fetch_ohlcv": 403}
        },
    )
    junit = [
        {
            "module": "test_market_data_providers_live.py",
            "name": "test_openfigi_keyless_mapping",
            "outcome": "passed",
        }
    ]

    evidence = runner._provider_live_evidence(
        run_id="entitlement-run",
        providers={"demo"},
        junit_cases=junit,
        ledger_path=ledger,
    )
    assert evidence["complete"] is False
    assert any("explicit expected_entitlement_denial" in item for item in evidence["missing"])

    base_operation["dispositions"] = {"expected_entitlement_denial": 1}
    ledger.write_text(
        json.dumps(
            {
                "run_id": "entitlement-run",
                "usage_scope": "unit-scope",
                "provider": "demo",
                "http_requests": 1,
                "response_bytes": 10,
                "failed_operations": 0,
                "operation_usage": {"fetch_ohlcv": base_operation},
                "case_usage": {
                    case_id: {
                        "http_requests": 1,
                        "response_bytes": 10,
                        "operations": {"fetch_ohlcv": base_operation},
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence = runner._provider_live_evidence(
        run_id="entitlement-run",
        providers={"demo"},
        junit_cases=junit,
        ledger_path=ledger,
    )
    assert evidence["complete"] is True
    assert evidence["cases"][0]["disposition"] == "expected_entitlement_denial"


def test_finra_otc_live_admission_requires_source_evidence(monkeypatch):
    runner = _runner_module()
    monkeypatch.delenv("FINRA_OTC_SOURCE_KIND", raising=False)
    monkeypatch.delenv("FINRA_OTC_SOURCE_REVIEWED", raising=False)
    monkeypatch.delenv("FINRA_OTC_SOURCE_EVIDENCE", raising=False)
    monkeypatch.delenv("FINRA_OTC_OPERATION_COSTS", raising=False)
    monkeypatch.delenv("FINRA_OTC_TERMS_REVIEWED", raising=False)
    monkeypatch.delenv("FINRA_OTC_COMPLETENESS_REVIEWED", raising=False)
    monkeypatch.delenv("FINRA_OTC_REDISTRIBUTION_REVIEWED", raising=False)
    monkeypatch.delenv("FINRA_OTC_POLL_INTERVAL_SECONDS", raising=False)
    missing_controls = runner.routing_safety_preflight()["finra otc directory"]
    assert "FINRA_OTC_SOURCE_REVIEWED" in missing_controls
    assert "FINRA_OTC_OPERATION_COSTS" in missing_controls
    assert "FINRA_OTC_TERMS_REVIEWED" in missing_controls

    monkeypatch.setenv(
        "FINRA_OTC_OPERATION_COSTS",
        '{"discover_universe_page": 3, "reconcile_universe_page": 3}',
    )
    monkeypatch.setenv("FINRA_OTC_TERMS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_COMPLETENESS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_REDISTRIBUTION_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "900")
    assert "FINRA_OTC_SOURCE_REVIEWED" in runner.finra_otc_source_review_missing()
    assert "FINRA_OTC_SOURCE_EVIDENCE" in runner.finra_otc_source_review_missing()

    monkeypatch.setenv("FINRA_OTC_SOURCE_KIND", "legacy_candidate")
    assert any("FINRA_OTC_SOURCE_KIND" in item for item in runner.finra_otc_source_review_missing())
    monkeypatch.setenv("FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setenv("FINRA_OTC_SOURCE_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_SOURCE_EVIDENCE", "FINRA support case 123")
    monkeypatch.setenv(
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setenv(
        "FINRA_OTC_REVIEWED_SOURCE_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    inactive = (
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&"
        "file=EQUITYMASTERIN&facility=ORF"
    )
    monkeypatch.setenv("FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", inactive)
    monkeypatch.setenv("FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL", inactive)
    monkeypatch.setenv(
        "FINRA_OTC_OPERATION_COSTS", '{"discover_universe_page": 3, "reconcile_universe_page": 3}'
    )
    monkeypatch.setenv("FINRA_OTC_TERMS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_COMPLETENESS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_REDISTRIBUTION_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "900")
    monkeypatch.setenv("FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "reviewed no-CUSIP entitlement")
    result = runner.routing_safety_preflight()
    assert result["finra otc directory"] == "routable"
    monkeypatch.setenv(
        "FINRA_OTC_REVIEWED_SOURCE_URL",
        "https://api.finra.org/data/group/otcMarket/name/anotherDataset",
    )
    result = runner.routing_safety_preflight()
    assert "FINRA_OTC_REVIEWED_SOURCE_URL" in runner.finra_otc_source_review_missing()


def test_eodhd_live_admission_uses_documented_default_and_bounds_overrides(monkeypatch):
    runner = _runner_module()
    from app.config import settings

    monkeypatch.setenv("EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED", "true")
    monkeypatch.setenv(
        "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE", "unit-test provider terms exception"
    )

    for name in (
        "EODHD_REVIEWED_MINUTE_RESET",
        "EODHD_MINUTE_QUOTA_EVIDENCE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EODHD_REVIEWED_MINUTE_LIMIT", "0")
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 0)
    result = runner.routing_safety_preflight()
    assert result["eodhd"] == (
        "routable: conservative Free-plan 20-requests/minute ceiling enforced by a rolling 60-second envelope"
    )

    monkeypatch.setenv("EODHD_REVIEWED_MINUTE_LIMIT", "500")
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 500)
    result = runner.routing_safety_preflight()
    assert "EODHD_REVIEWED_MINUTE_RESET" in result["eodhd"]
    assert "EODHD_MINUTE_QUOTA_EVIDENCE" in result["eodhd"]

    monkeypatch.setenv("EODHD_REVIEWED_MINUTE_RESET", "rolling")
    monkeypatch.setenv("EODHD_MINUTE_QUOTA_EVIDENCE", "EODHD API limits documentation")
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "rolling")
    monkeypatch.setattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "EODHD API limits documentation")
    assert runner.routing_safety_preflight()["eodhd"] == (
        "routable: account-specific minute override has reviewed reset/evidence"
    )

    monkeypatch.setenv("EODHD_REVIEWED_MINUTE_LIMIT", "1200")
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 1200)
    assert runner.routing_safety_preflight()["eodhd"] == (
        "routable: account-specific minute override has reviewed reset/evidence"
    )


def test_edgar_safety_report_separates_published_ceiling_from_live_baseline(monkeypatch):
    runner = _runner_module()
    from app.config import settings

    monkeypatch.delenv("EDGAR_REVIEWED_RESET", raising=False)
    monkeypatch.delenv("EDGAR_QUOTA_EVIDENCE", raising=False)
    monkeypatch.setattr(settings, "EDGAR_REVIEWED_RESET", "")
    monkeypatch.setattr(settings, "EDGAR_QUOTA_EVIDENCE", "")

    status = runner.routing_safety_preflight()["edgar quota"]

    assert "contract verified" in status
    assert status.startswith("routable:")
    assert "10-requests/second" in status
    assert "10-minute throttle recovery hold" in status
    assert "active shared-scope usage baseline is checked separately" in status
    assert runner.live_required_safety_blockers({"edgar"}, {"edgar quota": status}) == {}


def test_marketstack_discovery_safety_requires_full_operation_and_archive_controls(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "false")
    names = (
        "MARKETSTACK_DISCOVERY_EXCHANGE",
        "MARKETSTACK_DISCOVERY_MAX_PAGE_COST",
        "MARKETSTACK_DISCOVERY_COST_EVIDENCE",
        "MARKETSTACK_REVIEWED_MONTHLY_LIMIT",
        "MARKETSTACK_REVIEWED_MONTHLY_RESET",
        "MARKETSTACK_QUOTA_EVIDENCE",
        "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
        "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
    )
    for name in names:
        monkeypatch.setenv(name, "")

    status = runner.routing_safety_preflight()["marketstack discovery"]
    assert "MARKETSTACK_DISCOVERY_EXCHANGE" in status
    assert "MARKETSTACK_DISCOVERY_MAX_PAGE_COST" in status
    assert "MARKETSTACK_DISCOVERY_COST_EVIDENCE" in status
    assert "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED" in status
    assert not status.startswith("routable")

    monkeypatch.setenv("MARKETSTACK_DISCOVERY_EXCHANGE", "XNAS")
    monkeypatch.setenv("MARKETSTACK_DISCOVERY_MAX_PAGE_COST", "1000")
    monkeypatch.setenv("MARKETSTACK_DISCOVERY_COST_EVIDENCE", "reviewed provider billing evidence")
    monkeypatch.setenv("MARKETSTACK_REVIEWED_MONTHLY_LIMIT", "100")
    monkeypatch.setenv("MARKETSTACK_REVIEWED_MONTHLY_RESET", "calendar_month_utc")
    monkeypatch.setenv("MARKETSTACK_QUOTA_EVIDENCE", "reviewed account quota evidence")
    monkeypatch.setenv("MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", "true")
    monkeypatch.setenv("MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE", "provider terms exception")

    assert runner.routing_safety_preflight()["marketstack discovery"] == "routable"


def test_marketstack_focused_live_safety_only_requires_selected_capability():
    runner = _runner_module()
    statuses = {
        "marketstack quota": "routable",
        "marketstack discovery": "non-routable: missing reviewed MIC and page cost",
    }

    assert (
        runner.live_required_safety_blockers(
            {"marketstack"},
            statuses,
            operations_by_provider={"marketstack": {"fetch_ohlcv", "get_current_price"}},
        )
        == {}
    )
    assert runner.live_required_safety_blockers(
        {"marketstack"},
        statuses,
        operations_by_provider={"marketstack": {"discover_universe_page"}},
    ) == {"marketstack": [statuses["marketstack discovery"]]}
    assert runner.live_required_safety_blockers({"marketstack"}, statuses) == {
        "marketstack": [statuses["marketstack discovery"]]
    }


def test_coingecko_live_admission_requires_written_archive_rights(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "false")
    controls = (
        "COINGECKO_MARKET_DATA_USE_AUTHORIZED",
        "COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "COINGECKO_MARKET_DATA_USE_REVIEWED_AT",
    )
    for name in (*controls, "COINGECKO_MARKET_DATA_USE_EXPIRES_AT"):
        monkeypatch.setenv(name, "")

    status = runner.routing_safety_preflight()["coingecko market-data use"]

    assert "COINGECKO_MARKET_DATA_USE_AUTHORIZED" in status
    assert "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE" in status
    assert "coingecko" in runner.LIVE_PREFLIGHT_ROUTING_CONTROLS

    monkeypatch.setenv("COINGECKO_MARKET_DATA_USE_AUTHORIZED", "true")
    monkeypatch.setenv("COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE", "written provider approval")
    monkeypatch.setenv(
        "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "written_api_use_archive_audience_attribution_and_retention_after_termination",
    )
    monkeypatch.setenv("COINGECKO_MARKET_DATA_USE_REVIEWED_AT", "2026-10-01T00:00:00+00:00")
    monkeypatch.setenv("COINGECKO_MARKET_DATA_USE_EXPIRES_AT", "")
    assert runner.routing_safety_preflight()["coingecko market-data use"] == "routable"


def test_owner_terms_risk_decision_clears_only_terms_gates(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "false")
    assert (
        "fred",
        "test_market_data_providers_live.py",
        "test_fred_series_requires_persisted_data_rights_before_network_access",
    ) in runner.active_live_no_request_cases()
    assert (
        "fred",
        "test_market_data_providers_live.py",
        "test_fred_credentialed_current_value",
    ) in runner.active_live_no_request_cases()
    assert (
        "coinbase",
        "test_market_data_providers_live.py",
        "test_coinbase_keyless_crypto_history",
    ) in runner.active_live_no_request_cases()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "true")

    # The owner setting bypasses provider terms only; the published 120/minute
    # contract and rolling local cap remain the configured quota controls.
    for name, value in (
        ("FRED_REVIEWED_LIMIT_SCOPE", ""),
        ("FRED_REVIEWED_REQUESTS_PER_MINUTE", "0"),
        ("FRED_REVIEWED_QUOTA_EVIDENCE", ""),
        ("FRED_REVIEWED_RESET", ""),
        ("FRED_RESET_EVIDENCE", ""),
        ("FRED_APPLICATION_USER_SCOPE", ""),
        ("FRED_APPLICATION_USER_SCOPE_EVIDENCE", ""),
        ("FRED_AUTOMATED_USE_AUTHORIZED", "false"),
        ("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", ""),
        ("FRED_SERIES_RIGHTS_EVIDENCE", "{}"),
    ):
        monkeypatch.setenv(name, value)

    status = runner.routing_safety_preflight()
    assert status["fred"].startswith("routable: published 120-requests/minute ceiling")
    assert "FRED_APPLICATION_USER_SCOPE" not in status["fred"]
    assert "FRED_AUTOMATED_USE_AUTHORIZED" not in status["fred"]
    assert "FRED_SERIES_RIGHTS_EVIDENCE" not in status["fred"]
    assert "provider terms" not in status["fred"].lower()

    for name, value in (
        ("FRED_REVIEWED_LIMIT_SCOPE", "api_key"),
        ("FRED_REVIEWED_REQUESTS_PER_MINUTE", "120"),
        ("FRED_REVIEWED_QUOTA_EVIDENCE", "documented per-key limit"),
        ("FRED_REVIEWED_RESET", "rolling"),
        ("FRED_RESET_EVIDENCE", "documented rolling window"),
    ):
        monkeypatch.setenv(name, value)
    status = runner.routing_safety_preflight()
    assert status["fred"].startswith("routable: published 120-requests/minute ceiling")
    assert status["coinbase market-data use"] == "routable"
    active_no_request_cases = runner.active_live_no_request_cases()
    assert (
        "fred",
        "test_market_data_providers_live.py",
        "test_fred_series_requires_persisted_data_rights_before_network_access",
    ) not in active_no_request_cases
    assert (
        "fred",
        "test_market_data_providers_live.py",
        "test_fred_credentialed_current_value",
    ) not in active_no_request_cases
    assert (
        "coinbase",
        "test_market_data_providers_live.py",
        "test_coinbase_keyless_crypto_history",
    ) not in active_no_request_cases
    assert (
        "coinbase",
        "test_market_data_providers_live.py",
        "test_coinbase_keyless_history_quote_and_usd_products",
    ) not in active_no_request_cases
    assert not {
        "fetch_ohlcv",
        "get_current_price",
        "discover_universe_page",
    } & set(runner.LIVE_OPERATION_DISPOSITIONS.get("coinbase", {}))


def test_bybit_public_data_status_reports_only_egress_control(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "true")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", "false")
    monkeypatch.setenv("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", "")

    status = runner.routing_safety_preflight()["bybit_xstocks"]

    assert "permitted request egress" in status
    assert "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED" in status
    assert "user jurisdiction" not in status


def test_owner_terms_risk_default_matches_application_configuration(monkeypatch):
    runner = _runner_module()
    from app.config import settings

    monkeypatch.delenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", raising=False)
    assert (
        runner.owner_accepts_provider_terms_risk()
        is settings.PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK
    )


def test_fmp_code_default_byte_budgets_satisfy_live_safety_configuration(monkeypatch):
    runner = _runner_module()
    monkeypatch.delenv("FMP_OPERATION_BYTE_BOUNDS", raising=False)
    status = runner.routing_safety_preflight()["fmp"]
    assert "FMP_OPERATION_BYTE_BOUNDS" not in status


def test_owner_archive_risk_decision_bypasses_provider_terms_gates(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "true")
    for prefix in ("FMP", "TIINGO"):
        monkeypatch.setenv(f"{prefix}_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", "false")
        monkeypatch.setenv(f"{prefix}_PROVIDER_ARCHIVE_TERMS_EVIDENCE", "")

    statuses = runner.routing_safety_preflight()
    for provider, prefix, status_key in (
        ("fmp", "FMP", "fmp"),
        ("tiingo", "TIINGO", "tiingo provider controls"),
    ):
        assert f"{prefix}_PROVIDER_ARCHIVE_TERMS_AUTHORIZED" not in statuses[status_key]
        assert f"{prefix}_PROVIDER_ARCHIVE_TERMS_EVIDENCE" not in statuses[status_key]
        assert provider in runner.LIVE_PREFLIGHT_ROUTING_CONTROLS
    assert "tiingo" not in statuses
    assert "tiingo provider controls" in statuses
    assert "tiingo account plan" in statuses


def test_marketdata_app_and_twelve_data_live_probes_require_archive_terms(
    monkeypatch,
):
    runner = _runner_module()
    monkeypatch.setenv("PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", "false")
    for prefix, suffix in (
        ("MARKETDATA_APP", "PROVIDER_RETENTION_TERMS"),
        ("TWELVE_DATA", "PROVIDER_ARCHIVE_TERMS"),
    ):
        monkeypatch.setenv(f"{prefix}_{suffix}_AUTHORIZED", "false")
        monkeypatch.setenv(f"{prefix}_{suffix}_EVIDENCE", "")

    statuses = runner.routing_safety_preflight()
    for prefix, suffix, status_key in (
        ("MARKETDATA_APP", "PROVIDER_RETENTION_TERMS", "marketdata.app persistent archive"),
        ("TWELVE_DATA", "PROVIDER_ARCHIVE_TERMS", "twelve_data persistent archive"),
    ):
        assert status_key in statuses
        assert f"{prefix}_{suffix}_AUTHORIZED" in statuses[status_key]
    assert runner.LIVE_PREFLIGHT_ROUTING_CONTROLS["marketdata_app"] == (
        "marketdata.app persistent archive",
    )
    assert runner.LIVE_PREFLIGHT_ROUTING_CONTROLS["twelve_data"] == (
        "twelve_data persistent archive",
    )

    for prefix, suffix in (
        ("MARKETDATA_APP", "PROVIDER_RETENTION_TERMS"),
        ("TWELVE_DATA", "PROVIDER_ARCHIVE_TERMS"),
    ):
        monkeypatch.setenv(f"{prefix}_{suffix}_AUTHORIZED", "true")
        monkeypatch.setenv(f"{prefix}_{suffix}_EVIDENCE", "provider terms exception")
    statuses = runner.routing_safety_preflight()
    assert (
        statuses["marketdata.app persistent archive"]
        == "routable: current provider terms allow the configured use"
    )
    assert (
        statuses["twelve_data persistent archive"]
        == "routable: current provider terms allow the configured use"
    )


def test_eodhd_and_marketstack_live_probes_require_nonroutable_controls():
    runner = _runner_module()

    assert runner.LIVE_PREFLIGHT_ROUTING_CONTROLS["eodhd"] == ("eodhd",)
    assert runner.LIVE_PREFLIGHT_ROUTING_CONTROLS["marketstack"] == (
        "marketstack quota",
        "marketstack discovery",
    )


def test_marketdata_app_history_safety_diagnostic_reports_dynamic_date_bound():
    runner = _runner_module()

    status = runner.routing_safety_preflight()["marketdata.app option quote history"]

    assert status.startswith("routable for bounded calls:")
    assert "inclusive-calendar-date credit estimate" in status
    assert "no unbounded request" in status
    assert "fixed-cost fallback" in status


def test_staged_candidate_with_clean_index_returns_tree_identity():
    runner = _runner_module()
    candidate, error = runner._staged_candidate_from_git_state(
        status_output=(
            "M  backend/app/providers/finra.py\n" "A  backend/tests/live/test_provider.py\n"
        ),
        unstaged_diff_exit_code=0,
        untracked_output="",
        staged_diff_output="",
        staged_paths=(
            "backend/app/providers/finra.py",
            "backend/tests/live/test_provider.py",
        ),
        tree_sha="a" * 40,
        parent_sha="b" * 40,
    )

    assert error is None
    assert candidate == {"tree_sha": "a" * 40, "parent_sha": "b" * 40}


def test_staged_candidate_allows_unstaged_current_workstream_notes_only():
    runner = _runner_module()
    workstream_prefix = "ops/workstreams/feat-market-data-provider-platform/"
    base = {
        "unstaged_diff_exit_code": 1,
        "workstream_prefix": workstream_prefix,
        "untracked_output": "",
        "staged_paths": (
            "backend/app/providers/finra.py",
            f"{workstream_prefix}handoff.md",
        ),
        "staged_diff_output": "",
        "tree_sha": "a" * 40,
        "parent_sha": "b" * 40,
    }

    candidate, error = runner._staged_candidate_from_git_state(
        status_output=("M  backend/app/providers/finra.py\n" f"MM {workstream_prefix}handoff.md\n"),
        **base,
    )
    _, unrelated_worktree_change = runner._staged_candidate_from_git_state(
        status_output=("MM backend/app/providers/finra.py\n" f"M  {workstream_prefix}handoff.md\n"),
        **base,
    )
    _, other_workstream_change = runner._staged_candidate_from_git_state(
        status_output="MM ops/workstreams/another-branch/handoff.md\n",
        **{
            **base,
            "staged_paths": ("ops/workstreams/another-branch/handoff.md",),
        },
    )
    _, unstaged_only_workstream = runner._staged_candidate_from_git_state(
        status_output=f" M {workstream_prefix}handoff.md\n",
        **{**base, "staged_paths": ("backend/app/providers/finra.py",)},
    )

    assert error is None
    assert candidate == {"tree_sha": "a" * 40, "parent_sha": "b" * 40}
    assert unrelated_worktree_change == "working-tree changes are not fully staged"
    assert other_workstream_change == "working-tree changes are not fully staged"
    assert unstaged_only_workstream == "Git status contained a path with no staged change"


def test_staged_candidate_rejects_unstaged_untracked_and_secret_paths():
    runner = _runner_module()
    base = {
        "unstaged_diff_exit_code": 0,
        "untracked_output": "",
        "staged_paths": ("backend/app/providers/finra.py",),
        "staged_diff_output": "",
        "tree_sha": "a" * 40,
        "parent_sha": "b" * 40,
    }

    _, unstaged = runner._staged_candidate_from_git_state(
        status_output="MM backend/app/providers/finra.py\n",
        **{**base, "unstaged_diff_exit_code": 1},
    )
    _, untracked = runner._staged_candidate_from_git_state(
        status_output="M  backend/app/providers/finra.py\n",
        **{**base, "untracked_output": "backend/tests/live/new_case.py\n"},
    )
    _, secret_path = runner._staged_candidate_from_git_state(
        status_output="A  backend/.env.staging\n",
        **{**base, "staged_paths": ("backend/.env.staging",)},
    )
    _, credential_path = runner._staged_candidate_from_git_state(
        status_output="A  config/credentials.json\n",
        **{**base, "staged_paths": ("config/credentials.json",)},
    )

    assert unstaged == "working-tree changes are not fully staged"
    assert untracked == "untracked files must be staged or excluded before candidate validation"
    assert (
        secret_path == "credential-bearing path is prohibited in a candidate: backend/.env.staging"
    )
    assert (
        credential_path
        == "credential-bearing path is prohibited in a candidate: config/credentials.json"
    )


def test_candidate_source_unchanged_ignores_provider_receipt_metadata():
    runner = _runner_module()

    expected = {
        "tree_sha": "a" * 40,
        "parent_sha": "b" * 40,
        "provider": "finra_otc_directory",
    }
    same_git_snapshot = {"tree_sha": "a" * 40, "parent_sha": "b" * 40}
    changed_tree = {"tree_sha": "c" * 40, "parent_sha": "b" * 40}
    changed_parent = {"tree_sha": "a" * 40, "parent_sha": "d" * 40}

    assert runner._candidate_source_unchanged(expected, same_git_snapshot, None)
    assert not runner._candidate_source_unchanged(expected, changed_tree, None)
    assert not runner._candidate_source_unchanged(expected, changed_parent, None)
    assert not runner._candidate_source_unchanged(expected, None, "snapshot failed")


def test_candidate_provider_receipts_aggregate_only_complete_same_tree_manifests(
    tmp_path, monkeypatch
):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "LIVE_REQUIRED_OPERATIONS",
        {"demo": {"fetch_ohlcv", "get_current_price"}},
    )
    receipt = {
        "at": "2026-10-09T22:00:00+00:00",
        "kind": "provider_live_matrix",
        "scope": "provider_candidate",
        "result": "staged_candidate_provider_passed",
        "providers_selected": ["demo"],
        "providers_run": ["demo"],
        "candidate_unchanged": True,
        "candidate_tree_sha": "a" * 40,
        "candidate_parent_sha": "b" * 40,
        "live_acceptance": False,
        "exit_code": 0,
        "case_count": 2,
        "failed_cases": 0,
        "skipped_cases": 0,
        "live_evidence": {
            "complete": True,
            "providers": {
                "demo": {
                    "operations": {
                        "fetch_ohlcv": {"passed": True},
                        "get_current_price": {"passed": True},
                    }
                }
            },
        },
    }
    path = tmp_path / "candidate-receipts.jsonl"
    path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    verified = runner.verify_candidate_provider_receipts(
        path,
        candidate_tree_sha="a" * 40,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )

    assert verified["complete"] is True
    assert verified["providers_verified"] == ["demo"]
    assert verified["provider_http_requests"] == 0


def _dinari_candidate_canary_receipt(runner):
    case = f"{runner.DINARI_CANARY_CASE[0]}::{runner.DINARI_CANARY_CASE[1]}"
    return {
        "at": "2026-10-11T00:00:00+00:00",
        "kind": "provider_live_matrix",
        "scope": "provider_candidate_canary",
        "result": "staged_candidate_canary_passed",
        "providers_selected": ["dinari"],
        "providers_run": ["dinari"],
        "selected_cases": {},
        "canary_mode": "dinari_sandbox",
        "canary_max_requests": 1,
        "candidate_unchanged": True,
        "candidate_tree_sha": "a" * 40,
        "candidate_parent_sha": "b" * 40,
        "live_acceptance": False,
        "exit_code": 0,
        "case_count": 1,
        "passed_cases": 1,
        "failed_cases": 0,
        "skipped_cases": 0,
        "live_evidence": {
            "complete": True,
            "providers": {
                "dinari": {
                    "operations": {
                        runner.DINARI_CANARY_OPERATION: {
                            "passed": True,
                            "http_requests": 1,
                            "response_bytes": 100,
                            "failed_operations": 0,
                        }
                    }
                }
            },
            "cases": [
                {
                    "case": case,
                    "disposition": "live_required",
                    "pytest": "passed",
                    "http_requests": 1,
                }
            ],
            "provider_safety_dispositions": {
                "dinari": {
                    "kind": "intentional_no_request_policy",
                    "reason": runner.DINARI_CANARY_SAFETY_REASON,
                }
            },
        },
    }


def test_dinari_candidate_canary_receipt_does_not_satisfy_full_provider_gate(tmp_path):
    runner = _runner_module()
    receipt = _dinari_candidate_canary_receipt(runner)
    path = tmp_path / "dinari-candidate.jsonl"
    path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    verified = runner.verify_candidate_provider_receipts(
        path,
        candidate_tree_sha="a" * 40,
        candidate_parent_sha="b" * 40,
        required_providers={"dinari"},
    )

    assert verified["complete"] is False
    assert verified["providers_verified"] == []
    assert verified["provider_canaries_verified"] == ["dinari"]
    assert any("does not satisfy full provider acceptance" in item for item in verified["missing"])

    receipt["live_evidence"]["providers"]["dinari"]["operations"][runner.DINARI_CANARY_OPERATION][
        "http_requests"
    ] = 2
    path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    rejected = runner.verify_candidate_provider_receipts(
        path,
        candidate_tree_sha="a" * 40,
        candidate_parent_sha="b" * 40,
        required_providers={"dinari"},
    )
    assert rejected["complete"] is False
    assert rejected["provider_canaries_verified"] == []
    assert any("exactly one successful read" in item for item in rejected["missing"])


def test_candidate_canary_receipt_writer_records_dinari_scope_and_one_request(
    tmp_path, monkeypatch
):
    runner = _runner_module()
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    receipt_path = tmp_path / "state" / "provider-canary-receipts.jsonl"

    result = runner._record_live_validation(
        providers=["dinari"],
        exit_code=0,
        missing={},
        counts={
            "case_count": 1,
            "passed_cases": 1,
            "failed_cases": 0,
            "skipped_cases": 0,
        },
        approved_deferrals={},
        live_evidence=_dinari_candidate_canary_receipt(runner)["live_evidence"],
        candidate_tree={
            "tree_sha": "a" * 40,
            "parent_sha": "b" * 40,
            "provider": "dinari",
        },
        candidate_unchanged=True,
        canary_mode=True,
        candidate_receipt_file=receipt_path,
    )

    persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result == "staged_candidate_canary_passed"
    assert persisted["scope"] == "provider_candidate_canary"
    assert persisted["canary_max_requests"] == 1
    assert persisted["live_acceptance"] is False
    assert receipt_path.stat().st_mode & 0o777 == 0o600


def test_candidate_provider_receipts_aggregate_complete_quota_bounded_case_slices(
    tmp_path, monkeypatch
):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "LIVE_REQUIRED_OPERATIONS",
        {"demo": {"read_a", "read_b"}},
    )
    monkeypatch.setattr(
        runner,
        "LIVE_PROVIDER_CASES",
        {"demo": [("test_live.py", "test_read_a"), ("test_live.py", "test_read_b")]},
    )
    monkeypatch.setattr(
        runner,
        "LIVE_CASE_OPERATIONS",
        {"demo": {"test_read_a": {"read_a"}, "test_read_b": {"read_b"}}},
    )
    receipts = []
    for index, (case_name, operation) in enumerate(
        (("test_read_a", "read_a"), ("test_read_b", "read_b"))
    ):
        receipts.append(
            {
                "at": f"2026-10-09T22:0{index}:00+00:00",
                "kind": "provider_live_matrix",
                "scope": "provider_candidate_case",
                "result": "staged_candidate_case_passed",
                "providers_selected": ["demo"],
                "providers_run": ["demo"],
                "selected_cases": {"demo": [case_name]},
                "candidate_unchanged": True,
                "candidate_tree_sha": "a" * 40,
                "candidate_parent_sha": "b" * 40,
                "live_acceptance": False,
                "exit_code": 0,
                "case_count": 1,
                "failed_cases": 0,
                "skipped_cases": 0,
                "live_evidence": {
                    "complete": True,
                    "providers": {"demo": {"operations": {operation: {"passed": True}}}},
                },
            }
        )
    path = tmp_path / "candidate-case-receipts.jsonl"
    path.write_text(
        "".join(json.dumps(receipt) + "\n" for receipt in receipts),
        encoding="utf-8",
    )

    verified = runner.verify_candidate_provider_receipts(
        path,
        candidate_tree_sha="a" * 40,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )

    assert verified["complete"] is True
    assert verified["providers_verified"] == ["demo"]


def test_candidate_provider_case_receipts_require_every_manifest_case(tmp_path, monkeypatch):
    runner = _runner_module()
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"demo": {"read_a", "read_b"}})
    monkeypatch.setattr(
        runner,
        "LIVE_PROVIDER_CASES",
        {"demo": [("test_live.py", "test_read_a"), ("test_live.py", "test_read_b")]},
    )
    monkeypatch.setattr(
        runner,
        "LIVE_CASE_OPERATIONS",
        {"demo": {"test_read_a": {"read_a"}, "test_read_b": {"read_b"}}},
    )
    receipt = {
        "at": "2026-10-09T22:00:00+00:00",
        "kind": "provider_live_matrix",
        "scope": "provider_candidate_case",
        "result": "staged_candidate_case_passed",
        "providers_selected": ["demo"],
        "providers_run": ["demo"],
        "selected_cases": {"demo": ["test_read_a"]},
        "candidate_unchanged": True,
        "candidate_tree_sha": "a" * 40,
        "candidate_parent_sha": "b" * 40,
        "live_acceptance": False,
        "exit_code": 0,
        "case_count": 1,
        "failed_cases": 0,
        "skipped_cases": 0,
        "live_evidence": {
            "complete": True,
            "providers": {"demo": {"operations": {"read_a": {"passed": True}}}},
        },
    }
    path = tmp_path / "incomplete-case-receipts.jsonl"
    path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    verified = runner.verify_candidate_provider_receipts(
        path,
        candidate_tree_sha="a" * 40,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )

    assert verified["complete"] is False
    assert any("missing passing manifest cases" in item for item in verified["missing"])


def test_candidate_receipts_survive_only_non_contract_workstream_updates(tmp_path, monkeypatch):
    runner = _runner_module()
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    validation = root / "ops/workstreams/feat-market-data-provider-platform/validation.jsonl"
    validation.parent.mkdir(parents=True)
    validation.write_text('{"result":"before"}\n', encoding="utf-8")
    handoff = validation.with_name("handoff.md")
    handoff.write_text("# Handoff\n\nBefore.\n", encoding="utf-8")
    session = validation.with_name("session.json")
    session.write_text(
        json.dumps(
            {
                "acceptance": {"criteria": "v1"},
                "last_human_progress_update": "2026-10-09T22:00:00Z",
                "progress": {
                    "current_blocker": "before",
                    "current_phase": "before",
                    "next_action": "before",
                    "updated_at": "2026-10-09T22:00:00Z",
                    "completed": [],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "source.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    original_tree = subprocess.run(
        ["git", "-C", str(root), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with validation.open("a", encoding="utf-8") as stream:
        stream.write('{"result":"new-preflight"}\n')
    with handoff.open("a", encoding="utf-8") as stream:
        stream.write("\nAfter.\n")
    session_state = json.loads(session.read_text(encoding="utf-8"))
    session_state["progress"].update(
        {
            "current_blocker": "after",
            "current_phase": "after",
            "next_action": "after",
            "updated_at": "2026-10-09T23:00:00Z",
        }
    )
    session_state["last_human_progress_update"] = "2026-10-09T23:00:00Z"
    session.write_text(json.dumps(session_state) + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    appended_tree = subprocess.run(
        ["git", "-C", str(root), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"demo": {"read"}})
    receipt = {
        "at": "2026-10-09T22:00:00+00:00",
        "kind": "provider_live_matrix",
        "scope": "provider_candidate",
        "result": "staged_candidate_provider_passed",
        "providers_selected": ["demo"],
        "providers_run": ["demo"],
        "candidate_unchanged": True,
        "candidate_tree_sha": original_tree,
        "candidate_parent_sha": "b" * 40,
        "live_acceptance": False,
        "exit_code": 0,
        "case_count": 1,
        "failed_cases": 0,
        "skipped_cases": 0,
        "live_evidence": {
            "complete": True,
            "providers": {"demo": {"operations": {"read": {"passed": True}}}},
        },
    }
    receipts = tmp_path / "receipts.jsonl"
    receipts.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    verified = runner.verify_candidate_provider_receipts(
        receipts,
        candidate_tree_sha=appended_tree,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )
    assert verified["complete"] is True

    session_state["acceptance"]["criteria"] = "v2"
    session.write_text(json.dumps(session_state) + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    changed_acceptance_tree = subprocess.run(
        ["git", "-C", str(root), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    rejected_acceptance = runner.verify_candidate_provider_receipts(
        receipts,
        candidate_tree_sha=changed_acceptance_tree,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )
    assert rejected_acceptance["complete"] is False

    session_state["acceptance"]["criteria"] = "v1"
    session.write_text(json.dumps(session_state) + "\n", encoding="utf-8")
    (root / "source.py").write_text("value = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    changed_source_tree = subprocess.run(
        ["git", "-C", str(root), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    rejected = runner.verify_candidate_provider_receipts(
        receipts,
        candidate_tree_sha=changed_source_tree,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )
    assert rejected["complete"] is False
    assert any(
        "no receipt matches the current candidate tree" in item for item in rejected["missing"]
    )


def test_candidate_receipt_writer_persists_only_redacted_success_outside_worktree(
    tmp_path, monkeypatch
):
    runner = _runner_module()
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    receipt_path = tmp_path / "state" / "provider-receipts.jsonl"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.touch(mode=0o644)
    receipt_path.chmod(0o644)

    result = runner._record_live_validation(
        providers=["demo"],
        exit_code=0,
        missing={},
        counts={
            "case_count": 1,
            "passed_cases": 1,
            "failed_cases": 0,
            "skipped_cases": 0,
        },
        approved_deferrals={},
        live_evidence={
            "complete": True,
            "providers": {"demo": {"operations": {"read": {"passed": True, "http_requests": 1}}}},
        },
        candidate_tree={
            "tree_sha": "a" * 40,
            "parent_sha": "b" * 40,
            "provider": "demo",
        },
        candidate_unchanged=True,
        candidate_receipt_file=receipt_path,
        max_http_requests=7,
        admitted_http_transports=4,
    )

    persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result == "staged_candidate_provider_passed"
    assert persisted["candidate_unchanged"] is True
    assert persisted["live_acceptance"] is False
    assert persisted["transport_budget"] == {
        "max_http_requests": 7,
        "admitted_http_transports": 4,
    }
    assert receipt_path.stat().st_mode & 0o777 == 0o600


def test_candidate_receipt_writer_persists_exact_case_slice_without_acceptance(
    tmp_path, monkeypatch
):
    runner = _runner_module()
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    receipt_path = tmp_path / "state" / "provider-case-receipts.jsonl"
    result = runner._record_live_validation(
        providers=["demo"],
        exit_code=0,
        missing={},
        counts={
            "case_count": 1,
            "passed_cases": 1,
            "failed_cases": 0,
            "skipped_cases": 0,
        },
        approved_deferrals={},
        live_evidence={
            "complete": True,
            "providers": {"demo": {"operations": {"read": {"passed": True}}}},
        },
        candidate_tree={
            "tree_sha": "a" * 40,
            "parent_sha": "b" * 40,
            "provider": "demo",
        },
        candidate_unchanged=True,
        selected_cases={"demo": {"test_read"}},
        candidate_receipt_file=receipt_path,
    )

    persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result == "staged_candidate_case_passed"
    assert persisted["scope"] == "provider_candidate_case"
    assert persisted["selected_cases"] == {"demo": ["test_read"]}
    assert persisted["live_acceptance"] is False


def test_candidate_receipt_writer_rejects_source_worktree_path(tmp_path, monkeypatch):
    runner = _runner_module()
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])

    with pytest.raises(ValueError, match="outside the source worktree"):
        runner._record_live_validation(
            providers=["demo"],
            exit_code=0,
            missing={},
            counts={
                "case_count": 1,
                "passed_cases": 1,
                "failed_cases": 0,
                "skipped_cases": 0,
            },
            approved_deferrals={},
            live_evidence={"complete": True, "providers": {}},
            candidate_tree={
                "tree_sha": "a" * 40,
                "parent_sha": "b" * 40,
                "provider": "demo",
            },
            candidate_unchanged=True,
            candidate_receipt_file=root / "receipts.jsonl",
        )


def test_candidate_receipt_cli_verifies_staged_tree_without_live_opt_in(
    tmp_path, monkeypatch, capsys
):
    runner = _runner_module()
    receipt_file = tmp_path / "provider-candidate.jsonl"
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            verify_candidate_receipts=receipt_file,
            allow_staged_candidate=False,
            provider=None,
            case=[],
            account_usage_only=False,
            dinari_sandbox_canary=False,
            candidate_receipt_file=None,
            preflight_only=False,
        ),
    )
    monkeypatch.setattr(
        runner,
        "_staged_candidate_snapshot",
        lambda: ({"tree_sha": "a" * 40, "parent_sha": "b" * 40}, None),
    )
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"demo": (("x", "y"),)})
    monkeypatch.setattr(
        runner,
        "verify_candidate_provider_receipts",
        lambda path, **kwargs: {
            "complete": True,
            "candidate_tree_sha": kwargs["candidate_tree_sha"],
            "provider_http_requests": 0,
        },
    )

    assert runner.main() == 0
    assert '"provider_http_requests": 0' in capsys.readouterr().out


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("candidate_tree_sha", "c" * 40, "no receipt matches the current candidate tree"),
        ("candidate_unchanged", False, "candidate changed during"),
        ("result", "staged_candidate_failed", "manifest did not pass"),
        ("live_acceptance", True, "invalid acceptance scope"),
    ],
)
def test_candidate_provider_receipt_rejects_untrustworthy_evidence(
    tmp_path, monkeypatch, field, value, reason
):
    runner = _runner_module()
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"demo": {"read"}})
    receipt = {
        "at": "2026-10-09T22:00:00+00:00",
        "kind": "provider_live_matrix",
        "scope": "provider_candidate",
        "result": "staged_candidate_provider_passed",
        "providers_selected": ["demo"],
        "providers_run": ["demo"],
        "candidate_unchanged": True,
        "candidate_tree_sha": "a" * 40,
        "candidate_parent_sha": "b" * 40,
        "live_acceptance": False,
        "exit_code": 0,
        "case_count": 1,
        "failed_cases": 0,
        "skipped_cases": 0,
        "live_evidence": {
            "complete": True,
            "providers": {"demo": {"operations": {"read": {"passed": True}}}},
        },
    }
    receipt[field] = value
    path = tmp_path / "candidate-receipts.jsonl"
    path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    verified = runner.verify_candidate_provider_receipts(
        path,
        candidate_tree_sha="a" * 40,
        candidate_parent_sha="b" * 40,
        required_providers={"demo"},
    )

    assert verified["complete"] is False
    assert any(reason in item for item in verified["missing"])


def test_staged_candidate_scans_added_content_without_printing_secret_values(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "configured-very-secret-key")

    configured_secret = runner.staged_secret_findings(
        "+ALPHA_VANTAGE_API_KEY=configured-very-secret-key\n"
    )
    shaped_secret = runner.staged_secret_findings(
        "+MARKETDATA_APP_API_KEY=unusuallyLongOpaqueCredentialValue123\n"
    )
    placeholder = runner.staged_secret_findings("+MASSIVE_API_KEY=your_massive_api_key_here\n")

    assert configured_secret == ["ALPHA_VANTAGE_API_KEY"]
    assert shaped_secret == ["MARKETDATA_APP_API_KEY"]
    assert placeholder == []


def test_staged_secret_scan_does_not_treat_runtime_expressions_as_secret_values():
    runner = _runner_module()

    findings = runner.staged_secret_findings(
        '+current_refresh_token = source.get("refresh_token")\n'
        '+payload["refresh_token"] = str(response.get("refresh_token"))\n'
        "+token = provider.fetch_runtime_token()\n"
    )

    assert findings == []


def test_staged_secret_scan_still_rejects_quoted_and_unquoted_secret_literals():
    runner = _runner_module()

    findings = runner.staged_secret_findings(
        '+current_refresh_token = "opaqueCredentialLiteralValue123"\n'
        '+"client_secret": "opaqueJsonSecretLiteralValue456"\n'
        "+FINRA_CLIENT_SECRET=opaqueEnvSecretLiteralValue789\n"
    )

    assert findings == ["current_refresh_token", "client_secret", "FINRA_CLIENT_SECRET"]


def test_every_workflow_secret_is_scanned_and_redacted(monkeypatch):
    runner = _runner_module()
    names = runner.workflow_secret_environment_names()
    assert names
    for name in names:
        value = f"workflow-secret-{name.lower()}-value"
        monkeypatch.setenv(name, value)
        assert name in runner.staged_secret_findings("plain-text addition\n" + value)
        assert value not in runner.redact_runner_output("provider error: " + value)


def test_binary_staged_content_is_scanned_for_exact_configured_credentials(monkeypatch):
    runner = _runner_module()
    secret = b"binary-private-openfigi-value"
    monkeypatch.setenv("OPENFIGI_API_KEY", secret.decode("ascii"))

    findings = runner.staged_secret_findings(
        "",
        staged_content=b"\x00\xffpublic-prefix" + secret + b"public-suffix\x00",
    )

    assert findings == ["OPENFIGI_API_KEY"]


def test_staged_candidate_detects_credentialed_database_urls_without_local_value(monkeypatch):
    runner = _runner_module()
    monkeypatch.delenv("PROVIDER_QUOTA_LEDGER_DATABASE_URL", raising=False)
    credentialed_dsn = (
        "+PROVIDER_QUOTA_LEDGER_DATABASE_URL="
        "postgresql+psycopg2://candidate_user:"
        "candidate-password@quota.example:5432/ledger\n"
    )

    findings = runner.staged_secret_findings(credentialed_dsn)

    assert "PROVIDER_QUOTA_LEDGER_DATABASE_URL" in findings
    assert "credentialed database URL" in findings
    assert "candidate-password" not in str(findings)


def test_staged_secret_scan_allows_non_secret_provider_endpoint_urls_and_local_examples():
    runner = _runner_module()
    assert (
        runner.staged_secret_findings(
            "+FINRA_OTC_SYMBOL_DIRECTORY_URL=https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF\n"
            "+IBKR_READ_ONLY_URL=https://gateway.example.test\n"
        )
        == []
    )
    example_dsn = "postgresql+asyncpg://" + ("postgres:postgres@postgres:5432/chartingdb")
    assert runner.staged_secret_findings("DATABASE_URL=" + example_dsn + "\n") == []


def test_github_live_quota_preflight_rejects_ephemeral_sqlite(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv(
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "sqlite:////tmp/ephemeral-provider-quota.sqlite3"
    )

    ready, missing = runner.durable_quota_preflight()

    assert ready is False
    assert (
        missing == "PROVIDER_QUOTA_LEDGER_DATABASE_URL (persistent PostgreSQL coordinator required)"
    )


def test_quota_preflight_preserves_safe_coordinator_diagnostic(monkeypatch):
    runner = _runner_module()
    # This case exercises the coordinator's redacted diagnostic path. The
    # distinct GitHub-only PostgreSQL guard is covered below.
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    from app.services.provider_quota_coordinator import ProviderQuotaCoordinatorError

    def fail(*, require_persistent_coordinator=False):
        del require_persistent_coordinator
        raise ProviderQuotaCoordinatorError("provider quota ledger directory must be private")

    monkeypatch.setattr(runner, "ensure_provider_quota_coordinator", fail, raising=False)
    # The function imports the coordinator lazily, so patch the source module
    # rather than relying on a runner-local symbol.
    import app.services.provider_quota_coordinator as coordinator

    monkeypatch.setattr(coordinator, "ensure_provider_quota_coordinator", fail)
    ready, missing = runner.durable_quota_preflight()

    assert ready is False
    assert missing == "provider quota ledger directory must be private"


def test_live_operation_quota_preflight_requires_each_selected_active_baseline(
    monkeypatch,
):
    from app import config
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"demo": {"fetch_ohlcv"}})
    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "api_key",
            "quota_contract": {
                "reset": "calendar_day_utc",
                "dimensions": [
                    {
                        "name": "requests_per_day",
                        "limit": 10,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "demo-account",
                    }
                ],
            },
        },
    )

    def reviewed_plan(*_args, **_kwargs):
        return (
            "calendar_day_utc",
            {"requests_per_day": 1},
            [
                {
                    "dimension": "requests_per_day",
                    "quota_group": "demo-account",
                    "units": 1,
                    "release_only": False,
                }
            ],
        )

    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        reviewed_plan,
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "provider_quota_baseline_status",
        lambda **_kwargs: {"status": "unknown", "remaining_units": None},
    )

    blockers = runner.live_operation_quota_preflight({"demo"})

    assert blockers == {
        "demo": ["demo/fetch_ohlcv: active requests_per_day usage baseline is unknown"]
    }


def test_live_operation_quota_preflight_allows_explicit_local_zero_baseline(
    monkeypatch,
):
    from app import config
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"nasdaq": {"discover_universe_page"}})
    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "deployment",
            "quota_contract": {
                "reset": "calendar_day_est",
                "dimensions": [
                    {
                        "name": "directory_requests_per_market_day",
                        "limit": 2,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "deployment",
                        "quota_group": "nasdaq_symbol_directory",
                        "baseline_mode": "local_zero",
                    }
                ],
            },
        },
    )

    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        lambda *_args, **_kwargs: (
            "calendar_day_est",
            {"directory_requests_per_market_day": 2},
            [
                {
                    "dimension": "directory_requests_per_market_day",
                    "quota_group": "nasdaq_symbol_directory",
                    "units": 2,
                    "release_only": False,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "provider_quota_baseline_status",
        lambda **_kwargs: {
            "status": "initializable",
            "remaining_units": 2,
        },
    )

    assert runner.live_operation_quota_preflight({"nasdaq"}) == {}


def test_live_quota_preflight_allows_explicit_application_tracked_ip_window(monkeypatch):
    from app import config
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"edgar": {"search_instruments"}})
    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "ip",
            "quota_contract": {
                "reset": "provider_defined",
                "dimensions": [
                    {
                        "name": "requests_per_second",
                        "limit": 10,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "safety_reset": "rolling",
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        lambda *_args, **_kwargs: (
            "provider_defined",
            {"requests_per_second": 1},
            [
                {
                    "dimension": "requests_per_second",
                    "quota_group": "edgar",
                    "units": 1,
                    "release_only": False,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "provider_quota_baseline_status",
        lambda **_kwargs: {
            "status": "initializable",
            "remaining_units": 10,
            "initial_baseline": "local_zero",
        },
    )

    assert runner.live_operation_quota_preflight({"edgar"}) == {}


def test_live_operation_quota_preflight_allows_explicit_exclusive_account_rollover(
    monkeypatch,
):
    from app import config
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"alpha_vantage": {"fetch_ohlcv"}})
    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "api_key",
            "quota_contract": {
                "reset": "provider_defined",
                "dimensions": [
                    {
                        "name": "requests_per_second",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "account",
                        "safety_reset": "rolling",
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        lambda *_args, **_kwargs: (
            "rolling",
            {"requests_per_second": 1},
            [
                {
                    "dimension": "requests_per_second",
                    "quota_group": "account",
                    "units": 1,
                    "release_only": False,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "provider_quota_baseline_status",
        lambda **_kwargs: {
            "status": "initializable",
            "initial_baseline": "exclusive_account_reset",
            "remaining_units": None,
        },
    )

    assert runner.live_operation_quota_preflight({"alpha_vantage"}) == {}


def test_live_operation_quota_preflight_uses_bounded_response_cost_overrides(
    monkeypatch,
):
    from app import config
    from app.services import provider_quota_coordinator

    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "LIVE_REQUIRED_OPERATIONS",
        {"marketdata_app": {"fetch_ohlcv", "fetch_option_chain"}},
    )
    monkeypatch.setattr(
        runner,
        "LIVE_OPERATION_COST_OVERRIDES",
        {"marketdata_app": {"fetch_ohlcv": 2, "fetch_option_chain": 20}},
    )
    calls = []

    def reviewed_plan(
        provider, operation, usage_identity, now, operation_cost_override=None, **kwargs
    ):
        del usage_identity, now, kwargs
        calls.append((provider, operation, operation_cost_override))
        units = operation_cost_override or 1
        return (
            "09:30 America/New_York",
            {"credits_per_day": units},
            [
                {
                    "dimension": "credits_per_day",
                    "quota_group": "account",
                    "units": units,
                    "release_only": False,
                }
            ],
        )

    monkeypatch.setattr(
        provider_quota_coordinator,
        "_reservation_plan_for_live_probe",
        reviewed_plan,
    )
    monkeypatch.setattr(
        config,
        "provider_rate_limit_seed",
        lambda _provider: {
            "quota_scope": "api_key",
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "credits_per_day",
                        "limit": 10000,
                        "window_seconds": 86400,
                        "unit": "credits",
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "provider_quota_baseline_status",
        lambda **_kwargs: {"status": "verified", "remaining_units": 10000},
    )

    assert runner.live_operation_quota_preflight({"marketdata_app"}) == {}
    assert sorted(calls) == [
        ("marketdata_app", "fetch_ohlcv", 2),
        ("marketdata_app", "fetch_option_chain", 20),
    ]


def test_staged_candidate_quota_blocker_stops_before_live_run_lock(monkeypatch, capsys, tmp_path):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(allow_staged_candidate=True, provider=["demo"]),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(
        runner,
        "_staged_candidate_snapshot",
        lambda: ({"tree_sha": "a" * 40, "parent_sha": "b" * 40}, None),
    )
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"demo": ()})
    monkeypatch.setattr(runner, "LIVE_PREFLIGHT_ROUTING_CONTROLS", {})
    monkeypatch.setattr(runner, "CREDENTIALS", {"demo": ("DEMO_API_KEY",)})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(
        runner,
        "live_operation_quota_preflight",
        lambda _providers: {"demo": ["active usage baseline is unknown"]},
    )
    monkeypatch.setattr(runner, "routing_safety_preflight", lambda: {})
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("must not begin live run")),
    )

    assert runner.main() == 2
    output = capsys.readouterr().out
    assert "provider-specific quota/cost/baseline admission" in output
    assert "blocked before network calls" in output


def test_full_matrix_disposition_blocker_stops_before_live_run_lock(monkeypatch, capsys):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(allow_staged_candidate=False, provider=None),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"demo": ()})
    monkeypatch.setattr(
        runner,
        "LIVE_OPERATION_DISPOSITIONS",
        {"demo": {"search_instruments": "not yet live"}},
    )
    monkeypatch.setattr(runner, "LIVE_PREFLIGHT_ROUTING_CONTROLS", {})
    monkeypatch.setattr(runner, "CREDENTIALS", {"demo": ("DEMO_API_KEY",)})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(runner, "live_operation_quota_preflight", lambda _providers: {})
    monkeypatch.setattr(runner, "routing_safety_preflight", lambda: {})
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("must not begin live run")),
    )

    assert runner.main() == 2
    output = capsys.readouterr().out
    assert "unresolved capability live coverage" in output
    assert "blocked before network calls" in output


def test_staged_candidate_receipt_is_not_written_before_commit(tmp_path, monkeypatch, capsys):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: ["backend/app/providers/finra.py"])
    monkeypatch.setattr(runner, "_source_sha", lambda: "b" * 40)

    result = runner._record_live_validation(
        providers=None,
        exit_code=0,
        missing={},
        counts={
            "case_count": 8,
            "passed_cases": 8,
            "failed_cases": 0,
            "skipped_cases": 0,
        },
        approved_deferrals={"tradier": "deferred by user"},
        live_evidence={"complete": True, "missing": [], "providers": {}, "cases": []},
        candidate_tree={"tree_sha": "a" * 40, "parent_sha": "b" * 40},
    )

    assert result == "staged_candidate_full_matrix_passed"
    assert not validation_path.exists()
    output = capsys.readouterr().out
    receipt_line = next(
        line.removeprefix("staged candidate receipt: ")
        for line in output.splitlines()
        if line.startswith("staged candidate receipt: ")
    )
    assert json.loads(receipt_line)["candidate_tree_sha"] == "a" * 40


def test_staged_candidate_passing_pytest_without_live_evidence_is_not_accepted(
    tmp_path, monkeypatch
):
    runner = _runner_module()
    monkeypatch.setattr(
        runner, "_workstream_validation_path", lambda: tmp_path / "validation.jsonl"
    )
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_source_sha", lambda: "b" * 40)

    result = runner._record_live_validation(
        providers=None,
        exit_code=0,
        missing={},
        counts={"case_count": 8, "passed_cases": 8, "failed_cases": 0, "skipped_cases": 0},
        approved_deferrals={},
        live_evidence={"complete": False, "missing": ["FRED/series observation missing"]},
        candidate_tree={"tree_sha": "a" * 40, "parent_sha": "b" * 40},
    )

    assert result == "staged_candidate_missing_live_evidence"


def test_staged_candidate_with_zero_collected_cases_is_not_accepted(tmp_path, monkeypatch):
    runner = _runner_module()
    monkeypatch.setattr(
        runner, "_workstream_validation_path", lambda: tmp_path / "validation.jsonl"
    )
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_source_sha", lambda: "b" * 40)

    result = runner._record_live_validation(
        providers=None,
        exit_code=0,
        missing={},
        counts={"case_count": 0, "passed_cases": 0, "failed_cases": 0, "skipped_cases": 0},
        approved_deferrals={},
        candidate_tree={"tree_sha": "a" * 40, "parent_sha": "b" * 40},
    )

    assert result == "staged_candidate_failed"


def test_staged_candidate_checkout_uses_index_content(tmp_path, monkeypatch):
    import subprocess

    runner = _runner_module()
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Candidate Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "candidate@example.test"],
        check=True,
    )
    source = repository / "candidate.txt"
    source.write_text("parent\n", encoding="utf-8")
    nested_source = repository / "nested" / "module" / "candidate.py"
    nested_source.parent.mkdir(parents=True)
    nested_source.write_text("nested parent\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "candidate.txt"], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "nested"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    source.write_text("staged candidate\n", encoding="utf-8")
    nested_source.write_text("nested staged candidate\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "candidate.txt"], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "nested"], check=True)
    monkeypatch.setattr(runner, "ROOT", repository)
    destination = tmp_path / "snapshot"
    destination.mkdir()

    success, error = runner._checkout_index_candidate(destination)

    assert success is True
    assert error is None
    assert (destination / "candidate.txt").read_text(encoding="utf-8") == "staged candidate\n"
    assert (destination / "nested" / "module" / "candidate.py").read_text(
        encoding="utf-8"
    ) == "nested staged candidate\n"


def test_candidate_reuses_backend_environment_when_locked_dependencies_match(tmp_path, monkeypatch):
    runner = _runner_module()
    repository = tmp_path / "repository"
    backend = repository / "backend"
    candidate_backend = tmp_path / "candidate" / "backend"
    environment_python = backend / ".venv" / "bin" / "python"
    for directory in (backend, candidate_backend, environment_python.parent):
        directory.mkdir(parents=True, exist_ok=True)
    for manifest in ("pyproject.toml", "uv.lock"):
        (backend / manifest).write_text(f"locked {manifest}\n", encoding="utf-8")
        (candidate_backend / manifest).write_text(f"locked {manifest}\n", encoding="utf-8")
    environment_python.touch()
    monkeypatch.setattr(runner, "ROOT", repository)

    assert runner._candidate_can_reuse_backend_environment(candidate_backend.parent)


@pytest.mark.parametrize("difference", ["lock", "missing_environment"])
def test_candidate_does_not_reuse_backend_environment_when_not_identical(
    tmp_path, monkeypatch, difference
):
    runner = _runner_module()
    repository = tmp_path / "repository"
    backend = repository / "backend"
    candidate_backend = tmp_path / "candidate" / "backend"
    for directory in (backend, candidate_backend):
        directory.mkdir(parents=True)
    for manifest in ("pyproject.toml", "uv.lock"):
        (backend / manifest).write_text(f"locked {manifest}\n", encoding="utf-8")
        (candidate_backend / manifest).write_text(f"locked {manifest}\n", encoding="utf-8")
    if difference != "missing_environment":
        environment_python = backend / ".venv" / "bin" / "python"
        environment_python.parent.mkdir(parents=True)
        environment_python.touch()
        (candidate_backend / "uv.lock").write_text("different lock\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", repository)

    assert not runner._candidate_can_reuse_backend_environment(candidate_backend.parent)


def test_live_output_redacts_configured_credentials_and_query_tokens(monkeypatch):
    runner = _runner_module()
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "live-secret-value")

    result = runner.redact_runner_output(
        "url=https://api.test/query?apikey=live-secret-value&symbol=AAPL "
        "Authorization: Bearer second-secret Authorization: Basic third-secret"
    )

    assert "live-secret-value" not in result
    assert "second-secret" not in result
    assert "third-secret" not in result
    assert "<redacted>" in result


def test_staged_candidate_rejects_multi_provider_slice_before_network(monkeypatch, capsys):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            allow_staged_candidate=True, provider=["tiingo", "massive"], case=[]
        ),
    )

    assert runner.main() == 2
    assert "one provider" in capsys.readouterr().out


def test_staged_candidate_provider_slice_is_never_full_acceptance(tmp_path, monkeypatch, capsys):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    result = runner._record_live_validation(
        providers=["tiingo"],
        exit_code=0,
        missing={},
        counts={"case_count": 4, "passed_cases": 4, "failed_cases": 0, "skipped_cases": 0},
        approved_deferrals={},
        live_evidence={"complete": True, "missing": [], "providers": {"tiingo": {}}, "cases": []},
        candidate_tree={"tree_sha": "a" * 40, "parent_sha": "b" * 40, "provider": "tiingo"},
    )

    assert result == "staged_candidate_provider_passed"
    assert not validation_path.exists()
    output = capsys.readouterr().out
    receipt_line = next(
        line.removeprefix("staged candidate receipt: ")
        for line in output.splitlines()
        if line.startswith("staged candidate receipt: ")
    )
    receipt = json.loads(receipt_line)
    assert receipt["candidate_tree_sha"] == "a" * 40
    assert receipt["providers_run"] == ["tiingo"]
    assert receipt["live_acceptance"] is False


def test_staged_candidate_rejects_missing_live_opt_in(monkeypatch, capsys, tmp_path):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(allow_staged_candidate=True, provider=None),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.delenv("RUN_LIVE_PROVIDER_TESTS", raising=False)

    assert runner.main() == 2
    assert "RUN_LIVE_PROVIDER_TESTS=1" in capsys.readouterr().out


def test_staged_candidate_missing_credentials_blocks_before_network(monkeypatch, capsys, tmp_path):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(allow_staged_candidate=True, provider=None),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(
        runner,
        "_staged_candidate_snapshot",
        lambda: ({"tree_sha": "a" * 40, "parent_sha": "b" * 40}, None),
    )
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "KEYLESS", ("REQUIRED_CONTACT",))
    monkeypatch.setattr(runner, "CREDENTIALS", {"demo": ("DEMO_API_KEY",)})
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: False)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "routing_safety_preflight", lambda: {})

    assert runner.main() == 2
    assert "blocked before network calls" in capsys.readouterr().out


def test_canonical_live_runner_requires_transport_limit_before_launch(
    monkeypatch, capsys, tmp_path
):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            verify_candidate_receipts=None,
            candidate_receipt_file=None,
            provider=["demo"],
            case=[],
            allow_staged_candidate=False,
            account_usage_only=False,
            dinari_sandbox_canary=False,
            preflight_only=False,
            max_http_requests=None,
        ),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"demo": (("live.py", "test_read"),)})
    monkeypatch.setattr(runner, "CREDENTIALS", {"demo": ()})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(runner, "live_operation_quota_preflight", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "routing_safety_preflight", lambda: {})
    monkeypatch.setattr(runner, "live_required_safety_blockers", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "live_provider_plan_admission_blockers", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("must block before live lock")),
    )

    assert runner.main() == 2
    assert "--max-http-requests is required" in capsys.readouterr().out


def test_workstream_only_porcelain_changes_do_not_taint_live_source_receipt(monkeypatch):
    runner = _runner_module()
    porcelain = (
        " M ops/workstreams/feat-market-data-provider-platform/session.json\n"
        " M backend/app/providers/alpaca.py\n"
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=porcelain),
    )

    assert runner._git_output("status", "--porcelain") == porcelain.rstrip("\r\n")
    assert runner._dirty_source_paths() == ["backend/app/providers/alpaca.py"]


def test_preflight_only_never_launches_live_transport_and_records_nonacceptance(
    monkeypatch, capsys, tmp_path
):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    validation_path.touch()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            allow_staged_candidate=False,
            provider=["alpaca"],
            account_usage_only=False,
            dinari_sandbox_canary=False,
            preflight_only=True,
        ),
    )
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "live_matrix_inventory_errors", lambda: [])
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"alpaca": (("test", "test"),)})
    monkeypatch.setattr(runner, "CREDENTIALS", {"alpaca": ("ALPACA_API_KEY",)})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(
        runner, "provider_required_credentials", lambda _provider: ("ALPACA_API_KEY",)
    )
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(runner, "live_operation_quota_preflight", lambda _providers: {})
    monkeypatch.setattr(
        runner,
        "routing_safety_preflight",
        lambda: {"test_control": "routable by fixture"},
    )
    monkeypatch.setattr(runner, "LIVE_PREFLIGHT_ROUTING_CONTROLS", {"alpaca": ("test_control",)})
    monkeypatch.setattr(runner, "_source_sha", lambda: "source-sha")
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("preflight must not acquire live lock")),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("preflight must not start provider tests")
        ),
    )
    monkeypatch.delenv("RUN_LIVE_PROVIDER_TESTS", raising=False)

    assert runner.main() == 0

    output = capsys.readouterr().out
    assert "preflight: clear; transport was not attempted" in output
    receipt = json.loads(validation_path.read_text(encoding="utf-8"))
    assert receipt["kind"] == "provider_live_preflight"
    assert receipt["result"] == "clear_no_transport"
    assert receipt["providers_evaluated"] == ["alpaca"]
    assert receipt["provider_http_requests"] == 0
    assert receipt["transport_started"] is False
    assert receipt["live_acceptance"] is False


@pytest.mark.parametrize("allow_paid", [False, True])
def test_fmp_paid_plan_is_denied_by_free_only_checkpoint_independent_of_paid_toggle(
    allow_paid,
):
    runner = _runner_module()

    status = runner.fmp_account_plan_routing_status(
        "premium", free_only=True, allow_paid=allow_paid
    )

    assert status.startswith("non-routable: shared free-only checkpoint")


@pytest.mark.parametrize(
    ("plan", "free_only", "allow_paid", "routable"),
    [
        ("basic", True, False, True),
        ("premium", True, True, False),
        ("premium", False, False, False),
        ("premium", False, True, True),
        ("unknown", False, True, False),
    ],
)
def test_fmp_account_plan_status_tracks_exact_plan_and_free_only_switch(
    plan, free_only, allow_paid, routable
):
    runner = _runner_module()

    status = runner.fmp_account_plan_routing_status(
        plan, free_only=free_only, allow_paid=allow_paid
    )

    assert status.startswith("routable") is routable


@pytest.mark.parametrize("allow_paid", [False, True])
def test_effective_free_plan_controls_admit_reviewed_free_and_expired_trial(
    allow_paid,
):
    runner = _runner_module()
    future_now = datetime(2026, 10, 16, tzinfo=UTC)

    free_status = runner.marketdata_app_account_plan_routing_status(
        "free_forever", 100, "", free_only=True, allow_paid=allow_paid, now=future_now
    )
    expired_trial_status = runner.marketdata_app_account_plan_routing_status(
        "starter_trial",
        10000,
        "2026-10-15T18:09:00+00:00",
        free_only=True,
        allow_paid=allow_paid,
        now=future_now,
    )
    tiingo_status = runner.tiingo_account_plan_routing_status(
        "starter", free_only=True, allow_paid=allow_paid
    )

    assert free_status.startswith("routable")
    assert "Free Forever" in expired_trial_status
    assert expired_trial_status.startswith("routable")
    assert tiingo_status.startswith("routable")
    assert (
        runner.live_provider_plan_admission_blockers(
            {"marketdata_app"}, {"marketdata.app account plan": expired_trial_status}
        )
        == {}
    )
    assert (
        runner.live_provider_plan_admission_blockers(
            {"tiingo"}, {"tiingo account plan": tiingo_status}
        )
        == {}
    )


@pytest.mark.parametrize(
    ("provider", "scope", "plan", "limit", "expiry"),
    [
        ("marketdata_app", "full", "starter", 10000, ""),
        ("marketdata_app", "provider", "trader", 100000, ""),
        ("marketdata_app", "case", "starter_trial", 10000, "2026-10-17T18:09:00+00:00"),
        ("marketdata_app", "account_usage", "mystery", 0, ""),
        ("tiingo", "full", "power", 0, ""),
        ("tiingo", "provider", "custom", 0, ""),
        ("tiingo", "case", "mystery", 0, ""),
    ],
)
@pytest.mark.parametrize("allow_paid", ["false", "true"])
def test_live_runner_denies_nonfree_effective_plans_before_lock_or_subprocess(
    monkeypatch, capsys, tmp_path, provider, scope, plan, limit, expiry, allow_paid
):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    validation_path.touch()
    account_case = (
        "test_marketdata_app_credentialed_account_usage_snapshot"
        if provider == "marketdata_app"
        else "test_tiingo_credentialed_account_usage_snapshot"
    )
    read_case = "test_optional_credentialed_provider_small_read"
    case_selectors = [f"{provider}:{read_case}"] if scope == "case" else []
    arguments = SimpleNamespace(
        verify_candidate_receipts=None,
        candidate_receipt_file=None,
        allow_staged_candidate=False,
        provider=None if scope == "full" else [provider],
        case=case_selectors,
        account_usage_only=scope == "account_usage",
        dinari_sandbox_canary=False,
        preflight_only=False,
    )
    monkeypatch.setattr(runner, "_arguments", lambda: arguments)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "live_matrix_inventory_errors", lambda: [])
    monkeypatch.setattr(
        runner,
        "LIVE_PROVIDER_CASES",
        {
            provider: (
                ("test_market_data_providers_live.py", account_case),
                ("test_market_data_providers_live.py", read_case),
            )
        },
    )
    monkeypatch.setattr(
        runner,
        "LIVE_CASE_OPERATIONS",
        {provider: {account_case: {"fetch_account_usage"}, read_case: {"fetch_ohlcv"}}},
    )
    monkeypatch.setattr(runner, "LIVE_CASE_OPERATION_MULTIPLIERS", {})
    monkeypatch.setattr(runner, "LIVE_OPERATION_DISPOSITIONS", {provider: {}})
    monkeypatch.setattr(
        runner, "LIVE_REQUIRED_OPERATIONS", {provider: {"fetch_ohlcv", "fetch_account_usage"}}
    )
    monkeypatch.setattr(runner, "LIVE_PROVIDER_SAFETY_DISPOSITIONS", {})
    monkeypatch.setattr(runner, "LIVE_PREFLIGHT_ROUTING_CONTROLS", {provider: ()})
    monkeypatch.setattr(runner, "CREDENTIALS", {provider: ()})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(runner, "live_operation_quota_preflight", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "live_required_safety_blockers", lambda *args, **kwargs: {})
    if provider == "marketdata_app":
        status = runner.marketdata_app_account_plan_routing_status(
            plan,
            limit,
            expiry,
            free_only=True,
            allow_paid=allow_paid == "true",
            now=datetime(2026, 10, 16, tzinfo=UTC),
        )
        status_name = "marketdata.app account plan"
    else:
        status = runner.tiingo_account_plan_routing_status(
            plan, free_only=True, allow_paid=allow_paid == "true"
        )
        status_name = "tiingo account plan"
    monkeypatch.setattr(runner, "routing_safety_preflight", lambda: {status_name: status})
    monkeypatch.setattr(runner, "_source_sha", lambda: "a" * 40)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    validation_calls = []
    monkeypatch.setattr(
        runner,
        "_record_live_validation",
        lambda **kwargs: validation_calls.append(kwargs) or "blocked",
    )
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("blocked plan acquired live lock")),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("blocked plan started provider tests")
        ),
    )
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setenv("PROVIDER_FREE_ONLY_CHECKPOINT", "true")
    monkeypatch.setenv("ALLOW_PAID_PROVIDER_ROUTING", allow_paid)

    assert runner.main() == 2
    output = capsys.readouterr().out
    assert provider in output and "non-routable" in output
    assert len(validation_calls) == 1
    assert validation_calls[0]["exit_code"] == 2
    assert validation_calls[0]["counts"]["case_count"] == 0
    assert "required live capability safety" in validation_calls[0]["missing"]
    assert any(
        provider in blocker
        for blocker in validation_calls[0]["missing"]["required live capability safety"]
    )


def test_live_runner_plan_gate_does_not_remove_eodhd_zero_credit_usage_path():
    runner = _runner_module()

    assert runner.live_provider_plan_admission_blockers({"eodhd"}, {}) == {}
    assert (
        runner.live_required_safety_blockers(
            {"eodhd"},
            {"eodhd": "non-routable: data-use terms not approved"},
            account_usage_only=True,
        )
        == {}
    )


@pytest.mark.parametrize("scope", ["full", "case", "account_usage"])
@pytest.mark.parametrize("allow_paid", ["false", "true"])
def test_live_runner_main_blocks_paid_fmp_before_transport_for_each_scope(
    monkeypatch, capsys, tmp_path, scope, allow_paid
):
    runner = _runner_module()
    validation_path = tmp_path / "validation.jsonl"
    validation_path.touch()
    test_case = "test_fmp_credentialed_account_usage_snapshot"
    case_selectors = [f"fmp:{test_case}"] if scope == "case" else []
    arguments = SimpleNamespace(
        verify_candidate_receipts=None,
        candidate_receipt_file=None,
        allow_staged_candidate=False,
        provider=None if scope == "full" else ["fmp"],
        case=case_selectors,
        account_usage_only=scope == "account_usage",
        dinari_sandbox_canary=False,
        preflight_only=True,
    )
    monkeypatch.setattr(runner, "_arguments", lambda: arguments)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "DEFAULT_SHARED_ENV", tmp_path / "absent.env")
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "live_matrix_inventory_errors", lambda: [])
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"fmp": (("test", test_case),)})
    monkeypatch.setattr(
        runner,
        "LIVE_CASE_OPERATIONS",
        {"fmp": {test_case: {"fetch_account_usage"}}},
    )
    monkeypatch.setattr(runner, "LIVE_CASE_OPERATION_MULTIPLIERS", {})
    monkeypatch.setattr(runner, "LIVE_OPERATION_DISPOSITIONS", {"fmp": {}})
    monkeypatch.setattr(runner, "LIVE_REQUIRED_OPERATIONS", {"fmp": {"fetch_account_usage"}})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_SAFETY_DISPOSITIONS", {})
    monkeypatch.setattr(runner, "CREDENTIALS", {"fmp": ()})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(runner, "live_operation_quota_preflight", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        runner,
        "routing_safety_preflight",
        lambda: {
            "fmp": "routable",
            "fmp account plan": runner.fmp_account_plan_routing_status(
                "premium", free_only=True, allow_paid=allow_paid == "true"
            ),
        },
    )
    monkeypatch.setattr(runner, "_source_sha", lambda: "a" * 40)
    monkeypatch.setattr(runner, "_dirty_source_paths", lambda: [])
    monkeypatch.setattr(runner, "_workstream_validation_path", lambda: validation_path)
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("blocked preflight acquired live lock")),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("blocked preflight started provider tests")
        ),
    )
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setenv("PROVIDER_FREE_ONLY_CHECKPOINT", "true")
    monkeypatch.setenv("ALLOW_PAID_PROVIDER_ROUTING", allow_paid)

    assert runner.main() == 2
    assert "shared free-only checkpoint blocks paid FMP premium plan" in capsys.readouterr().out
    receipt = json.loads(validation_path.read_text(encoding="utf-8"))
    assert receipt["provider_http_requests"] == 0
    assert receipt["transport_started"] is False
