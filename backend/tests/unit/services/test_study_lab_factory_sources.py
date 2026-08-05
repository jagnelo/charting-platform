import ast
import re
from pathlib import Path

from app.services.code_validation import validate_workstation_python


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
