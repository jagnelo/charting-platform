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

- Native/live-backed providers: `392`
- Audited fallback-only providers: `104`

The current checkpoint promotes `guggenheim` through its public issuer-hosted
ETF holdings table, reconciles `ars` to the existing ARS Investment Partners
ACEP/AFOS product-page adapter, adds Avory's complete AVRY product-page
holdings route, reconciles Ballast to the complete MGMT FilePoint feed, adds
Bancreek's issuer-rendered BCUS/BCIL/BCGS holdings components, and adds
BeeHive's BEEX product-page-declared daily holdings CSV and Blueprint's TFPN
product-page-declared daily holdings CSV, and Bridgeway's BBLU/BAGX/BRSV/BSVO/BUSM
product-page complete holdings tables, and Brookstone's BAMD/BAMG/BAMV/BAMB/BAMU/BAMA/BAMO/BAMY
product-page-declared complete holdings CSVs, BufferLABS' BFLB product-page
complete current holdings table, and Bushido's SMRI/RNIN product-page complete
current holdings tables, CapForce's FFTY/BOUT product-page complete current
holdings tables, and Castellan's CTEF/CTIF product-page complete current
holdings tables, and Conductor's CGV product-page-declared complete current
holdings CSV, CresAlta's CVGD/CVSM full-holdings tables, Elm's ELM
product-page-declared complete current holdings CSV (also available under the
existing Cygnet parent identity), and Esoterica's WUGI product/data-page-declared
FilePoint dated aggregate holdings CSV, and Even Herd's EHLS product-page-declared
complete daily holdings CSV, and Everence/Praxis's PRXG, PRXV, and PRXI
product-page-declared complete daily holdings CSVs.
FalconX is now covered through its independently managed 21Shares subsidiary,
whose official U.S. catalogue and page-declared primary/secondary product-details
APIs provide current holdings for ARKB, TETH, TOXR, TSOL, TDOG, TDOT, TSUI, TCAN,
THYP, and TKNS.
The former `fcf_advisors` identity is recorded as an inactive/successor
disposition because Abacus Life acquired and rebranded it as Abacus FCF Advisors;
current ABFL, ABLG, ABLD, ABOT, ABLS, and ABXB holdings are covered by the
existing `abacus_global` successor adapter rather than a duplicate FCF route.
First Manhattan's official Excelsior ETF pages identify FMCX and FMCE but state
that holdings are disclosed only sixty days after each quarter-end, so it
remains an audited `non_executable_public_source` rather than a native route.
Fitzgerald is now covered through the official XFUNDS by Nicholas Wealth pages:
the FITZ and FIZY product pages declare nonce-scoped current holdings CSVs, and
the native adapter preserves daily dates, cash, CUSIPs, and FIZY option
positions as derivatives.
Framework Digital Advisors is now covered through the official GSR ETF site and
its declared transformer API for BESO, with the details `updateAt` date carried
through as holdings freshness and the GSR publisher/adviser relationship kept in
provenance. The SEC-listed DATZ product currently has no GSR product page or API
data, so it remains outside this narrowly scoped promotion rather than being
silently reconstructed from EDGAR.
Freedom ETFs is now covered through the official FRDM product page, whose
embedded complete holdings table publishes 136 rows and a September 2, 2026
effective date. The native adapter converts the page's Market Value ($mm)
column to dollars, preserves CUSIP/SEDOL/shares/weights, and classifies Cash &
Other as cash.
Fundstrat is now covered through the official Granny Shots full-holdings pages
for GRNY, GRNJ, and GRNI. Those pages publish complete server-rendered tables
dated September 2, 2026; the native adapter preserves identifiers, weights,
shares, and market values and classifies GRNI option positions as derivatives.
6 Meridian is now covered natively for SIXH, SIXL, SIXA, SIXS, and SXQG through
the official `6meridianfunds.com` product pages. Each page publishes a complete
dated holdings component in the Nuxt hydration payload with company name, ticker,
FIGI, shares, market value, and percentage of NAV. The native adapter validates
the symbol-scoped route and page identity, preserves FIGI/source-ticker metadata,
and classifies the SIXH SPX option and Cash & Other row explicitly while retaining
the Exchange Traded Concepts / 6 Meridian legal publisher relationship.
Gotham is now covered through the official GothamETFs product pages and their
symbol-scoped `DownloadHoldings` CSV routes for GSPY, GVLU, and SHRT. The native
adapter requires the declared schema and a consistent holdings-as-of date,
preserves CUSIPs, signed quantities, weights, and dollar values, and classifies
Cash & Other and SHRT TRS rows as cash and derivatives respectively.
Hexis is now covered for NICO through the official Hexis Capital product page
and its public FilePoint application. The app identifies NICO, exposes a
Download Holdings control, and declares a complete daily CSV route in its
application script. The native adapter validates that declaration and the
issuer-owned host/path, preserves dated equity and exchange-suffixed symbols,
signed TRS derivatives, the FXFXX money-market fund, and Cash&Other, and records
Hexis Capital Management/FilePoint publisher provenance.
Hilton is now covered for SMCO and HBDC through the official Hilton ETFs
product pages and their declared `https://hiltonetfjson.com/etf/AllHoldings.csv`
route. The native adapter filters the shared export by account, requires one
dated complete schema, preserves CUSIPs and percentage-point weights, and
classifies SMCO equities/funds/cash plus HBDC fixed-income/fund/cash rows with
Hilton ETFs publisher and Hilton Capital Management parent provenance.
Highland Capital is recorded as an audited `non_executable_public_source`:
its official AQLG page exposes a complete 130-row CSV with names, CUSIPs,
quantities, and weights, but every ticker field is blank, while the AQLV
prospectus identity has no assigned ticker/current holdings route. The source is
not promoted or reconstructed through SEC/CUSIP lookups because canonical symbol
mapping is unproven.
Horizons is recorded as an audited `inactive_or_successor_disposition`: the
official SEC reorganization document maps the former Horizons DAX, QYLD, and
HSPX funds into corresponding Global X funds, with Global X assuming management
and the Horizons target funds liquidated/terminated. Current QYLD, HSPX, and
DAX holdings therefore belong to the existing `global_x` publisher route; no
duplicate Horizons adapter is created.
Hoya is recorded as an audited inactive/successor alias of the existing native
`pettee` adapter: Hoya's official HOMZ and RIET product pages identify the two
current ETFs and link complete holdings workbooks through the issuer-owned
download route. The existing adapter validates both product identities and
records Hoya Capital Real Estate publisher provenance, so the StockAnalysis
`hoya` display identity does not warrant a duplicate adapter.
JLens is now covered natively for TOV through the official JLens product page at
`investjewishly.org`. The page identifies the JLens 500 Jewish Advocacy U.S. ETF
and publishes a complete server-rendered Fund Holdings table; the adapter
requires the TOV/page identity, preserves ticker/CUSIP/SEDOL/shares/weights,
converts the page's Market Value ($mm) field to dollars, and records the separate
fund-data as-of date plus JLens/Empowered Funds provenance.
Knowledge Leaders is now covered natively for KNO through the official AXS
Investments product page and its declared `axsetf.filepoint.live/v2/kno/nav`
FilePoint route. The dated multi-fund CSV publishes the current KNO snapshot;
the adapter scopes the export to KNO, preserves ISIN/CUSIP/SEDOL/ticker/shares,
weights, currencies, and cash/other-assets rows, and records the 2026-09-02
holdings date with AXS Investments and Knowledge Leaders Capital provenance.
Logiq is now covered natively for LCO through the official LOGIQ ETF product
page and its declared fund-scoped Tidal holdings download/static CSV route. The
adapter validates the product identity and issuer-owned route markers, parses
the current 2026-09-02 snapshot, preserves CUSIPs/quantities/values/weights,
and classifies CASH and EUR currency rows as cash with LOGIQ Capital Partners
provenance.
Long Pond is now covered natively for LPRE through the official Long Pond ETF
product page and its public CMS holdings endpoint. The adapter validates the
LPRE/product-page and CMS component identities, requires the exact six-column
dated schema, parses the current 2026-09-01 24-row snapshot, preserves FIGI/
ticker/shares/market value/weight fields, and records Long Pond Capital /
Exchange Traded Concepts provenance.
LSV is now covered natively for LSVD through the official LSV Asset Management
product page and its declared `ETFLive/LSVD-holdings.csv` route. The adapter
validates the product identity and exact CSV schema, parses the current
2026-09-01 136-row snapshot, preserves ISIN/ticker/shares/market value/weight
fields, and classifies the treasury-obligations sweep and Cash rows explicitly.
Granite Group Advisors is recorded as a non-portfolio-publisher identity: its
official wealth-management materials describe allocation to independent fund
managers, disclaim proprietary fund products, and expose no sponsored U.S. ETF
catalogue or complete issuer holdings route. Its adviser/13F records therefore
remain ineligible as ETF constituent data.
FormulaFolios is recorded as an inactive/successor identity: the official SEC
liquidation supplement names FFHG, FFSG, FFTG, and FFTI and schedules their
October 2023 termination, while Brookstone's official combination notice
establishes the successor context; current Brookstone ETF routes remain under
the distinct native `brookstone` identity.
Measured Risk Portfolios is now covered natively for SNTH and SNTQ through the
official SynthEquity product pages and their declared daily CSV routes. The
native adapter validates the shared dated schema, scopes rows by account,
preserves ticker/CUSIP and numeric holdings, classifies Treasury/fixed-income,
fund, option, and Cash&Other rows, and records issuer-owned provenance. SNTH's
current CSV is live-tested; SNTQ's issuer API is configured and fixture-tested
but reports `Unavailable midnight-7am ET.` outside its serving window, so no
separate SNTQ live-green claim is made yet.

