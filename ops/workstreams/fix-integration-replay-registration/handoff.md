# fix/integration-replay-registration

Created from `master` at `b0d0e7fd1c9ad00ab2f8eecbeef8a69a0e4c40e7`. Update this handoff at each coherent boundary.

The prior exact candidate passed the local exhaustive gate and was published,
but the integration process queried GitHub immediately after `git push`; the
new master run was not yet visible and the script incorrectly wrote a degraded
marker. This branch adds bounded polling before declaring a replay missing.
