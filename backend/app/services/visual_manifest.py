"""Validation for protected TC2000 Version 25 visual-reference manifests.

This module intentionally validates metadata only. It never reads protected source
captures or treats an absent/older reference as a visual baseline.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

ALLOWED_STATES = {
    "required_missing",
    "captured_unmeasured",
    "measured_unapproved",
    "approved",
    "superseded",
    "out_of_scope",
}
REQUIRED_ENVIRONMENTS = {
    "desktop-1080p-100": (1920, 1080, 100),
    "desktop-1080p-125": (1920, 1080, 125),
    "desktop-1440p-100": (2560, 1440, 100),
    "desktop-1440p-125": (2560, 1440, 125),
}


class VisualManifestError(ValueError):
    """The visual-reference pack is malformed or insufficient for a requested gate."""


def load_visual_manifest(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise VisualManifestError("manifest root must be a mapping")
    return data


def validate_visual_manifest(manifest: dict[str, Any], *, require_approved: bool = False) -> None:
    product = manifest.get("product")
    if (
        not isinstance(product, dict)
        or product.get("generation") != "25"
        or not product.get("build")
    ):
        raise VisualManifestError("product generation 25 and exact build are required")
    if manifest.get("reference_policy", {}).get("acceptance_requires") != "approved":
        raise VisualManifestError("visual acceptance must require approved references")

    environments = {
        item.get("id"): item for item in manifest.get("environments", []) if isinstance(item, dict)
    }
    for environment_id, (width, height, scale) in REQUIRED_ENVIRONMENTS.items():
        environment = environments.get(environment_id, {})
        viewport = environment.get("viewport", {})
        if (viewport.get("width"), viewport.get("height"), environment.get("display_scale")) != (
            width,
            height,
            scale,
        ):
            raise VisualManifestError(f"missing or invalid environment {environment_id}")

    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise VisualManifestError("at least one visual surface is required")
    seen: set[str] = set()
    for surface in surfaces:
        if not isinstance(surface, dict):
            raise VisualManifestError("surface entries must be mappings")
        surface_id, state = surface.get("id"), surface.get("state")
        if not isinstance(surface_id, str) or not surface_id or surface_id in seen:
            raise VisualManifestError("surface IDs must be unique non-empty strings")
        seen.add(surface_id)
        if state not in ALLOWED_STATES or surface.get("review", {}).get("status") != state:
            raise VisualManifestError(
                f"{surface_id}: state and review status must match an allowed state"
            )
        if not surface.get("required_states") or not surface.get("reproduction"):
            raise VisualManifestError(
                f"{surface_id}: required states and reproduction recipe are required"
            )
        state_entries = surface.get("state_entries")
        if state_entries is not None:
            if not isinstance(state_entries, list):
                raise VisualManifestError(f"{surface_id}: state_entries must be a list")
            required_states = set(surface["required_states"])
            entry_ids = {entry.get("id") for entry in state_entries if isinstance(entry, dict)}
            if entry_ids != required_states or len(entry_ids) != len(state_entries):
                raise VisualManifestError(
                    f"{surface_id}: state_entries must cover each required state exactly once"
                )
            for entry in state_entries:
                if not isinstance(entry, dict) or entry.get("state") not in ALLOWED_STATES:
                    raise VisualManifestError(f"{surface_id}: invalid state entry")
                if entry.get("review", {}).get("status") != entry.get("state"):
                    raise VisualManifestError(
                        f"{surface_id}/{entry.get('id')}: state and review status must match"
                    )
                if require_approved and entry.get("state") not in {"approved", "out_of_scope", "superseded"}:
                    raise VisualManifestError(
                        f"{surface_id}/{entry.get('id')}: visual acceptance is blocked by {entry.get('state')}"
                    )
        if state == "approved":
            source = surface.get("source", {})
            environment = surface.get("environment", {})
            tc2000 = surface.get("tc2000", {})
            review = surface.get("review", {})
            if (
                not source.get("type")
                or not source.get("locator")
                or not source.get("sha256")
                or not source.get("permission")
                or not surface.get("measurements", {}).get("tokens")
            ):
                raise VisualManifestError(
                    f"{surface_id}: approved references require source type, locator, hash, permission, and measurements"
                )
            if tc2000.get("generation") != "25" or tc2000.get("build") != product.get("build"):
                raise VisualManifestError(
                    f"{surface_id}: approved references must identify the pinned TC2000 build"
                )
            if not tc2000.get("capture_date") or not tc2000.get("operator"):
                raise VisualManifestError(
                    f"{surface_id}: approved references require capture date and operator"
                )
            if not review.get("reviewer"):
                raise VisualManifestError(f"{surface_id}: approved references require a reviewer")
            if not all(
                environment.get(key) is not None
                for key in (
                    "resolution",
                    "display_scale",
                    "theme",
                    "locale",
                    "timezone",
                    "device_pixel_ratio",
                )
            ):
                raise VisualManifestError(
                    f"{surface_id}: approved references require complete capture environment"
                )
        if require_approved and state not in {"approved", "out_of_scope", "superseded"}:
            raise VisualManifestError(f"{surface_id}: visual acceptance is blocked by {state}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the TC2000 visual-reference manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    validate_visual_manifest(
        load_visual_manifest(args.manifest), require_approved=args.require_approved
    )
    print(f"visual manifest valid: {args.manifest}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())
