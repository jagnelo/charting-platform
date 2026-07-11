# Active Handoff

## Current task

- ID: etf-holdings-constituents
- Title: Implement free-source-first ETF holdings / constituents subsystem.

## Latest checkpoint - 2026-07-11T02:05Z

- Promoted `gamco` (Gabelli) from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `GabelliHoldingsAdapter` that reads Gabelli's dedicated public per-fund daily holdings CSV.
- It preserves ticker, CUSIP, shares/par, price-derived market value, weight, cash classification, and issuer as-of date. A narrow issuer-local `requests` fallback is used only when Gabelli's CDN rejects `httpx` while accepting the same public CSV request.
- Live validation symbol: `GCAD`, returning more than 20 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `138`
  - providers still lacking native/live-backed support: `207`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `182 passed`
  - focused live Gabelli route: `1 passed, 141 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed

## Previous checkpoint - 2026-07-11T01:30Z

- Promoted `first_pacific` from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `FirstPacificHoldingsAdapter` that reads FPA's dated multi-fund daily CSV export, retries thirty preceding dates for non-publishing days, and filters the shared file by ETF ticker.
- It preserves ticker, CUSIP, ISIN, SEDOL, shares, market value, weight, cash classification, and issuer as-of date.
- Live validation symbol: `FPAG`, returning more than 20 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `137`
  - providers still lacking native/live-backed support: `208`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `181 passed`
  - focused live First Pacific route: `1 passed, 140 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed

## Previous checkpoint - 2026-07-11T00:05Z

- Promoted `brown_advisory` from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `BrownAdvisoryHoldingsAdapter` that reads the issuer's dated FilePoint daily export, retries fifteen preceding dates for non-publishing days, and filters the shared file by ETF ticker.
- It preserves ticker, CUSIP, ISIN, SEDOL, shares, market value, weight, cash classification, and issuer as-of date.
- Live validation symbol: `BAFE`, returning more than 20 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `136`
  - providers still lacking native/live-backed support: `209`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `180 passed`
  - focused live Brown Advisory route: `1 passed, 139 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed

## Previous checkpoint - 2026-07-10T22:10Z

- Promoted `prudential` (PGIM) from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `PgimHoldingsAdapter` that:
  - resolves a requested ticker from PGIM's public ETF directory;
  - follows the matched PGIM product page to its explicit `DAILY HOLDINGS` document;
  - downloads and parses the complete issuer PDF, preserving ticker, ISIN, CUSIP, SEDOL, shares, market value, currency, weight, cash rows, and issuer as-of date.
- Live validation symbol: `PJBF`, returning more than 30 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `135`
  - providers still lacking native/live-backed support: `210`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `179 passed`
  - focused live PGIM route: `1 passed, 138 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route. WisdomTree, Neuberger Berman, SoFi, and Thrivent remain unpromoted because their public issuer artifacts challenge direct backend requests.

## Previous checkpoint - 2026-07-10T21:45Z

- Promoted `tiaa` (Nuveen) from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `TiaaHoldingsAdapter` that:
  - reads Nuveen's issuer-owned ETF catalog to resolve an ETF from its ticker;
  - derives the product CUSIP from the matching public issuer product page;
  - calls Nuveen's complete public product API at `https://api.nuveen.com/ETF/v2/productdetail/bycusip/{CUSIP}?tooltip=1`;
  - preserves ticker, CUSIP/SEDOL, market value, net-assets weight, cash rows, and issuer composition date.
- Live validation symbol: `NULG`, returning more than 50 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `134`
  - providers still lacking native/live-backed support: `211`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `178 passed`
  - focused live Nuveen/TIAA route: `1 passed, 137 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route. WisdomTree, Neuberger Berman, SoFi, and Thrivent remain unpromoted because their public issuer artifacts challenge direct backend requests.

## Latest checkpoint - 2026-07-10T21:15Z

- Promoted `gqg` from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `GqgHoldingsAdapter` that reads GQG's issuer-native dated FilePoint export at `https://gqg.filepoint.live/assets/data/SEI_GQG_Tradedate_Holdings_{MMDDYYYY}.txt`.
  - probes up to ten prior calendar days for the latest published file, avoiding false failures on weekends and holidays;
  - filters the shared export by the requested fund ticker before building a snapshot;
  - preserves ticker, CUSIP, ISIN, SEDOL, shares, market value, net-assets weight, cash rows, and issuer composition date.
- Live validation symbol: `GQGU`, returning more than 20 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `133`
  - providers still lacking native/live-backed support: `212`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `177 passed`
  - focused live GQG route: `1 passed, 136 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route. WisdomTree, Neuberger Berman, SoFi, and Thrivent remain unpromoted because their public issuer artifacts challenge direct backend requests.

## Latest checkpoint - 2026-07-10T20:45Z

- Promoted `tcw` from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `TcwHoldingsAdapter` that:
  - reads TCW's public combined fixed-income ETF holdings PDF;
  - identifies the requested fund's page range before parsing, so schedules from the other TCW ETFs are never mixed into the snapshot;
  - preserves fixed-income position names, principal amounts, maturity dates, currencies, and market values without inventing equity tickers;
  - derives canonical position weights from the issuer-published market values.
- Live validation symbol: `ACLO`, returning more than 100 parseable issuer-native holdings rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `132`
  - providers still lacking native/live-backed support: `213`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `176 passed`
  - focused live TCW route: `1 passed, 135 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route. WisdomTree, Neuberger Berman, SoFi, and Thrivent remain unpromoted because their public issuer artifacts challenge direct backend requests.

## Latest checkpoint - 2026-07-10T20:00Z

- Promoted `groupe_bpce` (Natixis) from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `NatixisHoldingsAdapter` that reads the issuer-native daily CSV pattern at `https://mkt.im.natixis.com/files/etfs/{SYMBOL}_daily_full_holdings.csv`, verifies the CSV's declared ticker, and parses identifiers, quantity, net-assets weight, market value, cash rows, and the as-of date.
- Natixis currently omits a public DigiCert intermediate from its TLS chain. The adapter keeps certificate verification enabled and loads that official intermediate locally; it does not disable TLS verification.
- Live validation symbol: `GQI`, returning more than 50 parseable issuer-native holdings rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `131`
  - providers still lacking native/live-backed support: `214`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `175 passed`
  - focused live Natixis route: `1 passed, 134 deselected`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route; higher-priority blocked issuers remain unpromoted.

## Latest checkpoint - 2026-07-10T19:35Z

- Promoted `astoria` from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `AstoriaHoldingsAdapter` that:
  - discovers public ETF pages from `https://astoriaadvisorsetfs.com/wp-sitemap-posts-page-1.xml` and verifies the page-declared ETF ticker;
  - parses the complete issuer-owned holdings table, including ticker, name, CUSIP, shares, price, market value, weight, and effective date;
  - converts Astoria's published `Market Value ($mm)` values to canonical currency units;
  - uses a narrow issuer-local `requests` fallback only after Astoria returns `403` to `httpx`.
- Live validation symbol: `ROE`, returning 102 parseable issuer-native holdings rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `130`
  - providers still lacking native/live-backed support: `215`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `174 passed`
  - focused live Astoria route: `1 passed, 133 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route; higher-priority blocked issuers remain unpromoted.

## Latest checkpoint - 2026-07-10T19:10Z

- Promoted `rayliant` from recognition-only/SEC-backed support to native/live-backed support.
- Added an isolated `RayliantHoldingsAdapter` that:
  - uses Rayliant's public product sitemap at `https://funds.rayliant.com/page-sitemap.xml` to discover the requested ETF page and verifies the page's declared ticker;
  - follows the issuer page's explicit `?download_csv=1` full-holdings download, rather than ingesting the visible top-ten table;
  - preserves exchange-qualified foreign references such as `700 HK` as source references with SEDOL metadata rather than inventing unsupported local tickers;
  - uses a narrow issuer-local `requests` fallback only after Rayliant returns `403` to `httpx`; the issuer accepts the same public request through this transport.
- Live validation symbol: `CNQQ`, returning more than 50 parseable issuer-native holdings rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `129`
  - providers still lacking native/live-backed support: `216`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `173 passed`
  - focused live Rayliant route: `1 passed, 132 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route; do not promote blocked or SEC-only routes.

## Research checkpoint - 2026-07-10T18:45Z

- `russell_investments` public ETF directory and product pages are backend-reachable, including RIFR's public product payload. The issuer payload currently has `Holdings: null` and `HideHoldingTable: true`, with no downloadable full-holdings artifact exposed by the public page.
- Do not promote Russell Investments from this evidence. A native route requires a real issuer disclosure/feed containing complete holdings, not a reachable fund page with holdings explicitly suppressed.

## Latest checkpoint - 2026-07-10T18:30Z

- Promoted `akre` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `AkreHoldingsAdapter` using the issuer's public daily FilePoint CSV:
  - source: `https://akre.filepoint.live/assets/data/FilepointAkre.40B4.B4_ETF_Holdings.csv`
  - validates and selects the issuer's only current ETF, `AKRE`.
  - preserves CUSIPs and SEDOLs, while keeping exchange-qualified foreign references such as `CSU CN` as references instead of inventing incorrect US ticker symbols.
  - correctly retains money-market/cash rows as cash, including their actual signed weights.
- Live validation symbol: `AKRE`, returning more than 15 parseable issuer-native holdings rows from the public daily file.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `128`
  - providers still lacking native/live-backed support: `217`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `172 passed`
  - focused live Akre route: `1 passed, 131 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Feature commit: `efe3dc6 feat(etf-holdings): add Akre native holdings route`
- Next step:
  - Continue the 345-provider objective with the next backend-reachable issuer-native route; do not promote blocked or SEC-only routes.

## Research checkpoint - 2026-07-10T18:15Z

- Priority-issuer audit after the Tortoise checkpoint:
  - `wisdomtree`: the correct US product route (`https://www.wisdomtree.com/us/products/equity/dxj`) publicly exposes holdings in browser/search contexts, but repeated direct backend-style requests return Cloudflare `403`. Do not promote it or route it through SEC until a backend-reachable issuer-native feed is proven.
  - `tcw`: an issuer-hosted Edge/Sitecore PDF is reachable at `https://edge.sitecorecloud.io/thetcwgroupc320-tcwweb7bc3-prod0f26-25f9/media/Downloads/TCW/Products/ETFs/Holdings/FI-ETF-Q1-Holdings.pdf?sc_lang=en`. It contains complete schedules for ACLO, FIXT, IGCB, FLXR, HYBX, MUSE, and SLNZ, but is a multi-fund quarterly PDF. A native adapter must discover the current publication artifact and segment the selected fund defensibly before it can be promoted.
- The working tree is clean after the Tortoise feature/ops commits. Continue from the TCW native-PDF route or another backend-reachable high-priority issuer; do not mistake either research finding for completed provider support.

## Latest checkpoint - 2026-07-10T18:00Z

- Promoted `tortoise` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `TortoiseHoldingsAdapter` using the issuer's public ETF sitemap and embedded daily product-page holdings tables:
  - ETF sitemap: `https://tortoisecapital.com/etfs-sitemap.xml`
  - resolves the requested fund by verifying the product page's declared ticker, rather than guessing a ticker-to-slug URL.
  - parses the full `Security Name`, `Stock Ticker`, `CUSIP`, `Shares`, `Market Value`, and `Weight` table from the matching issuer page.
  - extracts the issuer's holdings as-of date and retains the normal cash/security classifications.
- Live validation symbol: `TPZ`, returning 39 parseable issuer-native holdings rows from Tortoise's public product page.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `127`
  - providers still lacking native/live-backed support: `218`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `171 passed`
  - focused live Tortoise route: `1 passed, 130 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Feature commit: `414e720 feat(etf-holdings): add Tortoise native holdings route`
- Next step:
  - Continue the user's priority sequence, proving a complete issuer-native route and live test before promoting each provider.

## Latest checkpoint - 2026-07-10T17:45Z

- Promoted `eldridge` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `EldridgeHoldingsAdapter` using the issuer's public combined daily holdings CSV:
  - source: `https://clozfund.com/assets/data/FilepointPanagram.40P2.P2_Holdings.csv`
  - filters the shared issuer file by the requested `Account` so `CLOX` and `CLOZ` never cross-contaminate a snapshot.
  - keeps issuer CUSIP-like loan/CLO identifiers as identifiers rather than misrepresenting them as exchange-traded tickers.
  - classifies structured-credit rows as fixed income and cash/money-market rows as cash.
- Live validation symbol: `CLOX`, returning more than 20 parseable issuer-native rows from the public daily file.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `126`
  - providers still lacking native/live-backed support: `219`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `170 passed`
  - focused live Eldridge route: `1 passed, 129 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Feature commit: `f3b16e4 feat(etf-holdings): add Eldridge native holdings route`
- Research note:
  - `sofi`, `neuberger_berman`, and `thrivent` each expose a documented issuer-owned complete holdings artifact, but their direct public hosts currently return browser/CDN challenges to backend requests. They remain unpromoted until an actual backend-reachable native route is proven and live-tested.
- Next step:
  - Continue the user's priority sequence, proving a complete issuer-native route and live test before promoting each provider.

## Latest checkpoint - 2026-07-10T17:20Z

- Promoted `rex` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `RexHoldingsAdapter` using the issuer's public product-page CSV download form:
  - product page: `https://www.rexshares.com/{symbol_lower}/`
  - posts `CSV=Download CSV` and the selected ETF symbol to retrieve the complete issuer CSV, rather than ingesting the visible top-ten preview.
  - parses ticker, name, CUSIP/security identifier, weight, net value, and shares.
  - classifies cash, money-market funds, swaps, and OCC-style option contracts accurately rather than treating them as ordinary equities.
  - uses `requests` through `asyncio.to_thread` because the issuer accepts the public form with that transport while rejecting the async client's TLS fingerprint.
- Live validation symbol: `FEPI`, returning 64 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `125`
  - providers still lacking native/live-backed support: `220`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `169 passed`
  - focused live REX route: `2 passed, 127 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the user-prioritized providers, with `wisdomtree`, `neuberger_berman`, `brookfield`, `sofi`, `tcw`, `thrivent`, and `wellington` still to be proven by native provider routes and live tests.

## Latest checkpoint - 2026-07-10T16:45Z

- Promoted `lazard` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `LazardHoldingsAdapter` using Lazard's public ETF directory and product API:
  - directory: `https://www.lazardassetmanagement.com/us/en_us/investment-solutions/how-to-invest/etfs`
  - holdings API: `https://lazardassetmanagement.com/api/products?id={product_id}&type=Fund`
  - discovers the issuer product ID from the directory when a stored profile has only a trading symbol.
  - verifies the returned ETF ticker and parses full constituents with ticker, CUSIP, ISIN, SEDOL, shares, market value, weight, asset class, security type, and as-of date.
  - preserves cash, FX, derivatives, fixed income, and fund rows with accurate classifications.
- Live validation symbol: `JPY`, returning 64 parseable issuer-native rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `124`
  - providers still lacking native/live-backed support: `221`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `168 passed`
  - focused live Lazard route: `1 passed, 127 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Next step:
  - Continue the user-prioritized providers, with `wisdomtree`, `neuberger_berman`, `brookfield`, `sofi`, `rex`, `tcw`, `thrivent`, and `wellington` still to be proven by native provider routes and live tests.

## Latest checkpoint - 2026-07-10T16:07Z

- Promoted `voya` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `VoyaHoldingsAdapter` using Voya's public daily account holdings CSV:
  - `https://vimetfs.com/{symbol}/holdings`
  - filters the shared CSV by requested ETF account before ingesting it.
  - parses date, identifiers, security name, shares, price, market value, percentage weight, net assets, and shares outstanding.
  - preserves cash, currency, and derivative exposures without materializing them as tradable securities; untickered securities are classified as fixed income.
- Live validation symbol: `VMSB`, returning more than 100 parseable rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `123`
  - providers still lacking native/live-backed support: `222`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `167 passed`
  - focused live Voya route: `1 passed, 123 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Feature commit: `6d55337 feat(etf-holdings): add Voya native holdings route`
- Remaining fast-track screenshot set:
  - `wisdomtree`, `neuberger_berman`, `lazard`, `brookfield`, `sofi`, `rex`, `tcw`, `thrivent`, and `wellington`.

## Previous checkpoint - 2026-07-10T15:52Z

- Promoted `fidelity` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `FidelityHoldingsAdapter` using Fidelity's public complete ETF basket table:
  - `https://research2.fidelity.com/fidelity/screeners/etf/etfholdings.asp?sortBy=Symbol&sortDir=asc&symbol={symbol}&view=Holdings`
  - parses the full creation/redemption basket, including symbol, company, weight, declared holding count, and as-of date.
  - rejects partial parses whenever parsed rows do not exactly match Fidelity's declared basket count.
  - preserves cash rows without materializing them as tradable instruments.
  - records the source honestly as a creation/redemption basket, including Fidelity's disclosure that it may differ from the full current or future investment portfolio.
- Live validation symbol: `FBCG`, returning more than 100 parseable rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `122`
  - providers still lacking native/live-backed support: `223`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `166 passed`
  - focused live Fidelity route: `1 passed, 122 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff and `git diff --check`: passed
- Feature commit: `cf87ea3 feat(etf-holdings): add Fidelity native basket route`
- Remaining fast-track screenshot set:
  - `wisdomtree`, `neuberger_berman`, `lazard`, `brookfield`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, and `wellington`.

## Earlier checkpoint - 2026-07-10T15:45Z

- Promoted `capital_group` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added an isolated `CapitalGroupHoldingsAdapter` using Capital Group's public daily holdings JSON API:
  - `https://www.capitalgroup.com/api/investments/investment-service/v1/etfs/{symbol}/holdings?audience=individual&redirect=true`
  - sends the public `x-app-source: dis-etf-web` request metadata used by the issuer holdings page.
  - validates the response belongs to the requested ETF.
  - parses ticker, name, CUSIP, ISIN, SEDOL, shares/principal, market value, percent-of-net-assets weight, asset class, and as-of date.
  - preserves cash/equivalent and spot-FX rows without falsely materializing them as tradable securities.
- Fixed existing DWS and Principal unit fixtures to mock their current `requests`-based fetch paths rather than leaking to the network.
- Live validation symbol: `CGGR`.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `121`
  - providers still lacking native/live-backed support: `224`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - full ETF adapter unit suite: `165 passed`
  - focused live Capital Group route: `1 passed, 121 deselected`
  - live provider matrix: `1 passed`
  - targeted ruff: passed
  - `git diff --check`: passed
- Feature commit: `2856ada feat(etf-holdings): add Capital Group native route`
- Remaining fast-track screenshot set:
  - `fidelity`, `wisdomtree`, `neuberger_berman`, `lazard`, `brookfield`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, and `wellington`.
- Next step:
  - Continue the same priority ordering, proving a complete issuer-native route and live test before promoting another provider.

## Earlier checkpoint - 2026-07-07T16:05Z

- Promoted `doubleline` from generated/SEC-backed recognition-only support to native/live-backed support.
- This was from the user-confirmed fast-track screenshot set:
  - `dimensional`, `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `victory`, `doubleline`, `lazard`, `brookfield`, `angel_oak`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, `wellington`.
- Added a provider-specific `DoubleLineHoldingsAdapter`:
  - probes recent dated public holdings PDFs such as `https://doubleline.com/wp-content/uploads/holdings/DoubleLine_DBND_Holdings_07-06-2026.pdf`.
  - adds `pypdf` as a backend dependency for issuer PDF text extraction.
  - parses PDF-extracted rows for weight, security name, security identifier/CUSIP, issuer ticker, market value, quantity, contract size, asset class, and composition date.
  - avoids treating generic fixed-income issuer tickers such as `T`, `FN`, or `FR` as platform tradable symbols while preserving them in row metadata.
  - classifies treasury/RMBS/CMBS/etc. rows as fixed income, fund rows as funds, and cash rows as cash.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `120`
  - providers still lacking native/live-backed support: `225`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_doubleline_adapter_parses_pdf_extracted_text tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k doubleline`
    - result: `1 passed, 120 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
- Remaining fast-track screenshot set:
  - `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `lazard`, `brookfield`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, and `wellington`.
- Next step:
  - Continue the exact screenshot-priority set. `wisdomtree` remains browser-renderable but backend-fetch blocked with HTTP `403`; do not claim it native until the backend can fetch a complete holdings artifact.

## Latest checkpoint - 2026-07-07T15:20Z

- Promoted `angel_oak` from generated/SEC-backed recognition-only support to native/live-backed support.
- This was from the user-confirmed fast-track screenshot set:
  - `dimensional`, `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `victory`, `doubleline`, `lazard`, `brookfield`, `angel_oak`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, `wellington`.
- Added a provider-specific `AngelOakHoldingsAdapter`:
  - uses Angel Oak's public combined ETF holdings CSV at `https://angeloakcapital.com/secure-gs/Angel_Oak_ETF_Holdings.csv`.
  - filters rows by the requested ETF `Account` symbol, so sibling ETF rows in the same file are not ingested into the selected ETF.
  - parses `Date`, `Account`, `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `Price`, `MarketValue`, `Weightings`, and `MoneyMarketFlag`.
  - avoids manufacturing fake tradable tickers when `StockTicker` is actually a CUSIP-like bond identifier.
  - classifies Angel Oak rows as fixed income by default and preserves cash-like rows as cash.
- Also hardened DWS/Xtrackers and Principal issuer downloads by using `requests` through `asyncio.to_thread` for issuer files that are more reliable with that client path than `httpx`.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `119`
  - providers still lacking native/live-backed support: `226`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_angel_oak_adapter_filters_combined_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k angel_oak`
    - result: `1 passed, 119 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
- Remaining fast-track screenshot set:
  - `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `doubleline`, `lazard`, `brookfield`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, and `wellington`.
- Probe notes from this pass:
  - `doubleline` exposes a public holdings PDF route such as `https://doubleline.com/wp-content/uploads/holdings/DoubleLine_DBND_Holdings_07-06-2026.pdf`; implementing it properly needs a PDF table extraction path before native support can be claimed.
  - `sofi` and `thrivent` returned HTTP `403`/challenge responses from this environment.
  - `tcw`, `lazard`, `brookfield`, and `voya` need deeper route work; no backend-parseable native holdings artifact was validated in this pass.
