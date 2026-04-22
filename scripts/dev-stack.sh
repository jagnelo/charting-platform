#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE_DEFAULT="$ROOT/docker-compose.dev.yml"
PROJECT_PREFIX="charting-dev"

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
    printf '%s-%s\n' "$PROJECT_PREFIX" "$(branch_slug)"
}

list_active_projects() {
    docker ps --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null \
        | awk 'NF' \
        | sort -u \
        | grep "^${PROJECT_PREFIX}-" || true
}

stop_other_projects() {
    local compose_file current project
    compose_file="${1:-$COMPOSE_FILE_DEFAULT}"
    current="$(project_name)"

    while IFS= read -r project; do
        [[ -z "$project" ]] && continue
        [[ "$project" == "$current" ]] && continue

        printf '[dev-stack] Stopping other branch dev stack: %s\n' "$project"
        COMPOSE_PROJECT_NAME="$project" docker compose -f "$compose_file" down
    done < <(list_active_projects)
}

describe() {
    printf 'branch=%s\n' "$(branch_name)"
    printf 'slug=%s\n' "$(branch_slug)"
    printf 'project=%s\n' "$(project_name)"
}

usage() {
    cat <<'EOF'
Usage: scripts/dev-stack.sh <command> [args]

Commands:
  branch-name           Print the current git branch name
  branch-slug           Print the normalized branch slug
  project-name          Print the branch-scoped Docker Compose project name
  stop-others [file]    Stop other running charting-dev Compose projects
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
            project_name
            ;;
        stop-others)
            stop_other_projects "${2:-$COMPOSE_FILE_DEFAULT}"
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
