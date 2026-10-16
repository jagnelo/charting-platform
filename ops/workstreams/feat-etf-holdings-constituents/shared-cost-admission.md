# Shared cost admission: ETF consumer contract

Status: ETF-owned integration preparation, not an implemented shared API or an
accepted scope reduction. The original roadmap still requires one shared
aggregate monthly ceiling of 20 EUR/USD-equivalent across active providers.
No subscription, paid probe, deployment, trial, or routing activation is
authorized by this document. The staging coordinator reconciles the producer
contract with the Provider owner before accepting the ETF checkpoint.

## Evidence boundary

Read-only inspection on 2026-10-15 found these existing Provider interfaces:

| Source | Existing behavior | What it does not establish |
| --- | --- | --- |
| `provider_runtime.resolve_provider_chain` | Applies shared entitlement, policy, health and configuration eligibility; excludes non-free entitlements when `ALLOW_PAID_PROVIDER_ROUTING` is false. | A consumer-specific, non-bypassable free-only operation policy or an aggregate recurring-subscription budget. |
| `provider_runtime.execute_provider_call` | Resolves the provider chain, checks operation costs and usage dimensions, then reserves/executes/settles shared calls. Supports exact `provider_name`, instrument, symbol and usage identity. Its `invoke` is synchronous and runs in an executor; the coordinator's current-source review says copied telemetry context is used, but a returned coroutine is not awaited. | ETF capability/adapter wiring, the ETF-owned async compatibility layer, all async issuer transports, or a whole multi-request fetch being one correctly charged request. |
| `provider_quota_coordinator.reserve_provider_quota_async` / `settle_provider_quota_async` | Shared durable quota reservation and settlement. | Currency conversion, monthly subscription activation approval or recurring spend admission. Quota units are not automatically monetary cents. |
| `provider_routing.settle_workload_lease(..., cost_cents=Decimal("0"))` | Adds cost to matching `ProviderQuotaWindow.cost_cents` during successful settlement. | Pre-transport reservation of money, aggregation of subscription commitments, a currency policy or proof that the default zero is the reviewed actual cost. |
| `settings.ALLOW_PAID_PROVIDER_ROUTING = False` | Default excludes reviewed paid plans from normal routing. | Proof that the same reviewed paid plan is excluded when a broad deployment flag is true. The setting is an explicit configurable switch, not an immutable checkpoint boundary. |

The inspected checkout's HEAD was
`65a467b43d7830b0875d9c3ad538e47a06d4a6db`, but its candidate has staged and
unstaged changes. In particular, the current uncommitted test
`test_free_only_checkpoint_boundary_rejects_reviewed_paid_provider` establishes
eligibility with the paid flag true and exclusion with it false. That is a
useful proposed default-config test, not a committed/passing receipt, not
evidence that true still denies, and not the aggregate-budget implementation.
Do not execute, stage, or modify the sibling candidate from this ETF worktree.
Refresh this map against the accepted, green staged producer before coding the
consumer. An interface not found here is not proof that none exists elsewhere.

## Shared admission decision needed before ETF transport

The bridge must obtain a shared decision for the exact canonical fund, publisher,
account scope, operation, entitlement revision and deployment environment.
It must not infer permission from a successful old issuer scrape, `is_free`
alone, a registry entry, a missing cost field, or an unused paid-routing switch.

The producer must identify the existing callable/contract, or supply the shared
repair, covering these semantics. Names below describe evidence fields, not
invented API attributes:

- Explicit allow/deny and a stable reason; link the reviewed source and terms,
  free/paid classification, account and applicable review/expiry evidence.
- Explicit reviewed operation cost and unit. Unknown, null, malformed, negative,
  non-finite or expired monetary/quota evidence is not silently zero.
- Atomic shared reservation before each actual outbound attempt, with durable
  settlement and a stable idempotency identity. Record the real publisher and
  account even when an adapter is reached through an issuer alias or successor.
- Retain request/admission/reservation/settlement references with ETF raw
  artifacts and health outcomes. No per-ETF in-memory budget or second ledger.
- Denial happens before any `httpx`, `requests`, curl, redirect hop, page, retry
  or SEC fallback can leave the process. No alternate transport bypass.