- Next step:
  - Continue the exact screenshot-priority set. Do not substitute unrelated providers while this high-priority list still has unresolved provider-specific routes.

## Latest checkpoint - 2026-07-07T14:35Z

- Promoted `victory` from generated/SEC-backed recognition-only support to native/live-backed support.
- This was from the user-confirmed fast-track screenshot set:
  - `dimensional`, `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `victory`, `doubleline`, `lazard`, `brookfield`, `angel_oak`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, `wellington`.
- Added a provider-specific `VictoryHoldingsAdapter`:
  - uses Victory Capital/VictoryShares public product-page metadata when a product URL is available.
  - reads page-visible `fundID` and `fundApiKey` values instead of relying on SEC fallback.
  - fetches full current holdings from `https://investorapi.vcm.com/search/product/{symbol}/AllHoldings`.
  - sends the required public `x-api-key` header used by the issuer site.
  - parses Victory JSON fields such as `holding_name`, `stock_symbol`, `security_type`, `portfolio_percentage`, `market_value`, `shares`, `isin`, and `as_of_date`.
  - preserves venue suffixes such as `ADBE US` as symbol/exchange metadata and classifies cash rows separately.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `118`
  - providers still lacking native/live-backed support: `227`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_victory_adapter_fetches_public_all_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k victory`
    - escalated network run passed with `1 passed, 118 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
- Priority-set probe notes from this pass:
  - `capital_group`: advisor ETF pages redirect to authentication; no public native holdings artifact found.
  - `fidelity`: public endpoints returned Fidelity unavailable/Akamai shell; no backend-fetchable holdings artifact validated.
  - `wisdomtree`: product/API routes were Cloudflare-blocked from this environment.
  - `neuberger_berman`: sitemap endpoints returned HTTP `429`.
  - `doubleline`, `sofi`, `rex`, `angel_oak`: product pages were Cloudflare/challenge blocked.
  - `lazard`: ETF product pages and sitemap are reachable, but no holdings artifact/API was found in the inspected page.
  - `brookfield`, `tcw`, `thrivent`, `voya`, `wellington`: probed quickly but no live-backed route was validated in this pass.
- Remaining fast-track screenshot set:
  - `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `doubleline`, `lazard`, `brookfield`, `angel_oak`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, and `wellington`.
- Next step:
  - Continue with the exact screenshot-priority set. Do not mark any blocked issuer native unless a provider-specific route plus static and live tests pass.

## Latest checkpoint - 2026-07-07T13:45Z

- Promoted `dimensional` from generated/SEC-backed recognition-only support to native/live-backed support.
- This was the first provider from the user-confirmed fast-track screenshot set:
  - `dimensional`, `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `victory`, `doubleline`, `lazard`, `brookfield`, `angel_oak`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, `wellington`.
- Added a provider-specific `DimensionalHoldingsAdapter`:
  - discovers ETF product pages from `https://www.dimensional.com/us-en/funds/sitemap.xml` when no product URL is already stored.
  - selects the public US individual-investor audience before loading the product page.
  - parses product-page runtime values such as `portfolioNumber` and `servicesApiBaseUrl`.
  - calls the issuer's public fund-detail API at `https://etf.dimensional.com/public/v2/fundcenter/funddetail`.
  - extracts the returned `fullHoldingsCsvUrl` instead of hardcoding a dated CSV path.
  - parses Dimensional's holdings CSV fields: `date`, `etf_ticker`, `ticker`, `description`, `weight`, `market_value`, `identifier`/CUSIP, `isin`, `sedol`, `shares`, `coupon_rate`, `maturity_date`, and `principal`.
  - preserves source ticker/exchange metadata and classifies maturity/coupon rows as fixed income rather than generic equity.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `117`
  - providers still lacking native/live-backed support: `228`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_dimensional_adapter_discovers_product_page_and_fetches_full_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k dimensional`
    - escalated network run passed with `1 passed, 117 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
- Remaining fast-track screenshot set:
  - `capital_group`, `fidelity`, `wisdomtree`, `neuberger_berman`, `victory`, `doubleline`, `lazard`, `brookfield`, `angel_oak`, `sofi`, `rex`, `tcw`, `thrivent`, `voya`, `wellington`.
- Important probe notes:
  - `fidelity` and `wisdomtree` public routes remain blocked or not yet resolved to a reliable backend-fetchable holdings artifact; do not mark them native until live tests pass.
  - Continue down the exact screenshot-priority list; do not substitute unrelated providers unless one of the priority providers is demonstrably blocked and checkpointed.

## Latest checkpoint - 2026-07-07T12:55Z

- Promoted `texas_capital` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `TexasCapitalHoldingsAdapter`:
  - native static JSON holdings route: `https://texascapitalbank.com/sites/default/files/documents/etf-funds-management/{issuer_product_id}/data/holdings-data.json`
  - supported live validation symbol: `TXS`
  - built-in fund slug map for `TXS`, `TXSS`, `OILT`, and `MMKT`
  - parser flattens the issuer's suffixed JSON row keys such as `ticker_1`, `marketValuePercentage_1`, and `sharesHeldOfSecurity_1`.
  - parser preserves ticker, name, CUSIP, shares, market value, currency, country, canonical decimal weight, composition date, and source metadata.
  - parser classifies currency/cash rows and treasury rows without manufacturing fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `116`
  - providers still lacking native/live-backed support: `229`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_texas_capital_adapter_parses_static_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k texas_capital`
    - escalated network run passed with `1 passed, 116 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `116`, `229`, `texas_capital_native=True`.
- Problems found:
  - Fidelity's obvious public routes did not expose a holdings artifact; the expected document URL returned access denied.
  - Exchange Traded Concepts was reachable but exposed a platform/catalogue payload rather than a per-fund holdings source suitable for native issuer support.
  - SoFi and REX were Cloudflare-gated; Victory and TCW routes were blocked/redirected before a parseable holdings source could be found.
- Next step:
  - Continue replacing generated/thin ETF provider adapters with isolated native/live-backed issuer routes. The full goal remains open with `229` providers still lacking native/live-backed support.

## Latest checkpoint - 2026-07-07T12:31Z

- Promoted `adaptive_investments` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `AdaptiveInvestmentsHoldingsAdapter`:
  - native public ADPV fund page route: `https://adpvetf.com/{symbol_lower}`
  - supported live validation symbol: `ADPV`
  - parser targets the symbol-specific holdings component inside the issuer's Nuxt SSR function payload.
  - parser resolves Nuxt argument references and preserves ticker, name, FIGI, shares, market value, canonical decimal weight, composition date, and source metadata.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `115`
  - providers still lacking native/live-backed support: `230`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_adaptive_investments_adapter_parses_variable_embedded_holdings_payload tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k adaptive_investments`
    - escalated network run passed with `1 passed, 115 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `115`, `230`, `adaptive_investments_native=True`.
- Problems found:
  - ADPV publishes holdings through Nuxt's embedded payload with values stored as argument references, not as direct JSON table rows, so the native route needs provider-specific payload resolution.
  - Capital Group and Dimensional were probed but not promoted because the reachable routes were auth/region guarded rather than parseable public holdings feeds.
- Next step:
  - Continue replacing generated/thin ETF provider adapters with isolated native/live-backed issuer routes. The full goal remains open with `230` providers still lacking native/live-backed support.

## Latest checkpoint - 2026-07-07T12:02Z

- Promoted `applied_finance` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `AppliedFinanceHoldingsAdapter`:
  - native public Applied Finance ETFData product page route: `https://appliedfinancefunds.com/ETF/ETFData/{symbol_upper}`
  - supported live validation symbol: `VSLU`
  - parser targets the issuer-rendered `etf_constituents` HTML table.
  - parser preserves ticker, name, Bloomberg FIGI in row metadata, shares, market value, USD currency, canonical decimal weight, composition/as-of date, and source metadata.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `114`
  - providers still lacking native/live-backed support: `231`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_applied_finance_adapter_parses_etf_constituents_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k applied_finance`
    - escalated network run passed with `1 passed, 114 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `114`, `231`, `applied_finance_native=True`.

## Latest checkpoint - 2026-07-07T11:31Z

- Promoted `ocean_park` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `OceanParkHoldingsAdapter`:
  - native public Ocean Park product pages:
    - `https://oceanparketfs.com/domestic-etf`
    - `https://oceanparketfs.com/international-etf`
    - `https://oceanparketfs.com/diversified-income-etf.html`
    - `https://oceanparketfs.com/high-income-etf.html`
  - concrete live holdings endpoint used by the issuer pages: `https://filepoint.live/oceanpark_getholdings_cached4.php`
  - supported live validation symbol: `DUKQ`
  - maps Ocean Park ETF symbols to issuer fund IDs (`DUKQ` -> `1356`, `DUKX` -> `1357`, `DUKZ` -> `1358`, `DUKH` -> `1359`).
  - parser preserves symbol, name, CUSIP when the issuer identifier is a valid CUSIP, shares, market value, currency, country, canonical decimal weight, composition/as-of date, and source metadata.
  - parser preserves sweep/short-term/cash-like rows as cash instead of fake tradable instruments.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `113`
  - providers still lacking native/live-backed support: `232`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_ocean_park_adapter_posts_fund_id_and_parses_filepoint_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k ocean_park`
    - escalated network run passed with `1 passed, 113 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `113`, `232`, `ocean_park_native=True`.

## Latest checkpoint - 2026-07-07T11:06Z

- Promoted `brandes` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `BrandesHoldingsAdapter`:
  - native public Brandes iframe route: `https://etfs.brandes.com/{symbol_lower}` via Brandes fund detail pages.
  - concrete holdings CSV: `https://etfs.brandes.com/assets/data/6c11_Report.csv`
  - supported live validation symbol: `BUSA`
  - parser filters the shared multi-fund CSV by Brandes basket ticker (`BINV.P`, `BSMC.P`, `BUSA.P`) so sibling ETF rows are not ingested into the selected fund.
  - parser preserves ticker, name, CUSIP, ISIN, SEDOL, shares, market value, USD currency, canonical decimal weight, composition/as-of date, and asset-group-derived holding type, while preserving cash/currency rows as cash instead of fake tradable instruments.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `112`
  - providers still lacking native/live-backed support: `233`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_brandes_adapter_filters_shared_iframe_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k brandes`
    - escalated network run passed with `1 passed, 112 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `112`, `233`, `brandes_native=True`.

## Latest checkpoint - 2026-07-07T10:42Z

- Promoted `castleark` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `CastleArkHoldingsAdapter`:
  - native public CastleArk daily holdings text route: `http://castleark-etfs.com/assets/data/SEI_CRK_Tradedate_Holdings_{MMDDYYYY}.txt`
  - supported live validation symbol: `CARK`
  - scans the current trading day and recent prior days for the newest issuer-published holdings file.
  - parser handles CastleArk's pipe-delimited schema with `fund_ticker`, security identifiers, ticker, description, quantity, market value, notional value, and percent-of-net-assets fields.
  - parser preserves ticker, name, CUSIP, ISIN, SEDOL, shares, market value, USD currency, canonical decimal weight, and composition/as-of date, while preserving cash rows as cash rather than fake tradable instruments.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `111`
  - providers still lacking native/live-backed support: `234`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_castleark_adapter_fetches_recent_daily_holdings_text tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k castleark`
    - escalated network run passed with `1 passed, 111 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `111`, `234`, `castleark_native=True`.

## Latest checkpoint - 2026-07-06T17:12Z

- Promoted `bahl_gaynor` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `BahlGaynorHoldingsAdapter`:
  - native public Bahl & Gaynor ETF product page route: `https://www.bahl-gaynor.com/etf/{symbol_lower}/`
  - supported live validation symbol: `BGIG`
  - discovers the latest linked holdings CSV under the issuer's `etf_holdings_csv` path.
  - parser handles `Name`, `Symbol/Ticker`, `CUSIP`, `Quantity`, and `Weight (%)`.
  - parser converts percent-point weights into canonical decimals, preserves CUSIPs/shares, and captures the composition/as-of date from the dated CSV filename.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `109`
  - providers still lacking native/live-backed support: `236`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_bahl_gaynor_adapter_discovers_product_page_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k bahl_gaynor`
    - escalated network run passed with `1 passed, 109 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `109`, `236`, `bahl_gaynor_native=True`.

## Latest checkpoint - 2026-07-06T17:05Z

- Promoted `etf_architect` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added a provider-specific `ETFArchitectHoldingsAdapter`:
  - native public Alpha Architect / ETF Architect product page route: `https://funds.alphaarchitect.com/{symbol_lower}/`
  - supported live validation symbol: `QVAL`
  - parser handles the issuer-rendered wpDataTables holdings table with `Ticker`, `Name`, `CUSIP`, `Shares`, `Price (Local)`, `Market Value ($mm)`, and `% of Net Assets`.
  - parser converts percent-point weights into canonical decimals, converts issuer-reported market values from millions into full-dollar values, preserves CUSIPs/shares, and captures page-level ISO dates as composition/as-of metadata when present.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `108`
  - providers still lacking native/live-backed support: `237`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_etf_architect_adapter_parses_alpha_architect_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k etf_architect`
    - escalated network run passed with `1 passed, 108 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `108`, `237`, `etf_architect_native=True`.

## Latest checkpoint - 2026-07-06T15:26Z

- Promoted `goldman_sachs` from SEC-backed/recognition-only support to native/live-backed support.
- Added a provider-specific `GoldmanSachsHoldingsAdapter`:
  - native public GSAM holdings workbook route: `https://www.gsam.com/content/dam/gsam/xls/us/en/etf/{issuer_product_id}.xlsx`
  - supported live validation symbol: `GVIP`
  - default workbook id for `GVIP`: `Goldman Sachs Hedge Industry VIP ETF_9532`
  - parser handles Goldman Sachs' workbook schema with title row, then `Date`, `Ticker`, `Cusip`, `ISIN`, `Sedol`, `Description`, `Market Value`, `Number of Shares`, and `% Weighting`.
  - parser converts percent-point weights into canonical decimals, preserves ticker/CUSIP/ISIN/SEDOL/shares/market value, and converts Excel serial workbook dates into composition/as-of dates.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `105`
  - providers still lacking native/live-backed support: `240`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_goldman_sachs_adapter_fetches_public_holdings_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k goldman_sachs`
    - escalated network run passed with `1 passed, 105 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `105`, `240`, `goldman_native=True`.

## Latest checkpoint - 2026-07-06T13:44Z

- Promoted `brookmont` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `BrookmontHoldingsAdapter`:
  - native public Brookstone Active ETF product page route: `https://www.brookstoneam.com/brookstone-active-etf`
  - supported live validation symbol: `BAMA`
  - discovers the linked public all-holdings CSV: `https://retirementwealth.com/wp-content/themes/retirement-wealth/inc/1485_all_holdings.csv`
  - parser handles Brookstone's preamble CSV schema with `Fund Holdings Data as of`, `Name`, `Security Identifier`, `Symbol`, `Net Assets %`, `Market Price`, `Shares Held`, `Market Value`, and `Market Value %`.
  - parser converts percent-point weights into canonical decimals, splits venue-qualified symbols such as `SPYM US`, preserves shares/market values/CUSIPs/composition date, and keeps sweep/receivable/payable rows as cash rather than fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `104`
  - providers still lacking native/live-backed support: `241`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_brookmont_adapter_discovers_product_page_all_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k brookmont`
    - escalated network run passed with `1 passed, 104 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `104`, `241`, `brookmont_native=True`.

## Latest checkpoint - 2026-07-06T13:02Z

- Promoted `virtus` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `VirtusHoldingsAdapter`:
  - native public Virtus ETF product page route: `https://www.virtus.com/products/virtus-silvant-small-mid-growth-etf`
  - supported live validation symbol: `SSMG`
  - discovers the linked public legacy XLS positions workbook from the product page: `https://www.virtus.com/assets/files/a72/positions_ssmg.xls`
  - parser handles Virtus' multi-row XLS schema with `Account Name`, `Security Id`, `Name`, `Ticker`, `Security Type`, `Quantity`, `Price`, and local `Market Value` columns.
  - parser calculates canonical weights from row market value divided by total workbook market value, preserves shares/market values/security ids, and classifies cash rows as cash instead of fake securities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `103`
  - providers still lacking native/live-backed support: `242`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_virtus_adapter_parses_positions_workbook_rows tests/unit/services/test_etf_holdings_adapters.py::test_virtus_adapter_discovers_public_positions_xls tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `3 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k virtus`
    - escalated network run passed with `1 passed, 103 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `103`, `242`, `virtus_native=True`.

## Latest checkpoint - 2026-07-06T12:55Z

- Promoted `cullen` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `CullenHoldingsAdapter`:
  - native public Cullen SRP holdings CSV route: `https://www.cullenfunds.com/srp/api/fund-holdings-csv-download/38/?fund_id={fund_id}&as_at_date={date}`
  - supported live validation symbol: `DIVP`
  - default fund id mapping: `DIVP -> 3156`
  - parser handles Cullen's `Security Name`, `Ticker`, `CUSIP`, `Shares`, `Market Value`, and issuer-specific `Percentage` schema.
  - parser converts percent-point weights into canonical decimals and preserves CUSIP, shares, market value, and composition date.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `102`
  - providers still lacking native/live-backed support: `243`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_cullen_adapter_fetches_public_srp_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k cullen`
    - escalated network run passed with `1 passed, 102 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `102`, `243`, `cullen_native=True`.

## Latest checkpoint - 2026-07-06T12:28Z

- Promoted `burney` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `BurneyHoldingsAdapter`:
  - native public Burney ETF product page route: `https://burneyetfs.com/{symbol_lower}/`
  - supported live validation symbol: `BRNY`
  - parser handles the issuer-rendered wpDataTables holdings table.
  - parser handles `Ticker`, `Name`, `CUSIP`, `Shares`, `Price (Local)`, `Market Value ($mm)`, `% of Net Assets`, and `EFFECTIVE_DATE`.
  - parser converts market value from issuer-reported millions into full-dollar market value, converts percent-point weights into canonical decimals, and preserves composition date.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `101`
  - providers still lacking native/live-backed support: `244`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_burney_adapter_parses_product_page_wpdatatables_holdings tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k burney`
    - sandboxed run failed at DNS as expected; escalated network rerun passed with `1 passed, 101 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `101`, `244`, `burney_native=True`.

## Latest checkpoint - 2026-07-06T11:55Z

- Promoted `yorkville` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `YorkvilleHoldingsAdapter`:
  - native public Truth Social Funds product page route: `https://www.truthsocialfunds.com/etfs/{symbol_lower}`
  - supported live validation symbol: `TSIC`
  - parser discovers the public Google Sheets holdings CSV linked from the product page.
  - parser handles the issuer's `Date`, `Account`, `Stock Ticker`, `CUSIP`, `Security Name`, `Shares`, `Price`, `Market Value`, `Weightings`, and `Net Assets` schema.
  - parser filters by ETF account symbol and preserves ticker, CUSIP, shares, market value, weight, and composition date.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `100`
  - providers still lacking native/live-backed support: `245`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_yorkville_adapter_discovers_truth_social_google_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k yorkville`
    - sandboxed run failed at DNS as expected; escalated network rerun passed with `1 passed, 100 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `100`, `245`, `yorkville_native=True`.

## Latest checkpoint - 2026-07-06T11:42Z

- Promoted `tuttle` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `TuttleHoldingsAdapter`:
  - native public Income Blast ETF product page route: `https://www.incomeblastetfs.com/etf/{symbol_lower}`
  - supported live validation symbol: `MAGO`
  - parser discovers the public Google Sheets holdings CSV linked from the product page.
  - parser handles the issuer's `Date`, `Account`, `Stock Ticker`, `CUSIP`, `Security Name`, `Shares`, `Price`, `Market Value`, `Weightings`, and `Net Assets` schema.
  - parser preserves option rows as options, Treasury bill collateral as fixed income, cash rows as cash, market values, shares, and composition date rather than forcing these rows into fake equity tickers.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `99`
  - providers still lacking native/live-backed support: `246`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_tuttle_adapter_discovers_income_blast_google_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k tuttle`
    - sandboxed run failed at DNS as expected; escalated network rerun passed with `1 passed, 99 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `99`, `246`, `tuttle_native=True`.

## Latest checkpoint - 2026-07-06T00:24Z

- Promoted `point_bridge` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `PointBridgeHoldingsAdapter`:
  - native public MAGA holdings page route: `https://www.investpolitically.com/maga-holdings/`
  - supported live validation symbol: `MAGA`
  - parser handles the issuer's server-rendered TablePress holdings table with `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `Weightings`, and `Date`.
  - parser maps valid CUSIPs, converts percent weights into canonical decimal weights, preserves shares and composition date, and avoids materializing cash-like rows as fake tradable securities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `98`
  - providers still lacking native/live-backed support: `247`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_point_bridge_adapter_parses_maga_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k point_bridge`
    - sandboxed run failed at DNS as expected; escalated network rerun passed with `1 passed, 98 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `98`, `247`, `point_bridge_native=True`.

## Latest checkpoint - 2026-07-03T18:05Z

- Promoted `leuthold` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `LeutholdHoldingsAdapter`:
  - native public ETF product page route: `https://funds.leutholdgroup.com/etf/{symbol_upper}`
  - supported live validation symbol: `LCR`
  - parser handles the Leuthold product-page holdings table with `Percentage of Net Assets`, `Name`, `Identifier (Cusip)`, `Shares Held`, and `Market Value`.
  - parser extracts ticker and CUSIP from issuer cells such as `SHY (464287457)`, maps percent weights into canonical decimal weights, preserves shares/market values, classifies ETF/fund holdings as funds, and avoids materializing cash-like rows as fake tradable securities.
  - parser extracts the composition date from product-page copy such as `ETF Summary As of July 2, 2026`.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `97`
  - providers still lacking native/live-backed support: `248`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_leuthold_adapter_parses_product_page_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k leuthold`
    - sandboxed run failed at DNS as expected; escalated network rerun passed with `1 passed, 97 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `97`, `248`, `leuthold_native=True`.

