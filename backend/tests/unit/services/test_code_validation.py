from app.services.code_validation import validate_workstation_python


def test_validates_sdk_dependencies_without_execution():
    result = validate_workstation_python("series = ta.sma(market.close('SPY'), 20)\noutput.series('trend', series)")
    assert result.valid
    assert result.dependencies == ("market", "output", "ta")
    assert result.lookback_hint == 20


def test_rejects_imports_and_dynamic_execution_with_source_positions():
    result = validate_workstation_python("import os\neval('1 + 1')")
    assert not result.valid
    assert {(item.code, item.line) for item in result.diagnostics} == {
        ("forbidden_syntax", 1),
        ("forbidden_call", 2),
    }


def test_rejects_dunder_escape_attempts():
    result = validate_workstation_python("market.__class__")
    assert not result.valid
    assert result.diagnostics[0].code == "forbidden_attribute"
