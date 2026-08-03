from app.services.code_validation import validate_workstation_python


def test_validates_sdk_dependencies_without_execution():
    result = validate_workstation_python("series = ta.sma(market.close('SPY'), 20)\noutput.series('trend', series)")
    assert result.valid
    assert result.dependencies == ("market", "output", "ta")
    assert result.lookback_hint == 20
    assert result.output_contracts == ("series",)


def test_collects_all_declared_output_contracts_without_executing_source():
    result = validate_workstation_python("output.scalar('n', 1)\noutput.boolean('qualifies', 1 > 0)\noutput.histogram('distribution', [1, 2])\noutput.scatter('relationship', [1], [2])\noutput.heatmap('matrix', [[1]])\noutput.dashboard('overview', [{'artifact': 'n'}])")
    assert result.valid
    assert result.output_contracts == ("boolean", "dashboard", "heatmap", "histogram", "scalar", "scatter")


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


def test_rejects_numpy_and_pandas_file_access():
    result = validate_workstation_python("pd.read_csv('/tmp/secret.csv')")
    assert not result.valid
    assert result.diagnostics[0].code == "forbidden_data_access"


def test_accepts_curated_scipy_namespace():
    result = validate_workstation_python(
        "score = scipy.stats.percentileofscore([1, 2, 3], 2)\noutput.scalar('percentile', score)"
    )
    assert result.valid
    assert result.dependencies == ("output", "scipy")


def test_accepts_curated_statsmodels_and_local_method_composition():
    result = validate_workstation_python(
        "model = statsmodels.api.OLS([1, 2, 3], [[1, 1], [1, 2], [1, 3]])\n"
        "fit = model.fit()\n"
        "output.scalar('r_squared', fit.rsquared)"
    )
    assert result.valid
    assert result.dependencies == ("output", "statsmodels")


def test_unbound_namespace_is_still_rejected():
    result = validate_workstation_python("model.fit()")
    assert not result.valid
    assert result.diagnostics[0].code == "unapproved_namespace"
