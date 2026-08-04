"""File protocol between API persistence and the isolated research runner."""

import json
from pathlib import Path

from app.config import settings
from app.models.research import ResearchArtifact, ResearchRun


def _prepare_shared_directory(path: Path, *, create: bool = True) -> None:
    """Make the backend/runner handoff directory writable by both containers.

    Named volumes are initialized by Docker as ``root:root`` with mode 0755. The
    runner intentionally executes as UID 10001, so a backend-created job would
    otherwise be readable but impossible for the runner to atomically claim or
    complete. These volumes are private to the backend and isolated runner; the
    shared mode is an explicit part of their file protocol.
    """
    if not path.exists():
        if not create:
            return
        path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o777)


def enqueue_research_run(run: ResearchRun) -> None:
    job_directory = Path(settings.RESEARCH_JOB_DIR)
    result_directory = Path(settings.RESEARCH_RESULT_DIR)
    _prepare_shared_directory(job_directory)
    # The runner image/Compose volume owns this directory. In local API tests the
    # result directory is intentionally created by the result fixture instead.
    _prepare_shared_directory(result_directory, create=False)
    payload = {
        "run_id": run.id,
        "source": run.code_version.source,
        "dataset": run.dataset_manifest,
        "parameters": run.run_config.get("parameters", {}),
        "output_contract": run.code_version.output_contract,
    }
    destination = Path(settings.RESEARCH_JOB_DIR) / f"{run.id}.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")))
    temporary.chmod(0o666)
    temporary.replace(destination)


def collect_research_result(run: ResearchRun) -> bool:
    path = Path(settings.RESEARCH_RESULT_DIR) / f"{run.id}.json"
    if not path.exists():
        return False
    result = json.loads(path.read_text())
    run.status = result["status"]
    run.diagnostics = result.get("diagnostics", [])
    run.resource_usage = result.get("resource_usage", {})
    run.reproducibility_hash = result.get("reproducibility_hash")
    for name, artifact in result.get("artifacts", {}).items():
        run.artifacts.append(ResearchArtifact(
            artifact_type=str(artifact.get("type", "unknown")),
            name=name,
            payload=artifact,
        ))
    path.rename(path.with_suffix(".collected"))
    return True


def read_research_progress(run_id: int) -> dict:
    """Return a runner-owned durable progress snapshot without executing code."""
    path = Path(settings.RESEARCH_RESULT_DIR) / f"{run_id}.progress.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def cancel_research_run(run: ResearchRun) -> None:
    path = Path(settings.RESEARCH_JOB_DIR) / f"{run.id}.json"
    if path.exists():
        path.rename(path.with_suffix(".canceled"))
    else:
        # A runner claims jobs by atomically renaming them to .running. The sentinel
        # is visible across the constrained shared job volume and checked between
        # batch cells; it never asks FastAPI to execute user code.
        (Path(settings.RESEARCH_JOB_DIR) / f"{run.id}.cancel").touch()
    run.status = "canceled"
