#!/usr/bin/env python3
"""Manual, scope-safe ARM64 bundle and RPi deployment helper.

This module deliberately has no cleanup path.  Remote Docker commands always
name the fixed charting-platform project and release Compose file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "rpi" / "compose.yml"
EXAMPLE = ROOT / "deploy" / "rpi" / "rpi.env.example"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_config() -> dict[str, str]:
    path = ROOT / ".ai" / "deploy" / "rpi.env"
    if not path.exists():
        raise SystemExit(f"missing ignored deployment config: {path} (copy {EXAMPLE})")
    if path.stat().st_mode & 0o077:
        raise SystemExit(f"deployment config must be mode 0600: {path}")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.replace("_", "").isalnum():
            raise SystemExit(f"invalid deployment config line: {line!r}")
        values[key] = value.strip().strip("'\"")
    required = {"RPI_SSH_TARGET", "RPI_DEPLOY_ROOT", "RPI_HTTP_PORT"}
    missing = sorted(required - values.keys())
    if missing:
        raise SystemExit(f"deployment config is missing: {', '.join(missing)}")
    if values["RPI_DEPLOY_ROOT"] != "/opt/charting-platform":
        raise SystemExit("RPI_DEPLOY_ROOT must remain /opt/charting-platform")
    int(values["RPI_HTTP_PORT"])
    return values


def exact_commit(commit: str) -> None:
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise SystemExit("COMMIT must be a full lowercase 40-character SHA")
    if git("branch", "--show-current") != "master":
        raise SystemExit("RPi operations must run from the root master checkout")
    if git("status", "--porcelain"):
        raise SystemExit("master is dirty")
    if git("rev-parse", "master") != commit:
        raise SystemExit("COMMIT is not the current master SHA")
    if git("rev-parse", "master") != git("rev-parse", "origin/master"):
        raise SystemExit("master is not synchronized with origin/master")
    receipt = ROOT / ".ai" / "validation" / f"{commit}.json"
    if not receipt.exists():
        raise SystemExit(f"missing exact validation receipt: {receipt}")
    try:
        data = json.loads(receipt.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid validation receipt: {receipt}: {exc}") from exc
    if data.get("candidate_sha") != commit or data.get("tree") != git(
        "rev-parse", f"{commit}^{{tree}}"
    ):
        raise SystemExit("validation receipt does not match COMMIT and tree")
    if (
        os.environ.get("RPI_REQUIRE_CI_REPLAY", "true").lower() == "true"
        and data.get("github_replay") != "pass"
    ):
        raise SystemExit("independent GitHub replay is not recorded as pass for COMMIT")


def ssh_args(config: dict[str, str]) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"ConnectTimeout={config.get('RPI_SSH_CONNECT_TIMEOUT', '10')}",
        config["RPI_SSH_TARGET"],
    ]


def remote(config: dict[str, str], command: str, *, stdin: bytes | None = None) -> str:
    result = subprocess.run(
        ssh_args(config) + ["--", "sh", "-s"], input=stdin, capture_output=True
    )
    if result.returncode:
        raise SystemExit(
            result.stderr.decode(errors="replace") or "remote command failed"
        )
    return result.stdout.decode()


def preflight(config: dict[str, str]) -> None:
    root = shlex.quote(config["RPI_DEPLOY_ROOT"])
    port = shlex.quote(config["RPI_HTTP_PORT"])
    script = f"""set -eu
test "$(uname -m)" = aarch64 || {{ echo 'RPi must run a 64-bit aarch64 OS' >&2; exit 20; }}
test "$(docker info --format '{{{{.Architecture}}}}')" = aarch64 || {{ echo 'Docker architecture is not linux/arm64' >&2; exit 21; }}
docker compose version >/dev/null
test -d {root} && test -w {root}
test -d {root}/shared && test -w {root}/shared
test -f {root}/shared/app.env && test "$(stat -c '%a' {root}/shared/app.env 2>/dev/null || stat -f '%Lp' {root}/shared/app.env)" = 600
test "$(df -Pk {root} | awk 'NR==2 {{print $4}}')" -gt 2097152
if command -v ss >/dev/null 2>&1; then ! ss -ltnH | awk '{{print $4}}' | grep -E '[:.]'"{port}"'$' >/dev/null; fi
foreign="$(docker ps --format '{{{{.Label \"com.docker.compose.project\"}}}}' | awk '$1 == \"charting-platform\" {{print}}')"
if test -n "$foreign" && test ! -L {root}/current; then
  echo 'reserved Compose project charting-platform is occupied without a managed release' >&2
  exit 22
