#!/usr/bin/env python3
"""Build and inspect the production application images for Linux ARM64.

The validation is deliberately independent of RPi credentials and does not
push or retain an image tag.  It proves that every application Dockerfile can
be built for the Pi architecture before an exact release bundle is created.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHA = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
).strip()
TAG_SUFFIX = SHA[:12]

BUILDS = (
    ("backend", ROOT / "backend" / "Dockerfile", ROOT / "backend"),
    (
        "research-runner",
        ROOT / "backend" / "Dockerfile.research-runner",
        ROOT / "backend",
    ),
    ("frontend", ROOT / "frontend" / "Dockerfile", ROOT / "frontend"),
)


def main() -> int:
    tags = [f"charting-platform/arm64-validation-{name}:{TAG_SUFFIX}" for name, _, _ in BUILDS]
    try:
        for (name, dockerfile, context), tag in zip(BUILDS, tags, strict=True):
            subprocess.run(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--platform",
                    "linux/arm64",
                    "--load",
                    "--label",
                    "org.opencontainers.image.repository=charting-platform",
                    "--label",
                    f"org.opencontainers.image.revision={SHA}",
                    "--label",
                    "org.opencontainers.image.architecture=linux/arm64",
                    "-f",
                    str(dockerfile),
                    "-t",
                    tag,
                    str(context),
                ],
                cwd=ROOT,
                check=True,
            )
            inspect = subprocess.check_output(
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{.Os}} {{.Architecture}}",
                    tag,
                ],
                cwd=ROOT,
                text=True,
            ).strip()
            if inspect != "linux arm64":
                raise RuntimeError(f"{name} image has unexpected platform: {inspect!r}")
    finally:
        # Remove only the exact temporary validation tags.  No unrelated
        # application, runtime, volume, or network resource is touched.
        for tag in tags:
            subprocess.run(
                ["docker", "image", "rm", tag],
                cwd=ROOT,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    print(f"validated {len(BUILDS)} production images for linux/arm64 at {SHA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
