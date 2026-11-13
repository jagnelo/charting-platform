# Provider native admission handoff — 2026-11-07

## Scope and evidence boundary

This handoff is pinned to Provider source `22c31cd3e7f35e361e286ef40576d379aaf44449` (clean worktree when reviewed). Relevant SHA-256 values: `backend/app/config.py` `334fc1f98f623569bf74e5b4d20fba9e8527f6de3b987fdf9073fa114887355a`, `backend/app/services/provider_runtime.py` `60a9438595d2d4a772e971697b3496b295dd97091f2dcf2d6703e35cf0a73b28`, `backend/app/tasks/data_tasks.py` `4552cd54c6a2cae965f074b39d60cf4c8db56011f6bc3d297c22c5e6c5f6e4fe`, `backend/app/services/data_preparation.py` `665433063a696ae1287cd427cbe334cfb18c163e9e908e67612f8fe5fd6a36f9`, `backend/app/providers/alpaca.py` `65cf8bf722a580c8c74d5562f73e57bc495196544590be8d71a1538b0182b3e6`, and `backend/app/services/market_series.py` `eecfac599f3d6a097f282ba467271a13194f99148ea3ffff339d7c1795b73597`. Root's current assignment is `root-provider-current-native-admission-assignment.json`.

Root's isolated native database has reviewed reference rows and 64 authenticated policy API updates applied; the readback is explicitly **not live-qualified** and records zero provider HTTP. The separate runtime-preparation receipt is also `prepared_only_NOT_LAUNCHABLE`. Do not treat either as production enablement. The only quota-ledger inspection available to this review is the 2026-11-07 14:49Z read-only receipt; it records ledger device/inode `64512/1451610`, zero provider HTTP, and is explicitly **not a current baseline**. Its Alpaca, Twelve Data, FMP and EODHD observations are from Nov 6 or earlier; no recent-window rows means unknown, never zero. Root must recheck the exact existing ledger identity and current baseline immediately before any native operation. Do not reset, replace, seed, or copy the ledger.

## Recommended first native route: Alpaca IEX

The exact22c operation inventory resolves Alpaca `fetch_ohlcv` as reviewed free plan `free-iex`, with history from `2016-01-01`; its quota contract is an account-scoped rolling 200 requests/minute plus the separate usage-probe concurrency lease. The source's price-history chain starts with Alpaca. No Alpaca checkpoint hold exists in `PROVIDER_CHECKPOINT_OPERATION_HOLDS`. The checked-in Alpaca adapter explicitly requests `adjustment=split` for `adjusted=true` and records `split_adjusted/alpaca-split`, compatible with the platform's split-adjusted view; it must remain a distinct series from raw or other provider-adjusted bases. This is the lowest-risk approved route for the requested 2016+ deep history; Twelve Data display permission is not a prerequisite. The underlying history entitlement cites [Alpaca market data documentation](https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api).

Before launch, read back—not blindly rewrite—the native DB rows for `alpaca/account_usage`, `alpaca/price_history`, and, for first-time symbols only, `alpaca/instrument_metadata`. The proposal expects enabled, unpinned rows and the existing reviewed free-IEX entitlement; if a row differs, the supported admin operation is:

```sh
curl -fsS -X PATCH "$BASE/api/v1/providers/policies/alpaca/price_history" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data '{"is_enabled":true,"is_pinned":false}'
```

Apply the same body only to a specifically mismatched `account_usage` or `instrument_metadata` row. Do not alter `quota_contract`, numeric rate limits, entitlement, base priority, or any other provider row. Then inspect `GET /api/v1/providers/policies` and `GET /api/v1/providers/entitlements`; the entitlement must remain `free-iex`, `is_free=true`, with its reviewed 2016 history bound and account quota scope. These authenticated APIs are the existing interface (`backend/app/routers/providers.py`); no direct SQL edits.

For on-demand unknown/stale usage pools, the 22c worker supports a native account-usage prerequisite only when the provider is explicitly allow-listed and the usage policy can report the exact same account pool, unit, limit, and reset semantics as the data policy. It will not substitute a local-zero baseline or reconcile unlike pools. Recommended bounded overlay for this phase:

```dotenv
PROVIDER_ROUTING_ENABLED=true
PROVIDER_REQUEST_DRIVEN_ONLY=true
PROVIDER_FREE_ONLY_CHECKPOINT=true
ALLOW_PAID_PROVIDER_ROUTING=false
DEFAULT_MARKET_DATA_PROVIDER=alpaca
PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED=true
PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS=["alpaca"]
```