The historical starting snapshot for this
workstream was 356 native and 140 fallback; the provider-audit ledger retains
that baseline record while tracking the current 392/104 split.

The current split is derived from `ISSUER_ADAPTER_CONFIGS` and
`FALLBACK_ISSUER_AUDITS` at the current ETF-branch implementation checkpoint
`e055868d4922f7ae937d6e8dd8c0b78797865934` (6 Meridian SIXH/SIXL/SIXA/SIXS/SXQG official product-page Nuxt holdings components; Measured Risk Portfolios SNTH/SNTQ official SynthEquity product-page-declared daily holdings CSV routes; MAX ETNs CARD/CARU/JETD/JETU official product-page index constituents; McElhenny Sheffield MSMR official product-page holdings table; LSV LSVD official product-page-declared holdings CSV; Long Pond LPRE official product-page CMS holdings JSON; Logiq LCO official product-page-declared Tidal daily holdings CSV; Knowledge Leaders KNO official AXS/FilePoint dated holdings CSV; JLens TOV official product-page embedded holdings table; Hoya Capital display-name and URL alias reconciliation to the existing Pettee HOMZ/RIET native route; Hilton SMCO/HBDC product-page-declared AllHoldings CSV; Hexis/NICO FilePoint app-declared daily holdings CSV; Gotham GSPY/GVLU/SHRT DownloadHoldings CSV routes; Fundstrat Granny Shots GRNY/GRNJ/GRNI holdings routes; Freedom/FRDM product-page holdings route; Framework/GSR BESO route; Fitzgerald/Nicholas Wealth FITZ and FIZY routes; FalconX/21Shares ARKB, TETH, TOXR, TSOL, TDOG, TDOT, TSUI, TCAN,
THYP, and TKNS native routes; Esoterica WUGI, Even Herd EHLS, and Everence/Praxis
PRXG/PRXV/PRXI native routes; Framework/GSR BESO, Freedom/FRDM, and Fundstrat Granny Shots are now native through their
declared details/holdings API; ETF Managers Group is recorded as an
inactive/successor identity after Amplify's documented acquisition; the Discipline
Funds, DVx Ventures, EA Series Trust, and Elements audits
remain fallback-only; Elm is now native-promoted through the same declared route
as the existing Cygnet parent identity).
The fallback audit statuses are:

- `issuer_access_blocked`: `8`
- `needs_first_party_route_discovery`: `87`
- `non_executable_public_source`: `3`
- `provider_not_a_portfolio_publisher`: `6`

