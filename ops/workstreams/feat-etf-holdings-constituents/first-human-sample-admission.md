# First-human ETF sample: source-backed SPY route recipe

Status: read-only preparation from exact accepted baseline
`f04fb2a26c6363c6090e76c2658cfcfe7adabf61` and retained local evidence. This
recipe makes no assumptions about post-f04 code changes. It is not a
live-source check, a route approval, a seeded sample, or evidence that SPY is
currently usable in the new private m920q target. No issuer, Provider, or SEC
request was made while preparing it.

## Candidate and evidence choice

Use SPY through the native SPDR route as the first candidate. It is the more
direct source path than RSP in this codebase: `KNOWN_ETF_PROVIDER_METADATA_BY_SYMBOL`
explicitly maps SPY to the `spdr` adapter, while RSP is routed through the
Invesco adapter. `SpdrHoldingsAdapter` constructs the fund-scoped workbook URL:

`https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx`

The adapter parses the workbook's fund ticker and `Holdings`/as-of preamble,
checks that the returned ticker equals the requested `SPY`, requires a known
workbook schema and nonempty holdings rows, and preserves the workbook rows and
composition date in the fetch result. The deterministic adapter test at
`backend/tests/unit/services/test_etf_holdings_adapters.py::test_spdr_adapter_parses_fund_scoped_workbook_and_preserves_row_types`
uses a mocked/synthetic workbook. That fixture proves parser behavior only; it
is not an issuer artifact and must not be imported or cited as a live sample.

I found no provenance-verifiable real SPY or RSP issuer response body in the
reviewed local test/evidence paths suitable for an honest dated import. The
new target has no seeded/borrowed holdings data. Therefore the defensible
first-sample path is a future, explicitly reviewed, single-symbol native SPY
fetch, not an invented historical import. The route/template and tests do not
prove that the current publisher page is reachable, that the issuer still
serves the workbook, that its terms allow this use, or that the route is
presently admitted.

## Required offline setup and review before any request

1. Apply the accepted migrations and prepare the canonical SPY instrument and
   linked ETF profile without fetching data. Verify the committed instrument
   identity is SPY and the profile's curated route is `adapter_key=spdr`; do
   not infer an issuer/account identity from ticker text alone. The admin
   `/{symbol}/probe-adapter` path is a static route probe; it returns the
   adapter URL without fetching the workbook. Do not use the bootstrap path for
   this first sample: `bootstrap_etf_holdings_profile` opportunistically
   attempts SEC fund-ticker enrichment when the profile has no SEC CIK, which
   is outside this sample's issuer-only scope.
2. Independently review and retain primary-source evidence for this exact
   issuer/product, the `www.ssga.com` HTTPS host, the actual holdings operation,
   permitted use/display/retention, and whether the disclosure is complete and
   dated. Do not treat a public URL or an old parser fixture as permission.
3. In the shared Provider runtime, create/approve only evidence-backed records:
   active `DataSource(name="spdr")`; enabled `ProviderPolicy` for
   `ProviderCapability.ETF_HOLDINGS`; a valid quota contract and explicit,
   reviewed cost for `fetch_etf_holdings_latest` (plus every quota-dimension
   cost required by that policy); a free source still has a positive reviewed
   request/quota cost unless the actual contract says otherwise. Add a current
   `ProviderEntitlement` with the reviewed terms, environment, and use
   permissions. Configure the provider's
   non-secret account scope for the policy's quota scope and bind the same
   resolved scope in `DataSource.config.etf_holdings_review.account_scope`.
   Review metadata must include `https_hosts` containing exactly the reviewed
   host and an `operations.fetch_etf_holdings_latest` record with meaningful,
   nonempty `evidence_source`, `evidence_version`, and `reviewed_at`. Include
   any separately reviewed publisher-owned redirect host needed by the route;
   each hop is independently checked against the host review. These are actual
   runtime gates, not suggested data to fill with guesses.
4. Verify the Provider-owned aggregate budget is itself reviewed/allowed and
   there is an active, verified-free recurring-cost commitment for the same
   provider, environment, and account-scope digest. The ETF bridge admits only
   an active commitment whose amount and monthly equivalent are zero and whose
   post-trial amount is absent. Do not create a zero commitment unless issuer
   terms and the applicable quota/cost facts actually establish it. No paid
   plan, billable trial, or activation is authorized.