Use only the real `app.workers.arq_worker` process. Keep its durable refresh processor available while requests are outstanding. The account-usage flag also registers the existing daily 15:00 UTC refresh, restricted to the explicit Alpaca allowlist; it is an actual provider request under the same admission controls. Do not enable unrelated universe-sync or broad scheduled history sweeps for the bounded canary. The explicit one-provider baseline read, if Root chooses to run it before the canary, is the normal authenticated `POST /api/v1/providers/usage/account/refresh?provider=alpaca`; inspect the result and `GET /api/v1/providers/usage/account?provider=alpaca`. This consumes a real provider request and is Root-owned. Alternatively the normal ensure worker will queue the same guarded prerequisite when an eligible operation has an unknown/stale baseline. A missing/unsupported usage observation remains held.

## Bounded normal-flow qualification

Run only after Root has released the exact isolated runtime and confirmed the current ledger identity, policy readback, network egress, and native baseline path. Keep E2E seed data disabled. Submit through the ordinary authenticated API; no direct service call or fabricated instrument/bar is part of proof.

The prepared native database currently has zero instruments and bars. Before the group request, Root must verify that its normal, reviewed initialization has made the `sp500-sectors` membership and canonical SPY/sector instrument listings available. If not, populate them only through the supported bounded ordinary identity/universe path; an empty group is not a pass, and no manual instrument/bar inserts or E2E seed are appropriate. The request below then ensures history for those existing resolved members.

1. RRG/deep history, one request for all 12 symbols:

```sh
curl -fsS -X POST "$BASE/api/v1/data/ensure" \
  -H "Authorization: Bearer $USER_TOKEN" -H 'Content-Type: application/json' \
  --data '{"target":{"kind":"market_group","group_key":"sp500-sectors"},"timeframe":"MN","adjusted":true,"analysis":{"kind":"rrg","benchmark_symbol":"SPY","lookback":20,"sampling":1,"tail_length":10}}'
```

Persist the returned request ID, close the browser, and poll `GET /api/v1/data/requests/{request_id}`. Verify all 11 sector dependencies plus SPY resolve, all requested monthly dependencies reach at least the server-derived 50 raw observations needed for two 20-point windows plus the 10-point tail, and the final D1/W1/MN selected series have truthful provider/feed/listing/adjustment lineage. `has_pending_work` and per-dependency `retry_at` must reflect actual jobs. A future native reset stays deferred; do not loop-poll or report a partial cache as full depth.

2. Existing/provisional and ordinary ETF selections: submit one normal ensure per exact symbol, for `BWET`, `XHB`, and `IGV`, with target `{kind:"instrument",symbol:"<SYMBOL>"}`, `timeframe:"D1"`, `adjusted:true`, and omit `datasets` so server defaults include applicable identity/profile/history/ETF holdings work. Use the returned durable request IDs after closing the browser. Confirm exact canonical symbol/listing reconciliation, 124 recent bars remain useful while older chunks proceed, and holdings/profile work is independent of a held history source.

3. Cached Massive extension: select a retained instrument with an existing short Massive series, then request deepest history through the same ordinary ensure path. Preserve every old Massive row. Alpaca IEX may form a separate series with its own feed and adjustment provenance; never merge overlapping observations, relabel Massive bars, or splice feeds. Switch the normal default only when one compatible series actually covers the requested interval; otherwise keep the useful selected cache and report partial/held work.

The prepared isolated native DB currently has zero instruments, bars, and refresh jobs, so it cannot yet prove preservation of a prior Massive cache. Run this third case only in a Root-authorized database that already contains the retained Massive series, or after a separate bounded, normal-admission Massive warm-up. Do not copy retained/production bars into the empty target to manufacture this proof.

4. Budgeted stop conditions: stop the canary on any unknown native pool, missing/mismatched usage dimension, provider rate-limit, identity/listing conflict, paid/trial entitlement, unexpected transport error, or repeated quota hold. Record actual calls, native counters/reset, returned statuses and lineage; do not retry beyond the native and application limits. A green cached-only response is not proof of a live extension.

## Other holds: what is stale and what is still real

`PROVIDER_CHECKPOINT_OPERATION_HOLDS` is an operation-routing overlay separate from admin policy, entitlement and native quota. In 22c, its entire value is replaced—not merged—by an explicit JSON environment override. Do not set it to `{}` or remove providers wholesale; that would erase genuine holds such as EODHD fundamentals, Tiingo, Dinari and Bybit. The Alpaca route above needs no checkpoint-map override.

