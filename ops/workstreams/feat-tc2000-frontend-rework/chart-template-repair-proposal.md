# Chart-template pointer repair for the staging coordinator

Checkpoint: `tc2000-workstation-integration-1`. Human acceptance pending.

Provider's recorded F9c-template-comparison failure is a toolbar stacking defect.
Read-only inspection of its current WorkstationToolContent.vue shows Plots at
z-index 13 and comparison controls at 12. The comparison chip extends into
the Plots hit area, so Plots receives the Remove RSP click.

TC already contains the relevant repair in historical commit
`8db6c9ac60e6532e82b15e89a86acaa504705586`. Current TC source puts comparisons
at z-index 14, sets pointer-events:none on their wrapper, and restores
pointer-events:auto on its input/direct buttons. Transparent wrapper space
therefore leaves the adjacent Plots button usable.

The coordinator can arrange an independently accepted narrow repair on its
authorized repair source. Proposed product delta against Provider's current
frontend is only:

```css
.chart-tool__compare {
  /* retain all current geometry declarations */
  z-index: 14;
  pointer-events: none;
}
.chart-tool__compare input, .chart-tool__compare > button {
  pointer-events: auto;
}
```

Do not import the TC feature branch. The historical commit also moved controls;
Provider already has those geometry changes, so importing the entire historical
patch is unnecessary. This session has not modified Provider or staging.

Current-source authenticated browser evidence on TC, using Vite 15190 against
the assigned backend 28008:

- Existing F9c-template-comparison passes 1/1 (12.4s), including ordinary
  Remove RSP and saved comparison restoration.
- All seven F9c/limited-width toolbar cases pass (38.1s): alternative transforms,
  template transforms, comparison restore, keyboard focus, constrained menus,
  bottom-edge menu placement, and constrained toolbar geometry.
- Strengthened F9c-template-comparison passes (8.4s), requiring both restored
  Remove RSP and Plots to pass normal pointer actionability checks.

These receipts establish TC behavior. The narrow repair source still needs its
own before/after reproduction, declared full validation and exact-source CI,
human acceptance, coordinator integration, and green staging CI. Provider can
then consume that green staging repair independently of the wider TC checkpoint.
Visual failures remain a separate investigation; no screenshot policy changes
are proposed here.
