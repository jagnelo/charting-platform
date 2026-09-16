from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.lineage import (
    ArtifactLineageEntry,
    ArtifactLineageIndex,
    LineageDecision,
    LineageRole,
    append_lineage_entry,
    build_lineage_index,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
ARTIFACT = content_digest({"manifest": "one"})
PARENT = content_digest({"manifest": "parent"})


def _entry(
    artifact: str = ARTIFACT,
    *,
    role: LineageRole = LineageRole.OUTPUT_ARTIFACT,
    created_at: datetime = NOW,
    parent: str | None = None,
) -> ArtifactLineageEntry:
    return ArtifactLineageEntry(
        owner_type="run_result",
        owner_id="result-1",
        artifact_manifest_fingerprint=artifact,
        role=role,
        created_at=created_at,
        parent_manifest_fingerprint=parent,
    )


def test_lineage_append_is_idempotent_and_deterministically_ordered() -> None:
    index = ArtifactLineageIndex("run_result", "result-1")
    output = _entry()
    first = append_lineage_entry(index, output)
    assert first.decision is LineageDecision.APPEND
    assert first.index.entries == (output,)
    replay = append_lineage_entry(first.index, output)
    assert replay.decision is LineageDecision.REPLAY_EXISTING
    assert replay.index == first.index

    source = _entry(
        PARENT,
        role=LineageRole.DATA_SNAPSHOT,
        created_at=NOW + timedelta(seconds=1),
    )
    combined = append_lineage_entry(first.index, source)
    assert combined.decision is LineageDecision.APPEND
    assert [item.role for item in combined.index.entries] == [
        LineageRole.DATA_SNAPSHOT,
        LineageRole.OUTPUT_ARTIFACT,
    ]
    assert combined.index.fingerprint.startswith("sha256:")


def test_same_semantic_lineage_with_changed_recording_time_conflicts() -> None:
    index = ArtifactLineageIndex("run_result", "result-1", (_entry(),))
    changed = _entry(created_at=NOW + timedelta(seconds=3))
    resolution = append_lineage_entry(index, changed)
    assert resolution.decision is LineageDecision.CONFLICT
    assert resolution.index == index


def test_lineage_rejects_foreign_owner_duplicate_keys_and_self_parent() -> None:
    index = ArtifactLineageIndex("run_result", "result-1")
    with pytest.raises(ValueError, match="index owner"):
        append_lineage_entry(
            index,
            ArtifactLineageEntry(
                "other_owner",
                "result-1",
                ARTIFACT,
                LineageRole.OUTPUT_ARTIFACT,
                NOW,
            ),
        )
    with pytest.raises(ValueError, match="itself"):
        _entry(parent=ARTIFACT)
    with pytest.raises(ValueError, match="semantic keys"):
        ArtifactLineageIndex("run_result", "result-1", (_entry(), _entry()))


def test_lineage_contract_validates_digest_and_input_sequence() -> None:
    with pytest.raises(ValueError, match="artifact_manifest_fingerprint"):
        _entry("bad")
    with pytest.raises(TypeError, match="entries"):
        build_lineage_index("run_result", "result-1", "not-entries")  # type: ignore[arg-type]
