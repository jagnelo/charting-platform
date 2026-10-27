# On-demand market acquisition contract proposal — 2026-10-27

Status: proposal for coordinator/owner review only. The human authorized
preparation of this checkpoint (“Ok, so proceed then”); this is not product
implementation, provider admission, live proof, or permission to replay the
consumed 119-request validation allowance. The existing 24-item Provider
roadmap and accepted checkpoints remain intact.

## Reuse and current gaps

- `GET /api/v1/instruments/search` in `backend/app/routers/instruments.py`
  calls `search_provider_instruments_async` when `canonical_only=false`.
  `backend/app/services/market_data.py` snapshots results and routes each
  provider call through `resolve_provider_chain` and `execute_provider_call`.
  Results are transient candidates; provider-only rows do not become canonical
  instruments. `POST /instruments/resolve-canonical` is intentionally local
  security-master-only.
- Avoid `GET /instruments/{symbol}` as the discovery/selection action: a
  missing symbol invokes `_create_from_provider`, then schedules bulk history
  and instrument-event work. `POST /instruments/resolve-expression` also has
  provider-backed auto-creation unless `canonical_only=true`.
- `GET /coverage/instruments/{symbol}/ohlcv` is a read-only local coverage
  assessment. `GET /ohlcv/local/{symbol}/{timeframe}` is local-only. In
  contrast, `GET /ohlcv/{symbol}/{timeframe}` defaults `local_only=false`, and
  its service path can call `fetch_ohlcv`; explicit range gaps are split by
  `missing_range_slices`, then `execute_provider_call` performs normal
  `PRICE_HISTORY` admission and persistence. The explicit workflow must not
  rely on a chart render or other ordinary GET as consent to acquire.
- Reuse `fetch_ohlcv` and its `_with_ohlcv_refresh_gate`, optional Redis lock,
  database advisory lock, cache recheck, selected default-series predicate,
  and provider request logging. Do not add a parallel provider adapter,
  quota ledger, or acquisition framework. `MarketRefreshJob` exists, but the
  generic worker claims a batch; an explicit request must not enqueue a broad
  batch that could consume unrelated queued jobs.

## Proposed additive wire contract

1. Keep typeahead/canonical lookup local (`canonical_only=true`). Add an
   authenticated explicit discovery action, preferably
   `POST /api/v1/instruments/discover`, with a bounded body:

   ```json
   {"query":"OIH","types":["ETF"],"limit":10,"request_id":"<client-generated-id>"}
   ```

   It may reuse `search_provider_instruments_async` but must run only on the
   explicit submit action, not on mount or every keystroke. Return a typed
   envelope with `request_id`, `status` (`complete`, `partial`, `held`,
   `unavailable`, `failed`), `candidates` (symbol/name/type/exchange,
   `instrument_id` nullable, provider/source, and `identity_status`), and
   `source_outcomes` (provider, capability, operation, status, stable
   `reason_code`). A returned provider candidate is not a verified canonical
   identity. Selecting it must use the existing identity/profile ingestion
   safeguards through an explicit selection step; do not make search itself
   silently fan out to profile, bars, or events.

   The coordinator-reported OIH row (instrument 43) is an existing
   industry-proxy scaffold, not proof of a qualified security identity. The
   repository's curated VanEck product slug and industry-proxy taxonomy are
   useful lookup context, but do not establish its external security key or
   authoritative active listing. Before treating OIH as the selected
   instrument, inspect the normal instrument/provenance representation for
   `identity_status`, `domain_key`, active primary listing/MIC, identifiers,
   and provider-symbol bindings. If any are absent, provisional, conflicting,
   or not source-proven, reconcile the existing row through the normal
   profile/mastering path; never create a duplicate or merge on ticker alone.
   Preserve the industry-proxy classification and field provenance, and
   quarantine an identifier/listing conflict rather than fetching history
   against an ambiguous row. The current source-only review cannot assert
   instrument 43's live identity fields; no target DB read was made.

2. Add an authenticated selected-history action, e.g.
   `POST /api/v1/instruments/{instrument_id}/history-acquisitions`, accepting
   only an existing non-synthetic canonical instrument and one timeframe:

   ```json
   {"timeframe":"D1","adjusted":true,"start":"<UTC instant>",
    "end":"<UTC instant>","request_id":"<client-generated-id>"}
   ```

   Require a finite ordered range, an application maximum range/response size
   derived from reviewed provider contracts, and a single symbol/timeframe per
   request. Compute local selected-series coverage first; return immediately
   without provider traffic if complete/fresh. Otherwise call the existing
   `fetch_ohlcv(..., start, end, adjusted=..., allow_provider_fetch=True)` for
   the requested missing slices, preserving normal runtime admission,
   reservations, transport accounting, settlement, and storage lineage. Use
   the existing coalescing locks and cache recheck so equivalent concurrent
   clicks share work and the waiter sees committed bars. Return a response
   envelope with request/instrument/timeframe/range, `status` (`complete`,
   `partial`, `held`, `no_data`, `failed`), canonical local coverage and
   `missing_slices`, plus non-secret provider `source_outcomes`/reason codes.
   Do not claim success from an empty response or partial local coverage.

The status envelope is response/status reporting, not a new admission layer.
Expose held candidates through existing provider status/governance facts (for
example `list_provider_status` and the read-only provider availability view),
with stable reasons such as held quota, unknown plan, unsupported symbol,
missing credential, circuit open, or no reviewed source. Provider exceptions
must remain redacted; no credentials or vendor payload secrets in results.

## Routing, schedules, eligibility, and proof gates

