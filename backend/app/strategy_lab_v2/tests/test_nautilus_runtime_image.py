from __future__ import annotations

from pathlib import Path

DOCKERFILE = Path(__file__).parents[1] / "nautilus_runtime_image" / "Dockerfile"
DOCKERIGNORE = DOCKERFILE.with_name("Dockerfile.dockerignore")


def test_rc_runtime_image_requires_explicit_base_and_wheel_integrity_inputs() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG PYTHON_BASE_IMAGE" in source
    assert "FROM ${PYTHON_BASE_IMAGE}" in source
    assert "ARG NAUTILUS_WHEEL_URL" in source
    assert "ARG NAUTILUS_WHEEL_SHA256" in source
    assert "ARG NAUTILUS_WHEEL_FILENAME" in source
    assert 'test -n "${NAUTILUS_WHEEL_URL}"' in source
    assert 'test -n "${NAUTILUS_WHEEL_FILENAME}"' in source
    assert "ADD --checksum=sha256:${NAUTILUS_WHEEL_SHA256}" in source
    assert "pyproject.toml" not in source
    assert "backend/.venv" not in source
    assert "COPY app/strategy_lab_v2/__init__.py app/strategy_lab_v2/__init__.py" in source
    assert "COPY strategy_runtime/protocol.py strategy_runtime/protocol.py" in source
    assert "COPY strategy_runtime/runner.py strategy_runtime/runner.py" in source
    assert (
        "COPY app/strategy_lab_v2/nautilus_strategy_bridge.py app/strategy_lab_v2/nautilus_strategy_bridge.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_rc_fixture_probe.py app/strategy_lab_v2/nautilus_rc_fixture_probe.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_runtime_data.py app/strategy_lab_v2/nautilus_runtime_data.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_runtime_adapter.py app/strategy_lab_v2/nautilus_runtime_adapter.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_runtime_adapter_probe.py app/strategy_lab_v2/nautilus_runtime_adapter_probe.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_runtime_cli.py app/strategy_lab_v2/nautilus_runtime_cli.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_native_event_stream.py app/strategy_lab_v2/nautilus_native_event_stream.py"
        in source
    )


def test_rc_runtime_context_excludes_everything_outside_the_pinned_runtime_sources() -> None:
    source = DOCKERIGNORE.read_text(encoding="utf-8")

    assert "**" in source
    assert "!app/strategy_lab_v2/strategy_validation.py" in source
    assert "!app/strategy_lab_v2/nautilus_native_event_stream.py" in source
    assert "!strategy_runtime/protocol.py" in source
    assert "!strategy_runtime/runner.py" in source


def test_rc_runtime_image_defaults_to_non_authoritative_rc5_runtime_cli_probe() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert (
        'CMD ["python", "-m", "app.strategy_lab_v2.nautilus_runtime_cli", "--probe", "--expected-version", "2.0.0rc5"]'
        in source
    )