- A content/parse failure is still an attempted request; billable usage follows
  the reviewed publisher contract, not whether a fresh ETF snapshot was stored.
- Cached API/current/historical reads spend no quota or money. An explicitly
  requested refresh/backfill/canary uses the same shared admission boundary.

### Full recurring-budget contract (original roadmap)

Provider owns the aggregate ledger and admission; ETF consumes its decisions.
The shared contract must count active recurring subscriptions plus reviewed
incremental charges without counting the same shared subscription once per
capability, fund, worker or alias. Preserve recorded currency, billing period,
recurring commitment, activation authorization and any normalization evidence.
The approved conversion/equivalence rule must be identified explicitly; neither
this branch nor a test may invent a current exchange rate or treat 20 EUR and
20 USD as an unreviewed interchangeable quantity.

Concurrent Provider/ETF workers cannot reserve beyond the remaining aggregate
ceiling. Restarts cannot erase commitments, reset consumption, or charge the
same idempotent settlement twice. Ambiguous timeout/crash settlements remain
conservatively reserved until reconciled under the producer's documented rule.
An attempted activation or reservation over the approved ceiling denies before
transport. Cancellation does not retrospectively refund a retained contractual
commitment. An approved existing subscription still counts toward the platform
total; already entitled is not synonymous with zero cost.

### Conditional free-only development checkpoint

The central handoff permits proposing a tested free-only checkpoint instead of
building a new budget subsystem now. This is a conditional alternative, not an
automatic ETF acceptance decision and not completion of the full budget goal.

For that alternative, the producer/coordinator must document which exact
operations are reviewed zero-recurring/zero-incremental cost and demonstrate
that the accepted checkpoint cannot select or activate a paid plan. A false
default flag alone is insufficient evidence for the broader claim that a
reviewed paid operation cannot slip through a different caller or flag value.
Either the accepted contract supplies an explicit shared free-only operation
constraint, or checkpoint startup/configuration validation rejects the enabling
configuration and all call paths preserve that boundary. This is a choice for
the shared producer/coordinator, not permission to add a second ETF policy
engine. A reviewed free trial with a later automatic paid commitment cannot be
assumed zero-cost; absent an accepted non-billing proof it remains excluded.

No automatic downgrade to this alternative is made here. The exact excluded
operations, aggregate-budget remainder, owner, continuation acceptance test and
checkpoint acceptance must be recorded. The original 20-unit monthly
requirement remains open until its real shared contract is delivered and tested.

## Producer/consumer integration acceptance matrix

These are required cases after the producer is accepted into green staging;
they are not claimed to pass today. Use real shared runtime and PostgreSQL/Redis
accounting where applicable, with deterministic intercepted issuer transports.

| Case | Required assertion and owner |
| --- | --- |
| Reviewed eligible free operation | Provider admits under the accepted free policy; ETF invokes the exact publisher, records shared references, retains raw response, and accepts only independently validated fresh complete identity-matched holdings. |
| Unreviewed terms, reuse restriction, expired review or missing account evidence | Provider denies; ETF invokes no transport or fallback, stores the exact denial and preserves prior artifacts. Global X's recorded reuse restriction must pass this review, not be ignored because its page is public. |
| Reviewed paid entitlement | Full budget path needs explicit paid activation plus all normal admission checks; free-only checkpoint denies with zero calls. Exercise both flag states or prove the true configuration is refused before any operation. |
| Trial or already-entitled paid subscription | Provider accounts actual commitment and review/expiry; no automatic free classification, activation or billing. ETF has no independent override. |
| Unknown cost, currency, conversion rule or aggregate balance | Deny before network. Zero is accepted only when affirmatively reviewed, never as the `cost_cents` argument's default. |
| Aggregate balance at/below/over boundary | Producer tests exact arithmetic, cross-provider subscription deduplication and atomic concurrent admission; ETF tests both allowed exact-boundary and denied over-boundary outcomes. No guessed currency conversion. |
| Pages, redirects, `requests`/curl retry and SEC fallback | Account each actual request/attempt under its real reviewed quota/cost contract; deny an exhausted second attempt before sending it. Assert no recursive direct-adapter bypass. |
| Failed parse, HTTP error, timeout and uncertain result | Preserve raw/error/admission lineage; settle or retain reservations under the actual provider billing contract. No arbitrary refund, double charge or fresh snapshot. |
| Concurrent workers, restart and duplicate settlement | Producer ledger remains durable/idempotent; ETF replay and backfill cannot reset or duplicate charges. Inspect exact same account scope across consumers. |
| Denied refresh with existing snapshot | ETF retains snapshot and source/knowledge timestamps; marks degraded or stale as appropriate; current-analysis requests reject non-current data. |
| Denied refresh without snapshot | ETF exposes unavailable with exact cause; no synthetic current data. |
| Read-only API, historical inspection and analysis | No admission reservation or network request; retain exact snapshot/canonical identity and point-in-time lineage. |

