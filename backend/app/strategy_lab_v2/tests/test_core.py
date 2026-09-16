from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from app.strategy_lab_v2.allocation import ALLOCATION_DEFINITION_VERSION
from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    Degradation,
    PreflightClass,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
    AttemptState,
    DataSeriesManifest,
    DataSnapshot,
    EvaluationWindow,
    EventGranularity,
    KeyedRandomStreamPairingClaim,
    MetricBasis,
    MetricSet,
    MetricValue,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    SensitivityComparisonEvidence,
    SensitivityEvidenceLevel,
    SharedRiskPolicy,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
    TrialSeedPolicy,
)
from app.strategy_lab_v2.experiments import (
    ExpansionMethod,
    SearchDesign,
    SearchDimension,
    WalkForwardMode,
    WalkForwardSpec,
    aggregate_out_of_sample,
    build_trial_designs,
    build_walk_forward_folds,
    expand_parameter_sets,
    expand_scenario_matrix,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    ForwardEventDisposition,
    create_retry_attempt,
    observe_forward_event,
    transition_attempt,
)
from app.strategy_lab_v2.metrics import calculate_performance_metrics, calculate_trade_metrics
from app.strategy_lab_v2.rebalance import (
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceTrigger,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    OrderIntent,
    OrderSide,
    OrderType,
    PositionSnapshot,
    StrategyDataDependency,
    StrategySdkManifest,
    TargetPositionIntent,
    build_strategy_context,
    validate_strategy_output,
)
from app.strategy_lab_v2.sensitivity import (
    MetricDeltaUnavailable,
    compare_one_factor_metric,
)

START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2022, 1, 1, tzinfo=UTC)
SOURCE_DIGEST = content_digest({"source": "strategy"})
EVIDENCE_DIGEST = content_digest({"provider": "fixture"})


def _requirement(
    *, session: str = "regular", corporate_action_semantics: str = "split-adjusted-v1"
) -> CapabilityRequirement:
    return CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=START,
        end=END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session=session,
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics=corporate_action_semantics,
    )


def _cell(
    *,
    sessions: frozenset[str] = frozenset({"regular"}),
    corporate_action_semantics: str = "split-adjusted-v1",
) -> CapabilityCell:
    return CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=sessions,
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({corporate_action_semantics}),
        history_start=START,
        history_end=END,
        evidence_digest=EVIDENCE_DIGEST,
    )


def test_canonical_content_is_order_independent_and_recursively_immutable() -> None:
    first = {"parameters": {"z": Decimal("1.2500"), "a": [1, 2]}}
    second = {"parameters": {"a": [1, 2], "z": Decimal("1.25")}}
    assert content_digest(first) == content_digest(second)
    assert canonical_json({"x": 1, "set": frozenset({"b", "a"})}) == canonical_json(
        {"set": frozenset({"a", "b"}), "x": 1}
    )
    assert content_digest(Decimal("1")) == content_digest(Decimal("1.000"))
    assert content_digest(Decimal("1")) != content_digest("1")
    assert content_digest(True) != content_digest(1)

    strategy = StrategyVersion("s-1", "v-1", "2.0", SOURCE_DIGEST, default_parameters=first)
    with pytest.raises(TypeError):
        strategy.default_parameters["new"] = 2  # type: ignore[index]
    assert strategy.default_parameters["parameters"]["z"] == Decimal("1.2500")


def test_scientific_trial_identity_is_stable_across_mapping_order() -> None:
    experiment = content_digest({"experiment": 1})
    snapshot = content_digest({"snapshot": 1})
    preflight = preflight_capabilities((_requirement(),), (_cell(),))
    first = ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=snapshot,
        preflight_report=preflight,
        parameter_set={"lookback": 20, "threshold": Decimal("0.03")},
        seed=19,
    )
    second = ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=snapshot,
        preflight_report=preflight,
        parameter_set={"threshold": Decimal("0.030"), "lookback": 20},
        seed=19,
    )
    assert first.trial_id == second.trial_id
    assert first.parameter_set["threshold"] == Decimal("0.03")
    assert first.preflight_label == "rigorous"
    assert first.ranking_eligible

    degraded_report = preflight_capabilities(
        (_requirement(session="extended"),),
        (_cell(),),
        allow_degraded=True,
        degradations=(
            Degradation("US.AAPL", "session", "regular", "extended session unavailable"),
        ),
    )
    degraded_trial = ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=snapshot,
        preflight_report=degraded_report,
        parameter_set={},
    )
    assert degraded_trial.preflight_label == "degraded"
    assert not degraded_trial.ranking_eligible

    with pytest.raises(ValueError, match="trial_id does not match"):
        # A mismatched caller-supplied trial id cannot pair a rigorous report with
        # altered ranking semantics; those semantics are derived from the report.
        type(first)(
            trial_id=first.trial_id,
            experiment_fingerprint=experiment,
            snapshot_fingerprint=snapshot,
            preflight_report=degraded_report,
            parameter_set={},
            scenario={},
            seed=first.seed,
            randomization=first.randomization,
        )
    unsupported = preflight_capabilities((_requirement(session="extended"),), (_cell(),))
    with pytest.raises(ValueError, match="unsupported preflight"):
        ScientificTrial.create(
            experiment_fingerprint=experiment,
            snapshot_fingerprint=snapshot,
            preflight_report=unsupported,
            parameter_set={},
        )