| Provider / operation | Evidence-based disposition | Smallest next action; no current enablement implied |
|---|---|---|
| Twelve Data search/history/latest/discovery | Admin readback deliberately defers all four market-facing operations because Basic display use is unresolved. The previous usage snapshot is stale. | Keep those four disabled/held. Its account-usage operation may remain independently available, but it is not needed for Alpaca. Reconcile account-specific display rights before any market-facing policy change. |
| Marketstack history/latest | Prior dashboard observation is 100/100 calls in a 30-day window opened Oct 15; on Nov 7 that window has not yet elapsed. Free plan is only 1-year history. | Keep held until a current native counter/reset or post-window qualified read establishes capacity. Preserve the 100/month and request cost limits. |
| Marketstack discovery | In addition to the stale hold, 22c diagnostics show operation routing is unconfigured: `MARKETSTACK_DISCOVERY_MAX_PAGE_COST` and `MARKETSTACK_DISCOVERY_COST_EVIDENCE` are missing. | Do not enable discovery until exact per-page cost evidence and a bounded cost are configured; a history entitlement does not authorize discovery. |
| EODHD history/latest/discovery | The `not live-verified` entries are deployment/checkpoint holds, not a claim the vendor forbids these operations. The free account contract is still limited to 20 calls/day and one year of EOD; the Nov 6 usage observation is stale. | Use the existing account-usage endpoint to get a fresh baseline, then qualify one bounded operation through normal admission before removing only that operation's checkpoint hold. Keep `get_instrument_profile` held: free Fundamentals are not entitled. EODHD cannot supply 2016+ depth. |
| FMP history/latest/profile | Current reviewed inventory has no checkpoint hold and marks free-plan operations eligible; its Nov 6 call/bandwidth observations are stale. No advertised earliest-history bound is present. | If used, refresh account usage through the existing bootstrap and rely on a source-specific earliest witness; no guessed IPO/history floor. FMP discovery remains held until `FMP_STOCK_LIST_ENTITLED` is explicitly reviewed/configured. |
| Alpha Vantage operations | The wildcard is an old checkpoint reservation, not a vendor-wide ban. But 22c has no native account-usage bootstrap for it; free allowance is a small 25/day with 5/min local cap, and current daily shared-account headroom is unknown. | Keep the hold until a bounded current allowance is established. Do not treat old local-policy rows as the account's current remaining calls. |
| Nasdaq / CTA directory discovery | Their current `daily headroom exhausted` reasons are dated checkpoint/application reservation states, not immutable vendor prohibitions. Exact operation policy/readiness is separate from price history. | Keep held for this canary. Root may qualify one ordinary bounded directory operation, verify current file/version and per-day app cost, then retire only the stale discovery hold. Do not run universe-wide fanout. |
| Tiingo history/quotes/profile/search | The owner's reviewed plan is CUSTOM, not Starter; the existing free-only evaluator still reports plan mismatch and the old account-usage endpoint returned 403. The documented custom caps do not prove this subscription has zero cost. | Preserve the free-only hold and do not replay `/account/usage`, overwrite the reviewed plan, or enable paid routing. |

Do not use FMP, EODHD, Alpha Vantage, Marketstack, CTA or Nasdaq as a prerequisite for the free Alpaca IEX depth path. Their operation holds should be revisited individually from current evidence, not cleared as a group. The global paid switch remains false and all native/app quota contracts remain unchanged.

## Source and read-only artifacts

- Exact source inspected: `22c31cd3e7f35e361e286ef40576d379aaf44449`.
- Assignment: `.ai/staging-attempts/platform-usability-20261106/root-provider-current-native-admission-assignment.json`.
- Isolated policy preparation/readback: `root-native-authenticated-policy-readback-review.json` (64 authenticated updates, zero native HTTP, not live qualified).
- Runtime prep: `root-native-runtime-preparation-review.json` (prepared only, not launchable).
- Ledger evidence: `root-native-ledger-readiness-readonly-20261107.json` (14:49Z historical snapshot; recheck before execution).
- Per-operation source/config review: `effective-provider-operation-inventory-v2.json`, `provider-activation-proposal-v2.json`, `backend/app/config.py`, `backend/app/services/provider_runtime.py`, `backend/app/tasks/data_tasks.py`, `backend/app/services/data_preparation.py`, and `backend/app/workers/arq_worker.py`.

No source call, service launch, fixture, policy mutation, quota mutation, or production change was made for this handoff. Exact-source CI, Root native execution, combined browser qualification and release remain pending.