## Release and remainder record

1. Coordinator/Provider names the selected existing/full/free-only contract and
   exact producer source/tests. ETF records the decision here without editing
   sibling files or weakening its roadmap.
2. Only after Provider is integrated and exact staging CI is green, merge the
   released staging baseline into this clean unfrozen ETF branch. Reconcile the
   actual interface, capability migration, registry and all transport call paths.
3. Execute the matrix against that real combined runtime. Existing persisted
   consumer tests are useful regression evidence, not proof of shared admission.
4. Run focused, full local Docker/browser and exact-source hosted validation.
   Publish an exact clean source receipt, enabled/excluded operations and any
   explicitly accepted remainder. Do not claim this document satisfies EICP3.
5. Keep the full monthly-budget and post-deployment observation requirements
   visible for continuation. No deployment or trial activation follows from a
   development checkpoint or a green test run.

## Central reconciliation update — 2026-10-15

The coordinator's published reconciliation at staging workflow commit
`98f0b888817c461fa00e6e310c5b378b0c4c512f` confirms that the Provider product
baseline has not been released. Its exhaustive/Playwright CI was still running
when the handoff arrived. Provider has been asked to either deliver the shared
aggregate subscription-cost admission contract or demonstrate a tested
free-only checkpoint boundary. ETF has not imported Provider code, merged
staging, or started another local full gate in response.

The exact consumer contract required from Provider is:

1. Given the canonical fund/instrument, actual publisher and account scope,
   environment, concrete operation, entitlement and terms revision, and
   current review/expiry evidence, return a durable allow/deny decision with a
   stable denial reason. Missing or ambiguous identity, account, terms, or
   review evidence denies before transport.
2. For an allow, provide the reviewed cost/quota basis for this operation and
   its actual outbound attempt. Cost, currency, billing period, reset window,
   or quota dimensions that are unknown, stale, malformed, negative, or
   non-finite deny; ETF must not infer a price, exchange rate, quota, or zero
   from an omitted field or settlement default.
3. Apply shared quota and cost admission atomically before every outbound
   attempt. The transport boundary must cover redirects, pagination, retries,
   alternate HTTP clients, and SEC fallback. Each attempt carries a stable
   idempotency key and durable reservation/settlement reference. An exhausted
   next attempt is denied before that request leaves the process. HTTP, timeout,
   or parse failure still records the attempt and follows Provider's reviewed
   billing/uncertain-settlement rule; it does not silently refund or create a
   fresh ETF snapshot.
4. Aggregate recurring commitments once per actual subscription across all
   providers and consumers, retain the source currency and billing period, and
   use only a coordinator-approved currency/equivalence policy. Atomically
   deny new commitments or usage that would exceed the approved 20 EUR/USD-
   equivalent monthly ceiling. Concurrent calls, process restarts, timeouts,
   and duplicate settlement cannot overspend, clear, or double-count it.
5. The current no-paid-activation rule is absolute: ETF cannot activate a
   subscription, start a billable trial, or change entitlement. Existing paid
   commitments must remain visible to the shared aggregate calculation. A
   conditional free-only checkpoint must deny every paid or uncertain-cost
   operation even if a general routing flag is enabled; it must enforce that
   at the shared boundary or reject the unsafe configuration at startup for
   every caller. A false default flag alone does not satisfy this contract.
6. Reads of cached/current/historical ETF data perform no provider request and
   reserve no quota or money. A denied refresh preserves raw artifacts and
   snapshot provenance, stores the decision/reason, and exposes unavailable
   when there is no prior usable snapshot or degraded/stale when one exists.
   It cannot make historical data current or bypass admission through a
   background worker, API, direct adapter, or fallback.

