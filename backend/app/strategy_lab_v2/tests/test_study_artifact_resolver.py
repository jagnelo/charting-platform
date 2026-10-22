"""I/O-free contract tests for the private selected-Study resolver."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.visitors import iterate

import app.strategy_lab_v2.study_artifact_resolver as study_resolver_module
from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ResolvedStudyArtifactOutput,
    SelectedStudyArtifactReference,
)
from app.strategy_lab_v2.study_artifact_resolver import (
    SelectedStudyArtifactResolutionError,
    _resolve_selected_study_artifact,
    create_selected_study_artifact_resolver,
)

_OWNER_ID = 73
_RUN_ID = 4101
_VERSION_ID = 5202
_ARTIFACT_ID = 6303
_RUN_HASH = "a" * 64


def _as_test_async_session(session: FakeAsyncSession) -> AsyncSession:
    """Adapt the deterministic fake at the production AsyncSession seam only."""

    return cast(AsyncSession, session)


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return self._rows


class FakeAsyncSession:
    """Return fixture rows while asserting the real query stays owner scoped."""

    def __init__(self, responses: list[list[Any]]) -> None:
        self._responses = list(responses)
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        model = statement.column_descriptions[0]["entity"]
        where_columns = {
            (getattr(getattr(node, "table", None), "name", None), getattr(node, "name", None))
            for node in iterate(statement.whereclause)
            if getattr(node, "table", None) is not None
        }
        params = statement.compile().params.values()
        if model is ResearchRun:
            assert ("research_run", "id") in where_columns
            assert ("research_run", "user_id") in where_columns
            assert _RUN_ID in params
            assert _OWNER_ID in params
        elif model is CodeVersion:
            assert ("code_version", "id") in where_columns
            assert _VERSION_ID in params
        elif model is CodeAsset:
            assert ("code_asset", "id") in where_columns
            assert ("code_asset", "user_id") in where_columns
            assert 901 in params
            assert _OWNER_ID in params
        elif model is ResearchArtifact:
            assert ("research_artifact", "research_run_id") in where_columns
            assert ("research_artifact", "name") in where_columns
            assert _RUN_ID in params
            assert "close-series" in params
        else:
            raise AssertionError(f"unexpected model query: {model!r}")
        return FakeResult(self._responses.pop(0))


def _graph() -> (
    tuple[
        SelectedStudyArtifactReference,
        list[list[Any]],
        object,
    ]
):
    asset = CodeAsset(
        id=901,
        user_id=_OWNER_ID,
        stable_key="owned-study",
        name="Owned study",
        kind="study",
        is_archived=False,
    )
    version = CodeVersion(
        id=_VERSION_ID,
        code_asset_id=asset.id,
        version_number=4,
        source="def study(context): return context.output.series('close', [1.0])",
        output_contract="study",
        output_name=None,
        parameter_schema={"window": {"type": "integer"}},
        default_parameters={"window": 5},
        sdk_version="1",
        runtime_version="1",
        dependencies=[],
        lookback=5,
        diagnostics=[],
    )
    run = ResearchRun(
        id=_RUN_ID,
        user_id=_OWNER_ID,
        code_version_id=version.id,
        status="completed",
        run_config={"output_contract": "study", "parameters": {"window": 5}},
        dataset_manifest={"dataset": "local-bars", "version": 3},
        reproducibility_hash=_RUN_HASH,
        resource_usage={"evaluation": {"status": "completed"}},
    )
    assert run.reproducibility_hash is not None
    artifact = ResearchArtifact(
        id=_ARTIFACT_ID,
        research_run_id=run.id,
        artifact_type="series",
        name="close-series",
        payload={"type": "series", "value": [1.0, 2.0]},
    )
    code_digest = content_digest(
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
    reference = SelectedStudyArtifactReference(
        research_run_id=run.id,
        code_version_id=version.id,
        artifact_id=artifact.id,
        artifact_name=artifact.name,
        artifact_type=artifact.artifact_type,
        output_contract=version.output_contract,
        run_reproducibility_hash=run.reproducibility_hash,
        code_version_digest=code_digest,
        dataset_manifest_digest=content_digest(run.dataset_manifest),
        artifact_content_digest=content_digest(artifact.payload),
    )
    # Strategy v2's authenticated principal exposes a canonical decimal string;
    # the shared research tables use the corresponding integer User primary key.
    principal = type("Principal", (), {"id": str(_OWNER_ID)})()
    responses: list[list[Any]] = [[run], [version], [asset], [artifact]]
    return reference, responses, principal


@pytest.mark.asyncio
async def test_resolves_exact_owner_scoped_completed_named_study_artifact() -> None:
    reference, responses, principal = _graph()
    session = FakeAsyncSession(responses)

    resolved = await _resolve_selected_study_artifact(
        session=_as_test_async_session(session), principal=principal, reference=reference
    )

    assert isinstance(resolved, ResolvedStudyArtifactOutput)
    assert resolved.reference == reference
    assert resolved.value == (1.0, 2.0)
    assert len(session.statements) == 4
    assert session._responses == []


def test_resolved_study_output_freezes_nested_payload_against_source_mutation() -> None:
    reference, _responses, _principal = _graph()
    payload = {"type": "series", "value": [{"close": 1.0}]}
    pinned_reference = replace(
        reference,
        artifact_content_digest=content_digest(payload),
    )

    resolved = ResolvedStudyArtifactOutput(pinned_reference, payload)
    cast(Any, payload)["value"][0]["close"] = 99.0

    assert resolved.value[0]["close"] == 1.0
    with pytest.raises(TypeError):
        cast(Any, resolved.value[0])["close"] = 2.0
    with pytest.raises(TypeError):
        cast(Any, resolved.payload)["type"] = "table"


def test_resolved_study_output_rejects_payload_that_does_not_match_pinned_digest() -> None:
    reference, _responses, _principal = _graph()
    changed_payload = {"type": "series", "value": [9.0, 2.0]}

    with pytest.raises(ValueError, match="immutable reference"):
        ResolvedStudyArtifactOutput(reference, changed_payload)


@pytest.mark.asyncio
async def test_host_resolver_owns_one_read_session_and_returns_exact_pin(monkeypatch) -> None:
    reference, responses, principal = _graph()
    session = FakeAsyncSession(responses)
    lifecycle: list[str] = []

    class SessionContext:
        async def __aenter__(self) -> AsyncSession:
            lifecycle.append("enter")
            return _as_test_async_session(session)

        async def __aexit__(self, *_args: Any) -> None:
            lifecycle.append("exit")

    resolver = create_selected_study_artifact_resolver(SessionContext)

    def reject_payload_materialization(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("reference-only API resolver must not freeze a runtime payload")

    monkeypatch.setattr(
        study_resolver_module,
        "ResolvedStudyArtifactOutput",
        reject_payload_materialization,
    )
    resolved = await resolver(principal=principal, reference=reference)

    assert resolved is reference or resolved == reference
    assert lifecycle == ["enter", "exit"]
    assert len(session.statements) == 4


@pytest.mark.parametrize(
    "case",
    (
        "foreign_run",
        "foreign_asset_row",
        "nonterminal_run",
        "incomplete_evaluation",
        "wrong_version_link",
        "missing_version",
        "missing_asset",
        "wrong_asset_id",
        "wrong_asset_kind",
        "wrong_version_contract",
        "wrong_run_contract",
        "missing_run_hash",
        "malformed_run_hash",
        "missing_artifact",
        "deleted_artifact",
        "ambiguous_name",
        "wrong_artifact_id",
        "wrong_artifact_name",
        "unsupported_artifact_type",
        "payload_type_mismatch",
        "run_hash_drift",
        "version_digest_drift",
        "dataset_digest_drift",
        "artifact_digest_drift",
        "noncanonical_artifact_digest",
    ),
)
@pytest.mark.asyncio
async def test_rejects_missing_ambiguous_foreign_or_drifted_study_evidence(case: str) -> None:
    reference, responses, principal = _graph()
    run, version, asset, artifact = (rows[0] for rows in responses)
    if case == "foreign_run":
        run.user_id += 1
    elif case == "foreign_asset_row":
        asset.user_id += 1
    elif case == "nonterminal_run":
        run.status = "running"
    elif case == "incomplete_evaluation":
        run.resource_usage = {"evaluation": {"status": "partial"}}
    elif case == "wrong_version_link":
        run.code_version_id += 1
    elif case == "missing_version":
        responses[1] = []
    elif case == "missing_asset":
        responses[2] = []
    elif case == "wrong_asset_id":
        asset.id += 1
    elif case == "wrong_asset_kind":
        asset.kind = "signal"
    elif case == "wrong_version_contract":
        version.output_contract = "series"
    elif case == "wrong_run_contract":
        run.run_config["output_contract"] = "series"
    elif case == "missing_run_hash":
        run.reproducibility_hash = None
    elif case == "malformed_run_hash":
        run.reproducibility_hash = "unknown"
    elif case in {"missing_artifact", "deleted_artifact"}:
        responses[3] = []
    elif case == "ambiguous_name":
        duplicate = ResearchArtifact(
            id=_ARTIFACT_ID + 1,
            research_run_id=_RUN_ID,
            artifact_type="series",
            name=artifact.name,
            payload=artifact.payload,
        )
        responses[3] = [artifact, duplicate]
    elif case == "wrong_artifact_id":
        responses[3] = [
            ResearchArtifact(
                id=_ARTIFACT_ID + 1,
                research_run_id=_RUN_ID,
                artifact_type=artifact.artifact_type,
                name=artifact.name,
                payload=artifact.payload,
            )
        ]
    elif case == "wrong_artifact_name":
        artifact.name = "different-output"
    elif case == "unsupported_artifact_type":
        artifact.artifact_type = "unknown"
        artifact.payload = {"type": "unknown", "value": []}
    elif case == "payload_type_mismatch":
        artifact.payload = {"type": "scalar", "value": [1.0, 2.0]}
    elif case == "run_hash_drift":
        run.reproducibility_hash = "b" * 64
    elif case == "version_digest_drift":
        version.source += "\n# changed after selection"
    elif case == "dataset_digest_drift":
        run.dataset_manifest["version"] += 1
    elif case == "artifact_digest_drift":
        artifact.payload["value"].append(3.0)
    elif case == "noncanonical_artifact_digest":
        artifact.payload["value"] = [float("nan")]

    with pytest.raises(SelectedStudyArtifactResolutionError):
        await _resolve_selected_study_artifact(
            session=_as_test_async_session(FakeAsyncSession(responses)),
            principal=principal,
            reference=reference,
        )


@pytest.mark.asyncio
async def test_rejects_untyped_reference_and_invalid_principal_without_queries() -> None:
    reference, responses, principal = _graph()
    session = FakeAsyncSession(responses)
    untyped_reference: Any = {"artifact_id": _ARTIFACT_ID}

    with pytest.raises(SelectedStudyArtifactResolutionError):
        await _resolve_selected_study_artifact(
            session=_as_test_async_session(session),
            principal=principal,
            reference=untyped_reference,
        )
    with pytest.raises(SelectedStudyArtifactResolutionError):
        await _resolve_selected_study_artifact(
            session=_as_test_async_session(session),
            principal=type("Principal", (), {"id": True})(),
            reference=reference,
        )
    with pytest.raises(SelectedStudyArtifactResolutionError):
        await _resolve_selected_study_artifact(
            session=_as_test_async_session(session),
            principal=type("Principal", (), {"id": "owner-73"})(),
            reference=reference,
        )
    assert session.statements == []