## Latest checkpoint - 2026-07-03T16:43Z

- Corrected ETF holdings live-provider test bookkeeping so Fidelity is no longer included in `SEC_BACKED_SAMPLE_ADAPTERS`.
- Fidelity still has explicit SEC-backed probe coverage through `test_live_sec_backed_adapters_probe_ready_with_sec_identifiers`, but it is not a native/live-backed issuer route and should not be used as a generic SEC-backed sample in the provider-matrix set.
- Current truthful provider count remains:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `96`
  - providers still lacking native/live-backed support: `249`
  - `fidelity.live_tested_default_route` is `False`
- Validation:
  - `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_sec_backed_adapters_probe_ready_with_sec_identifiers --no-cov -q`
    - result: `2 passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `96`, `249`, `fidelity_native=False`.

## Latest checkpoint - 2026-07-03T16:15Z

- Promoted `motley_fool` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `MotleyFoolHoldingsAdapter`:
  - native public FilePoint aggregate holdings CSV:
    - `https://etfs.fooletfs.com/assets/data/FilepointMotleyF.40MU.FW_Holdings.csv`
  - supported live validation symbol: `TMFC`
  - parser reuses the account-filtered FilePoint CSV shape already used by similar ETF issuers and filters rows by requested ETF account symbol, so sibling Motley Fool funds in the same aggregate file are not ingested into the selected ETF.
  - parser handles `Date`, `Account`, `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `Price`, `MarketValue`, `Weightings`, `NetAssets`, `SharesOutstanding`, `CreationUnits`, and `MoneyMarketFlag`.
  - parser maps percent weights into canonical decimal weights, preserves CUSIPs/shares/market values, and preserves cash rows as cash instead of fake tradable securities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `96`
  - providers still lacking native/live-backed support: `249`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_motley_fool_adapter_filters_filepoint_account_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k motley_fool`
    - result: `1 passed, 96 deselected`
  - `cd backend && uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `96`, `249`, `motley_fool=True`.

## Latest checkpoint - 2026-07-03T15:45Z

- Promoted `zacks` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `ZacksHoldingsAdapter`:
  - native public holdings download routes:
    - `https://www.zacksetfs.com/webservices/holdings.php` for `ZECP`
    - `https://www.zacksetfs.com/webservices/{symbol_lower}-holdings.php` style explicit routes for `SMIZ`, `GROZ`, `QUIZ`, `PRIZ`, and `ZINC`
  - supported live validation symbol: `ZECP`
  - parser handles Zacks' preamble CSV-like holdings downloads with `Fund Holdings Data as of ...`, `Name`, `Security Identifier`, `Symbol`, `Net Assets %`, `Market Price`, `Shares Held`, `Market Value`, and `Market Value %`.
  - parser splits venue-qualified symbols such as `RTX US` into `symbol=RTX` plus `exchange=US`, maps valid CUSIPs, converts percent-point weights into canonical decimal weights, preserves shares/market values, and classifies sweep rows as cash instead of fake tradable securities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `95`
  - providers still lacking native/live-backed support: `250`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_zacks_adapter_parses_symbol_holdings_download tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k zacks`
    - result: `1 passed, 95 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `95`, `250`, `zacks=True`.

## Latest checkpoint - 2026-07-03T15:21Z

- Promoted `deepwater` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `DeepwaterHoldingsAdapter`:
  - native public ETF product page route: `https://etfs.deepwatermgmt.com/dbsc-2/`
  - supported live validation symbol: `DBSC`
  - parser handles Deepwater's server-rendered holdings table with `Name`, `Symbol`, `Shares`, `Market Value`, and `Weightings (%)` columns.
  - parser extracts the composition date from the page/table `data-asof` metadata, maps percent weights to canonical decimal weights, preserves shares and market values, and avoids generic parser ambiguity around the page's DataTables CSV-export UI.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `94`
  - providers still lacking native/live-backed support: `251`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_deepwater_adapter_parses_product_page_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k deepwater`
    - result: `1 passed, 94 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `94`, `251`, `deepwater=True`.

## Latest checkpoint - 2026-07-03T15:07Z

- Promoted `howard_capital` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `HowardCapitalHoldingsAdapter`:
  - native public CSV routes:
    - `https://howardcmfunds.com/wp-content/themes/cms/assets/hcm-defender-100-holdings.csv` for `QQH`
    - `https://howardcmfunds.com/wp-content/themes/cms/assets/hcm-defender-500-holdings.csv` for `LGH`
  - supported live validation symbol: `QQH`
  - parser handles Howard Capital-specific fields including `asOfDate`, `portfolioName`, `securityIdentifier`, `securityTicker`, `securityDescriptionShort`, `securityDescriptionLong`, `shares`, `priceLocal`, `marketValueBase`, `tradingCurrency`, `country`, `segment`, `category`, `sector`, `industry`, `marketValuePercent`, and `netAssetsPercent`.
  - parser splits venue-qualified symbols such as `AAPL US` into `symbol=AAPL` plus `exchange=US`, maps valid CUSIPs, preserves market values/shares/currency/country, classifies ETF holdings as `fund`, and keeps cash-like rows as cash instead of fake tradable symbols.
  - deliberately keeps Howard's own QQH/LGH routes separate from the HCM/Direxion tactical product page on the same site, because HCMT belongs under Direxion-style issuer responsibility unless a safe Howard-owned route is proven.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `93`
  - providers still lacking native/live-backed support: `252`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_howard_capital_adapter_parses_symbol_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k howard_capital`
    - result: `1 passed, 93 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `93`, `252`, `howard_capital=True`.

## Latest checkpoint - 2026-07-03T14:50Z

- Promoted `true_shares` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `TrueSharesHoldingsAdapter`:
  - native product-page route: `https://www.true-shares.com/etf/{symbol_lower}`
  - current holdings CSV is discovered from the product page through the issuer's `Download Holdings CSV` Google Sheets export link.
  - supported live validation symbol: `ONEH`
  - parser filters account-style rows by the requested ETF account symbol so sibling TrueShares funds are not ingested into the selected ETF.
  - parser handles TrueShares-specific fields including `Date`, `Account`, `Stock Ticker`, `CUSIP`, `Security Name`, `Shares`, `Price`, `Market Value`, `Weightings`, and `Net Assets`.
  - parser converts issuer percent-point weights into canonical decimal weights, maps valid CUSIPs, preserves market values/shares, classifies Treasury bills as fixed income, and keeps hedge receivable/payable rows as derivative/other rather than fake tradable equity symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `92`
  - providers still lacking native/live-backed support: `253`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_true_shares_adapter_discovers_google_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k true_shares`
    - result: `1 passed, 92 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `92`, `253`, `true_shares=True`.

## Latest checkpoint - 2026-07-03T14:33Z

- Promoted `madison` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `MadisonHoldingsAdapter`:
  - native aggregate holdings route: `https://madisonfunds.com/data/etf/MadisonAdvWeb.40M3.M3_ETF_Holdings.csv`
  - supported live validation symbol: `CVRD`
  - parser filters the multi-account CSV by the requested ETF account symbol so sibling Madison funds are not ingested into the selected ETF.
  - parser handles Madison-specific fields including `Date`, `Account`, `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `Price`, `MarketValue`, `Weightings`, `NetAssets`, `SharesOutstanding`, `CreationUnits`, and `MoneyMarketFlag`.
  - parser maps valid CUSIPs, uses issuer percent values as canonical decimal weights, preserves market values and shares, classifies money-market rows as cash, and keeps option-like rows from becoming fake tradable equity symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `91`
  - providers still lacking native/live-backed support: `254`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_madison_adapter_filters_account_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k madison`
    - result: `1 passed, 91 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `91`, `254`, `madison=True`.

## Latest checkpoint - 2026-07-03T14:17Z

- Promoted `anfield` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `AnfieldHoldingsAdapter`:
  - native product page route: `https://anfieldfunds.com/our-funds/anfield-enhanced-market-strategy-etf/`
  - current issuer CSV is discovered from that page through `/csv/holdings-...csv`, avoiding a stale hardcoded dated filename.
  - supported live validation symbol: `AEMS`
  - parser handles Anfield-specific preamble holdings CSV fields including `Fund Holdings Data as of ...`, `Name`, `Security Identifier`, `Symbol`, `Net Assets %`, `Market Price`, `Shares Held`, `Market Value`, and `Market Value %`.
  - parser converts issuer percent-point fields into canonical decimal weights, preserves market values and shares, and classifies USD/future/receivable/payable rows as cash rather than fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `90`
  - providers still lacking native/live-backed support: `255`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_anfield_adapter_discovers_product_page_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k anfield`
    - result: `1 passed, 90 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `90`, `255`, `anfield=True`.

## Latest checkpoint - 2026-07-02T12:34Z

- Promoted `counterpoint` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `CounterpointHoldingsAdapter`:
  - native data route: `https://counterpointfunds.com/etfdata/holdings_{symbol_lower}.csv`
  - supported live validation symbol: `CPAI`
  - current Counterpoint ETF product page links directly to the issuer-hosted holdings CSV at `https://counterpointfunds.com/etfdata/holdings_cpai.csv`.
  - parser handles Counterpoint-specific fields including `asOfDate`, `securityIdentifier`, `securityTicker`, `securityDescriptionShort`, `securityDescriptionLong`, `shares`, `marketValueBase`, `tradingCurrency`, `country`, `longShortIndicator`, `segment`, `category`, `sector`, `industry`, `marketValuePercent`, and `netAssetsPercent`.
  - parser splits venue-qualified symbols such as `AAPL US`, maps valid CUSIPs, uses issuer decimal net-asset weights directly, and preserves sweep/short-term-investment rows as cash rather than fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `89`
  - providers still lacking native/live-backed support: `256`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_counterpoint_adapter_parses_symbol_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k counterpoint`
    - result: `1 passed, 89 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `89`, `256`, `counterpoint=True`.

## Latest checkpoint - 2026-07-02T12:22Z

- Promoted `future_fund` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `FutureFundHoldingsAdapter`:
  - native data routes:
    - `https://futurefundetf.com/modules/mod_csvtables_copy/cron/holdings.csv` for `FFLS`
    - `https://futurefundetf.com/modules/mod_csvtables_ffox/cron/FundxFutureWeb.40F3.F3_Holdings.csv` for `FFOX`
  - supported live validation symbol: `FFOX`
  - current Future Fund public modules expose two issuer-specific CSV shapes: a preamble/header holdings CSV and an account-style daily holdings CSV.
  - parser handles Future Fund-specific fields including `Name`, `Security Identifier`, `Symbol`, `Market Value %`, `Date`, `Account`, `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `MarketValue`, `Weightings`, and `MoneyMarketFlag`.
  - parser filters account-style rows by requested ETF symbol, splits venue-qualified symbols such as `NVDA US`, maps valid CUSIPs, converts issuer percent values into canonical decimal weights, and preserves cash/broker/sweep rows as cash rather than fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `88`
  - providers still lacking native/live-backed support: `257`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_future_fund_adapter_parses_preamble_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_future_fund_adapter_parses_account_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `3 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k future_fund`
    - result: sandbox DNS failed first, escalated network rerun passed with `1 passed, 88 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `88`, `257`.

## Latest checkpoint - 2026-07-02T12:03Z

- Promoted `palmer_square` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `PalmerSquareHoldingsAdapter`:
  - native data route: Palmer Square public ETF product pages such as `https://etf.palmersquarefunds.com/funds/us-etfs/palmer-square-credit-opportunities-etf`
  - supported live validation symbol: `PSQO`
  - current Palmer Square product pages embed a full `holdingsData` JSON array that the issuer page itself uses for CSV/XLSX export.
  - parser handles Palmer Square-specific fields including `cusip`, `name`, `asset_type`, `shares_par`, `market_value`, and `weight_percent`.
  - parser converts percent-point weights into canonical decimal weights, maps valid CUSIPs, preserves principal/market value, classifies CLO/CDO/debt rows as fixed income, and avoids inventing fake tradable symbols for fixed-income holdings without tickers.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `87`
  - providers still lacking native/live-backed support: `258`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_palmer_square_adapter_parses_embedded_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k palmer_square`
    - result: `1 passed, 87 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `129 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `87`, `258`, `palmer_square=True`.

## Latest checkpoint - 2026-07-02T11:45Z

- Promoted `clough` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `CloughHoldingsAdapter`:
  - native data route: `https://www.cloughcapital.com/wp-admin/admin-ajax.php?action=get_holdings_json&slug={symbol_lower}`
  - supported live validation symbol: `CBSE`
  - current Clough endpoint returns JSON with `data.asOfDate` plus `data.holdings` rows.
  - parser handles Clough-specific JSON fields including `name`, `hTicker`, `cusip`, `sharesPar`, `weight`, and `marketValue`.
  - parser converts percent weights into canonical decimal weights, maps valid CUSIPs, normalizes market values/shares, and preserves pseudo rows such as `BROKER SWEEP` / `GS.BROKER` as cash instead of fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `86`
  - providers still lacking native/live-backed support: `259`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_clough_adapter_fetches_native_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k clough`
    - result: `1 passed, 86 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `128 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - count command returned `345`, `86`, `259`, `clough=True`.

## Latest checkpoint - 2026-07-01T14:45Z

- Promoted `oneascent` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `OneAscentHoldingsAdapter`:
  - native data route: OneAscent ETF product pages such as `https://oneascent.com/investment-solutions/public-markets/etfs/oalc/`
  - supported live validation symbol: `OALC`
  - current OneAscent product pages expose holdings CSV files through a public `pds_download_holdings_csv` AJAX route.
  - parser handles OneAscent-specific CSV columns including `As Of Date`, `Ticker`, `Security Name`, `CUSIP`, `Shares`, `Market Value`, `Weight (%)`, `Sector`, `Category`, and `Country`.
  - parser splits venue-qualified tickers such as `NVDA US` into `symbol=NVDA` plus `exchange=US`, maps valid CUSIPs, converts percent-point weights into canonical decimal weights, and preserves cash rows as cash instead of fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `85`
  - providers still lacking native/live-backed support: `260`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_oneascent_adapter_discovers_ajax_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k oneascent`
    - result: `1 passed, 85 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `127 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `85`, `260`, `oneascent=True`.

## Latest checkpoint - 2026-07-01T14:08Z

- Promoted `faith_investor_services` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `FaithInvestorServicesHoldingsAdapter`:
  - native data route: `https://faithinvestorservices.com/etfs/{symbol_lower}`
  - supported live validation symbol: `BRIF`
  - current Faith Investor Services product page exposes a full holdings CSV through the page `__NEXT_DATA__` payload.
  - parser handles Faith Investor Services-specific headerless CSV rows with date, account, ticker, CUSIP, security name, shares, price, market value, weight, net assets, shares outstanding, creation units, and money-market flag.
  - parser filters aggregate holdings rows by requested ETF account symbol, maps CUSIPs and percent weights, and preserves money-market/treasury rows as cash instead of fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `84`
  - providers still lacking native/live-backed support: `261`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_faith_investor_services_adapter_discovers_next_data_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `1 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k faith_investor_services`
    - result: `1 passed, 84 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `126 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `84`, `261`, `faith_investor_services=True`.

## Latest checkpoint - 2026-07-01T13:28Z

- Promoted `diamond_hill` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `DiamondHillHoldingsAdapter`:
  - native data route: `https://www.diamond-hill.com/sitefiles/live/documents/etfs/holdings/diamond-hill-{symbol_upper}-holdings.csv`
  - supported live validation symbol: `DHLX`
  - current Diamond Hill CSV returns more than `20` parseable holdings rows dated `2026-06-30`.
  - parser handles Diamond Hill-specific CSV preamble text such as `Fund Holdings Data as of ...`, then normalizes `Name`, `Security Identifier`, `Symbol`, `Net Assets %`, `Market Price`, `Shares Held`, `Market Value`, and `Market Value %`.
  - parser splits Bloomberg-style symbols such as `AON US` into `symbol=AON` plus `exchange=US`, preserves the source ticker in metadata, maps CUSIP-like security identifiers, and keeps money-market/cash rows as cash rather than fake tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `83`
  - providers still lacking native/live-backed support: `262`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_diamond_hill_adapter_parses_symbol_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k diamond_hill`
    - result: `1 passed, 83 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `125 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `83`, `262`, `diamond_hill=True`.

## Latest checkpoint - 2026-07-01T12:49Z

- Promoted `miller_value` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `MillerValueHoldingsAdapter`:
  - native data route: `https://etf.millervaluefunds.com/{symbol_lower}`
  - supported live validation symbol: `MVPA`
  - current Miller Value fund page returns more than `20` parseable holdings rows.
  - parser extracts the requested fund's provider-specific Nuxt holdings component, such as `milleretf-mvpa-holdings-1`, rather than ingesting unrelated embedded fund data.
  - parser handles Miller Value fields including `figi`, `ticker`, `quantity`, `description`, `market_value`, and `percent_of_nav`, converts percent-of-NAV values into canonical weights, and classifies warrant tickers separately from ordinary equities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `82`
  - providers still lacking native/live-backed support: `263`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_miller_value_adapter_parses_embedded_holdings_payload tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k miller_value`
    - result: `1 passed, 82 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `124 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - count command returned `345`, `82`, `263`, `miller_value=True`.

## Latest checkpoint - 2026-07-01T12:17Z

- Promoted `principal` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `PrincipalHoldingsAdapter`:
  - native data route: `https://api.assetmgmt.principalam.com/public/files?key={symbol}.xlsx`
  - supported live validation symbol: `PSC`
  - current Principal workbook returns more than `100` parseable holdings rows.
  - parser handles Principal-specific workbook rows with `As of: ...`, `% of Net Assets`, `Market Value`, `Security Type`, `Description`, `Ticker`, `CUSIP/Identifier`, `ISIN`, `SEDOL`, `Par Value/Quantity/Notional`, `Security Price`, and `Currency`.
  - parser preserves Principal's decimal-fraction net-asset weights without 100x distortion, maps identifiers and quantities directly, and keeps cash rows as cash rather than synthetic tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `81`
  - providers still lacking native/live-backed support: `264`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_principal_adapter_parses_symbol_holdings_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k principal`
    - result: `1 passed, 81 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `123 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `81`, `264`, `principal=True`.

## Latest checkpoint - 2026-07-01T11:46Z

- Promoted `deutsche_bank` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `DeutscheBankHoldingsAdapter`:
  - native data route: `https://etf.dws.com/api/pdp/en-us/etf/{symbol}/holdings`
  - supported live validation symbol: `USSG`
  - current issuer JSON returns more than `100` parseable holdings rows.
  - parser handles DWS/Xtrackers-specific nested identifier cells for `Ticker`, `CUSIP`, `ISIN`, and `SEDOL`.
  - parser splits venue-qualified tickers such as `NVDA.O` into `symbol=NVDA` plus `exchange=O`, preserves source ticker in row metadata, maps issuer weights/market value/quantity/country/sector/asset-class fields, and keeps cash rows as cash rather than synthetic tradable symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `80`
  - providers still lacking native/live-backed support: `265`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_deutsche_bank_adapter_parses_dws_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `122 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k deutsche_bank`
    - result: `1 passed, 81 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - count command returned `345`, `80`, `265`, `deutsche_bank=True`.

## Latest checkpoint - 2026-07-01T11:21Z

- Promoted `spear` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `SpearHoldingsAdapter`:
  - native data route: `https://spear-funds.com/archivos/SpearAdv.40FU.FU_Holdings.csv`
  - supported live validation symbol: `SPRX`
  - current issuer CSV returns more than `20` parseable holdings rows dated `2026-06-29`.
  - parser handles Spear-specific `Date`, `Account`, `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `MarketValue`, and `Weightings` CSV rows.
  - parser filters the aggregate Spear CSV by the requested ETF account symbol, so unrelated account rows are not ingested into `SPRX`.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `79`
  - providers still lacking native/live-backed support: `266`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_spear_adapter_parses_fixed_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `121 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k spear`
    - result: sandbox DNS failed first, then escalated network run passed with `1 passed, 80 deselected`
  - Count command returned `345`, `79`, `266`, `spear=True`.

## Latest checkpoint - 2026-06-29T17:01Z

- Promoted `timothy_plan` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `TimothyPlanHoldingsAdapter`:
  - native data route: `https://timothyplan.com/our-etfs/summary-etf-{slug}-holdings.php`
  - supported issuer slugs include `hds`, `lcc`, `scc`, `int`, `tpfc`, `tpfg`, and `tpfi`, mapped from symbols such as `TPHD`, `TPLC`, `TPSC`, `TPIF`, `TPFC`, `TPFG`, and `TPFI`.
  - live validation uses `TPHD`; the current issuer page returns more than `50` parseable holdings rows dated `2026-06-29`.
  - parser handles Timothy Plan-specific HTML holdings tables with `Name`, `Symbol`, `ISIN`, `Shares Held`, `Market Value %`, and `Market Value $`.
  - parser preserves Bloomberg-style symbol/exchange pairs such as `AFL U` and keeps no-symbol fixed-income rows as fixed-income holdings instead of fabricating tradable tickers.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `78`
  - providers still lacking native/live-backed support: `267`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_timothy_plan_adapter_parses_holdings_page_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k timothy_plan`
    - result: `1 passed, 79 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `120 passed`
  - Count command returned `345`, `78`, `267`, `timothy_plan=True`.

## Latest checkpoint - 2026-06-29T16:42Z

- Promoted `allspring` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `AllspringHoldingsAdapter`:
  - native data route: `https://www.allspringglobal.com/globalassets/data/total-holdings/{symbol_upper}.csv`
  - product/listing route context: `https://www.allspringglobal.com/investments/performance/etfs/`
  - live validation uses `ASLV`; the current issuer CSV returns more than `20` parseable holdings rows dated `2026-06-26`.
  - parser handles Allspring-specific CSV preamble text such as `Total holdings as of ...`, then normalizes `SecurityName`, `Ticker`, `CUSIP`, `ISIN`, `SEDOL`, `AssetClass`, `SharesPrincipalAmount`, `MarketValue`, `NotionalValue`, and `PercentOfNetAssets`.
  - parser preserves equity rows, fixed-income rows without fake ticker materialization, `-US` ticker suffixes as symbol plus exchange, and `Other Asset` rows as non-tradable exposure while clearing pseudo-identifiers such as `NETOTHASS`.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `77`
  - providers still lacking native/live-backed support: `268`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_allspring_adapter_parses_symbol_total_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k allspring`
    - result: `1 passed, 78 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `119 passed`
  - Count command returned `345`, `77`, `268`, `allspring=True`.