5. Verify current Provider health/operation holds, quota baseline and remaining
   allowance from the canonical Provider runtime. Missing, unknown, expired,
   denied, or exhausted policy state means **stop before transport**; do not
   retry through SEC, another client, or a fallback.

The bridge validates committed profile/instrument identity, exact provider and
adapter bindings, the enabled capability, the reviewed HTTPS host and
operation, entitlement, account-scope match, and verified-free shared
commitment before it calls `execute_provider_call`. Each HTTP attempt, including
each redirect hop, is admitted and settled separately through that shared
runtime. SPDR requests redirects; the bridge follows them itself and defaults
to at most 20 redirects, so a single sample run can involve up to 21 separately
admitted physical requests. Preserve the configured fetch timeout and record
actual attempt/log/reservation/settlement lineage; do not describe this as one
quota unit unless the reviewed Provider contract says so.

### Canonical profile binding and shared-runtime bootstrap finding

The publisher alias does **not** require a product-source change if an
authorized operator completes a genuine review. Accepted f04 exposes the
admin-only `PATCH /api/v1/etf-holdings/{symbol}/profile` route. Its
`ETFProfileUpdateRequest` accepts both `provider_aliases` and `legal_metadata`;
the handler passes those to `ensure_etf_profile`, flushes, and the normal
request-scoped `get_db` commits on successful completion. `ensure_etf_profile`
stores the supplied aliases and honors `holdings_adapter` for adapter
selection. Therefore an evidence-backed admin update can persist
`holdings_source_provider: "spdr"` (or the bridge's supported
`source_provider: "spdr"`) alongside `holdings_adapter: "spdr"`, with the
review record retained in `legal_metadata`. The evidence must identify the
actual reviewed publisher/product/route; the endpoint accepts generic JSON
and does not validate the truth or sufficiency of that evidence. Merely
submitting the alias, an unsubstantiated legal-metadata note, or a raw
one-off database edit is not a review and does not make the route admitted.
No such profile update or review has been made for the new target. In the
current local ETF continuation (not in accepted f04), the canonical SPDR symbol
route metadata now also carries `holdings_source_provider: "spdr"` beside
`holdings_adapter: "spdr"`; `_apply_known_route_metadata` persists both while
retaining unrelated aliases, and focused tests cover that mapping. This is the
source-owned canonical identity binding, not external terms or quota evidence,
not a `DataSource` registration, and not route admission. It removes the need
for a one-off profile alias edit when normal canonical route hydration is used;
the independent shared-runtime bootstrap gap below still prevents admission.

There is a separate, concrete bootstrap gap in the accepted f04 management
surface. The ETF SPY metadata seeds only `holdings_adapter: "spdr"`. The
generic `seed_provider_runtime` enumerates `supported_provider_names()` from
`backend/app/providers/registry.py`; `spdr` is an ETF holdings adapter, not an
entry in that generic provider registry. The seed therefore does not create
`DataSource(name="spdr")` or its `ETF_HOLDINGS` policy/entitlement. The
Provider admin APIs can inspect providers and PATCH an *existing*
`/api/v1/providers/policies/{provider_name}/{capability}` or
`/api/v1/providers/entitlements/{provider_name}/{capability}` row, but do not
create an ETF publisher source or those initial rows. I found no accepted f04
admin endpoint to create that source or write its
`DataSource.config.etf_holdings_review` host/operation/account evidence.
Consequently those rows/review fields need an authorized, documented
provisioning path outside the currently exposed generic seed/PATCH flow, or a
future supported management capability; do not improvise them with a
one-off database alias or infer them from the adapter catalog.

The recurring-cost management routes do exist: admin-only
`PUT /api/v1/market-data/recurring-costs/budget` records the aggregate ceiling
with evidence, and `POST /api/v1/market-data/recurring-costs/commitments`
records/admit a commitment for an existing `data_source_id`. The latter
explicitly does not authorize provider activation. These routes do not fill
the missing SPDR source/policy/entitlement/review bootstrap, and no budget,
commitment, entitlement, policy, account scope, or publisher route was
created or activated during this preparation. Until the source, all reviewed
records, and the canonical SPY profile binding actually exist and pass the
bridge checks, the correct outcome remains zero transport and no sample.

### Exact f04 profile-identity path versus Provider admission

