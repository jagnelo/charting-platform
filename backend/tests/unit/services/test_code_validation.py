import pytest

from app.services.code_validation import validate_workstation_python


def test_validates_sdk_dependencies_without_execution():
    result = validate_workstation_python("series = ta.sma(market.close('SPY'), 20)\noutput.series('trend', series)")
    assert result.valid
    assert result.dependencies == ("market", "output", "ta")
    assert result.lookback_hint == 20
    assert result.output_contracts == ("series",)


def test_collects_all_declared_output_contracts_without_executing_source():
    result = validate_workstation_python("output.scalar('n', 1)\noutput.boolean('qualifies', 1 > 0)\noutput.bar('ranking', ['A'], [1])\noutput.histogram('distribution', [1, 2])\noutput.range('band', [1], [2])\noutput.scatter('relationship', [1], [2])\noutput.heatmap('matrix', [[1]])\noutput.dashboard('overview', [{'artifact': 'n'}])")
    assert result.valid
    assert result.output_contracts == ("bar", "boolean", "dashboard", "heatmap", "histogram", "range", "scalar", "scatter")


def test_rejects_imports_and_dynamic_execution_with_source_positions():
    result = validate_workstation_python("import os\neval('1 + 1')")
    assert not result.valid
    assert {(item.code, item.line) for item in result.diagnostics} == {
        ("forbidden_syntax", 1),
        ("forbidden_call", 2),
    }


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        ("open('/tmp/secret')", "forbidden_call"),
        ("__import__('socket')", "forbidden_name"),
        ("eval('1 + 1')", "forbidden_call"),
        ("compile('1 + 1', '<user>', 'eval')", "forbidden_call"),
        ("globals()", "forbidden_call"),
        ("locals()", "forbidden_call"),
        ("vars()", "forbidden_call"),
        ("socket.socket()", "unapproved_namespace"),
        ("subprocess.Popen(['id'])", "unapproved_namespace"),
        ("getattr(market, 'close')", "forbidden_call"),
        ("setattr(market, 'close', None)", "forbidden_call"),
        ("delattr(market, 'close')", "forbidden_call"),
        ("type('Escape', (), {})", "unapproved_namespace"),
    ],
)
def test_rejects_filesystem_network_process_reflection_and_dynamic_type_access(source, expected_code):
    result = validate_workstation_python(source)
    assert not result.valid
    assert any(item.code == expected_code for item in result.diagnostics)


def test_rejects_dunder_escape_attempts():
    result = validate_workstation_python("market.__class__")
    assert not result.valid
    assert result.diagnostics[0].code == "forbidden_attribute"


@pytest.mark.parametrize(
    "source",
    [
        "market.__dict__",
        "output.scalar.__globals__",
        "values = np.array([1])\nvalues.__array_interface__",
        "model = statsmodels.api.OLS([1, 2], [[1], [1]])\nmodel.__class__",
    ],
)
def test_rejects_object_graph_introspection_paths(source):
    result = validate_workstation_python(source)
    assert not result.valid
    assert any(item.code in {"forbidden_name", "forbidden_attribute"} for item in result.diagnostics)


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


def test_accepts_safe_python_composition_builtins():
    result = validate_workstation_python(
        "values = [1, 2, 3]\noutput.scalar('count', len(values))\noutput.scalar('total', sum(values))"
    )
    assert result.valid
    assert result.output_contracts == ("scalar",)


def test_rejects_dunder_name_access_in_the_runner_validator():
    from research_runner.validation import validate_workstation_python as validate_runner

    result = validate_runner("__builtins__['eval']('1 + 1')")
    assert not result.valid
    assert result.diagnostics[0].code == "forbidden_name"


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