Broad schedules are independent: `INSTRUMENT_SYNC_SCHEDULE_ENABLED` and
`MARKET_DATA_REFRESH_SCHEDULE_ENABLED` default false, and worker cron
registration is conditional on them. The explicit route can invoke the shared
service directly without enabling those schedules. However,
`PROVIDER_ROUTING_ENABLED=false` makes `resolve_provider_chain` return no
providers for every capability. Do not bypass that emergency switch. Before an
explicit acquisition is operational, the deployment must either keep global
routing enabled with only the reviewed required capability policies enabled
and ensure ordinary reads/background paths stay local-only, or obtain a
separate reviewed design for a request-scoped exception. Never flip the global
switch around a request or let a chart GET become hidden consent.

The source seeds `PRICE_HISTORY` as Alpaca then Alpha Vantage; Massive is not
in this default history chain. Alpaca's configured seed is free IEX with
authentication, plan/history/venue constraints and redistribution restrictions,
but exposed credentials are excluded and no current usable Alpaca credential
is claimed. Alpha Vantage has a free-key seed but its `*` checkpoint hold and
current quota/headroom conditions must clear; the seed alone does not admit
it. Thus no history source is asserted currently routable. Search seeds EDGAR,
Massive, and Alpha Vantage; each still needs its exact search operation to pass
runtime gates. Massive's Basic seed is described as free, but its rolling
account-minute baseline is a known prior hold; EDGAR search must retain its
User-Agent/fair-access and same-egress scope requirements. These are candidates,
not fresh quota or account evidence.

Every physical operation must continue through `resolve_provider_chain` /
`execute_provider_call`: global routing, enabled capability policy, exact
reviewed free entitlement (no trial; paid stays false), positive live-probe
state, configured credential/terms, provider and symbol/timeframe support,
operation-specific hold, health/circuit, exact cost, history-depth bounds,
fresh native/account observations where required, durable quota reservation
and settlement, response/attempt caps, and provider error/global-stop policy.
No source is admitted merely because it is marked free. Required fresh,
source-matching live validation and current native admission are outstanding;
the consumed 119 requests cannot satisfy a new acquisition allowance.

## Review boundary

Coordinator and Provider/ETF/TC owners should review route ownership, canonical
identity selection, and the global-routing/local-only interaction before
implementation. TC owns all UI. This proposal makes no provider call, changes
no policy/hold/quota, and records no live acceptance.

## Implementation contract update — 2026-10-27

The coordinator released the Provider-owned implementation. This section
supersedes earlier proposal-only routing and quota suggestions above where they
conflict with the reviewed implementation direction. The prior 1/minute Massive
application dimension is withdrawn: keep its existing exact 5 requests per
rolling 60 seconds durable application ledger contract and do not add a generic
one-per-minute cap. Native total/reset, concurrency, and burst remain unknown;
the existing local semaphore default is an application safety behavior, not
native verification. Root's current read-only ledger receipt (1,214 settled,
last Oct 26 21:03:39 UTC, no current-window/pending/uncertain rows at that
observation) is historical evidence only; actual admission must re-read shared
SQLite ledger, current window, holds, and headroom. Never create/reset/replace
the SQLite ledger because PostgreSQL has no quota-ledger tables.

The selected-history request adds optional exact `source_provider`. When set,
its server scope is `provider_names={source_provider}` and cannot fall back to
another provider; `massive` is the proposed selected source for a bounded OIH
D1 missing-slice request, subject to fresh ordinary free-only, operation-hold,
support, identity, cost, durable quota, settlement, credential, and current-
headroom admission. Keep request-range and missing-slice caps as application
workload bounds, separate from Massive's five-per-minute documented account
limit. No provider call is authorized by this contract.

The ETF-owned first VanEck sample may call this Provider helper only after ETF
has committed/claimed its durable one-shot job and checked the committed fund,
instrument, exact publisher symbol, review revision, and configured account
mapping:

```python
with bind_vaneck_initial_etf_qualification(
    job_id=job.id,
    fund_profile_id=profile.id,
    instrument_id=instrument.id,
    provider_symbol=committed_symbol,
    account_scope=resolved_account_scope,
    review_revision=entitlement.revision,
    expires_at=job.expires_at,
):
    execute_provider_call(
        db, ProviderCapability.ETF_HOLDINGS, "fetch_etf_holdings_latest",
        instrument_id=instrument.id, provider_symbol=committed_symbol,
        profile_id=profile.id, provider_name="vaneck", invoke=bridge_call,
    )
```

The permit is opaque, task-local, exact-source/operation/fund/account/revision
bound, expiry checked, and consumed before the first await so failure or
cancellation cannot replay it. It admits only an entitlement still `not_run`;
it does not write a positive probe, enable the persisted policy, clear holds,
bypass free-only/cost/health/identity/quota/native-unknown/global-routing checks,
or allow SEC fallback. A genuine matched issuer snapshot and ETF's durable
audit remain necessary before ETF records actual positive evidence. Failed or
partial qualification remains nonpositive. The normal emergency global-routing
switch remains authoritative and is a Root-owned target-operation precondition.

Root's VanEck sample bounds are application-only: concurrency 1, at least 30s
between physical attempts (including redirects), burst 1, at most 3 physical
requests including redirects, 120s deadline, 5 MiB response body, zero automatic
retries, and no SEC fallback. These are not vendor quota claims. The publisher
provisioner's quota timestamp is documented and persisted as an application
budget review when all dimensions are `application_usage_only`, never native
verification. An unknown first redirect is stopped before following and its
`Location` is retained for review. No target configuration or transport was
changed or exercised here.