The accepted f04 source confirms that an authorized admin can persist the
profile-side identity without a product-source change. `ETFProfileUpdateRequest`
accepts generic `provider_aliases` and `legal_metadata`; admin-only
`PATCH /api/v1/etf-holdings/SPY/profile` passes both to `ensure_etf_profile`,
which stores non-null values. For SPY, a reviewed update must submit the
complete alias set together, at minimum
`{"holdings_adapter":"spdr","holdings_source_provider":"spdr"}`
(the bridge also recognizes `source_provider` as the identity key). The
associated `legal_metadata` should retain the actual source/version, review
time, product/issuer and route decision. The endpoint does not validate those
claims or enforce a review schema: it is a supported admin configuration
mechanism, not self-authenticating evidence. It is legitimate only when the
admin's retained metadata reflects a real review; typing an alias into this
endpoint or inserting the same alias directly into a row just to pass the
identity comparison is not publisher verification. The accepted f04 SPY
catalog metadata itself supplies `holdings_adapter=spdr`, but not the
publisher identity alias; the identity addition therefore needs this evidenced
profile update (or a later canonical source change).

That profile update satisfies only the bridge's committed-profile identity
check. It does **not** by itself admit transport. In accepted f04,
`seed_provider_runtime` creates generic `DataSource`, policy and entitlement
rows only by iterating `supported_provider_names()` from the generic Provider
registry. SPDR is registered as an ETF holdings adapter and curated ETF route,
not as a generic Provider registry entry, so normal seeding does not create
`DataSource(name="spdr")` or its `ETF_HOLDINGS` policy/entitlement. The
admin Provider PATCH routes update existing rows and return not-found when
the SPDR source/policy/entitlement is absent; they are not creation paths.
The recurring-cost `POST /api/v1/market-data/recurring-costs/commitments`
can create/admit a commitment only after an existing `data_source_id` is
available. The budget `PUT` can record reviewed aggregate-budget evidence.
Neither creates SPDR's source, capability rows, account binding, nor the
bridge-required `DataSource.config.etf_holdings_review` host/operation review.
No accepted f04 admin management path was found to create that SPDR source,
policy, entitlement, or review-config record. Thus: profile identity has a
supported evidence-bearing admin path; complete shared Provider admission
still has a concrete provisioning/management gap. No such profile update,
review, Provider record, budget, or commitment was made in this preparation.

### Accepted-f04 provisioning design notes and local-delta boundary

The following design notes describe the accepted f04 baseline, where this API
did not exist. The current ETF worktree now has an uncommitted, unaccepted
admin-only first-create endpoint; it is not evidence that a real SPDR record
has been provisioned. The endpoint's exact validation, disabled-policy
behavior, and remaining evidence/DB-runtime limits are recorded in the current
workstream handoff/session, not attributed to accepted f04.

Any publisher-provisioning implementation must stay separate from generic
API-provider registration: SPDR is an ETF adapter, and adding it to the generic
registry would imply unrelated provider capabilities. It must be admin-only
and source-scoped, and must not infer capabilities, quotas, cost, terms, hosts,
operations, or account identity from the adapter catalog or SPY profile. The
current local first-create route rejects an existing source rather than
overwriting it; it is not an idempotent update path.

The current SQLAlchemy defaults make explicit quarantine essential: a new
`DataSource.is_active` defaults true, `ProviderPolicy.is_enabled` defaults
true, and `ProviderEntitlement.is_free` defaults true. A future creator must
not rely on those defaults. Before review is complete, leave the source
inactive and its `ETF_HOLDINGS` policy disabled; do not create an entitlement
that could be read as verified-free. Keep missing quota dimensions and
`quota_verified_at` unresolved until a complete evidence-backed contract is
recorded. Only create/update the entitlement and `DataSource.config.etf_holdings_review`
from the reviewed evidence, retaining entitlement revisions; do not turn a
successful profile PATCH into Provider review or activation.

After a real `DataSource` exists, the existing admin policy/entitlement PATCH
endpoints can update its corresponding existing rows, the recurring-cost
budget `PUT` can record reviewed aggregate evidence, and the commitments `POST`
can record an evidence-backed commitment for that source and billing scope.
Those endpoints are not a complete provisioning workflow: the first two
cannot create missing rows, and the cost endpoints cannot supply issuer terms,
host/operation review, quota evidence, or account-scope configuration. A
future implementation should either add an explicitly fail-closed, audited
publisher-provisioning path for those missing records or document an existing
authorized operational provisioning mechanism before claiming the gap closed.
Any activation remains a distinct, later reviewed act after every bridge gate
is satisfied; this proposal creates no authorization to activate or fetch.

