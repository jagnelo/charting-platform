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

The code currently enumerates `420` ETF holdings adapter keys. These keys are
all explicit adapter classes; dynamically generated recognition-only fallback
classes are not allowed.

Current gap to the broad LSEG promoter target:

- Market target: `496`
- Repo-registered adapter keys: `420`
- Missing named promoter identities: `76`

Do not fill this gap by inventing placeholder provider names. The public LSEG
article publishes the count, not the full promoter-name table. A provider may be
added to the registry only after a concrete name and identity relationship are
known.

## First Named Reconciliation Batch

On `2026-07-28`, the first named reconciliation batch added `27` ETF.com
issuer/brand table identities that were not already distinct repo adapter keys.
They are registered as explicit audited fallback-only adapters under
`needs_first_party_route_discovery` until a first-party complete holdings route
is proven for each provider.

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
were not clear aliases of existing route-backed providers. They are registered
as explicit audited fallback-only adapters under
`needs_first_party_route_discovery` until a first-party complete holdings route
is proven for each provider.

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

## Implementation Rule

Every registered provider identity must have an explicit adapter class.

- Native/live-backed providers must have provider-specific route logic, static
  coverage, and opt-in live coverage.
- Audited fallback-only providers must also have a named provider-specific
  adapter class plus a `FALLBACK_ISSUER_AUDITS` entry.
- SEC EDGAR may remain a fallback path, but it must not count as primary native
  provider support.

## Reconciliation Rule

The missing `76` promoter identities require a separate source reconciliation
step before code registration:

1. Obtain a current named U.S. ETF promoter/brand universe from LSEG Lipper,
   ETFGI, ETF.com/VettaFi/ETFDB, exchange listings, or SEC-derived mappings.
2. Map each promoter/brand to one repo adapter key, an alias/successor, an
   inactive/delisted status, or an explicit non-publisher disposition.
3. Add each confirmed missing provider as an explicit adapter class and audit
   entry before attempting native holdings route work.
4. Promote a provider to native only after proving a first-party complete
   holdings source that backend requests can execute.
