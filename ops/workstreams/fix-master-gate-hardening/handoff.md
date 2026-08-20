# fix/master-gate-hardening

Created from `master` at `82699837d80e84a573798c328b24ecd305ecf244`.

## Boundary

The promoted master replay `32385399045` was red in the exhaustive gate. The
hard failure was F8e plot-library reopening after an async save/close race;
F8s breadth had a historical timestamp race and intermittent numeric-input
restoration; the performance soak intermittently observed stale extra uPlot
canvases after popup churn. The backend job and the independent branch replay
were green.

## Implementation

- uPlot rebuilds now carry a generation through async sub-pane creation; stale
  generations cannot append renderers after a newer rebuild.
- Dense breadth numeric inputs update the local draft on `input`, retain the
  draft while the live configuration object is echoed by snapshot persistence,
  and clear only when a workspace reload replaces that object.
- Explicit historical occurrence selections republish their timestamp after
  chart hydration and two paint turns.
- F8e waits for the plot menu's documented closed/open states before checking
  the persisted RSI control.

## Validation evidence

- `npx tsc --noEmit` passed.
- F8e/F8s repeated ten times each: 20/20 passed after the fix.
- Multi-window performance churn repeated ten times: 10/10 passed after the
  generation fix.
- No visual baselines, masks, thresholds, or retries were changed.

Next boundary: commit, push, run branch CI, then integrate this exact SHA into
the degraded master candidate and require a new green master replay before
clearing `.ai/master-degraded.json`.
