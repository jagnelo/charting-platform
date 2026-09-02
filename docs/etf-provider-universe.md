# ETF Provider Universe

This project tracks ETF holdings providers at the provider, brand, sponsor,
adviser, and white-label publisher identity level because holdings artifacts are
usually published by product sites, not by a single normalized legal-issuer
field.

## Current Market Target

The current broad U.S. ETF promoter target is `496` identities.

Source: LSEG Lipper, `U.S. ETF Industry Review, June 2026`, as of
`2026-06-30`.

- Report URL:
  `https://lipperalpha.refinitiv.com/reports/2026/07/monday-morning-memo-u-s-etf-industry-review-june-2026/`
- Reported U.S. ETF promoters: `496`
- Reported primary ETF portfolios: `5,397`

The earlier `478` figure came from LSEG Lipper's Q1 2026 report, as of
`2026-03-31`, and is now superseded by the June 2026 report.

## Repo Coverage

The code currently enumerates `496` ETF holdings adapter keys. These keys are
all explicit adapter classes; dynamically generated recognition-only fallback
classes are not allowed.

Current native-route split:

- Native/live-backed providers: `358`
- Audited fallback-only providers: `138`

The current checkpoint promotes `guggenheim` through its public issuer-hosted
ETF holdings table and reconciles `ars` to the existing ARS Investment Partners
ACEP/AFOS product-page adapter. The historical starting snapshot for this
workstream was 356 native and 140 fallback; the provider-audit ledger retains
that baseline record while tracking the current 358/138 split.

The current split is derived from `ISSUER_ADAPTER_CONFIGS` and
`FALLBACK_ISSUER_AUDITS` at the approved ETF-branch checkpoint
`f33224ab94bba5a9f0b7d93c5b82e5578e3a191b`. The fallback audit statuses are:

- `issuer_access_blocked`: `8`
- `needs_first_party_route_discovery`: `121`
- `non_executable_public_source`: `3`
- `provider_not_a_portfolio_publisher`: `6`

The status counts describe the current fallback set. The starting 140-provider
snapshot is preserved in the branch-owned audit ledger. These counts are not a
claim that all remaining fallback dispositions have
already been freshly re-audited; each issuer requires dated route evidence
before promotion or terminal closure.

The current audit checkpoint has issuer-specific evidence for the highest-ranked
records reviewed so far: `ars` is native-promoted through complete ACEP/AFOS
first-party holdings tables; `advisors_asset_management` is blocked before a stable
backend export can be captured; `alphamark_advisors` now redirects to an EP
Wealth successor page; `amg_national` is a bank/wealth manager rather than an
ETF portfolio publisher; `amplius` exposes a complete table but blocks backend
requests with Cloudflare; `anydrus` shows placeholder holdings; and
`baillie_gifford` exposes only top-ten spreadsheets. `alphaclone` currently
serves unrelated content, while `argent` and `arin` expose holdings pages that
are likewise blocked to backend requests. These records remain fallback-only
until a complete executable issuer route is proven.

Current gap to the broad LSEG promoter target:

- Market target: `496`
- Repo-registered adapter keys: `496`
- Missing named promoter identities: `0`

Do not fill this gap by inventing placeholder provider names. The public LSEG
article publishes the count, not the full promoter-name table. A provider may be
added to the registry only after a concrete name and identity relationship are
known.

The arithmetic gap to the `496` LSEG promoter count is now closed through
source-backed named-provider reconciliation. This does not mean every registered
provider has native route support; many source-reconciled providers remain
audited fallback-only until first-party complete holdings routes are proven.

## First Named Reconciliation Batch

On `2026-07-28`, the first named reconciliation batch added `27` ETF.com
issuer/brand table identities that were not already distinct repo adapter keys.
They were initially registered as explicit audited fallback-only adapters under
`needs_first_party_route_discovery` until a first-party complete holdings route
was proven for each provider. `american_beacon` has since been promoted through
American Beacon product-page-declared holdings CSVs, `avantis` through its
Avantis Investors product-page embedded holdings route, `congress` through
Congress Asset Management product-page-declared daily holdings CSVs,
`day_hagan` through Day Hagan product-page-declared Airtable holdings,
`sp_funds` through SP Funds product-page-declared daily holdings CSVs,
`touchstone` through Touchstone ETF product-page full-holdings payloads,
`tradr` through Tradr dated aggregate holdings CSVs, and `vident` through
Vident product-page holdings tables. The other identities from this batch remain
audited fallback-only until proven otherwise.

Batch source:
`https://www.etf.com/sections/etf-league-tables/etf-league-tables-state-street-gathers-52b`

Added adapter keys:

- `alerian`
- `american_beacon`
- `avantis`
- `bridgeway`
- `calvert`
- `congress`
- `day_hagan`
- `fcf_advisors`
- `freedom`
- `fundstrat`
- `gotham`
- `horizons`
- `leverage_shares`
- `meridian`
- `oakmark`
- `panagram`
- `quadratic`
- `range`
- `return_stacked`
- `robo_global`
- `rockefeller_capital`
- `sp_funds`
- `strategy_shares`
- `touchstone`
- `tradr`
- `us_benchmark_series`
- `vident`

## Second Named Reconciliation Batch

On `2026-07-28`, the second named reconciliation batch added `20` ETF.com
issuer-page identities that were not already distinct repo adapter keys and
were not clear aliases of existing route-backed providers. They were registered
as explicit audited fallback-only adapters under
`needs_first_party_route_discovery` until a first-party complete holdings route
was proven for each provider. `emqq` has since been promoted through EMQQ
Global's public CMS complete holdings API.

Batch source:
`https://www.etf.com/etf-issuer`

Added adapter keys:

- `advisors_asset_management`
- `alphaclone`
- `alphamark_advisors`
- `credit_suisse`
- `elements`
- `emqq`
- `esoterica`
- `etf_managers_group`
- `formula_folio`
- `highland_capital`
- `knowledge_leaders`
- `merk`
- `merlyn_ai`
- `new_age_alpha`
- `oshares`
- `premise_capital`
- `riverfront`
- `saba_capital`
- `swedish_export_credit`
- `trimtabs`

## Third Named Reconciliation Batch

On `2026-07-28`, the third named reconciliation batch added `20` ETFDB/VettaFi
issuer-league identities that were not already distinct repo adapter keys after
checking for clear aliases and parent-name variants. They are registered as
explicit audited fallback-only adapters under
`needs_first_party_route_discovery` until a first-party complete holdings route
is proven for each provider.

Batch source:
`https://etfdb.com/issuers/`

The source table was ranked by estimated issuer ETF revenue and stated that the
issuer calculations are based on U.S.-listed ETFs with one issuer per ETF. The
extracted table was last updated on `2026-07-27`.

Added adapter keys:

- `merchant_investment_management`
- `norris_perne_french`
- `granite_group_advisors`
- `falconx`
- `desjardins`
- `amg_national`
- `m2_financial`
- `guggenheim`
- `m_d_sass`
- `worth_charting`
- `azimut`
- `pzena`
- `argent`
- `bancreek`
- `nicholas_wealth`
- `vega_financial`
- `wellesley_asset_management`
- `framework_digital_advisors`
- `saturna`
- `gc_ferry_parent`

## Fourth Named Reconciliation Batch

On `2026-07-28`, the fourth named reconciliation batch added `7` additional
ETFDB/VettaFi issuer-league identities that remained distinct after alias
checks against existing adapters. They are registered as explicit audited
fallback-only adapters under `needs_first_party_route_discovery` until a
first-party complete holdings route is proven for each provider.

Batch source:
`https://etfdb.com/issuers/`

The same ETFDB/VettaFi source table was last updated on `2026-07-27`.
High-ranked legal-parent or spelling variants that were already covered by
existing adapters were not duplicated.

Added adapter keys:

- `emirate_abu_dhabi`
- `measured_risk_portfolios`
- `dvx_ventures`
- `everence`
- `hexis`
- `milliman`
- `baillie_gifford`

## Fifth Named Reconciliation Batch

On `2026-07-28`, the fifth named reconciliation batch exhausted the locally
captured ETFDB/VettaFi issuer-league table rows by adding the remaining
distinct uncovered issuer as an explicit audited fallback-only adapter and by
disposing the final legal-parent/platform row to an existing adapter.

Batch source:
`https://etfdb.com/issuers/`

The same ETFDB/VettaFi source table was last updated on `2026-07-27`.

Added adapter key:

- `mig_capital`

Additional disposition:

- `TFG Parent Holdings LLC` -> `tidal`

`TFG Parent Holdings LLC` is treated only as an ETFDB legal-parent/platform
source-row disposition. It does not create a new generic Tidal route, and it
does not change the existing `tidal` adapter rule: Tidal-backed funds must be
supported only through verified sponsor-published fund-scoped holdings files.

## ETFDB Issuer-League Alias Dispositions

On `2026-07-28`, a follow-up ETFDB/VettaFi issuer-league pass added code-level
alias dispositions for source rows that are legal-parent, spelling, platform,
or jurisdiction variants of existing adapter keys. These rows are source
reconciled, but they do not create new provider keys and do not reduce the
adapter-count gap to the LSEG promoter target.

Batch source:
`https://etfdb.com/issuers/`

Representative dispositions:

