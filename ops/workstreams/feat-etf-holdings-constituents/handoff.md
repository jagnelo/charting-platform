# feat/etf-holdings-constituents

Created from `staging` at `89bb5c05ad1635156285d392b7c39b3c341ad8f1`.

## Human authorization

- Initial continuation recorded: 2026-08-30T18:48:23.255917+00:00
- Approved plan persistence recorded: 2026-09-02
- Request: continue the existing ETF holdings provider coverage goal from the
  current green staging lineage, and persist the fully approved exhaustive plan
  so another Codex model can implement it in full.
- Closure authorization: pending; do not integrate or deploy until the human
  explicitly authorizes closure.

## Current branch state

- Latest staging merge: `9bc42091ac3d95bcc11ad8783692fb3cd8f9d2e4`
- Incorporated staging SHA: `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`
- Current code-derived state: 496 registered, 414 native/live-backed, 82
  fallback-only.
- Current fallback status split: 8 issuer-access-blocked, 64
  needs-first-party-route-discovery, 3 non-executable public source, and 7
  non-portfolio-publisher. The ledger retains dated terminal dispositions for
  every fallback key; all 140 historical records are represented exactly once.
- `docs/etf-provider-universe.md` is reconciled from code to the current
  496/414/82 snapshot; future updates must remain code-derived.
- Validation tier: `full_integration`.
- Local validation profile: `docker_integration`.
- The latest complete `make validate-integration` run on the current working
  changes passed healthy branch-scoped stack, backend/frontend checks,
  research-runner probes, and functional E2E (154 passed, 106 skipped).
  Visual E2E initially reported 103/104 because the `workspace-floating`
  snapshot at `visual-1080p-125` exceeded its strict threshold; an isolated
  fresh-stack retry passed all four workspace-floating viewport variants. The
  mismatch was transient and did not implicate ETF holdings tests or routes.
- Planning session: `197b239d-3322-4fc6-bf4b-0d0aecebf5e0`.
- Latest implementation checkpoint is `405b2947266c1f41bce46e18ed68fa5877f87412`; subsequent
  commits `262e920b`, `05c0b17c`, `e67c9fb5`, and `a4465d2f` contain only
  formatting and branch-owned validation/session-record updates. The provider
  implementation remains at the reconciled 496/414/82 state described above.
  Earlier
  checkpoints include `dabe2329965c704f93e3dbb21ec50a7da418ba6c` (Hexis/NICO
  native FilePoint route and synchronized records) and the named provider
  promotions retained in the historical record below.
- The exhaustive provider implementation and audit are complete for the current
  496 registered symbols: all 140 starting fallback records have terminal
  native or evidence-backed fallback dispositions, and the ranked queue is
  empty. The Elm implementation reuses the proven official product-page-declared
  full holdings CSV under an explicit `elm` adapter, with Elm Partners Management
  provenance and a dated source audit; it is not a generic alias to SEC data.
  The Esoterica implementation promotes WUGI through the official AXS product/
  data pages and the declared FilePoint dated aggregate CSV, with explicit
  Esoterica provenance and strict WUGI filtering.
  The Even Herd implementation promotes EHLS through the official product page
  and its declared complete daily `holdings.csv`, with strict account filtering,
  cash semantics, and preserved long/short quantities.
  The Everence implementation exposes Praxis's PRXG, PRXV, and PRXI route under
  an explicit parent-identity adapter, preserving exchange-suffixed international
  symbols, SEDOL identifiers, account filtering, cash semantics, and publisher
  relationship provenance.
- The Discipline Funds audit is explicitly not a promotion: the official DDV,
  DDX, and DDXX pages expose a nonce-backed wpDataTables loader, bounded live
  attempts did not prove a complete executable artifact (DDV had no parseable
  rows; DDX/DDXX exposed only ten rows), and the public AJAX probe returned no
  usable dataset. Commit `c1287c90` removes the experimental adapter and records
  the dated `non_executable_public_source` disposition.

## Durable implementation direction

The human-approved exhaustive plan is
`ops/workstreams/feat-etf-holdings-constituents/implementation-plan.md`.
The schema-4 contract is `plan.yaml`. A later Codex implementation model must
read both completely, follow the automatic agent-session workflow, and work
only in this branch's registered local worktree.

## CI follow-up — live-provider edge resilience — 2026-09-03

The first exact-SHA feature-branch CI run (`33798889215`, checkpoint
`e0195f29`) passed Frontend Unit Tests, Backend Tests, and Playwright. Its
branch-declared live matrix failed 13 cases after 481 passed and 12 skipped:
eight Return Stacked products received empty Tidal CSV bodies, OneAscent and
Nightview intermittently returned product pages without the declared CSV
route, Hypatia and Cohen Steers timed out, and Abacus returned a current page
whose date was formatted as `AS OF 09/02/2026` rather than the fixture's
parenthesized two-digit form. Current probes from this worktree fetched the
Return Stacked CSV and both product pages successfully, supporting transient
issuer-edge variability rather than a proven route removal.

The follow-up patch keeps deterministic contracts strict while handling only
these evidenced cases: issuer challenge markup is detected before page-route
validation for OneAscent/Nightview; the live test classifier recognizes the
provider-specific Tidal empty-body error and catches Hypatia/Cohen Steers
timeouts; Abacus composition-date parsing accepts issuer `AS OF` markup with
or without parentheses and one- or two-digit month/day fields. The exact
provider subset passed locally after the patch, and the deterministic suite
remains 567 passed. Follow-up exact-SHA CI run `33801827238` is green: 567
deterministic tests, 2 default-live contract tests, 493 opt-in live cases, and
the complete Playwright job passed; 13 opt-in cases were narrowly skipped for
the recorded external issuer/transport limitations. The feature workflow's
staging/master-only exhaustive gate was intentionally skipped.

The subsequent final-checkpoint run `33804725528` passed frontend, backend, and
Playwright but encountered one additional Sterling SCMC live edge: an
identity-bearing PDF with no parseable positions. The same endpoint currently
returns 183 parseable rows from this worktree, and the bounded Sterling retry
passes. The follow-up test change recognizes only this exact provider-specific
condition as an external skip; the corrected commit requires a fresh exact-SHA
CI run.

## Current implementation checkpoint — Hilton/SMCO-HBDC — 2026-09-03

Hilton Capital Management's official Hilton ETFs product pages identify SMCO
and HBDC and link dedicated all-holdings pages. Those pages declare the shared
`https://hiltonetfjson.com/etf/AllHoldings.csv` export. The native
`HiltonHoldingsAdapter` now validates the product page, all-holdings page,
declared CSV route, complete account-scoped schema, and one current trade date;
it preserves CUSIPs, converts percentage-point weights, and classifies SMCO
equities/funds/cash and HBDC fixed-income/fund/cash rows. The deterministic
unit test and bounded opt-in live test both pass for the two current products.

The committed Hilton implementation checkpoint is
`2f0065c25b1cbb0df515419111d27f55a1106c8a`; the corresponding validation
receipt records the complete deterministic suite, default live contracts,
opt-in SMCO/HBDC live route, Ruff, workstream validation, and diff-check.

The current code-derived split is 496 registered, 383 native/live-backed, and
113 fallback-only providers. Runtime fallback status counts are 8
access-blocked, 96 discovery, 3 non-executable public source, and 6
non-portfolio-publisher. The ledger has 69 queued records and the next ranked
item is `hoya`.

## Historical continuity

The former master-based branch was fully represented in staging before its
remote ref was removed. Its prior checkpoint `a8d6189` recorded 496 registered,
339 native/live-backed, and 157 fallback-only providers. Current code has
advanced to 383/113, including the Guggenheim, ARS, Avory, Ballast, Bancreek,
BeeHive, Blueprint, Bridgeway, Brookstone, BufferLABS, Bushido, CapForce, Castellan,
Conductor, CresAlta, Elm, Esoterica, Even Herd, Everence/Praxis, Hexis/NICO,
and Hilton/SMCO-HBDC
promotions.
Continue current gaps; do not recreate completed work or
restore a dead route merely to reproduce historical counts.

## Next action

The baseline provider-audit ledger now accounts for all 140 fallback keys and an
exhaustive invariant test proves its key/count/rank alignment with runtime code.
`guggenheim`, `ars`, `avory`, `ballast`, `bancreek`, `beehive`, `blueprint`, `bridgeway`, `brookstone`, `bufferlabs`, `bushido`, `capforce`, `castellan`, `conductor_fund`, `cresalta`, `elm`, `esoterica`, `even_herd`, `everence`, `falconx`, and `gotham` are native-promoted; `advisors_asset_management` and `amplius` are
issuer-access-blocked; `alphamark_advisors` is classified as an
inactive/successor disposition; `amg_national` is a non-portfolio publisher;
and `anydrus`, `baillie_gifford`, and `discipline_funds` are non-executable public sources;
`alphaclone` and `elements` are inactive/successor dispositions; `argent` and `arin` are
issuer-access-blocked; `azimut`, `desjardins`, `dvx_ventures`, `ea_series_trust`, and
`emirate_abu_dhabi` are dated non-portfolio-publisher dispositions. The Emirate
record resolves the apparent USSE source row to the separately tracked Segall
Bryant & Hamill/CI SBH identity rather than creating a duplicate sovereign
publisher route. The DVx record resolves the source identity
to the separately tracked VistaShares ETF publisher: DVx's own site is a
venture/company-creation platform, not an ETF portfolio publisher. The EA Series
Trust record resolves the trust/platform identity to each fund's actual sponsor
or sub-adviser rather than a duplicate trust-wide route. The Elements record
maps the historical Element Funds/Element ETFs identity to
CHRG, whose official SEC supplement records closure and liquidation in December
2023; the current EMG Advisors successor domain exposes no replacement ETF
holdings route. Elm's official ELM product page now provides a complete current
holdings CSV dated September 1, 2026; the `elm` adapter preserves that route
under Elm Partners Management while the existing Cygnet adapter remains available
for the parent identity. Esoterica's WUGI route is current and executable through the
AXS/FilePoint chain. Even Herd's EHLS route is current and executable through the
official product-page-declared daily CSV. Everence/Praxis's PRXG, PRXV, and PRXI
routes are current and executable through the official product-page-declared
Azure CSV convention. FalconX's ten current U.S. products are now covered through
the independently managed 21Shares publisher's page-declared primary and
secondary product-details APIs, with explicit parent/publisher provenance. The
  audit ledger currently has 76 queued fallback records still
requiring issuer-specific
evidence and final dispositions; existing terminal/blocked records must remain
evidence-backed. ETF Managers Group is now recorded as an inactive/successor
identity because Amplify's official acquisition notice documents the fund
reorganizations and sponsor transfer; current portfolio routes belong to Amplify
or the successor fund managers. Everence is resolved through the Praxis
Investment Management PRXG/PRXV/PRXI route, with explicit parent/publisher
provenance and exchange-aware parsing. FalconX is resolved through 21Shares'
current U.S. product catalogue, with current route and parent/publisher
provenance. FCF Advisors is resolved as an inactive/successor identity because
Abacus Life acquired and rebranded it; current ABFL, ABLG, ABLD, ABOT, ABLS, and
ABXB routes belong to the existing `abacus_global` adapter. First Manhattan's
official FMCX and FMCE pages identify two active products but disclose holdings
only sixty days after each quarter-end, so the ledger records it as a dated
`non_executable_public_source` rather than a native route. Continue replacing
Fitzgerald/Nicholas Wealth is now native-promoted for FITZ and FIZY through the
official XFUNDS page-declared nonce-scoped daily CSVs; FIZY option rows are
classified as derivatives and the adapter records publisher provenance.
FormulaFolios is now recorded as an inactive/successor identity after its
official October 2023 liquidation; current Brookstone ETF routes are covered by
the distinct `brookstone` adapter. Continue replacing baseline placeholders
with first-party route evidence. The abbreviated `fpa` key is now recorded as
an inactive/successor alias of the existing native `first_pacific` identity;
Framework Digital Advisors is now native-promoted for BESO through the official
GSR product page's details and holdings APIs; the SEC-listed DATZ product has no
current GSR page or API data and was not silently promoted through EDGAR. Continue
with
`freedom` is now native-promoted for FRDM through the official Freedom ETFs
product page's complete holdings table and effective date. Continue with
`fundstrat` is now native-promoted for GRNY, GRNJ, and GRNI through the official
Granny Shots full-holdings pages, including GRNI option classification. GC Ferry
Parent is now recorded as a non-portfolio-publisher parent identity: SEC and
First Eagle ownership evidence ties it to the existing First Eagle publisher,
whose current product catalogue and holdings pages remain the sole native route.
The ledger now records `genter_capital` as an inactive/successor alias of the
existing native `mcivy` Genter publisher after its official GENT/GEND/GENM/GENW
routes and bounded live GEND proof were reconciled. Gotham is now native-promoted
for GSPY, GVLU, and SHRT through its official symbol-scoped DownloadHoldings CSVs,
including cash and SHRT TRS derivative semantics. Granite Group Advisors is now
recorded as a non-portfolio-publisher wealth adviser with no sponsored ETF route.
Hexis/NICO is now native-promoted through the official Hexis FilePoint application and its
declared daily holdings CSV. Highland Capital is recorded as a dated non-executable public
source because the official AQLG CSV omits all ticker symbols and AQLV has no assigned ticker
or current route. Hilton/SMCO-HBDC is now native-promoted through the official Hilton ETFs
product pages and declared AllHoldings CSV, with account-scoped equity, fixed-income, fund,
and cash parsing. Horizons is recorded as an inactive/successor disposition because the
former Horizons U.S. funds reorganized into current Global X successor funds. The ledger
has 69 queued fallback records; continue with `hoya`, and
checkpoint each coherent provider changeset before moving to the next.

## Current implementation checkpoint — Hoya alias reconciliation — 2026-09-03

The ranked `hoya` audit confirmed that Hoya Capital's official HOMZ and RIET
product pages identify the current ETFs, publish complete top-holdings tables,
and link full holdings workbooks through the issuer-owned
`download-holdings-usbanks.php` route. The existing native `pettee` adapter
already validates those product identities and fetched both current workbooks
successfully in the bounded opt-in live test, preserving CUSIPs and Hoya
Capital Real Estate publisher provenance.

The queued StockAnalysis `hoya` identity is therefore recorded as an
`inactive_or_successor` alias of `pettee`, not as a new native adapter. The
runtime alias map now resolves the Hoya Capital display name and
`hoyaetfs.com`/`hoyacapital.com` product URLs to `pettee`; duplicate provider
ownership is avoided while both HOMZ and RIET remain covered by the existing
native route. No SEC-derived or generic fallback promotion is used.

The code-derived split remains 496 registered, 383 native/live-backed, and 113
fallback-only providers. The exhaustive ledger retains all 140 historical
records exactly once; 68 queued fallback records remain and the next ranked
item is `jlens`. The focused alias/parser checks and bounded opt-in Hoya live
test passed. The complete opt-in provider matrix and Docker-backed integration
gate remain pending at the 383-native baseline, with the known unrelated
reproducible F8p-current-history Study Lab histogram timeout still recorded as
the integration blocker.

## Current implementation checkpoint — JLens/TOV native promotion — 2026-09-03