Static follow-through on the accepted f04 runtime found one additional required
row: `resolve_provider_chain` inner-joins `ProviderHealthState` for every
candidate. `seed_provider_runtime` creates health rows inside its generic
registry/capability loop, but SPDR is absent from that registry, so manually
creating only its `DataSource`, `ProviderPolicy`, and `ProviderEntitlement`
would still leave the ETF publisher absent from the shared resolver. The
future ETF-specific provisioning/seed path must create the shared health row
for the same source and `ETF_HOLDINGS` capability without recording a success
that never happened; policy must remain disabled until the independent
  evidence and explicit activation gates pass. The local provisioning endpoint
  now creates a neutral row as part of its transaction, but no such row has
  actually been created in a runtime. This is a source-derived runtime
  requirement, not a health observation.

## Bounded first request and interpretation

Only after the above review and explicit operator authorization, invoke the
existing single-symbol service path with `symbols=["SPY"]`, `max_symbols=1`,
and a finite canary timeout (the task/service default is 60 seconds), using
`run_etf_holdings_capability_canaries`; do not turn on the scheduled default
canary sweep or the broad `refresh_all_known_etf_holdings` task. This canary
calls the latest native route directly and does not invoke SEC fallback. The
current scheduled canary is disabled by default and its configured symbol set
does not include SPY; leave defaults unchanged. A cancellation/timeout still
has to let an admitted Provider attempt settle and retain its evidence.

Accept a returned artifact only if its raw body, actual final URL/redirect
attempts, source identity, parser/schema, issuer composition date, request
lineage, and completeness checks are retained and reviewable. The workbook's
as-of date is the date of the holdings disclosure; it is not the current wall
date and must not be rewritten. A successful HTTP response alone is not a
successful holdings snapshot. Current capability additionally requires the
persisted snapshot to pass the application's freshness, identity,
completeness, and route-health checks. A missing snapshot remains unknown; a
prior expired snapshot is stale/last-known and is not usable for current
analysis. Cached and historical/PIT reads remain network- and quota-free.

SPY fund identity validation is separate from constituent resolution. The
parser classifies equity, derivative, and cash rows; cash/options may
intentionally have no equity symbol. Ticker/CUSIP matching can leave legitimate
equity rows unresolved. Retain unresolved rows and counts; do not fabricate
constituent identities, drop cash/derivatives to inflate resolution, or treat
the ETF workbook's SPY preamble as proof that every holding resolved.

## Source pointers and limits

- `backend/app/services/etf_holdings_adapters.py`: SPY curated route metadata
  and `SpdrHoldingsAdapter` workbook URL/parser.
- `backend/app/services/etf_holdings_provider_bridge.py`:
  `ProviderBackedHTTPXClient`, `_review_attempt_context`, and
  `execute_etf_holdings_request_attempt` admission/redirect boundary.
- `backend/app/services/etf_holdings_refresh.py`: `probe_etf_holdings_adapter_route`,
  `bootstrap_etf_holdings_profile`, `_refresh_adapter_route`, and the bounded
  `run_etf_holdings_capability_canaries` service.
- `backend/app/services/etf_holdings_capability.py`: persisted capability,
  identity, freshness, and current-vs-last-known interpretation.

This recipe does not claim that any of these shared review records exist in the
new private target, that the SPY route has been recently live-tested, or that a
first-human sample has been accepted. RSP remains a possible later candidate,
but no better retained RSP artifact or simpler verified route was established
in this read-only pass.

## Coordinator follow-up: canonical SPY identity versus shared registration

The accepted f04 profile route is a legitimate way to persist SPY's reviewed
publisher identity; it is not necessary to add product code merely to set the
profile binding. In immutable f04, the admin-only
`PATCH /api/v1/etf-holdings/{symbol}/profile` route (router
`backend/app/routers/etf_holdings.py`, `update_etf_profile`, near line 986)
accepts `ETFProfileUpdateRequest.provider_aliases` and `legal_metadata`, then
passes them to `ensure_etf_profile`. That service stores each non-`None` value
on the profile. A properly reviewed SPY request can therefore bind the
existing adapter with `holdings_adapter: "spdr"` and publisher identity with
`holdings_source_provider: "spdr"` (the bridge also accepts
`source_provider: "spdr"`), while retaining actual source/version/review-time
evidence in `legal_metadata`. Since the service assigns the supplied
dictionaries rather than merging them, an operator must preserve any existing
approved aliases and legal metadata in the submitted full values. The handler
does not authenticate those claims or enforce an evidence schema: admin access
plus a typed alias is not review evidence. Only a genuine source/product/route
review recorded through this supported path makes the profile binding
defensible; a raw database alias inserted just to satisfy the comparison does
not. No such request or profile change was made here.