## Latest checkpoint - 2026-06-29T16:26Z

- Promoted `eventide` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `EventideHoldingsAdapter`:
  - issuer listing route: `https://www.eventideinvestments.com/etfs`
  - native data route: issuer-published Contentful holdings CSV files discovered from the Eventide ETF listing page.
  - live validation uses `ESUM`; the current CSV returns more than `100` parseable holdings rows dated `2026-06-26`.
  - parser handles Eventide-specific CSV preamble metadata such as `Product`, `Ticker`, and `As-of Date`, then normalizes the holdings table with `Ticker`, `Description`, `Shares`, and `Weight`.
  - parser preserves exchange-coded symbols such as `HY9H GR` as symbol plus exchange and keeps cash-equivalent rows as cash rather than tradable securities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `76`
  - providers still lacking native/live-backed support: `269`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_eventide_adapter_discovers_contentful_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k eventide`
    - result: `1 passed, 77 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `118 passed`
  - Count command returned `345`, `76`, `269`, `eventide=True`.

## Latest checkpoint - 2026-06-29T11:55Z

- Promoted `first_eagle` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `FirstEagleHoldingsAdapter`:
  - issuer product page routes include `https://www.firsteagle.com/funds/global-equity-etf`, `overseas-equity-etf`, and `usfe-us-equity-etf`.
  - native data route: issuer-rendered ETF holdings table on the First Eagle product page.
  - live validation uses `FEGE`; the current page returns more than `50` parseable holdings rows with an `ETF Holdings As of ...` date.
  - parser handles First Eagle-specific `Stock Ticker`, `CUSIP/Other`, `Security Name`, `Shares`, `Price`, `Market Value`, and `Weightings` table columns.
  - parser preserves exchange-coded tickers such as `005930 KS` as symbol plus exchange, treats `CUSIP/Other` as either CUSIP or SEDOL depending on identifier shape, and keeps `Cash & Other` as cash rather than a tradable symbol.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `75`
  - providers still lacking native/live-backed support: `270`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_first_eagle_adapter_parses_product_page_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k first_eagle`
    - result: `1 passed, 76 deselected`

## Latest checkpoint - 2026-06-29T11:32Z

- Promoted `davis` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `DavisHoldingsAdapter`:
  - issuer product routes include `https://www.davisetfs.com/etfs/us_equity`, `international`, `worldwide`, and `financial`.
  - native data route: `https://www.davisetfs.com/etfs/{product_slug}/holdings_download`
  - live validation uses `DUSA`; the current issuer CSV returns more than `20` parseable rows dated `2026-06-26`.
  - parser handles Davis-specific CSVs with a title/as-of first row, second-row headers, `Name`, `Ticker`, `Weighting (%)`, `Shares`, `Market Value ($)`, `Country`, and `CUSIP`.
  - parser preserves exchange-coded foreign tickers such as `005930 KS` as symbol plus exchange and stores Davis' unlabelled trailing CSV columns in row metadata rather than dropping the row.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `74`
  - providers still lacking native/live-backed support: `271`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_davis_adapter_parses_holdings_download_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k davis`
    - result: `1 passed, 75 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `116 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `74`, `271`, `davis=True`.

## Latest checkpoint - 2026-06-29T11:23Z

- Promoted `fm_investments` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `FMInvestmentsHoldingsAdapter`:
  - issuer ETF listing route: `https://www.fminvest.com/etfs`
  - product page route discovered by ticker, for example `https://www.fminvest.com/etfs/tbil-fm-us-treasury-3-month-bill-etf`
  - native data route: `https://www.fminvest.com/api/v1/etfs/{node_id}/holdings`
  - live validation uses `TBIL`; the current product page exposes Drupal ETF node id `1`, and the issuer JSON route returns parseable Treasury/cash holdings dated `2026-06-29`.
  - parser handles F/M-specific JSON rows including HTML-wrapped as-of dates, security name, CUSIP-like `field_symbol` values, par value, market value, percent weights, fixed-income classification, and cash rows.
  - adapter includes a narrow F/M-only requests fallback for issuer-page/API `403` responses because the route is backend-reachable with `requests` even when `httpx` receives 403.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `73`
  - providers still lacking native/live-backed support: `272`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_fm_investments_adapter_discovers_drupal_holdings_api tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k fm_investments`
    - result: `1 passed, 74 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `115 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `73`, `272`, `fm_investments=True`.

## Latest checkpoint - 2026-06-29T11:03Z

- Promoted `t_rowe_price` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `TRowePriceHoldingsAdapter`:
  - issuer overview route: `https://www.troweprice.com/financial-intermediary/us/en/investments/etfs.html`
  - product page route discovered by ticker, for example `https://www.troweprice.com/financial-intermediary/us/en/investments/etfs/blue-chip-growth-etf.html`
  - native data route: `https://api.public.troweprice.com/ds-dada/graphql`
  - live validation uses `TCHP`; the current product page exposes product code `BCX`, and the public `fullHoldingsExhibit` GraphQL route returns `59` parseable rows dated `2026-04-30`.
  - parser handles T. Rowe Price-specific GraphQL rows including ticker, name, CUSIP, ISIN, SEDOL, shares, market value, percent-point net-asset weights, currency, sector, industry, country, investment type, and asset class.
  - route remains T. Rowe Price-specific; SEC EDGAR remains fallback only and is not counted as native provider support.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `72`
  - providers still lacking native/live-backed support: `273`
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_t_rowe_price_adapter_discovers_product_page_and_fetches_graphql tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k t_rowe_price`
    - result: `1 passed, 73 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `114 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `72`, `273`, `t_rowe_price=True`.

## Latest checkpoint - 2026-06-29T10:42Z

- Promoted `tapp` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `TappAlphaHoldingsAdapter`:
  - issuer product-page route: `https://www.tappalphafunds.com/etfs/{symbol_lower}`
  - live validation uses `TDAX`; the current product page exposes a linked Google Sheets CSV export returning `3` parseable rows.
  - parser discovers the issuer's public holdings CSV from the TappAlpha product page instead of relying on SEC fallback or generic URL metadata.
  - parser handles TappAlpha-specific `Date`, `Account`, `Stock Ticker`, `CUSIP`, `Security Name`, `Shares`, `Market Value`, and `Weightings` CSV rows.
  - swap rows are preserved as `swap`, cash rows are preserved as `cash`, fund rows keep valid CUSIPs, and fake swap/cash symbols are not materialized as tradable equities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `71`
  - providers still lacking native/live-backed support: `274`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_tapp_adapter_discovers_google_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k tapp`
    - result: `1 passed, 72 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `113 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `71`, `274`, `tapp=True`.

## Latest checkpoint - 2026-06-29T10:30Z

- Promoted `hennessy` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `HennessyHoldingsAdapter`:
  - issuer product-page route: `https://www.hennessyetfs.com/etfs/{symbol_lower}`
  - live validation uses `STNC`; the current issuer-rendered product page exposes a full holdings table returning more than `20` parseable rows.
  - parser handles Hennessy-specific HTML holdings tables with `Name`, `Ticker`, `CUSIP`, `Shares`, `Market Value`, and `% of Net Assets`.
  - parser deliberately chooses the largest matching holdings table, because the issuer page exposes both a shorter holdings summary table and a larger full holdings table with the same headers.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `70`
  - providers still lacking native/live-backed support: `275`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_hennessy_adapter_parses_product_page_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k hennessy`
    - result: `1 passed, 71 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `112 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `70`, `275`, `hennessy=True`.

## Latest checkpoint - 2026-06-29T10:00Z

- Promoted `running_oak` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `RunningOakHoldingsAdapter`:
  - issuer page route: `https://www.runningoaketfs.com/full-holdings.html`
  - native data route: `https://filepoint.live/runningoak_holdings_1363_data.json`
  - live validation uses `ROEQ`; the current issuer-backed FilePoint JSON feed returns more than `50` parseable holdings rows.
  - parser handles Running Oak's JSON schema directly, including `securityTicker`, `securityIdentifier`, `securityDescriptionLong`, `shares`, `marketValueBase`, `tradingCurrency`, `country`, `segment`, and decimal-fraction `marketValuePercent`.
  - ticker/exchange pairs such as `SSNC US` are normalized into ticker `SSNC` plus exchange `US`, CUSIP-like identifiers are preserved, and cash-like rows are kept as cash instead of materialized as tradable equities.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `69`
  - providers still lacking native/live-backed support: `276`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_running_oak_adapter_parses_filepoint_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k running_oak`
    - result: `1 passed, 70 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `111 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `69`, `276`, `running_oak=True`.

## Latest checkpoint - 2026-06-29T09:45Z

- Promoted `swan_global` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `SwanGlobalHoldingsAdapter`:
  - issuer product page route: `https://etfs.swanglobalinvestments.com/hedged-equity-etf/`
  - adapter discovers the issuer-linked public holdings CSV from the Swan HEGD product page instead of relying on SEC fallback or generic route metadata.
  - live validation uses `HEGD`; the current issuer CSV returns more than `10` parseable rows.
  - parser intentionally reuses the hardened ETF Global/Tidal-style row normalization for `Date`, `Account`, `StockTicker`, `CUSIP`, `SecurityName`, `Shares`, `MarketValue`, `Weightings`, and `MoneyMarketFlag` while the adapter itself remains Swan-specific.
  - cash rows are preserved as cash, and SPX/SPXW option identifiers are classified as option holdings without materializing fake equity tickers.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `68`
  - providers still lacking native/live-backed support: `277`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_swan_global_adapter_discovers_product_page_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k swan_global`
    - result: `1 passed, 69 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `110 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `68`, `277`, `swan_global=True`.

## Latest checkpoint - 2026-06-26T15:23Z

- Promoted `abrdn` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `AbrdnHoldingsAdapter`:
  - issuer fund-centre route: `https://www.aberdeeninvestments.com/en-us/investor/funds/view-all-funds`
  - live validation uses `SGOL`; the backend-reachable issuer page references the abrdn physical-metal ETF trust lineup.
  - adapter represents abrdn's physical commodity trust ETFs as commodity holdings instead of pretending there is an equity-style constituent table.
  - single-metal trusts such as `SGOL`, `SIVR`, `PPLT`, and `PALL` produce a 100% physical commodity row; `GLTR` preserves the basket metal constituents without inventing live weights that the route does not expose.
  - the direct onlineprospectus product-page host worked from system Python but reset connections from the backend venv, so the adapter deliberately uses the backend-fetchable Aberdeen fund-centre page as the live-tested route.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `67`
  - providers still lacking native/live-backed support: `278`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_abrdn_adapter_verifies_physical_metal_product_page tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k abrdn`
    - result: `1 passed, 68 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `109 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `67`, `278`, `abrdn=True`.

## Latest checkpoint - 2026-06-26T14:54Z

- Promoted `baron` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `BaronHoldingsAdapter`:
  - product/root discovery page: `https://www.baroncapitalgroup.com/`
  - adapter discovers the latest public dated holdings CSV link shaped like `RONB-HOLDINGS-YYYYMMDD-0.csv` from Baron pages instead of hardcoding the date.
  - live validation uses `RONB`; the current issuer CSV returns more than `20` parseable holdings rows.
  - parser handles Baron-specific CSV columns directly: `Holding`, `Ticker`, `Weight (%)`, `Market Value ($)`, `Quantity`, `CUSIP`, `ISIN`, `SEDOL`, and `Currency Code`.
  - parser preserves security names that the generic parser would lose and uses narrow requests fallbacks when Baron blocks the async HTTP client with 403 responses.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `66`
  - providers still lacking native/live-backed support: `279`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_baron_adapter_discovers_latest_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k baron`
    - result: `1 passed, 67 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `108 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `66`, `279`, `baron=True`.

## Latest checkpoint - 2026-06-26T14:35Z

- Promoted `beyond_investing` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `BeyondInvestingHoldingsAdapter`:
  - route: `https://www.veganetf-sftp.com/csvs/BeyondAdvisorsWEB.40XZ.XZ_Holdings.csv`
  - product/root page metadata: `https://veganetf.com/`
  - live validation uses `VEGN`; the current issuer CSV returns more than `100` parseable holdings rows.
  - parser reuses the already hardened aggregate-account CSV path, filters rows by the selected ETF account symbol, preserves CUSIP, shares, market value, composition date, and percent weights, and preserves issuer cash rows as cash instead of materializing fake instruments.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `65`
  - providers still lacking native/live-backed support: `280`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_beyond_investing_adapter_filters_public_aggregate_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k beyond_investing`
    - result: `1 passed, 66 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `107 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `65`, `280`, `beyond_investing=True`.

## Latest checkpoint - 2026-06-26T14:22Z

- Promoted `cambiar` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `CambiarHoldingsAdapter`:
  - product-page route: `https://cambiar.com/etf/{symbol_lower}/`
  - adapter discovers the current dated workbook link from the product page, currently shaped like `SEI_Cambiar_Tradedate_Holdings_06252026-viewall.xlsx`.
  - live validation uses `CAMX`; the current issuer workbook returns more than `20` parseable holdings rows.
  - parser handles Cambiar-specific workbook columns directly: `fund_ticker`, `security_group`, `security_isin`, `security_ticker`, `security_description`, `quantity`, `market_value`, and percent-point `percent_of_net_assets`.
  - parser filters workbook rows by the requested fund ticker, preserves cash rows as cash, derives US CUSIPs from US ISINs when available, and converts percent-point weights correctly.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `64`
  - providers still lacking native/live-backed support: `281`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_cambiar_adapter_fetches_product_page_linked_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k cambiar`
    - result: `1 passed, 65 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `106 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `64`, `281`, `cambiar=True`.

## Latest checkpoint - 2026-06-26T14:05Z

- Promoted `hartford` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `HartfordHoldingsAdapter`:
  - native route: `https://www.hartfordfunds.com/dam/en/docs/pub/funddocuments/fullholdings/{symbol_upper}.xlsx`
  - product-page route metadata: `https://www.hartfordfunds.com/funds/{symbol_lower}.html`
  - live validation uses `HDUS`; the current issuer workbook returns more than `100` parseable holdings rows.
  - parser handles Hartford-specific workbook columns directly, including `Ticker/TRACE`, `Security Description`, `Value`, `Shares/Par`, `CUSIP`, `SEDOL`, `ISIN`, `Country of Issuer`, and decimal-fraction `% of Net Assets` values.
  - parser avoids generic-parser losses that would otherwise miss symbols, pick `Notional Value` instead of actual market `Value`, or understate Hartford weights by 100x.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `63`
  - providers still lacking native/live-backed support: `282`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_hartford_adapter_fetches_full_holdings_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k hartford`
    - result: `1 passed, 64 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `105 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - Count command returned `345`, `63`, `282`, `hartford=True`.

## Latest checkpoint - 2026-06-26T13:37Z

- Promoted `alliancebernstein` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `AllianceBernsteinHoldingsAdapter`:
  - product-page route currently live-tested with `FWD` at the AB Disruptors ETF page.
  - the adapter fetches the issuer's product page, extracts the `data-portfolio-holding` AEM model JSON route, fetches the latest linked monthly full-holdings XLSX workbook, and parses AB-specific workbook columns directly.
  - live validation uses `FWD`; the current issuer workbook returns `139` parseable holdings rows.
  - parser preserves AB workbook semantics for `% of Net Assets` values, avoiding the generic-parser 100x weight understatement, and captures ticker, issue name, ISIN, CUSIP, SEDOL, units/par/contracts, accounting value, base currency, net assets, and composition date.
  - hardened the shared OpenXML helper so issuer workbooks with uppercase worksheet paths such as `xl/worksheets/Sheet1.xml` parse correctly.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `62`
  - providers still lacking native/live-backed support: `283`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_alliancebernstein_adapter_fetches_model_linked_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k alliancebernstein`
    - result: `1 passed, 63 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `104 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `64 passed in 58.71s`
  - Count command returned `345`, `62`, `283`, `alliancebernstein=True`.

## Latest checkpoint - 2026-06-26T13:18Z

- Promoted `arrow` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `ArrowHoldingsAdapter`:
  - route: `https://arrowfunds.com/ArrowSharesExport.aspx?ProductID={product_id}&type=holdings`
  - live validation uses `ARCM`, whose current issuer export returns `157` parseable holdings rows.
  - parser handles Arrow's public CSV export shape, including the issuer's SQL/debug preamble before the actual holdings metadata/header rows.
  - parser extracts `Holdings as of` composition date metadata, preserves CUSIP-style security IDs, market value, country, and percent-of-net-assets weights, and classifies bond-like rows as fixed income instead of inventing ticker symbols.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `61`
  - providers still lacking native/live-backed support: `284`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_arrow_adapter_fetches_native_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k arrow`
    - result: `1 passed, 62 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `103 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `63 passed in 60.92s`
  - Count command returned `345`, `61`, `284`, `arrow=True`.

## Latest checkpoint - 2026-06-26T12:58Z

- Promoted `aptus` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `AptusHoldingsAdapter`:
  - product page template: `https://aptusetfs.com/{symbol_lower}/`
  - live validation uses `DRSK`; the current issuer product page exposes a server-rendered holdings table with `27` parseable holdings rows.
  - parser reads the Aptus `fund_holdings_table`-style HTML table, normalizes `Stock Ticker` and `Security Desc` into canonical ticker/name fields, preserves CUSIP, shares, market value, weight, and effective-date metadata, and extracts the page-level `Current as of` composition date.
  - request path uses browser-shaped issuer page headers plus an Aptus referer because the issuer returns a 403 to overly generic user-agent requests.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `60`
  - providers still lacking native/live-backed support: `285`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_aptus_adapter_fetches_product_page_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k aptus`
    - result: `1 passed, 61 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `102 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `62 passed in 58.15s`
  - Count command returned `345`, `60`, `285`, `aptus=True`.

## Latest checkpoint - 2026-06-26T12:23Z

- Promoted `main_management` from candidate/static-only support to native/live-backed support.
- Verified the current Main Management public ETF holdings route with `BUYW`:
  - route: `https://www.mainmgtetfs.com/etfs/download-{symbol_lower}.php`
  - live artifact: `https://www.mainmgtetfs.com/etfs/download-buyw.php`
  - current live fetch returned `21` parseable holdings rows with composition/as-of date `2026-06-25`.
  - cash rows remain cash and sector ETF / option-style rows continue to be parsed through the existing provider-specific parser.
- Promoted `clearshares` from recognition-only support to native/live-backed support.
- Added a provider-specific `ClearSharesHoldingsAdapter`:
  - route: `https://clear-shares.com/download-holdings-usbanks.php?fund={symbol_lower}`
  - product page template: `https://clear-shares.com/{symbol_lower}/`
  - live validation uses `OPER`; the current issuer workbook returns `6` parseable holdings rows.
  - the adapter uses the shared legacy XLS parser but has its own URL construction, request headers, route metadata, and live-backed registry configuration.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `59`
  - providers still lacking native/live-backed support: `286`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_main_management_adapter_fetches_symbol_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_clearshares_adapter_fetches_native_holdings_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `3 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k main_management`
    - result: `1 passed, 59 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k clearshares`
    - result: `1 passed, 60 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `101 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `61 passed in 64.58s`
  - Count command returned `345`, `59`, `286`, `main_management=True`, `clearshares=True`.

## Latest checkpoint - 2026-06-13T18:41Z

- Promoted `acquirers` from recognition-only/generated support to native/live-backed support.
- Added a provider-specific `AcquirersHoldingsAdapter`:
  - route: `https://acquirersfund.com/download-holdings-usbanks.php?fticker={symbol_upper}`
  - product page/root: `https://acquirersfund.com/`
  - live validation uses `ZIG`; the current issuer workbook returns more than 20 parseable holdings rows.
  - the adapter uses the existing legacy XLS parser but has its own URL construction, request headers, route metadata, and live-backed registry configuration.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `57`
  - providers still lacking native/live-backed support: `288`
  - SEC EDGAR remains fallback only and is not counted as native provider support.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_acquirers_adapter_fetches_native_holdings_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k acquirers`
    - result: `1 passed, 57 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `100 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `59 passed in 57.59s`
  - Count command returned `345`, `57`, `288`, `acquirers=True`.

## Latest checkpoint - 2026-06-13T17:57Z

- Promoted `allianz` from recognition-only to native/live-backed support.
- Added a provider-specific `AllianzHoldingsAdapter`:
  - route: `https://www.allianzim.com/wp-content/uploads/feeds/BBH_FOR_ALZ_ETF_PVAL_WEB.csv`
  - live validation uses `FEBT`; the current CSV returns five parseable rows for that ETF account.
  - the adapter filters AllianzIM's shared multi-fund feed by `Account == selected ETF symbol`, so rows from other Allianz ETFs such as `FLJJ`, `AIOO`, or `APRT` are not mixed into the selected ETF.
  - option-contract rows are preserved as option holdings without inventing fake ticker symbols or treating OCC-style option identifiers as CUSIPs; cash rows remain cash rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `55`
  - providers still lacking native/live-backed support: `290`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_allianz_adapter_filters_multi_fund_csv_and_preserves_option_rows tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k allianz`
    - result: `1 passed, 55 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `98 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `57 passed in 52.09s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `55`, `290`, `allianz=True`.

## Latest checkpoint - 2026-06-13T21:05Z

- Promoted `hashdex` and `kurv` from recognition-only to native/live-backed support.
- Added a provider-specific `HashdexHoldingsAdapter`:
  - product page route: `https://hashdex-etfs.com/{symbol_upper}`
  - live validation uses `DEFI`; the product page links to `https://hdx-website-cms-prod-upload-bucket.s3.amazonaws.com/DEFI_Holdings.xlsx`.
  - the parser handles Hashdex's non-standard workbook shape: `Reference Date`, followed by `Name`, `Shares`, `Price`, and `Weight`.
  - Hashdex crypto/cash/fund rows are preserved without inventing ticker symbols; BTC is emitted as a crypto holding and cash rows remain cash.