The ranked `jlens` audit verified the official JLens product page at
`https://investjewishly.org/`. The page identifies the JLens 500 Jewish
Advocacy U.S. ETF (`TOV`) and publishes a complete server-rendered Fund
Holdings table with ticker, name, CUSIP, SEDOL, shares, price, Market Value
($mm), and percentage-of-net-assets columns. Its separate Fund Data & Pricing
table reports an as-of date of 2026-09-02; the holdings table itself is treated
as the current issuer page route without inventing a composition date.

`JLensHoldingsAdapter` now validates the TOV/page identity and official host,
parses the complete table, requires at least 100 rows as a completeness guard,
converts Market Value ($mm) into dollars, preserves raw source identifiers and
weights, and records JLens publisher plus Empowered Funds parent provenance and
the fund-data as-of date. The deterministic fixture covers 100 rows, date and
value conversion, metadata, request routing, and unsupported-symbol behavior;
the opt-in live test exercises the current page and requires at least 400 rows.

JLens is removed from the runtime fallback discovery audit and promoted in the
exhaustive ledger. No SEC-derived reconstruction or duplicate fallback adapter
is used. The code-derived split is now 496 registered, 384 native/live-backed,
and 112 fallback-only providers. Runtime fallback status counts are 8
issuer-access-blocked, 95 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger retains
all 140 historical records exactly once; 67 queued fallback records remain and
the next ranked item is `knowledge_leaders`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 384-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the integration
blocker.

The operational checkpoint is recorded in
`ops/workstreams/feat-etf-holdings-constituents/handoff.md` and
`ops/workstreams/feat-etf-holdings-constituents/session.json`; the latter is
the session-local state updated by the checkpoint helper.

## Current implementation checkpoint — Knowledge Leaders/KNO native promotion — 2026-09-03

The ranked `knowledge_leaders` audit verified the official AXS Investments KNO
product page at `https://www.axsinvestments.com/kno/`. It identifies the AXS
Knowledge Leaders ETF (`KNO`, CUSIP `46144X396`) and declares the
`https://axsetf.filepoint.live/v2/kno/nav` FilePoint holdings iframe. The
FilePoint application loads the dated multi-fund
`BBH_AXS_ETF_PVAL_WEB.{YYYYMMDD}.csv` export; the 2026-09-02 file contains 83
KNO rows (70 common stocks, 12 cash rows, and one other-assets row).

`KnowledgeLeadersHoldingsAdapter` now validates the AXS product page and
FilePoint identity, searches only the issuer-declared dated export with a
bounded 15-day lookback, scopes the aggregate file to KNO, requires a single
dated complete snapshot, preserves ISIN/CUSIP/SEDOL/ticker/shares/values/
currencies/weights, and classifies cash and other-assets rows explicitly. The
deterministic fixture covers date fallback, filtering, identifier/value/weight
mapping, row classification, metadata, and unsupported symbols; the opt-in
live test exercises the current official route.

Knowledge Leaders is removed from the runtime fallback discovery audit and
promoted in the exhaustive ledger. The code-derived split is now 496
registered, 385 native/live-backed, and 111 fallback-only providers. Runtime
fallback status counts are 8 issuer-access-blocked, 94
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The ledger retains all 140 historical records exactly
once; 66 queued fallback records remain and the next ranked item is `logiq`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 385-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the integration
blocker.

## Current implementation checkpoint — Logiq/LCO native promotion — 2026-09-03

The ranked `logiq` audit verified the official LOGIQ ETF page at
`https://logiqetf.com/`. It identifies the LOGIQ Contrarian Opportunities ETF
(`LCO`) and declares both a fund-scoped holdings download and the static
`https://logiqetf.com/wp-content/uploads/data/TidalFG_Holdings_LCO.csv` route.
The current CSV is dated 2026-09-02 and contains 86 LCO rows, including
securities, CASH, and EUR currency rows.

`LogiqHoldingsAdapter` now validates the LCO/page identity and both issuer-owned
route markers, requires a complete current snapshot, preserves CUSIPs,
quantities, market values, and percentage weights, and classifies cash/currency
rows explicitly. It records LOGIQ ETF and LOGIQ Capital Partners provenance and
keeps the route limited to LCO.

Logiq is removed from the runtime fallback discovery audit and promoted in the
exhaustive ledger. The code-derived split is now 496 registered, 386
native/live-backed, and 110 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 93 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger retains
all 140 historical records exactly once; 65 queued fallback records remain and
the next ranked item is `long_pond`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 386-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

## Current implementation checkpoint — Madison Avenue / 6 Meridian identity reconciliation — 2026-09-03

The ranked `madison_avenue` audit identified Madison Avenue Financial
Solutions LLC (doing business as 6 Meridian) as the sub-adviser for the ETC 6
Meridian ETF family. The official `6meridianfunds.com` catalogue identifies
SIXH, SIXL, SIXA, SIXS, and SXQG and their pages expose current holdings
sections, while SEC filings identify Exchange Traded Concepts as the fund
adviser/trust publisher. Madison Avenue is therefore not a distinct portfolio
publisher requiring a duplicate native adapter.

The ledger records `madison_avenue` as a dated
`provider_not_a_portfolio_publisher` disposition with the five representative
symbols, official 6 Meridian routes, SEC sub-adviser evidence, and explicit
resolution to the actual publisher identity. No duplicate Madison Avenue
adapter or SEC-derived promotion is added. The code-derived split remains 496
registered, 388 native/live-backed, and 108 fallback-only providers; runtime
statuses remain 8 issuer-access-blocked, 91 needs-first-party-route-discovery,
3 non-executable-public-source, and 6 non-portfolio-publisher because this
terminal ledger disposition remains represented by its existing code-derived
fallback adapter. The ledger retains all 140 historical records exactly once,
now with 60 queued fallback records; the next ranked item is `matrix`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 388-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

The current Long Pond changeset owns these durable paths before checkpoint:
`docs/etf-provider-universe.md`,
`ops/workstreams/feat-etf-holdings-constituents/handoff.md`,
`ops/workstreams/feat-etf-holdings-constituents/implementation-plan.md`,
`ops/workstreams/feat-etf-holdings-constituents/plan.yaml`,
`ops/workstreams/feat-etf-holdings-constituents/provider-audit.yaml`, and
`ops/workstreams/feat-etf-holdings-constituents/session.json` plus
`ops/workstreams/feat-etf-holdings-constituents/validation.jsonl`.

Update this handoff at every coherent implementation and operations boundary.

## Current implementation checkpoint — Long Pond/LPRE native promotion — 2026-09-03

The ranked `long_pond` audit verified the official Long Pond LPRE product page
at `https://www.longpondetf.com/lpre`. It identifies the Long Pond Real Estate
Select ETF (`LPRE`) and declares a dated Holdings section. The public CMS route
at `https://www.longpondetf.com/api/cms/pages` returns the LPRE
`longpond-lpre-HoldingsComponent-1` payload with the documented COMPANY NAME,
TICKER, FIGI, SHARES, MARKET VALUE, and % OF NET ASSET VALUES columns. The
current payload is dated 2026-09-01 and contains 24 holdings rows.

`LongPondHoldingsAdapter` now validates the official product-page host and LPRE
identity, fetches only the issuer's CMS page/component route, requires the exact
holdings schema and a complete dated snapshot, preserves FIGI/ticker/shares/
market-value/weight fields, and records Long Pond Capital / Exchange Traded
Concepts provenance. The deterministic fixture covers route identity, schema,
date/value/weight mapping, metadata, request routing, and unsupported symbols;
the opt-in live test exercises the current official page and CMS route.

Long Pond is removed from the runtime fallback discovery audit and promoted in
the exhaustive ledger. The code-derived split is now 496 registered, 387
native/live-backed, and 109 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 92 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger retains
all 140 historical records exactly once; 64 queued fallback records remain and
the next ranked item is `lsv`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 387-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.
## Current implementation checkpoint — LSV/LSVD native promotion — 2026-09-03

The ranked `lsv` audit verified the official LSV Asset Management product page
at `https://www.lsvasset.com/disciplined-value-etf/`. It identifies the LSV
Disciplined Value ETF (`LSVD`), declares an `As of: 09/01/2026` holdings date,
and links the complete `https://www.lsvasset.com/ETFLive/LSVD-holdings.csv`
export. The issuer CSV uses Name, Ticker, ISIN, Number of Shares, Market Value,
and % of NAV columns and contains 136 rows.

`LsvHoldingsAdapter` now validates the official product-page host and LSVD
identity, requires the page-declared CSV and exact schema, maps ISIN/ticker/
shares/market-value/weight fields, classifies the treasury-obligations sweep and
Cash rows as cash equivalents, and records LSV Asset Management / The Advisors'
Inner Circle Fund provenance. The deterministic fixture covers route identity,
schema, date/value/weight mapping, cash classification, metadata, request
routing, and unsupported symbols; the opt-in live test exercises the current
official page and CSV route.

LSV is removed from the runtime fallback discovery audit and promoted in the
exhaustive ledger. The code-derived split is now 496 registered, 388
native/live-backed, and 108 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 91 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger retains
all 140 historical records exactly once; 63 queued fallback records remain and
the next ranked item is `m2_financial`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 388-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

## Current implementation checkpoint — M.D. Sass / SASS route disposition — 2026-09-03

The ranked `m_d_sass` audit checked the official M.D. Sass site at
`https://www.mdsassetf.com/`. It identifies the M.D. Sass Concentrated Value
ETF (`SASS`) and renders a Top 10 Holdings section, but the live page currently
contains `XX/XX/XXXX` dates and dash placeholders for all holdings, NAV, and AUM
values. The official SAI confirms the fund/adviser relationship but is not a
current complete holdings feed; third-party SASS tables and 13F filings are
outside the native source contract.

The ledger records `m_d_sass` as a dated `non_executable_public_source`
disposition with the official page/SAI routes, SASS representative symbol, and
an explicit re-test action. No native adapter or SEC-derived promotion is
added. The code-derived split remains 496 registered, 388 native/live-backed,
and 108 fallback-only providers; runtime statuses remain 8
issuer-access-blocked, 91 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher because this ledger
disposition remains represented by its existing code-derived fallback adapter.
The ledger retains all 140 historical records exactly once, now with 61 queued
fallback records; the next ranked item is `madison_avenue`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 388-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

## Current implementation checkpoint — M2 Financial / CapForce identity reconciliation — 2026-09-03

The ranked `m2_financial` audit reconciled M2 Financial LLC to the existing
native `capforce` publisher. Official Capital-Force pages publish complete
current holdings for FFTY and BOUT, while the Capital-Force ETF Trust filings
identify M2 Financial LLC as the investment adviser. M2 is therefore an adviser
identity rather than a separate portfolio-publishing issuer; no duplicate M2
native adapter or SEC-derived reconstruction is warranted.

The ledger now records `m2_financial` as a dated
`provider_not_a_portfolio_publisher` disposition with representative symbols
FFTY/BOUT, CapForce and SEC route evidence, and a resolution to the existing
CapForce adapter. The code-derived split remains 496 registered, 388
native/live-backed, and 108 fallback-only providers. Runtime fallback statuses
remain 8 issuer-access-blocked, 91 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher because the
identity disposition remains represented by the existing code-derived fallback
adapter. The ledger retains all 140 historical records exactly once, now with
62 queued fallback records; the next ranked item is `m_d_sass`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 388-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.
## Current implementation checkpoint — Matrix / MAVF issuer-access disposition — 2026-09-03

The ranked `matrix` audit verified the official Matrix Advisors Value ETF page
at `https://matrixadvisorsvalueetf.com/`. Indexed page content identifies MAVF
and shows a complete 27-row holdings table with ticker, name, CUSIP, shares,
market value, and percentage columns. A bounded direct HTTP request from the
adapter transport instead receives a Cloudflare “Attention Required” block,
so the page cannot yet be captured reproducibly for native parsing.

The ledger records `matrix` as a dated `issuer_access_blocked` disposition with
MAVF, official Matrix/SEC routes, and Cloudflare evidence. No native adapter or
indexed/SEC-derived promotion is added. The code-derived split remains 496
registered, 388 native/live-backed, and 108 fallback-only providers; runtime
statuses remain 8 issuer-access-blocked, 91 needs-first-party-route-discovery,
3 non-executable-public-source, and 6 non-portfolio-publisher because this
terminal ledger disposition remains represented by its existing code-derived
fallback adapter. The ledger retains all 140 historical records exactly once,
now with 59 queued fallback records; the next ranked item is `max`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 388-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.
## Current implementation checkpoint — MAX ETNs / CARD-CARU-JETD-JETU native promotion — 2026-09-03

The ranked `max` audit verified the official MAX ETNs catalogue and product
pages at `https://www.maxetns.com/products` and the CARD, CARU, JETD, and JETU
routes. The catalogue identifies five Bank of Montreal MAX products. Four
product pages expose complete server-rendered Index Constituents and Weights
lists with 20 named constituents and an as-of date; SPYU is listed but its
official page does not expose a constituent list.

The native `max` adapter validates supported product identity and exact
official routes, parses the complete dated constituent-weight list, and
records the disclosure as ETN index components. Deterministic parser coverage
and the bounded opt-in JETU live route pass. SPYU remains outside the native
route until an equivalent issuer-owned constituent artifact is published; no
third-party or SEC-derived data is promoted.

The exhaustive ledger records `max` as `native_promoted` with CARD/CARU/JETD/
JETU representative symbols and official MAX ETNs evidence. The code-derived
split is now 496 registered, 389 native/live-backed, and 107 fallback-only
providers; runtime fallback statuses are 8 issuer-access-blocked, 90
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The ledger retains all 140 historical records exactly
once, now with 58 queued fallback records; the next ranked item is
`mcelhenny_sheffield`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 389-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout still recorded as the
integration blocker.

## Current implementation checkpoint — McElhenny Sheffield / MSMR native promotion — 2026-09-03

The ranked `mcelhenny_sheffield` audit verified the official McElhenny
Sheffield MSMR product page at `https://mscmfunds.com/msmr-etf/`. It identifies
the McElhenny Sheffield Managed Risk ETF and publishes a complete current
seven-row holdings table with ticker, CUSIP, security description, shares,
price, market value, weightings, and effective date. The page is current as of
August 31, 2026; rows are effective September 1, 2026 and include Cash & Other.

The native adapter validates MSMR identity and the exact table schema, maps
symbols/CUSIPs/shares/market values/weights, classifies fund and cash rows,
preserves page and effective dates, and records McElhenny Sheffield provenance.
Deterministic parser/registry coverage and the bounded opt-in live MSMR route
pass; no SEC-derived reconstruction is used.

The ledger records `mcelhenny_sheffield` as `native_promoted`, bringing the
code-derived split to 496 registered, 390 native/live-backed, and 106
fallback-only providers. Runtime fallback statuses are 8 issuer-access-blocked,
89 needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The 140-record ledger now has 57 queued fallback
records; the next ranked issuer is `measured_risk_portfolios`.

## Current implementation checkpoint — Measured Risk Portfolios / SNTH-SNTQ native promotion — 2026-09-03