SPDR's accepted f04 runtime registration is ETF-specific, not generic Provider
registration. `backend/app/services/etf_holdings_adapters.py` exposes the
`spdr` adapter through `get_holdings_adapter` and the SPY curated route
metadata. By contrast, `backend/app/services/provider_runtime.py` seeds
`DataSource`, policy, entitlement, and health rows by iterating
`supported_provider_names()` from `backend/app/providers/registry.py`; SPDR is
not in that generic registry. `resolve_provider_chain` requires matching
`DataSource`, `ProviderPolicy`, `ProviderEntitlement`, and
`ProviderHealthState` rows and a supplied ETF adapter. Thus f04 knows how to
execute the ETF adapter but normal generic seeding does not register SPDR in
the shared `ETF_HOLDINGS` admission tables or supply its health row.

The existing admin management surface is partial, not a publisher-onboarding
path:

- `PATCH /api/v1/providers/policies/{provider_name}/{capability}` and
  `PATCH /api/v1/providers/entitlements/{provider_name}/{capability}` update
  rows only after lookup; each returns not-found when the SPDR source or its
  capability row is absent. They cannot create those rows.
- `PUT /api/v1/market-data/recurring-costs/budget` records a reviewed aggregate
  ceiling. `POST /api/v1/market-data/recurring-costs/commitments` can create
  and evaluate an evidence-backed commitment, including a verified-free one,
  but requires an existing `data_source_id`; it does not activate transport.
- I found no accepted-f04 admin route to create `DataSource(name="spdr")`, its
  initial `ETF_HOLDINGS` policy or entitlement, its neutral health row, or the
  bridge's `DataSource.config.etf_holdings_review` host/operation/account
  record. Nor does the profile PATCH create any of those shared Provider
  records.

Conclusion: the **profile identity binding has a supported admin configuration
path that can retain review evidence** and does not itself require a code
change. The **shared Publisher/Provider admission bootstrap remains a concrete f04
management gap**; only the later cost commitment has an existing create path,
and that path depends on the missing source record. No policy, entitlement,
commitment, review, account scope, health observation, or route activation was
created. Until the missing shared records are provisioned through a legitimate
authorized mechanism and every independent admission check passes, SPY remains
unadmitted and the sample recipe remains prospective.

### Evidence status for this identity binding

This source review establishes that f04 can persist a reviewed identity; it
does not itself supply the external evidence needed to make that review. The
adapter's curated `holdings_adapter=spdr` mapping and XLSX URL are application
configuration, not proof of current issuer ownership, reachability, use/retention
rights, or a verified-free plan. No new primary-source evidence was fetched or
found in the retained local sample material during this read-only check. Thus an
administrator may use the profile PATCH only after independently obtaining and
retaining genuine source/product/route evidence in the profile's `legal_metadata`
alongside the complete alias dictionary. The endpoint does not validate that
metadata, and this profile-side record alone still cannot satisfy shared
Provider admission; absent the separate SPDR source/policy/entitlement/health
and `etf_holdings_review` provisioning, transport remains denied.

### Current worktree-only provisioning implementation (not accepted f04)

The current ETF source delta adds admin-only `POST
/api/v1/providers/etf-publishers`. It permits only a registered native ETF
adapter, requires configured account-scope agreement, accepted ETF operations,
complete shared quota dimensions and explicit operation costs, and retains
publisher, quota, entitlement, HTTPS-host, operation, and account review
metadata in the shared Provider rows. It creates the source as active but the
`ETF_HOLDINGS` policy explicitly disabled, with neutral zero/no-observation
health and an entitlement revision; it creates no aggregate budget or
recurring commitment. It refuses to overwrite an existing source and returns
`routable=false`. The endpoint trusts admin-supplied attestations: nonblank
evidence fields are not proof that the cited publisher material or terms are
true. No actual request or runtime provisioning was performed. Synthetic
SQLite router tests prove only validation/persistence shape and the disabled
policy invariant, not production PostgreSQL/Redis admission or evidence
authenticity. Therefore this local delta is not in f04, does not admit SPY,
and does not close the sample's source-evidence, account/budget, activation,
live-evidence, full-profile, or roadmap requirements.