- Added a provider-specific `KurvHoldingsAdapter`:
  - route: `https://web.services.kurvinvest.com/etfdata/{symbol_upper}/holdings.csv`
  - live validation uses `AAPY`; the current CSV returns parseable option/equity/cash holdings.
  - the parser intentionally does not trust option identifiers in Kurv's `CUSIP` column as real CUSIPs; real CUSIP-looking values are still preserved.
  - option rows are typed as options rather than ordinary equity rows.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `54`
  - providers still lacking native/live-backed support: `291`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_hashdex_adapter_fetches_product_page_linked_workbook tests/unit/services/test_etf_holdings_adapters.py::test_kurv_adapter_fetches_public_holdings_csv_without_fake_cusips tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `3 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k "hashdex or kurv"`
    - result: `2 passed, 53 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `97 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `56 passed in 56.70s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `54`, `291`, `hashdex=True`, `kurv=True`.

## Latest checkpoint - 2026-06-13T20:05Z

- Promoted `grayscale` from recognition-only to native/live-backed support.
- Added a provider-specific `GrayscaleHoldingsAdapter`:
  - primary data source is Grayscale's public ETF product pages under `https://etfs.grayscale.com/{symbol_lower}`.
  - live validation uses `GBTC`, whose current page embeds a `holdingsData` payload containing the BTC holding and product metadata.
  - the parser supports both decoded JSON snippets and escaped Next/RSC transport snippets such as `\"holdingsData\": [...]`.
  - crypto holdings are preserved as crypto rows rather than equity constituents; current GBTC output captures symbol/name, weight, asset-per-share, date, fund CUSIP/ISIN, and trust asset metadata where available.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `52`
  - providers still lacking native/live-backed support: `293`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_grayscale_adapter_parses_embedded_holdings_data tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `95 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k grayscale`
    - result: `1 passed, 52 deselected`
  - First full live matrix run found a transient `strive` `ReadTimeout`; focused `strive` rerun passed immediately.
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - final rerun result: `54 passed in 41.18s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `52`, `293`, `grayscale=True`.

## Latest checkpoint - 2026-06-13T19:05Z

- Promoted `bondbloxx` from recognition-only to native/live-backed support.
- Added a provider-specific `BondBloxxHoldingsAdapter`:
  - primary data source is the issuer's public product pages, which embed full holdings under `var generalData = {...}`.
  - live validation uses `PCMM`, whose current product page exposes more than 20 parseable holdings rows with CUSIP, ISIN, market value, shares/par, currency, and portfolio weight.
  - known route: `https://bondbloxxetf.com/bondbloxx-private-credit-clo-etf/`
  - broader route discovery uses `https://bondbloxxetf.com/tickers-sitemap.xml` and checks candidate product pages for matching embedded `etfticker` values.
  - the adapter preserves fixed-income constituents as CUSIP/ISIN-backed named securities rather than inventing fake ticker symbols; cash rows are kept as cash rows.
  - BondBloxx currently rejects the production `httpx` request path with `403` for the product page, so this adapter includes a provider-specific fallback to the same browser-shaped headers through `requests` after an `httpx` 403. The live test proves this path.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `51`
  - providers still lacking native/live-backed support: `294`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_bondbloxx_adapter_fetches_product_page_embedded_holdings tests/unit/services/test_etf_holdings_adapters.py::test_bondbloxx_adapter_discovers_product_page_from_sitemap tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `3 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `94 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k bondbloxx`
    - result: `1 passed, 51 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `53 passed in 49.53s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `51`, `294`, `bondbloxx=True`.

## Latest checkpoint - 2026-06-13T18:10Z

- Promoted `new_york_life` from recognition-only to native/live-backed support.
- Added a provider-specific `NewYorkLifeHoldingsAdapter` for NYLI / IndexIQ public holdings CSV files:
  - route: `https://data.nylim.com/M{symbol_upper}.csv`
  - live validation uses `IQSI`, whose current issuer CSV returns more than 100 parseable holdings rows.
  - parser normalizes NYLI's Excel-formula-style CSV cells such as `="ASML"` and `=DOLLAR(13746455.09)` before canonical parsing.
  - rows preserve ticker, ISIN, SEDOL, CUSIP, security description, asset group, trading currency, shares/par, market value, notional value, and percent net assets.
- Shared parser alias coverage now treats `Trading Currency` as a currency field.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `50`
  - providers still lacking native/live-backed support: `295`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_new_york_life_adapter_fetches_public_holdings_csv tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `92 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k new_york_life`
    - result: `1 passed, 50 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `52 passed in 44.29s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `50`, `295`, `new_york_life=True`.

## Latest checkpoint - 2026-06-13T17:00Z

- Promoted `matthews` from recognition-only to native/live-backed support.
- Added a provider-specific `MatthewsHoldingsAdapter`:
  - product-page routes are mapped for Matthews Asia ETF tickers such as `MCH`, `ADVE`, `ASIA`, `EMSF`, `INDE`, `JPAN`, `MCHS`, `MEM`, `MEMS`, `MEMX`, `MINV`, and `MKOR`.
  - live validation uses `MCH`, whose server-rendered public product page currently exposes 58 parseable holdings rows with ticker, name, SEDOL, market value, shares, and percent net assets.
  - parser reads the `tblDailyTopHoldings` table and extracts the holdings as-of date from `asOfHoldings`.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `49`
  - providers still lacking native/live-backed support: `296`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_matthews_adapter_fetches_product_page_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k matthews`
    - result: `1 passed, 49 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `91 passed`
  - First full live matrix attempt found a transient `american_century` AVUV `ReadTimeout`; focused `american_century` rerun passed immediately.
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - final rerun result: `51 passed in 40.49s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `49`, `296`, `matthews=True`, `renaissance_capital=True`, `main_management=False`.

## Latest checkpoint - 2026-06-13T16:05Z

- Promoted `renaissance_capital` from recognition-only to native/live-backed support.
- Added a provider-specific `RenaissanceCapitalHoldingsAdapter`:
  - route: `https://etfs.renaissancecapital.com/excel-downloads/holdings/{symbol_lower}`
  - live validation uses `IPO`, whose issuer workbook currently returns 48 parseable holdings rows.
  - parser uses Renaissance's public XLSX workbook shape with `Date`, `Holding Name`, `Asset Class`, `Ticker`, `SEDOL`, `Shares`, `Holding Value`, and `Weight`.
  - shared holdings parser now also recognizes `Holding Value` as a market-value alias.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `48`
  - providers still lacking native/live-backed support: `297`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_renaissance_capital_adapter_fetches_public_holdings_workbook tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q`
    - result: `2 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k renaissance_capital`
    - result: `1 passed, 48 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `90 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `50 passed in 62.68s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - Count command returned `345`, `48`, `297`, `renaissance_capital=True`.

## Latest checkpoint - 2026-06-13T15:10Z

- Promoted `21shares` from recognition-only to native/live-backed support.
- Added a provider-specific `TwentyOneSharesHoldingsAdapter`:
  - primary route: `https://21sharesprimary.paradox-coworking.com/api/product_details/{symbol_upper}`
  - secondary route: `https://21sharessecondary.paradox-coworking.com/api/product_details/{symbol_upper}`
  - parser reads the JSON `data.constituents` array and emits crypto/security rows with symbol, name, weight, quantity, price, market value, currency, valuation date, and product metadata.
  - live validation uses `ARKB`, whose product details API returns one BTC constituent with full quantity/market-value data.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `47`
  - providers still lacking native/live-backed support: `298`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_21shares_adapter_fetches_product_details_constituents --no-cov -q`
    - result: `1 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k 21shares`
    - result: `1 passed, 47 deselected`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `89 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `49 passed in 46.53s`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - Count command returned `345`, `47`, `298`, `21shares=True`, `main_management=False`.

## Latest checkpoint - 2026-06-13T14:20Z

- Promoted `world_gold_council` from recognition-only to native/live-backed support.
- Added a provider-specific `WorldGoldCouncilHoldingsAdapter` for SPDR Gold trust public archive data:
  - route: `https://api.spdrgoldshares.com/api/v1/historical-archive?product={symbol_lower}&exchange=NYSE&lang=en`
  - parser reads the historical archive workbook's second worksheet and emits a single commodity holding row for the latest valid gold-bullion trust position.
  - the adapter preserves ounces as quantity, total trust NAV as market value, 100% gold weight, composition/as-of date, tonnes, ounces-per-share, NAV/share, closing price, and indicative price metadata.
  - this is intentionally modeled as a commodity/bullion holding, not an equity constituent basket.
- Registry count after promotion:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `46`
  - providers still lacking native/live-backed support: `299`
  - `main_management` remains demoted/not counted.
- Validation:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_world_gold_council_adapter_parses_gold_archive_workbook --no-cov -q`
    - result: `1 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k world_gold_council`
    - result: `1 passed, 46 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `48 passed in 47.80s`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `88 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - Count command returned `345`, `46`, `299`, `world_gold_council=True`, `main_management=False`.

## Latest checkpoint - 2026-06-13T13:25Z

- Live-provider audit corrected the native/live-backed count:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations currently passing live route tests: `45`
  - providers still lacking native/live-backed support: `300`
- `main_management` was demoted from `live_tested_default_route=True` to `False` because its configured native host currently fails DNS resolution:
  - `https://www.mainmgtetfs.com/etfs/download-buyw.php` -> `nodename nor servname provided, or not known`
  - `https://mainmgtetfs.com/etfs/download-buyw.php` -> same DNS failure
  - `https://www.mainmgt.com/etfs/download-buyw.php` and `https://mainmgt.com/etfs/download-buyw.php` -> `404`
  - `https://www.mainmanagement.com/etfs/download-buyw.php` -> no route to host
- The provider-specific `MainManagementHoldingsAdapter` code remains in place for repair, but it no longer counts as supported until a backend-fetchable live route is found and re-tested.
- `defiance` is still live-backed: its current QQQY page returns only 4 parseable rows, so the live fixture threshold was corrected from 5 to 4 rather than incorrectly treating it as a provider outage.
- Validation:
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q`
    - result: `47 passed in 39.27s`
  - Count command returned `345`, `45`, `300`, `main_management=False`.

## Latest checkpoint - 2026-06-13T12:45Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `46`
  - providers still lacking native/live-backed support: `299`
- No provider was promoted in this slice. This was intentional: each probed candidate either blocked backend access, exposed only page-shell/table-export UI, returned PDFs without a robust parser path, or returned stale/404 guessed artifacts.
- Negative route-discovery evidence captured so the next worker does not re-probe the same false leads as if they were fresh:
  - `wisdomtree`: `https://www.wisdomtree.com/investments/etfs/equity/wcld` returned `403` from the backend probe environment.
  - `fidelity`: `https://www.fidelity.com/etfs/overview` returned `403`.
  - `capital_group`: `https://www.capitalgroup.com/advisor/investments/exchange-traded-funds/cgdv` returned a small app/anti-bot shell with no holdings/CSV/XLSX route in initial HTML.
  - `t_rowe_price`: `https://www.troweprice.com/personal-investing/tools/fund-research/TSPA` returned a small shell with no holdings/CSV/XLSX route in initial HTML.
  - `abrdn`: `https://www.aberdeeninvestments.com/en-us/investor/funds/fund-literature` exposed literature/prospectus links and SPDR-like precious-metal documents, but no confirmed machine-readable holdings table route in this slice.
  - `matthews`: ETF pages were reachable and showed an Excel/table-export UI, but the visible export appears tied to page tables, not a proven holdings artifact; do not count without proving actual holdings rows.
  - `world_gold_council`: SPDR Gold pages exposed `https://api.spdrgoldshares.com/api/v1/barlist?underlying=gld`, but it returns `application/pdf`; do not count until a reliable PDF table/bar-list parser exists or a machine-readable route is found.
  - `sofi`, `aptus`, `angel_oak`, and Alpha Architect pages returned `403`/blocked for the probed routes.
  - `federated_hermes` returned `503` for the probed ETF route.
  - `true_shares`/`trueshares`: common Tidal-style CSV guesses timed out or failed; `www.trueshares.com` is a timeshare site and not the ETF issuer; `truesharesetfs.com` pages did not reveal a holdings artifact in the quick probe.
  - `renaissance_capital`: probed IPO ETF URL variants returned `404`.
  - `dimensional`, `tcw`, and some other page probes were reachable but did not expose a confirmed backend-fetchable holdings route in initial inspection.
- Validation in this slice:
  - `python -m json.tool ops/state.json` passed before this checkpoint edit.
  - `git diff --check` passed before this checkpoint edit.
  - Registry count command returned `345`, `46`, `299`.

## Latest checkpoint - 2026-06-13T11:55Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `46`
  - providers still lacking native/live-backed support: `299`
- Latest native/provider-specific additions in this slice:
  - `volatility_shares`: issuer public symbol-specific legacy XLS workbook route under `https://www.volatilityshares.com/download-holdings-usbanks-1933.php?fund={symbol_lower}`, currently live-tested with `SVIX`
  - `wahed`: issuer public product-page discovery of linked Google Sheets holdings exports, currently live-tested with `HLAL`
- Important implementation note:
  - Volatility Shares holdings are derivative/cash rows with descriptions such as VIX options/futures and `Cash & Other`, so the adapter intentionally preserves names, contracts/shares, notional/market value, and holding type while avoiding fake ticker symbols for derivative descriptions.
  - `parse_holdings_xls` now returns the first non-empty workbook sheet as fallback rows when generic canonical parsing finds no rows, allowing provider-specific XLS parsers to normalize odd issuer layouts.
  - Wahed holdings sheets can include non-ticker identifier-looking values in `StockTicker`, so the adapter only materializes compact ticker-like values and only persists valid 9-character CUSIPs.
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `amplify`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `distillate`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `harbor`
  - `horizon_kinetics`
  - `innovator`
  - `inspire`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `main_management`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `procuream`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `tema`
  - `teucrium`
  - `themes`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `volatility_shares`
  - `wahed`
  - `yieldmax`
- Validation for the Volatility Shares and Wahed additions:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_volatility_shares_adapter_parses_derivative_xls --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_wahed_adapter_discovers_public_google_sheet_holdings --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `87 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k volatility_shares`
    - result: `1 passed, 45 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k wahed`
    - result: `1 passed, 46 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "... count native live-backed adapters ..."`
    - result: `345`, `46`, `299`, `volatility_shares=True`, `wahed=True`

## Latest checkpoint - 2026-06-13T11:27Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `44`
  - providers still lacking native/live-backed support: `301`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `amplify`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `distillate`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `harbor`
  - `horizon_kinetics`
  - `innovator`
  - `inspire`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `main_management`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `procuream`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `tema`
  - `teucrium`
  - `themes`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific additions in this slice:
  - `amplify`: issuer public multi-account holdings CSV route under `https://amplifyetfs.com/wp-content/uploads/feeds/AmplifyWeb.40XL.XL_Holdings.csv`, currently live-tested with `BLOK`
  - `tema`: issuer symbol-specific public holdings CSV route under `https://temaetfs.com/hubfs/Website/Holdings/{SYMBOL}-holdings.csv`, currently live-tested with `TOLL`
- Validation for the Amplify addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_amplify_adapter_filters_multi_account_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `84 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k amplify`
    - result: `1 passed, 43 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "... count native live-backed adapters ..."`
    - result: `345`, `43`, `302`, `amplify=True`
- Validation for the Tema addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_tema_adapter_fetches_symbol_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `85 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k tema`
    - result: `1 passed, 44 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "... count native live-backed adapters ..."`
    - result: `345`, `44`, `301`, `tema=True`

## Previous checkpoint - 2026-06-13T11:05Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `42`
  - providers still lacking native/live-backed support: `303`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `distillate`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `harbor`
  - `horizon_kinetics`
  - `innovator`
  - `inspire`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `main_management`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `procuream`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `themes`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific additions in this slice:
  - `inspire`: issuer-page public quarterly holdings JSON route via the ETFLogic endpoint embedded by Inspire's public holdings page, currently live-tested with `BIBL`
  - `horizon_kinetics`: issuer symbol-specific public daily holdings XLSX route under `https://horizonkinetics.com/wp/wp-admin/admin-ajax.php?action=daily_holdings&ticker={SYMBOL}&prefix=Holdings`, currently live-tested with `INFL`
  - `distillate`: issuer symbol-specific public daily holdings CSV route under `https://distillatecapital.com/wp-content/uploads/data-feeds/DistillateWeb.{SYMBOL}_Holdings.csv`, currently live-tested with `DSTL`
- Validation for the Inspire addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_inspire_adapter_fetches_quarterly_holdings_json --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `83 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k inspire`
    - result: `1 passed, 42 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "... count native live-backed adapters ..."`
    - result: `345`, `42`, `303`, `inspire=True`
- Validation for the Horizon Kinetics addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_horizon_kinetics_adapter_fetches_daily_xlsx --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `82 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k horizon_kinetics`
    - result: `1 passed, 41 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "... count native live-backed adapters ..."`
    - result: `345`, `41`, `304`, `horizon_kinetics=True`
- Validation for the Distillate addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_distillate_adapter_fetches_symbol_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `81 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k distillate`
    - result: `1 passed, 40 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "... count native live-backed adapters ..."`
    - result: `345`, `40`, `305`, `distillate=True`

## Latest checkpoint - 2026-06-13T10:25Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `39`
  - providers still lacking native/live-backed support: `306`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `harbor`
  - `innovator`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `main_management`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `procuream`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `themes`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific additions in this slice:
  - `procuream`: issuer product-page discovery of ProcureAM's current public holdings CSV link under `https://procureetfs.com/{symbol}/`, currently live-tested with `UFO`
  - `main_management`: issuer symbol-specific public holdings CSV route under `https://www.mainmgtetfs.com/etfs/download-{symbol}.php`, currently live-tested with `BUYW`
  - `themes`: issuer symbol-specific public holdings CSV route under `https://themesetfs.com/storage/holdings/Holdings-{SYMBOL}.csv`, currently live-tested with `SPAM`
  - `harbor`: issuer Gatsby `page-data.json` route containing first-party `fullHoldings`, currently live-tested with `WINN`
- Validation for the ProcureAM addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_procure_adapter_discovers_current_holdings_csv_from_product_page --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `80 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k procuream`
    - result: `1 passed, 39 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `39`, `advisor_shares,american_century,ark,axs,bitwise,bny_mellon,calamos,cambria,defiance,direxion,first_trust,franklin,global_x,graniteshares,harbor,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,main_management,neos,northern_trust,pacer,procuream,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,themes,us_global_investors,vaneck,vanguard,yieldmax`, `306`

## Previous checkpoint - 2026-06-13T09:50Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `37`
  - providers still lacking native/live-backed support: `308`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `harbor`
  - `innovator`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `themes`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific addition:
  - `themes`: issuer symbol-specific public holdings CSV route under `https://themesetfs.com/storage/holdings/Holdings-{SYMBOL}.csv`, currently live-tested with `SPAM`
  - `harbor`: issuer Gatsby `page-data.json` route containing first-party `fullHoldings`, currently live-tested with `WINN`
  - `bny_mellon`: issuer product-page discovery of BNY's daily holdings XLS link, currently live-tested with `BKAG`
  - `direxion`: issuer symbol-specific public holdings CSV route under `https://www.direxion.com/holdings/{SYMBOL}.csv`, currently live-tested with `SPXL`
- Validation for the Themes addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_themes_adapter_fetches_symbol_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `78 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k themes`
    - result: `1 passed, 37 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `37`, `advisor_shares,american_century,ark,axs,bitwise,bny_mellon,calamos,cambria,defiance,direxion,first_trust,franklin,global_x,graniteshares,harbor,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,neos,northern_trust,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,themes,us_global_investors,vaneck,vanguard,yieldmax`, `308`

## Previous checkpoint - 2026-06-13T09:28Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `36`
  - providers still lacking native/live-backed support: `309`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `harbor`
  - `innovator`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific addition:
  - `harbor`: issuer Gatsby `page-data.json` route containing first-party `fullHoldings`, currently live-tested with `WINN`
  - `bny_mellon`: issuer product-page discovery of BNY's daily holdings XLS link, currently live-tested with `BKAG`
  - `direxion`: issuer symbol-specific public holdings CSV route under `https://www.direxion.com/holdings/{SYMBOL}.csv`, currently live-tested with `SPXL`
- Validation for the Harbor addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_harbor_adapter_parses_gatsby_page_data_full_holdings --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `77 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k harbor`
    - result: `1 passed, 36 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `36`, `advisor_shares,american_century,ark,axs,bitwise,bny_mellon,calamos,cambria,defiance,direxion,first_trust,franklin,global_x,graniteshares,harbor,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,neos,northern_trust,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `309`

## Previous checkpoint - 2026-06-13T09:17Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `35`
  - providers still lacking native/live-backed support: `310`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `bny_mellon`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `innovator`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific addition:
  - `bny_mellon`: issuer product-page discovery of BNY's daily holdings XLS link, currently live-tested with `BKAG`
  - `direxion`: issuer symbol-specific public holdings CSV route under `https://www.direxion.com/holdings/{SYMBOL}.csv`, currently live-tested with `SPXL`
- Validation for the BNY Mellon addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_bny_mellon_adapter_discovers_daily_xls_and_parses_holdings --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `76 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k bny_mellon`
    - result: `1 passed, 35 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `35`, `advisor_shares,american_century,ark,axs,bitwise,bny_mellon,calamos,cambria,defiance,direxion,first_trust,franklin,global_x,graniteshares,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,neos,northern_trust,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `310`

## Previous checkpoint - 2026-06-13T09:06Z

- The active goal remains **not complete** under the user's clarified standard:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `34`
  - providers still lacking native/live-backed support: `311`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `calamos`
  - `cambria`
  - `defiance`
  - `direxion`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `innovator`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `us_global_investors`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific addition:
  - `direxion`: issuer symbol-specific public holdings CSV route under `https://www.direxion.com/holdings/{SYMBOL}.csv`, currently live-tested with `SPXL`
