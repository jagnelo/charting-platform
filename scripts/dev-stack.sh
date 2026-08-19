#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE_DEFAULT="$ROOT/docker-compose.dev.yml"
PROJECT_PREFIX_BASE="charting"

branch_name() {
    local branch
    branch="$(git -C "$ROOT" branch --show-current 2>/dev/null || true)"
    if [[ -z "$branch" ]]; then
        branch="detached-head"
    fi
    printf '%s\n' "$branch"
}

branch_slug() {
    local branch slug
    branch="$(branch_name)"
    slug="$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
    if [[ -z "$slug" ]]; then
        slug="detached-head"
    fi
    printf '%s\n' "$slug"
}

project_name() {
    local flavor prefix
    flavor="${1:-dev}"
    case "$flavor" in
        dev)
            prefix="${PROJECT_PREFIX_BASE}-dev"
            ;;
        app|stack|e2e|test)
            prefix="${PROJECT_PREFIX_BASE}-stack"
            ;;
        *)
            prefix="${PROJECT_PREFIX_BASE}-${flavor}"
            ;;
    esac
    printf '%s-%s\n' "$prefix" "$(branch_slug)"
}

describe() {
    printf 'branch=%s\n' "$(branch_name)"
    printf 'slug=%s\n' "$(branch_slug)"
    printf 'dev_project=%s\n' "$(project_name dev)"
    printf 'stack_project=%s\n' "$(project_name stack)"
}

usage() {
    cat <<'EOF'
Usage: scripts/dev-stack.sh <command> [args]

Commands:
  branch-name           Print the current git branch name
  branch-slug           Print the normalized branch slug
  project-name [flavor] Print the branch-scoped Docker Compose project name
  stop-current [file] [flavor]
                        Stop only this worktree's exact Compose project
  describe              Print branch, slug, and project name
EOF
}

main() {
    local cmd="${1:-}"
    case "$cmd" in
        branch-name)
            branch_name
            ;;
        branch-slug)
            branch_slug
            ;;
        project-name)
            project_name "${2:-dev}"
            ;;
        stop-current)
            COMPOSE_PROJECT_NAME="$(project_name "${3:-dev}")" docker compose -f "${2:-$COMPOSE_FILE_DEFAULT}" down
            ;;
        describe)
            describe
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
