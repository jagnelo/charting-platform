from pathlib import Path

import pytest

from app.services.visual_manifest import (
    VisualManifestError,
    load_visual_manifest,
    validate_visual_manifest,
)

MANIFEST = Path(__file__).parents[4] / "tests/visual/references/tc2000-v25/manifest.yaml"


def test_current_manifest_is_well_formed_but_cannot_pass_visual_acceptance():
    manifest = load_visual_manifest(MANIFEST)
    validate_visual_manifest(manifest)
    with pytest.raises(VisualManifestError, match="visual acceptance is blocked"):
        validate_visual_manifest(manifest, require_approved=True)


def test_approved_reference_requires_full_capture_evidence():
    manifest = {
        "product": {"generation": "25", "build": "25.0.9571"},
        "reference_policy": {"acceptance_requires": "approved"},
        "environments": [
            {"id": key, "viewport": {"width": width, "height": height}, "display_scale": scale}
            for key, (width, height, scale) in {
                "desktop-1080p-100": (1920, 1080, 100),
                "desktop-1080p-125": (1920, 1080, 125),
                "desktop-1440p-100": (2560, 1440, 100),
                "desktop-1440p-125": (2560, 1440, 125),
            }.items()
        ],
        "surfaces": [
            {
                "id": "shell",
                "state": "approved",
                "required_states": ["default"],
                "reproduction": "Open shell.",
                "tc2000": {
                    "generation": "25",
                    "build": "25.0.9571",
                    "capture_date": "2026-08-03",
                    "operator": "qa",
                },
                "source": {
                    "type": "authorised_live_capture",
                    "locator": "controlled://shell",
                    "sha256": "a" * 64,
                    "permission": "controlled_reference_only",
                },
                "environment": {
                    "resolution": "1920x1080",
                    "display_scale": 100,
                    "theme": "dark",
                    "locale": "en-US",
                    "timezone": "UTC",
                    "device_pixel_ratio": 1,
                },
                "measurements": {"tokens": {"menu_height": 20}},
                "review": {"status": "approved", "reviewer": "qa"},
            }
        ],
    }
    validate_visual_manifest(manifest, require_approved=True)

    incomplete = {
        **manifest,
        "surfaces": [{**manifest["surfaces"][0], "review": {"status": "approved"}}],
    }
    with pytest.raises(VisualManifestError, match="reviewer"):
        validate_visual_manifest(incomplete, require_approved=True)


def test_state_entries_must_cover_each_required_surface_state():
    manifest = load_visual_manifest(MANIFEST)
    for surface in manifest["surfaces"]:
        assert {entry["id"] for entry in surface["state_entries"]} == set(
            surface["required_states"]
        )
    with pytest.raises(VisualManifestError, match="state_entries"):
        broken = load_visual_manifest(MANIFEST)
        broken["surfaces"][0]["state_entries"] = broken["surfaces"][0]["state_entries"][:-1]
        validate_visual_manifest(broken)


def test_manifest_records_composite_reference_board_contract():
    manifest = load_visual_manifest(MANIFEST)
    board = manifest["reference_policy"]["composite_reference_board"]
    assert board["builder"] == "tests/visual/build-tc2000-reference-board.py"
    assert board["media_count"] == 230
    assert board["surface_count"] == 26
    assert board["status"] == "accepted_working_authority"
    assert "visual and interaction authority" in board["acceptance_role"]


def test_manifest_gap_ids_are_documented_and_attached_to_required_surfaces():
    manifest = load_visual_manifest(MANIFEST)
    board_doc = (MANIFEST.parents[4] / "docs/tc2000-reference-board.md").read_text()
    expected_gap_ids = {
        "REF-SHELL-V25",
        "REF-STATE-VARIANTS",
        "REF-LINKING-V25",
        "REF-STUDY-LAB-V25",
        "REF-ENV-TOKENS",
        "REF-PERMISSION-REVIEW",
    }
    assert manifest["reference_policy"]["gap_register"] == "docs/tc2000-reference-board.md"
    for gap_id in expected_gap_ids:
        assert gap_id in board_doc
    referenced_gap_ids = {
        gap_id for surface in manifest["surfaces"] for gap_id in surface.get("gap_ids", [])
    }
    assert referenced_gap_ids == expected_gap_ids
    for surface in manifest["surfaces"]:
        if surface["state"] == "required_missing":
            assert surface.get("gap_ids")


def test_manifest_partitions_board_covered_states_and_remaining_gaps():
    manifest = load_visual_manifest(MANIFEST)
    for surface in manifest["surfaces"]:
        required = set(surface["required_states"])
        covered = set(surface["board_covered_states"])
        gaps = set(surface["board_gap_states"])
        assert covered.isdisjoint(gaps)
        assert covered | gaps == required
        entries = {entry["id"]: entry for entry in surface["state_entries"]}
        assert {
            key for key, entry in entries.items() if entry["state"] == "board_covered"
        } == covered
        assert {
            key for key, entry in entries.items() if entry["state"] == "required_missing"
        } == gaps


def test_visual_gap_entries_record_interim_oracles_and_known_local_baselines():
    manifest = load_visual_manifest(MANIFEST)
    entries = {
        (surface["id"], entry["id"]): entry
        for surface in manifest["surfaces"]
        for entry in surface["state_entries"]
    }
    assert (
        entries[("chart-window", "loading")]["interim_oracle"]
        == "F8i-b functional loading assertion"
    )
    assert len(entries[("chart-window", "loading")]["local_baselines"]) == 4
    assert (
        entries[("workspace-docking", "blocked_popout")]["interim_oracle"]
        == "F8k-a behavioral recovery assertion"
    )
    assert len(entries[("workspace-docking", "blocked_popout")]["local_baselines"]) == 4
    assert (
        entries[("chart-window", "error")]["interim_oracle"]
        == "F8i-a functional provider-error assertion plus deterministic four-environment visual baseline"
    )
    assert len(entries[("chart-window", "error")]["local_baselines"]) == 4
    assert (
        entries[("watchlist-column-filter", "partial_coverage")]["interim_oracle"]
        == "F8i-d functional partial-coverage assertion"
    )


def test_required_missing_state_without_interim_oracle_is_rejected():
    broken = load_visual_manifest(MANIFEST)
    broken["surfaces"][-1]["state_entries"][0].pop("interim_oracle")
    with pytest.raises(VisualManifestError, match="need an interim oracle"):
        validate_visual_manifest(broken)


def test_required_missing_state_without_four_environment_baselines_is_rejected():
    broken = load_visual_manifest(MANIFEST)
    broken["surfaces"][-1]["state_entries"][0]["local_baselines"] = ["only-one-baseline"]
    with pytest.raises(
        VisualManifestError, match="one deterministic local baseline per required environment"
    ):
        validate_visual_manifest(broken)


def test_required_missing_state_with_duplicate_baselines_is_rejected():
    broken = load_visual_manifest(MANIFEST)
    broken["surfaces"][-1]["state_entries"][0]["local_baselines"] = [
        "same-baseline",
        "same-baseline",
        "third-baseline",
        "fourth-baseline",
    ]
    with pytest.raises(
        VisualManifestError, match="one deterministic local baseline per required environment"
    ):
        validate_visual_manifest(broken)
