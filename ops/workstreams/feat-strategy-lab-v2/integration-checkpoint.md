# strategy-lab-v2-integration-1 preparation

Planning direction: central-first coordination dated 2026-10-15 in the staging
coordinator checkout. Human checkpoint acceptance and closure remain pending.
The complete goal and all 18 original criteria are retained verbatim in
`roadmap_goal` and `roadmap_acceptance_criteria` in plan.yaml. Historical progress
is retained separately and is not completion evidence for the five checkpoint criteria.

## Consumer contract map

| Consumer boundary | Existing Strategy-owned contract and executable evidence | Required staged reconciliation |
| --- | --- | --- |
| Capability admission | `capability_preparation.py`, `test_capability_preparation.py`: absent host coverage, injected trusted cells, request digest mismatch and degraded ranking rejection | Provider canonical identity, entitlement, quota and coverage readers; no guessed capability cells |
| Acquire/verify/freeze | `data_acquisition.py`, `test_data_acquisition.py`, `snapshot_coverage.py`, `test_snapshot_coverage.py`: receipt time/identity drift, missing/duplicate/misaligned series attestations | Provider canonical series/calendar/coverage identity and provenance; acquisition stays outside simulation |
| Frozen history | `authenticated_event_tape.py`, `test_event_tape_artifacts.py`: absent owner snapshot, alias fingerprints, missing/corrupt bytes and source interval mismatch | Staged provider decoder and canonical IDs; unavailable inputs reject before runtime |
| Portfolio membership | Frozen snapshot/dependency declarations exist; a real ETF consumer bridge is not yet proven | ETF owns membership history and known-at provenance. Verify historical inclusion and reject future-known or unavailable membership; never substitute current holdings |
| Strategy/Study lineage | `forward_execution_plan.py`, `test_forward_execution_plan.py`: pinned component strategies/packages/seeds and foreign-owner rejection | Bind actual staged immutable CodeVersion and Study outputs, source/output hashes and owner lineage; reject mutable/latest aliases and stale outputs |
| API/artifact access | `api_router.py`, `test_api_router.py`, PostgreSQL curve integration: owner-scoped reads and corrupt/released-pin rejection | Reconcile router/auth/config registration; confirm real combined API success and unavailable responses |
| Worker startup/recovery | Dedicated backtest/forward entrypoints, Compose contract tests and PostgreSQL/Redis recovery integrations | Reconcile shared config, migration graph and service startup with staged changes; persist receipt before ACK and enforce lease/owner checks |

These are consumer-side contracts and independent tests, not proof of the future
combined adapters. Required consumer behavior remains open until tested against
the actual staged implementations. No provider, ETF or TC code is imported here.

The capability service also has repeated-request evidence: after an earlier
rigorous result, removed host coverage rejects a later identical request;
coverage/engine resolver outages propagate failure without reusing prior success;
and rigorous data cannot authorize an engine lacking the requested product,
execution model or account model. This checks the Strategy-owned consumer
boundary only. Provider entitlement/quota revocation must still be verified
through the real staged host resolver and API error mapping.

## Evidence reconciliation

The later validation journal supersedes the old session instruction to implement
RC6 OOS recovery. RC6 native OOS terminal settlement/reclaim and forward recovery
already have dated PostgreSQL/Redis receipts. The journal also records 1,632
package tests passed, one skipped, 83.35% combined backend coverage, API transfer
and migration/Compose checks. These are historical source-qualified receipts;
they do not prove combined staging acceptance or exact-current-source CI.
The skipped image integration requires its explicit pinned runtime fixture; it
is not a general platform skip or an accepted omission from conformance.

The live HTTP probe used seeded 43-byte fixture content with curve media headers.
It proves authenticated metadata/pin-to-byte transport only, not valid Parquet
generation or a complete user-submitted experiment. Native curve serialization
and combined experiment execution require their separate evidence.

Exact-pinned scope-qualified Nautilus 2.0.0rc6 remains eligible; no stable-release
label is required. A new build needs its own scope conformance. Broker access,
capital execution, deployed shadow activation and operational trials stay outside
this checkpoint preparation.

## Required sequence and review receipt

1. Prepare and run independent consumer/negative-path tests in this worktree.
2. Wait for the coordinator's exact synchronized green staging receipt containing
   accepted Provider, ETF and TC2000 checkpoints, and verify source is unfrozen.
3. Merge that staging baseline into this clean feature branch, reconcile each
   contract above and every overlapping router/migration/config/worker path.
4. Run full_integration/full_stack_browser and exact-source branch CI. Preserve
   failures and explicit unsupported operations; fixture green is insufficient.
5. Publish a clean pushed checkpoint for human review, including tested source,
   migration/default impacts, limitations, original-criterion dispositions and
   `integration_capture: exact branch HEAD`. Human acceptance stays pending.

The central coordinator alone integrates into staging. After all four integrations
are green and source freeze is released, merge the common green staging into this
same branch, validate affected contracts and continue the complete roadmap.