def test_evaluation_window_is_typed_normalized_and_bound_to_trial_identity() -> None:
    experiment = content_digest({"experiment": "window"})
    snapshot = content_digest({"snapshot": "window"})
    preflight = preflight_capabilities((_requirement(),), (_cell(),))
    window = EvaluationWindow(
        start=datetime(2021, 1, 4, 14, 30, tzinfo=UTC),
        end=datetime(2021, 1, 8, 21, tzinfo=UTC),
        purpose="out_of_sample",
        warmup_start=datetime(2020, 12, 1, 14, 30, tzinfo=UTC),
    )
    offset_window = EvaluationWindow(
        start=datetime(2021, 1, 4, 15, 30, tzinfo=timezone(timedelta(hours=1))),
        end=datetime(2021, 1, 8, 22, tzinfo=timezone(timedelta(hours=1))),
        purpose="out_of_sample",
        warmup_start=datetime(2020, 12, 1, 15, 30, tzinfo=timezone(timedelta(hours=1))),
    )
    assert window == offset_window
    first = ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=snapshot,
        preflight_report=preflight,
        parameter_set={"lookback": 20},
        seed=19,
        evaluation_window=window,
    )
    second = ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=snapshot,
        preflight_report=preflight,
        parameter_set={"lookback": 20},
        seed=19,
        evaluation_window=replace(window, end=datetime(2021, 1, 9, 21, tzinfo=UTC)),
    )
    assert first.evaluation_window is window
    assert first.trial_id != second.trial_id
    with pytest.raises(ValueError, match="warmup_start"):
        EvaluationWindow(
            start=datetime(2021, 1, 4, tzinfo=UTC),
            end=datetime(2021, 1, 5, tzinfo=UTC),
            purpose="training",
            warmup_start=datetime(2021, 1, 6, tzinfo=UTC),
        )


def test_capability_preflight_fails_closed_and_labels_explicit_degradation() -> None:
    rigorous = preflight_capabilities((_requirement(),), (_cell(),))
    assert rigorous.classification is PreflightClass.RIGOROUS
    assert rigorous.ranking_eligible

    missing = preflight_capabilities((_requirement(session="extended"),), (_cell(),))
    assert missing.classification is PreflightClass.UNSUPPORTED
    assert not missing.executable

    wrong_event_type = preflight_capabilities(
        (_requirement(),), (replace(_cell(), event_types=frozenset({"trades"})),)
    )
    assert wrong_event_type.classification is PreflightClass.UNSUPPORTED
    assert wrong_event_type.decisions[0].gaps == ("event_type",)

    declared = Degradation("US.AAPL", "session", "regular", "extended session unavailable")
    degraded = preflight_capabilities(
        (_requirement(session="extended"),),
        (_cell(),),
        allow_degraded=True,
        degradations=(declared,),
    )
    assert degraded.classification is PreflightClass.DEGRADED
    assert degraded.executable
    assert not degraded.ranking_eligible
    assert degraded.decisions[0].degradations == (declared,)
    with pytest.raises(ValueError, match="match the decision substitutions"):
        replace(rigorous, degradations=(declared,))

    alternate_cell = preflight_capabilities(
        (_requirement(session="extended"),),
        (_cell(), _cell(sessions=frozenset({"extended"}))),
    )
    assert alternate_cell.classification is PreflightClass.RIGOROUS
    regular_requirement = _requirement()
    extended_requirement = _requirement(session="extended")
    extended_cell = _cell(sessions=frozenset({"extended"}))
    ordered = preflight_capabilities(
        (regular_requirement, extended_requirement),
        (_cell(), extended_cell),
    )
    reversed_inputs = preflight_capabilities(
        (extended_requirement, regular_requirement),
        (extended_cell, _cell()),
    )
    assert ordered.fingerprint == reversed_inputs.fingerprint
    with pytest.raises(ValueError, match="must match values supported"):
        preflight_capabilities(
            (_requirement(session="extended"),),
            (_cell(),),
            allow_degraded=True,
            degradations=(Degradation("US.AAPL", "session", "overnight", "use overnight data"),),
        )