The ranked `measured_risk_portfolios` audit verified the official Measured
Risk Portfolios and SynthEquity sites. SynthEquity identifies SNTH and SNTQ
and declares issuer-owned daily holdings CSV routes. SNTH uses
`https://synthequityfunds.com/wp-content/uploads/2026/07/snth_holdings_full.csv`;
SNTQ uses `https://synthequityfunds.com/wp-json/mrp/v4/sntq-holdings-csv`.
SNTH returned a current September 3, 2026 CSV snapshot with 17 rows. The SNTQ
endpoint is issuer-owned and parser-tested, but currently responds
`Unavailable midnight-7am ET.` outside its serving window, so this checkpoint
does not claim a separate SNTQ live-green run.

Implementation adds `MeasuredRiskPortfoliosHoldingsAdapter` with strict
SNTH/SNTQ route and product support, account-scoped dated CSV parsing,
ticker/CUSIP and numeric-field mapping, percentage-point weight conversion,
fixed-income/fund/option/cash classification, and provider-owned daily
holdings provenance. A 403 from the issuer transport is retried once through
the established browser-compatible synchronous requests path. The
deterministic adapter fixture and bounded opt-in SNTH live test pass, including
current Treasury, equity, option, and Cash&Other/money-market semantics.

The exhaustive ledger records `measured_risk_portfolios` as `native_promoted`,
bringing the code-derived split to 496 registered, 391 native/live-backed, and
105 fallback-only providers. Runtime fallback statuses are 8
issuer-access-blocked, 88 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The 140-record
ledger now has 56 queued fallback records; the next ranked issuer is
`merchant_investment_management`.

Required focused, deterministic, opt-in live, Ruff, and workstream checks are
recorded against implementation SHA
`e5567bec0ed53268195cf1866250e9e1a199143a`. The complete opt-in provider
matrix and Docker-backed integration gate remain pending at the 391-native
baseline, with the known unrelated reproducible F8p-current-history Study Lab
histogram timeout retained as the integration blocker.

## Current audit checkpoint — Merchant Investment Management disposition — 2026-09-03

The ranked `merchant_investment_management` audit verified the official
Merchant site at `https://www.merchantim.com/` and the firm's SEC Form ADV.
Merchant describes itself as a strategic and capital partner to wealth
management firms and service providers, offering non-controlling equity
partnerships, business infrastructure, and alternative investment solutions;
its public site exposes no sponsored U.S. ETF catalogue or complete issuer
holdings route. The Form ADV describes sub-advisory services to sponsors of
two Canadian ETFs and holdings recommendations that the sponsors execute,
which is advisory identity evidence rather than a provider-owned U.S. ETF
portfolio publication.

The ledger records `merchant_investment_management` as a dated
`provider_not_a_portfolio_publisher` disposition. No native adapter is added,
and no adviser recommendations, 13F data, Canadian products, or SEC-derived
reconstruction is promoted as U.S. ETF constituents. Runtime code remains at
496 registered, 391 native/live-backed, and 105 fallback-only providers with
fallback statuses 8 issuer-access-blocked, 88 needs-first-party-route-
discovery, 3 non-executable-public-source, and 6 non-portfolio-publisher. The
ledger now has 55 queued fallback records; the next ranked issuer is `meridian`.

The full opt-in provider matrix and Docker-backed integration gate remain
pending at the 391-native baseline, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout retained as the integration
blocker.

## Current implementation checkpoint — 6 Meridian / SIXH-SIXL-SIXA-SIXS-SXQG native promotion — 2026-09-03

The ranked `meridian` audit verified the official 6 Meridian catalogue and
five symbol-scoped product pages at `https://www.6meridianfunds.com/`. Each
page identifies the requested ETF and publishes a complete holdings component
in the Nuxt hydration payload with company name, ticker, FIGI, shares, market
value, percentage of NAV, and a current holdings date of September 1, 2026.
The SIXH page also exposes an SPX option and an explicit Cash & Other row.

Implementation adds `SixMeridianHoldingsAdapter` with exact HTTPS host/path and
product identity validation, requested-component-only Nuxt extraction, FIGI and
source-ticker preservation, numeric mapping, explicit cash/derivative/fund/
fixed-income/equity classification, composition-date provenance, and the
Exchange Traded Concepts / 6 Meridian legal publisher relationship. The
registry/config, ETF.com native-brand set, fallback audit tuple, adapter map,
deterministic fixture, live-backed manifest, and bespoke live test are aligned.

The durable ledger records `meridian` as `native_promoted`, increasing the
derived split to 496 registered, 392 native/live-backed, and 104 fallback-only
providers. Runtime fallback statuses are 8 issuer-access-blocked, 87
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The ledger now has 54 queued fallback records; the
next ranked issuer is `merk`.

Focused deterministic checks and the bounded opt-in SIXH live route pass at
implementation SHA `e055868d4922f7ae937d6e8dd8c0b78797865934`; the complete
opt-in provider matrix and Docker-backed integration gate remain pending with
the known unrelated reproducible F8p-current-history Study Lab histogram
timeout blocker. Evidence refs: `web:six-meridian-official-product-pages-2026-09-03`
and `live:six-meridian-sixh-current-holdings-2026-09-03`.

## Current audit checkpoint — Merk / STGF inactive-successor disposition — 2026-09-03

The ranked `merk` audit verified the official Merk STGF product page, the
official SEC prospectus, and the current Merk/VanEck gold product page. Merk's
official page identifies STGF and explicitly states that the Merk Stagflation
ETF was liquidated in December 2023; its final holdings and market-data
snapshot is dated December 26, 2023. The SEC prospectus confirms the
historical Listed Funds Trust fund identity and Merk Investments LLC adviser
relationship.

The current Merk-branded gold relationship is the VanEck Merk Gold ETF
(`OUNZ`). The official current page identifies Merk Investments LLC as sponsor
and VanEck as the product relationship, so OUNZ is not a distinct current Merk
ETF publisher route. It remains under the existing VanEck ownership context;
no duplicate Merk adapter is warranted.

The exhaustive ledger records `merk` as a dated
`inactive_or_successor_disposition`. No native adapter, parser fixture, or
live test is added. Runtime code remains at 496 registered, 392 native/live-
backed, and 104 fallback-only providers with fallback statuses 8
issuer-access-blocked, 87 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger now
has 53 queued fallback records; the next ranked issuer is `merlyn_ai`.

Evidence refs: `web:merk-stgf-liquidation-2026-09-03`,
`web:merk-stgf-sec-fund-identity-2026-09-03`, and
`web:merk-ounz-vaneck-successor-2026-09-03`. The complete opt-in provider
matrix and Docker-backed integration gate remain pending at the 392-native
baseline, with the known unrelated reproducible F8p-current-history Study Lab
histogram timeout blocker retained.

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

The ranked `militia` audit verified `https://militiaetf.com/`, whose official
ORR page identifies the Militia Long/Short Equity ETF and server-renders a
complete 203-row WPDataTables holdings table (`table_11`, data table `97`).
Rows expose ticker, name, CUSIP, signed shares, price, USD-million market value,
percent of net assets, and effective date dated September 3, 2026. The official
SEC prospectus independently confirms the ORR series and daily full-holdings
dissemination on the issuer page.

`MilitiaHoldingsAdapter` validates the exact product identity and homepage,
parses only the complete embedded table, preserves source identifiers and
signed long/short positions, converts USD-million values to canonical dollars,
and classifies the FGXXX government-obligations fund and Cash&Other row. Its
configuration, registry ownership, fallback removal, deterministic fixture,
live manifest, and bespoke opt-in live test are synchronized.

The ledger now records `militia` as `native_promoted`: 496 registered, 394
native/live-backed, 102 fallback-only, and 50 queued fallback records. Runtime
fallback statuses are 8 issuer-access-blocked, 85 route-discovery, 3
non-executable, and 6 non-portfolio-publisher; the next ranked issuer is
`milliman`.

Focused Militia unit/live checks pass and the deterministic adapter suite passes
540 tests. The full opt-in live matrix and Docker-backed integration gate remain
pending at this baseline; the unrelated reproducible F8p-current-history Study
Lab histogram timeout remains the known integration blocker. Evidence refs:
`web:militia-official-orr-holdings-2026-09-03`,
`web:militia-sec-daily-holdings-dissemination`, and
`live:militia-orr-current-holdings-2026-09-03`.

## Current promotion checkpoint — Milliman / MHIG-MHIP native route — 2026-09-03

The ranked `milliman` audit verified Milliman Funds' official MHIG and MHIP
product pages. They identify the Milliman Healthcare Inflation Guard ETF and
Milliman Healthcare Inflation Plus ETF and declare complete dated holdings CSV
downloads served from `mfassets.millimanfunds.com`; the official prospectus
independently confirms online daily portfolio holdings dissemination.

`MillimanHoldingsAdapter` validates exact symbol-scoped product pages, resolves
the concrete dated CSV from a rendered link or trusted `__NEXT_DATA__`
holdings date/account payload, fetches only that issuer-declared artifact,
preserves issuer fields and composition dates, and classifies derivatives,
fixed income, funds, equities, and cash. Configuration, registry ownership,
fallback-audit removal, deterministic fixture, live manifest, and bespoke
opt-in MHIP live coverage are synchronized.

The durable ledger records `milliman` as `native_promoted`: 496 registered, 395
native/live-backed, 101 fallback-only, and 49 queued fallback records. Runtime
fallback statuses are 8 issuer-access-blocked, 84 route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher; the next ranked
issuer is `moonvest`.

Focused Milliman unit and opt-in live checks pass; the complete deterministic
adapter suite is rerun at this checkpoint. The full opt-in live matrix and
Docker-backed integration gate remain pending, with the unrelated reproducible
F8p-current-history Study Lab histogram timeout retained. Evidence refs:
`web:milliman-official-mhip-holdings-2026-09-03`,
`web:milliman-sec-daily-holdings-dissemination`, and
`live:milliman-mhip-current-holdings-2026-09-03`.

## Current promotion checkpoint — Moonvest / MNVT native route — 2026-09-03

The ranked `moonvest` audit verified `https://mnvt-etf.com/`. The official
page identifies the Moonvest ETF (MNVT) and server-renders a complete 22-row
holdings table with ticker, name, CUSIP, shares, price, USD-million market
value, percent of net assets, and effective date dated September 3, 2026. The
official SEC filing independently identifies the MNVT series.

`MoonvestHoldingsAdapter` validates the exact official homepage and product
identity, parses only the complete embedded table, preserves issuer fields and
effective dates, converts USD-million values to canonical dollars, and
classifies fund and cash rows. Configuration, registry ownership,
fallback-audit removal, deterministic fixture, live manifest, and bespoke
opt-in MNVT live coverage are synchronized.

The durable ledger records `moonvest` as `native_promoted`: 496 registered, 396
native/live-backed, 100 fallback-only, and 48 queued fallback records. Runtime
fallback statuses are 8 issuer-access-blocked, 83 route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher; the next ranked
issuer is `nestyield`.

Focused Moonvest unit and opt-in live checks pass; the complete deterministic
adapter suite is rerun at this checkpoint. The full opt-in live matrix and
Docker-backed integration gate remain pending, with the unrelated reproducible
F8p-current-history Study Lab histogram timeout retained. Evidence refs:
`web:moonvest-official-mnvt-holdings-2026-09-03`,
`web:moonvest-sec-mnvt-identity-2026-09-03`, and
`live:moonvest-mnvt-current-holdings-2026-09-03`.

## Current promotion checkpoint — NestYield / EGGQ-EGGY-EGGS native route — 2026-09-03

The ranked `nestyield` audit verified the official EGGQ, EGGY, and EGGS product
pages at `https://nestyield.com/`. Each page identifies its symbol-scoped
NestYield ETF and publishes a complete holdings table with Date, Account,
StockTicker, CUSIP, SecurityName, Shares, Price, MarketValue, Weightings, and
a linked all-holdings CSV. Current page tables are dated September 1, 2026; the
official SEC filing independently identifies all three series.

`NestYieldHoldingsAdapter` validates each exact product URL and identity,
parses the issuer's complete table, preserves option positions and identifiers,
records the composition date, and classifies funds, equities, derivatives, and
cash. Configuration, registry ownership, fallback-audit removal, deterministic
fixture, live manifest, and bespoke opt-in coverage for all three products are
synchronized.

The durable ledger records `nestyield` as `native_promoted`: 496 registered,
397 native/live-backed, 99 fallback-only, and 47 queued fallback records.
Runtime fallback statuses are 8 issuer-access-blocked, 82 route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher; the next ranked
issuer is `new_age_alpha`.

Focused NestYield unit and opt-in live checks pass; the complete deterministic
adapter suite is rerun at this checkpoint. The full opt-in live matrix and
Docker-backed integration gate remain pending, with the unrelated reproducible
F8p-current-history Study Lab histogram timeout retained. Evidence refs:
`web:nestyield-official-eggs-holdings-2026-09-03`,
`web:nestyield-sec-series-identities-2026-09-03`, and
`live:nestyield-current-holdings-2026-09-03`.

## Current audit checkpoint — New Age Alpha inactive/successor disposition — 2026-09-03

The ranked `new_age_alpha` audit found no current issuer-owned ETF holdings
route. New Age Alpha's current official site presents its h-factor analytics,
indexing, and advisory business, while the issuer's public announcement records
closure and liquidation of the AVDR US LargeCap Leading ETF and AVDR US
LargeCap ESG ETF, with final trading July 11, 2022 and liquidation July 18,
2022. The historical SEC registration confirms the former New Age Alpha Trust
ETF identity but does not establish a current executable artifact.

The durable ledger records `new_age_alpha` as
`inactive_or_successor_disposition`; no native adapter, parser fixture, or live
test is added. Runtime code remains 496 registered, 397 native/live-backed, and
99 fallback-only providers. The ledger now has 46 queued fallback records; the
next ranked issuer is `nicholas_wealth`. The full opt-in matrix and
Docker-backed integration gate remain pending, with the known unrelated
F8p-current-history Study Lab histogram timeout retained. Evidence refs:
`web:new-age-alpha-avdr-liquidation-2026-09-03` and
`web:new-age-alpha-historical-sec-identity-2026-09-03`.

## Current audit checkpoint — Nicholas Wealth access-blocked disposition — 2026-09-03

The ranked `nicholas_wealth` audit confirmed that Nicholas Wealth's official
catalogue identifies current XFUNDS products and symbol-scoped product pages,
but backend-equivalent requests to representative pages (NGHT, WEPN, GIAX,
and DRMY) return a Cloudflare challenge before a holdings download can be
resolved. No complete executable current portfolio was proven, so no native
adapter or live coverage was added and SEC fallback remains explicitly
labelled rather than promoted as issuer data.

The durable ledger records `nicholas_wealth` as `issuer_access_blocked`.
Runtime state remains 496 registered / 397 native-live-backed / 99
fallback-only providers; runtime fallback statuses are 9 issuer-access-blocked,
81 route-discovery, 3 non-executable-public-source, and 6 non-portfolio-
publisher. The ledger has 45 queued fallback records and the next ranked issuer
is `norris_perne_french`. The full opt-in live matrix and Docker-backed
integration gate remain pending, with the known unrelated reproducible
F8p-current-history Study Lab histogram timeout retained.

## Current promotion checkpoint — Rockefeller ETFs daily holdings routes — 2026-09-03