The status counts describe the current fallback set. The starting 140-provider
snapshot is preserved in the branch-owned audit ledger. These counts are not a
claim that all remaining fallback dispositions have
already been freshly re-audited; each issuer requires dated route evidence
before promotion or terminal closure.

The current audit checkpoint has issuer-specific evidence for the highest-ranked
records reviewed so far: `ars` is native-promoted through complete ACEP/AFOS
first-party holdings tables, `avory` through a complete AVRY product page,
`ballast` through the MGMT FilePoint feed, `bancreek` through its issuer Nuxt
holdings components, `beehive` through its official BEEX page and declared
daily CSV, and `blueprint` through its official TFPN product page and declared
daily CSV;
`advisors_asset_management` is blocked before a stable
backend export can be captured; `alphamark_advisors` now redirects to an EP
Wealth successor page; `amg_national` is a bank/wealth manager rather than an
ETF portfolio publisher; `amplius` exposes a complete table but blocks backend
requests with Cloudflare; `anydrus` shows placeholder holdings; and
`baillie_gifford` exposes only top-ten spreadsheets. `alphaclone` currently
serves unrelated content, while `argent` and `arin` expose holdings pages that
are likewise blocked to backend requests. These records remain fallback-only
until a complete executable issuer route is proven.
`azimut` is classified as a non-portfolio publisher because its official
catalogue contains mutual-fund/UCITS products rather than a U.S. ETF holdings
route.
`bridgeway` is native-promoted through complete, dated holdings tables on its
official BBLU, BAGX, BRSV, BSVO, and BUSM product pages.
`brookstone` is native-promoted through complete, dated holdings CSVs declared by
its official BAMD, BAMG, BAMV, BAMB, BAMU, BAMA, BAMO, and BAMY product pages.
`bushido` is native-promoted through complete, dated holdings tables on its
official SMRI and RNIN product pages.
`capforce` is native-promoted through complete, dated holdings tables on its
official FFTY and BOUT product pages.
`castellan` is native-promoted through complete, dated holdings tables on its
official CTEF and CTIF product pages.
`conductor_fund` is native-promoted through its official CGV product page's
declared complete current holdings CSV.
`cresalta` is native-promoted through its official CVGD and CVSM full-holdings
pages, each exposing a complete dated holdings table.
`esoterica` is native-promoted through the official AXS WUGI product/data pages
and their declared FilePoint dated aggregate holdings CSV.
`even_herd` is native-promoted through the official EHLS product page and its
declared complete daily `holdings.csv` export, with strict account filtering and
long/short quantity preservation.
`etf_managers_group` is an inactive/successor identity: Amplify's official
acquisition notice documents the ETFMG fund reorganizations and sponsor transfer,
so current holdings routes belong to Amplify or the successor fund managers.
`discipline_funds` remains fallback-only as a non-executable public source:
its official DDV, DDX, and DDXX pages expose a nonce-backed wpDataTables
component, but the current route does not provide a reproducible complete
machine-readable holdings artifact. Bounded attempts returned no DDV rows and
only ten DDX/DDXX rows, so the potentially paginated/incomplete view is not
counted as native support.
`dvx_ventures` remains fallback-only as a non-portfolio publisher: DVx's
official site describes a venture/company-creation platform rather than an ETF
issuer, while official VistaShares materials identify VistaShares as the ETF
issuer and describe DVx personnel as contributors. Any VistaShares holdings
route belongs to the separately tracked `vistashares` identity; no duplicate DVx
native adapter is warranted.
`ea_series_trust` remains fallback-only as a non-portfolio publisher: official
ETF Architect materials describe the trust as a white-label platform hosting
funds with distinct sponsor names, and the trust's filings assign investment
selection to each fund's adviser/sub-adviser. Holdings routes therefore belong
to the actual sponsor or sub-adviser identity, not to a duplicate trust-wide
adapter.
`elements` remains fallback-only with an inactive/successor disposition: the
historical Element Funds/Element ETFs identity maps to CHRG, whose official SEC
supplement records closure and liquidation in December 2023; the current EMG
Advisors successor domain exposes no replacement ETF holdings route.
`formula_folio` remains fallback-only with an inactive/successor disposition:
the official SEC supplement records the October 2023 liquidation of FFHG, FFSG,
FFTG, and FFTI, and Brookstone's official combination notice establishes the
successor context; no distinct current FormulaFolios holdings route exists.
`fpa` is recorded as an inactive/successor alias of the existing native
`first_pacific` identity: First Pacific Advisors' official catalogue lists FPAG,
FPAS, and FPAA, while the verified current FPAG daily route and live coverage
already belong to `first_pacific`; no duplicate FPA adapter is warranted.
`elm` is native-promoted through Elm Partners Management's official ELM product
page and its explicitly declared complete full-holdings CSV. The adapter keeps
the ELM provider identity distinct while preserving the previously validated
Cygnet parent route and provenance.
`credit_suisse` remains fallback-only with an inactive/successor disposition:
UBS's official acquisition and fund-migration notices show the former issuer
identity is being absorbed into UBS, with no current independent U.S. ETF
holdings route available for native promotion.
`desjardins` remains fallback-only as a non-U.S. publisher: its official pages
expose Canadian ETF portfolios and funds, while the expected U.S. ETF provider
catalogue is 404.
`emirate_abu_dhabi` remains fallback-only as a non-portfolio publisher: the
representative `USSE` source row is identified by the current SEC prospectus
and the CI SBH issuer page as Segall Bryant & Hamill/CI SBH, while Emirate of
Abu Dhabi is a sovereign debt issuer. The source identity therefore resolves
to the separately tracked `segall_bryant_hamill` identity; no duplicate Abu
Dhabi native route is warranted.

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
keys after alias checks against existing adapters. They were initially registered
as explicit audited fallback-only adapters under
`needs_first_party_route_discovery`; each is promoted only after a first-party
complete holdings route is proven.

Batch source:
`https://stockanalysis.com/etf/provider/`

The same source table listed `469` U.S. ETF providers and ranked them by ETF
assets, ETF count, and average expense ratio when refreshed on `2026-07-28`.

