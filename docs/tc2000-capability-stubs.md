# TC2000 Workstation Capability Stubs

These are stable extension contracts, not visible disabled features. They remain absent
from the primary workstation menus until their enabling conditions and tests are met.

| ID | Intended contract | Required data/capability | Enabling condition | Current visibility |
| --- | --- | --- | --- | --- |
| `brokerage-trading` | Submit/cancel orders and show positions/fills. | Regulated broker integration, account authorization, order lifecycle. | Separate compliance/security review and broker adapter acceptance suite. | Legacy only; absent. |
| `options` | Chains, greeks, exposure, scans, and option charting. | Entitled option quote/history coverage and contract identity lifecycle. | Canonical options capability and provider entitlement acceptance. | Legacy only; absent. |
| `news` | Symbol-linked news feed and research articles. | Licensed redistribution/feed entitlement. | Provider contract, retention and attribution policy. | Absent. |
| `analyst-ratings` | Consensus/rating history and provider provenance. | Licensed ratings dataset. | Field-level provenance, terms, and coverage acceptance. | Absent. |
| `earnings-estimates` | Calendar, estimates, surprises, and revisions. | Licensed estimates/calendar source. | Point-in-time revision history and entitlement acceptance. | Absent. |
| `financial-statements` | Full historical statements and filing-derived report. | Normalized SEC/XBRL statement pipeline and taxonomy coverage. | Accounting-data reconciliation and field provenance acceptance. | Absent. |
| `consolidated-realtime` | Consolidated real-time quotes. | Paid/entitled consolidated market-data feed. | Explicit product decision; no free-source fallback may imply this capability. | Absent. |

Source-level ownership:

- Primary-menu registration is confined to `frontend/src/views/WorkstationView.vue` and
  its tool registry as it is introduced; no stub ID may be registered there.
- Legacy routes retain only the existing supported surfaces beneath `/legacy/*`.
- The final frontend acceptance suite must assert every ID above is absent from the
  authenticated workstation menu and that no disabled shell is rendered.