### f04 profile-binding and shared-registration clarification (read-only, 2026-10-23)

The accepted f04 tree supports a canonical admin profile write for the identity
binding itself: `PATCH /api/v1/etf-holdings/{symbol}/profile` requires
`require_admin`; `ETFProfileUpdateRequest` accepts both `provider_aliases` and
`legal_metadata`, and `update_etf_profile` passes both to
`ensure_etf_profile`. The persisted alias map can therefore retain the existing
`holdings_adapter: "spdr"` together with the bridge's expected
`holdings_source_provider: "spdr"` (the bridge also accepts legacy
`source_provider`). Prefer the explicit `holdings_source_provider` key and
preserve any other existing aliases rather than replacing the map. Actual
review provenance may be retained in `legal_metadata` through this same
supported configuration path. This is a documented/admin-controlled profile
binding, not a direct database bypass.

That path is not an evidence-verification workflow: the endpoint accepts
admin-supplied dictionaries and does not validate their cited source, terms,
freshness, or truth, nor does the profile PATCH alone create immutable shared
Provider review records. No qualifying primary-source evidence was established
in this read-only source review, and no profile was changed. A bounded local
artifact search found one superficially relevant retained capture:
`.ai/validation/structural-return-stacked-20261015.headers` records a redirect
to `static.returnstackedetfs.com/data/TidalFG_Holdings_RSST.csv` and an HTTP 200
CSV; its paired body is dated 2026-10-15 and scoped to account `RSST`. It lists
`SPYM` (State Street SPDR Portfolio S&P 500 ETF) as one RSST constituent. This
is a real retained Return Stacked artifact candidate for a dated RSST import,
but it is not SPY's complete basket, is not an artifact fetched from SPDR, and
cannot support SPY's current basket or source binding. It remains evidence for
the RSST artifact only. Thus the route is
available for an administrator to record a binding only after separately
reviewing and retaining genuine issuer/product/route and rights evidence; the
alias alone is not evidence and does not make SPY admitted.

Accepted f04 registers SPDR as an ETF-native adapter/route, not as a generic
Provider-registry publisher. The ETF adapter registry and curated SPDR symbol
metadata let ETF refresh select the SPDR adapter. Separately,
`ProviderCapability.ETF_HOLDINGS` exists in the shared runtime, but generic
`seed_provider_runtime` iterates `supported_provider_names()` from the generic
`app.providers.registry._PROVIDERS`; `spdr` is absent there. The seed logic
explicitly preserves ETF policy rows for the ETF bridge's adapter, which is
not equivalent to creating SPDR's `DataSource`, publisher policy, entitlement,
health, or review configuration.

The accepted f04 admin surface has no publisher bootstrap for those SPDR
records. `PATCH /api/v1/providers/policies/{provider_name}/{capability}` and
`PATCH /api/v1/providers/entitlements/{provider_name}/{capability}` only update
rows found after lookup and return 404 when source/capability rows are absent.
`PUT /api/v1/market-data/recurring-costs/budget` can record the reviewed
aggregate ceiling; `POST /api/v1/market-data/recurring-costs/commitments` can
create a commitment, including a verified-free one, but requires an existing
`data_source_id`. Neither creates SPDR's source, initial ETF policy or
entitlement, health, account/review configuration, or publisher-review record.
So f04's profile PATCH solves the legitimate profile identity-binding part
without a product change, but **it cannot by itself satisfy bridge admission**;
the accepted f04 management gap for initial shared SPDR publisher records
remains concrete.

The current ETF worktree additionally has the unaccepted admin-only
`POST /api/v1/providers/etf-publishers` provisioning implementation described
above. It creates the shared source, disabled ETF policy, entitlement, neutral
health, and admin-attested source/quota/operation/account review metadata, but
does not create the aggregate budget or recurring-cost commitment and does not
verify the truth of supplied evidence. It is not part of frozen f04 and is not
an f04 management path; no endpoint was called and no record or policy was
created or activated in this preparation.

### Accepted-f04 operator import boundary