def test_search_grid_random_and_latin_hypercube_are_deterministic() -> None:
    design = SearchDesign(
        (
            SearchDimension("lookback", minimum=Decimal(5), maximum=Decimal(15), grid_steps=3),
            SearchDimension("side", choices=("long", "short")),
        )
    )
    grid = expand_parameter_sets(design, ExpansionMethod.GRID)
    assert len(grid) == 6
    assert {row["lookback"] for row in grid} == {Decimal(5), Decimal(10), Decimal(15)}

    random_a = expand_parameter_sets(design, ExpansionMethod.RANDOM, count=12, seed=41)
    random_b = expand_parameter_sets(design, ExpansionMethod.RANDOM, count=12, seed=41)
    assert random_a == random_b

    lhs = expand_parameter_sets(design, ExpansionMethod.LATIN_HYPERCUBE, count=8, seed=41)
    assert lhs == expand_parameter_sets(design, ExpansionMethod.LATIN_HYPERCUBE, count=8, seed=41)
    strata = {int((row["lookback"] - Decimal(5)) / Decimal(10) * Decimal(8)) for row in lhs}
    assert len(lhs) == 8
    assert all(Decimal(5) <= row["lookback"] < Decimal(15) for row in lhs)
    assert strata == set(range(8))

    scenarios = expand_scenario_matrix({"regime": ("calm", "stress"), "cost_bps": (0, 5)})
    plans = build_trial_designs(({"lookback": 5}, {"lookback": 10}), scenarios, seed=41)
    repeated = build_trial_designs(({"lookback": 5}, {"lookback": 10}), scenarios, seed=41)
    assert len(plans) == 8
    assert plans == repeated
    assert len({item.seed for item in plans}) == len(plans)
    assert [item.seed for item in plans] == [
        6980317637284689226,
        8685861484798666868,
        4423458724541804185,
        4469982436725750052,
        1295317444626196142,
        3296952616154428720,
        1590824964799001329,
        8319398782401529149,
    ]
    assert all(
        item.randomization.policy is TrialSeedPolicy.PER_CANDIDATE
        and item.randomization.replicate_index == 0
        and item.randomization.master_seed == 41
        and item.randomization.seed_group_fingerprint is not None
        and item.randomization.replicate_count == 1
        and not item.randomization.has_schedule_provenance
        for item in plans
    )
    preflight = preflight_capabilities((_requirement(),), (_cell(),))
    default_plan = plans[0]
    generated_trial = ScientificTrial.create(
        experiment_fingerprint=content_digest({"experiment": "legacy-id"}),
        snapshot_fingerprint=content_digest({"snapshot": "legacy-id"}),
        preflight_report=preflight,
        parameter_set=default_plan.parameters,
        scenario=default_plan.scenario,
        randomization=default_plan.randomization,
    )
    legacy_trial = ScientificTrial.create(
        experiment_fingerprint=generated_trial.experiment_fingerprint,
        snapshot_fingerprint=generated_trial.snapshot_fingerprint,
        preflight_report=preflight,
        parameter_set=default_plan.parameters,
        scenario=default_plan.scenario,
        seed=default_plan.seed,
    )
    assert generated_trial.randomization == default_plan.randomization
    assert generated_trial.trial_id == legacy_trial.trial_id
    with pytest.raises(ValueError, match="does not match its seed-group fingerprint"):
        replace(default_plan.randomization, seed=default_plan.seed + 1)
    with pytest.raises(ValueError, match="unsupported trial seed derivation version"):
        replace(default_plan.randomization, derivation_version="unrecognized.v1")

    independent_replicates = build_trial_designs(
        ({"lookback": 5},),
        scenarios[:1],
        seed=41,
        replicate_count=3,
    )
    assert [item.replicate_index for item in independent_replicates] == [0, 1, 2]
    assert all(item.randomization.replicate_count == 3 for item in independent_replicates)
    assert len({item.seed for item in independent_replicates}) == 3
    assert len(
        {item.randomization.seed_group_fingerprint for item in independent_replicates}
    ) == 3
    assert all(item.randomization.has_schedule_provenance for item in independent_replicates)