Added adapter keys:

- `brookstone`
- `fpa`
- `elm` (now native-promoted through the official ELM product-page CSV)
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

Additional disposition:

- `Hoya Capital` -> `pettee`

The Hoya Capital display identity is reconciled to the existing Pettee/Hoya
native adapter, which owns the official HOMZ and RIET product-page-linked
workbooks. This source reconciliation does not create a new provider key.

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
- `bufferlabs` (now native-promoted through its official BFLB fund page)
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
disposition before they should affect registry accounting. BufferLABS, Bushido,
CapForce, Castellan, Conductor, CresAlta, and Even Herd are the exceptions in
this batch: their official product pages now provide complete current holdings
tables or CSVs and are tracked as native routes in the current split. Bushido
covers SMRI and RNIN, CapForce covers FFTY and BOUT, Castellan covers CTEF and
CTIF, Conductor covers CGV through its declared CSV, CresAlta covers CVGD and
CVSM, Elm covers ELM through its declared CSV, and Even Herd covers EHLS through
its declared daily CSV; each route has dated current evidence.

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

## Current audit checkpoint — M2 Financial / CapForce identity reconciliation — 2026-09-03

The ranked `m2_financial` audit found that M2 Financial LLC is identified in
the Capital-Force ETF Trust filings as the investment adviser for the FFTY and
BOUT funds, while the official CapForce product pages are the portfolio
publisher and already expose the complete current holdings tables through the
native `capforce` adapter. M2 therefore does not own a distinct first-party
holdings publication route in this repository.

The exhaustive ledger records `m2_financial` as a dated
`provider_not_a_portfolio_publisher` disposition with FFTY/BOUT representative
symbols, CapForce and SEC evidence, and an explicit resolution to the existing
CapForce publisher. No duplicate M2 adapter or SEC-derived promotion is added.
The code-derived split remains 496 registered, 388 native/live-backed, and 108
fallback-only providers; runtime statuses remain 8 issuer-access-blocked, 91
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher because this terminal ledger disposition, like other
identity reconciliations, remains represented by its existing code-derived
fallback adapter. The ledger now has 62 queued fallback records and the next
ranked item is `m_d_sass`.

## Current audit checkpoint — M.D. Sass / SASS route disposition — 2026-09-03

The ranked `m_d_sass` audit verified the official M.D. Sass ETF site at
`https://www.mdsassetf.com/`. It identifies the M.D. Sass Concentrated Value
ETF (`SASS`) and presents a Top 10 Holdings table, but the live page currently
serves `XX/XX/XXXX` dates and dash placeholders for every holding, NAV, and AUM
value. The official SAI confirms fund/adviser identity but does not provide a
current complete holdings artifact. Third-party SASS tables and M.D. Sass 13F
filings are not issuer-published daily ETF holdings and are not substituted.

The exhaustive ledger records `m_d_sass` as a dated
`non_executable_public_source` disposition with the official page and SAI
routes, one representative symbol, and explicit next steps to re-test for a
populated complete export. No native adapter or SEC-derived promotion is added.
The code-derived split remains 496 registered, 388 native/live-backed, and 108
fallback-only providers; runtime statuses remain 8 issuer-access-blocked, 91
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher because this terminal ledger disposition remains
represented by its existing code-derived fallback adapter. The ledger now has
61 queued fallback records and the next ranked item is `madison_avenue`.

## Current audit checkpoint — Madison Avenue / 6 Meridian identity reconciliation — 2026-09-03

The ranked `madison_avenue` audit identified Madison Avenue Financial
Solutions LLC (doing business as 6 Meridian) as the sub-adviser for the ETC 6
Meridian ETF family. The official `6meridianfunds.com` catalogue identifies
SIXH, SIXL, SIXA, SIXS, and SXQG and their pages expose current holdings
sections, while SEC filings identify Exchange Traded Concepts as the fund
adviser/trust publisher. Madison Avenue is therefore not a distinct portfolio
publisher requiring a duplicate native adapter.

The exhaustive ledger records `madison_avenue` as a dated
`provider_not_a_portfolio_publisher` disposition with the five representative
symbols, official 6 Meridian routes, SEC sub-adviser evidence, and explicit
resolution to the actual publisher identity. No duplicate Madison Avenue
adapter or SEC-derived promotion is added. The code-derived split remains 496
registered, 388 native/live-backed, and 108 fallback-only providers; runtime
statuses remain 8 issuer-access-blocked, 91 needs-first-party-route-discovery,
3 non-executable-public-source, and 6 non-portfolio-publisher because this
terminal ledger disposition remains represented by its existing code-derived
fallback adapter. The ledger now has 60 queued fallback records and the next
ranked item is `matrix`.

## Current audit checkpoint — Matrix / MAVF issuer-access disposition — 2026-09-03

The ranked `matrix` audit verified the official Matrix Advisors Value ETF page
at `https://matrixadvisorsvalueetf.com/`. Indexed page content identifies MAVF
and shows a complete 27-row holdings table with ticker, name, CUSIP, shares,
market value, and percentage columns. However, a bounded direct HTTP request
from the adapter transport receives a Cloudflare “Attention Required” block
before the page can be captured reproducibly.

The exhaustive ledger records `matrix` as a dated `issuer_access_blocked`
disposition with MAVF, official Matrix and SEC routes, and the captured
Cloudflare evidence. No native adapter or indexed/SEC-derived promotion is
added. The code-derived split remains 496 registered, 388 native/live-backed,
and 108 fallback-only providers; runtime statuses are now 9
issuer-access-blocked, 90 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger now has
59 queued fallback records and the next ranked item is `max`.
## Current audit checkpoint — MAX ETNs / CARD-CARU-JETD-JETU native promotion — 2026-09-03

The ranked `max` audit verified the official MAX ETNs catalogue and product
pages at `https://www.maxetns.com/products` and the CARD, CARU, JETD, and JETU
routes. The catalogue identifies five Bank of Montreal MAX ETNs. Four product
pages expose complete server-rendered `Index Constituents` and `Weights` lists
with 20 named constituents and a dated as-of line; the SPYU page is listed but
does not expose a constituent list.

