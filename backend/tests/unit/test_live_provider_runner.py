from __future__ import annotations

import importlib.util
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
    arguments = runner.selected_live_test_arguments(
        None, deferred_providers=set(deferrals)
    )
    selection = arguments[arguments.index("-k") + 1]
    assert "not tradier" in selection
    assert "not ibkr" in selection
    assert "not ondo" in selection


def test_focused_parameterized_provider_selection_does_not_select_siblings():
    runner = _runner_module()
    arguments = runner.selected_live_test_arguments(["tiingo"])

    assert "tests/live/test_market_data_providers_live.py::test_optional_credentialed_provider_small_read" in arguments
    selection = arguments[arguments.index("-k") + 1]
    assert "tiingo" in selection
    assert "optional_credentialed_provider_small_read" not in selection


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