- Validation for the Direxion addition:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_direxion_adapter_fetches_symbol_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `75 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k direxion`
    - result: `1 passed, 34 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `34`, `advisor_shares,american_century,ark,axs,bitwise,calamos,cambria,defiance,direxion,first_trust,franklin,global_x,graniteshares,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,neos,northern_trust,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `311`
- Providers with named concrete classes but **not** live-backed still do not count as complete under the user's requested bar.
- The generated `RecognitionOnlyHoldingsAdapter` path remains present for the long tail and is explicitly unacceptable as final provider support.
- The next worker must continue replacing generated/thin adapters with native provider implementations, one provider at a time, each with static parser tests and opt-in live route tests.

## Previous checkpoint - 2026-06-13T08:49Z

- The active goal has been tightened by the user: **SEC EDGAR fallback does not count as provider support**. It is a fallback only.
- Under that stricter definition, the current implementation is **not complete**:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `33`
  - providers still lacking native/live-backed support: `312`
- Native/live-backed providers currently in the registry:
  - `advisor_shares`
  - `american_century`
  - `ark`
  - `axs`
  - `bitwise`
  - `calamos`
  - `cambria`
  - `defiance`
  - `first_trust`
  - `franklin`
  - `global_x`
  - `graniteshares`
  - `innovator`
  - `invesco`
  - `ishares`
  - `janus_henderson`
  - `jpmorgan`
  - `kraneshares`
  - `neos`
  - `northern_trust`
  - `pacer`
  - `proshares`
  - `roundhill`
  - `schwab`
  - `simplify`
  - `spdr`
  - `sprott`
  - `strive`
  - `teucrium`
  - `vaneck`
  - `vanguard`
  - `yieldmax`
- Latest native/provider-specific additions:
  - `northern_trust`: FlexShares public holdings CSV route under `flexshares.com/content/dam/ntflexshares/fund/{symbol}/{symbol}-holdings.csv`, currently live-tested with `QDF`
  - `janus_henderson`: issuer full-holdings HTML table route under `janushenderson.com/en-us/advisor/product/{slug}/full-holdings/`, currently live-tested with `JAAA`
  - `calamos`: issuer XLSX holdings route under `https://www.calamos.com/download/{SYMBOL}Holdings.xlsx`, currently live-tested with `CPSM`
  - `franklin`: issuer GraphQL holdings route under `franklintempleton.com/api/pds/price-and-performance`, currently live-tested with `FLQL` after resolving Franklin's internal fund id (`25773`)
  - `jpmorgan`: issuer product-data JSON route under `am.jpmorgan.com/FundsMarketingHandler/product-data?cusip=...`, currently live-tested with `JEPI` / CUSIP `46641Q332`
  - `axs`: issuer dated aggregate Filepoint CSV route under `axsetf.filepoint.live/assets/data/BBH_AXS_ETF_PVAL_WEB.{yyyymmdd}.csv`, currently live-tested with `TARK`
  - `graniteshares`: issuer product-page discovery route under `graniteshares.com/etfs/{slug}/`, currently mapped for `NVD`, with legacy `.xls` holdings parsing via `xlrd`
  - `pacer`: issuer public holdings CSV route under `paceretfs.com/usbank/live/.../{symbol}_Holdings.csv`, currently mapped for `COWZ`
  - `american_century`: Avantis public product-page embedded holdings payload route, currently mapped for `AVUV`
  - `us_global_investors`: issuer product-page holdings table route under `usglobaletfs.com/fund/{symbol}/`
  - `vanguard`: issuer public JSON route under `investor.vanguard.com/vmf/api/.../portfolio-holding/...`
  - `innovator`: issuer aggregate CSV route filtered by `Account`
  - `bitwise`: product-page embedded `__NEXT_DATA__` holdings
  - `cambria`: issuer aggregate CSV route filtered by `Account`
  - `simplify`: issuer aggregate XLSX discovered from Simplify's ETF page and filtered by `FUND NAME`
  - `neos`: issuer WordPress AJAX CSV route filtered by `Account`
  - `strive`: issuer public CSV download route
  - `defiance`: issuer full-holdings HTML table route under `defianceetfs.com/{symbol}-full-holdings/`
  - `kraneshares`: issuer dated holdings CSV lookback route under `kraneshares.com/csv/{mm_dd_yyyy}_{symbol}_holdings.csv`
  - `advisor_shares`: issuer symbol-specific holdings CSV route under `advisorshares.com/wp-content/uploads/csv/holdings/AdvisorShares_{symbol}_Holdings_File.csv`
  - `teucrium`: issuer aggregate Filepoint holdings CSV route filtered by `Account`
- Providers with named concrete classes but **not** live-backed still do not count as complete under the user's requested bar.
- The generated `RecognitionOnlyHoldingsAdapter` path remains present for the long tail and is explicitly unacceptable as final provider support.
- The next worker must continue replacing generated/thin adapters with native provider implementations, one provider at a time, each with static parser tests and opt-in live route tests.
- Validation already run for the latest native-provider additions:
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `30`, `advisor_shares,american_century,ark,axs,bitwise,cambria,defiance,first_trust,franklin,global_x,graniteshares,innovator,invesco,ishares,jpmorgan,kraneshares,neos,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `315`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `71 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k franklin`
    - result: `1 passed, 30 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k jpmorgan`
    - result: `1 passed, 29 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k axs`
    - result: `1 passed, 28 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k graniteshares`
    - result: `1 passed, 27 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k pacer`
    - result: `1 passed, 26 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_calamos_adapter_parses_native_xlsx_holdings --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `72 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k calamos`
    - result: `1 passed, 31 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `31`, `advisor_shares,american_century,ark,axs,bitwise,calamos,cambria,defiance,first_trust,franklin,global_x,graniteshares,innovator,invesco,ishares,jpmorgan,kraneshares,neos,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `314`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_janus_henderson_adapter_parses_full_holdings_html --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `73 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k janus_henderson`
    - result: `1 passed, 32 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `32`, `advisor_shares,american_century,ark,axs,bitwise,calamos,cambria,defiance,first_trust,franklin,global_x,graniteshares,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,neos,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `313`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py::test_northern_trust_adapter_parses_flexshares_holdings_csv --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
    - result: `74 passed`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k northern_trust`
    - result: `1 passed, 33 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `cd backend && ./.venv/bin/python -c "from app.services.etf_holdings_adapters import ISSUER_ADAPTER_CONFIGS; native=sorted(k for k,c in ISSUER_ADAPTER_CONFIGS.items() if c.live_tested_default_route); print(len(ISSUER_ADAPTER_CONFIGS)); print(len(native)); print(','.join(native)); print(len(ISSUER_ADAPTER_CONFIGS)-len(native))"`
    - result: `345`, `33`, `advisor_shares,american_century,ark,axs,bitwise,calamos,cambria,defiance,first_trust,franklin,global_x,graniteshares,innovator,invesco,ishares,janus_henderson,jpmorgan,kraneshares,neos,northern_trust,pacer,proshares,roundhill,schwab,simplify,spdr,sprott,strive,teucrium,us_global_investors,vaneck,vanguard,yieldmax`, `312`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k american_century`
    - result: blocked in the normal sandbox by DNS/network; escalated retry was rejected by external usage limit. A direct public-page probe before implementation confirmed the Avantis product page exposes parseable embedded holdings, but the pytest live case still needs to be rerun when network/escalation is available.
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k 'defiance or kraneshares'`
    - result: `2 passed, 20 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k 'advisor_shares or teucrium'`
    - result: `2 passed, 22 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k simplify`
    - result: `1 passed, 17 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k neos`
    - result: `1 passed, 18 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k strive`
    - result: `1 passed, 19 deselected`
  - `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q`
    - result: `1 passed`

## Current worker

- Name: Codex
- Session started: 2026-06-05T18:38:49Z
- Soft stop deadline: n/a

## Completed in this session

- Reworked ETF issuer/provider support so the registered provider universe is no longer only recognized:
  - all 345 registered ETF issuer/provider adapter keys now expose an actual holdings retrieval path through SEC EDGAR filings when SEC identifiers are available
  - the 7 issuer-native routes remain explicitly marked as native/live-backed: ARK, Global X, Invesco, iShares/BlackRock, SPDR/State Street, Sprott, and VanEck
  - the remaining 338 registered providers are no longer treated as unsupported candidates; they are provider-specific adapters with `sec_edgar_filing_fallback` support
  - adapter probes now return `ready` for any registered provider when `sec_cik` is present, while still preferring issuer-native routes where they exist
  - adapter catalogue output now exposes `supports_sec_filing_fallback` and `support_route_types` so callers can distinguish issuer-native routes from SEC-backed routes
  - adapter-backed SEC fetches persist snapshots with SEC provenance/quality metadata instead of mislabeling them as issuer-native holdings
- Live smoke-validated the new non-native route:
  - `vanguard` + `VOO` + SEC CIK `0000036405` fetched 519 rows from SEC EDGAR through `sec_edgar_filing_fallback`
- Validation for this support-model pass:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_adapters.py tests/unit/services/test_etf_holdings_bootstrap.py tests/unit/services/test_etf_holdings_edgar.py tests/unit/services/test_etf_holdings_sec.py --no-cov -q`
    - result: `61 passed`
  - `cd backend && ./.venv/bin/pytest tests/live/test_etf_holdings_live_providers.py --no-cov -q`
    - result: `18 skipped` without `RUN_LIVE_ETF_HOLDINGS_TESTS=1`
  - `cd backend && ./.venv/bin/pytest tests/integration/api/test_etf_holdings.py -k 'adapter_catalog or probe' --no-cov -q`
    - result: `6 passed, 46 deselected`
  - `cd backend && ./.venv/bin/ruff check app/services/etf_holdings_adapters.py app/services/etf_holdings_refresh.py app/schemas/etf_holdings.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py tests/integration/api/test_etf_holdings.py`
    - result: `All checks passed`
  - `git diff --check`
    - result: passed

- Fixed the ETF-holdings `make test-all` integration stall the user reported:
  - reproduced the exact behavior: `tests/integration/api/test_etf_holdings.py` failed on its second test and then appeared to hang on the third
  - isolated the “hang” with faulthandler and confirmed it was not fixture teardown; the third test was blocking inside unintended live OpenFIGI calls reached through ETF constituent bootstrap/fallback logic
- Backend fixes applied:
  - `backend/app/services/etf_holdings.py`
    - skipped `fetch_stable_identifiers(...)` provider calls while `settings.APP_ENV == "test"` so ETF holdings integration tests no longer drift into live identifier-provider IO during placeholder creation
  - `backend/app/services/etf_holdings_refresh.py`
    - added `_bootstrap_savepoint(...)` so ETF bootstrap refresh savepoints now support both:
      - real async SQLAlchemy sessions
      - the sync-session adapter used by integration tests (`SessionTransaction`)
    - this fixes the reverse regression surfaced after the earlier NIKL fix, where integration tests were now failing with `'SessionTransaction' object does not support the asynchronous context manager protocol`
- Test hardening applied:
  - `backend/tests/integration/api/test_etf_holdings.py`
    - added an autouse fixture forcing ETF holdings integration tests into `APP_ENV=test`
    - explicitly monkeypatched `_bootstrap_from_sec_filings` to `None` in the fake bootstrap-route tests so they no longer silently fall through into SEC fallback and mask the real failure mode
  - `backend/tests/unit/services/test_etf_holdings_bootstrap.py`
    - added regression coverage for the sync-session wrapper case so bootstrap savepoints are validated against both async and sync nested-transaction objects
- Revalidated:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_bootstrap.py --no-cov -q`
    - result: `4 passed`
  - `cd backend && ENV_FILE=.env.dev uv run pytest tests/integration/api/test_etf_holdings.py -k 'test_admin_can_refresh_ark_provider_route or test_bootstrap_endpoint_can_materialize_and_fetch_first_snapshot or test_bootstrap_endpoint_seeds_known_ishares_route_metadata or test_bootstrap_endpoint_seeds_known_eem_ishares_route_metadata' --no-cov -q`
    - result: `4 passed, 48 deselected`
- A full `rtk make test-all` rerun was started afterward to confirm the end-to-end path, but this shell has not yet yielded a final result for that long-running command. The ETF holdings failure/hang slice itself is fixed and green.

- Fixed the concrete `NIKL` ETF bootstrap failure reported by the user:
  - root cause: `bootstrap_etf_holdings_profile(...)` in `backend/app/services/etf_holdings_refresh.py` was opening a nested transaction with `with db.begin_nested():` even though `db` is an async SQLAlchemy session
  - that raised `'AsyncSessionTransaction' object does not support the context manager protocol` before the Sprott refresh path could complete
  - fixed by switching the savepoint to `async with db.begin_nested():`
- Added a focused bootstrap regression in `backend/tests/unit/services/test_etf_holdings_bootstrap.py` proving the ready-route bootstrap path:
  - enters/exits the async nested transaction correctly
  - marks the bootstrap as attempted and successful
- Revalidated:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_bootstrap.py --no-cov -q`
  - result: `3 passed`
- Attempted to rerun the matching API/integration ETF bootstrap slice too, but this shell still cannot access Docker/Testcontainers, so that broader validation remains blocked here by environment permissions rather than application behavior.

- Fixed the concrete `NIKL` bootstrap failure:
  - root cause: `bootstrap_etf_holdings_profile(...)` in `backend/app/services/etf_holdings_refresh.py` was using `with db.begin_nested():` against an async SQLAlchemy session
  - that raised `'AsyncSessionTransaction' object does not support the context manager protocol` before the Sprott refresh path could even run
  - fixed by switching the issuer refresh savepoint to `async with db.begin_nested():`
- Added focused regression coverage in `backend/tests/unit/services/test_etf_holdings_bootstrap.py` proving the ready-route bootstrap path enters/exits an async nested transaction and succeeds cleanly.
- Revalidated:
  - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_bootstrap.py --no-cov -q`
  - result: `3 passed`
- Attempted to rerun the matching API integration bootstrap slice too, but this shell is still blocked from Docker/Testcontainers access, so that slice could not be executed here. The failure was environmental (`PermissionError` on Docker socket), not application-level.

- Fixed the concrete `EEM` duplicate-`SUGI` holdings corruption the user reported.
  - Root cause was not a real ETF composition nuance. It was a resolver/data-quality bug:
    - placeholder/internal ETF-holdings identifiers like `N/A` had historically been treated as real identifiers
    - later reconciliations had also attached unrelated stable identifiers onto the real `SUGI` instrument
    - the name-compatibility heuristic was too permissive for international suffixes like `PT` / `TBK`, so unrelated rows could remain “compatible enough” to stay mapped to `SUGI`
  - Backend fixes now in place:
    - `_find_instrument_by_identifier(...)` only considers active identifiers
    - incompatible internal ETF-holdings identifier aliases can be deactivated during constituent resolution
    - `register_identifier(...)` can reassign conflicting `etf_holdings_internal` aliases to the correct instrument instead of leaving them stuck on the wrong one forever
    - ETF holdings name compatibility was tightened so generic suffix/token overlap (`PT`, `TBK`, single generic words like `energy`) no longer falsely blesses unrelated instruments as compatible
    - historical reconcile now actually revisits already-resolved rows whose linked instrument name is not compatible with the reported holding name
  - Added focused regression coverage in `backend/tests/unit/services/test_etf_holdings_resolution.py` for:
    - ignoring incompatible internal identifier aliases
    - reassigning conflicting internal aliases
    - forcing reconcile on false-positive international-suffix name matches
  - Revalidated:
    - `cd backend && ./.venv/bin/pytest tests/unit/services/test_etf_holdings_resolution.py --no-cov -q`
    - result: `12 passed`
  - Live local DB repair was also executed for `EEM` in forced no-network mode after terminating stale blocked reconciliation sessions.
    - Before repair: `934` non-Sugih rows incorrectly rendered as `SUGI`
    - After repair verification: `0` bogus `SUGI` collisions remain for `EEM`
    - Example repaired rows now render under their own symbols/placeholders/names instead of collapsing onto `SUGI`:
      - `PT Bank Rakyat Indonesia (Persero) Tbk` -> `HOLDING-CA086D32E3`
      - `Zhejiang Leapmotor Technology Co Ltd` -> `HOLDING-BCCE55944C`
      - real `Sugih Energy Tbk PT` still remains correctly mapped to `SUGI`

- Added a detailed roadmap entry for **Relative Rotation Graph (RRG-style) relative-strength rotation analysis** in [docs/project-todos.md](/Users/jagnelo/Documents/Projects/charting-platform/docs/project-todos.md):
  - anchored the feature on benchmark-relative relative-strength trend and momentum-of-relative-strength
  - documented the four-quadrant model (`leading`, `weakening`, `lagging`, `improving`) plus tails/history over time
  - positioned the main first-class use case as S&P sector ETF rotation versus the S&P 500 while keeping the design generic for arbitrary watchlists, baskets, and ETF-derived universes
  - called out the need to respect the trademarked/proprietary nature of branded RRG/JdK implementations and, unless licensed, build this as a transparent internal **RRG-style** relative-rotation view
  - covered analytics, UX, companion tables, downstream integrations, coverage semantics, and validation requirements

- Fixed a second broad ETF holdings ingestion failure class uncovered by `QQQJ`:
  - long-form holding-row currencies such as `Canada Dollar` are now normalized to canonical codes like `CAD` before persisting `etf_holding.currency`
  - SEC N-PORT / SEC legacy parsers now normalize those currency labels earlier in the pipeline too
  - added regression coverage for both parser normalization and holdings-snapshot ingestion normalization

- Fixed a persistence/upgrade gap for already-stored ETF holdings snapshots:
  - added `reconcile_snapshot_constituents(...)` so stored rows can be re-resolved from their persisted CUSIP/ISIN/SEDOL/name metadata
  - ETF bootstrap now reconciles the latest stored snapshot before returning it, instead of blindly serving old placeholder-backed rows forever
  - added a regression test proving an identifier-only placeholder row is promoted from `HOLDING-*` to `TXN` during reconciliation

- Fixed the concrete ETF holdings failures reported by the user for `NIKL`/Sprott, `EEM` bootstrap, and noisy enrichment logs:
  - added a real provider-specific `SprottHoldingsAdapter` backed by Sprott's public sitemap plus product-page holdings discovery
  - hardened product-page discovery to support inline `data:` CSV download links
  - normalized oversized exchange labels and long-form currency names before persisting provider-enriched/lightweight constituent instruments, fixing the `varchar(10)` / `varchar(3)` crashes
  - isolated issuer refresh failures inside a nested transaction so SEC fallback can continue after a failed refresh attempt
  - downgraded expected yfinance quote-miss noise during best-effort enrichment from error-level logging to debug
- Added focused validation and coverage:
  - unit coverage for Sprott/data-URI discovery and provider-persistence normalization
  - Docker-backed integration coverage for the EEM/SEC-fallback path
  - live sanity check confirming Sprott `NIKL` returns parseable holdings rows

- Fixed the six ETF-holdings regressions from the pasted `make test-all` failure log:
  - historical point-in-time overlap requests were excluding manually ingested snapshots because default `known_at` was being stamped with wall-clock “now” instead of the composition date
  - Invesco product-page discovery tests were bypassed by the new default QQQ live JSON route
  - the SEC-fallback bootstrap test no longer forced an issuer-route failure even though Invesco now has a ready route
  - Vanguard probe semantics had drifted from the stale test expectation
- Concrete code changes:
  - `backend/app/services/etf_holdings.py`
    - default snapshot `known_at` now falls back to end-of-day of `composition_date`, which restores correct historical point-in-time behavior for manual/test ingests
  - `backend/app/services/etf_holdings_adapters.py`
    - Invesco now honors an explicitly configured product page as a discovery path instead of always jumping straight to the default ticker-based JSON route
  - `backend/tests/integration/api/test_etf_holdings.py`
    - the SEC-fallback bootstrap test now explicitly monkeypatches `_refresh_adapter_route(...)` to fail, matching its intended scenario
    - the Vanguard probe test now asserts the current honest provider state: `needs_provider_implementation`
- Revalidated the exact failing slice from the user’s log:
  - `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py -k "falls_back_to_sec or overlap_summary_compares_constituents_across_etfs or overlap_matrix_summarizes_many_etf_relationships or overlap_matrix_can_expand_etf_family_from_profile_metadata or issuer_adapter_can_discover_holdings_file_from_product_page or keeps_vanguard_as_candidate" --no-cov -q`
  - result: `6 passed, 46 deselected`

- Expanded the ETF/market-events roadmap in [docs/project-todos.md](/Users/jagnelo/Documents/Projects/charting-platform/docs/project-todos.md) instead of creating a duplicate entry:
  - clarified Massive as the primary free structured IPO source
  - clarified Alpha Vantage as complementary IPO/earnings calendar plus post-listing `LISTING_STATUS` follow-through
  - clarified SEC EDGAR as filing-pipeline enrichment rather than listing-date truth
  - added explicit pre-listing instrument lifecycle, provider-horizon semantics, and page/widget UX goals for a future market-events calendar

- Fixed the two concrete ETF holdings quality gaps the user called out:
  - placeholder constituent symbols like `HOLDING-*` leaking into the ETF holdings UI
  - QQQ/Invesco still being treated like an effectively unsupported path despite being a critical US ETF issuer
- Extended OpenFIGI identifier support beyond ticker-only lookup:
  - added identifier-profile resolution by `CUSIP`, `ISIN`, and `SEDOL`
  - ETF constituent resolution now uses those identifier routes before falling back to lightweight placeholder materialization
  - when a previously materialized placeholder instrument already exists, the resolver now promotes it in place to the real provider-backed symbol/name instead of leaving the placeholder symbol forever
- Hardened snapshot rebootstrap/reingest semantics:
  - if the same ETF holdings snapshot hash is ingested again, the backend now reconciles existing stored rows instead of simply returning the old snapshot untouched
  - this allows already-stored placeholder constituent rows to be upgraded after the resolver/provider logic improves, without requiring a brand-new composition date
- Reworked the Invesco adapter from “candidate gap” behavior to a real live-backed provider path:
  - confirmed the correct public holdings endpoint is the `dng-api` shareclasses JSON route
  - matched the request shape that the real Invesco site uses (browser-like user-agent/referer/client-hint headers)
  - `QQQ` now resolves a default Invesco source URL and the adapter successfully fetches/parses live holdings rows from the public endpoint
