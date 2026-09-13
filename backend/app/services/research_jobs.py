"""File protocol between API persistence and the isolated research runner."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.models.research import ResearchArtifact, ResearchRun
from app.services.breadth import detect_breadth_occurrences


def _manifest_evaluation_status(manifest: object, *, transport_status: str) -> str:
    """Classify local evaluator readiness without conflating transport completion."""

    if transport_status in {"queued", "running", "failed", "canceled"}:
        return transport_status
    if transport_status != "completed":
        return "unknown"
    if not isinstance(manifest, dict):
        return "completed"

    exclusions = manifest.get("exclusions")
    datasets = manifest.get("datasets")
    exclusion_count = len(exclusions) if isinstance(exclusions, list) else 0
    dataset_count = len(datasets) if isinstance(datasets, list) else None
    if exclusion_count and dataset_count:
        return "partial"
    if exclusion_count:
        return "deferred"
    return "completed"


def persist_evaluation_status(
    run: ResearchRun,
    *,
    status: str | None = None,
    details: dict | None = None,
) -> str:
    """Persist evaluator readiness under a distinct durable resource key.

    ``ResearchRun.status`` remains the isolated runner/transport state.  The
    nested ``resource_usage.evaluation`` record is deliberately additive so it
    survives existing result-file reconciliation without requiring another
    Alembic head in the repository's already-divergent migration graph.
    """

    transport_status = str(getattr(run, "status", "unknown"))
    evaluation_status = status or _manifest_evaluation_status(
        getattr(run, "dataset_manifest", {}), transport_status=transport_status
    )
    usage = getattr(run, "resource_usage", None)
    usage = dict(usage) if isinstance(usage, dict) else {}
    evaluation = usage.get("evaluation")
    evaluation = dict(evaluation) if isinstance(evaluation, dict) else {}
    evaluation.update(
        {
            "status": evaluation_status,
            "transport_status": transport_status,
            "observed_at": datetime.now(UTC).isoformat(),
        }
    )
    if details:
        evaluation["details"] = details
    usage["evaluation"] = evaluation
    run.resource_usage = usage
    return evaluation_status


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
    # Persist a distinct evaluator state before writing the runner job file.
    persist_evaluation_status(run, status="queued")
    job_directory = Path(settings.RESEARCH_JOB_DIR)
    result_directory = Path(settings.RESEARCH_RESULT_DIR)
    _prepare_shared_directory(job_directory)
    # The runner image/Compose volume owns this directory. In local API tests the
    # result directory is intentionally created by the result fixture instead.
    _prepare_shared_directory(result_directory, create=False)
    output_adapter = run.run_config.get("output_adapter")
    if not isinstance(output_adapter, str):
        diagnostics = (
            getattr(run.code_version, "diagnostics", []) if run.code_version is not None else []
        )
        if isinstance(diagnostics, list):
            output_adapter = next(
                (
                    item.get("output_adapter")
                    for item in diagnostics
                    if isinstance(item, dict) and isinstance(item.get("output_adapter"), str)
                ),
                None,
            )
    payload = {
        "run_id": run.id,
        "source": run.code_version.source,
        "dataset": run.dataset_manifest,
        "parameters": run.run_config.get("parameters", {}),
        "output_contract": run.run_config.get("output_contract", run.code_version.output_contract),
        "output_name": run.run_config.get("output_name", run.code_version.output_name),
        "execution_mode": run.run_config.get("execution_mode"),
        "history_limit": run.run_config.get("history_limit"),
        "series_target": run.run_config.get("series_target"),
        "condition_tree": run.run_config.get("condition_tree"),
        "output_adapter": output_adapter,
    }
    destination = Path(settings.RESEARCH_JOB_DIR) / f"{run.id}.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")))
    temporary.chmod(0o666)
    temporary.replace(destination)


def _breadth_history_occurrences(points: list[object]) -> list[dict]:
    """Project runner cell rows through the canonical breadth occurrence schema."""
    normalized: list[dict] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        members = point.get("members")
        if not isinstance(members, list):
            members = point.get("cells", [])
        members = members if isinstance(members, list) else []
        eligible = sum(
            isinstance(member, dict) and isinstance(member.get("value"), bool) for member in members
        )
        passed = sum(isinstance(member, dict) and member.get("value") is True for member in members)
        timestamp = point.get("timestamp")
        parsed_timestamp = timestamp
        if isinstance(timestamp, str):
            try:
                parsed_timestamp = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                parsed_timestamp = timestamp
        normalized.append(
            {
                **point,
                "timestamp": parsed_timestamp,
                "members": members,
                "eligible_count": eligible,
                "pass_count": passed,
                "percentage": passed / eligible if eligible else None,
            }
        )
    occurrences = detect_breadth_occurrences(normalized)
    for occurrence in occurrences:
        timestamp = occurrence.get("timestamp")
        if isinstance(timestamp, datetime):
            occurrence["timestamp"] = timestamp.isoformat().replace("+00:00", "Z")
    return occurrences


def collect_research_result(run: ResearchRun) -> bool:
    path = Path(settings.RESEARCH_RESULT_DIR) / f"{run.id}.json"
    if not path.exists():
        return False
    result = json.loads(path.read_text())
    run.status = result["status"]
    run.diagnostics = result.get("diagnostics", [])
    incoming_usage = result.get("resource_usage", {})
    existing_usage = (
        getattr(run, "resource_usage", {})
        if isinstance(getattr(run, "resource_usage", {}), dict)
        else {}
    )
    run.resource_usage = dict(incoming_usage) if isinstance(incoming_usage, dict) else {}
    if isinstance(existing_usage.get("evaluation"), dict):
        run.resource_usage["evaluation"] = existing_usage["evaluation"]
    run.reproducibility_hash = result.get("reproducibility_hash")
    for name, artifact in result.get("artifacts", {}).items():
        persisted_artifact = artifact
        if isinstance(artifact, dict) and artifact.get("type") == "breadth_history":
            value = artifact.get("value")
            if isinstance(value, dict) and isinstance(value.get("points"), list):
                # Occurrences are a projection of persisted runner output. This
                # boundary enriches the artifact for generic Research Results
                # consumers; it never evaluates source or calls a provider.
                persisted_artifact = {
                    **artifact,
                    "value": {
                        **value,
                        "occurrences": _breadth_history_occurrences(value["points"]),
                    },
                }
        run.artifacts.append(
            ResearchArtifact(
                artifact_type=str(persisted_artifact.get("type", "unknown")),
                name=name,
                payload=persisted_artifact,
            )
        )
    path.rename(path.with_suffix(".collected"))
    persist_evaluation_status(run)
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
    persist_evaluation_status(run, status="canceled")
