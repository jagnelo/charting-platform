# Project TODO Memory

This file is the persistent deferred-work memory for the charting platform.

Purpose:
- Keep track of work that we explicitly chose to postpone.
- Preserve the surrounding context so a later pass does not lose the rationale.
- Act as the canonical place I should consult when you ask "what is still on the TODO list?"

Maintenance rules:
- When you ask to add something to the TODOs, I should add it here with context.
- When we fully solve one of these items, I should remove it from this file.
- If a TODO meaningfully changes shape, I should update the existing entry instead of duplicating it.
- This file is only for deferred or future work, not for work actively underway in the current turn.
- If another prompt, note, or agent hint disagrees with this file, prefer this file unless the user explicitly says otherwise.

Interpretation rules:
- Treat each entry as deferred work that was explicitly discussed and intentionally postponed.
- Do not use this file for the task currently in progress, vague brainstorming, or already completed work.
- Keep enough context that future sessions can understand why the item exists.
- Prefer updating an existing entry over creating a duplicate if the topic is the same.

Status legend:
- `Deferred`: explicitly postponed for later
- `Planned`: agreed future work that has not started yet

## Deferred TODOs

### 1. Expand test coverage further
Status: `Deferred`

Context:
- We stabilized the broken backend and frontend suites and got them green again.
- Measured coverage is still uneven:
  - backend full-suite coverage is materially improved but still has dark areas
  - frontend lines/statements/branches are strong, but function coverage remains the main weak point

What remains:
- Raise frontend function coverage, especially around:
  - stores
  - composables
  - uPlot plugins
  - chart rendering helpers
- Raise backend coverage in currently under-covered routers/services/providers, especially:
  - dashboard-facing routers
  - watchlist/provider/options routers
  - provider adapters and ingestion-heavy services

Why this was deferred:
- The immediate goal was to first fix broken tests and restore reliability.
- The next coverage push should be targeted, not broad or mechanical.

### 2. Enrich options navigation and contract-history UX
Status: `Deferred`

Context:
- Options contracts are now treated as proper instruments and can be opened in the main chart flow.
- The current options-chain interaction is still functional-but-basic.
- We explicitly agreed to think about deeper options navigation later.

What remains:
- Improve navigation from options chain to contract history.
- Decide whether to add:
  - quick-chart preview
  - split-pane contract chart
  - side drawer / modal inspection
  - better dashboard/widget-side inspection flow
- Make options exploration feel more fluid in both `/chart` and dashboard contexts.

Why this was deferred:
- The current path works, but the UX can be substantially better and deserves a focused design pass.

### 3. Add instrument/asset-type targeting controls for screeners and similar universe consumers
Status: `Deferred`

Context:
- Options contracts can currently participate in broader instrument workflows if present in the DB.
- This is not inherently wrong, but we agreed the platform should let users deliberately decide what kinds of instruments a screener or similar flow should target.

What remains:
- Add explicit include/exclude targeting for instrument classes, such as:
  - equities
  - ETFs
  - indices
  - forex
  - futures
  - options
  - crypto
  - synthetics
- Review whether similar filtering should exist in:
  - screeners
  - search/browse/discovery
  - any other "evaluate many instruments" workflows

Why this was deferred:
- The underlying behavior is acceptable for now, but targeted control is important before the universe grows further.

### 4. Extend provider-side options data support beyond the current baseline
Status: `Deferred`

Context:
- We agreed to squeeze as much practical value as possible out of current providers for options.
- The architecture is ready for full options timeseries.
- Current provider support is still limited in what it can truly deliver historically.

What remains:
- Push option contract OHLCV/history further where current providers allow it.
- Later support true historical timeseries for:
  - bid
  - ask
  - open interest
  - implied volatility
  - greeks
- Keep treating these as time-series data, even when a provider only gives snapshots at specific times.

Why this was deferred:
- The storage and provider-agnostic model came first.
- Richer provider capability work belongs in a dedicated follow-up pass.

## Notes

- This file intentionally focuses on postponed work that already came up in discussion.
- It is not meant to replace issue tracking if we later decide to formalize roadmap management elsewhere.
- This is the only file that should be treated as the canonical TODO memory for deferred work in this repo.