These are semantic requirements, not proposed names or signatures for a new
Provider API. Provider must identify the actual accepted callable and evidence
fields, or identify the shared repair owner and its staged contract. ETF will
adapt only after that producer contract is present in coordinator-released,
green staging. No ETF-owned ledger or guessed per-request price is implied.

### Independent tests still required

The persisted-consumer preparation tests cover snapshot, API, basket, denial,
freshness, and point-in-time behavior. They do not exercise Provider admission.
Once the producer interface is identified, ETF still needs independent
consumer-contract tests against the real shared runtime (with issuer transports
intercepted and call-counted):

- Allowed, reviewed free operation reaches only its exact issuer route and
  stores shared decision/reservation/settlement references with the validated
  raw artifact.
- Missing, expired, ambiguous, or restricted terms; unknown cost/quota/currency;
  denied entitlement; and exhausted budget each produce the exact persisted
  denial and zero calls through every HTTP client, redirect, retry, page,
  worker, and SEC fallback path.
- The accepted free-only boundary denies when the general paid-routing flag is
  true as well as false, or unsafe startup configuration fails before serving
  any operation. No test may activate a paid plan or trial.
- A multi-attempt operation reserves each reviewed attempt; after a denied
  page/redirect/retry reservation there is no corresponding transport call.
  Transport, HTTP, timeout, and parser failures retain raw/error evidence and
  settle or hold the reservation according to Provider's actual contract.
- Concurrent ETF/other-provider admission, process restart, ambiguous
  settlement, and duplicate idempotency replay preserve the same aggregate
  balance. These tests require the real shared database/ledger; mocks alone do
  not establish this behavior.
- A denial with prior data retains source, composition, fetched, and
  knowledge-time lineage and rejects current analysis when stale/degraded; a
  denial without prior data remains unavailable. Cached and historical reads
  assert zero transport and zero reservation.

Provider owns producer-side tests for subscription deduplication, currency
equivalence, exact ceiling arithmetic, atomic concurrent admission,
restart/uncertain-settlement recovery, and enforcement of the paid-activation
boundary. ETF owns its adapter/consumer no-transport and truthful-state tests.
The two suites must run against the same staged runtime for checkpoint
acceptance. None of these new shared-contract tests is claimed implemented or
passing by this documentation update; no tests were run for this documentation
only change.

## Bounded ETF transport-test design — 2026-10-16

This is an ETF-owned test plan, not an API proposal and not evidence that the
Provider implementation is accepted. Provider is correcting its admission and
runner gates and still owns the reserved heavy validation slot. Do not import
its branch, make issuer/SEC live calls, or encode request prices, quota units,
currency conversion, or a cost ceiling interpretation. Implement these tests
only after the coordinator releases the exact green Provider product source and
the ETF branch reconciles that exact synchronized staging baseline.

The key acceptance invariant is about a single actual outbound request, not a
logical holdings refresh: the shared admission executor must make the reviewed
decision before bytes leave the process. Libraries must not auto-follow a
redirect behind the executor. A 403-triggered alternate client, retry, next
page, separate SEC endpoint, or SEC filing download is a new request and needs
its own decision and durable reference. An outer refresh-level allow is never
sufficient to authorize hidden nested traffic.

### Test groups and assertions