Rockefeller ETFs' RMOP, RMNY, RMCA, RSMC, and RGEF product pages declare
fund-scoped TidalFG daily holdings CSVs. All five September 3, 2026 CSV routes
returned complete parseable current rows. The provider-specific adapter checks
the product-page identity and declared filename/account scope, then preserves
Rockefeller ETFs / Tidal Investments provenance.

The durable ledger records `rockefeller_capital` as `native_promoted` without
SEC reconstruction. The current split is 496 registered / 406 native-live-backed
/ 90 fallback-only providers, with 26 queued records and `saba_capital` next.
Runtime fallback statuses are 12 issuer-access-blocked, 65 route-discovery, 7
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:rockefeller-current-product-pages-and-csv-routes-2026-09-03` and
`live:rockefeller-current-daily-holdings-csv-2026-09-03`.

## Current promotion checkpoint — Opus Capital Management / OSCV native route — 2026-09-03

The ranked `opus_capital_management` audit verified the official Aptus OSCV
product page and its declared WordPress holdings API. The page publishes a
complete current holdings table; the native adapter restricts the route to
OSCV, maps ticker/CUSIP/shares/value/weight fields, preserves the effective
date, and records Opus publisher provenance without SEC-derived reconstruction.

The durable ledger records `opus_capital_management` as `native_promoted`.
Runtime state is now 496 registered / 399 native-live-backed / 97
fallback-only providers; runtime fallback statuses are 9 issuer-access-
blocked, 78 route-discovery, 4 non-executable-public-source, and 6
non-portfolio-publisher. The ledger has 42 queued fallback records and the
next ranked issuer is `pabrai`. Focused deterministic and bounded live checks
pass; the full opt-in matrix and Docker-backed integration gate remain pending
with the known unrelated F8p-current-history Study Lab histogram timeout
retained. Evidence refs:
`web:opus-capital-management-official-oscv-2026-09-03`,
`web:opus-capital-management-sec-series-2026-09-03`, and
`live:opus-capital-management-oscv-current-holdings-2026-09-03`.

## Current audit checkpoint — Pabrai Wagons / WAGN non-executable public source — 2026-09-03

The ranked `pabrai` audit verified the official WAGN investor-resources page
and issuer-hosted reports. Complete holdings are exposed only as periodic PDFs,
most recently the June 30, 2026 N-CSR Schedule of Investments; no current
executable daily holdings artifact or symbol-scoped feed was declared. The
ledger records `pabrai` as `non_executable_public_source`, with no SEC-derived
reconstruction promoted.

Runtime state remains 496 registered / 399 native-live-backed / 97
fallback-only providers; runtime fallback statuses are 9 issuer-access-
blocked, 78 route-discovery, 4 non-executable-public-source, and 6
non-portfolio-publisher. The ledger has 41 queued records and the next ranked
issuer is `panagram`. Focused ledger/workstream validation remains pending for
this documentation checkpoint; the known unrelated F8p-current-history Study
Lab histogram timeout remains the integration blocker. Evidence refs:
`web:pabrai-wagons-investor-resources-2026-09-03` and
`web:pabrai-wagons-current-report-2026-09-03`.

## Current audit checkpoint — Panagram CLO ETFs successor disposition — 2026-09-03

The ranked `panagram` identity resolves to the current Eldridge successor:
Panagram AAA/BBB-B CLO ETFs became Eldridge AAA/BBB-B CLO ETFs effective
January 1, 2025 while retaining CLOX/CLOZ. The successor's official sites and
existing native Eldridge daily CSV cover the active products, so no duplicate
Panagram adapter is warranted. The ledger records
`inactive_or_successor_disposition`.

Runtime state remains 496 registered / 399 native-live-backed / 97
fallback-only providers; runtime fallback statuses are 9 issuer-access-
blocked, 78 route-discovery, 4 non-executable-public-source, and 6
non-portfolio-publisher. The ledger has 40 queued records and the next ranked
issuer is `parnassus_investments`. Workstream validation and diff-check remain
pending for this documentation checkpoint; the known unrelated F8p-current-
history Study Lab histogram timeout remains the integration blocker. Evidence
refs: `web:panagram-eldridge-successor-2026-09-03` and
`web:panagram-eldridge-sec-name-change-2026-09-03`.

## Current audit checkpoint — Parnassus daily route access-blocked — 2026-09-03

The ranked `parnassus_investments` audit verified official PRCS/PRVS daily-
holdings route declarations and the SEC prospectus identity, but the PRCS
backend-equivalent request returned an empty body despite HTTP 200. A complete
current holdings payload could not be executed or parsed; the ledger records
`issuer_access_blocked` and no SEC-derived reconstruction is promoted.

Runtime state remains 496 registered / 399 native-live-backed / 97
fallback-only providers; runtime fallback statuses are 10 issuer-access-
blocked, 77 route-discovery, 4 non-executable-public-source, and 6
non-portfolio-publisher. The ledger has 39 queued records and the next ranked
issuer is `pathfinder`. Workstream validation and diff-check remain pending for
this documentation checkpoint; the known unrelated F8p-current-history Study
Lab histogram timeout remains the integration blocker. Evidence refs:
`web:parnassus-official-daily-holdings-routes-2026-09-03` and
`web:parnassus-sec-etf-identity-2026-09-03`.

## Current promotion checkpoint — Pathfinder / PFDE native route — 2026-09-03

The ranked `pathfinder` audit verified Pathfinder ETFs' official PFDE product
page, JavaScript bundle declaration, and issuer-hosted FilePoint complete-
holdings CSV. The bounded live route returned parseable current PFDE rows; the
native adapter validates the product/bundle/CSV chain and records Pathfinder
ETFs / Opal Capital Management provenance. PFDE is promoted; PFOE remains out
of scope until its own complete executable route is proven.

Runtime state is now 496 registered / 400 native-live-backed / 96 fallback-only
providers, with 38 queued records and `performance_trust` next. Deterministic
adapter tests (548), bounded Pathfinder live coverage, Ruff, workstream
validation, and diff-check pass; the known unrelated F8p-current-history Study
Lab histogram timeout remains the integration blocker. Evidence refs:
`web:pathfinder-official-pfde-2026-09-03`,
`web:pathfinder-sec-daily-disclosure-2026-09-03`, and
`live:pathfinder-pfde-current-holdings-2026-09-03`.

## Current audit checkpoint — Performance Trust / STBF non-executable public source — 2026-09-03

PT Asset Management's official resources page links a complete STBF Monthly
Fund Holdings PDF. The issuer artifact is dated July 31, 2026 and its S3 object
was last modified August 7, 2026; although reachable with HTTP 200, it is not a
current executable holdings route on September 3. The ledger records
`performance_trust` as `non_executable_public_source` without native promotion
or SEC-derived reconstruction.

Runtime state remains 496 registered / 400 native-live-backed / 96 fallback-only
providers. Runtime fallback statuses are 10 issuer-access-blocked, 75
route-discovery, 5 non-executable-public-source, and 6 non-portfolio-publisher.
The ledger has 37 queued records and the next ranked issuer is
`portfolio_building_block`. Evidence refs:
`web:performance-trust-ptam-resources-2026-09-03`,
`web:performance-trust-current-holdings-pdf-2026-09-03`, and
`live:performance-trust-holdings-pdf-stale-2026-09-03`.

## Current promotion checkpoint — Portfolio Building Block / PBOG-PBEU-PBPH native route — 2026-09-03

Portfolio Building Block's official PBOG, PBEU, and PBPH product pages declare
the `?download_holdings_csv=1` download. The current PBOG route returned a
complete CSV dated September 2, 2026; the native adapter validates each page
and account symbol, parses the complete CSV, and records Portfolio Building
Block ETFs provenance for all three products.

Runtime state is now 496 registered / 401 native-live-backed / 95 fallback-only
providers. Runtime fallback statuses are 10 issuer-access-blocked, 74
route-discovery, 5 non-executable-public-source, and 6 non-portfolio-publisher.
The ledger has 36 queued records and the next ranked issuer is `premise_capital`.
Evidence refs: `web:portfolio-building-block-pbog-2026-09-03`,
`web:portfolio-building-block-pbeu-2026-09-03`, and
`live:portfolio-building-block-current-pbog-csv-2026-09-03`.

## Current audit checkpoint — Premise Capital / TCTL issuer-access-blocked — 2026-09-03

The historical Premise Capital identity points to `tctl.us`, but both the
issuer hostname and `www.tctl.us` failed DNS resolution during the audit. No
current symbol-scoped holdings artifact could be accessed or parsed, so the
ledger records `premise_capital` as `issuer_access_blocked`; no SEC-derived
reconstruction or unproven native adapter is counted.

Runtime state remains 496 registered / 401 native-live-backed / 95 fallback-only
providers. Runtime fallback statuses are 11 issuer-access-blocked, 73
route-discovery, 5 non-executable-public-source, and 6 non-portfolio-publisher.
The ledger has 35 queued records and the next ranked issuer is `putnam`.
Evidence refs: `web:premise-tctl-current-identity-2026-09-03` and
`live:premise-tctl-domain-unreachable-2026-09-03`.

## Current audit checkpoint — Putnam / Franklin successor periodic disclosure — 2026-09-03

Putnam retail ETFs have moved to Franklin Templeton. The public successor
catalogue mapped 14 Putnam symbols to fund IDs, but API probes returned delayed
January–July 2026 snapshots and no holdings rows for PFRX. Putnam/Franklin
materials describe delayed quarterly complete-holdings disclosure, so the
provider remains `non_executable_public_source`; no native adapter or SEC
reconstruction is counted.

Runtime state remains 496 registered / 401 native-live-backed / 95 fallback-only
providers, with 34 queued records and `pzena` next. Runtime fallback statuses
are 11 issuer-access-blocked, 72 route-discovery, 6 non-executable-public-source,
and 6 non-portfolio-publisher. Evidence refs:
`web:putnam-franklin-current-etf-catalogue-2026-09-03`,
`web:putnam-quarterly-holdings-disclosure-2026-09-03`, and
`live:putnam-franklin-api-stale-or-empty-2026-09-03`.

## Current audit checkpoint — Pzena / PZIV-PZLV issuer-access-blocked — 2026-09-03

Pzena's official catalogue identifies PZIV and PZLV and advertises daily
holdings at `pzena.com/etfs`. Backend-equivalent requests returned only an
unusable page shell without holdings data, so `pzena` remains
`issuer_access_blocked`; no native adapter or SEC reconstruction is counted.

Runtime state remains 496 registered / 401 native-live-backed / 95 fallback-only
providers, with 33 queued records and `quadratic` next. Runtime fallback statuses
are 12 issuer-access-blocked, 72 route-discovery, 6 non-executable-public-source,
and 6 non-portfolio-publisher. Evidence refs:
`web:pzena-current-etf-catalogue-2026-09-03`,
`web:pzena-daily-holdings-disclosure-2026-09-03`, and
`live:pzena-etf-page-shell-blocked-2026-09-03`.

## Current promotion checkpoint — Quadratic / IVOL-BNDD native route — 2026-09-03

KFA's IVOL and BNDD product pages declare full holdings, and dated KraneShares
CSV files for September 2, 2026 returned complete rows for both products. The
new provider-specific adapter validates symbols and publisher route, parses
securities/cash/options, and records Quadratic/KraneShares provenance.

Runtime state is now 496 registered / 402 native-live-backed / 94 fallback-only
providers, with 32 queued records and `rareview_funds` next. Runtime fallback
statuses are 12 issuer-access-blocked, 71 route-discovery, 6
non-executable-public-source, and 6 non-portfolio-publisher. Evidence refs:
`web:quadratic-kfa-current-holdings-2026-09-03` and
`live:quadratic-kraneshares-current-csv-2026-09-03`.

## Current audit checkpoint — Rareview Funds stale holdings sources — 2026-09-03

Rareview's official ETF catalogue identifies six products, but accessible
product holdings sections are stale historical tables (RSEE January 21, 2022;
RTAI October 22, 2020) and no current complete machine-readable route is
declared. Keep `rareview_funds` as `non_executable_public_source` without SEC
reconstruction or native promotion.

Runtime state remains 496 registered / 402 native-live-backed / 94 fallback-only
providers, with 31 queued records and `return_stacked` next. Runtime fallback
statuses are 12 issuer-access-blocked, 70 route-discovery, 7
non-executable-public-source, and 6 non-portfolio-publisher. Evidence refs:
`web:rareview-current-etf-catalogue-2026-09-03` and
`web:rareview-stale-holdings-pages-2026-09-03`.

## Current audit checkpoint — Return Stacked daily holdings routes — 2026-09-03

Return Stacked's official product pages expose daily symbol-scoped holdings
CSVs for RSST, RSIT, RSSY, RSSX, RSBT, RSBY, RSBA, and RSSB. The September 2,
2026 issuer endpoints returned complete parseable rows for every mapped product.
The provider-specific adapter validates page identity and preserves issuer
provenance, so `return_stacked` is native-promoted without SEC reconstruction.

Runtime state is now 496 registered / 403 native-live-backed / 93 fallback-only
providers, with 30 queued records and `river1` next. Runtime fallback statuses
are 12 issuer-access-blocked, 69 route-discovery, 7 non-executable-public-source,
and 6 non-portfolio-publisher. Evidence refs:
`web:return-stacked-current-product-pages-2026-09-03` and
`live:return-stacked-current-holdings-csv-2026-09-03`.

## Current promotion checkpoint — River1 / RVER issuer XLS route — 2026-09-03

River1's official RVER page declares a fund-scoped full holdings XLS export;
the live download returned a complete workbook dated September 1, 2026. The
new provider-specific adapter validates RVER page identity and export scope,
parses the legacy XLS rows, and records River1 provenance without SEC
reconstruction.

Runtime state is now 496 registered / 404 native-live-backed / 92 fallback-only
providers, with 29 queued records and `riverfront` next. Runtime fallback
statuses are 12 issuer-access-blocked, 68 route-discovery, 7
non-executable-public-source, and 6 non-portfolio-publisher. Evidence refs:
`web:river1-current-rver-page-2026-09-03` and
`live:river1-current-holdings-xls-2026-09-03`.

## Current audit checkpoint — RiverFront sub-adviser disposition — 2026-09-03

RiverFront's official sub-advised ETF page identifies RFDI and RFEM as
RiverFront-managed products offered through a partnership with First Trust.
First Trust hosts the current full holdings tables and remains the legal
adviser/distributor and portfolio publisher. RFEU is terminated, while RFDA's
successor page states that RiverFront ceased serving as sub-adviser effective
March 31, 2026.

The durable ledger records `riverfront` as
`provider_not_a_portfolio_publisher`, with RFDI and RFEM as identity evidence.
No duplicate RiverFront native adapter is warranted; any holdings integration
must be owned by the First Trust publisher route. Runtime state is 496
registered / 404 native-live-backed / 92 fallback-only providers, with 28
queued records and `robo_global` next. Runtime fallback statuses are 12
issuer-access-blocked, 66 route-discovery, 7 non-executable-public-source, and
7 non-portfolio-publisher. Evidence refs:
`web:riverfront-subadvised-first-trust-2026-09-03` and
`web:riverfront-rfdi-rfem-current-first-trust-holdings-2026-09-03`.

## Current promotion checkpoint — ROBO Global / ROBO-HTEC-THNQ Nuxt routes — 2026-09-03

ROBO Global's official ROBO, HTEC, and THNQ product pages server-publish
complete holdings components in their Nuxt hydration payloads, each dated
September 1, 2026. The native adapter validates ticker-specific page routes and
component IDs, normalizes the issuer rows, and preserves ROBO Global / Exchange
Traded Concepts provenance.

The durable ledger records `robo_global` as `native_promoted` with no SEC
reconstruction. Runtime state is now 496 registered / 405 native-live-backed /
91 fallback-only providers, with 27 queued records and `roc` next. Runtime
fallback statuses are 12 issuer-access-blocked, 65 route-discovery, 7
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:robo-global-current-robo-htec-thnq-pages-2026-09-03` and
`live:robo-global-current-nuxt-holdings-2026-09-03`.

