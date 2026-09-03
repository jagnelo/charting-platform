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