- `Proshare Advisors LLC` -> `proshares`
- `Mirae Asset Global Investments Co., Ltd.` -> `mirae_asset`
- `The Charles Schwab Corp.` -> `schwab`
- `SS&C Technologies Holdings, Inc.` -> `ssc`
- `TIAA Board of Governors` and `Nuveen Securities LLC` -> `tiaa`
- `BNY` -> `bny_mellon`
- `Deutsche Bank AG` -> `deutsche_bank`
- `Cohen & Steers, Inc. (New York)` -> `cohen_steers`
- `Arax Investment Partners LLC` -> `araq`
- `Corgi Insurance Services, Inc.` -> `corgi`
- `Man Group Plc (Jersey)` -> `man_group`
- `Natixis Investment Managers` -> `natixis`
- `CYBER HORNET ETFs LLC` -> `cyber_hornet`
- `21Shares AG` -> `21shares`
- `Colliers International Group, Inc.` -> `colliers`
- `TFG Parent Holdings LLC` -> `tidal`

The full executable mapping is
`ETFDB_ISSUER_LEAGUE_ALIAS_DISPOSITIONS` in
`backend/app/services/etf_holdings_adapters.py`; unit coverage verifies each
source row resolves to its intended existing adapter.

## Sixth Named Reconciliation Batch

On `2026-07-28`, a StockAnalysis provider-table pass added `10` high-ranked
provider identities that were not already distinct repo adapter keys after
alias checks against existing adapters. They were initially registered as
explicit audited fallback-only adapters under
`needs_first_party_route_discovery` until a first-party complete holdings route
was proven for each provider. `bluemonte` has since been promoted through
Bluemonte fund-page holdings payloads, `columbia_threadneedle` through Columbia
Threadneedle's public CUSIP-addressed holdings CSV export, `ershares` through
EntrepreneurShares/ERShares SS&C full-holdings API pages, `kovitz` through
Kovitz FilePoint holdings JSON, `mfs` through MFS public daily ETF holdings
pages, and `strategas` through Strategas current holdings CSVs.

Batch source:
`https://stockanalysis.com/etf/provider/`

The source table listed `469` U.S. ETF providers and ranked them by ETF assets,
ETF count, and average expense ratio when captured on `2026-07-28`.

Added adapter keys:

- `putnam`
- `columbia_threadneedle`
- `mfs`
- `bluemonte`
- `vistashares`
- `ershares`
- `portfolio_building_block`
- `kovitz`
- `sapient`
- `strategas`

Additional dispositions:

- `PIMCO` -> `pacific_investments`
- `VictoryShares` -> `victory`
- `AB Funds` -> `alliancebernstein`
- `REX Microsectors` -> `rex`
- `Akre` -> `akre`
- `Tema` -> `tema`
- `Davis` -> `davis`
- `Distillate` -> `distillate`
- `CCM` -> `ccm`

These dispositions are source reconciled but do not create new provider keys.
They prevent StockAnalysis display names and product-line labels from inflating
the adapter-count gap.

## Seventh Named Reconciliation Batch

On `2026-07-28`, a StockAnalysis provider-table continuation pass added `10`
more ranked provider identities that were not already distinct repo adapter
keys after alias checks against existing adapters. They are registered as
explicit audited fallback-only adapters under `needs_first_party_route_discovery`
until a first-party complete holdings route is proven for each provider.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `castellan`
- `bushido`
- `opus_capital_management`
- `lsv`
- `max`
- `tweedy_browne`
- `ars`
- `subversive`
- `fairlead`
- `jlens`

Additional dispositions:

- `iPath` -> `barclays`
- `ETRACS` -> `ubs`
- `Monarch` -> `kingsview`
- `InfraCap` -> `infrastructure_capital`
- `Scharf` -> `scharf`
- `Corgi` -> `corgi`
- `Longview` -> `focus_financial`
- `MIG` -> `mig_capital`
- `The Brinsmere Funds` -> `estate_counselors`

These dispositions are source reconciled but do not create new provider keys.
The `Eagle`, `iM`, and `Horizon` rows remain unresolved because their short
display names are unsafe substring hints without a more specific source-row
spelling in this table snapshot.

## Eighth Named Reconciliation Batch

On `2026-07-28`, a second StockAnalysis provider-table continuation pass added
`10` more ranked provider identities that were not already distinct repo adapter
keys after alias checks against existing adapters. They are registered as
explicit audited fallback-only adapters under `needs_first_party_route_discovery`
until a first-party complete holdings route is proven for each provider.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `smi_funds`
- `militia`
- `roc`
- `madison_avenue`
- `pathfinder`
- `yoke`
- `pabrai`
- `cresalta`
- `hilton`
- `north_square`

