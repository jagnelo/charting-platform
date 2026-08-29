# fix/research-runner-probes

This workstream starts from master `e2f67d6c1c9e08a23ba4004fc3a0a87cf15dc844`.

The latest independent master replay reaches the exhaustive integration gate but
fails in `make test-research-runner-probes`. GNU Make reports the sub-target as
exit 2, which hid whether container discovery, sandbox checks, or resource
pressure was responsible. This branch adds a nested stage boundary and GitHub
annotation so the next exact replay preserves the first failing probe stage.

Local ARM64 Docker validation currently passes all sandbox and resource checks.
The remaining acceptance boundary is a green Linux/amd64 GitHub replay followed
by the exact-candidate integration receipt.

## 2026-08-29 — Workflow branch closure

The human authorized closure of this workflow-only branch. Its source changes are reachable from master. The branch is no longer an active development line; its remote ref and workstream record remain as audit history. Any future work starts from green `staging`, and product/deployment gaps are not claimed complete merely because the implementation is reachable from `master`.
