from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _runner_module():
    path = Path(__file__).parents[3] / "scripts" / "run-live-provider-probes.py"
    spec = importlib.util.spec_from_file_location("run_live_provider_probes_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_plan_approved_live_deferrals_are_excluded_from_full_matrix():
    runner = _runner_module()
    deferrals = runner.approved_live_deferrals()

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
        "DINARI_SANDBOX_CANARY_MAX_REQUESTS",
    }

    monkeypatch.setenv("DINARI_SANDBOX_CANARY_AUTHORIZED", "true")
    monkeypatch.setenv(
        "DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE", "owner-approved-sandbox-check"
    )
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "20")
    assert runner.dinari_sandbox_canary_controls_missing() == []


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


def test_normal_dinari_selection_remains_blocked_without_canary(monkeypatch, capsys):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(
            allow_staged_candidate=False,
            provider=["dinari"],
            account_usage_only=False,
            dinari_sandbox_canary=False,
        ),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setattr(runner, "changed_provider_code", lambda: True)
    monkeypatch.setattr(runner, "live_matrix_inventory_errors", lambda: [])
    monkeypatch.setattr(runner, "approved_live_deferrals", lambda: {})
    monkeypatch.setattr(runner, "LIVE_PROVIDER_CASES", {"dinari": (("x", "y"),)})
    monkeypatch.setattr(runner, "CREDENTIALS", {"dinari": ("DINARI_API_KEY_ID",)})
    monkeypatch.setattr(runner, "KEYLESS", ())
    monkeypatch.setattr(runner, "setting_is_configured", lambda _name: True)
    monkeypatch.setattr(runner, "usage_scope_is_configured", lambda: True)
    monkeypatch.setattr(runner, "durable_quota_preflight", lambda: (True, None))
    monkeypatch.setattr(runner, "live_operation_quota_preflight", lambda _providers: {})
    monkeypatch.setattr(
        runner,
        "routing_safety_preflight",
        lambda: {"dinari sandbox canary quota": "non-routable: quota unknown"},
    )
    monkeypatch.setattr(
        runner,
        "provider_live_run_lock",
        lambda: (_ for _ in ()).throw(AssertionError("must not begin live run")),
    )

    assert runner.main() == 2
    assert "required live capability safety" in capsys.readouterr().out


def test_unit_runner_does_not_persist_synthetic_receipts_to_workstream_by_default(
    monkeypatch, tmp_path
):
    """Runner unit tests must not pollute the durable branch validation ledger."""

    runner = _runner_module()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_live_provider_runner.py::unit")
    monkeypatch.delenv("PROVIDER_LIVE_VALIDATION_WRITE", raising=False)
    monkeypatch.setattr(runner, "_git_output", lambda *args: "feat/unit-runner")
    validation_path = (
        tmp_path / "ops" / "workstreams" / "feat-unit-runner" / "validation.jsonl"
    )
    validation_path.parent.mkdir(parents=True)
    validation_path.touch()

    assert runner._workstream_validation_path() is None
    assert validation_path.read_text(encoding="utf-8") == ""


def test_runner_validation_persistence_requires_explicit_unit_test_opt_in(
    monkeypatch, tmp_path
):
    """A runner test may exercise persistence only through an explicit opt-in."""

    runner = _runner_module()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_live_provider_runner.py::unit")
    monkeypatch.setenv("PROVIDER_LIVE_VALIDATION_WRITE", "1")
    monkeypatch.setattr(runner, "_git_output", lambda *args: "feat/unit-runner")
    validation_path = (
        tmp_path / "ops" / "workstreams" / "feat-unit-runner" / "validation.jsonl"
    )
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


def test_account_usage_only_selection_keeps_only_the_dedicated_case():
    runner = _runner_module()
    arguments = runner.selected_live_test_arguments(
        ["eodhd"], account_usage_only=True
    )

    assert arguments == [
        "tests/live/test_market_data_providers_live.py::test_eodhd_credentialed_account_usage_snapshot",
        "-k",
        "eodhd_credentialed_account_usage_snapshot",
    ]

    binance_arguments = runner.selected_live_test_arguments(
        ["binance"], account_usage_only=True
    )
    assert binance_arguments == [
        "tests/live/test_market_data_providers_live.py::test_binance_keyless_account_usage_snapshot",
        "-k",
        "binance_keyless_account_usage_snapshot",
    ]

    alpaca_arguments = runner.selected_live_test_arguments(
        ["alpaca"], account_usage_only=True
    )
    assert alpaca_arguments == [
        "tests/live/test_market_data_providers_live.py::test_alpaca_credentialed_account_usage_snapshot",
        "-k",
        "alpaca_credentialed_account_usage_snapshot",
    ]