The native `max` adapter validates each supported product identity and exact
official route, parses the complete dated constituent-weight list, and records
the disclosure as ETN index components. Deterministic parser coverage and the
bounded opt-in JETU live route both pass. SPYU remains outside the native route
until an equivalent issuer-owned constituent artifact is published; no
third-party or SEC-derived data is promoted.

The exhaustive ledger records `max` as `native_promoted` with CARD/CARU/JETD/
JETU representative symbols and official MAX ETNs evidence. The code-derived
split is now 496 registered, 389 native/live-backed, and 107 fallback-only
providers; runtime fallback statuses are 8 issuer-access-blocked, 90
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The ledger retains all 140 historical records exactly
once, now with 58 queued fallback records; the next ranked item is
`mcelhenny_sheffield`.

## Current audit checkpoint — McElhenny Sheffield / MSMR native promotion — 2026-09-03

The ranked `mcelhenny_sheffield` audit verified the official McElhenny
Sheffield MSMR product page at `https://mscmfunds.com/msmr-etf/`. The page
identifies the McElhenny Sheffield Managed Risk ETF and publishes a complete
current seven-row holdings table with ticker, CUSIP, security description,
shares, price, market value, weightings, and effective date. The page is
current as of August 31, 2026; the holdings rows are effective September 1,
2026 and include the explicit Cash & Other row.

The native `mcelhenny_sheffield` adapter validates the requested MSMR identity
and exact table schema, maps security identifiers and numeric fields, classifies
fund and cash rows, preserves both page and composition dates, and records
provider-owned provenance. Deterministic parser/registry coverage and the
bounded opt-in live MSMR route pass; no SEC-derived reconstruction is used.

The exhaustive ledger records `mcelhenny_sheffield` as `native_promoted`,
increasing the code-derived split to 496 registered, 390 native/live-backed,
and 106 fallback-only providers. Runtime fallback statuses are 8
issuer-access-blocked, 89 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger
retains all 140 historical records exactly once, now with 57 queued fallback
records; the next ranked issuer is `measured_risk_portfolios`.

## Current audit checkpoint — Measured Risk Portfolios / SNTH-SNTQ native promotion — 2026-09-03

The ranked `measured_risk_portfolios` audit verified the official Measured
Risk Portfolios and SynthEquity sites. The SynthEquity product pages identify
SNTH and SNTQ and declare issuer-owned daily holdings CSV routes: SNTH uses
`https://synthequityfunds.com/wp-content/uploads/2026/07/snth_holdings_full.csv`,
while SNTQ uses
`https://synthequityfunds.com/wp-json/mrp/v4/sntq-holdings-csv`. The SNTH CSV
returned a current September 3, 2026 snapshot with 17 rows. The SNTQ endpoint
is a valid issuer-declared route but currently returns `Unavailable
midnight-7am ET.` outside its serving window; it is therefore recorded as
configured and parser-tested, without a separate live-green claim.

The native `measured_risk_portfolios` adapter validates SNTH/SNTQ product
identity and exact holdings routes, requires the dated account-scoped CSV
schema, maps ticker/CUSIP/shares/price/market value/weight fields, parses
percentage-point weights, classifies Treasury and other fixed-income rows,
funds, options, and Cash&Other/money-market rows, and preserves
provider-owned daily holdings provenance. Deterministic parser/registry
coverage and the bounded opt-in SNTH live route pass; the live transport also
handles the issuer's HTTP 403 response by retrying once through the established
browser-compatible requests path.

The exhaustive ledger records `measured_risk_portfolios` as `native_promoted`,
bringing the code-derived split to 496 registered, 391 native/live-backed, and
105 fallback-only providers. Runtime fallback statuses are 8
issuer-access-blocked, 88 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The 140-record
ledger now has 56 queued fallback records; the next ranked issuer is
`merchant_investment_management`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 391-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

## Current audit checkpoint — Merk / STGF inactive-successor disposition — 2026-09-03

The ranked `merk` audit verified Merk's official STGF page, SEC fund identity,
and current Merk/VanEck gold product relationship. Merk's official STGF page
identifies the Merk Stagflation ETF and explicitly states that the fund was
liquidated in December 2023; its final holdings and market-data snapshot is
dated December 26, 2023. The SEC prospectus confirms STGF as a historical
series of Listed Funds Trust advised by Merk Investments LLC.

Merk's current gold product is the VanEck Merk Gold ETF (OUNZ). The official
current product page identifies Merk Investments LLC as sponsor and VanEck as
the product relationship, so OUNZ is not a distinct current Merk-published ETF
route and must not be duplicated under the Merk adapter identity.

The exhaustive ledger records `merk` as a dated
`inactive_or_successor_disposition`; no native adapter, parser fixture, or
live test is added. Runtime code remains at 496 registered, 392 native/live-
backed, and 104 fallback-only providers with fallback statuses 8
issuer-access-blocked, 87 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The 140-record
ledger now has 53 queued fallback records; the next ranked issuer is
`merlyn_ai`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 392-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout retained as the integration
blocker. Evidence refs: `web:merk-stgf-liquidation-2026-09-03`,
`web:merk-stgf-sec-fund-identity-2026-09-03`, and
`web:merk-ounz-vaneck-successor-2026-09-03`.

## Current audit checkpoint — 6 Meridian / SIXH-SIXL-SIXA-SIXS-SXQG native promotion — 2026-09-03

The ranked `meridian` audit verified the official 6 Meridian catalogue and its
five symbol-scoped product pages at `https://www.6meridianfunds.com/`. Each page
identifies the matching ETF and publishes a complete holdings component in the
Nuxt hydration payload. The payload schema includes company name, ticker, FIGI,
shares, market value, percentage of NAV, and a current holdings date of
September 1, 2026. The SIXH page also publishes an SPX option and an explicit
Cash & Other row, proving that the source includes non-equity positions rather
than only a top-ten equity preview.

