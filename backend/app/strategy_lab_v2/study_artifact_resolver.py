"""Fail-closed revalidation for explicitly pinned, owner-scoped Study artifacts.

The authenticated local API and worker compositions use this reader against the
existing Study ORM tables. Resolving a Study artifact authenticates immutable
stored input; it is not evidence of native Nautilus execution.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ResolvedStudyArtifactOutput,
    SelectedStudyArtifactReference,
)

_RUN_HASH = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_STUDY_ARTIFACT_TYPES = frozenset(
    {
        "scalar",
        "series",
        "boolean",
        "table",
        "bar",
        "histogram",
        "range",
        "scatter",
        "heatmap",
        "dashboard",
        "events",
    }
)


class SelectedStudyArtifactResolutionError(ValueError):
    """A selected immutable Study reference cannot be authenticated locally."""


SelectedStudyArtifactResolver = Callable[..., Awaitable[SelectedStudyArtifactReference]]
ResolvedStudyArtifactOutputResolver = Callable[..., Awaitable[ResolvedStudyArtifactOutput]]


def create_selected_study_artifact_resolver(
    session_factory: Callable[[], Any],
) -> SelectedStudyArtifactResolver:
    """Bind reference-only Study revalidation for existing API admission callers."""

    output_resolver = create_resolved_study_artifact_output_resolver(session_factory)

    async def resolve(
        *, principal: Any, reference: SelectedStudyArtifactReference
    ) -> SelectedStudyArtifactReference:
        return (await output_resolver(principal=principal, reference=reference)).reference

    return resolve


def create_resolved_study_artifact_output_resolver(
    session_factory: Callable[[], Any],
) -> ResolvedStudyArtifactOutputResolver:
    """Bind verified immutable payload resolution to the local SQL session factory."""

    if not callable(session_factory):
        raise TypeError("session_factory must be callable")

    async def resolve(
        *, principal: Any, reference: SelectedStudyArtifactReference
    ) -> ResolvedStudyArtifactOutput:
        if not isinstance(reference, SelectedStudyArtifactReference):
            raise SelectedStudyArtifactResolutionError("selected Study reference is not typed")
        async with session_factory() as session:
            return await _resolve_selected_study_artifact(
                session=session,
                principal=principal,
                reference=reference,
            )

    return resolve


def _code_version_digest(version: CodeVersion, asset: CodeAsset) -> str:
    """Digest the executable version and its owner-scoped stable asset identity."""

    return content_digest(
        {
            "code_asset": {
                "id": asset.id,
                "user_id": asset.user_id,
                "stable_key": asset.stable_key,
                "name": asset.name,
                "kind": asset.kind,
            },
            "code_version": {
                "id": version.id,
                "code_asset_id": version.code_asset_id,
                "version_number": version.version_number,
                "source": version.source,
                "output_contract": version.output_contract,
                "output_name": version.output_name,
                "parameter_schema": version.parameter_schema,
                "default_parameters": version.default_parameters,
                "sdk_version": version.sdk_version,
                "runtime_version": version.runtime_version,
                "dependencies": version.dependencies,
                "lookback": version.lookback,
                "diagnostics": version.diagnostics,
            },
        }
    )


async def _load_exactly_one(
    session: AsyncSession,
    statement: Select[Any],
    *,
    description: str,
) -> Any:
    result = await session.execute(statement)
    rows = result.scalars().all()
    if len(rows) != 1:
        raise SelectedStudyArtifactResolutionError(
            f"selected Study {description} is missing, foreign, or ambiguous"
        )
    return rows[0]


async def _resolve_selected_study_artifact(
    *,
    session: AsyncSession,
    principal: Any,
    reference: SelectedStudyArtifactReference,
) -> ResolvedStudyArtifactOutput:
    """Revalidate a pinned artifact from the existing immutable Study tables.

    This seam accepts only a typed reference; it does not derive or guess an
    artifact from a latest-run alias. The reference remains a claim until this
    authenticated query revalidates every producer-owned immutable field.
    """

    if not isinstance(reference, SelectedStudyArtifactReference):
        raise SelectedStudyArtifactResolutionError("selected Study reference is not typed")
    raw_owner_id = getattr(principal, "id", principal)
    if isinstance(raw_owner_id, int) and not isinstance(raw_owner_id, bool):
        owner_id = raw_owner_id
    elif isinstance(raw_owner_id, str) and re.fullmatch(r"[1-9][0-9]*", raw_owner_id):
        owner_id = int(raw_owner_id)
    else:
        owner_id = 0
    if owner_id <= 0:
        raise SelectedStudyArtifactResolutionError("authenticated Study owner is unavailable")

    run = await _load_exactly_one(
        session,
        select(ResearchRun).where(
            ResearchRun.id == reference.research_run_id,
            ResearchRun.user_id == owner_id,
        ),
        description="run",
    )
    if run.id != reference.research_run_id or run.user_id != owner_id:
        raise SelectedStudyArtifactResolutionError(
            "selected Study run is unavailable to the authenticated owner"
        )
    if run.code_version_id != reference.code_version_id:
        raise SelectedStudyArtifactResolutionError(
            "selected Study run references a different code version"
        )
    if run.status != "completed" or run.evaluation_status != "completed":
        raise SelectedStudyArtifactResolutionError("selected Study run is not fully completed")
    if not isinstance(run.reproducibility_hash, str) or not _RUN_HASH.fullmatch(
        run.reproducibility_hash
    ):
        raise SelectedStudyArtifactResolutionError(
            "selected Study run has no valid reproducibility hash"
        )
    if not isinstance(run.run_config, Mapping) or not isinstance(run.dataset_manifest, Mapping):
        raise SelectedStudyArtifactResolutionError(
            "selected Study run configuration or dataset manifest is invalid"
        )

    version = await _load_exactly_one(
        session,
        select(CodeVersion).where(CodeVersion.id == reference.code_version_id),
        description="code version",
    )
    if version.id != reference.code_version_id or version.code_asset_id is None:
        raise SelectedStudyArtifactResolutionError("selected Study code asset is missing")
    asset = await _load_exactly_one(
        session,
        select(CodeAsset).where(
            CodeAsset.id == version.code_asset_id,
            CodeAsset.user_id == owner_id,
        ),
        description="code asset",
    )
    if asset.id != version.code_asset_id or asset.user_id != owner_id:
        raise SelectedStudyArtifactResolutionError(
            "selected Study code asset is unavailable to the authenticated owner"
        )
    effective_contract = run.run_config.get("output_contract", version.output_contract)
    if (
        asset.kind != "study"
        or version.output_contract != "study"
        or effective_contract != "study"
        or reference.output_contract != "study"
    ):
        raise SelectedStudyArtifactResolutionError(
            "selected Study code version does not declare the Study output contract"
        )

    artifacts_result = await session.execute(
        select(ResearchArtifact).where(
            ResearchArtifact.research_run_id == run.id,
            ResearchArtifact.name == reference.artifact_name,
        )
    )
    artifacts = artifacts_result.scalars().all()
    if len(artifacts) != 1:
        raise SelectedStudyArtifactResolutionError(
            "selected Study artifact name is missing or ambiguous"
        )
    artifact = artifacts[0]
    if (
        artifact.id != reference.artifact_id
        or artifact.research_run_id != run.id
        or artifact.name != reference.artifact_name
    ):
        raise SelectedStudyArtifactResolutionError(
            "selected Study artifact identity differs from its immutable reference"
        )
    if (
        not isinstance(artifact.name, str)
        or artifact.name != reference.artifact_name
        or not isinstance(artifact.artifact_type, str)
        or artifact.artifact_type not in _SUPPORTED_STUDY_ARTIFACT_TYPES
        or artifact.artifact_type != reference.artifact_type
        or not isinstance(artifact.payload, Mapping)
        or artifact.payload.get("type") != artifact.artifact_type
        or "value" not in artifact.payload
    ):
        raise SelectedStudyArtifactResolutionError(
            "selected Study artifact has an unsupported or inconsistent type/payload"
        )

    try:
        resolved = SelectedStudyArtifactReference(
            research_run_id=run.id,
            code_version_id=version.id,
            artifact_id=artifact.id,
            artifact_name=artifact.name,
            artifact_type=artifact.artifact_type,
            output_contract=version.output_contract,
            run_reproducibility_hash=run.reproducibility_hash,
            code_version_digest=_code_version_digest(version, asset),
            dataset_manifest_digest=content_digest(run.dataset_manifest),
            artifact_content_digest=content_digest(artifact.payload),
        )
    except (TypeError, ValueError) as error:
        raise SelectedStudyArtifactResolutionError(
            "selected Study immutable evidence is malformed"
        ) from error
    if resolved != reference:
        raise SelectedStudyArtifactResolutionError(
            "selected Study evidence differs from its immutable reference"
        )
    try:
        return ResolvedStudyArtifactOutput(reference=resolved, payload=artifact.payload)
    except (TypeError, ValueError) as error:
        raise SelectedStudyArtifactResolutionError(
            "selected Study artifact payload cannot be frozen for runtime use"
        ) from error