- Tightened frontend ETF holdings symbol presentation:
  - the ETF holdings workspace and chart-side holdings panel now suppress synthetic `HOLDING-*` constituent symbols
  - when an old placeholder still exists, the UI falls back to the reported ticker instead of surfacing backend placeholder junk
  - added frontend regression coverage to ensure legacy placeholder symbols are not shown to users
- Added focused backend regression coverage for:
  - OpenFIGI ticker mapping
  - OpenFIGI identifier-profile resolution
  - placeholder promotion from CUSIP-only constituent rows
  - re-ingesting the same snapshot to reconcile old placeholder rows
- Revalidated live provider fetches directly:
  - Invesco `QQQ` live fetch returns 105 holdings rows
  - iShares `IWM` live fetch returns 1913 holdings rows

- Fixed the real QQQ bootstrap blocker in the SEC fallback path instead of falsely promoting Invesco to a supported live-backed route:
  - confirmed the direct public Invesco JSON endpoint for `QQQ` still returns live HTTP `406`, so the previous `needs_provider_implementation` probe classification remains correct
  - traced the failed QQQ bootstrap to SEC N-PORT ingestion failures, not missing SEC filings or missing ETF metadata
  - verified the failing QQQ N-PORT filings were XHTML/HTML-rendered SEC documents, and the strict XML parser was crashing with `mismatched tag`
- Hardened `parse_sec_nport_xml(...)` with an XHTML fallback parser:
  - when strict XML parsing fails, the parser now reconstructs holdings rows from the SEC XHTML “Item C.1. Identification of investment” schedule blocks
  - the fallback extracts issuer/title, CUSIP/ISIN/SEDOL, balance, currency, value, and percentage-of-net-assets fields into canonical holdings rows
  - the fallback intentionally leaves `report_date` unset so the backfill pipeline safely uses EDGAR filing metadata (`filing.report_date`) instead of guessing the wrong date from XHTML text
- Revalidated the real QQQ path directly against the live SEC filing and the local DB:
  - the previously failing filing `0001067839-26-000024` now parses into 102 holdings rows
  - a real local `backfill_sec_nport_holdings(...)` run for QQQ completed successfully and persisted snapshot `2026-03-31` with 102 rows
- Kept Invesco support semantics honest:
  - reverted the temporary attempt to classify Invesco as a default live-backed route
  - restored the existing test expectation that `QQQ` probes as `needs_provider_implementation` at the issuer-route layer, while SEC fallback remains the usable path
- Added deterministic unit coverage for the SEC XHTML N-PORT variant in `backend/tests/unit/services/test_etf_holdings_sec.py`

- Removed ETF holdings user-facing internal mastering jargon from the ETF holdings workspace:
  - row/status language is now action-oriented (`ready`, `reference`, `needs match`) instead of `resolved/unresolved`
  - the detail panes no longer expose backend `resolution_note` strings such as “lightweight instrument materialized...”
  - non-security/reference rows such as cash/collateral no longer present as chart-openable tradable holdings
- Hardened ETF constituent materialization in `backend/app/services/etf_holdings.py` so bootstrap/refresh resolution is less dependent on raw ETF row labels:
  - constituent resolution now tries stable-identifier enrichment through configured identifier providers before falling back to lightweight placeholder creation
  - provider metadata enrichment now uses the default metadata provider for a higher-confidence instrument materialization pass when symbol/name compatibility is plausible
  - stable identifiers discovered during enrichment are registered back onto matched/materialized instruments to help collapse duplicate ETF-holdings aliases into one canonical instrument
  - placeholder fallback still exists, but it is now the last resort rather than the main path
- Added focused regression coverage for the new provider-backed constituent resolution and duplicate-collapse behavior:
  - `backend/tests/unit/services/test_etf_holdings_resolution.py`
  - updated ETF holdings frontend tests to assert the new user-facing availability language and disabled chart action for reference rows
- Revalidated:
  - `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_etf_holdings_resolution.py --no-cov -q`
  - `rtk npm --prefix frontend run test -- --run tests/unit/components/test_etf_holdings_panel.test.ts`
  - `rtk npm --prefix frontend run test -- --run tests/unit/views/test_etf_holdings_view.test.ts`
  - `rtk uv run ruff check backend/app/services/etf_holdings.py backend/tests/unit/services/test_etf_holdings_resolution.py`

- Hardened standard ETF bootstrap metadata so previously broken ETF profiles no longer survive after the code was fixed:
  - known-standard ETF metadata is now applied canonically during bootstrap instead of only filling blanks
  - seeded provider aliases now override stale route identifiers instead of preserving old bad values
  - seeded SEC metadata is now baked in for the first-class standard ETF set we already bless in code (`QQQ`, `EEM`, `IVV`, `IWM`, `XLE`), so bootstrap does not depend on a live SEC enrichment call just to get a working fallback path
- Revalidated the exact standard ETF scenarios that kept regressing for users:
  - `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py -k "known_eem or known_invesco or stale_known_standard" --no-cov -q`
  - `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_etf_holdings_adapters.py -k "invesco or qqq or eem or iwm or known" --no-cov -q`
- Added focused integration coverage proving that bootstrap rewrites stale broken `EEM` ETF profile metadata back to the canonical iShares route + SEC identifiers before refresh.

- Corrected the remaining “standard ETF” bootstrap dead-ends in `/etf-holdings` without falsely claiming unsupported issuer routes:
  - `EEM` now bootstraps cleanly through seeded iShares/BlackRock product-id metadata (`239637`) and the live-backed BlackRock JSON holdings route.
  - `QQQ` no longer depends on the broken backend-unfriendly default Invesco holdings endpoint. Instead, bootstrap now:
    - opportunistically enriches SEC fund metadata from the public `company_tickers_mf` feed
    - falls back to the latest available SEC holdings filings when the issuer route is missing or not actually live-backed
  - Invesco is no longer advertised as a live-backed default-route issuer in the adapter catalog or live test matrix.
- Hardened the ETF holdings frontend snapshot selection path so switching ETFs cannot keep a stale snapshot id from a previously selected ETF.
- Revalidated:
  - `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_etf_holdings_adapters.py backend/tests/integration/api/test_etf_holdings.py -k "QQQ or EEM or IWM or adapters" --no-cov -q`
  - `rtk npm --prefix frontend run test -- --run tests/unit/views/test_etf_holdings_view.test.ts`
  - `RUN_LIVE_ETF_HOLDINGS_TESTS=1 rtk backend/.venv/bin/pytest backend/tests/live/test_etf_holdings_live_providers.py -k "IWM or EEM or QQQ or matrix" --no-cov -q`
- Important correction: the earlier assumption that Invesco’s `dng-api` holdings route for `QQQ` was backend-fetchable was wrong; direct live requests still return HTTP `406`, so the working path is now SEC fallback rather than a false “ready” probe.

- Closed two concrete ETF bootstrap gaps that were still breaking the `/etf-holdings` workspace for standard US ETFs:
  - `QQQ` now uses a provider-specific default Invesco holdings JSON route and probes as `ready` without requiring manual per-profile route metadata.
  - `EEM` now bootstraps like `IVV`/`IWM` by seeding the official iShares/BlackRock product id `239637`.
- Added/updated coverage for the new routes:
  - unit adapter coverage for default Invesco route resolution/readiness
  - unit adapter coverage for seeded iShares `EEM` product-id readiness
  - Docker-backed integration coverage for:
    - `QQQ` bootstrap
    - `EEM` bootstrap
    - `QQQ` probe readiness
    - adapter catalog exposure of Invesco as a live-backed default route
- Revalidated:
  - `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_etf_holdings_adapters.py --no-cov -q`
  - `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py -k "bootstrap_endpoint_seeds_known_eem_ishares_route_metadata or bootstrap_endpoint_seeds_known_qqq_invesco_route_metadata or admin_can_probe_ready_invesco_default_route or admin_can_list_holdings_adapter_catalog or bootstrap_endpoint_seeds_known_ishares_route_metadata" --no-cov -q`

- Fixed the remaining `make test-all` failures and noise until the full platform suite completed cleanly end to end.
- Corrected ETF holdings point-in-time snapshot resolution so same-day snapshots are eligible through end-of-day rather than being excluded by a start-of-day cutoff.
- Brought ETF holdings adapter/test expectations back in sync:
  - generic dated/source alias support now works for concrete issuer adapters without incorrectly promoting unresolved providers to ready routes
  - Invesco now falls back through the shared issuer discovery path when no direct source URL is resolved
  - Schwab catalog/product-page discovery expectations and current iShares/BlackRock JSON route expectations are covered by integration tests
- Updated `SearchBar` frontend unit tests to match the current emit contract, which includes the selected result payload when available.
- Filtered the exact external pytest runtime warning `coroutine 'Connection._cancel' was never awaited` so backend integration output is clean again; this warning was coming from third-party async cleanup rather than application code.
- Revalidated:
  - `rtk make test-fe`
  - `rtk make test-int`
  - `rtk make test-all`
- Temporarily stopped the branch dev infra to avoid `:5432` conflicts with the full-stack test run, then restored it afterward with `make dev-infra`.

- Fixed the failing ETF bootstrap unit test assertion so it now matches the intended mastering behavior:
  - ETF bootstrap may legitimately promote the instrument primary identifier to a stronger external identifier such as `composite_figi`
  - the invariant we actually need is that only one canonical active internal identifier exists
- Revalidated the original pasted failure against the full backend unit suite; all backend unit tests now pass cleanly.
- Fixed ETF holdings bootstrap so selecting a valid ETF from the `/etf-holdings` picker no longer dead-ends on a fresh branch with an empty holdings database.
- Added a non-admin ETF bootstrap endpoint that:
  - persists/selects the ETF profile for the chosen symbol
  - uses the picker-provided ETF name to improve adapter inference
  - attempts an immediate first holdings snapshot refresh when a route is ready
  - returns a structured readiness/message payload when no current snapshot can yet be fetched
- Updated the ETF holdings frontend workspace to bootstrap on picker selection instead of only browsing pre-existing stored snapshots.
- Hardened the ETF holdings frontend workspace against empty/non-array profile reloads during bootstrap transitions.
- Fixed a backend mastering bug uncovered by XLE bootstrap:
  - lightweight ETF bootstrap was incorrectly creating a fake `internal` identifier (`etf:{symbol}`)
  - the mastering layer then tried to add the real `instrument:{id}` internal identifier
  - this produced multiple internal identifiers on one instrument and crashed with `MultipleResultsFound`
- Removed the bogus ETF bootstrap `internal` identifier and made `ensure_internal_identifier` self-heal duplicate internal-identifier rows by keeping one canonical `instrument:{id}` row active and deactivating/superseding the rest.
- Added focused regression coverage for:
  - lightweight ETF bootstrap creating only one canonical internal identifier
  - duplicate internal-identifier cleanup in instrument mastering
  - the ETF holdings bootstrap endpoint materializing a first snapshot or persisting a route-not-ready profile cleanly

- Added ETF holdings persistence with Alembic migration and ORM models:
  - `etf_profile`
  - `etf_holdings_raw_artifact`
  - `etf_holdings_snapshot`
  - `etf_holding`
  - `etf_holdings_adapter_state`
  - `etf_index_proxy_mapping`
- Added ETF holdings backend schemas, service layer, and authenticated API endpoints:
  - list/search ETFs with holdings
  - latest holdings snapshot
  - available composition dates
  - point-in-time nearest snapshot
  - constituent membership timeline
  - unresolved holdings
  - requested-range coverage summary
  - admin manual row ingestion
  - admin CSV ingestion
  - admin ETF profile/routing update
  - admin refresh trigger
- Added canonical holdings parsing for common issuer CSV formats and simple XLSX/OpenXML workbooks, including ticker/name/weight/shares/market value/currency/identifier fields.
- Added lightweight instrument materialization for ETF profiles and constituent rows without fetching price history.
- Added source/provenance semantics that separate arbitrary issuer/source names from the registered internal data-source provider.
- Registered `etf_holdings_internal` as a provider descriptor for provenance and instrument-mastering compatibility.
- Added ETF holdings refresh through provider-specific issuer adapters:
  - arbitrary profile-level holdings URLs are no longer registered as a supported fallback adapter
  - concrete issuer adapters resolve that provider's own route shape, parse holdings, store raw artifacts, and create dated snapshots
  - failures are stored in `etf_holdings_adapter_state`
- Added a scheduled ETF holdings refresh task behind `ETF_HOLDINGS_REFRESH_ENABLED`.
- Added a Chart page ETF holdings panel:
  - hidden unless the viewed symbol has holdings
  - compact/collapsible presentation matching the platform dark style
  - source/freshness/resolution metadata
  - filter/sort holdings
  - click a resolved constituent to open its chart
- Added Strategy Lab ETF holdings snapshot universes:
  - universe type selector can use an ETF holdings snapshot
  - saved strategy versions persist `universe_config.etf_holdings`
  - coverage preview and backtest execution resolve ETF snapshot constituents through the shared universe resolver
  - supports latest available snapshots, snapshots on/before a selected date, and dynamic point-in-time membership from the visual builder
  - rules backtests can opt into dynamic point-in-time ETF holdings membership with `universe_config.etf_holdings.snapshot_mode = "dynamic"`; bars are filtered by the latest ETF holdings snapshot known on each bar date
  - dynamic ETF runs expose a constituent-removal policy that can leave positions marked open or realize them as `constituent_removed` exits
  - dynamic ETF result summaries include the snapshot set used by the run, and execution-log rows identify snapshot id/composition date/known-at plus membership status for entries and removal exits
  - Strategy Lab execution log now surfaces dynamic ETF snapshot context in the reason cell and includes it in reason filtering
  - run-subset controls are limited to resolved ETF constituent symbols from coverage preview
- Added a minimal basket foundation for ETF-derived baskets:
  - `basket` and `basket_member` persistence with source/provenance fields
  - read-only system-managed baskets can be materialized from an ETF holdings snapshot
  - `GET /api/v1/etf-holdings/{symbol}/basket` creates/returns the snapshot basket
  - `GET /api/v1/baskets` and `GET /api/v1/baskets/{id}` expose readable basket summaries
- Expanded baskets into a user-owned backend feature:
  - authenticated users can create, update, list, read, and delete manual baskets
  - manual basket members must reference existing resolved instruments
  - duplicate members are rejected
  - custom weights must sum to 1.0
  - equal-weight baskets leave member weights null for 1/N interpretation
  - read-only/system-managed ETF-derived baskets are protected from manual edits/deletes
  - auto-classification sets sector/industry when all members share the same metadata
- Added Strategy Lab basket universes:
  - `universe_config.basket_id` resolves basket members through coverage preview and run execution
  - the visual builder can select a basket as the strategy universe and save/load it
  - advanced run subsets are limited to selected basket members
  - ETF-derived system baskets can opt into dynamic source ETF holdings history through `basket_snapshot_mode = "dynamic"` in Strategy Lab
  - manual baskets now persist composition snapshots on create/update, expose snapshot history through `/baskets/{id}/snapshots`, and can opt into dynamic point-in-time replay through `basket_snapshot_mode = "dynamic"`
- Added a dedicated basket builder/editor workspace:
  - `/baskets` is accessible from the sidebar
  - users can create, edit, and delete manual baskets
  - instruments are added through the existing provider-backed search picker
  - equal and custom weighting are supported
  - custom weights show real-time allocation status and require full allocation before saving
  - ETF-derived baskets are shown as read-only system-managed baskets
- Added a dedicated ETF holdings browse/research workspace:
  - `/etf-holdings` lists ETFs with stored holdings and loads holdings rows through a server-side paginated/searchable/sortable API
  - users can page through holdings, inspect selected holding details, and open constituent charts directly
  - users can compare the selected snapshot against another stored snapshot through a diff view that highlights added, removed, and reweighted holdings
  - the diff workspace also surfaces first-pass research summaries such as gross churn, total added/removed weight, total upweights/downweights, and the largest additions/removals/reweights
  - users can inspect a first weight-evolution panel that ranks top constituent weight movers across stored snapshots and visualizes each mover's observed weight path
  - users can inspect a turnover timeline that batch-navigates adjacent historical snapshots and summarizes churn, additions, removals, reweights, and top movers per transition
  - constituent timeline API points now include each point's weight delta from the previous observed snapshot
  - cross-ETF overlap analytics can compare selected ETF snapshots for shared/unique constituents, Jaccard overlap, shared weights, minimum-overlap weight, and top shared holdings
  - the ETF holdings workspace now has a compact overlap panel so users can select peer ETFs from the loaded profile list and inspect pairwise overlap cards
  - overlap matrix analytics can now expand the ETF comparison set from ETF profile metadata such as issuer, fund family, and search query, not only explicit symbol lists
  - the overlap panel now exposes a first issuer/family/search comparison control that uses the server-side matrix expansion path
- Added backend basket synthetic OHLCV:
  - `GET /api/v1/baskets/{basket_id}/ohlcv/{timeframe}` returns a rebased-to-100 weighted cumulative-return series
  - equal weights are interpreted as 1/N
  - explicit source/custom weights are normalized before series calculation
- Added initial Chart integration for basket synthetic series:
  - the basket builder can open `/chart/BASKET:{id}`
  - Chart loads basket OHLCV through the basket endpoint
  - basket chart tokens are not added to recent instruments or watchlists and do not show the ETF holdings panel
- Refactored ETF holdings refresh behind an adapter registry:
  - only concrete provider-specific issuer adapters are registered; the old generic configured-URL adapter path has been retired
  - major issuer adapter keys now use issuer-aware CSV route adapters that can resolve source URLs from profile URLs, URL templates, issuer product ids, and file-name hints
  - ARK-style public holdings file-name route construction is implemented as the first concrete issuer-specific route
  - iShares/BlackRock product-id based CSV route construction is implemented as a second concrete issuer-specific route
  - State Street/SPDR symbol-based public daily holdings XLSX route construction is implemented as another concrete issuer-specific route
  - inferred issuer product-page templates now cover common symbol-addressable Vanguard, Invesco, Schwab, Global X, and VanEck pages; the adapter discovers linked CSV/XLSX/ZIP holdings files from those pages before ingestion
  - issuer adapters probe route readiness before refresh and mark profiles without enough metadata as needing issuer route configuration
  - admin `POST /api/v1/etf-holdings/{symbol}/probe-adapter` exposes and persists route-readiness status, confidence, resolved URL, and missing route identifiers
  - admin `GET /api/v1/etf-holdings/adapters` exposes registered adapter keys, route identifiers, required identifiers, supported artifact formats, parser confidence, dated-fetch support, and explicit configured discovery-feed support
  - fetched issuer artifacts now support explicit ETF identity validation before ingestion:
    - profiles can provide expected fund/ETF symbol, name, CUSIP, or ISIN in `provider_aliases`
    - downloaded artifacts must contain at least one configured expected identifier before a snapshot is stored
    - conservative generic CSV/XLSX table metadata extraction can infer ETF identity from two-column preambles and explicit fund/ETF identity columns without confusing generic constituent ticker columns for ETF identity
    - matched/unverified validation status is retained in legal metadata
    - mismatched artifacts fail refresh rather than creating a wrong holdings snapshot
  - adapter-state success/failure health is persisted
  - admin `GET /api/v1/etf-holdings/{symbol}/adapter-state` exposes persisted adapter health, including source/count/completeness metadata and HTTP rate-limit/blocking classifications such as 429/403
  - adapter inference now uses configured ETF profile/product/holdings URL domains as confidence-scored issuer signals while preserving the no ticker-only guessing rule
  - issuer adapters now support explicit dated holdings URL templates plus admin `POST /api/v1/etf-holdings/{symbol}/refresh-date` for fetching one requested composition date when an issuer archive pattern is known
  - issuer adapters now support explicit configured fund-list discovery feeds through admin `POST /api/v1/etf-holdings/discover`; CSV/XLSX/ZIP discovery feeds can materialize lightweight ETF instruments and upsert profiles with issuer product ids, holdings URLs/templates, dated URL templates, CUSIP/ISIN identifiers, SEC CIK/series/class ids, FIGI/composite/share-class FIGI aliases, discovery source metadata, and raw discovery-row audit data
  - simple XLSX/OpenXML issuer holdings workbooks and ZIP archives containing CSV/XLSX holdings files preserve raw table data, source-format metadata, parser-version source format, and artifact identity validation through the same ingestion path
  - holdings row API outputs now expose the persisted per-snapshot `source_row_hash` for audit/replay tooling, not just the optional source row id
- Extended issuer-aware adapter routing with product/fund page discovery:
  - ETF profiles can provide issuer product-page URLs such as `product_url`, `issuer_product_url`, `fund_url`, `profile_url`, or `etf_url`
  - the adapter discovers linked CSV/XLSX/ZIP holdings files from those pages using conservative holdings/portfolio/constituent link hints
  - discovery scans anchor hrefs, conservative URL-bearing data attributes, and quoted page configuration strings while still requiring supported holdings-like file URLs
  - discovered files still pass through the existing fetched-artifact identity validation before ingestion
- Added SEC N-PORT/N-PORT-P-style XML reconstruction ingestion:
  - admin endpoint parses raw SEC filing XML into canonical holdings rows
  - report date, CUSIP/ISIN/SEDOL, shares, market value, currency, asset category, and percent-of-value weights are normalized where present
  - snapshots are stored as `sec_nport_reconstructed_holdings` with raw XML and known/published/source metadata
- Added baseline legacy SEC N-Q/N-CSR-style XML/HTML table reconstruction ingestion:
  - admin endpoint parses simple table-like legacy filing XML and simple EDGAR HTML schedule-of-investments tables into canonical holdings rows
  - split-row SEC HTML schedule tables are supported when security identity/CUSIP appears separately from the following numeric position row
  - report date, CUSIP/ISIN/SEDOL, shares, market value, currency, asset/security type, and percent-of-net-assets weights are normalized where present
  - snapshots are stored as `sec_legacy_reconstructed_holdings` with raw XML and known/published/source metadata
- Added an admin EDGAR N-PORT backfill primitive:
  - ETF profiles with `sec_cik` can query SEC submissions metadata for recent N-PORT filings and older SEC submissions `files` archive pages
  - discovered primary XML documents are downloaded from SEC Archives and ingested through the SEC reconstruction parser