The native `meridian` adapter validates the exact HTTPS host/path for SIXH,
SIXL, SIXA, SIXS, and SXQG, checks the product identity and requested Nuxt
HoldingsComponent, maps FIGI/source ticker and numeric fields without inventing
CUSIPs, classifies cash, derivatives, funds, fixed income, and equities, and
preserves the issuer composition date and Exchange Traded Concepts / 6 Meridian
legal publisher relationship. Deterministic parser/registry coverage and the
bounded opt-in live SIXH route pass; no SEC-derived reconstruction is used.

The exhaustive ledger records `meridian` as `native_promoted`, bringing the
code-derived split to 496 registered, 392 native/live-backed, and 104
fallback-only providers. Runtime fallback statuses are 8 issuer-access-blocked,
87 needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The 140-record ledger now has 54 queued fallback
records; the next ranked issuer is `merk`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 392-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker. Evidence refs: `web:six-meridian-official-product-pages-2026-09-03`
and `live:six-meridian-sixh-current-holdings-2026-09-03`.

## Current audit checkpoint — Merchant Investment Management disposition — 2026-09-03

The ranked `merchant_investment_management` audit verified the official
Merchant site at `https://www.merchantim.com/` and the firm's SEC Form ADV.
Merchant describes itself as a strategic and capital partner to wealth
management firms and service providers, offering non-controlling equity
partnerships, business infrastructure, and alternative investment solutions;
its public site exposes no sponsored U.S. ETF catalogue or complete issuer
holdings route. The Form ADV describes sub-advisory services to sponsors of
two Canadian ETFs and holdings recommendations that those sponsors execute.
This is advisory identity evidence, not a provider-owned U.S. ETF portfolio
publication route.

The exhaustive ledger records `merchant_investment_management` as a dated
`provider_not_a_portfolio_publisher` disposition. No native adapter is added,
and no adviser recommendations, 13F data, Canadian products, or SEC-derived
reconstruction is promoted as U.S. ETF constituents. Runtime code remains at
496 registered, 391 native/live-backed, and 105 fallback-only providers with
fallback statuses 8 issuer-access-blocked, 88 needs-first-party-route-
discovery, 3 non-executable-public-source, and 6 non-portfolio-publisher. The
ledger now has 55 queued fallback records; the next ranked issuer is
`meridian`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 391-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

## Current audit checkpoint — Merlyn.AI / WIZ-SNUG-BOB-DUDE inactive-successor disposition — 2026-09-03

The ranked `merlyn_ai` audit verified the historical Merlyn.AI ETF series and
their liquidation records. The official SEC filings enumerate the four
Merlyn.AI funds—WIZ, SNUG, BOB, and DUDE—under EA Series Trust. The ETF
Architect announcement records SNUG and BOB closing in November 2022 because
of insufficient assets, while the SEC liquidation supplements and issuer
announcement record WIZ and DUDE closing and liquidating in November 2023.

The historical MerlynETF site and SEC disclosures cannot provide a current
executable holdings portfolio for any of the four symbols. The complete
historical identity is retained for reconciliation, but stale liquidation-era
constituents are not promoted as current ETF holdings.

The exhaustive ledger records `merlyn_ai` as a dated
`inactive_or_successor_disposition`; no native adapter, parser fixture, or
live test is added. Runtime code remains at 496 registered, 392 native/live-
backed, and 104 fallback-only providers with fallback statuses 8
issuer-access-blocked, 87 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The 140-record
ledger now has 52 queued fallback records; the next ranked issuer is
`mig_capital`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 392-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout retained as the integration
blocker. Evidence refs: `web:merlyn-ai-liquidation-2026-09-03` and
`web:merlyn-ai-sec-fund-series-2026-09-03`.

## Current promotion checkpoint — MIG Capital / MIGO native route — 2026-09-03

The ranked `mig_capital` audit verified MIG Capital's official ETF site at
`https://www.migcapitaletf.com/` and the firm's about page. The homepage
identifies MIGO as the MIG Core ETF and publishes a complete 50-row holdings
component in the Nuxt hydration payload, dated September 1, 2026. The firm
page confirms that MIG Capital launched the long-only ETF in 2026; the current
SEC index independently identifies the MIGO series.

Implementation adds `MigCapitalHoldingsAdapter`, scoped to the exact HTTPS
homepage and `migocap-home-HoldingsComponent-1`. It validates the MIG Core ETF
identity, extracts only the complete holdings component, preserves FIGI and
source ticker values, maps numeric holdings fields, classifies ETF funds,
equities, and cash rows, and records the Exchange Traded Concepts / MIG Capital
publisher relationship. Config, registry, fallback audit removal, deterministic
fixture, live-backed manifest, and bespoke opt-in MIGO live coverage are aligned.

The durable ledger records `mig_capital` as `native_promoted`, increasing the
code-derived split to 496 registered, 393 native/live-backed, and 103
fallback-only providers. Runtime fallback statuses are 8 issuer-access-blocked,
86 needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The 140-record ledger now has 51 queued fallback
records; the next ranked issuer is `militia`.

The focused deterministic adapter checks and bounded opt-in MIGO live route pass
at implementation SHA `590d0f4de26a8c89171f0d9842eef82ac7bff394`. The complete
opt-in provider matrix and Docker-backed integration gate remain pending at the
393-native baseline, with the known unrelated reproducible F8p-current-history
Study Lab histogram timeout retained as the integration blocker. Evidence refs:
`web:mig-capital-official-migo-holdings-2026-09-03` and
`live:mig-capital-migo-current-holdings-2026-09-03`.

## Current promotion checkpoint — Militia / ORR native route — 2026-09-03

The ranked `militia` audit verified the official ORR page at
`https://militiaetf.com/`. It identifies the Militia Long/Short Equity ETF and
server-renders a complete 203-row WPDataTables portfolio (`table_11`, data
table `97`) with ticker, name, CUSIP, signed shares, price, USD-million market
value, percent of net assets, and effective date dated September 3, 2026. The
official SEC prospectus independently confirms the ORR series and daily full
holdings dissemination on the issuer page.

`MilitiaHoldingsAdapter` validates the exact official page and product
identity, parses only the complete embedded table, preserves source tickers,
CUSIPs, effective dates, and signed long/short positions, converts USD-million
values to canonical dollars, and classifies the FGXXX government-obligations
fund and Cash&Other row. Configuration, registry ownership, fallback removal,
deterministic fixture, live manifest, and bespoke opt-in live coverage are
aligned.