fi
"""
    # The foreign-project check is intentionally informational for the fixed
    # project: a charting deployment may already exist and is inspected by the
    # transaction before it is updated; unrelated project names are untouched.
    print(remote(config, script.encode()).strip() or "RPi preflight passed")


def image_tag(name: str, commit: str) -> str:
    return f"charting-platform/{name}:{commit}"


def build_bundle(commit: str) -> Path:
    exact_commit(commit)
    output = ROOT / ".ai" / "deploy" / "bundles"
    output.mkdir(parents=True, exist_ok=True)
    tags = [
        image_tag("backend", commit),
        image_tag("research-runner", commit),
        image_tag("frontend", commit),
    ]
    builds = [
        ("backend", ROOT / "backend" / "Dockerfile", ROOT / "backend"),
        (
            "research-runner",
            ROOT / "backend" / "Dockerfile.research-runner",
            ROOT / "backend",
        ),
        ("frontend", ROOT / "frontend" / "Dockerfile", ROOT / "frontend"),
    ]
    for (name, dockerfile, context), tag in zip(builds, tags, strict=True):
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
                f"org.opencontainers.image.revision={commit}",
                "--label",
                "org.opencontainers.image.architecture=linux/arm64",
                "--label",
                f"org.opencontainers.image.created={datetime.now(timezone.utc).isoformat()}",
                "-f",
                str(dockerfile),
                "-t",
                tag,
                str(context),
            ],
            cwd=ROOT,
            check=True,
        )
    manifest = {
        "source_sha": commit,
        "tree": git("rev-parse", f"{commit}^{{tree}}"),
        "architecture": "linux/arm64",
        "compose_sha256": hashlib.sha256(COMPOSE.read_bytes()).hexdigest(),
        "images": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    for tag in tags:
        inspect = subprocess.check_output(
            ["docker", "image", "inspect", tag], text=True
        )
        item = json.loads(inspect)[0]
        manifest["images"].append(
            {
                "tag": tag,
                "id": item.get("Id"),
                "repo_digests": item.get("RepoDigests", []),
            }
        )
    manifest_path = output / f"{commit}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    archive = output / f"{commit}.docker.tar.gz"
    # docker save output is captured to avoid shell redirection and to make the
    # resulting bytes explicit before compression.
    raw = subprocess.check_output(["docker", "save", *tags], cwd=ROOT)
    import gzip

    with gzip.open(archive, "wb", compresslevel=6) as handle:
        handle.write(raw)
    manifest["bundle_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "bundle": str(archive),
                "manifest": str(manifest_path),
                "sha256": manifest["bundle_sha256"],
            },
            indent=2,
        )
    )
    return archive


def deploy(config: dict[str, str], commit: str, confirm: str) -> None:
    if confirm != commit:
        raise SystemExit("CONFIRM must exactly equal COMMIT")
    exact_commit(commit)
    preflight(config)
    bundle = ROOT / ".ai" / "deploy" / "bundles" / f"{commit}.docker.tar.gz"
    manifest = ROOT / ".ai" / "deploy" / "bundles" / f"{commit}.manifest.json"
    if not bundle.exists() or not manifest.exists():
        raise SystemExit("build the exact COMMIT bundle first with make rpi-bundle")
    root = config["RPI_DEPLOY_ROOT"]
    remote_path = f"{root}/incoming/{commit}.docker.tar.gz.part"
    subprocess.run(
        ssh_args(config)
        + [
            "--",
            "mkdir",
            "-p",
            f"{root}/incoming",
            f"{root}/releases",
            f"{root}/backups",
            f"{root}/locks",
        ],
        check=True,
    )
    subprocess.run(
        [
            "scp",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"ConnectTimeout={config.get('RPI_SSH_CONNECT_TIMEOUT', '10')}",
            str(bundle),
            f"{config['RPI_SSH_TARGET']}:{remote_path}",
        ],
        check=True,
    )
    checksum = hashlib.sha256(bundle.read_bytes()).hexdigest()
    checksum_path = bundle.with_suffix(bundle.suffix + ".sha256")
    checksum_path.write_text(f"{checksum}  {commit}.docker.tar.gz.part\n")
    subprocess.run(
        [
            "scp",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            str(checksum_path),
            f"{config['RPI_SSH_TARGET']}:{root}/incoming/{commit}.docker.tar.gz.part.sha256",
        ],
        check=True,
    )
    remote_script = f"""set -eu
