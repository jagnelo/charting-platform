from __future__ import annotations

from pathlib import Path

DOCKERFILE = Path(__file__).parents[1] / "nautilus_runtime_image" / "Dockerfile"


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


def test_rc_runtime_image_is_probe_only_and_defaults_to_non_authoritative_rc5() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["python", "-m", "app.strategy_lab_v2.nautilus_runtime_probe"]' in source
    assert 'CMD ["--expected-version", "2.0.0rc5"]' in source
