# fix/f8e-swing-analysis-gate

Created from degraded `master` at `01e8a63f901e033d6fe82c30689091ee93641174`.

The independent replay `32610660180` passed Backend Tests, Frontend Unit
Tests, and normal Playwright E2E, but the exhaustive gate failed only at
`F8e.swing-analysis` after 153 passed and 106 skipped tests. Both attempts
timed out waiting for a GET `/api/v1/instrument-indicators/` response after
returning to the sector; the page remained on the selected XLB sector. The
test incorrectly made a transport event mandatory even though the instrument
state can be restored from the client cache. The repair removes that wait and
asserts the restored RSI control through the UI, preserving the behavioural
contract without changing application code.