def test_trial_seed_sharing_is_explicit_replicated_and_identity_bound() -> None:
    scope = content_digest({"experiment": "fixed-input-scope"})
    parameters = ({"lookback": 5}, {"lookback": 10}, {"lookback": 20})
    scenarios = expand_scenario_matrix({"regime": ("calm", "stress")})
    plans = build_trial_designs(
        parameters,
        scenarios,
        seed=41,
        seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        replicate_count=3,
        scope_fingerprint=scope,
    )
    repeated = build_trial_designs(
        parameters,
        scenarios,
        seed=41,
        seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        replicate_count=3,
        scope_fingerprint=scope,
    )
    assert len(plans) == len(repeated) == 18
    assert plans == repeated

    assignments = {
        (item.scenario["regime"], item.replicate_index): item.randomization
        for item in plans
        if item.parameters["lookback"] == 5
    }
    for scenario in ("calm", "stress"):
        replicate_assignments = [assignments[(scenario, replicate)] for replicate in range(3)]
        assert len({item.seed for item in replicate_assignments}) == 3
        assert len({item.seed_group_fingerprint for item in replicate_assignments}) == 3

    for item in plans:
        peers = [
            other
            for other in plans
            if other.scenario == item.scenario
            and other.replicate_index == item.replicate_index
        ]
        assert len(peers) == 3
        assert {other.seed for other in peers} == {item.seed}
        assert {other.randomization.seed_group_fingerprint for other in peers} == {
            item.randomization.seed_group_fingerprint
        }
        assert item.randomization.policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE
        assert item.randomization.scope_fingerprint == scope
        assert item.randomization.master_seed == 41

    permuted = build_trial_designs(
        tuple(reversed(parameters)),
        tuple(reversed(scenarios)),
        seed=41,
        seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        replicate_count=3,
        scope_fingerprint=scope,
    )
    assignment_by_candidate = {
        (canonical_json(item.parameters), canonical_json(item.scenario), item.replicate_index): (
            item.seed,
            item.randomization.seed_group_fingerprint,
        )
        for item in plans
    }
    assert assignment_by_candidate == {
        (canonical_json(item.parameters), canonical_json(item.scenario), item.replicate_index): (
            item.seed,
            item.randomization.seed_group_fingerprint,
        )
        for item in permuted
    }

    other_master_seed = build_trial_designs(
        parameters,
        scenarios,
        seed=42,
        seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        replicate_count=3,
        scope_fingerprint=scope,
    )
    other_scope = build_trial_designs(
        parameters,
        scenarios,
        seed=41,
        seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        replicate_count=3,
        scope_fingerprint=content_digest({"experiment": "another-scope"}),
    )
    assert plans[0].randomization.seed_group_fingerprint != other_master_seed[0].randomization.seed_group_fingerprint
    assert plans[0].randomization.seed_group_fingerprint != other_scope[0].randomization.seed_group_fingerprint

    preflight = preflight_capabilities((_requirement(),), (_cell(),))
    first = ScientificTrial.create(
        experiment_fingerprint=scope,
        snapshot_fingerprint=content_digest({"snapshot": 1}),
        preflight_report=preflight,
        parameter_set=plans[0].parameters,
        scenario=plans[0].scenario,
        randomization=plans[0].randomization,
    )
    second = ScientificTrial.create(
        experiment_fingerprint=scope,
        snapshot_fingerprint=content_digest({"snapshot": 1}),
        preflight_report=preflight,
        parameter_set=plans[6].parameters,
        scenario=plans[6].scenario,
        randomization=plans[6].randomization,
    )
    assert first.seed == second.seed
    assert first.randomization == plans[0].randomization
    assert first.trial_id != second.trial_id
    same_candidate_next_replicate = ScientificTrial.create(
        experiment_fingerprint=scope,
        snapshot_fingerprint=content_digest({"snapshot": 1}),
        preflight_report=preflight,
        parameter_set=plans[1].parameters,
        scenario=plans[1].scenario,
        randomization=plans[1].randomization,
    )
    assert same_candidate_next_replicate.parameter_set == first.parameter_set
    assert same_candidate_next_replicate.seed != first.seed
    assert same_candidate_next_replicate.randomization.replicate_index == 1
    assert same_candidate_next_replicate.trial_id != first.trial_id
    with pytest.raises(ValueError, match="scope must match its experiment"):
        ScientificTrial.create(
            experiment_fingerprint=content_digest({"experiment": "wrong-scope"}),
            snapshot_fingerprint=content_digest({"snapshot": 1}),
            preflight_report=preflight,
            parameter_set=plans[0].parameters,
            scenario=plans[0].scenario,
            randomization=plans[0].randomization,
        )

    with pytest.raises(ValueError, match="positive integer"):
        build_trial_designs(parameters, scenarios, seed=41, replicate_count=0)
    with pytest.raises(ValueError, match="positive integer"):
        build_trial_designs(parameters, scenarios, seed=41, replicate_count=True)
    with pytest.raises(ValueError, match="seed must be an integer"):
        build_trial_designs(parameters, scenarios, seed=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fixed-input scope_fingerprint"):
        build_trial_designs(
            parameters,
            scenarios,
            seed=41,
            seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        )
    with pytest.raises(ValueError, match="unique parameter sets"):
        build_trial_designs(
            ({"lookback": 5}, {"lookback": 5}),
            scenarios,
            seed=41,
            seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
            scope_fingerprint=scope,
        )
    with pytest.raises(ValueError, match="unique scenarios"):
        build_trial_designs(
            parameters,
            (scenarios[0], scenarios[0]),
            seed=41,
            seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
            scope_fingerprint=scope,
        )
    with pytest.raises(ValueError, match="more than max_trials"):
        build_trial_designs(
            parameters,
            scenarios,
            seed=41,
            seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
            replicate_count=3,
            scope_fingerprint=scope,
            max_trials=17,
        )


def test_walk_forward_gaps_embargo_and_oos_aggregation_are_explicit() -> None:
    spec = WalkForwardSpec(
        train_periods=5,
        test_periods=2,
        step_periods=2,
        gap_periods=1,
        embargo_periods=1,
        mode=WalkForwardMode.ROLLING,
    )
    folds = build_walk_forward_folds(16, spec)
    assert folds[0].train_indices == (0, 1, 2, 3, 4)
    assert folds[0].excluded_indices == (5,)
    assert folds[0].test_indices == (6, 7)
    assert folds[1].train_indices == (1, 2, 3, 4, 5)
    assert 6 in folds[1].excluded_indices and 7 in folds[1].excluded_indices
    observations = tuple(range(16))
    assert aggregate_out_of_sample(folds, observations) == (6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
    with pytest.raises(ValueError, match="history is too short"):
        build_walk_forward_folds(6, spec)


def test_sdk_intents_are_typed_scoped_and_context_is_read_only() -> None:
    requirement = _requirement()
    strategy = StrategyVersion("s-1", "v-1", "2.0", SOURCE_DIGEST)
    dependency = StrategyDataDependency("daily-bars", requirement, ("close",), lookback_periods=0)
    manifest = StrategySdkManifest(strategy, (dependency,))
    market_event = MarketEvent(
        "daily-bars",
        "bar-1",
        "US.AAPL",
        END,
        10,
        {"close": Decimal("190.25")},
    )
    context = build_strategy_context(
        manifest,
        event_time=END,
        event_sequence=10,
        random_seed=7,
        parameters={"fast": 4},
        market_events={"daily-bars": (market_event,)},
        positions={
            "US.AAPL": PositionSnapshot("US.AAPL", Decimal(2), Decimal(180), Decimal(360))
        },
    )
    assert context.parameters["fast"] == 4
    assert context.market_events["daily-bars"][0].values["close"] == Decimal("190.25")
    assert context.positions["US.AAPL"].quantity == Decimal(2)
    with pytest.raises(TypeError):
        context.market_events["daily-bars"][0].values["close"] = Decimal(0)  # type: ignore[index]
    with pytest.raises(ValueError, match="missing required fields"):
        build_strategy_context(
            manifest,
            event_time=END,
            event_sequence=10,
            random_seed=7,
            parameters={},
            market_events={"daily-bars": (replace(market_event, values={}),)},
        )
    with pytest.raises(ValueError, match="undeclared fields"):
        build_strategy_context(
            manifest,
            event_time=END,
            event_sequence=10,
            random_seed=7,
            parameters={},
            market_events={
                "daily-bars": (
                    MarketEvent(
                        "daily-bars",
                        "bar-2",
                        "US.AAPL",
                        END,
                        11,
                        {"close": Decimal("190.25"), "secret": Decimal(7)},
                    ),
                )
            },
        )
    with pytest.raises(ValueError, match="cannot expose events"):
        build_strategy_context(
            manifest,
            event_time=END,
            event_sequence=10,
            random_seed=7,
            parameters={},
            market_events={
                "daily-bars": (
                    MarketEvent(
                        "daily-bars",
                        "bar-future-sequence",
                        "US.AAPL",
                        END,
                        11,
                        {"close": Decimal("190.25")},
                    ),
                )
            },
        )
    intents = validate_strategy_output(
        manifest,
        (
            OrderIntent("US.AAPL", OrderSide.BUY, Decimal("2"), OrderType.MARKET),
            TargetPositionIntent("US.AAPL", Decimal("0.5")),
        ),
    )
    assert len(intents) == 2
    with pytest.raises(ValueError, match="undeclared instrument"):
        validate_strategy_output(manifest, (TargetPositionIntent("US.MSFT", Decimal("0.5")),))
    with pytest.raises(ValueError, match="limit orders require"):
        OrderIntent("US.AAPL", OrderSide.BUY, Decimal(1), OrderType.LIMIT)


def test_metric_contracts_include_basis_sample_size_and_null_reason() -> None:
    metrics = calculate_performance_metrics(
        (Decimal(110), Decimal(100), Decimal(120)),
        initial_capital=Decimal(100),
        base_currency="USD",
        periods_per_year=252,
        basis=MetricBasis.NET,
    )
    by_name = {item.name: item for item in metrics}
    assert by_name["total_return"].value == Decimal("0.2")
    assert by_name["total_return"].basis is MetricBasis.NET
    assert by_name["sharpe_ratio"].value is not None
    assert by_name["sharpe_ratio"].annualization_basis == "252 observed periods per year"
    assert all(item.definition_version == "strategy-lab.metrics.v6" for item in metrics)

    trade_metrics = {
        item.name: item
        for item in calculate_trade_metrics((Decimal(10), Decimal(-5)), base_currency="USD")
    }
    assert trade_metrics["profit_factor"].value == Decimal(2)
    no_trades = {
        item.name: item for item in calculate_trade_metrics((), base_currency="USD")
    }
    assert no_trades["win_rate"].value is None
    assert no_trades["win_rate"].null_reason == "no completed trades"

    created = datetime(2024, 1, 1, tzinfo=UTC)
    metric_set = MetricSet(
        "metrics-1", "trial-1", "attempt-1", metrics[0].definition_version, metrics, created
    )
    assert len(metric_set.values) == len(metrics)
    with pytest.raises(ValueError, match="must match their metric-set"):
        MetricSet("metrics-2", "trial-1", "attempt-1", "other-version", metrics, created)


def test_portfolio_snapshot_and_artifact_manifests_are_versioned_and_content_addressed() -> None:
    strategy = StrategyVersion("s-1", "v1", "2.0", SOURCE_DIGEST)
    component = PortfolioComponent(
        "component-1", strategy.fingerprint, ("US.AAPL",), Decimal("0.60"), priority=1
    )
    portfolio = PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("100000"),
        "usd",
        (component,),
        rebalance_policy=CalendarRebalancePolicy(
            calendar_id="XNYS",
            calendar_fingerprint=content_digest("XNYS-test-calendar"),
            cadence=RebalanceCadence.MONTHLY,
            trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        ),
        shared_risk_policy=SharedRiskPolicy(max_gross_exposure_fraction=Decimal("1.0")),
    )
    assert portfolio.base_currency == "USD"
    assert portfolio.unallocated_capital_weight == Decimal("0.40")
    assert portfolio.fingerprint == content_digest(portfolio)
    with pytest.raises(TypeError, match="CalendarRebalancePolicy or None"):
        replace(
            portfolio,
            rebalance_policy=cast(
                CalendarRebalancePolicy,
                {"frequency": "monthly"},
            ),
        )

    package = StrategyPackage(
        package_id="package-s1-v1",
        strategy_fingerprint=strategy.fingerprint,
        package_format=StrategyPackageFormat.SOURCE_ARCHIVE,
        archive_digest=content_digest({"package": "strategy archive"}),
        manifest_digest=content_digest({"manifest": "v1"}),
        dependency_lock_digest=content_digest({"dependencies": []}),
        archive_byte_length=512,
        entrypoint="strategy.main:Strategy",
        sdk_version="2.0",
        runtime_abi="cpython-312",
    )
    with pytest.raises(ValueError, match="entrypoint must use"):
        replace(package, entrypoint="not-an-entrypoint")

    series = DataSeriesManifest(
        instrument_id="US.AAPL",
        event_type="ohlcv",
        event_granularity=EventGranularity.BAR,
        timeframe="1d",
        session="regular",
        feed="consolidated",
        start=START,
        end=END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        corporate_action_semantics="split-adjusted-v1",
        coverage_evidence_digest=content_digest({"coverage": "verified fixture"}),
        content_digest=content_digest({"bars": 1}),
        row_count=100,
    )
    report = preflight_capabilities((_requirement(),), (_cell(),))
    snapshot = DataSnapshot(
        "snapshot-1",
        "provider-snapshot-1",
        report,
        (series,),
        datetime(2024, 1, 1, tzinfo=UTC),
    )
    snapshot_copy = DataSnapshot(
        "snapshot-2",
        "provider-snapshot-2",
        report,
        (series,),
        datetime(2024, 1, 2, tzinfo=UTC),
    )
    assert snapshot.fingerprint == snapshot_copy.fingerprint
    assert snapshot.fingerprint == content_digest(
        {
            "capability_contract_digest": snapshot.capability_contract_digest,
            "series": snapshot.series,
        }
    )

    with pytest.raises(ValueError, match="does not cover preflight requirement"):
        DataSnapshot(
            "snapshot-wrong-schema",
            "provider-snapshot-wrong-schema",
            report,
            (replace(series, event_type="trades"),),
            datetime(2024, 1, 5, tzinfo=UTC),
        )

    total_return_semantics = "total-return-v1"
    semantic_report = preflight_capabilities(
        (
            _requirement(),
            _requirement(corporate_action_semantics=total_return_semantics),
        ),
        (_cell(), _cell(corporate_action_semantics=total_return_semantics)),
    )
    alternate_semantics = replace(
        series,
        corporate_action_semantics=total_return_semantics,
        content_digest=content_digest({"bars": 2}),
    )
    semantic_snapshot = DataSnapshot(
        "snapshot-semantics",
        "provider-snapshot-semantics",
        semantic_report,
        (series, alternate_semantics),
        datetime(2024, 1, 5, tzinfo=UTC),
    )
    reversed_semantic_snapshot = DataSnapshot(
        "snapshot-semantics-reversed",
        "provider-snapshot-semantics-reversed",
        semantic_report,
        (alternate_semantics, series),
        datetime(2024, 1, 6, tzinfo=UTC),
    )
    assert semantic_snapshot.fingerprint == reversed_semantic_snapshot.fingerprint
    with pytest.raises(ValueError, match="row_count must be positive"):
        replace(series, row_count=True)

    midpoint = datetime(2021, 1, 1, tzinfo=UTC)
    segmented = DataSnapshot(
        "snapshot-segmented",
        "provider-snapshot-segmented",
        report,
        (
            replace(series, end=midpoint, content_digest=content_digest({"bars": 1})),
            replace(series, start=midpoint, content_digest=content_digest({"bars": 2})),
        ),
        datetime(2024, 1, 3, tzinfo=UTC),
    )
    assert len(segmented.series) == 2
    broad_series = replace(
        series,
        start=datetime(2019, 1, 1, tzinfo=UTC),
        end=datetime(2023, 1, 1, tzinfo=UTC),
    )
    broad_snapshot = DataSnapshot(
        "snapshot-broad",
        "provider-snapshot-broad",
        report,
        (broad_series,),
        datetime(2024, 1, 3, tzinfo=UTC),
    )
    assert broad_snapshot.series[0] == broad_series
    with pytest.raises(ValueError, match="does not cover preflight requirement"):
        DataSnapshot(
            "snapshot-short",
            "provider-snapshot-short",
            report,
            (replace(series, end=datetime(2021, 12, 31, tzinfo=UTC)),),
            datetime(2024, 1, 4, tzinfo=UTC),
        )
    overlap_start = datetime(2020, 12, 31, tzinfo=UTC)
    with pytest.raises(ValueError, match="overlapping series coverage"):
        DataSnapshot(
            "snapshot-overlap",
            "provider-snapshot-overlap",
            report,
            (
                replace(series, end=midpoint),
                replace(series, start=overlap_start),
            ),
            datetime(2024, 1, 4, tzinfo=UTC),
        )
    with pytest.raises(TypeError, match="typed PreflightReport"):
        DataSnapshot(
            "snapshot-unchecked",
            "provider-snapshot-unchecked",
            content_digest({"capability": 1}),  # type: ignore[arg-type]
            (series,),
            datetime(2024, 1, 5, tzinfo=UTC),
        )

    trial = ScientificTrial.create(
        experiment_fingerprint=content_digest({"experiment": 1}),
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=report,
        parameter_set={"lookback": 20},
        seed=11,
    )
    created = datetime(2024, 1, 1, tzinfo=UTC)
    attempt = RunAttempt("attempt-result-1", trial.trial_id, 1, AttemptState.SUCCEEDED, created)
    metric_value = MetricValue(
        "total_return",
        Decimal("0.15"),
        "fraction",
        "strategy-lab.metrics.v2",
        MetricBasis.NET,
        252,
    )
    metric_set = MetricSet(
        "result-metrics-1",
        trial.trial_id,
        attempt.attempt_id,
        "strategy-lab.metrics.v2",
        (metric_value,),
        created,
    )
    equity_digest = content_digest({"equity": "parquet"})
    result = RunResultManifest(
        trial=trial,
        attempt=attempt,
        strategy_packages=(package,),
        portfolio=portfolio,
        snapshot=snapshot,
        engine_name="nautilus",
        engine_version="2.0.0",
        engine_build_digest=content_digest({"engine-build": 1}),
        allocation_definition_version=ALLOCATION_DEFINITION_VERSION,
        dependency_catalog_digest=content_digest({"catalog": 1}),
        assumptions_digest=content_digest({"assumptions": 1}),
        metric_set=metric_set,
        output_artifacts=(
            ArtifactManifest(equity_digest, 1024, "application/parquet", "1", equity_digest),
        ),
        created_at=created,
    )

    def result_for_trial(trial: ScientificTrial, attempt_id: str) -> RunResultManifest:
        attempt = RunAttempt(
            attempt_id, trial.trial_id, 1, AttemptState.SUCCEEDED, created
        )
        trial_metrics = replace(
            metric_set,
            metric_set_id=f"metrics-{attempt_id}",
            trial_id=trial.trial_id,
            attempt_id=attempt_id,
        )
        return replace(result, trial=trial, attempt=attempt, metric_set=trial_metrics)

    equal_seed_trial = ScientificTrial.create(
        experiment_fingerprint=result.experiment_fingerprint,
        snapshot_fingerprint=result.snapshot_fingerprint,
        preflight_report=report,
        parameter_set={"lookback": 30},
        seed=result.seed,
    )
    equal_seed_result = result_for_trial(equal_seed_trial, "attempt-equal-seed")
    assert (
        SensitivityComparisonEvidence(result, equal_seed_result).evidence_level
        is SensitivityEvidenceLevel.UNPAIRED
    )

    shared_designs = build_trial_designs(
        ({"lookback": 20}, {"lookback": 30}),
        ({},),
        seed=17,
        seed_policy=TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE,
        replicate_count=2,
        scope_fingerprint=result.experiment_fingerprint,
    )

    def trial_for_design(index: int) -> ScientificTrial:
        design = shared_designs[index]
        return ScientificTrial.create(
            experiment_fingerprint=result.experiment_fingerprint,
            snapshot_fingerprint=result.snapshot_fingerprint,
            preflight_report=report,
            parameter_set=design.parameters,
            scenario=design.scenario,
            seed=design.seed,
            randomization=design.randomization,
        )

    shared_baseline = result_for_trial(trial_for_design(0), "attempt-shared-baseline")
    shared_variant = result_for_trial(trial_for_design(2), "attempt-shared-variant")
    shared_evidence = SensitivityComparisonEvidence(shared_baseline, shared_variant)
    assert shared_evidence.evidence_level is SensitivityEvidenceLevel.SHARED_SEED_ONLY
    shared_delta = compare_one_factor_metric(
        shared_evidence, metric_name="total_return", basis=MetricBasis.NET
    )
    assert isinstance(shared_delta, MetricDeltaUnavailable)
    assert shared_delta.evidence_level is SensitivityEvidenceLevel.SHARED_SEED_ONLY

    different_replicate = result_for_trial(trial_for_design(3), "attempt-different-replicate")
    assert (
        SensitivityComparisonEvidence(shared_baseline, different_replicate).evidence_level
        is SensitivityEvidenceLevel.UNPAIRED
    )
    retry_of_result = result_for_trial(result.trial, "attempt-sensitivity-retry")
    with pytest.raises(ValueError, match="not sensitivity replicates"):
        SensitivityComparisonEvidence(result, retry_of_result)

    baseline_trace_digest = content_digest({"stream-trace": "baseline"})
    variant_trace_digest = content_digest({"stream-trace": "variant"})
    paired_draws_digest = content_digest({"aligned-keyed-draws": 4})
    pairing_claim = KeyedRandomStreamPairingClaim(
        baseline_attempt_id=shared_baseline.attempt_id,
        variant_attempt_id=shared_variant.attempt_id,
        engine_build_digest=shared_baseline.engine_build_digest,
        engine_conformance_fingerprint=content_digest({"engine-conformance": "keyed-v1"}),
        stream_contract_fingerprint=content_digest({"stream-contract": "keyed-v1"}),
        baseline_trace_digest=baseline_trace_digest,
        variant_trace_digest=variant_trace_digest,
        paired_draws_digest=paired_draws_digest,
        matched_draw_count=4,
    )

    def artifact_for(digest: str) -> ArtifactManifest:
        return ArtifactManifest(digest, 64, "application/json", "1", digest)

    paired_baseline = replace(
        shared_baseline,
        output_artifacts=(
            *shared_baseline.output_artifacts,
            artifact_for(baseline_trace_digest),
            artifact_for(paired_draws_digest),
            artifact_for(pairing_claim.fingerprint),
        ),
    )
    paired_variant = replace(
        shared_variant,
        output_artifacts=(
            *shared_variant.output_artifacts,
            artifact_for(variant_trace_digest),
            artifact_for(paired_draws_digest),
            artifact_for(pairing_claim.fingerprint),
        ),
    )
    paired_evidence = SensitivityComparisonEvidence(
        paired_baseline, paired_variant, pairing_claim
    )
    paired_delta = compare_one_factor_metric(
        paired_evidence, metric_name="total_return", basis=MetricBasis.NET
    )
    assert isinstance(paired_delta, MetricDeltaUnavailable)
    assert paired_delta.evidence_level is SensitivityEvidenceLevel.PAIRING_CLAIM_UNVERIFIED
    assert paired_evidence.fingerprint == SensitivityComparisonEvidence(
        paired_baseline, paired_variant, pairing_claim
    ).fingerprint
    assert paired_evidence.evidence_level is SensitivityEvidenceLevel.PAIRING_CLAIM_UNVERIFIED

    incomplete_baseline = replace(
        paired_baseline,
        output_artifacts=tuple(
            item
            for item in paired_baseline.output_artifacts
            if item.content_digest != pairing_claim.fingerprint
        ),
    )
    with pytest.raises(ValueError, match="referenced by both results"):
        SensitivityComparisonEvidence(incomplete_baseline, paired_variant, pairing_claim)
    with pytest.raises(ValueError, match="bind these result attempts"):
        SensitivityComparisonEvidence(
            paired_baseline,
            paired_variant,
            replace(pairing_claim, baseline_attempt_id="different-attempt"),
        )
    with pytest.raises(ValueError, match="one shared seed group"):
        SensitivityComparisonEvidence(
            paired_baseline,
            different_replicate,
            replace(pairing_claim, variant_attempt_id=different_replicate.attempt_id),
        )
    with pytest.raises(ValueError, match="complete draw-key alignment"):
        replace(pairing_claim, unmatched_variant_draw_count=1)
    different_observation_basis = replace(
        shared_variant.metric_set,
        values=(
            replace(
                shared_variant.metric_set.values[0],
                calculation_basis="same versioned formula; variant observation digest differs",
            ),
        ),
    )
    assert (
        SensitivityComparisonEvidence(
            shared_baseline,
            replace(shared_variant, metric_set=different_observation_basis),
        ).evidence_level
        is SensitivityEvidenceLevel.SHARED_SEED_ONLY
    )
    with pytest.raises(ValueError, match="fixed execution context"):
        SensitivityComparisonEvidence(
            shared_baseline,
            replace(
                shared_variant,
                engine_build_digest=content_digest({"engine-build": "different"}),
            ),
        )

    retry_attempt = RunAttempt(
        "attempt-result-2", trial.trial_id, 2, AttemptState.SUCCEEDED, created + timedelta(days=1)
    )
    retry_metrics = replace(
        metric_set,
        metric_set_id="result-metrics-2",
        attempt_id=retry_attempt.attempt_id,
        created_at=retry_attempt.created_at,
    )
    retry_result = replace(
        result,
        attempt=retry_attempt,
        metric_set=retry_metrics,
        created_at=retry_attempt.created_at,
    )
    assert result.reproduction_fingerprint == retry_result.reproduction_fingerprint
    assert result.fingerprint != retry_result.fingerprint
    unrelated_package = replace(
        package,
        strategy_fingerprint=content_digest({"strategy": "unrelated"}),
    )
    with pytest.raises(ValueError, match="packages must match the portfolio"):
        replace(result, strategy_packages=(unrelated_package,))

    digest = content_digest({"artifact": "parquet bytes"})
    artifact = ArtifactManifest(digest, 512, "application/vnd.apache.parquet", "1", digest)
    assert artifact.storage_key == artifact.content_digest
    with pytest.raises(ValueError, match="storage_key must equal"):
        ArtifactManifest(digest, 512, "application/vnd.apache.parquet", "1", "arbitrary-key")


def test_attempt_retry_preserves_trial_and_forward_events_are_auditable() -> None:
    created = datetime(2024, 1, 1, tzinfo=UTC)
    first = RunAttempt("attempt-1", "same-trial", 1, AttemptState.QUEUED, created)
    running = transition_attempt(first, AttemptState.RUNNING, now=created + timedelta(seconds=1))
    assert running.updated_at == created + timedelta(seconds=1)
    with pytest.raises(ValueError, match="cannot move backwards"):
        transition_attempt(running, AttemptState.FAILED, now=created + timedelta(milliseconds=500))
    failed = transition_attempt(running, AttemptState.FAILED, now=created + timedelta(seconds=2))
    retry = create_retry_attempt(
        (failed,), attempt_id="attempt-2", created_at=created + timedelta(seconds=3)
    )
    assert retry.trial_id == first.trial_id
    assert retry.ordinal == 2

    cursor = ForwardCursor(last_sequence=3, last_event_id="e3", last_event_time=created)
    gap_event = CanonicalForwardEvent(
        "e6", 6, created + timedelta(seconds=3), created + timedelta(seconds=3), EVIDENCE_DIGEST
    )
    gap = observe_forward_event(cursor, gap_event)
    assert gap.disposition is ForwardEventDisposition.GAP
    assert (gap.missing_sequence_start, gap.missing_sequence_end) == (4, 5)
    assert gap.buffer_event
    assert gap.next_cursor == cursor

    event4 = CanonicalForwardEvent(
        "e4", 4, created + timedelta(seconds=1), created + timedelta(seconds=1), EVIDENCE_DIGEST
    )
    event5 = CanonicalForwardEvent(
        "e5", 5, created + timedelta(seconds=2), created + timedelta(seconds=2), EVIDENCE_DIGEST
    )
    accepted4 = observe_forward_event(cursor, event4)
    accepted5 = observe_forward_event(accepted4.next_cursor, event5)
    recovered6 = observe_forward_event(accepted5.next_cursor, gap_event)
    assert accepted4.disposition is ForwardEventDisposition.ACCEPTED
    assert accepted5.disposition is ForwardEventDisposition.ACCEPTED
    assert recovered6.disposition is ForwardEventDisposition.ACCEPTED
    assert recovered6.next_cursor.last_sequence == 6

    duplicate = observe_forward_event(
        recovered6.next_cursor,
        CanonicalForwardEvent(
            "e6", 6, created + timedelta(seconds=3), created + timedelta(seconds=4), EVIDENCE_DIGEST
        ),
        processed_event_ids=frozenset({"e6"}),
    )
    assert duplicate.disposition is ForwardEventDisposition.DUPLICATE
    assert duplicate.next_cursor == recovered6.next_cursor

    correction = observe_forward_event(
        recovered6.next_cursor,
        CanonicalForwardEvent(
            "e6-correction",
            7,
            created + timedelta(seconds=3),
            created + timedelta(minutes=6),
            EVIDENCE_DIGEST,
            correction_of="e6",
        ),
    )
    assert correction.disposition is ForwardEventDisposition.CORRECTION
    assert correction.stale
    assert correction.correction_requires_counterfactual_replay
    assert correction.next_cursor == recovered6.next_cursor
