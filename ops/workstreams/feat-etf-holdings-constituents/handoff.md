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
- Current code-derived state: 496 registered, 383 native/live-backed, 113
  fallback-only.
- Current fallback status split: 8 access-blocked, 96 discovery, 3
  non-executable public source, 6 non-portfolio-publisher (the ledger's dated
  terminal dispositions preserve each record's original runtime audit status;
  Elm, Esoterica, Even Herd, Everence, Hexis, and Hilton are no longer runtime fallbacks
  after their native promotions).
- `docs/etf-provider-universe.md` has been reconciled from code to the current
  496/383/113 snapshot; future updates must remain code-derived.
- Validation tier: `full_integration`.
- Local validation profile: `docker_integration`.
- The full integration gate at `2d96697d` reached e2e-functional but failed one
  unrelated Study Lab browser case (`F8p-current-history`); 153 e2e cases passed
  and 106 were skipped. A fresh-stack retry reproduced a missing histogram
  element timeout. The ETF holdings tests and routes were not implicated.
- Planning session: `197b239d-3322-4fc6-bf4b-0d0aecebf5e0`.
- Latest implementation checkpoint: `dabe2329965c704f93e3dbb21ec50a7da418ba6c` (Hexis/NICO native FilePoint route, adapter/config/tests, current holdings evidence, and synchronized workstream records); prior `5f8d0b9d` (Gotham GSPY/GVLU/SHRT complete current holdings through official symbol-scoped DownloadHoldings CSV routes, with derivative CUSIP preservation; Fundstrat Granny Shots GRNY/GRNJ/GRNI complete current holdings tables through the official Granny Shots pages; Freedom/FRDM complete current holdings table through the official Freedom ETFs product page; Framework/GSR BESO current holdings route through the official GSR product page and details/holdings APIs; Fitzgerald/Nicholas Wealth FITZ and FIZY current holdings routes through the official XFUNDS pages and nonce-scoped CSV endpoints; FalconX parent coverage through the independently managed 21Shares ARKB, TETH, TOXR, TSOL, TDOG, TDOT, TSUI, TCAN, THYP, and TKNS routes; Everence/Praxis PRXG, PRXV, and PRXI native routes; Even Herd native EHLS route; the existing
  Esoterica WUGI and Cygnet/Elm routes remain intact); prior `915282cd` (Esoterica native WUGI route); prior `a4571ff3` (Elements inactive/successor
  disposition; prior EA Series Trust dated non-portfolio-publisher disposition;
  prior DVx Ventures dated
  non-portfolio-publisher disposition; prior Discipline Funds dated
  non-executable-route disposition); prior `9cc5be81` (CresAlta native CVGD/CVSM
  holdings tables); prior `fd07b17f` (Conductor native CGV declared
  holdings CSV); prior `1aa7cc48` (Castellan native CTEF/CTIF
  holdings tables); prior `992a554d` (CapForce native FFTY/BOUT
  holdings tables); prior `b9a984c4` (Bushido native SMRI/RNIN
  holdings tables); prior `b967113b` (BufferLABS native BFLB
  holdings table and live coverage); prior Brookstone checkpoint `6aa2adb3` (Brookstone native BAMD/BAMG/BAMV/
  BAMB/BAMU/BAMA/BAMO/BAMY holdings routes and live coverage); prior Bridgeway
  checkpoint `c1caf555` (Bridgeway native BBLU/BAGX/BRSV/BSVO/BUSM holdings routes
  and live coverage); prior Blueprint checkpoint
  `ba4b80ea` (Blueprint native TFPN holdings route); prior BeeHive checkpoint `bc77c274` (BeeHive native holdings route plus
  promoted-adapter contract alignment);
  prior Ballast/Avory/ARS checkpoints are `b4c96335`/`695dea16`/`f33224ab` and
  the Guggenheim audit receipt remains `c4bef2ec`.
- Product implementation is underway; current changes add Guggenheim, ARS,
  Avory, Ballast, Bancreek, BeeHive, Blueprint, Bridgeway, Brookstone, BufferLABS,
  Bushido, CapForce, Castellan, Conductor, and CresAlta
  native coverage and issuer-specific audit dispositions for the ranked fallback
  records reviewed so far.
  The Elm implementation reuses the proven official product-page-declared full
  holdings CSV under an explicit `elm` adapter, with Elm Partners Management
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