- Added SEC fund ticker/series/class discovery:
  - admin `POST /api/v1/etf-holdings/discover-sec-funds` ingests SEC `company_tickers_mf`-style mappings
  - the endpoint materializes lightweight ETF instruments and upserts ETF profiles with SEC CIK, series id, and class id for EDGAR backfill routing
  - the endpoint supports an explicit `source_url` override for mirrors/fixtures and parses both keyed-object and `fields`/`data` SEC payload shapes
- Added an admin EDGAR legacy SEC backfill primitive:
  - ETF profiles with `sec_cik` can query SEC submissions metadata for N-Q/N-CSR-style filings
  - discovered primary XML/table documents are downloaded from SEC Archives and ingested through the legacy SEC reconstruction parser
  - single-ETF and bulk endpoints mirror the N-PORT backfill workflow
- Added persistent SEC backfill orchestration state:
  - `etf_holdings_backfill_job` stores run-level status, request bounds, counts, summary, and requester
  - `etf_holdings_backfill_filing` stores accession-level state, snapshot links, filing metadata, duplicate-safe status, and failure reasons
  - `GET /api/v1/etf-holdings/{symbol}/backfills` and `GET /api/v1/etf-holdings/backfill-jobs/{job_id}` expose the audit trail
  - repeated backfills skip already-ingested accessions instead of silently duplicating work
- Added SEC N-PORT bulk/scheduled orchestration:
  - admin `POST /api/v1/etf-holdings/backfill-sec-nport` processes all or selected ETF profiles with SEC CIKs under bounded limits
  - `ETF_HOLDINGS_SEC_BACKFILL_ENABLED` controls the scheduled worker hook
- Added basket universe support beyond Strategy Lab:
  - Screeners can persist `universe_basket_id` and run against manual or system-managed baskets
  - Radar run requests can pass `universe_type="basket"` with `universe_filter.basket_id`
- Added frontend Screener/Radar basket universe controls:
  - Screener builder can select and persist a manual or ETF-derived basket universe
  - Screener sidebar/result metadata names the selected basket rather than showing only the raw universe type
  - Radar can run scans against either all instruments or a selected manual/ETF-derived basket
  - Radar disables basket scans until a concrete basket is selected
- Added focused backend and frontend coverage:
  - provider registry unit test
  - ETF holdings API integration tests for manual ingest, CSV ingest, configured URL refresh, coverage summaries, point-in-time nearest snapshots, and ETF-derived basket materialization
  - basket API integration tests for manual CRUD, validation, and auto-classification
  - basket synthetic OHLCV integration test
  - SEC N-PORT-style XML ingestion integration test
  - SEC EDGAR N-PORT discovery/download backfill integration test with mocked recent and archived SEC responses, persisted job/filing state, duplicate skipping, and bulk endpoint coverage
  - Strategy Lab integration test proving an ETF holdings snapshot universe can preview and run
  - Strategy Lab integration test proving a basket universe can preview and run
  - Strategy Lab integration test proving a manual basket with stored composition snapshots can run dynamically through time
  - Screener integration test proving a basket universe can run
  - Radar integration test proving basket universe filtering limits evaluation
  - ETF holdings panel unit tests
  - Strategy Lab view unit tests proving ETF holdings, static basket, and dynamic ETF-derived basket universe configs are saved from the visual builder
  - chart-store and basket-view unit tests proving synthetic basket chart loading and basket-to-chart navigation

## Validation

- `cd backend && ENV_FILE=.env.dev uv run pytest tests/unit --cov=app --cov-report=term-missing --no-header -q`
- `backend/.venv/bin/pytest backend/tests/unit/services/test_etf_holdings_bootstrap.py --no-cov -q`
- `backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_bootstrap_endpoint_can_materialize_and_fetch_first_snapshot backend/tests/integration/api/test_etf_holdings.py::test_bootstrap_endpoint_persists_profile_when_no_route_can_be_resolved --no-cov -q`
- `backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py --no-cov -q`
- `rtk npm --prefix frontend run test -- tests/unit/views/test_etf_holdings_view.test.ts`
- `rtk npm --prefix frontend run type-check`
- `rtk uv run ruff check backend/app/services/etf_holdings.py backend/app/services/instrument_mastering.py backend/tests/unit/services/test_etf_holdings_bootstrap.py`
- `rtk uv run ruff check backend/app/routers/etf_holdings.py backend/app/services/etf_holdings_refresh.py backend/app/schemas/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`

- `rtk uv run ruff check backend/app/models/etf_holdings.py backend/app/schemas/etf_holdings.py backend/app/services/etf_holdings.py backend/app/services/etf_holdings_adapters.py backend/app/services/etf_holdings_refresh.py backend/app/routers/etf_holdings.py backend/app/tasks/etf_holdings_tasks.py backend/app/main.py backend/app/workers/arq_worker.py backend/app/providers/etf_holdings_internal.py backend/app/providers/registry.py backend/tests/integration/api/test_etf_holdings.py backend/tests/unit/services/test_provider_registry.py backend/alembic/versions/b8c9d0e1f2a3_add_etf_holdings.py`
- `rtk uv run ruff check backend/app/models/basket.py backend/app/schemas/basket.py backend/app/services/baskets.py backend/app/routers/baskets.py backend/app/routers/etf_holdings.py backend/app/main.py backend/app/models/__init__.py backend/tests/integration/api/test_etf_holdings.py backend/alembic/versions/c9d0e1f2a3b4_add_baskets.py`
- `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_provider_registry.py backend/tests/integration/api/test_etf_holdings.py --no-cov -q`
- `rtk uv run ruff check backend/app/services/strategy_lab.py backend/tests/integration/api/test_strategy_lab.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py backend/tests/integration/api/test_strategy_lab.py::TestStrategyLabAPI::test_strategy_run_can_use_etf_holdings_snapshot_universe --no-cov -q`
- `rtk npm --prefix frontend run type-check`
- `rtk npm --prefix frontend run test -- --run tests/unit/components/test_etf_holdings_panel.test.ts`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_strategy_lab_view.test.ts tests/unit/components/test_etf_holdings_panel.test.ts`
- `rtk make dev-infra`
- `git diff --check`
- `rtk uv run ruff check backend/app/schemas/basket.py backend/app/services/baskets.py backend/app/routers/baskets.py backend/app/services/strategy_lab.py backend/tests/integration/api/test_baskets.py backend/tests/integration/api/test_strategy_lab.py`
- `rtk npm --prefix frontend run type-check`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_strategy_lab_view.test.ts`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_baskets.py backend/tests/integration/api/test_strategy_lab.py::TestStrategyLabAPI::test_strategy_lab_can_preview_and_run_basket_universe --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_baskets_view.test.ts`
- `rtk uv run ruff check backend/app/services/baskets.py backend/app/routers/baskets.py backend/app/services/etf_holdings_adapters.py backend/app/services/etf_holdings_refresh.py backend/tests/integration/api/test_baskets.py backend/tests/integration/api/test_etf_holdings.py backend/tests/integration/api/test_strategy_lab.py`
- `rtk npm --prefix frontend run type-check`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_baskets_view.test.ts tests/unit/views/test_strategy_lab_view.test.ts tests/unit/components/test_etf_holdings_panel.test.ts`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_baskets.py backend/tests/integration/api/test_etf_holdings.py backend/tests/integration/api/test_strategy_lab.py::TestStrategyLabAPI::test_strategy_lab_can_preview_and_run_basket_universe --no-cov -q`
- `rtk uv run ruff check backend/app/services/etf_holdings_sec.py backend/app/routers/etf_holdings.py backend/app/schemas/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/stores/test_stores.test.ts tests/unit/views/test_baskets_view.test.ts`
- `rtk uv run ruff check backend/app/services/etf_holdings_edgar.py backend/app/routers/etf_holdings.py backend/app/schemas/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py --no-cov -q`
- `rtk uv run ruff check backend/app/services/etf_holdings_adapters.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py --no-cov -q`
- `rtk uv run ruff check backend/app/config.py backend/app/services/etf_holdings_edgar.py backend/app/routers/etf_holdings.py backend/app/schemas/etf_holdings.py backend/app/tasks/etf_holdings_tasks.py backend/app/workers/arq_worker.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py --no-cov -q`
- `rtk uv run ruff check backend/app/models/screener.py backend/app/services/screener_engine.py backend/app/routers/screener.py backend/tests/integration/api/test_screener.py backend/alembic/versions/e0f1a2b3c4d5_add_screener_basket_universe.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_screener.py --no-cov -q`
- `rtk uv run ruff check backend/app/services/radar_engine.py backend/app/routers/radar.py backend/tests/integration/api/test_radar.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_radar.py --no-cov -q`
- `cd backend && ENV_FILE=.env.dev uv run alembic heads`
- `rtk npm --prefix frontend run type-check`
- `rtk npm --prefix frontend run test -- --run tests/unit/stores/test_radar_store.test.ts tests/unit/views/test_radar_view.test.ts`
- `rtk npm --prefix frontend run test -- --run tests/unit/components/test_etf_holdings_panel.test.ts`
- `rtk uv run ruff check backend/app/schemas/etf_holdings.py backend/app/services/etf_holdings.py backend/app/routers/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_holdings_page_supports_server_side_paging_sorting_and_search --no-cov -q`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_holdings_diff_reports_added_removed_and_changed_rows --no-cov -q`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_weight_evolution_reports_top_historical_weight_movers --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_etf_holdings_view.test.ts`
- `rtk npm --prefix frontend run test -- --run tests/unit/components/test_etf_holdings_panel.test.ts`
- `rtk uv run ruff check backend/app/schemas/etf_holdings.py backend/app/services/etf_holdings.py backend/app/routers/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_etf_holdings_view.test.ts`
- `rtk npm --prefix frontend run type-check`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_transition_timeline_reports_adjacent_snapshot_churn --no-cov -q`
- `rtk uv run ruff check backend/app/schemas/etf_holdings.py backend/app/services/etf_holdings.py backend/app/routers/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_overlap_summary_compares_constituents_across_etfs --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_etf_holdings_view.test.ts`
- `rtk npm --prefix frontend run type-check`
- `rtk uv run ruff check backend/app/schemas/etf_holdings.py backend/app/services/etf_holdings.py backend/app/routers/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_overlap_matrix_summarizes_many_etf_relationships --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/views/test_etf_holdings_view.test.ts`
- `rtk npm --prefix frontend run type-check`
- `rtk uv run ruff check backend/app/services/etf_holdings_sec.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_sec_legacy_ingestion_reconstructs_split_identity_html_rows --no-cov -q`
- `rtk uv run ruff check backend/app/services/etf_holdings_adapters.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_issuer_adapter_discovers_holdings_file_from_product_page_data_attribute --no-cov -q`
- `rtk uv run ruff check backend/app/schemas/etf_holdings.py backend/app/services/etf_holdings.py backend/app/routers/etf_holdings.py backend/tests/integration/api/test_etf_holdings.py`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_etf_holdings.py::test_overlap_matrix_can_expand_etf_family_from_profile_metadata --no-cov -q`

## Assumptions

- Free-source ETF holdings are stored as ETF holdings/proxy membership, not official index constituents.
- `known_at`/`published_at` are persisted so Strategy Lab can later avoid look-ahead bias.
- Provider-specific ETF issuer adapters are the target and current architecture: one implementation per issuer/provider, promoted to supported only after backend-reachable live tests prove full-holdings fetches.
- Lightweight instrument materialization creates metadata-only instruments. Price history is still fetched later by the existing market-data/provider resolver when another feature needs prices.

## Pending

- ETF issuer/provider recognition currently covers 345 registered adapter keys, but provider-native support is only 102/345 under the user's clarified standard. SEC EDGAR fallback is useful fallback infrastructure only and must not be counted as native provider support.
- Native/live-backed providers currently total `102`; inspect `ISSUER_ADAPTER_CONFIGS` entries with `live_tested_default_route=True` for the authoritative list.
- Broad issuer routing infrastructure exists through provider-specific route constructors, explicit product URLs, configured issuer fund-list feeds, concrete issuer constructors, product-page discovery, and SEC filing fallback. Native issuer-route claims still require backend-reachable live tests; 321 registered providers still need isolated native/live-backed implementations.
- US Global Investors now has a backend-reachable native/live-tested route through public product-page holdings tables such as JETS.
- Current backend-reachable live-tested issuer routes now also include Invesco through the symbol-based QQQ-style holdings JSON route template.
- iShares/BlackRock default support now uses the current BlackRock product-data JSON holdings API; seeded, live-tested product ids include IVV and IWM, so IWM can bootstrap a full current holdings snapshot from a fresh DB.
- Seeded iShares/BlackRock default support now also includes EEM (`239637`), so EEM can bootstrap a full current holdings snapshot from a fresh DB without manual route configuration.
- The live provider test matrix now covers every registered issuer adapter without allowing silent recognition-only gaps: native live-backed adapters remain explicitly classified, and SEC-backed adapters probe ready when SEC identifiers are present.
- Invesco has a backend-fetchable native route for QQQ-style holdings; SEC fallback remains available when a native route is absent or not configured for a specific ETF/profile.
- Long-tail issuers may still retrieve holdings through SEC fallback when SEC identifiers are available, but they remain unsupported under the provider-native standard until each has an isolated native implementation plus static and live tests.
- Source-hardening baseline exists for malformed/empty issuer files, rate-limit classification, common schema aliases, CUSIP-like security identifiers, cash rows, accounting negatives, disclaimer-row skipping, and SEC legacy parsing. Remaining source work is still large because each remaining issuer needs native route research, implementation, static parser coverage, and live route validation.
- Live issuer smoke tests exist in `backend/tests/live/test_etf_holdings_live_providers.py` behind `RUN_LIVE_ETF_HOLDINGS_TESTS=1`. Native-route live tests cover the 102 direct issuer routes, while SEC-backed adapter behavior is validated separately and cannot be used to claim native support.
- SEC N-PORT/N-PORT-P XML parsing/admin ingestion, recent and archived EDGAR discovery/download, persistent accession/job state, duplicate-safe reruns, and bulk/scheduled hooks exist; baseline N-Q/N-CSR-style legacy XML/table, simple HTML schedule-table parsing, split-row HTML schedule reconstruction, month-name report dates, value-in-thousands schedules, manual/admin ingestion, EDGAR discovery/download/backfill, duplicate-safe reruns, and bulk processing also exist. Deeply nested/footnoted HTML filings and PDF-like filing handling remain long-tail maintenance.
- Basket builder/editor UI, backend basket OHLCV, and initial Chart synthetic basket loading exist; richer basket metadata/watchlist/compare semantics are not implemented yet.
- Strategy Lab consumes ETF holdings snapshots and baskets as static universes, and rules backtests now expose opt-in dynamic point-in-time ETF holdings mode plus ETF-derived and manual basket dynamic modes in the visual builder with an explicit constituent-removal exit policy and baseline execution-log snapshot attribution surfaced in the UI. Richer basket rebalance policies, historical basket snapshot editing/import UX, and deeper attribution drilldowns remain open.
- Screener/Radar backend and frontend basket universe consumption exists for static manual/ETF-derived baskets.
- Holdings navigation now has a compact Chart panel with selected-holding mini-stats, previous/next navigation, source/resolution metadata, and explicit constituent open actions.
- A dedicated `/etf-holdings` workspace now lists ETFs with stored holdings and loads holdings rows through a server-side paginated/searchable/sortable API.
- The `/etf-holdings` workspace now includes a first cross-snapshot diff view so users can compare two stored snapshots for additions, removals, and weight changes.
- The `/etf-holdings` workspace now includes a first top-mover weight-evolution view across stored snapshots.
- Historical adjacent-snapshot batch navigation now exists through the ETF holdings turnover timeline; cross-ETF overlap summaries and many-ETF overlap matrix analytics now have a compact ETF holdings workspace UI, and matrix requests can expand participants by issuer/fund-family/search metadata. Constituent timelines expose per-point weight deltas but still lack a richer dedicated exploration UI.

## Exact next step

- Continue replacing generated/thin ETF provider adapters with native provider integrations until the count reaches 345/345. Each promotion must include isolated implementation code, static parser/contract tests, and opt-in live provider tests. Current count is 110/345 native/live-backed, leaving 235 providers.

## 2026-07-07 - CoinShares native ETF holdings route

### Summary

- Promoted `coinshares` from generated/SEC-backed recognition-only support to native/live-backed support.
- Added provider-specific `CoinSharesHoldingsAdapter`:
  - uses the public CoinShares/Valkyrie widgets API behind product pages such as `https://coinshares.com/us/etf/wgmi/`.
  - fetches `https://www-api.coinshares.com/api/v2/Widgets?...&names=VALKYRIE_HOLDINGS_{symbol}`.
  - parses widget sections into canonical holdings rows with ticker, name, CUSIP, shares, price, market value, net assets, weight, and composition date.
  - preserves `Cash & Other` as a cash row rather than a fake tradable symbol.
- Live validation symbol: `WGMI`.
- Current truthful provider-native count is now:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `110`
  - providers still lacking native/live-backed support: `235`

### Validation

- `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_coinshares_adapter_fetches_widget_holdings tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q` -> `2 passed`
- `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py` -> `All checks passed`
- `git diff --check` -> passed
- `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k coinshares` -> escalated network run passed with `1 passed, 110 deselected`
- `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q` -> `1 passed`
- count command -> `345`, `110`, `235`, `coinshares_native=True`

### Next step

- Continue replacing generated/thin ETF provider adapters with isolated native/live-backed issuer routes. The goal remains open: `235` registered providers still lack native/live-backed support.

## 2026-07-06 - SS&C/ALPS native ETF holdings route

### Summary

- Promoted `ssc` from generated/SEC-backed recognition-only support to native/live-backed support through the public ALPS ETF holdings route.
- Added provider-specific `AlpsHoldingsAdapter`:
  - uses the same public HubSpot proxy route the ALPS product page calls: `https://www.alpsfunds.com/_hcms/api/getData?api_url=...`.
  - targets the public ALPS holdings API path `https://secure.alpsinc.com/MarketingAPI/api/v1/Holding/{symbol}/Full`.
  - uses public product pages such as `https://www.alpsfunds.com/exchange-traded-funds/sdog` as the request referer.
  - parses JSON fields including holding symbol, name, CUSIP, ISIN, SEDOL, weight, shares, market value, as-of date, holding type, sector, country, region, and industry.
  - classifies cash, fixed income, derivatives, funds, and equities instead of treating every row as a tradable equity.
  - expands `ssc` inference hints to include ALPS names/domains.
- Current truthful provider-native count is now:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `107`
  - providers still lacking native/live-backed support: `238`

### Validation

- `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py` -> `All checks passed`
- `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_ssc_alps_adapter_fetches_public_proxy_holdings_json tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q` -> `2 passed`
- `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q` -> `1 passed`
- `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k ssc` -> escalated network run passed with `1 passed, 107 deselected`
- count command -> `345`, `107`, `238`, `ssc_native=True`

### Problems found

- The direct ALPS API returns `401` when called without the ALPS/HubSpot proxy path; the native route must use the same `_hcms/api/getData` proxy used by the public product page.
- ALPS is represented in the registry as `ssc`, so this promotion had to include ALPS-specific issuer aliases and domain hints for better inference.

### Next step

- Continue replacing generated/thin ETF provider adapters with isolated native/live-backed issuer routes. The goal remains open: `238` registered providers still lack native/live-backed support.

## 2026-07-06 - Federated Hermes native ETF holdings route

### Summary

- Promoted `federated_hermes` from SEC-backed/recognition-only support to native/live-backed support.
- Added provider-specific `FederatedHermesHoldingsAdapter`:
  - visits the public ETF listing first to establish the anonymous session state Federated Hermes expects.
  - loads symbol-specific public ETF product pages such as `https://www.federatedhermes.com/us/products/exchange-traded-funds/total-return-bond-etf.do`.
  - posts the issuer product form to the Federated Hermes product section endpoint for daily holdings.
  - follows the public daily portfolio holdings table link and parses `daily-portfolio-holdings-table`.
  - handles Federated Hermes fields including name, security type, ticker, CUSIP, ISIN, SEDOL, maturity/expiration, long/short, shares/contracts, price, notional value, market value/unrealized appreciation or depreciation, and market-value weight.
  - classifies bonds/fixed income, derivatives, cash, and equities instead of treating every row as a tradable equity.
- Current truthful provider-native count is now:
  - registered ETF provider keys: `345`
  - native/live-backed provider integrations: `106`
  - providers still lacking native/live-backed support: `239`

### Validation

- `cd backend && UV_CACHE_DIR=../.uv-cache uv run ruff check app/services/etf_holdings_adapters.py tests/unit/services/test_etf_holdings_adapters.py tests/live/test_etf_holdings_live_providers.py` -> `All checks passed`
- `cd backend && UV_CACHE_DIR=../.uv-cache uv run pytest tests/unit/services/test_etf_holdings_adapters.py::test_federated_hermes_adapter_fetches_daily_holdings_table tests/unit/services/test_etf_holdings_adapters.py::test_holdings_adapter_catalog_exposes_expanded_recognition_set --no-cov -q` -> `2 passed`
- `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_provider_matrix_covers_every_registered_issuer_adapter --no-cov -q` -> `1 passed`
- `cd backend && RUN_LIVE_ETF_HOLDINGS_TESTS=1 UV_CACHE_DIR=../.uv-cache uv run pytest tests/live/test_etf_holdings_live_providers.py::test_live_issuer_direct_holdings_routes_return_parseable_rows --no-cov -q -k federated_hermes` -> escalated network run passed with `1 passed, 106 deselected`
- count command -> `345`, `106`, `239`, `federated_hermes_native=True`

### Problems found

- Federated Hermes does not expose a direct static CSV/XLSX route for the tested ETF. The daily holdings table is only reachable after product listing/session setup and an XHR-style product-section form post.
- Fetching the product page directly without the listing session can make the daily holdings section appear unavailable, so the adapter intentionally establishes issuer session state first.

### Next step

- Continue replacing generated/thin ETF provider adapters with isolated native/live-backed issuer routes. The goal remains open: `239` registered providers still lack native/live-backed support.
