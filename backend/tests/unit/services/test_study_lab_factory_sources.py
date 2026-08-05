import ast
import re
from pathlib import Path

from app.services.code_validation import validate_workstation_python
from research_runner.runner import execute_job


FRONTEND_STUDY_LAB = Path(__file__).resolve().parents[4] / "frontend" / "src" / "components" / "workstation" / "StudyLabTool.vue"


def _source_constant(name: str) -> str:
    text = FRONTEND_STUDY_LAB.read_text(encoding="utf-8")
    match = re.search(rf"^const {re.escape(name)} = (\".*\")$", text, re.MULTILINE)
    assert match, f"missing Study Lab source constant: {name}"
    return ast.literal_eval(match.group(1))


def test_seasonality_factory_source_matches_the_actual_sandbox_policy():
    source = _source_constant("seasonalitySource")
    result = validate_workstation_python(source)

    assert result.diagnostics == ()
    assert set(result.output_contracts) == {"bar", "table"}
    assert "weekday_names = ['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']" in source
    assert "lambda" not in source


def test_seasonality_factory_source_executes_all_calendar_outputs_in_the_runner():
    source = _source_constant("seasonalitySource")
    result = execute_job({
        "source": source,
        "dataset": {
            "symbol": "SPY",
            "timestamps": [
                "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04",
                "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
            ],
            "closes": [100, 101, 102, 101, 103, 104, 105, 106],
        },
    })

    assert result["status"] == "completed"
    assert result["artifacts"]["average_monthly_return"]["type"] == "bar"
    assert result["artifacts"]["average_day_of_month_return"]["type"] == "bar"
    assert result["artifacts"]["average_day_of_week_return"]["type"] == "bar"
    assert result["artifacts"]["day_of_week_observations"]["type"] == "table"