root={shlex.quote(root)}; sha={shlex.quote(commit)}
lock="$root/locks/deploy.lock"
mkdir "$lock" 2>/dev/null || {{ echo 'deployment lock already held' >&2; exit 30; }}
trap 'rmdir "$lock"' EXIT
test -f "$root/shared/app.env"
test "$(sha256sum "$root/incoming/$sha.docker.tar.gz.part" | awk '{{print $1}}')" = "$(awk '{{print $1}}' "$root/incoming/$sha.docker.tar.gz.part.sha256")"
mv "$root/incoming/$sha.docker.tar.gz.part" "$root/incoming/$sha.docker.tar.gz"
mkdir "$root/releases/$sha"
cp "$root/incoming/$sha.docker.tar.gz" "$root/releases/$sha/"
cp "$root/incoming/$sha.manifest.json" "$root/releases/$sha/"
cp "$root/incoming/$sha.compose.yml" "$root/releases/$sha/compose.yml"
cp "$root/shared/app.env" "$root/releases/$sha/release.env"
printf '\\nBACKEND_IMAGE=charting-platform/backend:%s\\nRESEARCH_RUNNER_IMAGE=charting-platform/research-runner:%s\\nFRONTEND_IMAGE=charting-platform/frontend:%s\\nPOSTGRES_IMAGE={shlex.quote(config.get('POSTGRES_IMAGE', 'postgres:16-alpine'))}\\nREDIS_IMAGE={shlex.quote(config.get('REDIS_IMAGE', 'redis:7-alpine'))}\\nRPI_HTTP_PORT={shlex.quote(config['RPI_HTTP_PORT'])}\\n' "$sha" "$sha" "$sha" >> "$root/releases/$sha/release.env"
if test -L "$root/current" && docker compose -p charting-platform -f "$root/current/compose.yml" --env-file "$root/current/release.env" ps postgres --format '{{{{.State}}}}' 2>/dev/null | grep -q running; then
  backup="$root/backups/$sha.sql.part"
  docker compose -p charting-platform -f "$root/current/compose.yml" --env-file "$root/current/release.env" exec -T postgres pg_dump -Fc -U "${{POSTGRES_USER:-postgres}}" "${{POSTGRES_DB:-chartingdb}}" > "$backup"
  docker run --rm -i {shlex.quote(config.get('POSTGRES_IMAGE', 'postgres:16-alpine'))} pg_restore --list < "$backup" >/dev/null
  mv "$backup" "$root/backups/$sha.sql"
fi
docker load < "$root/releases/$sha/$sha.docker.tar.gz"
docker compose -p charting-platform -f "$root/releases/$sha/compose.yml" --env-file "$root/releases/$sha/release.env" up -d --no-build --wait
docker compose -p charting-platform -f "$root/releases/$sha/compose.yml" --env-file "$root/releases/$sha/release.env" ps
"""
    # Upload metadata separately and atomically after its content is verified.
    for local, remote_name in (
        (manifest, f"{root}/incoming/{commit}.manifest.json"),
        (COMPOSE, f"{root}/incoming/{commit}.compose.yml"),
    ):
        subprocess.run(
            [
                "scp",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                str(local),
                f"{config['RPI_SSH_TARGET']}:{remote_name}",
            ],
            check=True,
        )
    try:
        remote(config, remote_script.encode())
    except Exception as exc:
        rollback = f"""set -eu
root={shlex.quote(root)}
if test -L "$root/current"; then docker compose -p charting-platform -f "$root/current/compose.yml" --env-file "$root/current/release.env" up -d --no-build --wait; fi
"""
        try:
            remote(config, rollback.encode())
        except Exception:
            pass
        raise SystemExit(str(exc)) from exc
    try:
        smoke(config, commit)
        finalize = f"""set -eu
root={shlex.quote(root)}; sha={shlex.quote(commit)}
ln -s "$root/releases/$sha" "$root/current.$sha.tmp"
mv -Tf "$root/current.$sha.tmp" "$root/current"
"""
        remote(config, finalize.encode())
    except Exception as exc:
        rollback = f"""set -eu
root={shlex.quote(root)}
if test -L "$root/current"; then docker compose -p charting-platform -f "$root/current/compose.yml" --env-file "$root/current/release.env" up -d --no-build --wait; fi
"""
        remote(config, rollback.encode())
        raise SystemExit(str(exc)) from exc
    finally:
        checksum_path.unlink(missing_ok=True)
    print(
        f"deployed charting-platform at {commit}; no unrelated Docker resources were touched"
    )


def smoke(config: dict[str, str], commit: str) -> None:
    username = config.get("RPI_SMOKE_USERNAME", "")
    password = config.get("RPI_SMOKE_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "RPI_SMOKE_USERNAME and RPI_SMOKE_PASSWORD are required for authenticated deployment smoke"
        )
    base = f"http://{config['RPI_SSH_TARGET']}:{config['RPI_HTTP_PORT']}"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"health returned HTTP {response.status}")
        payload = json.dumps({"username": username, "password": password}).encode()
        request = urllib.request.Request(
            f"{base}/api/v1/auth/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            token = json.loads(response.read()).get("access_token")
        if not token:
            raise RuntimeError("login response did not contain access_token")
        request = urllib.request.Request(
            f"{base}/api/v1/providers/availability",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"authenticated availability returned HTTP {response.status}"
                )
    except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
        raise RuntimeError(
            f"authenticated LAN smoke failed for {commit}: {exc}"
        ) from exc


def status(config: dict[str, str]) -> None:
    root = shlex.quote(config["RPI_DEPLOY_ROOT"])
    print(
        remote(
            config,
            f"set -eu; docker compose -p charting-platform -f {root}/current/compose.yml ps".encode(),
        ).strip()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    p = sub.add_parser("bundle")
    p.add_argument("commit")
    p = sub.add_parser("deploy")
    p.add_argument("commit")
    p.add_argument("confirm")
    sub.add_parser("status")
    args = parser.parse_args()
    config = load_config()
    if args.command == "preflight":
        preflight(config)
    elif args.command == "bundle":
        build_bundle(args.commit)
    elif args.command == "deploy":
        deploy(config, args.commit, args.confirm)
    else:
        status(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