1. **Direct issuer artifact through the shared parser** (`PublicCsvHoldingsAdapter.fetch_latest`, currently the httpx-to-requests 403 fallback): with intercepted transports and the real shared runtime, assert each attempt is admitted independently and carries the same canonical ETF/publisher binding plus its concrete operation. Configure an HTTPX 403 followed by a requests retry; prove a denied retry has zero requests.get calls. For redirect responses, prove the client does not silently follow: each hop must be admitted before its target request, and a denied hop leaves that target untouched. Verify only the final validated complete artifact can reach snapshot ingestion.
2. **Concrete adapter subrequests and pagination**: select representative real adapters from the reconciled route-to-operation inventory for product-page discovery, token/session setup, data download, multi-page/category holdings, and alternate-transport retry. Assert the shared executor sees the exact order of attempted requests, one reservation/settlement reference per actual attempt, and no second transport when admission denies. Cover status retry, timeout retry, parse failure, and malformed next-page metadata without permitting an unadmitted continuation. Derive the adapter list from the final source inventory; do not assume a single adapter is representative of all direct client call sites.
3. **Issuer-feed discovery** (`discover_etf_profiles_from_issuer_feed`): discovery GET and any redirect are independently admitted as the reviewed issuer-discovery operation. Denial must happen before the call and before any profile upsert. A successful discovery may only upsert rows from the returned response and cannot silently invoke holdings fetches.
4. **SEC ticker discovery and enrichment** (`discover_etf_profiles_from_sec_fund_tickers`, `enrich_etf_profile_from_sec_fund_tickers`): each separately invoked SEC request is gated under its reviewed SEC operation and account scope. Assert denial causes zero transport and no identifier mutation; cached/read paths make zero calls. This metadata lookup is not a holdings-currentness signal.
5. **SEC reconstruction fallback** (`IssuerCsvHoldingsAdapter._fetch_latest_sec_filing_holdings` plus `etf_holdings_edgar`): exercise submission-index/listing discovery and each candidate filing-document fetch as separate attempts. A rejected issuer route must not turn into an unmetered SEC escape hatch. If a SEC attempt is denied, assert no further filing/page is requested and preserve prior ETF snapshots; if admitted, preserve SEC source-tier/freshness semantics and never label the reconstruction issuer-current. Instrument redirects and candidate-form fallback in these tests too.
6. **ETF-owned compatibility with Provider's synchronous invoke**: after the accepted Provider runtime is staged, integrate to its documented contract rather than requiring Provider to implement ETF's bridge before its checkpoint. The reviewed producer boundary accepts a synchronous `invoke` callback and runs it in an executor with copied telemetry context; it does not await a coroutine returned by that callback. ETF must therefore adapt its async adapter/transport work in its own source so the actual request completes (or raises) exactly once before Provider records a successful (or failed) attempt. Assert a coroutine cannot escape as successful data, be awaited twice, or outlive settlement. Exercise cancellation and timeout so a still-running request cannot be double-settled or retried outside admission. Preserve the shared provider runtime and avoid an outer-refresh-only allow or duplicate ledger.
7. **No-bypass and no-network denial matrix**: for each reached transport family above, use denied fixtures for missing/ambiguous identity, publisher/account/terms review, expired or restricted terms, entitlement denial, unknown cost/quota/currency/reset evidence, exhausted quota/aggregate budget, and disabled/free-only restrictions. Assert the exact shared denial is persisted and all intercepted network call counts remain zero for the denied attempt and all downstream fallbacks. Exercise unsafe global routing configuration both enabled and disabled (or the producer's tested startup rejection); never turn on a paid provider or trial.
8. **Durability and ETF outcome semantics**: against the real shared PostgreSQL/Redis ledger, cover duplicate idempotency replay, restart, concurrent shared admission, timeout/uncertain settlement, and exact actual request attempt references. With prior data, denial must retain raw artifact, source/composition/fetched/knowledge times and yield degraded/stale as appropriate; with no prior data it remains unavailable. Current analysis rejects non-current state. Cached and historical reads assert zero reservation and zero transport.
9. **Inventory anti-regression**: regenerate an AST/source inventory for outbound transports across adapters, refresh, and EDGAR modules. Every reachable request site must either route through the accepted executor or be explicitly classified as non-network/test-only. Fail if a newly added `httpx`, `requests`, curl, or equivalent transport call is absent from the approved inventory. This static guard supplements—not replaces—intercepted runtime call-count tests.

Before consumer implementation, Provider must document its actual synchronous
`invoke` contract honestly, including executor/context behavior, when success or
failure is recorded, and the shared operation/account/admission/reference
fields. Provider does not have to build or accept the ETF async/redirect bridge
before its first product checkpoint. After the coordinator releases its exact
green staging SHA, ETF owns reconciliation of that sync producer contract with
async ETF adapters, all per-attempt transport admission, and exactly-once
completion before settlement. Names above target existing ETF paths, not
required Provider method names. Final ETF tests must use the real staged shared
runtime and intercepted issuer transports; admission mocks alone cannot prove
shared durability, concurrency, request accounting, or safe cancellation.

### Central review correction — async consumer ownership — 2026-10-16

The coordinator's read-only review of ETF commit `90b2f12cf` clarified the
dependency boundary: `execute_provider_call` has a synchronous `invoke`, runs it
through `run_in_executor` with copied telemetry context, and does not await a
coroutine returned by `invoke`. Provider must document this existing producer
behavior as part of its checkpoint contract, but does not need to deliver
ETF-specific async adapters, redirects, or transport wiring before Provider's
own checkpoint can be accepted. That compatibility integration is an ETF-owned
post-release task. Test it against the actual green staged runtime with exact
once completion, each outbound attempt admitted/settled, denial-before-call,
and cancellation/timeout accounting. This correction avoids making Provider's
first checkpoint circular while retaining the full ETF acceptance requirement.

## Offline real-path binding inventory — 2026-10-16

This mapping is derived only from the ETF branch's adapter/refresh/EDGAR source,
provider audit ledger, settings, retained local validation, and existing
consumer tests. It is the bridge's post-staging input map, not a Provider API
contract, terms audit, permission claim, or runtime acceptance. The "operation"
labels below are semantic distinctions for mapping to the accepted Provider
operation catalogue later; they are not newly asserted Provider enum values.

| Existing request family and ETF path | Identity/publisher/operation context available per request | Current missing binding / admission consequence |
| --- | --- | --- |
| Registered native adapter: direct latest/dated artifact, usually `PublicCsvHoldingsAdapter.fetch_latest` / `fetch_for_date` called by an issuer adapter | Outer refresh has `ETFProfile` and linked canonical `Instrument`; adapter receives `adapter_key`, `source_provider`, `symbol`, optional `issuer_product_id`, identifiers and resolved URL. A request can capture exact URL host, method, transport and latest-vs-dated action. | The HTTP call itself does not receive canonical instrument ID, provider account ID, reviewed terms/revision, or a shared operation/admission reference. `source_provider`/`adapter_key` are code provenance labels, not proof of the legal publisher or zero-cost entitlement for every destination host/CDN. No per-attempt shared reservation exists here. |
| Issuer product-page discovery followed by holdings artifact (e.g. `IssuerCsvHoldingsAdapter.fetch_latest` → `_discover_source_url_from_product_page` → artifact fetch) | Same fund symbol/product/adapter context exists at the adapter call; product-page host and final artifact host are separately observable. The logical actions differ: issuer route discovery vs holdings artifact fetch. | Each page, redirect and final download is currently independently executed with no shared admission binding. The URL may point to an issuer, API host, CDN or file host; do not collapse those hosts into the `adapter_key` without publisher review. Account scope is absent. |
| Provider-specific API/token/product-ID/multi-request adapters in `etf_holdings_adapters.py` | Methods commonly retain the current symbol and adapter instance/config; each request URL reveals destination host. Existing code may make lookup, token/session, holdings, category/page, or retry requests in one logical fetch. | There is no common per-request context object or central transport wrapper. The exact provider-account/credential scope, operation cost/quota dimension, and call ordering vary by adapter and must be recovered from each native route before bridge wiring. A whole-fetch allow would miss these attempts. |
| Transport fallback: HTTPX → `requests` after selected 403s, adapter-specific `requests` paths, and the retained curl subprocess path | Same initiating adapter/symbol/source URL is generally in local method scope; the chosen client/transport and actual target host can be recorded separately. | Every retry/client switch and redirect hop is a distinct attempt. Current automatic redirect options can hide hops; there is no shared attempt ID, account binding, reservation, or settlement in these paths. A retry is not free merely because it reuses the same URL. |
| Issuer ETF-list discovery: `discover_etf_profiles_from_issuer_feed` | Caller supplies `adapter_key` and `source_url`; registered adapter supplies its `source_provider`. Response rows introduce individual symbol/product identity only after the feed request completes. Semantic operation: issuer-universe discovery. | Before the response, this is a publisher-scoped universe operation rather than one known-fund request. The current call has no provider account, reviewed feed terms, quota or admission reference; it follows redirects automatically. Do not invent one symbol binding for the entire feed. |
| SEC fund-ticker discovery/enrichment: `discover_etf_profiles_from_sec_fund_tickers` and `enrich_etf_profile_from_sec_fund_tickers` | Fixed SEC source URL and SEC User-Agent; enrichment additionally has a target canonical profile/symbol, while whole-map discovery has no single ETF identity. Semantic operations: SEC fund-map discovery vs profile identifier enrichment. | Current requests are not shared-admitted and follow redirects automatically. SEC public accessibility/User-Agent use does not establish a per-request quota, commercial reuse or raw-data retention permission for this product. Account identity is not represented. |
| SEC filing fallback: `IssuerCsvHoldingsAdapter._fetch_latest_sec_filing_holdings` → `etf_holdings_edgar.discover_holdings_filings` → N-PORT/legacy document fetch | Starting adapter/profile supplies ETF symbol and SEC CIK/series/class identifiers; filing attempts add accession, form and report date. Actual publisher/source host is SEC (`data.sec.gov` or `www.sec.gov`); semantic operations are submissions index, archived submissions file, and individual filing document. The result is explicitly marked SEC/filing provenance. | Each index/archive/document request and redirect is currently a separate ungoverned HTTP call. Shared account/admission IDs and current SEC quota/terms/retention review are absent from this ETF code/evidence. An issuer denial/error must not create an unmetered SEC bypass. SEC reconstruction remains non-issuer-current. |
| Local `data:` fixture parsing and cached/current/historical/PIT reads | A `data:` URL is parsed locally; persisted reads use existing ETF profile/snapshot/artifact identity and knowledge/composition timestamps. | These are not provider requests: they must create zero shared reservation and zero transport. Preserve point-in-time selection and historical lineage; do not route a read through refresh or relabel old data as current. |

Fallback classification is symbol/adapter evidence, not a transport guarantee.
Audited fallback adapters generally inherit `IssuerCsvHoldingsAdapter`; when a
complete issuer route is absent they may either stop before transport because
the probe is not ready, or use the configured SEC filing path when sufficient
SEC identity is present. Some adapter classes also contain narrow symbol-scoped
routes (for example Pacific AM's GEME path) that must not promote another
symbol/provider identity. Therefore the bridge must take the actual resolved
symbol, adapter, source URL and provenance for each attempt; neither a
fallback-only label nor an SEC-capable probe promises an executable or complete
holdings result.

### Evidence status: source facts versus application limits

| Fact class | Reviewed in existing ETF context | Still unknown, held, or explicitly not implied |
| --- | --- | --- |
| Monetary cost | The issuer adapter config exposes `source_access` and optional free-text `terms_note`; some prior issuer route tests used unauthenticated public responses. The retained `provider-audit.yaml` records quoted USD candidate prices (FundFacts commercial Pro US$49/month, StockFit US$39/month, FMP US$149/month, EODHD US$41.99/month) and records individual candidate dispositions; these historical ledger values are not refreshed or recalculated here. SecuritiesDB and DealCharts were observed as free candidates for specific pages, but their ledger entries say quota and commercial terms were not established. | No uniform reviewed zero-monetary-cost agreement for every enabled issuer host, API, CDN, redirect target, or retry. A public URL, `issuer_public_holdings_file`, a successful anonymous GET, or `published_monthly_cost_usd: 0` for one candidate does not prove no billable access, no future charge, or entitlement. No FX/equivalence calculation is made here; provider/currency values and approval remain authoritative inputs, not inferred. No paid source, credential or trial is activated. |
| Terms/entitlement | The code can persist `source_access`, `terms_note`, issuer/source labels and route provenance. The provider audit contains symbol/candidate-specific terms findings (including automated-use restrictions, personal/evaluation-only tiers, paid gates, and unresolved redistribution for listed vendors). | `terms_note` is nullable descriptive metadata, not an approved legal review. No blanket commercial collection, reuse, display, redistribution, or retention permission follows from public accessibility. Exact terms revision, reuse right, account/credential owner and review expiry are not common per-request bindings. Unreviewed/held routes stay disabled. |
| Quota/rate limits | The ETF code supplies operational bounds: HTTP timeout 20s; capability canary disabled by default, max 20 symbols, 60s canary timeout, failure threshold 3/cooldown 3600s; classification maintenance disabled by default, max 50 profiles and 32 enrichments/profile; SEC backfill disabled by default, max 50 profiles and 20 filings/ETF. SEC EDGAR helpers also default to max 20 candidate filings. | These are application workload/safety caps, not publisher quotas, per-request units, reset windows, or proof of zero cost. They do not bound all redirects/retries: auto-followed redirects are hidden, and archive metadata can cause requests before 20 qualifying filings are found. No exact issuer/SEC quota or account baseline is established by this inventory. |
| Storage/retention | Existing code stores raw payload text/JSON, source URL/identifier, content hash, composition/as-of/published/fetched dates, parser version and legal metadata in `ETFHoldingsRawArtifact`, linked from snapshots. The app exposes historical snapshots and maintains source/knowledge-time lineage. Existing consumer tests cover cached/historical/PIT semantics. | This demonstrates application persistence, not publisher permission or an approved retention duration. No per-publisher storage/redistribution right, purge schedule, expiry, or source-specific retention window is established here. Preserve retained records and historical/PIT behavior; do not clean up data as part of this preparation. |

### Binding contract to consume after exact green staging

For each actual outbound attempt, the ETF bridge should construct context from
the owning `ETFProfile`/canonical `Instrument` and current adapter: canonical
instrument/profile identity; issuer product ID and provider symbol; stable
adapter/provider label; actual request host and reviewed publisher/account
scope; semantic operation (discovery, current/dated artifact, API lookup/page,
SEC map/index/archive/document); transport and attempt number; and an
idempotency/admission reference returned by the accepted shared runtime. The
shared runtime must supply—not ETF code invent—the reviewed entitlement, exact
quota/cost basis, terms revision/review state, and reservation/settlement
semantics. Missing publisher/account/terms/quota/cost evidence denies before
that attempt. Provider's producer contract remains its documented synchronous
invoke; ETF owns adapting async transports after release. Keep discovery as a
separate universe operation, SEC as a distinct degraded/non-current source,
and cached/historical/PIT reads entirely off the network path.

This family-level map is intentionally not the full 496-publisher terms audit
or a route-by-route release approval. The exhaustive 140-key fallback audit,
15 Tier-0/156 Tier-1 priorities and all remaining symbol-specific free-first
work remain open on the existing roadmap.

### Common repair baseline consumed — 2026-10-15 21:40Z

The exact synchronized common repair baseline `82d881e76be8de538abb6ec5c454d96afe0ee56a`
is merged into the ETF branch. This release repairs shared workstation behavior;
it does not contain an accepted Provider product checkpoint or the
`ETF_HOLDINGS` producer contract. Provider owns the first heavy local validation
slot, and the actual ETF adapter/capability/async transport bridge remains gated
on Provider's reviewed green product contract. The complete admission matrix
above remains required and unchanged.

The coordinator's current semantic boundary remains: a general routing flag
whose default is false is not proof that every caller rejects unsafe
`paid=true`. Before any real page request, retry, redirect, or SEC fallback, an
unknown/paid cost, quota, entitlement, account, or terms decision must fail
closed at the shared admission boundary. ETF must not add a second ledger or
infer that omitted cost is zero. Previously retained ETF identity and mixed
asset-kind evidence (including futures and cash rows) remains required when
mapping shared canonical identities; ticker-like strings must never synthesize
equity identities. Neither this baseline merge nor bounded unit/type checks
constitutes EICP3/ETF product acceptance.

### Policy onboarding ownership clarification — 2026-10-16

The coordinator's review of `949a013` clarifies the producer/consumer boundary:
Provider supplies the generic reviewed-policy, admission, and durable-ledger
contract. Provider's first checkpoint is not contingent on reviewing or
onboarding every ETF publisher. After the exact green Provider release, ETF
owns binding its actual issuer, host, account, and semantic operation contexts
to that shared runtime, and onboarding ETF policies only when supported by
reviewed evidence. The shared runtime remains the sole policy/admission ledger;
ETF must not invent cost, quota, terms, account, or retention values.

For each ETF operation, absent or inadequate publisher/account/terms/quota/cost
evidence remains denied and non-routable until reviewed; this fail-closed rule
does not make the all-publisher audit an omnibus prerequisite for Provider's
first merge. The full symbol-level and issuer/publisher evidence roadmap stays
open and must be completed in ETF-owned continuation. Cached, historical, and
point-in-time reads remain network- and reservation-free. This clarification
does not accept either source, authorize live requests, or reduce ETF criteria.