Accepted f04 does include admin-only manual import APIs:
`POST /api/v1/etf-holdings/{symbol}/ingest` for normalized rows and
`POST /api/v1/etf-holdings/{symbol}/ingest-csv` for a supplied CSV. The CSV
request can retain the supplied bytes as `raw_csv` and accepts composition,
as-of, known-at and publication times, provenance, source provider/URL/
identifier, quality, completeness, parser version, legal metadata and notes.
The handler passes those values to `ingest_holdings_snapshot`; that service
persists the snapshot/raw artifact under the internal `etf_holdings_internal`
data source. This is a supported admin import path for a real artifact already
obtained through an independently authorized means. It is not an upload of a
synthetic test fixture and is not a native SPDR fetch.

Crucially, the import handlers call the ingestion service directly; they do
not call the ETF shared-Provider bridge, reserve quota, or create SPDR's shared
`DataSource`/policy/entitlement/health/review records. The request schema's
defaults (`source_provider=manual_csv`, `provenance=issuer_current_holdings`,
`source_quality=issuer_current`, `completeness_status=complete`) are caller
defaults, not source verification. Do not use them to relabel an old,
incomplete, synthetic, or unverified file as current/complete. An import may
preserve a genuinely sourced dated artifact for historical/PIT use, with its
actual dates, original payload and provenance; it cannot be cited as evidence
that native SPDR transport passed Provider admission. Source tracing found an
important caveat: `ingest_holdings_snapshot` unconditionally calls
`_record_adapter_success`, including when invoked by these manual-import
handlers. Capability classification can infer `issuer_native` from the
caller-supplied default provenance, and identity verification consumes
caller-supplied `artifact_identity_validation` metadata. Therefore an admin
import can potentially satisfy the generic `CURRENT` checks without any
shared-Provider request/reservation/settlement lineage, if the remaining
identity/freshness/completeness conditions are supplied. That is not proof of
native SPDR admission. Do not use the importer as a workaround or represent
such a result as Provider-admitted; the import-success versus native-transport
success distinction is a concrete semantics gap for an implementation/test
decision. No runtime/test was used to claim that this conditional path actually
produced `CURRENT` for SPY.

This makes the first-human choice precise. If an already retained, lawful,
provenance-verifiable SPY/RSP issuer artifact is later found, the accepted
manual-import route can preserve it as a dated artifact without an upstream
request, but accepted f04 does not clearly isolate manual-import health from
native adapter health; until that behavior is corrected or an explicit manual
source contract is accepted, do not rely on it to prove current SPY support.
The bounded local evidence search recorded above found no such artifact. For a
native SPY request, the reviewed profile PATCH can legitimately store both
`holdings_adapter=spdr` and `holdings_source_provider=spdr` (with real review
evidence retained in `legal_metadata`), but only the first is in f04's curated
SPY metadata by default. That profile binding is separate from and insufficient
for shared Provider admission. In accepted f04, generic seeding only creates
runtime rows for generic registry providers; the admin policy/entitlement
PATCHes update existing rows, and the recurring-cost commitment POST requires
an existing source ID. I found no accepted-f04 admin creation route or
documented operator runbook for bootstrapping SPDR's shared source, ETF policy,
entitlement, health and review configuration. That is the concrete native
admission provisioning gap; do not fill it with a direct DB alias or by
claiming that manual import admitted a publisher request.

The shared recurring-cost API paths are the existing admin-reviewed aggregate
budget `PUT /api/v1/market-data/recurring-costs/budget` and commitment
`POST /api/v1/market-data/recurring-costs/commitments`. They do not establish
publisher terms, quota dimensions, account binding, HTTPS host/operation
review, or free status on their own. No endpoint or import was invoked and no
profile, provider, budget, commitment, health, policy or entitlement record
was changed in this source review. The sample remains not admitted/not seeded;
all evidence and the missing provisioning step remain explicit.

The adapter fetch timeout, redirect ceiling, canary symbol cap, and any local
request-size/concurrency guards are application safety envelopes. They are not
claims that SPDR permits that request rate, has those quota counters, allows
retention, or charges zero. Publisher-native limits/account counters and cost
remain unknown until supported by reviewed source evidence.

### Retained RSST sample: manual/noncurrent feasibility follow-up — 2026-10-23

The retained `.ai/validation/structural-return-stacked-20261015.body` is a
genuine captured Return Stacked CSV, not synthetic fixture data. Its rows are
all dated `2026-10-15` and account-scoped `RSST`; the paired response headers
record observation at `2026-10-15T19:09:11Z`, a redirect to
`https://static.returnstackedetfs.com/data/TidalFG_Holdings_RSST.csv`, and an
HTTP 200 CSV. The separate retained transport event reports 36 rows. The
saved header capture does not preserve the initial request URL; only the
redirect target/final CSV URL is explicit in the files inspected, so complete
request-URL lineage must be recovered before an import. The body includes the
full captured mix of SPYM, cash, long futures, and short futures. This
establishes a structural-return-stacked
sample, not a SPY/RSP basket or an SPDR-source observation.