Additional dispositions:

- `HCM` -> `howard_capital`
- `Convergence` -> `convergence`
- `Swan` -> `swan_global`
- `Polen` -> `polen`
- `Counterpoint` -> `counterpoint`
- `Abacus` -> `abacus_global`
- `Baron` -> `baron`
- `NPF` -> `norris_perne_french`
- `TappAlpha` -> `tapp`
- `Canary` -> `canary`
- `Transamerica` -> `aegon`
- `KKM Financial` -> `killir`

These dispositions are source reconciled but do not create new provider keys.

## Ninth Named Reconciliation Batch

On `2026-07-28`, a third StockAnalysis provider-table continuation pass added
`10` more ranked provider identities that were not already distinct repo adapter
keys after alias checks against existing adapters. They are registered as
explicit audited fallback-only adapters under `needs_first_party_route_discovery`
until a first-party complete holdings route is proven for each provider.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `brookstone`
- `fpa`
- `elm`
- `segall_bryant_hamill`
- `amplius`
- `nestyield`
- `rareview_funds`
- `srh`
- `parnassus_investments`
- `beehive`

The skipped high-ranked source rows `Eagle`, `iM`, and `Horizon` remain
unresolved because their short display names are unsafe substring hints without
a more specific source-row spelling in this table snapshot.

## Tenth Named Reconciliation Batch

On `2026-07-28`, a fourth StockAnalysis provider-table continuation pass added
`10` more ranked provider identities that were not already distinct repo adapter
keys after alias checks against existing adapters. They are registered as
explicit audited fallback-only adapters under `needs_first_party_route_discovery`
until a first-party complete holdings route is proven for each provider.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `mcelhenny_sheffield`
- `ballast`
- `stance`
- `long_pond`
- `blueprint`
- `stratified`
- `hoya`
- `genter_capital`
- `river1`
- `impact_shares`

Rows such as `Nicholas`, `Myriad Capital`, `Obra`, `ACV`, `The Future Fund`,
`Absolute`, and `REX-Osprey` require separate alias or identity disposition
before they can be counted as new provider keys.

## Eleventh Named Reconciliation Batch

On `2026-07-28`, a fifth StockAnalysis provider-table continuation pass added
`10` more ranked provider identities that were not already distinct repo adapter
keys after alias checks against existing adapters. They are registered as
explicit audited fallback-only adapters under `needs_first_party_route_discovery`
until a first-party complete holdings route is proven for each provider.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `conductor_fund`
- `acsi_funds`
- `first_manhattan`
- `keating`
- `truth_social`
- `altshares`
- `academy`
- `discipline_funds`
- `avos`
- `sophus`

Generic or short adjacent rows such as `PLUS`, `Smart`, `MC`, and `Man` remain
unresolved until they can be safely mapped without introducing broad substring
false positives.

## Twelfth Named Reconciliation Batch

On `2026-07-28`, a sixth StockAnalysis provider-table continuation pass added
the final `16` source-backed provider identities needed to close the arithmetic
gap to the LSEG `496` promoter target. They are registered as explicit audited
fallback-only adapters under `needs_first_party_route_discovery` until a
first-party complete holdings route is proven for each provider.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `capforce`
- `arin`
- `matrix`
- `towle`
- `fitzgerald`
- `ea_series_trust`
- `siren`
- `bufferlabs`
- `performance_trust`
- `anydrus`
- `sammons_enterprises`
- `moonvest`
- `avory`
- `suncoast`
- `even_herd`
- `logiq`

The StockAnalysis table still contains unresolved names after the arithmetic
gap closes. Those rows require alias, product-line, inactive, or source-taxonomy
disposition before they should affect registry accounting.

## Implementation Rule

Every registered provider identity must have an explicit adapter class.

- Native/live-backed providers must have provider-specific route logic, static
  coverage, and opt-in live coverage.
- Audited fallback-only providers must also have a named provider-specific
  adapter class plus a `FALLBACK_ISSUER_AUDITS` entry.
- SEC EDGAR may remain a fallback path, but it must not count as primary native
  provider support.

## Reconciliation Rule

Any future promoter identity changes require a separate source reconciliation
step before code registration:

1. Obtain a current named U.S. ETF promoter/brand universe from LSEG Lipper,
   ETFGI, ETF.com/VettaFi/ETFDB, exchange listings, or SEC-derived mappings.
2. Map each promoter/brand to one repo adapter key, an alias/successor, an
   inactive/delisted status, or an explicit non-publisher disposition.
3. Add each confirmed missing provider as an explicit adapter class and audit
   entry before attempting native holdings route work.
4. Promote a provider to native only after proving a first-party complete
   holdings source that backend requests can execute.
