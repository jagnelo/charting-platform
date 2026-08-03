# TC2000 Version 25 Parity Matrix

This is the implementation-facing matrix for the controlling plan. `Blocked` means
the source reference is required before visual acceptance; it is not an approval.

| Surface | Implementation ownership | Reference state | Functional status | Required evidence |
| --- | --- | --- | --- | --- |
| Application shell and US Top Down | `WorkstationView.vue` | Blocked | In progress | V25 capture, interaction/E2E, visual baseline |
| Workspace tabs and factory layouts | `workspaces.py` | Blocked | In progress | persistence, reset, layout visual reference |
| Docking/pop-outs | `WorkspaceLayoutHost.vue` | Blocked | In progress | pop-out/recovery, golden layout lifecycle, screenshots |
| Chart | `UPlotChart.vue` | Blocked | Existing/rework in progress | uPlot lifecycle, transforms, visual states |
| Watchlists/columns/filters | workstation tools + batch APIs | Blocked | In progress | 10k virtual-list, editor/scan/gauge tests |
| Top-down sector/breadth workflow | `analysis.py`, market groups | Blocked | In progress | point-in-time and E2E drill-down evidence |
| Unified Python | `/code`, runner | N/A | In progress | sandbox escape/resource suite |
| Study Lab | `/research`, `StudyLabView.vue` | Blocked | In progress | reproducibility/artifact/rendering suite |
| Notes and alerts | `/notes`, existing alerts | Blocked | In progress | user isolation and linked-tool tests |
| Excluded capabilities | `tc2000-capability-stubs.md` | N/A | Documented | primary-menu absence test |

No row can change to `Complete` until its full functional and visual acceptance evidence
is recorded in the referenced test/baseline system.

Current implementation evidence (not completion): the isolated Study Lab runner now
supports a typed `histogram` artifact with deterministic numeric buckets, the factory
positive-close study exposes current/longest/average/shortest streak metrics,
point-in-time forward-return rows, symbol-linked streak occurrences, and completed-
streak lengths for that distribution, and both
primary Study Lab result surfaces render the artifact through a uPlot bar overlay. The
focused runner, validation, Study Lab, and persisted-results tests pass; visual parity
remains blocked until the required approved Version 25 references exist.

The isolated image also installs pinned NumPy/Pandas wheels at build time and exposes
only restricted `np`/`pd` facades to user code. File/external-data methods are rejected
by source validation; NumPy/Pandas values are normalized before artifact persistence.
The rebuilt image import check reports NumPy `2.1.3` and Pandas `2.2.3`.