The durable split is now 496 registered, 394 native/live-backed, and 102
fallback-only providers, with 50 queued fallback records; the next ranked
issuer is `milliman`. Focused Militia checks and the deterministic 540-test
adapter suite pass. The full opt-in live matrix and Docker-backed integration
gate remain pending at this baseline; the unrelated reproducible F8p-current-
history Study Lab histogram timeout remains the known integration blocker.

## Current promotion checkpoint — Milliman / MHIG-MHIP — 2026-09-03

Milliman's official MHIG and MHIP product pages declare complete dated
holdings CSV downloads on `mfassets.millimanfunds.com`; the official prospectus
confirms daily online holdings dissemination. The native route validates exact
product pages, resolves dated artifacts from rendered links or Next.js page
metadata, and preserves issuer holdings fields and composition dates while
classifying derivatives, fixed income, funds, equities, and cash.

The current split is 496 registered, 395 native/live-backed, and 101
fallback-only providers. The ledger has 49 queued fallback records and
`moonvest` is next. Focused deterministic and opt-in MHIP live checks pass; the
full opt-in matrix and Docker integration gate remain pending, with the known
unrelated F8p-current-history Study Lab histogram timeout retained.

## Current promotion checkpoint — Opus Capital Management / OSCV — 2026-09-03

The official Aptus OSCV product page identifies the Opus Small Cap Value ETF
and publishes a complete current holdings table with ticker, CUSIP, shares,
market value, weight, and effective date. The native adapter uses the page's
declared WordPress API, restricts the route to OSCV, and records truthful
current-date and publisher provenance. A bounded live request returned the
current issuer table successfully.

The current split is 496 registered, 399 native/live-backed, and 97
fallback-only providers. Runtime statuses are 9 issuer-access-blocked, 78
route-discovery, 4 non-executable, and 6 non-portfolio-publisher. The ledger
has 42 queued records and `pabrai` is next. Evidence refs:
`web:opus-capital-management-official-oscv-2026-09-03`,
`web:opus-capital-management-sec-series-2026-09-03`, and
`live:opus-capital-management-oscv-current-holdings-2026-09-03`.

## Current audit checkpoint — Pabrai Wagons / WAGN non-executable public source — 2026-09-03

The official Pabrai Wagons investor-resources page identifies WAGN and links
periodic complete-holdings PDFs and shareholder reports, including the June 30,
2026 N-CSR Schedule of Investments. It does not declare a current executable
daily holdings artifact or symbol-scoped feed, so the ledger records Pabrai as
`non_executable_public_source` without SEC-derived reconstruction.

The current split remains 496 registered, 399 native/live-backed, and 97
fallback-only providers. Runtime statuses are 9 issuer-access-blocked, 78
route-discovery, 4 non-executable, and 6 non-portfolio-publisher. The ledger
has 41 queued records and `panagram` is next. Evidence refs:
`web:pabrai-wagons-investor-resources-2026-09-03` and
`web:pabrai-wagons-current-report-2026-09-03`.

## Current audit checkpoint — Panagram CLO ETFs successor disposition — 2026-09-03

The former Panagram AAA and BBB-B CLO ETFs (CLOX/CLOZ) are now the Eldridge
AAA and BBB-B CLO ETFs. The current CLOX/CLOZ sites expose the successor
holdings surface, and the SEC supplement confirms the January 1, 2025 name
change while retaining the symbols. Because Eldridge already owns the native
daily holdings adapter, the ledger records Panagram as
`inactive_or_successor_disposition` rather than duplicating the route.

The current split remains 496 registered, 399 native/live-backed, and 97
fallback-only providers. Runtime statuses are 9 issuer-access-blocked, 78
route-discovery, 4 non-executable, and 6 non-portfolio-publisher. The ledger
has 40 queued records and `parnassus_investments` is next. Evidence refs:
`web:panagram-eldridge-successor-2026-09-03` and
`web:panagram-eldridge-sec-name-change-2026-09-03`.

## Current audit checkpoint — Parnassus daily route access-blocked — 2026-09-03

Parnassus' official PRCS and PRVS daily-holdings pages are publicly advertised
and the SEC prospectus confirms that policy, but backend-equivalent retrieval of
the PRCS route returned an empty body despite HTTP 200. No holdings payload or
declared machine-readable endpoint could be executed, so the ledger records
`issuer_access_blocked` without SEC-derived reconstruction.

The current split remains 496 registered, 399 native/live-backed, and 97
fallback-only providers. Runtime statuses are 10 issuer-access-blocked, 77
route-discovery, 4 non-executable, and 6 non-portfolio-publisher. The ledger
has 39 queued records and `pathfinder` is next. Evidence refs:
`web:parnassus-official-daily-holdings-routes-2026-09-03` and
`web:parnassus-sec-etf-identity-2026-09-03`.

## Current audit checkpoint — North Square non-executable public source — 2026-09-03

North Square's official NSIV and NSIG pages identify current ETFs but state
that portfolio characteristics are quarterly and complete holdings are
available upon request. The FilePoint catalogue lists the products without a
current holdings download. The ledger records `north_square` as
`non_executable_public_source`; no SEC-derived reconstruction is promoted.

The current split remains 496 registered, 398 native/live-backed, and 98
fallback-only providers. Runtime statuses are 9 issuer-access-blocked, 79
route-discovery, 4 non-executable, and 6 non-portfolio-publisher. The ledger
has 43 queued records and `opus_capital_management` is next.

## Current promotion checkpoint — Norris Perne French / NPFE — 2026-09-03

NPF Investment Advisors' official NPFE page declares a complete current
holdings JSON endpoint. The bounded live route returned 328 rows dated
September 3, 2026; the native parser preserves issuer fields, dates, and
publisher provenance while classifying cash and derivative-like rows.

The current split is 496 registered, 398 native/live-backed, and 98
fallback-only providers. Runtime statuses are 9 issuer-access-blocked, 80
route-discovery, 3 non-executable, and 6 non-portfolio-publisher. The ledger
has 44 queued records and `north_square` is next.