def test_manifest_has_exact_operation_evidence_for_every_provider():
    runner = _runner_module()

    assert set(runner.LIVE_REQUIRED_OPERATIONS) == set(runner.LIVE_PROVIDER_CASES)
    assert runner.LIVE_PROVIDER_CASES["nasdaq"] == (
        (
            "test_market_data_providers_live.py",
            "test_nasdaq_trader_full_directory_pagination_is_complete",
        ),
    )
    assert runner.LIVE_REQUIRED_OPERATIONS["finnhub"] == {
        "search_instruments",
        "get_instrument_profile",
        "fetch_instrument_events",
        "fetch_market_events",
        "discover_universe_page",
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
            "fetch_instrument_events": 2,
        },
        "binance": {"fetch_latest_ohlcv": 2, "fetch_ohlcv": 2},
        "coinbase": {"fetch_latest_ohlcv": 1},
        "kraken": {"fetch_latest_ohlcv": 1},
        "massive": {"fetch_ohlcv": 1},
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
    assert runner.live_operation_disposition_kind("deferred by user: account") == (
        "human_deferred"
    )
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
        "fred": {"get_current_price"},
        "coingecko": {"discover_universe_page"},
        "finra": {
            "submit_async_dataset",
            "poll_async_dataset",
            "download_async_result",
        },
        "massive": {
            "discover_universe_page",
            "fetch_market_events_page",
            "fetch_instrument_events",
        },
        "alpha_vantage": {
            "search_instruments",
            "get_current_price",
            "discover_universe_page",
        },
        "tiingo": {"search_instruments", "get_current_price"},
        "twelve_data": set(),
        "finnhub": {
            "fetch_ohlcv",
            "get_current_price",
        },
        "marketstack": {"discover_universe_page"},
        "eodhd": set(),
        "fmp": {"get_current_price", "discover_universe_page"},
        "tradier": {"search_instruments", "get_current_price"},
        "marketdata_app": set(),
        "ibkr": {"search_instruments", "futures_history"},
        "binance": set(),
        "coinbase": {"fetch_ohlcv", "get_current_price", "discover_universe_page"},
        "kraken": {"fetch_ohlcv"},
        "ondo_global_markets": {"get_tokenized_asset"},
    }

    assert {
        provider: set(runner.LIVE_OPERATION_DISPOSITIONS[provider])
        for provider in expected
    } == expected


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


def test_fred_policy_guard_pass_cannot_substitute_for_live_evidence(tmp_path):
    runner = _runner_module()
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
    assert deferred_evidence["operation_dispositions"]["openfigi"]["search_instruments"][
        "kind"
    ] == "human_deferred"


def test_expected_entitlement_denial_requires_explicit_receipt_disposition(
    tmp_path, monkeypatch
):
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
    monkeypatch.delenv("FINRA_OTC_SOURCE_REVIEWED", raising=False)
    monkeypatch.delenv("FINRA_OTC_SOURCE_EVIDENCE", raising=False)
    monkeypatch.setenv(
        "FINRA_OTC_OPERATION_COSTS",
        '{"discover_universe_page": 3, "reconcile_universe_page": 3}',
    )
    monkeypatch.setenv("FINRA_OTC_TERMS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_COMPLETENESS_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_REDISTRIBUTION_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "900")

    result = runner.routing_safety_preflight()
    assert "FINRA_OTC_SOURCE_REVIEWED" in result["finra otc directory"]
    assert "FINRA_OTC_SOURCE_EVIDENCE" in result["finra otc directory"]

    monkeypatch.setenv("FINRA_OTC_SOURCE_REVIEWED", "true")
    monkeypatch.setenv("FINRA_OTC_SOURCE_EVIDENCE", "FINRA support case 123")
    monkeypatch.setenv(
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
    )
    monkeypatch.setenv(
        "FINRA_OTC_REVIEWED_SOURCE_URL",
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
    )
    result = runner.routing_safety_preflight()
    assert result["finra otc directory"] == "routable"
    monkeypatch.setenv(
        "FINRA_OTC_REVIEWED_SOURCE_URL",
        "https://api.finra.org/data/group/otcMarket/name/anotherDataset",
    )
    result = runner.routing_safety_preflight()
    assert "FINRA_OTC_REVIEWED_SOURCE_URL" in result["finra otc directory"]


def test_staged_candidate_requires_clean_staging_and_returns_tree_identity():
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

    assert unstaged == "tracked working-tree changes are not fully staged"
    assert untracked == "untracked files must be staged or excluded before candidate validation"
    assert (
        secret_path == "credential-bearing path is prohibited in a candidate: backend/.env.staging"
    )
    assert (
        credential_path
        == "credential-bearing path is prohibited in a candidate: config/credentials.json"
    )


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
    assert runner.staged_secret_findings(
        "+FINRA_OTC_SYMBOL_DIRECTORY_URL=https://apidownload.finratrags.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF\n"
        "+IBKR_READ_ONLY_URL=https://gateway.example.test\n"
    ) == []
    example_dsn = "postgresql+asyncpg://" + (
        "postgres:postgres@postgres:5432/chartingdb"
    )
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
    monkeypatch.setattr(
        runner, "LIVE_REQUIRED_OPERATIONS", {"demo": {"fetch_ohlcv"}}
    )
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
        "demo": [
            "demo/fetch_ohlcv: active requests_per_day usage baseline is unknown"
        ]
    }


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


def test_staged_candidate_quota_blocker_stops_before_live_run_lock(
    monkeypatch, capsys, tmp_path
):
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
    subprocess.run(["git", "-C", str(repository), "add", "candidate.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    source.write_text("staged candidate\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "candidate.txt"], check=True)
    monkeypatch.setattr(runner, "ROOT", repository)
    destination = tmp_path / "snapshot"
    destination.mkdir()

    success, error = runner._checkout_index_candidate(destination)

    assert success is True
    assert error is None
    assert (destination / "candidate.txt").read_text(encoding="utf-8") == "staged candidate\n"


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


def test_staged_candidate_rejects_focused_mode_before_network(monkeypatch, capsys):
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: SimpleNamespace(allow_staged_candidate=True, provider=["tiingo"]),
    )

    assert runner.main() == 2
    assert "full matrix" in capsys.readouterr().out


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
