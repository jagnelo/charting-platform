"""Build and qualify an exact, isolated Nautilus RC6 image locally.

The build context is reconstructed from the image Dockerfile's explicit COPY
inputs, so unrelated backend files never enter the engine image or Docker
daemon. The resulting image records a digest of its source/build inputs, runs
the lifecycle and simulator fixtures with networking disabled, and only then
publishes the typed conformance receipt into an operator-owned artifact store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.local_conformance_source import (
    LocalNautilusRcConformanceEvidencePublisher,
)
from app.strategy_lab_v2.nautilus_runtime import NautilusRcCompatibilityRuntime

PYTHON_BASE_IMAGE = (
    "python:3.12.4-slim@sha256:" "a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85"
)
NAUTILUS_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/59/9a/"
    "0886eb3c2610e802cb4c432f97bf5a323ff204ebee0b644ec738bf3f0f54/"
    "nautilus_trader-2.0.0rc6-cp312-cp312-manylinux_2_34_x86_64.whl"
)
NAUTILUS_WHEEL_SHA256 = "9b4002a7bf5e6399c51073039b740ccf3ca7a1e2584ff72c7d479f03eaa9658d"
NAUTILUS_WHEEL_FILENAME = "nautilus_trader-2.0.0rc6-cp312-cp312-manylinux_2_34_x86_64.whl"
NAUTILUS_PACKAGE_VERSION = "2.0.0rc6"
NAUTILUS_RUST_VERSION = "1.98.1"
EXPECTED_PYTHON_VERSION = "3.12.4"
SOURCE_DIGEST_LABEL = "org.charting-platform.strategy-lab.nautilus-source-digest"
WHEEL_DIGEST_LABEL = "org.charting-platform.strategy-lab.nautilus-wheel-sha256"
PACKAGE_VERSION_LABEL = "org.charting-platform.strategy-lab.nautilus-package-version"
DOCKERFILE_RELATIVE_PATH = "app/strategy_lab_v2/nautilus_runtime_image/Dockerfile"
SOURCE_MANIFEST_SCHEMA = "strategy-lab.nautilus-runtime-build-inputs.v1"
PROBE_MODULE = "app.strategy_lab_v2.nautilus_runtime_probe"
FIXTURE_MODULE = "app.strategy_lab_v2.nautilus_rc_fixture_probe"

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class NautilusRcImageQualification:
    """Exact local image and content-addressed conformance evidence result."""

    source_digest: str
    runtime_image_digest: str
    artifact_digest: str
    conformance_fingerprint: str
    tested_at: datetime

    def __post_init__(self) -> None:
        for field in ("source_digest", "runtime_image_digest", "artifact_digest"):
            require_sha256_digest(getattr(self, field), field_name=field)
        require_sha256_digest(self.conformance_fingerprint, field_name="conformance_fingerprint")
        if self.tested_at.tzinfo is None or self.tested_at.utcoffset() is None:
            raise ValueError("tested_at must be timezone-aware")


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("runtime image inputs must be safe relative paths")
    return path


def runtime_image_source_paths(
    source_root: Path,
    *,
    dockerfile_relative_path: str = DOCKERFILE_RELATIVE_PATH,
) -> tuple[PurePosixPath, ...]:
    """Return the Dockerfile and every explicit regular-file COPY input."""

    if not isinstance(source_root, Path):
        raise TypeError("source_root must be a Path")
    dockerfile_relative = _safe_relative_path(dockerfile_relative_path)
    try:
        source_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Nautilus runtime source root is unavailable") from exc
    dockerfile = source_root / Path(*dockerfile_relative.parts)
    if dockerfile.is_symlink() or not dockerfile.resolve(strict=True).is_relative_to(source_root):
        raise ValueError("Nautilus runtime Dockerfile must remain inside its source root")
    try:
        lines = dockerfile.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("Nautilus runtime Dockerfile is unavailable") from exc

    inputs: set[PurePosixPath] = {dockerfile_relative}
    for line_number, line in enumerate(lines, start=1):
        if not line.lstrip().upper().startswith("COPY "):
            continue
        try:
            tokens = shlex.split(line, comments=True, posix=True)
        except ValueError as exc:
            raise ValueError(f"invalid Dockerfile quoting on line {line_number}") from exc
        if not tokens or tokens[0].upper() != "COPY":
            raise ValueError(f"invalid COPY instruction on Dockerfile line {line_number}")
        if any(token.startswith("--") for token in tokens[1:]):
            raise ValueError("runtime Dockerfile COPY flags require an explicit manifest update")
        if len(tokens) < 3:
            raise ValueError(f"COPY on Dockerfile line {line_number} has no source")
        for source in tokens[1:-1]:
            if any(char in source for char in "*?[]{}"):
                raise ValueError("runtime Dockerfile COPY sources must not contain globs")
            relative = _safe_relative_path(source)
            source_file = source_root / Path(*relative.parts)
            if (
                source_file.is_symlink()
                or not source_file.is_file()
                or not source_file.resolve(strict=True).is_relative_to(source_root)
            ):
                raise ValueError(f"runtime image source is missing or not a regular file: {source}")
            inputs.add(relative)
    return tuple(sorted(inputs, key=lambda path: path.as_posix()))


def runtime_image_source_digest(
    source_root: Path,
    *,
    dockerfile_relative_path: str = DOCKERFILE_RELATIVE_PATH,
) -> str:
    """Hash exact Dockerfile/COPY bytes and immutable upstream build pins."""

    source_root = source_root.resolve(strict=True)
    source_paths = runtime_image_source_paths(
        source_root,
        dockerfile_relative_path=dockerfile_relative_path,
    )
    manifest_paths = set(source_paths)
    if dockerfile_relative_path == DOCKERFILE_RELATIVE_PATH:
        builder_source = PurePosixPath(
            "app/strategy_lab_v2/nautilus_runtime_image/evidence_build.py"
        )
        builder_path = source_root / Path(*builder_source.parts)
        if (
            builder_path.is_symlink()
            or not builder_path.is_file()
            or not builder_path.resolve(strict=True).is_relative_to(source_root)
        ):
            raise ValueError("Nautilus image qualification source is missing or not a regular file")
        manifest_paths.add(builder_source)
    source_hashes: dict[str, str] = {}
    for relative in sorted(manifest_paths, key=lambda path: path.as_posix()):
        path = source_root / Path(*relative.parts)
        source_hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return content_digest(
        {
            "schema": SOURCE_MANIFEST_SCHEMA,
            "files": source_hashes,
            "build_inputs": {
                "python_base_image": PYTHON_BASE_IMAGE,
                "nautilus_package_version": NAUTILUS_PACKAGE_VERSION,
                "nautilus_wheel_url": NAUTILUS_WHEEL_URL,
                "nautilus_wheel_sha256": NAUTILUS_WHEEL_SHA256,
                "nautilus_wheel_filename": NAUTILUS_WHEEL_FILENAME,
                "nautilus_rust_version": NAUTILUS_RUST_VERSION,
            },
        }
    )


def copy_runtime_build_context(
    source_root: Path,
    context_root: Path,
    *,
    dockerfile_relative_path: str = DOCKERFILE_RELATIVE_PATH,
) -> tuple[Path, ...]:
    """Copy only reviewed runtime inputs into a fresh minimal build context."""

    source_paths = runtime_image_source_paths(
        source_root,
        dockerfile_relative_path=dockerfile_relative_path,
    )
    context_root.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for relative in source_paths:
        source = source_root / Path(*relative.parts)
        destination = context_root / Path(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.append(destination)
    return tuple(copied)


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def _run_checked(
    command: Sequence[str],
    *,
    runner: CommandRunner,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(command)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(
            f"local Nautilus image qualification command failed: {detail[-4000:]}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "non-zero exit status").strip()
        raise RuntimeError(f"local Nautilus image qualification command failed: {detail[-4000:]}")
    return result


def _decode_json_output(raw: str, *, field_name: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field_name} contains duplicate JSON keys")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{field_name} contains invalid JSON constant {value}")

    try:
        payload = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"{field_name} is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    return payload


def _hardened_probe_command(docker_binary: str, image_digest: str, module: str) -> tuple[str, ...]:
    return (
        docker_binary,
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev",
        "--tmpfs",
        "/root/.cache:rw,noexec,nosuid,nodev",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint",
        "python",
        image_digest,
        "-m",
        module,
        *(("--expected-version", NAUTILUS_PACKAGE_VERSION) if module == PROBE_MODULE else ()),
    )


def qualify_local_nautilus_rc_image(
    *,
    source_root: Path,
    artifact_directory: Path,
    image_tag: str | None = None,
    docker_binary: str = "docker",
    runner: CommandRunner = _run,
) -> NautilusRcImageQualification:
    """Build, probe, and publish one current-source RC6 runtime evidence artifact."""

    if not isinstance(artifact_directory, Path):
        raise TypeError("artifact_directory must be a Path")
    if not artifact_directory.is_dir():
        raise ValueError("artifact_directory must be an existing operator-owned directory")
    if image_tag is not None and (
        not isinstance(image_tag, str) or not image_tag.strip() or image_tag.startswith("-")
    ):
        raise ValueError("image_tag must be a non-empty Docker tag when provided")
    if not isinstance(docker_binary, str) or not docker_binary.strip():
        raise ValueError("docker_binary must not be empty")

    source_digest = runtime_image_source_digest(source_root)
    if image_tag is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        image_tag = (
            "strategy-lab-v2/nautilus-rc6:source-"
            f"{source_digest.removeprefix('sha256:')[:12]}-{timestamp}"
        )
    with tempfile.TemporaryDirectory(prefix="strategy-lab-v2-nautilus-build-") as temporary:
        temporary_root = Path(temporary)
        context_root = temporary_root / "context"
        copy_runtime_build_context(source_root, context_root)
        iidfile = temporary_root / "image.iid"
        dockerfile = context_root / DOCKERFILE_RELATIVE_PATH
        build_command = (
            docker_binary,
            "build",
            "--platform=linux/amd64",
            "--iidfile",
            str(iidfile),
            "--tag",
            image_tag,
            "--file",
            str(dockerfile),
            "--build-arg",
            f"PYTHON_BASE_IMAGE={PYTHON_BASE_IMAGE}",
            "--build-arg",
            f"NAUTILUS_WHEEL_URL={NAUTILUS_WHEEL_URL}",
            "--build-arg",
            f"NAUTILUS_WHEEL_SHA256={NAUTILUS_WHEEL_SHA256}",
            "--build-arg",
            f"NAUTILUS_WHEEL_FILENAME={NAUTILUS_WHEEL_FILENAME}",
            "--build-arg",
            f"NAUTILUS_SOURCE_DIGEST={source_digest}",
            str(context_root),
        )
        _run_checked(build_command, runner=runner)
        try:
            build_image_digest = iidfile.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError("Docker did not emit the built image ID") from exc
        require_sha256_digest(build_image_digest, field_name="build_image_digest")

    inspected = _run_checked(
        (docker_binary, "image", "inspect", "--format", "{{json .}}", build_image_digest),
        runner=runner,
    )
    image = _decode_json_output(inspected.stdout, field_name="Docker image inspection")
    config = image.get("Config")
    labels = config.get("Labels") if isinstance(config, Mapping) else None
    if not isinstance(labels, Mapping):
        raise ValueError("qualified Nautilus image has no build provenance labels")
    if labels.get(SOURCE_DIGEST_LABEL) != source_digest:
        raise ValueError(
            "qualified Nautilus image source digest label differs from current sources"
        )
    if labels.get(WHEEL_DIGEST_LABEL) != NAUTILUS_WHEEL_SHA256:
        raise ValueError("qualified Nautilus image wheel digest label differs from its pin")
    if labels.get(PACKAGE_VERSION_LABEL) != NAUTILUS_PACKAGE_VERSION:
        raise ValueError("qualified Nautilus image package label differs from its pin")
    runtime_image_digest = image.get("Id")
    if runtime_image_digest != build_image_digest:
        raise ValueError("Docker image ID differs from its build receipt")

    probe = _decode_json_output(
        _run_checked(
            _hardened_probe_command(docker_binary, runtime_image_digest, PROBE_MODULE),
            runner=runner,
        ).stdout,
        field_name="Nautilus runtime probe",
    )
    fixture = _decode_json_output(
        _run_checked(
            _hardened_probe_command(docker_binary, runtime_image_digest, FIXTURE_MODULE),
            runner=runner,
        ).stdout,
        field_name="Nautilus RC fixture",
    )
    if probe.get("python_version") != EXPECTED_PYTHON_VERSION:
        raise ValueError("Nautilus runtime probe reported an unexpected Python version")
    if probe.get("nautilus_package_version") != NAUTILUS_PACKAGE_VERSION:
        raise ValueError("Nautilus runtime probe reported an unexpected package version")

    tested_at = datetime.now(UTC)
    runtime = NautilusRcCompatibilityRuntime(
        source_digest=source_digest,
        runtime_image_digest=runtime_image_digest,
        python_version=EXPECTED_PYTHON_VERSION,
        rust_version=NAUTILUS_RUST_VERSION,
    )
    published = LocalNautilusRcConformanceEvidencePublisher(artifact_directory).publish(
        runtime=runtime,
        probe_payload=probe,
        fixture_payload=fixture,
        build_digest=runtime_image_digest,
        tested_at=tested_at,
    )
    return NautilusRcImageQualification(
        source_digest=source_digest,
        runtime_image_digest=runtime_image_digest,
        artifact_digest=published.artifact_digest,
        conformance_fingerprint=published.resolution.fingerprint,
        tested_at=tested_at,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--image-tag")
    parser.add_argument("--docker-binary", default="docker")
    args = parser.parse_args()
    result = qualify_local_nautilus_rc_image(
        source_root=args.backend_root,
        artifact_directory=args.artifact_directory,
        image_tag=args.image_tag,
        docker_binary=args.docker_binary,
    )
    print(
        json.dumps(
            {
                "artifact_digest": result.artifact_digest,
                "conformance_fingerprint": result.conformance_fingerprint,
                "runtime_image_digest": result.runtime_image_digest,
                "source_digest": result.source_digest,
                "tested_at": result.tested_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI integration
    raise SystemExit(main())


__all__ = [
    "NautilusRcImageQualification",
    "copy_runtime_build_context",
    "main",
    "qualify_local_nautilus_rc_image",
    "runtime_image_source_digest",
    "runtime_image_source_paths",
]
