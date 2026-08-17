import ast
import re
from pathlib import Path

from app.services.code_validation import validate_workstation_python
from research_runner.runner import execute_job

FRONTEND_STUDY_LAB = (
    Path(__file__).resolve().parents[4]
    / "frontend"
    / "src"
    / "components"
    / "workstation"
    / "StudyLabTool.vue"
)


def _source_constant(name: str) -> str:
    text = FRONTEND_STUDY_LAB.read_text(encoding="utf-8")
    match = re.search(rf"^const {re.escape(name)} = (\".*\")$", text, re.MULTILINE)
    assert match, f"missing Study Lab source constant: {name}"
    return ast.literal_eval(match.group(1))


def _source_constants() -> dict[str, str]:
    text = FRONTEND_STUDY_LAB.read_text(encoding="utf-8")
    return {
        name: ast.literal_eval(raw)
        for name, raw in re.findall(r"^const (\w+Source) = (\".*\")$", text, re.MULTILINE)
    }


def test_all_named_factory_sources_match_the_actual_sandbox_policy():
    sources = _source_constants()

    assert len(sources) >= 12
    for name, source in sources.items():
        result = validate_workstation_python(source)
        assert result.diagnostics == (), name


def test_seasonality_factory_source_matches_the_actual_sandbox_policy():
    source = _source_constant("seasonalitySource")
    result = validate_workstation_python(source)

    assert result.diagnostics == ()
    assert set(result.output_contracts) == {"bar", "table"}
    assert "weekday_names = ['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']" in source
    assert "lambda" not in source


def test_seasonality_factory_source_executes_all_calendar_outputs_in_the_runner():
    source = _source_constant("seasonalitySource")
    result = execute_job(
        {
            "source": source,
            "dataset": {
                "symbol": "SPY",
                "timestamps": [
                    "2026-01-01",
                    "2026-01-02",
                    "2026-01-03",
                    "2026-01-04",
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-07",
                    "2026-01-08",
                ],
                "closes": [100, 101, 102, 101, 103, 104, 105, 106],
            },
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["average_monthly_return"]["type"] == "bar"
    assert result["artifacts"]["average_day_of_month_return"]["type"] == "bar"
    assert result["artifacts"]["average_day_of_week_return"]["type"] == "bar"
    assert result["artifacts"]["day_of_week_observations"]["type"] == "table"


def test_all_named_factory_sources_execute_against_a_prepared_fixture():
    timestamps = [f"2026-01-{day:02d}" for day in range(1, 31)]
    closes = [100 + day + (day % 4) for day in range(30)]
    dataset = {
        "symbol": "SPY",
        "timestamps": timestamps,
        "closes": closes,
        "benchmark_dataset": {
            "symbol": "SPY",
            "status": "ready",
            "closes": [200 + day for day in range(30)],
            "timestamps": timestamps,
        },
        "datasets": [
            {
                "instrument_id": 1,
                "symbol": "SPY",
                "closes": closes,
                "volumes": [1000 + day * 10 for day in range(30)],
                "timestamps": timestamps,
            },
            {
                "instrument_id": 2,
                "symbol": "XLK",
                "closes": [90 + day * 2 for day in range(30)],
                "volumes": [900 + day * 8 for day in range(30)],
                "timestamps": timestamps,
            },
            {
                "instrument_id": 3,
                "symbol": "XLE",
                "closes": [120 + day for day in range(30)],
                "volumes": [800 + day * 6 for day in range(30)],
                "timestamps": timestamps,
            },
        ],
    }

    aggregate_sources = {
        "crossSectionalRankSource",
        "breadthParticipationSource",
        "breadthThrustSource",
        "breadthThrustHistorySource",
        "genericBreadthSource",
        "genericHighBreadthSource",
        "crossSectionalBreadthSource",
    }
    for name, source in _source_constants().items():
        run_dataset = (
            dataset
            if name in aggregate_sources
            else {key: value for key, value in dataset.items() if key != "datasets"}
        )
        job = {"source": source, "dataset": run_dataset}
        if name in aggregate_sources:
            job["output_contract"] = "study"
        result = execute_job(job)
        assert result["status"] == "completed", (name, result.get("diagnostics"))
