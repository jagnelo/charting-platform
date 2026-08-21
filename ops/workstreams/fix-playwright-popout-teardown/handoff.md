# fix/playwright-popout-teardown

Created from degraded master `2d71422874e4b4b05aa233ce6318cbcd7ec3d159`.
The exact master replay failed F8h when a popup closed during a direct click;
this branch routes both closes through the existing bounded race-safe helper and
keeps the independent visibility/page-count assertions intact.
The first repair replay also exposed F8j setup timing: its injected conflict did
not identify the Notes mutation, so the test now waits for the visible Notes tool
and matches its tool type/title before fulfilling the 409.