Accepted f04 has an admin CSV-ingest request capable of carrying the raw CSV,
composition date, `known_at`, nullable `published_at`, provenance, source
provider/URL/identifier, quality/completeness, and legal metadata. The
normalized-row `/ingest` schema can also preserve an exact raw body alongside
explicit row classifications. However, f04 does **not** expose a profile
`adapter_key` field on the profile PATCH. It stores only the alias map, and
`ensure_etf_profile` honors an explicit `holdings_adapter` only if that key is
registered by `get_holdings_adapter`; `manual_csv` is not a registered adapter
key. Setting `holdings_adapter: manual_csv` is therefore not an accepted
operator path to a manual profile binding, while a direct DB edit would be an
unsupported bypass.

The generic f04 CSV parser recognizes the retained header's ticker, CUSIP,
security name, shares, market value, and `Weightings` fields; it preserves raw
row fields in `extra_data` and recognizes `Cash&Other` as cash. But the source
has no asset-class/type column. The parser defaults every non-cash row to
`holding_type=equity`, so its default CSV route would mislabel the futures as
equities. The normalized-row route permits explicit `holding_type`,
`row_type`, raw body, and `source_row_id`, so it could represent cash and
derivatives faithfully while retaining unresolved reported identities. That
route is not yet safe for a no-network operator import: both accepted f04
handlers leave `allow_provider_enrichment` at its service default (`true`),
which can call external metadata/identifier providers for unresolved rows.
Do not invoke either route under the current no-HTTP boundary. A safe
manual-only import needs an explicitly no-enrichment path and a verified
normalization of derivative rows; no such operator flag is exposed by f04.

If those boundaries were resolved and a human authorized an actual import,
the truthful record would use ETF symbol `RSST`, composition/as-of date
`2026-10-15`, `provenance=manual_import`, `source_provider=manual_csv`,
`source_tier=none`, non-current quality/completeness values, the original
artifact and issuer URL/redirect evidence, and `published_at=null` because
the retained HTTP `Last-Modified` header is not itself verified publication
evidence. `known_at` must be no earlier than the retained observation and the
actual import time (use the later proven timestamp); the source's `Date` field
supports composition date only. Preserve all raw rows/bytes, including the
short futures and cash, and leave identities unresolved unless independently
supported by existing canonical identity evidence. Public availability does
not establish license, redistribution, or retention rights; written/otherwise
reviewable rights for storing and displaying this captured issuer artifact
remain missing. No such rights evidence or publication time was found here.

The f04 capability evaluator recognizes explicit `source_tier=none` and
reports an existing snapshot as non-current/degraded with
`usable_for_current_analysis=false` while remaining displayable as
last-known. Its historical `get_nearest_snapshot(..., point_in_time=True)`
filters both composition date and `known_at` cutoff: a snapshot imported after
2026-10-15 must not appear in an as-of-October-15 view, but may be visible at
or after its actual import/knowledge time. The ETF holdings panel displays
capability/provenance/known-at and gates opening constituents on current
capability; it does not provide a separate date-selection control in that
panel. The accepted-f04 ingest path nevertheless writes adapter-success state
unconditionally. The current ETF worktree's unaccepted follow-up now tags
admin row/CSV ingestion as `manual_import`, forces source tier `none` before
profile hydration, and skips native adapter-success writes; its resolution plus
route-wiring tests pass 60/60 with live flags off. This is local unaccepted
source, not a claim that frozen f04 has the safeguard, and it does not yet
close the separate provider-enrichment/network risk above.

Disposition: **not ready to import** under the current scope. The retained
body is a credible offline RSST sample candidate, but no import/admin/profile
operation was made. The remaining real blockers are rights/retention evidence,
initial request-URL provenance, a no-enrichment operator path, truthful
derivative row typing, a supported
manual-profile representation (or an explicit decision that no adapter key is
needed), and a final human-authorized sample scope. No SPY substitution,
native entitlement/health claim, provider admission, source quota/cost claim,
or external request is implied. The full AC1–AC14 roadmap, all quarantines,
and observation gate remain open.
