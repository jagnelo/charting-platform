from __future__ import annotations

from pathlib import Path

from app.strategy_lab_v2.conformance import NAUTILUS_V2_RC_WHEEL_SHA256
from app.strategy_lab_v2.nautilus_runtime_image.evidence_build import (
    PACKAGE_VERSION_LABEL,
    SOURCE_DIGEST_LABEL,
    WHEEL_DIGEST_LABEL,
)

DOCKERFILE = Path(__file__).parents[1] / "nautilus_runtime_image" / "Dockerfile"
DOCKERIGNORE = DOCKERFILE.with_name("Dockerfile.dockerignore")
REPORTING_REQUIREMENTS = DOCKERFILE.with_name("reporting-requirements.txt")


def test_rc_runtime_image_requires_explicit_base_and_wheel_integrity_inputs() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG PYTHON_BASE_IMAGE" in source
    assert "FROM ${PYTHON_BASE_IMAGE}" in source
    assert "ARG NAUTILUS_WHEEL_URL" in source
    assert "ARG NAUTILUS_WHEEL_SHA256" in source
    assert "ARG NAUTILUS_WHEEL_FILENAME" in source
    assert 'test -n "${NAUTILUS_WHEEL_URL}"' in source
    assert (
        f'test "${{NAUTILUS_WHEEL_SHA256}}" = "{NAUTILUS_V2_RC_WHEEL_SHA256.removeprefix("sha256:")}"'
        in source
    )
    assert 'test -n "${NAUTILUS_WHEEL_FILENAME}"' in source
    assert "ARG NAUTILUS_SOURCE_DIGEST" in source
    assert f"{SOURCE_DIGEST_LABEL}=${{NAUTILUS_SOURCE_DIGEST}}" in source
    assert f"{PACKAGE_VERSION_LABEL}=2.0.0rc5" in source
    assert f"{WHEEL_DIGEST_LABEL}=${{NAUTILUS_WHEEL_SHA256}}" in source
    assert "ADD --checksum=sha256:${NAUTILUS_WHEEL_SHA256}" in source
    assert "COPY app/strategy_lab_v2/nautilus_runtime_image/reporting-requirements.txt" in source
    assert "--requirement /opt/strategy-lab-v2/reporting-requirements.txt" in source
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
        "COPY app/strategy_lab_v2/nautilus_session_equity.py app/strategy_lab_v2/nautilus_session_equity.py"
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
        "COPY app/strategy_lab_v2/nautilus_portfolio_wire.py app/strategy_lab_v2/nautilus_portfolio_wire.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_rebalance_wire.py app/strategy_lab_v2/nautilus_rebalance_wire.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_rebalance_schedule.py app/strategy_lab_v2/nautilus_rebalance_schedule.py"
        in source
    )
    assert "COPY app/strategy_lab_v2/allocation.py app/strategy_lab_v2/allocation.py" in source
    assert "COPY app/strategy_lab_v2/risk_models.py app/strategy_lab_v2/risk_models.py" in source
    assert (
        "COPY app/strategy_lab_v2/order_routing.py app/strategy_lab_v2/order_routing.py" in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_target_allocation.py app/strategy_lab_v2/nautilus_target_allocation.py"
        in source
    )
    assert (
        "COPY app/strategy_lab_v2/nautilus_order_routing.py app/strategy_lab_v2/nautilus_order_routing.py"
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
        "COPY app/strategy_lab_v2/nautilus_calendar_wire.py app/strategy_lab_v2/nautilus_calendar_wire.py"
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
    assert "!app/strategy_lab_v2/nautilus_portfolio_wire.py" in source
    assert "!app/strategy_lab_v2/nautilus_rebalance_schedule.py" in source
    assert "!app/strategy_lab_v2/nautilus_session_equity.py" in source
    assert "!app/strategy_lab_v2/nautilus_calendar_wire.py" in source
    assert "!app/strategy_lab_v2/allocation.py" in source
    assert "!app/strategy_lab_v2/risk_models.py" in source
    assert "!app/strategy_lab_v2/order_routing.py" in source
    assert "!app/strategy_lab_v2/nautilus_target_allocation.py" in source
    assert "!app/strategy_lab_v2/nautilus_order_routing.py" in source
    assert "!app/strategy_lab_v2/nautilus_native_event_stream.py" in source
    assert "!strategy_runtime/protocol.py" in source
    assert "!strategy_runtime/runner.py" in source
    assert "!app/strategy_lab_v2/nautilus_runtime_image/reporting-requirements.txt" in source


def test_rc_runtime_reporting_stack_is_exactly_pinned() -> None:
    source = REPORTING_REQUIREMENTS.read_text(encoding="utf-8")

    assert source.splitlines() == [
        "numpy==2.2.6",
        "pandas==2.2.3",
        "pyarrow==25.0.1",
        "python-dateutil==2.9.0.post0",
        "pytz==2025.2",
        "six==1.17.0",
        "tzdata==2025.2",
    ]


def test_rc_runtime_image_defaults_to_non_authoritative_rc5_runtime_cli_probe() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert (
        'CMD ["python", "-m", "app.strategy_lab_v2.nautilus_runtime_cli", "--probe", "--expected-version", "2.0.0rc5"]'
        in source
    )
