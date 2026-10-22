# Strategy Lab v2 post-release reconciliation map

Prepared read-only on 2026-10-19 from published Git objects only:

- Provider `a8440efb82232a8b217df9c7330fab1795b257c9`
- ETF `2eec09cbf9c188e1c1e61fb27ead3eb86e54e66a`
- TC2000 `c8d386d01c65b3eb31e8ddc8f30df1c00822837f`
- Strategy `b6f1e48670a74aee669e9b80330fec836770fad1`
- workflow-only staging `26443f94c5b9fd3741d28db392fecf9aafe9c699`

These refs are an inspection boundary, not accepted or frozen product sources.
No producer branch was imported. Actual implementation starts only after the
coordinator releases synchronized green Provider, then ETF, then TC2000 through
staging and supplies their final exact SHAs.

## Callable seams and assertions

| Released boundary to consume | Existing Strategy seam | Positive assertion after release | Denial and isolation assertions |
| --- | --- | --- | --- |
| Provider canonical identity | `market_data_identity.apply_domain_identity` and the persisted `Instrument.domain_key`; adapt through the host callback supplied to `CapabilityPreflightService` | A stable external identifier resolves the same owner-visible instrument and is carried into the frozen snapshot/requirement fingerprint | ticker-only, quarantined, conflicting, missing, or changed identity returns unsupported; no acquisition, worker admission, or engine launch |
| Provider local series and coverage | `market_series.SeriesScope`/`MarketSeries`, `ohlcv_coverage.OhlcvCoverageAssessment`; adapt to `CapabilityCell`, `DataSeriesManifest`, `CoverageAttestation`, `verify_snapshot_coverage`, and `verify_data_acquisition` | exact series ID/scope, timeframe, session, feed, adjustment basis/version, requested interval and locally persisted coverage produce one verified immutable snapshot | partial/missing/stale coverage, inactive/default drift, scope mismatch, missing/duplicate attestation, or freshness expiry rejects before dispatch; the resolver must not perform provider HTTP or hide a transport fallback |
| ETF historical membership | `ETFHoldingsSnapshot` and the point-in-time selectors using `composition_date`, `known_at`, and visibility state; adapt to the portfolio/universe dependency frozen into the Strategy resource | a snapshot with `composition_date <= decision date` and `known_at <= decision timestamp` freezes exact membership and lineage into the experiment/portfolio fingerprint | current/nearest non-PIT holdings, future-known snapshots, unknown timing, invisible/incomplete snapshots, unresolved/placeholder/cash/derivative rows, and owner mismatch reject; no substitution with latest holdings |
| TC immutable Code/Study output | exact `CodeVersion` (`code_asset_id`, `version_number`, source, output contract, SDK/runtime versions, dependencies and promotion lineage), completed `ResearchRun.reproducibility_hash`, and named `ResearchArtifact` output | a completed owner-scoped version/output resolves to immutable source/output fingerprints which bind `ForwardComponentExecutionPlan.strategy_fingerprint`, package fingerprint, parameters and seed | mutable latest aliases, archived/foreign assets, incomplete/failed runs, missing or stale artifact, wrong output contract, source/output hash drift, or owner mismatch reject before admission |
| Strategy worker terminal path | `PostgresStrategyLabV2Adapter`, `WorkerRecoveryApplication.complete_terminal_if_persisted`, result-completion, settlement, pool/reservation and lease stores | one admitted attempt publishes native result/completion, then matching settlement/release; restart/redelivery closes the same candidate and ACKs without a second Nautilus launch | completion newer than observation, settlement before completion, unavailable/wrong pool profile, reservation attempt/time mismatch, lease/release mismatch, conflicting candidate, or cross-owner evidence remains `RETRY`; no replacement attempt or ACK |

Fixture or synthetic adapter output may establish parsing and denial behavior,
but cannot be labelled native Nautilus execution proof. Native publication keeps
the existing scope-qualified exact-pinned Nautilus v2 authority: local backtests
need their four conformance checks; broker-free forward shadow needs event-tape
parity; broker/capital access remains disabled for prereleases and by default.

## Implementation order after the synchronized release

1. Verify the released staging SHA and each accepted producer SHA; recompute the
   shared-path and migration inventories before editing.
2. Merge that exact staging release into this branch through the owner workflow.
   Reconcile `main.py`, `config.py`, router registration, Compose worker commands,
   and coverage-runner semantics without enabling provider or broker traffic.
3. Add host adapters at `StrategyLabV2ApiBindings`/`PostgresStrategyLabV2Adapter`
   composition boundaries. Keep `capability_preparation.py`,
   `data_acquisition.py`, `snapshot_coverage.py`, and
   `forward_execution_plan.py` provider-neutral and I/O-free.
4. Add focused adapter/application tests for every positive and denial row above,
   including repeated calls after revocation, process restart, cross-owner reads,
   and a no-hidden-network spy asserting zero provider callbacks on denial and all
   cached/PIT reads.
5. Preserve `slv2_0001..slv2_0008` unchanged. If upstream heads diverge, add one
   additive merge/equivalence revision from the actual released heads. Prove one
   head plus fresh and retained previous-release PostgreSQL upgrade/schema
   equivalence and startup compatibility; never reparent, stamp, reset, or delete.
6. Run the Strategy package and adapter suites, combined backend coverage with
   actual Strategy collection and unchanged package 55/aggregate 75 thresholds,
   combined PostgreSQL/Redis migration and restart tests, API success/unavailable
   routes, worker startup/health, then the assigned `full_stack_browser` profile.
   The coordinator-owned staging merge must subsequently pass the Exhaustive
   Integration Gate. Preserve any red/flaky result instead of rerunning blindly.

## Current wait condition

Product checkpoints in staging remain `0/4`. Provider candidate `a8440efb...`
has green hosted/browser/live-subset evidence, but its corrected current-source
local backend gate, migration/held-operation review, coordinator acceptance, and
staging release remain open. ETF and TC2000 follow it in order. Until the
coordinator supplies the synchronized green release, combined-source adapter
implementation and its heavy validation are intentionally not started.