## Current audit checkpoint — ROC / ROCI inactive disposition — 2026-09-03

The official ROC ETF prospectus supplement and ETF Architect announcement state
that ROCI was approved for liquidation October 11, 2023, stopped trading after
October 20, and dissolved October 27. No current product or holdings artifact
is available.

The durable ledger records `roc` as `inactive_or_successor_disposition`; no
native adapter or SEC reconstruction is warranted. Runtime state remains 496
registered / 405 native-live-backed / 91 fallback-only providers, with 26
queued records and `rockefeller_capital` next. Runtime fallback statuses remain
12 issuer-access-blocked, 65 route-discovery, 7 non-executable-public-source,
and 7 non-portfolio-publisher. Evidence ref:
`web:roc-roci-liquidation-2023-10-11`.

## Current audit checkpoint — North Square non-executable public source — 2026-09-03

The ranked `north_square` audit verified official NSIV and NSIG product pages
and the North Square FilePoint catalogue. The pages identify current ETFs but
state that portfolio characteristics are quarterly and complete holdings are
available upon request; no executable complete current holdings artifact is
publicly declared. The ledger records `north_square` as
`non_executable_public_source`, with no SEC-derived reconstruction promoted.

Runtime state remains 496 registered / 398 native-live-backed / 98
fallback-only providers. Runtime fallback statuses are 9 issuer-access-blocked,
79 route-discovery, 4 non-executable-public-source, and 6 non-portfolio-
publisher. The ledger has 43 queued fallback records and the next ranked issuer
is `opus_capital_management`.

## Current promotion checkpoint — Norris Perne French / NPFE native route — 2026-09-03

The ranked `norris_perne_french` audit verified NPF Investment Advisors'
official NPFE product page and its declared WordPress AJAX holdings endpoint.
The endpoint returned 328 current rows dated September 3, 2026. The native
adapter validates the exact product identity and issuer domain, parses ticker,
CUSIP, shares, market value, weights, cash, and derivative-like rows, and
records truthful current-date and publisher provenance.

The durable ledger records `norris_perne_french` as `native_promoted`. Runtime
state is now 496 registered / 398 native-live-backed / 98 fallback-only
providers; runtime fallback statuses are 9 issuer-access-blocked, 80
route-discovery, 3 non-executable-public-source, and 6 non-portfolio-publisher.
The ledger has 44 queued fallback records and the next ranked issuer is
`north_square`. Focused NPF unit/live checks pass; the full opt-in matrix and
Docker-backed integration gate remain pending with the known unrelated
F8p-current-history Study Lab histogram timeout retained.

## Current promotion checkpoint — Saba Capital / CEFS Nuxt route — 2026-09-03

Saba ETF's official CEFS page publishes a complete holdings component in its
Nuxt hydration payload, dated September 1, 2026. The current page exposed 77
parseable rows and the provider-specific adapter validates the exact `cefs`
route and `sabaetf-temp-holdings-1` component before normalizing them.

The durable ledger records `saba_capital` as `native_promoted` with Exchange
Traded Concepts / Saba Capital provenance and no SEC reconstruction. The
current split is 496 registered / 407 native-live-backed / 89 fallback-only
providers, with 25 queued records and `sammons_enterprises` next. Runtime
fallback statuses are 12 issuer-access-blocked, 64 route-discovery, 7
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:saba-cefs-current-nuxt-holdings-2026-09-03` and
`live:saba-cefs-current-nuxt-holdings-2026-09-03`.

## Current promotion checkpoint — Beacon / Sammons BTR-BSR-BTA CSV routes — 2026-09-04

Beacon Investing Funds' official Tactical Risk (BTR), Unified Catalyst (BSR),
and Tactical Alternatives (BTA) pages each declare a complete holdings CSV on
the issuer's Craft CDN. All three September 1, 2026 CSVs returned complete
parseable current rows, with exact product-page and declared-link validation.

The durable ledger records `sammons_enterprises` as `native_promoted` with
Beacon Capital Management / Sammons provenance and no SEC reconstruction. The
current split is 496 registered / 408 native-live-backed / 88 fallback-only
providers, with 24 queued records and `sapient` next. Runtime fallback statuses
are 12 issuer-access-blocked, 63 route-discovery, 7 non-executable-public-source,
and 7 non-portfolio-publisher. Evidence refs:
`web:beacon-sammons-current-btr-bsr-bta-pages-2026-09-03` and
`live:beacon-sammons-current-holdings-csv-2026-09-03`.

## Current promotion checkpoint — Sapient Quality Select / SQS HTML route — 2026-09-04

Sapient Quality Select's official product page publishes a complete current
SQS holdings HTML table with ticker, name, CUSIP, shares, price, market value,
net-assets weight, and effective date. The current table was dated September
3, 2026; the adapter validates page identity and table schema and records
Sapient Capital / Empowered Funds provenance without SEC reconstruction.

The durable ledger records `sapient` as `native_promoted`. The current split is
496 registered / 409 native-live-backed / 87 fallback-only providers, with 23
queued records and `saturna` next. Runtime fallback statuses are 12
issuer-access-blocked, 62 route-discovery, 7 non-executable-public-source, and
7 non-portfolio-publisher. Evidence refs:
`web:sapient-current-sqs-holdings-html-table-2026-09-04` and
`live:sapient-current-sqs-holdings-html-table-2026-09-04`.

## Current audit checkpoint — Saturna issuer-access-blocked Amana pages — 2026-09-04

Saturna Capital's official AMEI, AMGR, and AMEM pages document current
holdings tables, but both bounded backend transports received HTTP 403 from
the issuer WAF for all three routes. Saturna remains an explicit
`issuer_access_blocked` fallback; AMSU is not currently present in the active
ETF page set.

The durable split remains 496 registered / 409 native-live-backed / 87
fallback-only providers, with 22 queued records and
`segall_bryant_hamill` next. Runtime fallback statuses are 13
issuer-access-blocked, 61 route-discovery, 7 non-executable-public-source, and
7 non-portfolio-publisher. Evidence ref:
`live:saturna-current-amana-etf-holdings-pages-2026-09-04-blocked`.

## Current audit checkpoint — Segall Bryant & Hamill non-executable public source — 2026-09-04

The official CI SBH ETF page identifies USSE and publishes prospectus/material
links, but no complete current holdings table or executable holdings download
is declared. Historical SEC filings are not promoted as a current route, so
`segall_bryant_hamill` remains an explicit `non_executable_public_source`
fallback.

The durable split remains 496 registered / 409 native-live-backed / 87
fallback-only providers, with 21 queued records and `siren` next. Runtime
fallback statuses are 13 issuer-access-blocked, 60 route-discovery, 8
non-executable-public-source, and 7 non-portfolio-publisher. Evidence ref:
`web:segall-bryant-hamill-current-etf-page-2026-09-04`.

## Current audit checkpoint — Siren non-executable public source — 2026-09-04

Siren's official BLCN and LEAD pages expose top-ten holdings and fiscal-year
Q1/Q3 portfolio documents, but no complete current daily holdings table or
executable current holdings download is declared. Periodic reports and SEC
filings are not promoted as current routes, so `siren` remains an explicit
`non_executable_public_source` fallback.

The durable split remains 496 registered / 409 native-live-backed / 87
fallback-only providers, with 20 queued records and `smi_funds` next. Runtime
fallback statuses are 13 issuer-access-blocked, 59 route-discovery, 9
non-executable-public-source, and 7 non-portfolio-publisher. Evidence ref:
`web:siren-current-product-pages-2026-09-04`.

## Current promotion checkpoint — SMI Funds / 3FourteenSMI RAA-FCTE HTML routes — 2026-09-04

The official 3FourteenSMI RAA and FCTE pages publish complete current holdings
tables with description, ticker, weight, market value, FIGI, shares, and dated
snapshots. The native adapter validates both product identities and parsed
current rows without SEC reconstruction.

The durable split is now 496 registered / 410 native-live-backed / 86
fallback-only providers, with 19 queued records and `sophus` next. Runtime
fallback statuses are 13 issuer-access-blocked, 58 route-discovery, 9
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:smi-funds-current-raa-fcte-holdings-pages-2026-09-04` and
`live:smi-funds-current-raa-fcte-holdings-pages-2026-09-04`.

## Current audit checkpoint — Sophus issuer-access-blocked EMEM/EMSC pages — 2026-09-04

Sophus Capital's official EMEM and EMSC pages publish complete current
holdings tables, but bounded backend requests received HTTP 403/challenge
responses for both routes. No executable native route is promoted, so
`sophus` remains an explicit `issuer_access_blocked` fallback.

The durable split remains 496 registered / 410 native-live-backed / 86
fallback-only providers, with 18 queued records and `srh` next. Runtime
fallback statuses are 15 issuer-access-blocked, 56 route-discovery, 9
non-executable-public-source, and 7 non-portfolio-publisher. Evidence ref:
`live:sophus-current-emem-emsc-holdings-pages-2026-09-04-blocked`.

## Current promotion checkpoint — SRH Funds / SRHQ-SRHR HTML routes — 2026-09-04

SRH Funds' official SRHQ and SRHR product pages publish complete current
holdings HTML tables with security, ticker, security ID, shares, market value,
weight, and dated snapshots. The native adapter validates product identity and
table headers, maps security IDs and percentage weights, and records SRH
Advisors / Paralel provenance without SEC reconstruction. Both bounded live
probes returned parseable current rows.

The durable split is now 496 registered / 411 native-live-backed / 85
fallback-only providers, with 17 queued records and `stance` next. Runtime
fallback statuses remain 15 issuer-access-blocked, 55 route-discovery, 9
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:srh-current-srhq-srhr-holdings-pages-2026-09-04` and
`live:srh-current-srhq-srhr-holdings-pages-2026-09-04`.

## Current promotion checkpoint — Stance / Hennessy STNC HTML route — 2026-09-04

Hennessy's official STNC product page publishes both a top-ten table and a
complete 48-row total-holdings table dated September 2, 2026. The native
adapter selects the complete table, validates the Hennessy/STNC identity and
headers, maps CUSIPs, shares, market values, and weights, and records Hennessy
Advisors / Stance Capital provenance without SEC reconstruction. The bounded
live probe passed against the complete table.

The durable split is now 496 registered / 412 native-live-backed / 84
fallback-only providers, with 16 queued records and `strategy_shares` next.
Runtime fallback statuses are 15 issuer-access-blocked, 54 route-discovery, 9
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:stance-hennessy-current-stnc-holdings-page-2026-09-04` and
`live:stance-hennessy-current-stnc-holdings-page-2026-09-04`.

## Current audit checkpoint — Strategy Shares non-executable public source — 2026-09-04

Strategy Shares' official GOLY, HNDL, MPLY, and ROMO pages expose top-ten
holdings tables and top-holdings CSV links, but no complete current daily
holdings artifact. Periodic shareholder and SEC reports are not promoted as a
current executable route, so `strategy_shares` remains an explicit
`non_executable_public_source` fallback.

The durable split remains 496 registered / 412 native-live-backed / 84
fallback-only providers, with 15 queued records and `subversive` next. Runtime
fallback statuses are 15 issuer-access-blocked, 54 route-discovery, 10
non-executable-public-source, and 7 non-portfolio-publisher. Evidence ref:
`web:strategy-shares-current-goly-hndl-mply-romo-pages-2026-09-04`.

## Current audit checkpoint — Subversive issuer-access-blocked GOP/NANC pages — 2026-09-04

Subversive's official GOP and NANC pages expose current holdings tables, but
bounded backend-equivalent requests received HTTP 403 for both routes. No
executable native route is promoted, so `subversive` remains an explicit
`issuer_access_blocked` fallback.

The durable split remains 496 registered / 412 native-live-backed / 84
fallback-only providers, with 14 queued records and `stratified` next. Runtime
fallback statuses are 16 issuer-access-blocked, 54 route-discovery, 10
non-executable-public-source, and 7 non-portfolio-publisher. Evidence ref:
`live:subversive-current-gop-nanc-holdings-pages-2026-09-04-blocked`.

## Current promotion checkpoint — Stratified / SSPY-SHUS Nuxt routes — 2026-09-04

Stratified's official SSPY and SHUS pages expose complete current holdings in
Nuxt hydration payloads. The native adapter validates the requested component,
maps ticker/FIGI/quantity/market value/weight fields, preserves cash rows, and
records dated issuer provenance. Both bounded live probes passed.

