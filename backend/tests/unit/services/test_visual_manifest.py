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

    incomplete = {**manifest, "surfaces": [{**manifest["surfaces"][0], "review": {"status": "approved"}}]}
    with pytest.raises(VisualManifestError, match="reviewer"):
        validate_visual_manifest(incomplete, require_approved=True)


def test_state_entries_must_cover_each_required_surface_state():
    manifest = load_visual_manifest(MANIFEST)
    for surface in manifest["surfaces"]:
        assert {entry["id"] for entry in surface["state_entries"]} == set(surface["required_states"])
    with pytest.raises(VisualManifestError, match="state_entries"):
        broken = load_visual_manifest(MANIFEST)
        broken["surfaces"][0]["state_entries"] = broken["surfaces"][0]["state_entries"][:-1]
        validate_visual_manifest(broken)


def test_manifest_records_composite_reference_board_contract():
    manifest = load_visual_manifest(MANIFEST)
    board = manifest["reference_policy"]["composite_reference_board"]
    assert board["builder"] == "tests/visual/build-tc2000-reference-board.py"
    assert board["media_count"] == 190
    assert board["surface_count"] == 22
    assert board["status"] == "implementation_aid"
    assert "not a synthetic screenshot baseline" in board["acceptance_role"]