## Current audit checkpoint — Nicholas Wealth access-blocked — 2026-09-03

Nicholas Wealth's official XFUNDS catalogue identifies current products and
symbol-scoped pages, but representative backend-equivalent requests returned
Cloudflare challenges before any complete holdings artifact could be resolved.
The provider remains fallback-only as `issuer_access_blocked`; no SEC-derived
reconstruction or unproven native adapter is counted.

The current split is 496 registered, 397 native/live-backed, and 99
fallback-only providers. Runtime statuses are 9 issuer-access-blocked, 81
route-discovery, 3 non-executable, and 6 non-portfolio-publisher. The ledger
has 45 queued records and `norris_perne_french` is next.

## Current promotion checkpoint — NestYield / EGGQ-EGGY-EGGS — 2026-09-03

NestYield's official product pages publish complete dated holdings tables for
EGGQ, EGGY, and EGGS. The native route validates symbol-scoped identities,
parses issuer rows and option positions, preserves dates/identifiers, and
classifies funds, equities, derivatives, and cash.

The current split is 496 registered, 397 native/live-backed, and 99
fallback-only providers. The ledger has 47 queued fallback records and
`new_age_alpha` is next. Focused deterministic and opt-in live checks pass; the
full opt-in matrix and Docker integration gate remain pending, with the known
unrelated F8p-current-history Study Lab histogram timeout retained.

## Current audit checkpoint — New Age Alpha inactive/successor disposition — 2026-09-03

New Age Alpha's current official site presents h-factor analytics, indexing,
and advisory services. Its issuer announcement records closure and liquidation
of the AVDR and AVDG ETFs in July 2022; the historical SEC registration
confirms the former trust identity but no current executable holdings artifact
exists. The ledger records an inactive/successor disposition without a native
adapter.

Runtime state remains 496 registered / 397 native-live-backed / 99
fallback-only, with 46 queued ledger records and `nicholas_wealth` next. The
full opt-in live matrix and Docker-backed integration gate remain pending; the
known unrelated F8p-current-history Study Lab histogram timeout is retained.

## Current promotion checkpoint — NestYield / EGGQ-EGGY-EGGS — 2026-09-03

NestYield's official product pages publish complete dated holdings tables for
EGGQ, EGGY, and EGGS. The native route validates symbol-scoped identities,
parses issuer rows and option positions, preserves dates/identifiers, and
classifies funds, equities, derivatives, and cash.

The current split is 496 registered, 397 native/live-backed, and 99
fallback-only providers. The ledger has 47 queued fallback records and
`new_age_alpha` is next. Focused deterministic and opt-in live checks pass; the
full opt-in matrix and Docker integration gate remain pending, with the known
unrelated F8p-current-history Study Lab histogram timeout retained.

## Current promotion checkpoint — Moonvest / MNVT — 2026-09-03

Moonvest's official MNVT page publishes a complete dated WPDataTables holdings
table. The native route validates the product identity, parses issuer rows,
normalizes USD-million market values, and classifies fund and cash rows.

The current split is 496 registered, 396 native/live-backed, and 100
fallback-only providers. The ledger has 48 queued fallback records and
`nestyield` is next. Focused deterministic and opt-in MNVT live checks pass; the
full opt-in matrix and Docker integration gate remain pending, with the known
unrelated F8p-current-history Study Lab histogram timeout retained.

## Current promotion checkpoint — Pathfinder / PFDE native route — 2026-09-03

Pathfinder's official PFDE product page and declared FilePoint bundle provide a
complete current holdings route. The native adapter validates the product,
bundle, and CSV chain, parses PFDE rows through the strict FilePoint parser, and
records Pathfinder ETFs / Opal Capital Management provenance. PFDE is native;
PFOE is not promoted until its own executable complete route is proven.

The current split is 496 registered / 400 native-live-backed / 96 fallback-only,
with 38 queued records and `performance_trust` next. Evidence refs:
`web:pathfinder-official-pfde-2026-09-03`,
`web:pathfinder-sec-daily-disclosure-2026-09-03`, and
`live:pathfinder-pfde-current-holdings-2026-09-03`.

## Current audit checkpoint — Performance Trust / STBF — 2026-09-03

PT Asset Management links an issuer-hosted STBF Monthly Fund Holdings PDF, but
the latest artifact is dated July 31, 2026 (S3 last modified August 7, 2026).
It is therefore recorded as `non_executable_public_source`, not native, until
a current symbol-scoped holdings route is available.

The current split remains 496 registered / 400 native-live-backed / 96
fallback-only, with 37 queued records and `portfolio_building_block` next.
Evidence refs: `web:performance-trust-ptam-resources-2026-09-03`,
`web:performance-trust-current-holdings-pdf-2026-09-03`, and
`live:performance-trust-holdings-pdf-stale-2026-09-03`.

## Current promotion checkpoint — Portfolio Building Block / PBOG-PBEU-PBPH — 2026-09-03

The official PBOG, PBEU, and PBPH product pages declare a complete
`?download_holdings_csv=1` route. The current PBOG CSV returned rows dated
September 2, 2026. The native adapter validates page/account identity and
parses the issuer CSV for all three products with truthful publisher provenance.

The current split is 496 registered / 401 native-live-backed / 95 fallback-only,
with 36 queued records and `premise_capital` next. Evidence refs:
`web:portfolio-building-block-pbog-2026-09-03`,
`web:portfolio-building-block-pbeu-2026-09-03`, and
`live:portfolio-building-block-current-pbog-csv-2026-09-03`.

## Current audit checkpoint — Premise Capital / TCTL — 2026-09-03

Premise Capital's historical TCTL identity points to `tctl.us`, but both issuer
hostnames failed DNS resolution and no current symbol-scoped holdings artifact
was available. The provider remains `issuer_access_blocked` without SEC-derived
reconstruction or native promotion.

The current split remains 496 registered / 401 native-live-backed / 95
fallback-only, with 35 queued records and `putnam` next. Evidence refs:
`web:premise-tctl-current-identity-2026-09-03` and
`live:premise-tctl-domain-unreachable-2026-09-03`.