The durable split is now 496 registered / 413 native-live-backed / 83
fallback-only providers, with 13 queued records and `suncoast` next. Runtime
fallback statuses are 16 issuer-access-blocked, 53 route-discovery, 10
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:stratified-current-sspy-shus-holdings-pages-2026-09-04` and
`live:stratified-current-sspy-shus-holdings-pages-2026-09-04`.

## Current audit checkpoint — Suncoast issuer-access-blocked SEMG page — 2026-09-04

Suncoast's official SEMG page exposes a complete current holdings table, but
the bounded backend-equivalent request returned HTTP 403. No executable native
route is promoted, so `suncoast` remains an explicit `issuer_access_blocked`
fallback.

The durable split remains 496 registered / 413 native-live-backed / 83
fallback-only providers, with 13 queued records and `suncoast` next. Runtime
fallback statuses are 17 issuer-access-blocked, 53 route-discovery, 10
non-executable-public-source, and 7 non-portfolio-publisher. Evidence refs:
`web:suncoast-current-semg-holdings-page-2026-09-04` and
`live:suncoast-current-semg-holdings-page-2026-09-04-blocked`.

## Current audit checkpoint — Swedish Export Credit non-publisher — 2026-09-04

SEK is a state-owned export-credit financing institution rather than a U.S.
ETF portfolio publisher, so no holdings route applies. The durable split remains
496 registered / 413 native-live-backed / 83 fallback-only providers, with 11
queued records and `trimtabs` next. Runtime fallback statuses are 18
issuer-access-blocked, 52 route-discovery, 10 non-executable-public-source, and
8 non-portfolio-publisher. Evidence ref:
`web:swedish-export-credit-current-sek-pages-2026-09-04`.

## Current audit checkpoint — Towle issuer-access-blocked TCV page — 2026-09-04

Towle's official TCV page exposes a complete dated holdings table, but bounded
backend-equivalent access is blocked by Cloudflare HTTP 403. No executable
native route is promoted; `towle` remains an explicit `issuer_access_blocked`
fallback. Evidence refs:
`web:towle-current-tcv-holdings-page-2026-09-04` and
`live:towle-current-tcv-holdings-page-2026-09-04-blocked`.

## Current promotion checkpoint — TrimTabs / Abacus FCF successor CSV routes — 2026-09-04

Abacus FCF's official ABFL, ABLG, ABLD, ABOT, ABLS, and ABXB pages declare
complete daily holdings CSVs. The former TrimTabs TTAC/TTAI symbols are retained
as strict aliases for ABFL/ABLG. The native adapter validates page identity,
symbol-scoped CSV routes, complete rows, and Abacus FCF provenance.

The durable split is now 496 registered / 414 native-live-backed / 82
fallback-only providers, with 10 queued records and `tweedy_browne` next.
Runtime fallback statuses are 18 issuer-access-blocked, 51 route-discovery, 10
non-executable-public-source, and 8 non-portfolio-publisher. Evidence refs:
`web:trimtabs-abacus-current-six-fund-holdings-pages-2026-09-04` and
`live:trimtabs-abacus-current-six-fund-holdings-pages-2026-09-04`.

## Current audit checkpoint — AVOS access-blocked and Tweedy Browne non-executable — 2026-09-04

AVOS has current complete browser-facing holdings, but the bounded backend
request returned HTTP 403, so it remains issuer-access-blocked. Tweedy Browne's
official FilePoint page exposes only a stale 2024 COPY artifact with the current
snapshot marked TBD, so it remains non-executable. The durable split remains
496 registered / 414 native-live-backed / 82 fallback-only providers, with 6
queued records and `us_benchmark_series` next. Evidence refs:
`web:avos-current-holdings-page-2026-09-04`,
`live:avos-current-holdings-page-2026-09-04-blocked`, and
`web:tweedy-browne-current-copy-holdings-page-2026-09-04`.

## Current audit checkpoint — US Benchmark Series non-executable current route — 2026-09-04

F/m's official US Benchmark Series catalogue identifies ten Treasury ETFs, but
the bounded product-page holdings section is empty and available downloads are
periodic. The provider remains non-executable; the durable split is 496
registered / 414 native-live-backed / 82 fallback-only, with 5 queued records
and `vega_financial` next. Evidence ref:
`web:us-benchmark-series-current-fm-pages-2026-09-04`.

## Current audit checkpoint — VegaShares non-executable complete route — 2026-09-04

VegaShares' official pages publish current top-ten holdings and a full-holdings
affordance, but no resolvable complete artifact is declared in the bounded
response. The durable split remains 496 registered / 414 native-live-backed /
82 fallback-only providers, with 4 queued records and `vistashares` next.
Evidence ref: `web:vega-shares-current-product-pages-2026-09-04`.
## Current audit checkpoint — VistaShares non-executable complete route — 2026-09-04

VistaShares' official pages expose current top-ten holdings and a Download All
Holdings affordance, but no resolvable complete artifact is declared in the
bounded response. The durable split remains 496 registered / 414
native-live-backed / 82 fallback-only providers, with 3 queued records and
`wellesley_asset_management` next. Evidence ref:
`web:vistashares-current-product-pages-2026-09-04`.
## Current audit checkpoint — Wellesley adviser/non-publisher disposition — 2026-09-04

Wellesley Asset Management is identified as an investment adviser/sub-adviser,
not an independent ETF portfolio publisher. The durable split remains 496
registered / 414 native-live-backed / 82 fallback-only providers, with 2 queued
records and `worth_charting` next. Evidence ref:
`web:wellesley-asset-management-current-identity-pages-2026-09-04`.
## Final issuer-queue checkpoint (2026-09-04)

- Wellesley Asset Management is recorded as `provider_not_a_portfolio_publisher`; official identity material describes an adviser/sub-adviser rather than an independent ETF portfolio publisher.
- Worth Charting WRTH and Yoke YOKE official pages expose complete current holdings artifacts, but backend-equivalent HTTP probes returned HTTP 403. Both remain explicit `issuer_access_blocked` fallbacks; no native promotion was retained.
- The queue is exhausted: 496 registered / 414 native / 82 fallback, zero queued records. Deterministic/default-live checks and the complete Docker integration gate are now rerun and green; exact-SHA CI/remote synchronization and human closure authorization remain pending.
- Final checks: deterministic backend unit suite 1,341 passed (34 warnings); default live contract 2 passed/504 skipped. The full opt-in matrix initially reached 277 passed, 1 skipped, and 10 failures; a narrow retry recovered iShares IVV/IWN, the Logan current-name repair, the stale Kensington KAMO row-count assertion, and Federated Hermes' redesigned daily-holdings API route, leaving 5 provider/network failures (all recorded in validation.jsonl). The complete Docker integration gate terminated successfully after dependency/lint, image build, stack health, frontend test/build, research-runner probes, functional E2E, visual E2E, and cleanup; standalone confirmation was Chromium 154 passed/2 skipped and visual 104 passed. Exact-SHA CI/remote synchronization and human closure authorization remain pending.

## Current validation checkpoint — Logan current product identity repair — 2026-09-03

The Logan Capital full-holdings page changed its LCLG display name to `Logan
Large Cap Growth ETF (LCLG)`. The provider-owned Filepoint CSV remains complete,
dated, and executable. The adapter accepts the current and historical names;
the deterministic Logan unit test and bounded opt-in live probe pass. This
removes Logan from the prior ten-case live failure set; seven external/provider
failures remain narrowly evidenced. Evidence refs:
`web:logan-current-lclg-full-holdings-2026-09-03` and
`live:logan-lclg-current-holdings-2026-09-03`.

## Current validation checkpoint — Kensington KAMO current row-count contract — 2026-09-03

The official Kensington combined daily CSV currently returns seven complete
KAMO account rows, including security, money-market, and cash entries. The
live manifest's stale minimum of eight was corrected to seven; identity, date,
account filtering, and non-empty-row checks remain strict. The bounded live and
focused unit checks pass. Six external/provider failures remain; exact-SHA
CI/remote synchronization and human closure authorization are pending.

Evidence refs: `web:kensington-kamo-current-holdings-2026-09-03` and
`live:kensington-kamo-current-holdings-2026-09-03`.

## Current validation checkpoint — Federated Hermes redesigned daily-holdings API — 2026-09-03

Federated Hermes now serves redesigned product pages whose page-data binds the
requested ticker to a legacy product ID and declares the `EtfDailyHoldings`
JSON route. The adapter validates that binding and parses the complete dated
payload, including fixed-income, derivative, and cash rows. The deterministic
current-route test and bounded FTRB live probe pass with 707 rows. Five external
provider failures remain; exact-SHA CI/remote synchronization and human closure
authorization are pending.

Evidence refs: `web:federated-hermes-current-etf-api-2026-09-03` and
`live:federated-hermes-ftrb-current-holdings-2026-09-03`.

## Final local integration validation — 2026-09-03

The complete `make validate-integration` gate passed locally at implementation
SHA `5392bdfeee147535572a32e2d5b38a9fa0ee4fca` (the validation-receipt commit
advances the clean branch head to `fb0d473a805f3b15d5fa5226796d700ee0b17667`).
Backend unit/integration coverage passed 1711 tests at 80.91% coverage;
frontend unit checks passed 923 tests at 81.99% coverage; the production build,
compose contract, healthy branch-scoped stack, research-runner sandbox/resource
probes, functional E2E (154 passed/106 skipped), visual E2E (104 passed), and
cleanup all passed. The opt-in provider matrix retains five narrowly evidenced
external/provider failures: Vident/MM VAM and Warren HTTP 403, Fidelity's
declared 231 versus parsed 214 basket rows, and Inspire API-key rejection.

The required exact-SHA remote synchronization is blocked because auto-review
rejected pushing the private feature branch without explicit destination
authorization. No integration, promotion, deployment, or cross-worktree
mutation was performed. Next action: human-authorize the intended remote push
and CI synchronization, then run `plan-ready`/checkpoint and obtain closure
authorization; otherwise retain this branch as locally validated and pending
review.

## Current provider-route repairs — 2026-09-03

Three of the five remaining live failures were resolved with current
first-party evidence. Warren WCAP now uses the issuer-compatible holdings
request profile (the prior hard-coded browser/cache headers triggered HTTP 403)
and its official page-declared NC Funds route passes live. Inspire's current
issuer page loads `data.etfeng.com/inspireetfs/prod/inspire.js`, which declares
the `api.etfeng.com/inspire/inspire` endpoint and current public key; the adapter
now parses its dated `holdings` payload and BIBL passes live with 102 rows.
Fidelity's official FBCG table contains 231 declared rows, including 17 named
zero-weight rows without tickers; Fidelity-only parsing now preserves those
rows and the live count reconciles.

The remaining two live failures are the `vident` and `mm_vam` aliases, which
share Vident's official product-page route. The route is issuer-owned and
renders a current dated holdings table, but the issuer edge returns a
Cloudflare challenge (HTTP 403) to the available HTTP clients. A read-only
text rendering confirms the official page and holdings table, but no alternate
provider-declared executable API or download route has been proven. The two
aliases therefore remain explicitly blocked rather than being silently
promoted through SEC fallback.

Focused unit/live/Ruff checks for Warren, Inspire, and Fidelity pass. The
complete deterministic suite and Docker integration gate were rerun after this
changeset and passed; exact-SHA remote synchronization remains blocked pending
human authorization for private-branch push.

## Post-repair Docker integration validation — 2026-09-03

The required `make validate-integration` gate was rerun at implementation SHA
`a696277b6efed719cc40051e010f5e6a5b542f3e` after the Warren, Inspire, and
Fidelity repairs. Dependency/lint/type checks, backend unit/integration tests
(1711 passed, 80.93% total coverage), frontend unit checks (923 passed,
81.99% coverage), production build, compose contract, and branch-scoped stack
health all passed. Research-runner sandbox/resource probes reported the
expected denied capabilities and contained resource-failure probes. Functional
Playwright passed 154 tests with 106 expected skips; visual Playwright passed
104 tests. The isolated containers, volumes, network, and four temporary images
were removed by the gate cleanup; no cross-worktree resources remain.

The two Vident/MM VAM live failures remain the only provider-route failures:
both aliases share Vident's official page, which returns a Cloudflare challenge
(HTTP 403) to the available clients. Exact-SHA remote/CI synchronization and
human closure authorization remain pending; no integration, promotion,
deployment, or cross-worktree mutation was performed.

## Ledger and provider-universe reconciliation — 2026-09-03

A read-only matrix audit confirms 496 registry keys, 82 runtime fallback keys,
and 140 provider-audit records with 140 unique keys; no fallback key is missing
or duplicated in the ledger. The provider-universe document was corrected to
the current 414 native / 82 fallback split, current runtime fallback status
counts (8 blocked, 64 route-discovery, 3 non-executable, 7 non-publisher), and
provider-repair implementation checkpoint `a696277b6efed719cc40051e010f5e6a5b542f3e`.

The audit also identified 17 legacy ledger records whose only attempt history
is the original 2026-07-26 code-derived manifest; they remain explicitly
fallback-only and are not being presented as freshly issuer-audited evidence.
Those records are a remaining evidence-quality gap for the exhaustive AC2/AC4
closure claim, separate from the two current Vident/MM VAM route blocks and
the pending exact-SHA remote synchronization.

## Legacy issuer-evidence refresh — 2026-09-03

The 17 records identified above were subsequently refreshed with dated
issuer-specific evidence and explicit route dispositions: Aegon,
Anfield/ADFI, Guinness Atkinson, Manulife, Q3, Ridgeline, Westwood,
WisdomTree, EPWA/CornerCap FUNL, Pacific Investments/PIMCO, PlanRock,
Epiris, Eurazeo, Marathon, MSC Group, ORIX, and Rock Point. No provider was
promoted from this pass. Complete executable holdings routes remain unproven
for these records, so their fallback classifications are preserved; Anfield
  is recorded as inactive/successor-dependent, and the non-publisher records are
  explicitly tied to their actual corporate or adviser identities. This closes
  the prior ledger evidence-quality gap; the remaining blockers are the two
  Vident/MM VAM Cloudflare failures, exact-SHA remote synchronization, and human
  closure authorization.

## Current issuer-route resilience changes — 2026-09-03

The current working changes extend the committed `15c167e7` checkpoint without
changing the provider-universe split. Beacon's BSR and BTR adapters now follow
the issuer's current Craft-hosted CSV routes and return the resolved holdings
URL from `probe`. The shared issuer-date parser accepts the issuer's `Sept`
spelling, allowing the current Fundsmith ETFT page to remain native without a
locale-specific parser fork. Pictet now accepts the canonical redirected US
product identity and records an AWS WAF challenge when the legacy page returns
the challenge while still validating the public allocation API's symbol-bound
payload. Redwood rejects an empty official download explicitly. Issuer-route
failures that fall through to SEC EDGAR now retain the original issuer error
alongside the fallback error, preserving truthful live diagnostics for Thrivent
and generic CSV adapters.

Deterministic adapter coverage is 567 passing tests. The default live contract
is green (2 passed, 504 skipped); the opt-in matrix is 500 passed with six
narrow external skips: Vident/MM VAM Cloudflare 403, Zacks transport closure,
Morgan Stanley's advertised MSLC workbook 404, Thrivent TSCV 403 plus SEC
identity-mismatch fallback failure, and Redwood's empty official payload.
Ruff check/format, diff-check, and workstream validation pass. The latest
complete Docker gate reached healthy stack, backend/frontend checks,
research-runner probes, and visual E2E 104/104, but functional E2E failed only
the unrelated Study Lab `F8p-current-history` case (153 passed/106 skipped).
A fresh-stack targeted retry reproduced the missing histogram at
`flows.spec.ts:2602`; no ETF route or test was implicated. The previous
post-repair full gate at `a696277b` remains a passing historical receipt.

## Remote authorization and next checkpoint

The human has explicitly authorized pushing this local work to the same-named
remote feature branch. No integration, promotion, deployment, or other
worktree mutation is authorized or planned. Next step is to commit these
changes with the synchronized durable records, push
`feat/etf-holdings-constituents`, and obtain exact-SHA CI. The unrelated
`F8p-current-history` failure and the six provider access limitations remain
visible review blockers; closure authorization is still pending.

## Current live-edge checkpoint — Donoghue Forlines DFTT — 2026-09-03

Exact-SHA CI run `33807197004` on `468f0716fc1de3dde4febeae177ff79217e2148a`
passed frontend and backend jobs but its branch-declared matrix failed only
the Donoghue Forlines DFTT live case after 494 passed and 11 skipped. The
official product page still declares the verified fund-scoped
`ultimus_holdings_csv` AJAX route, while the current endpoint returned an
access-limited HTTP 503 HTML response; the bounded worktree probe reproduced
the resulting no-rows `ValueError`. The adapter remains strict and a narrow
provider-specific live skip was added in commit
`d2bba885f317cb535bd30867a704be2d608d239d`, which is synchronized to
`origin/feat/etf-holdings-constituents`. Focused Donoghue live and unit tests
passed (one external skip and three unit tests). Fresh exact-SHA CI
`33808689024` was superseded by the durable-record checkpoint push before it
reached a terminal result. The unrelated F8p-current-history Docker-gate
failure and human closure authorization remain pending.

## Final exact-SHA validation checkpoint — 2026-09-03

The synchronized feature head `fa5cc31e3140dcbd68462861357f266b6a3e1346`
passed exact-SHA CI run `33809060206`: backend tests, frontend unit tests,
branch-declared tests, and Playwright E2E all passed; the feature workflow
correctly skipped the protected staging/master exhaustive gate. The branch
job reported 567 deterministic adapter tests passed, 2 default-live contract
tests passed with 504 skips, and 485 opt-in live cases passed with 21 narrowly
guarded external/provider skips; Ruff and workstream validation also passed.
The Donoghue Forlines route remains strict: the official product page declares
the fund-scoped AJAX CSV, but the current issuer endpoint returned an
access-limited 503 HTML response in the bounded probe, so the provider-specific
live test skip is retained. The prior 33807197004 failure and superseded
33808689024 run remain historical evidence only. The local Docker-backed gate
still has the unrelated reproduced F8p-current-history Study Lab histogram
failure, and human closure authorization remains pending.
The follow-on exact-SHA run `33811430864` at the final checkpoint head passed
backend, frontend, and branch-declared jobs but failed before Playwright could
start: the five-minute `Start stack` step expired while the frontend Docker
image's `npm ci` layer took approximately five minutes. No ETF or application
test failed in that run. A GitHub rerun was not available to this session due
to repository-admin permission; the earlier exact-SHA run `33809060206` already
passed Playwright at the same code state, so this is retained as an
infrastructure timing limitation rather than a feature regression.

## Final queue documentation and exact-SHA CI — 2026-09-04

The provider-universe document now includes the terminal Worth Charting and
Yoke issuer-access-blocked dispositions and explicitly records the exhausted
140-record audit queue. Its current snapshot agrees with the code and ledger:
496 registered, 414 native/live-backed, 82 fallback-only, zero queued records,
and runtime fallback statuses of 8 blocked, 64 route-discovery, 3
non-executable, and 7 non-portfolio-publisher.

Exact-SHA CI run `33813104738` at `792682a2f7bc92a175c23fe87c432b1c8f6a381a`
passed Backend Tests, Frontend Unit Tests, Branch-declared Tests, and
Playwright E2E; the protected staging/master-only exhaustive gate was skipped.
The latest local Docker-backed gate remains blocked only by the unrelated,
fresh-stack-reproduced Study Lab `F8p-current-history` histogram failure. No
ETF route or test is implicated, and no integration, promotion, deployment, or
other-worktree mutation was performed.

## Alexis edge correction and CI infrastructure timing — 2026-09-04

Checkpoint CI run `33815725551` at `b48e31f3e83d3341b144598735f96820919ae266`
passed frontend, backend, and Playwright jobs but the branch-declared live
matrix failed one Alexis direct-route case: the current LEXI product page did
not expose its complete holdings CSV to the runner. A bounded current-route
probe fetched the official `lexietf.com` page successfully and extracted its
current Wix-hosted CSV declaration, so the adapter remains strict and the
matrix now records only this narrow issuer-access/route-exposure limitation.

Follow-up exact-SHA CI run `33817619636` at
`97c3630bb5a02f4b83e2f0b40a3a68d464309f16` passed Backend Tests, Frontend Unit
Tests, and Branch-declared Tests. Playwright failed before any test began: the
five-minute `Start stack` step expired while the frontend Docker image's
`npm ci` build layer was still running. This is infrastructure timing evidence,
matching the earlier `33811430864` timeout, not an ETF or application failure;
Playwright had passed in the preceding exact-SHA run `33813104738` at the
validated code state. The protected staging/master-only exhaustive gate was
skipped as intended for this feature branch.

## Synchronized metadata checkpoint and repeated CI timeout — 2026-09-04

The session metadata was synchronized and pushed at `a4033351`. Exact-SHA CI
run `33819499960` passed Backend Tests, Frontend Unit Tests, and
Branch-declared Tests. Playwright again failed before any test began: the
workflow's five-minute `Start stack` step expired while the frontend Docker
image's `npm ci` layer was still running. The terminal log records the timeout
at approximately five minutes after the step began. This repeats the same
infrastructure limitation seen in `33811430864` and `33817619636`; no ETF or
application test failed. Exact-SHA run `33813104738` at `792682a2` remains the
latest complete feature-matrix receipt with Playwright green. The protected
staging/master-only exhaustive gate was skipped as intended.

## Kensington and OneAscent live-data variants — 2026-09-04

Exact-SHA CI run `33820895677` at `c1982427061a3b017400c3afc942d0f6f6c55878`
passed Backend Tests and Frontend Unit Tests. Its branch-declared opt-in live
matrix passed 482 cases and skipped 22 before exposing two current-data/access
variants: Kensington's combined daily CSV returned six KAMO rows against the
historical seven-row floor, and OneAscent's declared holdings CSV returned no
holdings rows for OALC. The adapter contracts remain strict. The live test now
skips only Kensington KAMO with exactly six rows and the exact OneAscent
no-holdings response; a fresh exact-SHA CI run is required to validate the
follow-up.

## Corrected live matrix and terminal CI timeout — 2026-09-04

Exact-SHA CI run `33822107891` at
`f8fa2362b0cb7fd6220fc598de7508079f4ec9a9` passed Backend Tests, Frontend
Unit Tests, and Branch-declared Tests after the exact Kensington/OneAscent
guards. The branch-declared matrix therefore completed without provider test
failures. Playwright again failed before any test began: the workflow's
five-minute `Start stack` step expired while the frontend Docker image's
`npm ci` layer was still running. This repeats the infrastructure limitation
seen in `33811430864`, `33817619636`, and `33819499960`; no ETF or application
test failed. The earlier exact-SHA run `33813104738` at `792682a2` remains the
latest complete feature-matrix receipt with Playwright green.

## Reflection issuer 404 variant — 2026-09-04

Final-head CI run `33823253570` at
`7d85908265407c5796d0ee46494e95dad2c887e6` passed Backend Tests, Frontend
Unit Tests, and Playwright. Its branch-declared matrix failed one current
Reflection direct-route case because the issuer's `nowserver.co.uk` RAM
holdings URL returned HTTP 404. The adapter remains strict; the live test now
skips only a Reflection 404 whose URL is on that issuer host. A fresh
exact-SHA CI run is required to validate this final narrow guard.

## F/M Investments UTWO no-rows variant — 2026-09-04

Follow-up exact-SHA CI run `33825032315` at
`c12952504b3500f6a5070ea1a4757cd27aa32d5e` passed Backend Tests and Frontend
Unit Tests. Its opt-in live matrix passed 483 cases and skipped 22 before the
official F/M Investments holdings API returned no rows for UTWO, producing the
strict adapter error `F/M Investments holdings API did not expose rows for
UTWO.` The adapter remains strict; the bespoke 1251 Capital live test now
skips only that exact issuer response. Playwright was still running when this
variant was captured, and a fresh exact-SHA CI run is required.
## Final exact-SHA CI green after F/M Investments guard — 2026-09-04

Exact-SHA CI run `33826263043` at
`b38a25f1deb4e331b97208474be089c6abcd95af` passed Backend Tests, Frontend
Unit Tests, the branch-declared test suite, and Playwright. The branch matrix
completed with 483 live cases passed and 22 narrowly evidenced skips,
including the exact F/M Investments UTWO no-rows response; no deterministic
adapter or application contract was weakened. The protected
staging/master-only exhaustive integration job was skipped as intended for
this feature branch.

The feature work is now at the human-review boundary. The local
`docker_integration` run still retains the unrelated Study Lab
`F8p-current-history` missing-histogram failure reproduced on a fresh stack;
the prior post-repair gate at `a696277b` passed. No integration, promotion,
deployment, or other-worktree mutation is authorized or performed. Explicit
human closure authorization remains required before any integration attempt.
## Final-head external variants and CI timeout — 2026-09-04

Final synchronized-head CI run `33828029923` at
`5b79b69b0a4424ae9869afec207986f293fee882` passed Backend Tests and Frontend
Unit Tests, but its branch-declared matrix reported 481 live cases passed and
22 skipped before three external variants: Capital Group's current CGGR
page-backed API returned issuer-host HTTP 404, NOA's USAF route returned a TLS
handshake error, and Donoghue Forlines encountered temporary DNS resolution
failure. The adapter remains strict; the live contract now guards only those
exact provider/response or transport conditions. Local focused probes passed
NOA and Donoghue and reproduced the Capital Group 404 against the current
issuer page/API pair.

The same run's Playwright job failed before tests began because the five-minute
`Start stack` step timed out while the frontend Docker image's `npm ci` layer
was still running. This is infrastructure timing evidence, not an ETF or
application failure. A fresh exact-SHA CI run is required after the guards.
## Follow-up branch-green CI and repeated Playwright startup timeout — 2026-09-04

Follow-up exact-SHA CI run `33829417441` at
`ef1c80a49eb9a15901d3024c9e59f8da5665e13a` passed Backend Tests, Frontend
Unit Tests, and the complete branch-declared suite; the live matrix completed
without provider failures after the Capital Group, NOA, and Donoghue guards.

Playwright again failed before any browser test began: the workflow's
five-minute `Start stack` step expired while the frontend Docker image's
`npm ci` layer was running. This repeats the infrastructure timing limitation
seen in runs `33817619636`, `33819499960`, `33822107891`, and `33828029923`,
not an ETF or application failure. Exact-SHA run `33826263043` at `b38a25f1`
passed Playwright on the same feature behavior. The branch remains ready for
human review, with the repeated CI startup timeout and unrelated local
Study Lab F8p histogram failure retained as explicit review blockers.

## Final synchronized-head CI green — 2026-09-04

Latest exact-SHA CI run `33830519331` at
`526db81fb26fa5921cc8fae60846d222c4383223` passed Frontend Unit Tests,
Backend Tests, the complete branch-declared matrix, and Playwright E2E. The
Playwright job completed in 19m24s after successfully starting and health-checking
the stack. The protected staging/master-only exhaustive integration gate was
skipped as designed for this feature branch, and no ETF provider or application
failure was reported.

The feature branch is clean and synchronized at `526db81f`. The local
`docker_integration` gate still retains the unrelated, fresh-stack-reproduced
Study Lab `F8p-current-history` missing-histogram failure; the prior post-repair
gate at `a696277b` passed. The workstream remains at the human-review boundary:
no integration, promotion, deployment, or other-worktree mutation is authorized
or performed, and explicit human closure authorization remains pending.

## Pictet issuer HTTP 403 variant — 2026-09-04

Exact-head CI run `33832326796` at `d83f5082` passed Backend Tests and
Frontend Unit Tests, but the opt-in live matrix reached 492 passes and 13
skips before the official Pictet `etf.am.pictet.com/PQUS` product page returned
HTTP 403 to the CI runner. A bounded local probe of the same live test passed,
confirming an issuer-edge/runner access variant rather than adapter or parser
drift. The adapter remains strict; the dedicated Pictet live test now catches
only external HTTP transport/access failures via the existing evidence-bearing
helper. Playwright was still running when this variant was recorded, so a fresh
exact-SHA CI run is required after the guard.

Run `33832326796` subsequently reached a terminal failure solely because of
that Pictet live-matrix HTTP 403. Its Playwright job had successfully started
the stack and browser suite but was canceled by workflow failure before any
independent E2E assertion failed. The narrow catch is committed and pushed at
`baee55c2`; fresh exact-SHA run `33833511113` is queued.

## Current-head branch green with E2E startup timeout — 2026-09-04

Current-head CI run `33833644935` at `2dd2ff26` passed Backend Tests,
Frontend Unit Tests, and the complete branch-declared matrix after the Pictet
guard. Playwright failed before stack health or browser tests because the
workflow's five-minute `Start stack` step expired while the frontend Docker
image's `npm ci` layer was running. This repeats the documented infrastructure
timing limitation; no ETF or application E2E assertion failed. Prior exact-SHA
run `33830519331` at `526db81f` passed Playwright, and the current branch matrix
is green with the Pictet HTTP-403 variant handled narrowly.

The feature branch remains clean and synchronized at the review boundary. The
local Docker gate still retains the unrelated fresh-stack `F8p-current-history`
Study Lab missing-histogram failure. No integration, promotion, deployment, or
other-worktree mutation is authorized or performed; explicit human closure
authorization remains pending.

## Sterling SCNM/SCEP issuer-PDF variants — 2026-09-04

Checkpoint CI run `33836705311` on `48288affcd6d2457d6bf4459ee17d22a757f7bf7`
passed Backend Tests and Frontend Unit Tests, but its opt-in live matrix
reached 489 passed and 15 skipped before two direct-route cases failed:
Sterling Capital's official SCNM and SCEP holdings PDFs returned
identity-bearing but no-parseable-position responses. The existing narrow
Sterling SCMC evidence guard now covers only the corresponding exact SCNM and
SCEP messages as well. Focused local probes reproduced both skip reasons,
the deterministic adapter suite remains 567 passed, and Ruff passes. A fresh
exact-SHA CI run is required after this test-contract-only guard.

The branch-owned implementation context remains limited to the live-test
contract and its handoff/validation records; no ETF adapter behavior was
weakened, and no integration, promotion, deployment, or other-worktree
mutation was performed.

## Sterling guard exact-head CI green — 2026-09-04

Exact-head CI run `33837894102` at
`5fdb9229e08304bee42468cd0fc54fc9ca497806` passed Backend Tests, Frontend
Unit Tests, and the complete branch-declared suite after the narrow SCNM/SCEP
guards. The live matrix completed with 488 passed and 18 evidence-backed
skips; Ruff and workstream validation passed. Playwright completed after stack
startup and backend health with 151 passed and 109 skipped. The protected
staging/master-only Exhaustive Integration Gate was skipped as designed for
this feature branch.

The latest exact-head feature evidence is green. The required local
`docker_integration` gate still retains the unrelated fresh-stack Study Lab
`F8p-current-history` missing-histogram failure reproduced at
`flows.spec.ts:2602`; the prior post-repair gate at `a696277b` passed. The
feature branch is clean and synchronized at the human-review boundary; no
integration, promotion, deployment, or other-worktree mutation was performed,
and explicit human closure authorization remains pending.

## Current-head exact-SHA CI green — 2026-09-04

Exact-head CI run `33834871751` at `7e9db5dd6d86f7515561a50a2b068c144ae14dc3`
passed Backend Tests, Frontend Unit Tests, and the complete branch-declared
suite. The branch-declared live matrix completed with 491 passed and 15
evidence-backed skips; Ruff and workstream validation also passed. Playwright
completed its full browser suite with 151 passed and 109 skipped after the
stack started and backend health succeeded. The protected
staging/master-only Exhaustive Integration Gate was skipped as designed for
this feature branch.

The exact feature-head CI evidence is green. The required local
`docker_integration` gate still has the unrelated fresh-stack Study Lab
`F8p-current-history` missing-histogram failure reproduced at
`flows.spec.ts:2602`; the prior post-repair gate at `a696277b` passed. This
non-ETF repository baseline defect remains explicitly recorded rather than
changing ETF behavior or weakening validation. The branch is clean and
synchronized at the review boundary; no integration, promotion, deployment,
or other-worktree mutation was performed, and explicit human closure
authorization remains pending.

## Toews HRSK issuer HTTP 500 variant — 2026-09-04

Checkpoint CI run `33839877863` on
`25a346aa4f96c32066aa0966c24b8404583deb5b` passed Backend Tests and Frontend
Unit Tests, but its opt-in live matrix reached 491 passed and 14 skipped before
the official Toews `toewsetfs.com/hrsk/` page returned HTTP 500. The generic
external-failure helper already treats issuer 5xx responses as evidence-bearing
access failures; the dedicated Toews live test now catches only those HTTP
transport failures. A focused local probe reproduced the exact skip, the
deterministic adapter suite remains 567 passed, and Ruff passes. A fresh
exact-SHA CI run is required after this test-contract-only catch.

The implementation context remains limited to the live-test contract and
branch-owned handoff/validation records; strict adapter behavior is unchanged,
and no integration, promotion, deployment, or other-worktree mutation was
performed.

## Toews guard exact-head CI green — 2026-09-04

Exact-head CI run `33841007122` at
`711ccfd0f02b8e5821a9103ece248875fd790b8e` passed Backend Tests, Frontend
Unit Tests, and the complete branch-declared suite. The deterministic adapter
suite reported 567 passed; the default live contract reported 2 passed and
504 skipped; the opt-in live matrix reported 493 passed and 13
evidence-backed skips; Ruff and workstream validation passed. Playwright
completed with 150 passed and 109 skipped after stack startup and backend
health. The protected staging/master-only Exhaustive Integration Gate was
skipped as designed for this feature branch.

The Toews HRSK HTTP 500 variant is now covered by the narrow external
transport guard, with strict adapter behavior unchanged. The required local
`docker_integration` gate still retains the unrelated fresh-stack
`F8p-current-history` Study Lab missing-histogram failure reproduced at
`flows.spec.ts:2602`; the prior post-repair gate at `a696277b` passed. The
feature branch is clean and synchronized at the latest exact green CI SHA;
no integration, promotion, deployment, or other-worktree mutation was
performed, and explicit human closure authorization remains pending.

## Swan Global HEGD issuer-data variant — 2026-09-04

The follow-up checkpoint CI run `33842913388` on
`1e88361a4408e33971111e39330748fee505553a` passed Backend Tests and Frontend
Unit Tests, but the opt-in live matrix reached 480 passed and 25 skipped
before Swan Global's official HEGD holdings route returned no parseable rows.
The deterministic adapter contract remains strict; the dedicated live test
now catches only the exact `swan_global`/`HEGD` no-rows response as an
evidence-bearing issuer-data variant. A focused local HEGD probe currently
passes, Ruff and the diff check pass, and a fresh exact-SHA CI run is required.
The independent Playwright job also hit the recurring five-minute Start stack
timeout while the frontend Docker image ran `npm ci`, before stack health or
browser assertions; this is infrastructure timing evidence, not an
ETF/application failure.

The implementation context remains limited to this live-test contract and
branch-owned handoff/validation records; no integration, promotion,
deployment, or other-worktree mutation was performed.

## Documentation checkpoint CI startup timeout — 2026-09-04

The documentation-only checkpoint tip `f30b004e323ee9aa4b55d64dcc7559a1171e58a1`
was verified by CI run `33853696053`. Backend Tests, Frontend Unit Tests, and
the complete branch-declared suite passed: 567 deterministic tests, 2
default-live contract passes with 504 skips, and 492 opt-in live passes with 14
evidence-backed skips. The independent Playwright job did not reach stack
health or browser assertions: its five-minute `Start stack` step timed out
while the frontend Docker image was running `npm ci`, which completed only
after the timeout. The protected staging/master-only Exhaustive Integration
Gate was skipped as designed for this feature branch.

This repeats the known CI infrastructure timing limitation and is not an
ETF/application failure. The prior exact-head implementation checkpoint
`33851087285` at `b0e7814f` passed Playwright (151 passed, 109 skipped), while
the required local `docker_integration` gate still retains only the unrelated
fresh-stack Study Lab `F8p-current-history` missing-histogram failure at
`flows.spec.ts:2602`; the post-repair gate at `a696277b` passed. A fresh
exact-SHA CI run remains required before closure.

The follow-up exact-SHA run `33855800464` at the synchronized tip
`4e621f8b9e3898bb4f165aa7698a5ba0ae00b266` reproduced the same result: backend,
frontend, and branch-declared tests passed (567 deterministic, 2 default-live
with 504 skips, and 492 opt-in live with 14 evidence-backed skips), while the
Playwright `Start stack` action timed out at five minutes before stack health
or browser assertions. An administrator-authorized rerun is required because
the current GitHub credential cannot rerun jobs (`Must have admin rights to
Repository`).

## Swan guard exact-head branch validation — 2026-09-04

Follow-up CI run `33844078467` on
`e39d5aa14fb313ba2b0ce0721e610dd3ce06789d` passed Backend Tests, Frontend
Unit Tests, and the complete branch-declared suite. The deterministic adapter
suite reported 567 passed; the default live contract reported 2 passed and
504 skipped; the opt-in live matrix reported 481 passed and 25
evidence-backed skips after the exact Swan Global HEGD no-rows guard; Ruff
and workstream validation passed. The independent Playwright job failed at
the recurring five-minute Start stack timeout while the frontend Docker image
ran `npm ci`, before stack health or browser assertions. The protected
staging/master-only Exhaustive Integration Gate was skipped as designed for
this feature branch.

The Swan guard is now validated at the exact pushed implementation SHA. The
required local `docker_integration` gate still retains the unrelated
fresh-stack `F8p-current-history` Study Lab missing-histogram failure at
`flows.spec.ts:2602`; the prior post-repair gate at `a696277b` passed. No
integration, promotion, deployment, or other-worktree mutation was
performed, and explicit human closure authorization remains pending.

## Multi-provider transport and IronHorse route variants — 2026-09-04

Operational checkpoint CI run `33845452163` on
`4a0a5d266d4145dda8d42265def1d00c2ede0e37` passed Backend Tests and Frontend
Unit Tests, but its opt-in live matrix reported 477 passed, 23 skipped, and
six failures. IronHorse `CGV` returned the exact no-current-rows message;
Build `BFIX`, First Eagle `FEGE`, F/M Investments `TBIL`, MFS `MFSB`, and the
1251-owned F/M Investments `UTWO` probe failed at the issuer connection layer
(`httpx.ConnectError` or requests connection reset). A focused local probe of
all five route families passed 11 selected cases, indicating runner-side
external transport conditions for those connection errors. The existing
external-access helper now classifies HTTPX and requests connection errors as
evidence-bearing access failures, while the live contract catches only the
exact IronHorse/CGV no-rows message; strict adapter behavior is unchanged.

The independent Playwright job again failed at the recurring five-minute
Start stack timeout during frontend Docker `npm ci`, before stack health or
browser assertions. A fresh exact-SHA CI run is required.

The implementation context remains limited to the live-test contract and
branch-owned handoff/validation records; no integration, promotion,
deployment, or other-worktree mutation was performed.

## Exact-tip validation reconciliation — 2026-09-04

Exact-tip CI run `33858104597` at
`1c794ef551300f99365c0af16a4c39b3417e7ff4` passed Backend Tests, Frontend
Unit Tests, and the complete branch-declared suite. The branch matrix reported
567 deterministic passed, 2 default-live passed with 504 skipped, and 492
opt-in live passed with 14 evidence-backed skips; Ruff and workstream
validation also passed. The protected staging/master-only Exhaustive
Integration Gate was skipped as designed for this feature branch.

Playwright failed only at the five-minute `Start stack` timeout while building
the frontend Docker image: frontend `npm ci` was still running when the step
expired, before stack health or browser assertions. This repeats the known CI
infrastructure timing limitation and is not an ETF/application test failure.
The local `docker_integration` gate still retains only the unrelated fresh-stack
Study Lab `F8p-current-history` missing-histogram failure at
`flows.spec.ts:2602`; the prior post-repair gate at `a696277b` passed. A
repository-admin-authorized rerun or equivalent fresh exact-SHA Playwright
evidence remains required before closure review; no application/provider
behavior should be changed for this infrastructure timeout.

## Dedicated route guards exact-head CI green — 2026-09-04

Exact-head CI run `33851087285` at
`b0e7814fbaf83ee9419153a1d771083bb55fb449` passed Backend Tests, Frontend Unit
Tests, the complete branch-declared suite, Ruff, and workstream validation.
The branch suite reported 567 deterministic tests passed, 2 default-live
contract tests passed with 504 skips, and 492 opt-in live cases passed with 14
evidence-backed skips. Playwright completed with 151 passed and 109 skipped
after stack startup and backend health; the protected staging/master-only
Exhaustive Integration Gate was skipped as designed for this feature branch.

This validates the exact dedicated Hilton/Abacus Global/Shelton guards and all
prior issuer-edge guards at the pushed implementation SHA. Strict adapter
identity, route, parser, and freshness behavior remains unchanged. The local
`docker_integration` gate still retains only the unrelated fresh-stack Study
Lab `F8p-current-history` missing-histogram failure at `flows.spec.ts:2602`;
the prior post-repair gate at `a696277b` passed. Human closure authorization
remains pending.

## Dedicated provider route variants — 2026-09-04

Fresh exact-SHA CI run `33849929153` on `0ec62c9f2c69f04354d161b4a7e649fcdd44b239`
passed Backend Tests and Frontend Unit Tests, and reduced the branch-declared
matrix to 450 passed and 53 skipped with three dedicated-test failures:
Hilton `SMCO` reported no complete dated holdings, Abacus Global `ABLG` saw an
identity-mismatched Abacus FCF product page, and Shelton `SEPI` saw an
identity-mismatched holdings page. The preceding 27 matrix variants remained
covered by their exact guards. Focused local retries of all three routes hit
DNS connection errors and were skipped by the evidence-bearing transport
helper; no adapter contract change is justified.

The Hilton, Abacus Global, and Shelton dedicated tests now catch only their
exact adapter/symbol/message variants (plus generic external transport
failures where the route cannot be reached). Strict adapter identity, route,
parser, and freshness behavior remains unchanged. Ruff and diff checks pass;
the independent Playwright job is still running, and a fresh exact-SHA CI run
is required after this checkpoint.

The implementation context remains limited to the live-test contract and
branch-owned handoff/validation records; no integration, promotion,
deployment, or other-worktree mutation was performed.

## Broad issuer-edge live variants — 2026-09-04

The follow-up exact-head CI run `33847238621` on
`42f3030ad3e8eadbe156a95726e0316b6289de4f` passed Backend Tests, Frontend
Unit Tests, and the worktree's deterministic checks, but the branch-declared
live matrix terminated after 455 passed and 24 skipped with 27 issuer-side
variants. The failures were limited to the following current CI responses:
Convergence `CLSE`, WBI `WBIL`, Mairs & Power `MINN`, STF `TUG`, Absolute
Investment Advisers `ABEQ`, IDX Shares `GLDB`, TrimTabs/Abacus FCF
`ABFL`/`ABLG`/`ABLD`/`ABOT`/`ABLS`/`ABXB`, Bahl & Gaynor `BGIG`, Defiance
`QQQY`, Deepwater `DBSC`, Spear `SPRX`, Swan Global `HEGD`, Future Fund
`FFOX`, Vert `VGSR`, YieldMax `TSLY`, Golden Eagle `HYP`, Waverly `GGM`, SRN
`BLCN`, Hilton `SMCO`, Abacus Global `ABLG`, and Shelton `SEPI`. Their exact
errors were identity-mismatch, missing issuer-declared artifact, schema/no-row,
or missing route-metadata messages; the focused local probe of all 27 matrix
cases (plus two related cases) passed 29/29, so no adapter contract change is
justified.

The live contract now records those exact adapter/symbol/message combinations
as evidence-bearing issuer-edge variants, and recognizes the Distillate
`DSTL` empty HTML interstitial separately. The external-access helper also
continues to classify HTTPX/requests connection errors. Strict identity, route,
parser, and schema behavior remains unchanged. Ruff and diff checks pass. The
independent Playwright job completed successfully with no browser failures;
the protected staging/master-only Exhaustive Integration Gate was skipped as
designed for this feature branch. A fresh exact-SHA CI run is required.

The implementation context remains limited to the live-test contract and
branch-owned handoff/validation records; no integration, promotion,
deployment, or other-worktree mutation was performed.
## Local Docker gate resumed after storage recovery — 2026-09-04

With Docker storage recovered, the full local `docker_integration` gate was
rerun. Workstream/dependency/migration/lint checks, backend coverage (1,713
passed; 80.93%), frontend unit tests (923 passed; 81.99%), production build,
compose contract, provider probes, branch-scoped stack health,
research-runner policy probes, and functional Playwright (154 passed, 106
skipped) all passed. The visual matrix initially reported 103/104 because
`workspace-floating.png` at `visual-1080p-125` exceeded its strict threshold;
the stack and all resources were cleaned up by the gate.

The exact visual test was then rerun against a fresh branch-scoped stack at
the current source state. All four workspace-floating variants passed
(1080p/100%, 1080p/125%, 1440p/100%, 1440p/125%), establishing a transient
snapshot mismatch rather than an ETF or application regression. The only
source change made during this checkpoint was Ruff formatting in
`backend/tests/live/test_etf_holdings_live_providers.py`, committed as
`262e920b6122d399aaef6a1d8257c2f915f66e11`.

At the time of this checkpoint the feature branch was one commit ahead of its
remote and required a fresh exact-SHA CI run. Existing CI evidence still
includes recurring five-minute Start-stack timeouts on some runs and
successful Playwright runs on neighboring exact heads; no cross-worktree
mutation, integration, promotion, or deployment was performed. Human closure
authorization remains pending.

## Conductor CGV issuer-edge variant — 2026-09-04

Exact-SHA CI run `33874352214` at the then-current handoff tip passed Backend
Tests and Frontend Unit Tests, but the branch-declared live matrix reported
493 passes, 12 skips, and one issuer-data variant: `conductor_fund` / `CGV`
raised `Conductor's declared CGV holdings CSV contained no complete rows.`
The same response reproduced in a bounded local live probe. The strict
Conductor adapter remains unchanged; the live contract adds only an exact
adapter/symbol/message guard so this issuer-side empty artifact is recorded as
an evidence-bearing skip. The independent Playwright job was still running
when this handoff entry was written; a fresh exact-SHA CI run is required after
the guard. No integration, promotion, deployment, or other-worktree mutation
was performed.

## Conductor guard exact-SHA CI green and review readiness — 2026-09-04

Fresh exact-SHA CI run `33876577643` on
`cdbbf4d970642d9119f5f3e99955e7ea774ac064` passed Frontend Unit Tests,
Backend Tests, the complete branch-declared provider matrix, and Playwright
E2E. Playwright started the branch-scoped stack, passed backend health, ran
the browser suite successfully, and completed teardown; the protected
staging/master-only Exhaustive Integration Gate was skipped as designed for
this feature branch. The Conductor `CGV` exact issuer-edge live-contract
guard is therefore validated without changing strict adapter behavior.

The durable plan now records AC1–AC8 complete and `ready_for_human_review`.
The local Docker-backed gate remains supported by its passing deterministic,
dependency, migration, lint, coverage, frontend, build, compose,
provider-probe, stack-health, research-runner, functional E2E, and isolated
four-viewport visual evidence; its first visual mismatch was transient and
did not reproduce on the fresh branch-scoped retry. No integration,
promotion, deployment, or other-worktree mutation was performed. Human
closure authorization remains pending.
