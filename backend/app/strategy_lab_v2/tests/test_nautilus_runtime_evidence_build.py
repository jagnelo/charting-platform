from __future__ import annotations

from pathlib import Path

import pytest

from app.strategy_lab_v2.nautilus_runtime_image.evidence_build import (
    copy_runtime_build_context,
    runtime_image_source_digest,
    runtime_image_source_paths,
)


def _build_source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    (root / "runtime").mkdir(parents=True)
    (root / "runtime" / "Dockerfile").write_text(
        "FROM example@sha256:abc\nCOPY app/one.py app/one.py\n"
        "COPY strategy_runtime/protocol.py strategy_runtime/protocol.py\n",
        encoding="utf-8",
    )
    (root / "app").mkdir()
    (root / "app" / "one.py").write_text("print('one')\n", encoding="utf-8")
    (root / "strategy_runtime").mkdir()
    (root / "strategy_runtime" / "protocol.py").write_text("VERSION = 1\n", encoding="utf-8")
    (root / "unrelated.py").write_text("must not enter the image context\n", encoding="utf-8")
    return root


def test_runtime_source_manifest_is_sorted_and_hashes_only_docker_inputs(tmp_path: Path) -> None:
    root = _build_source(tmp_path)

    paths = runtime_image_source_paths(root, dockerfile_relative_path="runtime/Dockerfile")
    digest = runtime_image_source_digest(root, dockerfile_relative_path="runtime/Dockerfile")

    assert tuple(path.as_posix() for path in paths) == (
        "app/one.py",
        "runtime/Dockerfile",
        "strategy_runtime/protocol.py",
    )
    assert digest.startswith("sha256:")


def test_runtime_source_digest_changes_when_any_copied_file_changes(tmp_path: Path) -> None:
    root = _build_source(tmp_path)
    first = runtime_image_source_digest(root, dockerfile_relative_path="runtime/Dockerfile")

    (root / "app" / "one.py").write_text("print('two')\n", encoding="utf-8")

    second = runtime_image_source_digest(root, dockerfile_relative_path="runtime/Dockerfile")
    assert first != second


def test_build_context_copies_exactly_the_hashed_files(tmp_path: Path) -> None:
    root = _build_source(tmp_path)
    context = tmp_path / "context"

    copied = copy_runtime_build_context(
        root,
        context,
        dockerfile_relative_path="runtime/Dockerfile",
    )

    assert len(copied) == 3
    assert not (context / "unrelated.py").exists()
    assert (context / "runtime/Dockerfile").read_text(encoding="utf-8").startswith("FROM")


@pytest.mark.parametrize(
    "dockerfile",
    (
        "FROM example\nCOPY ../outside.py /app/outside.py\n",
        "FROM example\nCOPY app/*.py /app/\n",
        "FROM example\nCOPY --from=other app/one.py /app/one.py\n",
    ),
)
def test_runtime_source_manifest_rejects_unreviewed_copy_forms(
    tmp_path: Path,
    dockerfile: str,
) -> None:
    root = _build_source(tmp_path)
    (root / "runtime" / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    with pytest.raises(ValueError):
        runtime_image_source_paths(root, dockerfile_relative_path="runtime/Dockerfile")
