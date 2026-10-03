# feat/strategy-lab-v2

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## 2026-10-03 - Trial-bound runtime evidence and worker lineage

The runtime artifact reference now carries a non-circular immutable binding to
its exact attempt, trial, experiment, portfolio, snapshot, strategy package,
engine input, and invocation input. Trial assembly creates the binding alongside
the content-addressed bundle. `MaterializedNautilusTrialInput` requires that
binding to match its owner-hydrated graph and assembly. A new runtime-evidence
builder derives `StrategyRuntimeRequest` and isolation preflight from that same
materialized input, checks the package/runtime ABI, and takes dependency pins
from the immutable strategy version. It is synchronous and belongs in the
dedicated backtest preparation process, not an API or heartbeat loop.

The authenticated search-worker handoff now requires the runtime request and
artifact bundle digests to agree, requires the persisted trial binding, and
cross-checks its attempt/trial/experiment/portfolio/snapshot/package identities
against the owner-hydrated PostgreSQL graph before allowing execution. The
binding travels inside the serialized worker request, so the existing durable
payload digest covers it. The host's search-dispatch evidence/request builder
still needs to use this new composition; dispatch continues to accept explicit
host evidence and no API event-loop or provider fetch was added.

At clean, pushed source SHA `8a98a0dca8fd3ae180ee28b9ee48a34b96f701a2`, all
1,133 Strategy Lab v2 tests passed; MyPy passed across 331 files; Ruff passed
for the package and runtime SDK; all eight changed Python files passed Ruff
formatting; and `git diff --check HEAD^ HEAD` was clean. The commit is pushed to
`origin/feat/strategy-lab-v2`.

Stable Nautilus 2.x remains unnecessary. Exact-pinned `2.0.0rc5` is qualified
for the four local backtest checks only; forward parity is separate. No
external dependency blocks the next owned composition slice. Full-stack-browser
is still final branch acceptance, not this slice's blocker.

Next: connect the materialized runtime evidence and artifact binding to the
host's pre-dispatch evidence/request builder. Construct admission, engine and
sandbox plans, encode the worker request from the same artifact reference, and
make the PostgreSQL/outbox staging path reject any drift among payload,
authorization, request, preflight, and materialized binding before enqueue.

## 2026-10-03 - Owner-hydrated runtime input materialization

Added a package-owned composition boundary that takes the already
owner-hydrated immutable attempt/trial/experiment/portfolio/snapshot/strategy
graph, canonical instrument/venue context, the exact package resolver and
verified local artifact store, plus an injected provider-owned frozen-series
decoder. It resolves the pinned strategy package and frozen series/event-tape
artifacts, assembles the Nautilus runtime input, and ties the result back to the
graph and exact attempt/experiment/portfolio/snapshot/package identities. It
rejects mismatched stores, package bindings, or instrument sets. It performs no
provider/network acquisition and does not import Nautilus; synchronous assembly
must run in a dedicated backtest preparation process rather than an API or
heartbeat event loop.

At exact clean source SHA `84617e4adaf6b82d2ef796febff67c2631375eb5`, all
1,132 Strategy Lab v2 tests passed; MyPy passed across 331 files; Ruff passed
for the package; the two new Python files passed Ruff formatting; and
`git diff --check` was clean. The implementation commit is pushed to
`origin/feat/strategy-lab-v2`.

This materializes the runtime input in package-owned code, but it is not yet
wired into search dispatch, persisted as an atomic attempt/dispatch binding, or
connected to the provider-owned Arrow decoder implementation. Those are the
next worker-composition and staging-contract integration slices. Stable
Nautilus 2.x is not a prerequisite: the pinned 2.0.0rc5 build remains qualified
for the four local backtest checks only; forward event-tape parity is separate.
The full-stack-browser profile remains final branch acceptance, not a blocker
for the next local implementation slice.

Next: feed this exact materialized input into host pre-dispatch evidence and
request composition, derive preflight/admission and the encoded worker payload
from it, then bind its fingerprint atomically to the attempt and dispatch via
the existing PostgreSQL/outbox path. Keep assembly in the dedicated serial
worker boundary and retain the provider-owned decoder seam until its contract
reaches staging.

## 2026-10-03 - Owner-bound search worker graph handoff

The authenticated search-dispatch worker callback now hydrates the dispatched
attempt using the persisted dispatch owner's scope before returning its worker
request. It verifies that the dispatch experiment matches the hydrated graph
and that the runtime package, strategy source digest, and entrypoint are all
pinned by that experiment. Search-worker composition fails closed when the
owner-scoped domain reader is unavailable. This prevents a correctly signed
queue payload from substituting a different persisted trial or package.

At exact clean source SHA `f515326b5eebe621c7251825e96e87423fc74126`, all
1,129 Strategy Lab v2 tests passed; MyPy passed across 329 files; Ruff passed
for the package; the four changed Python files passed Ruff formatting; and
`git diff --check` was clean. The commit is pushed to
`origin/feat/strategy-lab-v2`.

This verifies and binds the current decoded worker request; it still does not
construct that request's runtime bundle directly from the hydrated graph. The
next owned slice is production worker runtime-input assembly from verified
package and frozen-data artifacts, followed by atomic attempt/dispatch/runtime
provenance. Provider-owned Arrow decoding remains behind its staging contract.
Stable Nautilus v2 availability, forward parity, and the final full-stack
browser acceptance profile are not prerequisites for this implementation slice.

## 2026-10-03 - Owner-scoped trial graph hydration

`PostgresResourceReader` now resolves batches of typed domain records by their
content fingerprints inside the principal's owner scope, rejects ambiguous
owner-local duplicates, and rehydrates each record against its declared domain
fingerprint. `NautilusTrialDomainHydrator` uses that read surface to resolve a
queued/running attempt through its immutable trial, experiment, portfolio,
snapshot, strategy versions, and pinned packages. It rejects missing/foreign
resources and checks every cross-resource fingerprint, preflight, portfolio,
and package binding before returning the immutable graph. This is now the next
input to connect to worker runtime assembly; event/series bytes, instrument and
account adapters, and dispatch binding remain separate work.

At exact source SHA `516c1273a4a1d1df9b3f1e905a6c3d7670d76035`, all 1,127
Strategy Lab v2 tests passed; MyPy passed across 329 files; package Ruff checks
passed; and the four changed files passed Ruff formatting and `git diff --check`.
The package-wide format probe reports 198 untouched files that would be
reformatted, so no repository-wide formatting rewrite was applied. This host-
side change does not alter the pinned Nautilus runtime image or require rebuilding
it. The source commit is pushed to `origin/feat/strategy-lab-v2`.

This advances persisted owner-scoped worker hydration only; it does not yet
construct a worker request directly from the hydrated graph or complete atomic
runtime dispatch. Stable Nautilus v2 availability is not a prerequisite.

## 2026-10-03 - Scoped RC backtest result publication provenance

Nautilus result materialization now carries typed, content-fingerprinted engine
provenance: exact v2 package/release channel, source/wheel/runtime-image pin,
conformance evidence and report, authoritative execution scope, and execution
plan. The new provenance builder recomputes the conformance report and verifies
the ready plan, engine/build/snapshot identity, hardened sandbox plan/image,
scope-required checks, and pre-release restrictions. `plan_result_publication`
independently recomputes conformance, requires exact plan/result/evidence
identity, and permits `BACKTEST_AUTHORITATIVE` publication when its four
simulator checks pass without pretending forward parity passed. PostgreSQL
canonical decoding now recognizes the nested conformance provenance records.

At clean source SHA `f102f310499431b0c892483ec15e376f5503319f`, all 1,121 Strategy Lab v2 tests passed; scoped
MyPy passed across 321 files; Ruff and format checks passed for all 17 changed
Python files. The exact-pinned RC5 image rebuilt as
`sha256:66ace07d47af15aee57b75dcfaffe2a72df720c35355524efe628cd8f7c3d144`.
Its actual native fixture ran with networking disabled, read-only root,
capabilities dropped, no-new-privileges, UID 65532, and bounded CPU, memory,
file size, PIDs, and temporary storage. `NautilusRcFixtureReceipt` accepted the
actual JSON: multi-instrument accounting, native order/fill/cost, deterministic
replay, and lifecycle passed; forward event-tape parity remains explicitly
deferred; the fixture receipt itself remains non-authoritative. Fixture digest:
`sha256:b233d6aa9953894f65628247455f6b349590c21946fac0a84797e3e9a78eee3e`.

This closes the local backtest result-provenance/publication seam, not the full
Strategy Lab goal. At this checkpoint source and native market-event tapes were
still materialized; a later source commit makes verified disk-spooled event-tape
resolution the default. Production worker hydration/dispatch, canonical
account/instrument adapters, target-position allocation/risk, broader
asset/product conformance, forward parity, and final full-stack-browser
validation remain. No stable Nautilus tag or upstream branch blocks continued
implementation. Provider, ETF, and TC2000 contract consumption is only a later
shared-path integration gate.

The source commit is pushed to `origin/feat/strategy-lab-v2`; local `HEAD` and
the tracked remote are both `f102f310499431b0c892483ec15e376f5503319f`.

This checkpoint updates the branch-owned
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`, `handoff.md`,
`validation.jsonl`, and `session.json` only.

Next replace full native event-tape bundle materialization with verified,
content-addressed stream/catalog chunks consumed incrementally by exact-pinned
RC5, preserving same-time ordering and deterministic replay. Then continue
owner-scoped trial hydration and atomic runtime dispatch.

## 2026-10-02 - Bounded Nautilus invocation-result artifact handoff

The invocation-result side of the Nautilus worker handoff is now streamed to a
bounded JSONL sidecar and published as a content-addressed artifact. The native
bridge writes each callback result incrementally; the runtime adapter returns
only a compact descriptor; and the host verifies the exact bytes, digest,
length, count, protocol, trailer, and status before artifact publication.
Output byte limits are enforced inside the isolated worker. Legacy batch
compatibility remains available.

At source SHA `adbf408e19169dd1a40087b69c30f36b74f25678`, all 1,098 Strategy Lab
v2 tests passed; Ruff and format checks for the 19 changed Python files passed;
MyPy passed across 325 source files; and `git diff --check` was clean. The
exact-pinned Nautilus `2.0.0rc5` image
(`sha256:00b866abd2d4f5fa858999ebec6a6d2a7f0e66912561b4f4f570bdffea68f76c`)
ran the real CLI and engine with networking disabled, a read-only root,
capabilities dropped, no-new-privileges, unprivileged UID, and bounded CPU,
memory, file size, PIDs, and temporary storage. It processed two native events,
invoked the SDK once, produced one native order and one open position, verified
the streamed result artifact (one record, 1,016 bytes), and remained
`authoritative=false`. Runtime evidence digest:
`sha256:47ed789b76c6c48293174b08caa4b5b01be7aa3378e8be655c5f750b3963e6a3`.

This closes the bounded invocation-result artifact seam only. Source and native
market-event tapes are still materialized before runtime launch; next replace
the full native-event tape with verified, content-addressed stream/catalog
chunks consumed incrementally by exact-pinned RC5, preserving same-time order
and deterministic replay. RC5 is usable for local testing after conformance;
it remains barred from broker/real-capital use, and full conformance—not a
stable upstream tag—gates authoritative results. No external dependency blocks
the next implementation slice.

The source commit is pushed to `origin/feat/strategy-lab-v2`; local `HEAD` and
the tracked remote are both `adbf408e19169dd1a40087b69c30f36b74f25678`.

## 2026-10-02 - End-to-end pinned context-stream handoff

Trial assembly no longer builds a full SDK context tuple or serialized batch.
It streams `iter_event_tape_contexts` into a content-addressed pinned-input
artifact, and the v2 runtime bundle binds that sidecar's manifest and context
count while preserving the legacy v1 batch format for compatibility. The
worker request and hardened Docker plan require the matching read-only mount
and digest; the host verifies the exact mounted bytes before launch. The
isolated CLI independently authenticates the bundle, attempt, snapshot,
runtime version, sidecar descriptor, and sidecar bytes before passing the
seekable file to the RC5 strategy bridge. Unapproved Docker mounts/environment
options are rejected. The isolated CLI does not import host artifact-store or
backend-only modules.

At clean source SHA `8cb165aab6843c2bd3577b2aab17d59b7584decb`, all 1,093
Strategy Lab v2 tests passed; Ruff and formatting checks passed; MyPy passed
across 325 source files; and `git diff --check` was clean. A freshly built,
wheel-checksum-pinned Nautilus `2.0.0rc5` image
(`sha256:2ed9fb927087c1af483d05e8a24c50f7b656da0161c7a5a240e27eb2a255f436`)
ran the real bundle/sidecar CLI and native engine under network-disabled,
read-only, dropped-capability, no-new-privileges, unprivileged, memory/CPU/file
size/PID-limited settings. It processed two same-time quotes, invoked the SDK
once, produced one native order and one open position, and remained explicitly
non-authoritative.

This closes only the bounded SDK-context side of the runtime handoff. The
frozen source `EventTape` and the native event tape are still fully
materialized; the runtime result and invocation-result list are still
materialized before artifact publication. Next, stream result records directly
to bounded artifacts, then move native market events into verified
content-addressed stream/catalog chunks consumed incrementally by RC5. After
those data-plane seams, continue owner-scoped runtime hydration, instrument /
venue / account adapters, atomic dispatch binding, target-position allocation
and risk routing, and broad native conformance. Exact-pinned prereleases remain
eligible for local testing; full conformance still gates authority, while
stable-tag availability does not block development. Provider / ETF / TC2000
shared-path work remains a later staging reconciliation gate only.

## 2026-10-02 - Streaming Strategy SDK runtime consumer

Connected the context-stream protocol to the engine-neutral runtime CLI. It
validates the complete source/manifest/context stream before invoking strategy
code, then runs one persistent SDK session while pulling one context at a time.
Typed invocation results are written incrementally to a versioned JSONL stream
with contiguous indexes, a record digest/count trailer, and atomic file
publication. The context stream now also carries a trailer so truncation and
record drift are detected. Existing one-event and batch CLI inputs/outputs
remain compatible.

At clean source SHA `1018c65cf5fe8969bf53add492ebe180e88c7eb2`, all 1,083
Strategy Lab v2 tests passed; Ruff and MyPy across 325 source files passed;
all four changed Python files passed formatting checks; and whitespace
validation was clean. The implementation commit is pushed and local `HEAD`
matches `origin/feat/strategy-lab-v2`.

This materially reduces SDK replay serialization/runtime memory, but does not
yet make the Nautilus backtest end-to-end bounded. Trial assembly and the
Nautilus CLI/bridge still use the old in-memory event tape and batch path. Next
bind content-addressed context and native-event stream artifacts into the
compact runtime manifest and worker handoff, verify/mount them read-only, and
consume the native data through exact-pinned RC5 catalog chunks. Preserve
same-time ordering and full conformance as gates for authoritative results.

## 2026-10-02 - Bounded SDK invocation-context stream protocol

Added `iter_event_tape_contexts`, which yields one same-time SDK context at a
time while retaining only declared rolling histories and the current event
batch. Added a versioned JSONL invocation-context protocol that writes and
reads one context record at a time, validates strict chronology and contiguous
record indexes, rejects oversized rows/streams, and preserves the existing
duplicate-field and non-finite JSON protections. The batch APIs remain
available for compatibility.

At clean source SHA `446288c20ecf75af6258a46b573fc49d105824aa`, all 1,079
Strategy Lab v2 tests passed; Ruff and MyPy across 325 source files passed;
the five changed Python files passed format checks; and `git diff --check` was
clean. This source commit is pushed and local `HEAD` matches
`origin/feat/strategy-lab-v2`.

This is a streaming boundary, not yet end-to-end bounded backtesting: trial
assembly still accepts/materializes an in-memory frozen tape, builds the full
native event tape and context batch, and embeds them in the runtime bundle.
The next implementation slice must bind verified event/context stream
artifacts into the runtime input and consume them in the isolated Nautilus
worker through catalog chunks. Exact-pinned RC5 remains eligible for local
research; full platform conformance and event-tape parity remain gates for
authoritative results and broker-free shadow activation. No stable 2.x tag,
parallel worktree, or provider/ETF/TC2000 staging change blocks this work.

## 2026-10-02 - Pinned Nautilus v2 qualification policy

The Strategy Lab does not wait for an upstream stable 2.x tag. An exact-pinned
Nautilus v2 build, including the current `2.0.0rc5`, is eligible for local
backtests after it passes the full platform conformance suite. Results retain
the exact package version/channel and wheel/image digests. A pre-release may
not connect to a broker or control real capital; broker-free forward-shadow
qualification separately requires event-tape parity. This converts the former
stable-tag dependency into a measurable local qualification gate while keeping
the research sandbox local and fail-closed.

Upstream currently documents v2 wheels as release candidates, requires
pre-release installation, and advises against using them in production to
control real capital: [NautilusTrader installation guidance](https://nautilustrader.io/docs/nightly/getting_started/installation/)
and [official releases](https://github.com/nautechsystems/nautilus_trader/releases).
The branch has already built and exercised its digest-pinned RC5 image in the
isolated sandbox. At source SHA
`443a692bfde9113579f35bb60c028e2b9c6d6730`, the exact Strategy Lab v2 suite
passed 1,047 tests, Ruff passed, MyPy passed across 320 source files, all eight
changed Python files passed formatting, and the whitespace check was clean.
The partial RC fixture remains non-authoritative; full multi-instrument,
accounting, reporting, replay, lifecycle, and forward-parity evidence remains
implementation work, not an upstream release wait.

## 2026-10-02 - Fail-closed persisted domain fingerprint validation

The owner-scoped typed resource reader now rejects a present-but-malformed
persisted `domain_fingerprint` instead of treating it as absent and skipping
the identity comparison. The malformed-type regression test is included in the
full package suite. At exact source SHA
`badee4d716345258a8393833969f765de5576bed`, all 1,047 Strategy Lab v2 tests
passed, Ruff passed, MyPy passed across 320 source files, the four changed
Python files passed format checks, and whitespace validation was clean. This
source commit is pushed and the local/remote hashes match.

## 2026-10-02 - Owner-scoped typed resource rehydration

`ResourceDomainNormalization` now retains the typed domain contract it already
constructs while validating strategy, package, portfolio, experiment, attempt,
snapshot, trial, metric-set, and forward-instance resources. The new
`rehydrate_resource_contract` function rebuilds a typed value from the canonical
persisted attributes through the same strict normalizers used at creation and
rejects generic resource types without a typed contract. The PostgreSQL
resource reader exposes `get_domain_contract`, reusing its owner-scoped read and
checking a stored domain fingerprint against rehydrated attributes when that
fingerprint is present. Foreign resources remain indistinguishable from missing
ones; malformed attributes and fingerprint drift fail closed.

At source SHA `462fbb541361a758f8bfdb2c9a0e517a8acbc9e2`, all 1,046
Strategy Lab v2 tests passed, Ruff passed, MyPy passed across 320 source files,
all four changed Python files passed format checks, and whitespace validation
was clean. PostgreSQL reader behavior is unit-tested through the existing
owner-scoped reader with an in-memory aggregate store; a live database
integration run remains part of the broader acceptance gate. The source commit
is pushed and local/remote hashes matched.

The next host-composition work still needs verified local resolvers for
package/source/manifest and frozen event-tape bytes, plus provider-derived
instrument metadata and venue/account construction. The immutable bundle
producer can then consume those values and its artifact reference can be bound
into atomic dispatch. Target-position allocation/risk integration and broad
native product/accounting/report conformance remain later gates. No parallel
provider, ETF, or TC2000 worktree was read or modified.

## 2026-10-02 - Immutable Nautilus trial-input assembly

Added a producer that binds one queued/running attempt to its immutable
scientific trial, experiment, portfolio, snapshot, preflight report, frozen
event tape, strategy package/SDK manifest/source, native instrument catalog,
and venue cash account. It cross-checks their fingerprints and declared
instrument/capital scope, combines strategy defaults with trial parameters,
builds event-aligned SDK contexts and native engine input, then publishes the
serialized bundle to the pinned content-addressed artifact store. Unsupported
multi-component portfolios, rebalances, scenarios, and evaluation windows fail
closed before publication. The producer does not access a database or dispatch
a worker; host rehydration and atomic dispatch binding remain the next seam.

At source SHA `58e2882d6820301db3eb579c712553606145bda9`, all 1,041
Strategy Lab v2 tests passed, Ruff passed, MyPy passed across 320 source files,
and both changed Python files passed the format check. This proves the local
producer and its contracts, not the complete API-to-worker route. Nautilus
2.0.0rc5 remains usable for isolated non-authoritative research runs; its
upstream stable release is not a development blocker and still gates only the
branch's stable-authority acceptance requirements.

The next action is a trusted host resolver that rehydrates the persisted trial
inputs and binds the resulting artifact reference into the existing atomic
dispatch evidence. Target-position intents still need event-aligned
allocation/risk integration, followed by broader native product, accounting,
and report conformance. No provider-platform, ETF, or TC2000 worktree is being
modified; only their eventual shared-contract integration depends on staging.
This source context is committed as `58e2882d6820301db3eb579c712553606145bda9`
and pushed to `origin/feat/strategy-lab-v2`; the verified local and remote
source hashes matched at publication.

## 2026-10-02 - Nautilus same-time event-batch bridge

The isolated Nautilus bridge now consumes the engine-neutral SDK's same-time
event batches as one strategy invocation, bound to the final native callback
for that timestamp so all events in the batch are visible first. Legacy
one-context-per-event worker payloads remain supported. The bridge also now
compares native nanosecond timestamps to SDK timestamps at their shared
microsecond precision; the previous comparison could only pass around the Unix
epoch and rejected normal modern dates. Its RC5 runtime probe now uses two
simultaneous native events at a 2024 timestamp.

At source SHA `4f3cfc4d4f2212841825d696f8f191cf47b59f2c`, the complete
Strategy Lab v2 package passed 1,035 tests, Ruff passed, MyPy passed across 318
source files, changed files passed format checks, and all 30 workstream records
validated. A separately tagged, checksum-pinned Nautilus `2.0.0rc5` image
(`sha256:bc8aa4436f0083382d0ea49a9ebd28d829dcab83cca631085b26910bf5d3f0a9`)
passed the network-disabled, read-only, capability-dropped probe: two native
events, one SDK invocation, one native order, one open position, explicitly
non-authoritative. This is local compatibility evidence, not publication or
conformance authority.

No release wait blocks implementation. The next producer gap remains assembling
persisted trial/snapshot/portfolio inputs into the pinned bundle and binding it
into durable dispatch. Multi-strategy shared-account routing and target-position
allocation/risk integration are still unsupported; stable-v2 conformance still
gates authoritative publication and deployed shadow activation.

## 2026-10-02 - Content-addressed Nautilus runtime-input handoff

Added a typed pinned-input artifact reference that keeps the Nautilus bundle's
semantic input digest distinct from the raw-byte SHA-256 used by the shared
artifact store. Bundle materialization is idempotent; reloading cross-checks
the schema, attempt identity, semantic digest, raw byte integrity, and an
explicit input-size bound. `WorkerExecutionRequest` now carries only this
compact reference, and its canonical durable envelope is versioned as v2.
Before launching Docker, the serial worker verifies the exact mounted regular
file against the artifact manifest, request digest, attempt, and memory-derived
size limit. The isolated CLI continues to recheck the semantic bundle digest.
Bad or drifted inputs are rejected before a container starts.

The complete Strategy Lab v2 package suite passed 1,031 tests; Ruff passed and
MyPy passed across 311 source files. Production assembly of the bundle from
frozen trial/snapshot/portfolio inputs and the dispatch producer remains the
next seam. Nautilus 2.0.0rc5 remains a local non-authoritative compatibility
runtime; stable v2 remains the gate for authority, published rankings, and
deployed shadow activation.

## 2026-09-25 - Account-settling forward-worker pipeline checkpoint

Added `RedisDispatchRuntime.account_settling_forward_worker_service()`, an
explicit composition factory for the complete forward handoff lifecycle. It
nests the reservation/lease authorization gate, canonical-event-bound account
settlement, and atomic capacity release so a host cannot accidentally wire a
worker that acknowledges after only one of those stages. Event/engine
resolution and durable adapters remain host-supplied.

The focused account-worker, capacity-settlement, and Redis runtime composition
suite passed 11 tests. Ruff and MyPy remain green across 293 source files;
whitespace validation is clean.

## 2026-09-25 - Forward-worker capacity settlement checkpoint

Added `ForwardWorkerCapacityReleaseHandler` and the
`RedisDispatchRuntime.settling_forward_worker_service()` factory. A forward
handler must first return a durable completion receipt; only then is a release
observation validated against the authorized worker/lease and passed to the
existing atomic PostgreSQL `release_capacity` boundary. Released and exact
replay outcomes permit acknowledgement; rejected release evidence remains
retryable, preventing capacity loss or premature Redis acknowledgement.

The focused capacity-settlement and Redis runtime suite passed 8 tests. Ruff
and MyPy remain green across 293 source files; whitespace validation is clean.

## 2026-09-25 - Atomic forward-worker authorization load checkpoint

`PostgresWorkerStateAdapter.load_forward_authorization()` now loads the
forward worker profile, reservation, and lease plus its authenticated
observation history in one transaction with row locks. The application bridge
delegates to this method, eliminating the race that separate pool and lease
reads could introduce between authorization and dispatch handling.

The focused PostgreSQL worker-state and application authorization suite passed
8 tests. Ruff and MyPy remain green across 291 source files; whitespace
validation is clean.

## 2026-09-25 - Durable forward-worker authorization bridge checkpoint

The application adapter now exposes
`load_forward_worker_authorization()`, loading an authenticated worker-pool
reservation and lease from the existing PostgreSQL worker-state adapter and
returning the typed authorization consumed by the forward-worker gate. Missing
reservation or lease records return no authorization; no capacity or lease is
invented at the application boundary.

The focused application authorization bridge suite passed 2 tests. Ruff and
MyPy remain green across 291 source files; whitespace validation is clean.

## 2026-09-25 - Forward-worker reservation/lease authorization checkpoint

Added the pure `AuthorizedForwardEventHandler` gate and the
`RedisDispatchRuntime.authorized_forward_worker_service()` factory. A forward
work item now requires a host-loaded `WorkerReservation` of kind `FORWARD` and
an `ExecutionAttemptLease` bound to the same worker and instance. Released,
wrong-kind, cross-instance, or expired evidence cannot reach account/engine
handling; expired leases remain retryable for recovery. Persistence remains
responsible for loading the reservation and lease records.

The focused authorization and Redis runtime suites passed 11 tests. Ruff and
MyPy remain green across 291 source files; whitespace validation is clean.

## 2026-09-25 - Dedicated forward-worker runtime composition checkpoint

`RedisDispatchRuntime` now exposes an explicit `forward_worker_service()`
factory. It binds a dedicated queue scheduler to
`ForwardEventWorkerService`, while preserving the generic backtest/runtime
worker factory as a separate path. The host still supplies authenticated
handoff materialization, canonical-event/account settlement, worker
reservation, and engine callbacks; this seam does not start providers or
Nautilus.

The Redis runtime composition suite passed 6 tests, with Ruff, MyPy, and
whitespace validation green across 289 source files.

## 2026-09-25 - Forward shadow-account API projection checkpoint

Added the authenticated read-only
`GET /api/v1/strategy-lab/v2/forward-instances/{instance_id}/account` route.
It exposes canonical cash, positions, orders, fills, cursor, and applied-event
identities through the same fail-closed adapter boundary as forward admission
state, returning typed not-found and host-not-configured errors without
inventing account data.

The focused API serializer suite passed 2 tests, with Ruff, MyPy, and
whitespace validation green. Full TestClient startup remains restricted by the
existing environment hang; route logic is covered through the package-owned
serializer and adapter seam.

## 2026-09-25 - Shadow-account compare-and-set hardening

Account state updates now include the previously loaded state fingerprint in
their SQL compare-and-set predicate. A concurrent or stale writer therefore
fails closed even though normal reads already lock the account row; exact
replays continue to return the persisted state without a second mutation.
Focused PostgreSQL account and worker-binding coverage passed 6 tests, with
Ruff, MyPy, and whitespace validation still green.

## 2026-09-25 - Forward shadow-account worker settlement checkpoint

Added `ForwardAccountWorkerHandler`, a composable host-worker boundary for
durable shadow-account settlement. The host resolver produces a typed binding
between the canonical stream event and immutable account effects for an
authenticated `ForwardEventWorkItem`; the handler verifies event identity,
sequence, timestamp, and instance fingerprints before applying them through
the owner-scoped account store. Redis is acknowledged only after an `APPLIED`
or exact `REPLAY_EXISTING` account resolution. Missing initialization and
out-of-order effects remain retryable, while identity conflicts and malformed
effects remain pending as fail-closed rejections.

The focused account-worker, forward-worker, ledger, and PostgreSQL account
suite passed 13 tests. Ruff and MyPy remain green across 289 source files;
whitespace validation is clean. Provider event resolution, worker
capacity/authorization, and stable Nautilus execution remain explicit host
gates.

## 2026-09-25 - Forward shadow-account persistence checkpoint

Added `PostgresForwardAccountAdapter` and the additive
`strategy_lab_v2_forward_accounts` table. Account state is stored as
owner-authenticated canonical JSON with a deterministic state fingerprint and
instance-bound primary key. Initialization is idempotent for exact retries and
rejects changed state; loads and event applications preserve typed replay,
conflict, out-of-order, and rejection outcomes from the engine-neutral ledger.
The shared persistence bundle and application adapter now expose
initialize/load/apply account methods, and canonical rehydration accepts the
forward-account event/state contracts without bypassing field validation.

Focused forward-account, worker/handoff/dispatch/application/persistence
coverage passed 29 tests, and the migration suite passed 2 tests. Ruff and
MyPy remain green across 287 source files; whitespace validation is clean. A
package-wide collection was started but did not complete in the restricted
test environment, so this checkpoint relies on the focused suite and static
validation. Event-stream/provider authorization, worker capacity binding, and
stable Nautilus execution remain gated.

## 2026-09-25 - Forward shadow-account ledger checkpoint

Added the engine-neutral `forward_account.py` contract for broker-free shadow
state: immutable accepted orders, authoritative fills, multi-currency cash
balances, positions, and append-only applied-event identities. The pure
transition applies fills deterministically, preserves weighted average prices,
rejects unknown or overfilled orders, rejects out-of-order events, and replays
exact content without rewriting prior decisions. It performs no broker,
provider, persistence, or Nautilus I/O; a PostgreSQL account-state adapter is
the next persistence seam.

Focused forward account plus worker/handoff/dispatch/application/persistence
coverage passed 39 tests. Ruff and MyPy remain green across 285 source files.
Account-state persistence, event-stream activation, worker authorization, and
stable Nautilus execution remain gated.

## 2026-09-25 - Forward worker service checkpoint

Added `ForwardEventWorkerService`, a bounded Redis scheduler composition for
authenticated forward-event work items. It retries materialization or host
handler failures without acknowledging the stream entry and acknowledges only
the handler's entry-bound durable receipt. The handler receives the validated
stream entry plus typed event/replay fingerprints; provider event acquisition,
forward worker reservation, and Nautilus execution remain explicit host-owned
integration seams.

Focused forward worker service, handoff, dispatch, application, and
persistence coverage passed 35 tests. Ruff and MyPy remain green across 283
source files. Event-stream activation, worker authorization/capacity binding,
and stable Nautilus execution remain gated.

## 2026-09-25 - Authenticated forward worker handoff checkpoint

`PostgresForwardEventDispatchAdapter` now exposes an authenticated
`load_by_request_fingerprint` lookup for Redis consumers. The new
`forward_worker_handoff.py` materializer binds a stream entry to that durable
owner/instance/request identity, verifies queue and payload digests, and
returns a typed `ForwardEventWorkItem` containing the event and optional
counterfactual replay fingerprints. Canonical event acquisition remains an
explicit host-owned event-stream seam; no provider or engine is selected by
the transport payload.

Focused forward worker-handoff, dispatch, and persistence coverage passed 10
tests. Ruff and MyPy remain green across 281 source files. Event-stream
registration, worker authorization/capacity activation, and stable Nautilus
execution remain gated.

## 2026-09-25 - Forward-event dispatch persistence checkpoint

Added `PostgresForwardEventDispatchAdapter`, which reuses the authenticated
forward checkpoint/replay transaction and stages canonical event payload bytes,
idempotent forward dispatch identity, and the shared execution outbox together.
The application persistence bundle and adapter now expose this seam, and the
Alembic revision creates its owner/event/request uniqueness boundary. Replayed
events cannot create a second dispatch identity; the pure resolver returns a
typed conflict before persistence.

Focused forward-dispatch, application/persistence, and migration coverage
passed 29 tests. Ruff and MyPy remain green across 279 source files. Worker
authorization/capacity binding, event-stream activation, and stable Nautilus
execution remain gated.

## 2026-09-25 - Search dispatch payload durability checkpoint

The atomic PostgreSQL search-dispatch adapter now canonicalizes and verifies
the application payload against `DispatchRequest.payload_digest`, persists the
payload in the shared dispatch-payload table before enqueue, and rejects
changed bytes on replay. The application evidence path now forwards its
payload into that durable store. Redis workers can therefore resolve the
content-addressed handoff after dispatch without a second, uncoordinated
payload write.

Focused application and PostgreSQL dispatch coverage passed 18 tests. Ruff and
MyPy remain green across the package. Forward-event dispatch persistence and
stable Nautilus execution remain gated.

## 2026-09-25 - Search dispatch migration reconciliation checkpoint

The canonical additive Alembic revision now creates the two tables required by
`PostgresSearchDispatchAdapter`: owner-scoped execution admissions and
idempotent search dispatch identities. Their keys, uniqueness constraints, and
authenticated fields match the adapter schema, so durable search dispatch no
longer depends on undeclared tables. Migration coverage now asserts 41 v2
tables and the focused PostgreSQL search-dispatch/persistence suite passed 10
tests; Ruff and MyPy remain green across the package.

Forward-event dispatch persistence and stable Nautilus execution remain gated.

## 2026-09-25 - Local worker evidence resolver activation checkpoint

The opt-in `strategy-lab-v2-worker` Compose profile now defaults its evidence
resolver to the package-owned authenticated single-output mapper. This lets a
local worker reach callback composition without an unrelated blank environment
setting, while preserving explicit override for host-owned multi-artifact
mapping and the resolver's fail-closed publication checks. Compose validation
passed with the profile enabled; no worker or Docker socket was started.

Stable Nautilus execution, host multi-artifact policy, live runtime activation,
provider reconciliation, and deployment remain gated.

## 2026-09-25 - Search and forward state read API checkpoint

The application adapter now exposes authenticated reads for resumable search
checkpoints and restart-safe forward admission state, preserving owner
normalization and the persistence adapters' integrity checks. The versioned
router adds read-only `GET /experiments/{experiment_id}/search` and
`GET /forward-instances/{instance_id}/state` projections with typed 404/501
failure paths and stable state fingerprints. These reads do not mutate queues,
start workers, or infer provider/engine state.

Focused application coverage passed 15 tests and the read-only serializer
coverage passed 1 test. Ruff passed for the package and MyPy passed across 277
source files. The broader API TestClient rerun remains unavailable because the
restricted runtime hangs during Starlette context startup; stable Nautilus,
worker activation, provider reconciliation, and deployment remain gated.

## 2026-09-25 - Dedicated worker outbox scheduler checkpoint

`RedisDispatchRuntime` now exposes an `outbox_scheduler(...)` factory, and the
dedicated worker entrypoint starts that bounded transactional-outbox scheduler
beside the Redis worker pump whenever the runtime and persistence surfaces are
available. The relay task is cancelled and awaited before worker shutdown, so
Redis publication acknowledgements remain retry-safe without leaking a task.
Runtime doubles without an outbox surface continue to work for isolated tests.

Focused outbox/runtime and worker-entrypoint coverage passed 12 tests. Ruff
passed for the package and MyPy passed across 277 source files. Full production
Redis, migration, stable Nautilus, and deployment activation remain gated.

## 2026-09-25 - Explicit multi-artifact publication mapping checkpoint

The sandbox evidence resolver retains its safe single-file default and now
supports an explicit host-owned path mapping callback for result manifests
with multiple output artifacts. It requires an exact one-to-one mapping by
manifest digest, calls the byte-verifying `publish_file` path for each output,
and fails closed on missing/extra mappings, invalid paths, publisher rejection,
or missing publication plans. Worker payloads never select host paths.

Focused worker evidence coverage passed 14 tests, including the new
multi-artifact mapping and existing single-file rejection paths. Ruff passed
for the package and MyPy passed across 277 source files. Stable Nautilus,
worker activation, event-stream integration, and deployment remain gated.

## 2026-09-25 - Search candidate application lifecycle checkpoint

The application adapter now exposes owner-normalized search candidate
start/retry and terminal-record operations over `PostgresSearchStateAdapter`.
Candidate transition timestamps are normalized to UTC before persistence, and
the typed candidate phase/result boundary is validated before the durable
compare-and-set adapter is called. Search dispatch authorization and worker
transport remain explicit host-owned seams.

Focused application lifecycle coverage passed 2 tests. Ruff passed for the
package and MyPy passed across 277 source files. Search dispatch activation,
stable Nautilus execution, upstream reconciliation, and deployment remain
gated.

## 2026-09-25 - Forward lifecycle application seam checkpoint

`PostgresStrategyLabV2Adapter` now exposes owner-normalized forward lifecycle
operations over the durable forward-state adapter: instance registration,
compare-and-set lifecycle transition, one-time warm-up completion, and atomic
canonical event/correction admission. Transition timestamps are normalized to
UTC before persistence, while event acquisition and worker scheduling remain
explicit host responsibilities.

Focused application forward-lifecycle coverage passed 1 test. Ruff passed for
the package and MyPy passed across 277 source files. Forward event-stream
activation, provider integration, stable Nautilus execution, and deployment
remain gated.

## 2026-09-25 - Worker terminal publication binding checkpoint

`PostgresWorkerTerminalAdapter` now receives the shared result-publication
adapter from `PostgresStrategyLabV2Persistence`. Successful terminal retries
re-register the authenticated publication plan before manifest/completion
persistence; a rejected plan is rejected at the worker boundary, while exact
accepted retries continue through the atomic completion/artifact ledger. This
closes the bypass where a terminal callback could load publication evidence
but invoke completion without re-authenticating the owner-scoped plan.

Focused worker callback, terminal adapter, and persistence coverage passed 18
tests. Ruff passed for the package and MyPy passed across 277 source files.
Stable Nautilus execution, worker activation, publication-byte mapping, and
upstream/deployment gates remain open.

## 2026-09-25 - Application result publication/completion bridge checkpoint

`PostgresStrategyLabV2Adapter.publish_and_complete_result` now provides the
application-owned seam between authenticated host evidence and the durable
result adapters. It normalizes the authenticated principal, registers the
immutable owner-scoped publication plan before terminal completion, records
rejected plans without entering completion, and delegates accepted plans to
the atomic PostgreSQL completion/artifact transaction with UTC-normalized
completion time. This gives worker evidence lookup a durable publication
identity without claiming that publication-plan registration and completion
are one cross-table transaction.

Focused application/result coverage passed 5 tests. Ruff passed for the
changed package files and MyPy passed across 277 source files. The existing
full package rerun limitation remains: Starlette `TestClient` hangs during
context startup in this restricted runtime, while direct ASGI validation is
successful. Worker activation, publication-byte mapping, stable Nautilus v2,
upstream reconciliation, and deployment remain gated.

## 2026-09-25 - PostgreSQL read-model replay identity checkpoint

Persisted metric-set and runtime-request read models now normalize aware
creation/submission timestamps to UTC before durable record fingerprints are
calculated. Offset-equivalent PostgreSQL projections therefore retain one
replay identity while their canonical payload and authentication checks remain
unchanged. Focused adapter/provenance coverage passed 14 tests. Ruff passed for
the package, MyPy passed across 277 source files, 2 schema migration tests
passed, diff validation passed, and workstream validation accepted 30 records.

The branch remains `ready_for_human_review`. Application result-publication
wiring, dedicated worker activation, upstream provider/ETF/TC2000 reconciliation,
stable Nautilus v2 publication, and deployment remain gated.

## 2026-09-25 - Search and legacy replay identity checkpoint

Legacy records/import requests and resumable search candidate/checkpoint state
now normalize aware timestamps to UTC before preservation, monotonicity, and
replay identity. Offset-equivalent legacy observations and search transitions
therefore share one deterministic fingerprint. Focused regression coverage
passed 18 tests. Ruff passed for the package, MyPy passed across 277 source
files, 2 schema migration tests passed, diff validation passed, and workstream
validation accepted 30 records.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated. The previously
recorded restricted-runtime TestClient limitation remains open for full rerun
evidence; direct ASGI route validation remains successful.

## 2026-09-25 - Preflight and cleanup evidence identity checkpoint

Capability requirements/cells, provider coverage attestations, and artifact
cleanup evidence now normalize aware history, series, observation, attestation,
and filesystem timestamps to UTC before matching and fingerprinting. Canonical
serialization now gives `timedelta` an explicit structural representation,
allowing cleanup resolutions with minimum-age policies to fingerprint and replay
deterministically. Focused regression coverage passed 64 tests. Ruff passed for
the package, MyPy passed across 277 source files, the 2 migration tests passed,
diff validation passed, and workstream validation accepted 30 records.

The last complete exact backend gate remains 2,542 tests with 83.81% coverage
from the preceding artifact-lifecycle checkpoint. A fresh broad package rerun
could not complete in this restricted runtime because Starlette's `TestClient`
hangs even for a minimal FastAPI application during context startup; direct
ASGI transport for the Strategy Lab route succeeds. This is recorded as an
environmental validation limitation, not as a passing claim. The branch remains
`ready_for_human_review`; stable Nautilus v2 publication, shared
worker/database reconciliation, host activation, upstream provider/ETF/TC2000
integration, and deployment remain gated.

## 2026-09-25 - Artifact lifecycle identity checkpoint

Artifact commit, lineage, and retention timestamps now normalize aware
acquisition/creation/expiry/release/observation timestamps to UTC before
provenance, retention, and replay identity. Offset-equivalent artifact
lifecycle observations therefore retain one deterministic identity and replay
path. Focused artifact lifecycle coverage passed 20 tests. The complete branch
gate passed 891 package tests, 2 migration tests, Ruff, MyPy across 276 files,
diff validation, and workstream validation. The exact backend coverage gate
passed 2,542 tests with 83.81% total coverage (required threshold: 75%) and 86
warnings; the referenced runtime env file was absent and `.env.dev` supplied
test configuration. The cleanup helper refused Docker inspection in this
restricted session on both passes; the generated backend coverage shard was
removed explicitly after verification.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Transactional outbox identity checkpoint

Transactional outbox messages now normalize aware creation and availability
timestamps to UTC before ordering and state fingerprinting. Offset-equivalent
enqueue schedules therefore preserve one message identity and replay path while
remaining storage- and transport-neutral. Focused outbox coverage passed 15
tests. The complete branch gate passed 888 package tests, 2 migration tests,
Ruff, MyPy across 276 files, diff validation, and workstream validation. The
exact backend coverage gate passed 2,539 tests with 83.81% total coverage
(required threshold: 75%) and 86 warnings; the referenced runtime env file was
absent and `.env.dev` supplied test configuration. Two cleanup passes retained
zero testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Result identity checkpoint

Engine result evidence, metric-set creation, and run-result manifest creation
timestamps now normalize aware offsets to UTC before content fingerprinting.
Offset-equivalent engine observations and manifest creation times therefore
retain one reproducible result identity and replay path. Focused result/core
coverage passed 25 tests. The complete branch gate passed 887 package tests,
2 migration tests, Ruff, MyPy across 276 files, diff validation, and workstream
validation. The exact backend coverage gate passed 2,538 tests with 83.81%
total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent and `.env.dev` supplied test configuration. Two
cleanup passes retained zero testcontainer sessions, containers, images, or
volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Dispatch and acquisition identity checkpoint

Dispatch requests and provider acquisition requests/receipts now normalize
aware creation, request, and acquisition timestamps to UTC at their contract
boundaries. Offset-equivalent queue and data handoffs therefore preserve one
content identity and replay path. Focused dispatch/acquisition coverage passed
17 tests. The complete branch gate passed 886 package tests, 2 migration tests,
Ruff, MyPy across 276 files, diff validation, and workstream validation. The
exact backend coverage gate passed 2,537 tests with 83.80% total coverage
(required threshold: 75%) and 86 warnings; the referenced runtime env file was
absent and `.env.dev` supplied test configuration. Two cleanup passes retained
zero testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Worker lifecycle timestamp checkpoint

Worker reservations, lease observations, and settlement receipts now normalize
aware acquisition, heartbeat, expiry, and release timestamps to UTC at their
contract boundaries. Offset-equivalent worker lifecycle observations therefore
retain one capacity/lease/settlement identity and replay path. Focused worker
lifecycle coverage passed 20 tests. The complete branch gate passed 884 package
tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation, and
workstream validation. The exact backend coverage gate passed 2,535 tests with
83.80% total coverage (required threshold: 75%) and 86 warnings; the
referenced runtime env file was absent and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Conformance evidence gate checkpoint

Conformance evidence construction now fails closed when a fixture suite omits a
required check, while retaining complete suites with failed observations as
explicit compatibility evidence. Conformance test timestamps normalize to UTC,
so offset-equivalent evidence retains one identity. Focused conformance
coverage passed 16 tests. The complete branch gate passed 881 package tests,
2 migration tests, Ruff, MyPy across 276 files, diff validation, and workstream
validation. The exact backend coverage gate passed 2,532 tests with 83.79%
total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent and `.env.dev` supplied test configuration. Two
cleanup passes retained zero testcontainer sessions, containers, images, or
volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Search candidate dispatch API boundary checkpoint

The versioned API now exposes `POST /experiments/{experiment_id}/search/dispatch`.
It strictly validates the candidate index, attempt identity, content-addressed
payload, queue name, timestamp, and `Idempotency-Key`, then delegates the full
candidate/admission/dispatch decision to an application-owned callback. The
response serializes the candidate state, admission ledger, worker-pool
evidence, and deterministic dispatch envelope. Saturation, conflicts, and
rejections map to typed retryable or fail-closed API errors.

`PostgresStrategyLabV2Adapter` accepts the same optional callback and normalizes
the authenticated owner before delegation. No partial mutation is attempted
when the binding is absent; the route returns a typed 501 precondition failure.
The callback remains deliberately host-owned because authorization, runtime
preflight, worker reservation, PostgreSQL CAS, and outbox staging must be one
transaction. Focused API/application coverage passed 34 tests, including
successful evidence serialization, strict-body rejection, and missing-binding
failure. The next durable slice is the PostgreSQL candidate/admission/outbox
transaction; worker process execution remains gated by stable Nautilus v2
conformance.

## 2026-09-25 - Atomic PostgreSQL search dispatch checkpoint

`postgres_search_dispatch.py` now provides the durable counterpart to the
pure search-dispatch resolver. In one SQLAlchemy transaction it locks the
owner-scoped search state and worker profile/reservations, authenticates the
admission and dispatch ledgers, resolves candidate start plus worker admission
plus idempotent queue intent, and persists the candidate CAS update, worker
reservation, admission receipt, dispatch identity, and shared execution
outbox message together. Saturation, rejection, and conflict resolutions
return before any write. Exact retries replay the existing admission and
dispatch evidence without duplicating rows.

The pure resolver also rejects a second dispatch identity for an already bound
attempt, so a new idempotency key cannot create a duplicate queue message for
the same candidate.

## 2026-09-25 - Durable search dispatch application binding checkpoint

`PostgresStrategyLabV2Adapter` now accepts a typed
`SearchDispatchEvidence` resolver. The host supplies authenticated execution
authorization, runtime request/preflight, reservation identity, and dispatch
time; the application then calls the shared `PostgresSearchDispatchAdapter`
itself, preserving one transaction for search state, worker capacity, admission,
dispatch, and outbox. The older result-returning callback remains available
for registration-neutral hosts, and configuring both forms is rejected as
ambiguous. Focused application coverage passed 10 tests, including normalized
owner propagation, durable-store delegation, and fail-closed missing binding.

## 2026-09-25 - Authenticated worker dispatch lookup checkpoint

`PostgresSearchDispatchAdapter` now exposes owner-scoped lookup by experiment
and candidate, plus an ambiguity-rejecting lookup by the Redis request
fingerprint. Both paths re-authenticate the dispatch request and its stored
fingerprint before returning the attempt/queue identity needed by a worker or
recovery handler; no owner is guessed when a request identity is ambiguous.
Focused lookup coverage passed 3 tests. Dedicated worker handler binding and
stable Nautilus execution remain separate gates.

The shared persistence bundle now exposes this adapter while leaving runtime
authorization, provider entitlement, and Nautilus execution as explicit host
inputs. The additive schema declares only admission and search-dispatch tables;
the existing execution-outbox table remains the authoritative shared outbox.
Focused PostgreSQL/persistence/application coverage passed 17 tests and the
complete package passed 866 tests. Stable Nautilus v2 conformance, host
capability/evidence resolvers, upstream provider/ETF/TC2000 reconciliation,
and migration/application integration remain open gates.

## Human authorization

- Recorded at: 2026-09-15T19:48:24.815519+00:00
- Request: Implement the approved Strategy Lab v2 plan; honor the repository AI-driven workflow rules and active branch boundaries.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; the plan remains at `ready_for_human_review` and the
  session-local goal is held at its plan-ready guard.

## 2026-09-25 - Capability preflight API seam checkpoint

The registration-neutral v2 router now exposes `POST /capabilities/preflight`.
Requests require a canonical JSON object and `Idempotency-Key`; an optional
application-owned `preflight_capability` binding receives the authenticated
principal, request identity, idempotency key, payload, and payload digest, then
returns the typed `CapabilitySummary` without exposing provider or engine
handles. Responses are stable `capability-preflights` documents with report,
binding, request, and payload fingerprints. If the host has not supplied the
binding, the route fails closed with `capability_unsupported`/501 rather than
inventing entitlement or engine capability.

Focused API coverage passed 23 tests, including successful delegation,
canonical identity propagation, malformed-body rejection, and the missing
binding failure. Capability calculation, provider entitlement, engine
registration, and application wiring remain host-owned gates. The authorized
push remains blocked by the environment's rejected GitHub SSH key
(`Permission denied (publickey)`).

## 2026-09-25 - Application capability preflight binding checkpoint

`PostgresStrategyLabV2Adapter` now exposes the optional application-owned
capability resolver behind the registration-neutral route. The resolver receives
the normalized owner, request/idempotency identities, canonical payload, and
payload digest; its typed `CapabilitySummary` is authenticated and registered
through the shared owner-scoped PostgreSQL capability adapter before the API
response is returned. A missing resolver remains an explicit typed 501 rather
than silently treating provider or engine capability as available.

Focused application tests cover owner normalization, durable summary handoff,
route registration, and the missing-binding failure. Provider entitlement,
engine registration, and the resolver's actual calculation remain host-owned
and are not inferred by this branch.

## 2026-09-25 - Durable search queue API checkpoint

The versioned API now exposes durable search lifecycle routes:
`POST /experiments/{experiment_id}/search` strictly accepts a content-addressed
trial-fingerprint list and creates/replays the owner-scoped PostgreSQL search
queue, while `POST /experiments/{experiment_id}/search/cancel` records an
idempotent cancellation request. Responses expose candidate phases, attempt
lineage, cancellation state, and authenticated state fingerprints as a stable
`search-experiments` document. Conflicting definitions, invalid fingerprints,
and missing search persistence fail closed with typed errors; no worker or
engine execution is started by FastAPI.

The application adapter now delegates initialization and cancellation to the
existing CAS-backed `PostgresSearchStateAdapter`. Focused router coverage
passed 25 tests; search dispatch, worker scheduling, and engine execution
remain separate durable-worker gates.

## 2026-09-25 - Result-manifest artifact binding checkpoint

Result completion now accepts the successful manifest's output-artifact
identities as an optional application-supplied evidence set. When supplied,
the pure completion gate rejects omitted, substituted, duplicated, or extra
artifact publication plans before any commit is resolved. The PostgreSQL
completion adapter carries the same evidence through its transaction, and the
worker terminal adapter supplies `RunResultManifest.output_artifacts` so the
host resolver cannot finalize a result against unrelated artifact bytes.

Focused completion/persistence tests passed 10 tests; the complete Strategy Lab
v2 package passed 832 tests. Branch-declared validation passed all six checks
(832 package tests, 2 migration tests, Ruff, MyPy across 270 files, diff, and
workstream validation). The exact backend gate passed 2,483 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Host application evidence resolution, stable
Nautilus release conformance, upstream contract reconciliation, and full
application integration remain open gates.

## 2026-09-25 - Typed worker terminal evidence resolver checkpoint

`worker_evidence_resolution.py` now deterministically combines the authenticated
owner/attempt lookup, durable submission/outcome/progress state, result
manifest, and accepted publication plan into `WorkerTerminalEvidence`. It
rejects process/attempt drift, missing or conflicting durable evidence,
multiple publication candidates, non-terminal runtime state, and artifact
plans on failed/cancelled runs. Artifact-file mapping remains an explicit host
callback; no worker path or principal is guessed. The persistence bundle now
exposes `worker_terminal_evidence_resolver()` to compose its authenticated
lookup with that callback shape.

Focused resolver/persistence tests passed 7 tests; the complete Strategy Lab v2
package passed 836 tests. Branch-declared validation passed all six checks
(836 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,487 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Host artifact mapping, stable Nautilus release
conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Artifact publication plan handoff checkpoint

`ArtifactPublicationResolution` now retains the exact verified
`ArtifactPublicationPlan` used for storage and commit finalization. Successful
create and replay resolutions therefore expose the same manifest/content/
retention/action identity that terminal completion must receive, while
rejections cannot carry a plan. This removes a reconstruction gap for the
explicit host artifact-mapping callback and keeps publication policy bound to
the verified bytes that were actually written.

Focused artifact-application tests passed 9 tests; the complete Strategy Lab
v2 package passed 836 tests. Branch-declared validation passed all six checks
(836 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,487 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Host artifact source mapping, stable Nautilus
release conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Single-output sandbox artifact mapper checkpoint

`create_sandbox_artifact_plan_resolver()` now composes the worker process
evidence with `LocalArtifactPublicationService.publish_sandbox_result()` for
the current one-file `/outputs/result` contract. It returns the exact verified
publication plan retained by the service, so terminal completion can bind its
artifact commit to the bytes observed by the sandbox. Manifests containing
multiple output artifacts fail closed and require an explicit host mapping
callback; failed/cancelled runs produce no artifact plans.

Focused resolver/artifact tests passed 5 tests; the complete Strategy Lab v2
package passed 838 tests. Branch-declared validation passed all six checks
(838 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,489 tests at 83.74%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Multi-artifact host mapping, stable Nautilus
release conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Package evidence resolver factory checkpoint

`worker_callbacks.py` now exposes
`default_evidence_resolver_factory(persistence, artifact_root)`. When selected
through the existing namespaced resolver setting, it composes the shared
owner/attempt lookup, the single-output sandbox artifact mapper, and the
durable PostgreSQL terminal writer without a host-specific module. Startup
remains fail-closed when the resolver setting is absent or malformed; the
factory itself still rejects persistence bundles missing explicit artifact or
terminal composition methods.

Focused callback tests passed 5 tests; the complete Strategy Lab v2 package
passed 839 tests. Branch-declared validation passed all six checks (839
package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,490 tests at 83.74%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Multi-artifact host mapping, deployment
configuration selection, stable Nautilus release conformance, upstream
contract reconciliation, and full application integration remain open gates.

## 2026-09-25 - Mounted result evidence checkpoint

`sandbox.py` now exposes the validated host source for the hardened
`/outputs/result` bind mount, reusing the same mount parser used by plan
validation. `sandbox_execution.py` hashes a successful mounted result file in
bounded streaming chunks and records its content digest and byte length on
`SandboxRunResult`; symlinks, directories, missing files, and files over the
declared output limit produce no valid result-file evidence. The executor does
not publish bytes or choose an application result manifest: those remain
application-owned adapter responsibilities, while stdout/stderr runtime
evidence remains backward compatible.

Focused sandbox tests passed 12 tests, the complete Strategy Lab v2 package
passed 823 tests, and branch-declared validation passed all six checks across
823 package tests, migrations, Ruff, MyPy across 270 files, diff, and
workstream validation. The exact backend gate passed 2,474 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Both required cleanup
passes retained zero testcontainer sessions, containers, images, or volumes.
The application-owned evidence resolver, stable Nautilus release, upstream
contract reconciliation, and full application integration remain open gates.

## 2026-09-25 - Streamed local artifact publication checkpoint

`artifacts.py` now verifies digest/byte-length observations independently of
in-memory payloads. `LocalArtifactStore.publish_file()` streams regular local
result files into the same-directory temporary/atomic-link workflow, verifies
the manifest before linking, re-verifies existing/racing/published targets by
streamed digest and length, and never buffers the mounted artifact. The
application publication service exposes `publish_file()` and finalizes the
existing idempotent PostgreSQL commit ledger through the same publication
decision path as byte payloads. Symlinks, directories, digest/length drift,
and malformed target content fail closed.

Focused artifact tests passed 27 tests; the complete Strategy Lab v2 package
passed 828 tests. Branch-declared validation passed all six checks across 828
package tests, migrations, Ruff, MyPy across 270 files, diff, and workstream
validation. The exact backend gate passed 2,479 tests at 83.73% coverage with
86 warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Both required cleanup passes retained
zero testcontainer sessions, containers, images, or volumes. Host application
evidence resolution, stable Nautilus release conformance, upstream contract
reconciliation, and full application integration remain open gates.

## 2026-09-25 - Sandbox-bound artifact publication checkpoint

`LocalArtifactPublicationService.publish_sandbox_result()` now binds artifact
publication to the exact successful `SandboxCommandPlan` and
`SandboxRunResult`. It requires captured mounted-file evidence, verifies the
manifest digest and byte length before any storage or commit operation, derives
the validated `/outputs/result` host source from the plan, and delegates to
streamed file publication. Plan drift, failed executions, missing evidence,
and manifest identity drift fail before the artifact ledger can change.

Focused artifact tests passed 29 tests; the complete Strategy Lab v2 package
passed 830 tests. Branch-declared validation passed all six checks across 830
package tests, migrations, Ruff, MyPy across 270 files, diff, and workstream
validation. The exact backend gate passed 2,481 tests at 83.73% coverage with
86 warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Both required cleanup passes retained
zero testcontainer sessions, containers, images, or volumes. Host application
evidence resolution, stable Nautilus release conformance, upstream contract
reconciliation, and full application integration remain open gates.

## 2026-09-25 - Mounted result identity materialization checkpoint

Successful runtime materialization now uses the validated mounted result-file
digest and byte length as terminal output evidence whenever that file was
captured by the sandbox. Legacy plans without a mounted result continue to use
their bounded stdout evidence. Both the pure runtime adapter and the
owner-scoped PostgreSQL runtime adapter apply the same selection, so retries,
compare-and-set state, and persisted update receipts cannot silently switch
between logs and the produced result artifact.

Focused runtime/sandbox/persistence tests passed 20 tests; the complete
Strategy Lab v2 package passed 824 tests. Branch-declared validation passed
all six checks across 824 package tests, migrations, Ruff, MyPy across 270
files, diff, and workstream validation. The exact backend gate passed 2,475
tests at 83.73% coverage with 86 warnings; the referenced runtime env file was
absent in this checkout and `.env.dev` supplied test configuration. Both
required cleanup passes retained zero testcontainer sessions, containers,
images, or volumes. Host application evidence resolution, stable Nautilus
release conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Typed metric-set rehydration

`postgres_metrics.py` now exposes owner-scoped `load_metric_set()` and
`load_all_metric_sets()` reads that strictly rehydrate authenticated canonical
payloads into `MetricSet` contracts through the shared allowlisted decoder.
Reads require exact canonical bytes and verify metric-set fingerprint, ID,
trial/attempt lineage, definition version, creation timestamp, and compact
value-summary bytes against the persisted projection. Reordered fields or
other payload tampering therefore fails closed before metric data reaches later
result/API adapters.

Focused lint and MyPy checks pass; the focused persistence suite passes 10
tests and the complete Strategy Lab v2 package passes 805 tests. The following
typed-resource integration checkpoint then passed all six branch checks, the
exact backend gate (2,457 tests at 83.69% coverage), two cleanup passes, and
workstream validation. The canonical push remains blocked by the environment's
rejected GitHub SSH key (`Permission denied (publickey)`).

## 2026-09-25 - Typed metric-set resource projection

The application persistence bundle now projects `metric-sets` API resources
from `PostgresMetricsAdapter.load_all_metric_sets()` instead of exposing raw
`PersistedMetricSet` summary rows. Resource IDs and revision metadata are bound
to the typed contract identity, so every API metric-set read passes through
canonical payload, lineage, and value-summary verification first.

Focused lint and MyPy checks pass; the focused persistence/metric suite passes
6 tests and the complete Strategy Lab v2 package passes 806 tests. The exact
backend gate passes 2,457 tests at 83.69% coverage, both cleanup passes retain
zero testcontainer resources, and all branch/workstream checks are recorded in
`validation.jsonl`.

## 2026-09-25 - Typed runtime-preflight rehydration

`postgres_runtime_receipts.py` now exposes
`load_preflight_contract()`, rehydrating the canonical
`StrategyRuntimePreflight` payload through the shared allowlisted decoder.
Reads require exact canonical bytes and verify request/profile/isolation
fingerprints, decision, and rejection-reason projections before admission
evidence is returned. Runtime contract modules are now part of the decoder's
explicit allowlist; unsupported tags and reordered fields fail closed.

Focused lint and MyPy checks pass; the focused runtime/materialization suite
passes 11 tests and the complete Strategy Lab v2 package passes 807 tests.

The exact backend gate then passed 2,458 tests at 83.69% combined coverage
with 86 warnings; both cleanup passes retained zero testcontainer resources.
The branch-declared checks and workstream validator remain green.

## 2026-09-25 - Opt-in worker Compose activation

The root Compose stack now exposes `strategy-lab-v2-worker` under the explicit
`strategy-lab-v2` profile, leaving the general ARQ worker unchanged. The
profile waits for PostgreSQL/Redis health, mounts a dedicated
`strategy_lab_artifacts` volume, runs with a read-only root, dropped
capabilities, no-new-privileges, and bounded `/tmp`, and binds the local Docker
socket only when the configured socket exists. Its namespaced callback factory
is intentionally empty by default, so enabling the profile without application
terminal/result wiring fails closed at startup rather than silently processing
jobs with incomplete evidence.

`docker compose --profile strategy-lab-v2 config --quiet` passes and the
rendered service contains no provider credentials. Stable Nautilus release
conformance and callback implementation remain separate gates.

## 2026-09-25 - Typed worker dispatch handoff

`worker_handoff.py` now defines the versioned
`strategy-lab.worker-execution-request.v1` envelope. It binds canonical
`WorkerExecutionRequest` bytes to the outer `DispatchPayload` digest, fully
rehydrates nested authorization/admission/runtime/sandbox/engine/worker/lease
contracts through the allowlisted decoder, and exposes an async
`materialize_worker_handoff()` callback adapter. Schema drift, reordered
canonical fields, request-fingerprint drift, and outer-envelope drift fail
closed before process execution.

Focused handoff/process checks pass (7 tests); the complete Strategy Lab v2
package passes 810 tests. Terminal/result evidence resolution remains an
application-owned callback gate.

## 2026-09-25 - Resolver-configured worker callbacks

`worker_callbacks.py` now composes `materialize_worker_handoff()` with the
durable `PostgresWorkerTerminalAdapter`. The opt-in worker loads an explicit
`STRATEGY_LAB_V2_EVIDENCE_RESOLVER` module/attribute factory and fails before
opening Redis when it is missing, malformed, or does not return a callable
resolver. A legacy completion path is retained only as a typed retry guard;
terminal evidence cannot be acknowledged without the durable terminal writer.

The callback package is covered by focused composition tests and the full
branch/coverage gates below. The resolver remains intentionally application
owned: this branch supplies the typed composition boundary, not a guessed
resource lookup or transport-derived evidence implementation.

The environment contract now names the package-owned callback composer as the
default and documents the resolver as the only required application setting.
Malformed module/attribute targets are rejected before callback construction;
the focused callback/handoff suite covers missing, malformed, and valid
resolver configuration.

`PostgresSubmissionDispatchAdapter.load_submission()` now provides the
owner-scoped, authenticated attempt lookup that an application evidence
resolver needs to bind terminal context to a durable `SubmissionReceipt`.
Missing attempts return no record; duplicate attempt bindings and row identity
drift fail closed.

`worker_evidence.py` and
`PostgresStrategyLabV2Persistence.load_worker_terminal_evidence_inputs()` now
compose the authenticated submission, execution outcome/progress context,
rehydrated result manifest, and owner-scoped publication plans for an explicit
application resolver. The bundle preserves missing-state signals and requires
all returned records to retain the same attempt identity and deterministic
publication ordering; it does not pretend those independent reads are one
cross-table transaction.

The worker-facing lookup now derives the owner from the unique durable
submission request fingerprint (`load_submission_binding()`), then performs
owner-scoped evidence reads. If the same request/attempt identity is bound to
multiple owners, the adapter rejects it as ambiguous; no tenant is guessed
from Redis or strategy payload bytes.

## 2026-09-24 - Typed result-manifest rehydration

`postgres_result_materialization.py` now exposes owner-scoped
`load_manifest()` and `load_all_manifests()` reads that fully rehydrate the
authenticated canonical payload into the typed `RunResultManifest` contract.
The decoder is allowlisted to the Strategy Lab contracts, capability, and
rebalance modules; it validates every canonical tag, exact dataclass schema,
enum type, and contract constructor, then verifies manifest, attempt, trial,
metric-set, and snapshot identities against the persisted projection. Artifact
reads now use that validated typed manifest, so nested tampering or contract
drift fails closed rather than being projected through a narrow field parser.

Focused lint and MyPy checks pass; the focused materialization suite passes 5
tests and the complete Strategy Lab v2 package passes 803 tests. Branch validation, exact backend
coverage, cleanup, and the checkpoint push remain to be recorded below.

The corrected focused suite passes 5 tests including authenticated nested-tag
tamper rejection. Branch-declared validation passes all 6 checks (803 package
tests, migration checks, Ruff, MyPy, diff, and workstream validation). The exact
backend gate passes 2,452 tests at 83.68% combined coverage with 86 warnings;
both required cleanup passes retain zero testcontainer sessions, containers,
images, or volumes. The implementation checkpoint and canonical branch push
follow this evidence.

The local checkpoint is complete, but the canonical push could not be completed
from this environment: the configured GitHub SSH key is rejected with
`Permission denied (publickey)`, and the HTTPS retry has no available username
credential. The local tracking ref remains at `c5583f5b8`; no remote state is
claimed beyond that checkout-local reference.

## 2026-09-24 - Canonical result-manifest byte enforcement

The typed result-manifest decoder now requires the decoded contract to
re-serialize to the exact stored canonical bytes. Authenticated rows with
reordered dataclass fields or unsupported nested tags are rejected before
lineage or artifact projection, preserving content-addressed identity rather
than merely accepting semantically equivalent JSON.

Focused lint/MyPy/materialization tests pass (6 tests), and the complete
Strategy Lab v2 package passes 804 tests. Branch and exact-gate evidence for
this follow-up is pending.

Branch-declared validation passes all 6 checks (804 package tests, migration
checks, Ruff, MyPy, diff, and workstream validation). The exact backend gate
passes 2,453 tests at 83.68% combined coverage with 86 warnings; both cleanup
passes retain zero testcontainer sessions, containers, images, or volumes.

## 2026-09-24 - API startup migration rollout

The FastAPI lifespan now invokes the existing idempotent
`StrategyLabV2MigrationService` before provider seeding, scheduling, or API
readiness whenever `STRATEGY_LAB_V2_MIGRATIONS_ENABLED` is enabled. It uses the
sync PostgreSQL URL and repository Alembic path, logs only stable failure
digests, and raises a generic startup failure before accepting work. Compose
enables this setting by default while the documented local `.env.example`
default remains opt-in for test/developer environments; the worker entrypoint
continues to own its independent migration gate.

Focused startup migration tests pass (2), branch validation passes all 6
checks, and the exact backend gate passes 2,455 tests at 83.68% coverage with
86 warnings. Both cleanup passes retain zero testcontainer sessions,
containers, images, or volumes.

## 2026-09-17 - Concrete terminal/result persistence adapter

`worker_terminal_adapter.py` now provides the application-owned terminal
writer over the existing runtime, public outcome/progress, result-completion,
summary, and worker-state adapters. A typed `WorkerTerminalEvidence` resolver
supplies only authenticated principal/submission/result/publication evidence;
the coordinator re-materializes the Nautilus runtime result, applies the pure
terminal and worker-settlement gates, persists the public terminal pair,
finalizes successful result/artifact commits, records the execution summary,
retains a settlement receipt, and atomically releases the worker lease and
serial reservation before returning a Redis acknowledgement digest. Process
timeouts and missing evidence remain pending for recovery; rejected or
contradictory evidence is never acknowledged.

`postgres_worker_settlement.py` and additive migration `ff2a3b4c5d6e` retain
owner-scoped immutable settlement receipts. The coordinator handles the
crash window where that receipt exists before capacity release by rebuilding
the deterministic pure proposal and letting the receipt adapter verify exact
identity. `PostgresWorkerStateAdapter.load_lease()` exposes the authenticated
lease history needed by the writer. The persistence bundle now exposes
`worker_terminal_writer(...)` as the explicit callback factory seam; no
FastAPI, general ARQ worker, Compose, provider, ETF, or TC2000 path was
modified.

Focused terminal/settlement tests passed (9 tests) and the full Strategy Lab v2
package passed 769 tests. Compose activation, stable Nautilus conformance,
upstream contract reconciliation, and full repository integration remain open.

Update this handoff at each coherent boundary.

## 2026-09-17 - Durable resource-creation aggregate bridge

`PostgresStrategyLabV2Adapter.create_resource()` now connects the generic
mutable-resource route to the shared compare-and-set aggregate store. The
application seam normalizes the authenticated owner, derives a stable resource
identity, binds storage request identity to owner/resource/idempotency content,
and persists the mutation fingerprint plus accepted timestamp alongside the
resource envelope. Exact retries reconstruct the original receipt (including
its original acceptance time) after a process restart; changed payloads,
resource collisions, and cross-owner access fail closed without projecting the
foreign document. Domain-specific validation, outbox publication, result
policy, migration startup, worker activation, and stable Nautilus execution
remain separate gates.

Focused application/resource/router tests passed (25 tests). The next
checkpoint must include the full Strategy Lab v2 package, exact backend
coverage, branch validation, and branch-scoped resource cleanup.

## 2026-09-17 - Typed strategy resource registration

`resource_domains.py` now owns the first domain-specific mutation decoder. A
`POST /strategy-lab/v2/strategies` envelope is converted into the immutable
`StrategyVersion` contract before aggregate persistence: source and dependency
digests are validated, exact dependency versions are canonicalized, parameter
maps are frozen, unknown fields are rejected, and conflicting `id`/
`resource_id` aliases fail closed. The normalized strategy fingerprint is
retained in resource metadata and the application bridge continues to provide
owner-bound compare-and-set and exact replay.

Other mutable resource types remain registration-neutral until their domain
adapters are implemented. Focused domain/application/API tests passed (29
tests); Compose activation, stable Nautilus conformance, upstream contract
reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed strategy package resource registration

`resource_domains.py` now extends the application-owned typed mutation boundary
to strategy packages. Source archives and wheels are represented by the
immutable `StrategyPackage` contract: the linked strategy fingerprint, archive,
manifest, and dependency-lock digests, positive archive length,
module-entrypoint, SDK version, and runtime ABI are validated and
canonicalized. Unknown fields and conflicting API ID aliases fail closed, and
the package fingerprint is retained in resource metadata through the same
owner-scoped compare-and-set and exact-replay bridge used for strategies.

Focused package/domain/application tests passed (31 tests); the full Strategy
Lab v2 package passed 788 tests, branch-declared validation passed, and Compose
activation, stable Nautilus conformance, upstream contract reconciliation, and
full repository integration remain open.

## 2026-09-17 - Typed portfolio resource registration

`resource_domains.py` now extends typed mutation validation to portfolio
compositions. The application decodes exact decimal initial capital and
component weights, strategy-linked instrument components, shared risk limits
and product risk models, and optional calendar rebalance policy into the
immutable `PortfolioComposition` contract. Nested unknown fields, invalid
digests/enums/decimals, duplicate or overweight components, and conflicting
API ID aliases fail closed; the portfolio fingerprint is retained in resource
metadata through the existing owner-scoped compare-and-set and exact-replay
bridge.

Focused portfolio/domain/application tests passed (13 tests); the full Strategy
Lab v2 package passed 790 tests. Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain open.

## 2026-09-17 - Typed experiment resource registration

`resource_domains.py` now extends typed mutation validation to experiment
definitions. The application binds portfolio, strategy-version, snapshot, and
capability-contract digests with an integer seed, metric-definition version,
and frozen engine contract through the immutable `ExperimentDefinition`
contract. Strategy fingerprint order is canonicalized; unknown fields,
malformed digest lists, non-integer seeds, invalid engine contracts, and
conflicting API ID aliases fail closed; the experiment fingerprint is retained
in resource metadata through the existing owner-scoped compare-and-set and
exact-replay bridge.

Focused experiment/domain/application tests passed (15 tests); the full
Strategy Lab v2 package passed 792 tests. Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain open.

## 2026-09-17 - Typed run-attempt resource registration

`resource_domains.py` now extends typed mutation validation to run attempts.
Attempt identity, trial linkage, positive ordinal, lifecycle state, and
timezone-aware creation/update timestamps are decoded into the immutable
`RunAttempt` contract; API ID aliases and malformed timestamps/states fail
closed. A stable identity digest excludes mutable timestamps/state while the
normalized lifecycle envelope remains available to the owner-scoped
compare-and-set and exact-replay bridge.

Focused attempt/domain/application tests passed (17 tests); the full Strategy
Lab v2 package passed 794 tests. Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain open.

## 2026-09-17 - Typed data snapshot resource registration

`resource_domains.py` now extends typed mutation validation to frozen data
snapshots. Embedded capability requirements, decisions, degradations, and
preflight fingerprints are rehydrated through the existing fail-closed
capability contracts; each series validates event semantics, UTC coverage
intervals, adjustment/corporate-action policy, provider evidence digest,
content digest, and positive row count. The immutable `DataSnapshot` fingerprint
is retained in resource metadata, with unknown fields, tampered preflight
identity, malformed series, and conflicting API ID aliases rejected before
aggregate persistence.

Focused snapshot/preflight tests passed (14 tests); the full Strategy Lab v2
package passed 796 tests. Compose activation, stable Nautilus conformance,
upstream contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed trial resource registration

`resource_domains.py` now extends typed mutation validation to scientific
trials. It rehydrates the embedded fail-closed preflight report, freezes
parameter/scenario inputs, preserves explicit or derived `TrialRandomization`
provenance, validates optional UTC evaluation windows, and derives the
canonical `ScientificTrial.trial_id` when omitted. Supplied IDs must match the
immutable identity; malformed randomization, unsupported capability reports,
and conflicting API ID aliases fail closed before aggregate persistence.

Focused trial/domain tests passed (16 tests); the full Strategy Lab v2 package
passed 798 tests. Compose activation, stable Nautilus conformance, upstream
contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed metric-set resource registration

`resource_domains.py` now extends typed mutation validation to metric sets.
Metric values validate exact decimal/null semantics, basis, sample size,
annualization and calculation context, nested formula definitions, and
content-addressed evidence references before the immutable `MetricSet`
contract is persisted. Values are canonically ordered by name/basis/unit;
unknown fields, malformed evidence/digests, null values without reasons, and
conflicting API ID aliases fail closed.

Focused metric/domain tests passed (18 tests); the full Strategy Lab v2 package
passed 800 tests. Compose activation, stable Nautilus conformance, upstream
contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed forward-instance resource registration

`resource_domains.py` now completes typed mutation validation for the persisted
forward-instance identity. Portfolio and warm-up snapshot digests, carry-in and
lifecycle state, event progress, correction count, timestamp ordering, and
resource ID aliases are validated through the immutable `ForwardInstance`
contract before persistence. Invalid progress, state, timestamps, digests,
unknown fields, and conflicting aliases fail closed; normalized timestamps are
UTC and the domain fingerprint is content-addressed.

Focused metric/domain tests passed (20 tests); the full Strategy Lab v2 package
passed 802 tests. Compose activation, stable Nautilus conformance, upstream
contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Worker terminal metric-set persistence

The dedicated PostgreSQL worker terminal callback now requires the shared
metrics adapter and persists the successful `RunResultManifest.metric_set`
after result completion. The operation is idempotent and retry-safe, so a crash
between completion and final settlement can replay the exact metric-set record;
metric persistence failures leave the transport entry pending for recovery.

Focused terminal/persistence tests passed (3 tests); the branch-declared suite
passed 802 package tests plus migration, Ruff, MyPy, diff, and workstream checks.
The exact combined backend gate passed 2,451 tests with 83.70% coverage (75%
required); both branch-scoped cleanup passes left no testcontainer sessions.

## 2026-09-17 - Worker terminal result-manifest persistence

The dedicated PostgreSQL worker terminal callback now registers the successful
`RunResultManifest` through the shared result-materialization adapter before
result completion. The manifest remains owner-scoped, attempt-bound,
immutable, and replay-safe; persistence failures leave the transport entry
pending and prevent acknowledgement of an unregistered result. Metric-set
persistence remains the post-completion idempotent step.

Focused terminal/persistence tests passed (3 tests); the branch-declared suite
passed 802 package tests plus migration, Ruff, MyPy, diff, and workstream checks.
The exact combined backend gate passed 2,451 tests with 83.70% coverage (75%
required); both branch-scoped cleanup passes left no testcontainer sessions.

## 2026-09-17 - Executable Nautilus conformance harness

`conformance_fixtures.py` now exposes `execute_conformance_suite(...)`, an
engine-neutral executable fixture boundary. It requires an exact expected
digest for every required conformance check, invokes each check in deterministic
order through an injected runner, canonicalizes the observed JSON-shaped
evidence, and reduces runner exceptions to stable failed observations without
leaking exception text into identities. The returned suite, engine evidence,
and conformance report are bound together and preserve the existing rule that
only a complete passing stable release may be authoritative. No Nautilus import,
provider access, or runtime activation is performed by the package harness.

Focused executable-conformance tests passed (9 tests). Compose activation,
stable Nautilus release/conformance against the real engine, upstream contract
reconciliation, and full repository integration remain open.

## 2026-09-17 - Isolated Nautilus release-pin contract

`conformance.py` now exposes `NautilusReleasePin`, binding the exact v2 package
version/tag, source digest, runtime-image digest, Python and Rust versions, and
explicit isolation from the legacy Nautilus runtime. `EngineConformanceEvidence`
retains that pin and `evaluate_engine_conformance()` reports its validity;
complete fixture coverage without a valid isolated pin remains compatible
evidence but cannot be authoritative. Stable labels with prerelease tags,
shared legacy runtimes, missing pins, and engine-version drift fail the
authority gate while release-candidate evidence remains executable but
non-authoritative.

Focused conformance/publication tests passed (23 tests). Compose activation,
stable Nautilus release/conformance against the real engine, upstream contract
reconciliation, and full repository integration remain open.

## 2026-09-17 - Idempotent resource-creation API boundary

`resource_mutations.py` now provides immutable resource-mutation requests,
receipts, and accept/replay/conflict/reject decisions. The registration-neutral
router adds `POST /strategy-lab/v2/{resource}` for mutable resource types with
strict canonical `attributes`, optional relationship identifiers, bounded JSON
payloads, required `Idempotency-Key`, and 202 resource-document responses.
Artifact and metric-set resources remain read-only through this generic route;
the application adapter still owns domain validation, persistence, outbox
staging, and result-publication policy.

Focused resource-mutation/API tests passed (20 tests). Compose activation,
stable Nautilus release/conformance against the real engine, upstream contract
reconciliation, full persistence-backed mutation flows, and full repository
integration remain open.

## 2026-09-17 - Explicit terminal/result completion context

`worker_service.py` now exposes an optional terminal writer that receives an
immutable `WorkerCompletionContext`: the exact Redis entry, the materialized
`WorkerExecutionRequest`, the `WorkerProcessResolution`, and a UTC observation
time. Its typed `WorkerHandleResult` is used as the completion receipt before
the scheduler can acknowledge the stream entry; the legacy two-argument
completion writer remains supported when no terminal writer is configured.
`WorkerServiceCallbacks` and the local entrypoint accept this optional fourth
callback alongside materialization, completion, and lease heartbeat. This is
the explicit seam for binding `materialize_worker_terminal`, result-completion
publication, and atomic capacity release without placing outcome/metric policy
inside Redis transport.

The focused worker-service/entrypoint tests passed (11 tests); branch
validation passed 764 package tests; and the exact backend gate passed 2,413
tests with 83.76% combined coverage (required threshold: 75%). Branch-scoped
Docker resources were cleaned with no retained testcontainer sessions.
Concrete terminal/result adapter implementations, Compose activation, stable
Nautilus conformance, upstream contract reconciliation, and full repository
integration remain deferred.

## 2026-09-17 - Atomic worker lease/capacity settlement

`PostgresWorkerStateAdapter.release_capacity()` now closes the worker-side
release boundary in one locked transaction. It authenticates the profile,
reservation, lease, and release observation identities; applies the ordered
release observation; compare-and-set updates the lease; and releases the
serial reservation before returning. Exact retries replay both the already
released lease and capacity state, while sequence gaps, foreign attempts,
non-release observations, missing rows, and identity drift fail closed without
partial state. This works for both backtest and forward worker profiles and is
available to the entrypoint's injected completion/recovery callbacks.

The focused PostgreSQL worker-state tests passed (7 tests); branch validation
passed 763 package tests; and the exact backend gate passed 2,412 tests with
83.77% combined coverage (required threshold: 75%). Branch-scoped Docker
resources were cleaned with no retained testcontainer sessions. Concrete
terminal/result callback wiring, Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain deferred.

## 2026-09-17 - Durable lease-heartbeat integration

`worker_service.py` now accepts an optional durable lease-observation writer.
When enabled, one ordered content-addressed heartbeat is emitted at each
configured interval while the fresh serial process runs; the service advances
only on an `APPLY`/exact replay with the expected sequence and leaves the
stream entry pending if persistence rejects or contradicts a heartbeat. The
entrypoint accepts a two- or three-item callback factory result, passes the
third callback through Redis runtime composition, and exposes namespaced
heartbeat interval/extension configuration. Completion persistence and worker
capacity settlement remain authoritative injected adapters, so a heartbeat
failure cannot be acknowledged as a completed dispatch.

The focused worker-service/entrypoint tests passed (10 tests), package Ruff and
MyPy passed, the branch gate passed 761 package tests, and the exact backend
gate passed 2,410 tests with 83.77% combined coverage (required threshold:
75%). Branch-scoped Docker resources were cleaned with no retained
testcontainer sessions. Forward-capacity settlement integration, Compose
activation, stable Nautilus conformance, upstream contract reconciliation,
and full repository integration remain deferred.

## 2026-09-17 - Explicit local worker entrypoint

`worker_entrypoint.py` now owns the local dedicated-worker lifecycle without
touching FastAPI, the general ARQ worker, Compose, or upstream worktrees. The
validated environment contract selects Redis/PostgreSQL, queue/group/consumer
identity, migration target, artifact root, process limits, and an explicit
callback factory. Startup runs the idempotent Alembic service before opening
Redis; a shared PostgreSQL persistence bundle supplies the durable payload
loader; the Redis runtime composes the bounded scheduler and fresh serial
process service; SIGINT/SIGTERM drive an `asyncio.Event`; and Redis is closed
in `finally`. Callback materialization and completion persistence remain
injected so the entrypoint does not invent engine or result-authority policy.

The focused entrypoint tests cover environment validation, callback loading,
migration fail-closed ordering, runtime closure/signal cleanup, and worker
limit composition. Lease-heartbeat integration, forward-worker reservations,
Compose service activation, stable Nautilus conformance, upstream contract
reconciliation, and full repository integration remain deferred.

## 2026-09-17 - Explicit startup migration service

`migration_startup.py` now provides the application-owned Alembic upgrade
seam. It validates PostgreSQL URLs and absolute script locations, executes the
configured target off the event loop, serializes concurrent callers, replays
the exact in-process result, and exposes only stable exception-type digests on
failure. Importing FastAPI or constructing the v2 router remains side-effect
free; the local deployment entrypoint explicitly decides when to invoke it.

The focused migration tests passed (3 tests), with branch and exact backend
validation recorded below. Dedicated worker service activation, stable
Nautilus release/conformance, upstream contract reconciliation, and full
repository integration remain deferred.

## 2026-09-17 - Dedicated worker service composition

`worker_service.py` now composes the authenticated Redis payload loader,
bounded scheduler, fresh serial worker process, and injected durable
completion writer. Each handoff runs off the event loop, and the transport can
acknowledge an entry only after the writer returns a matching receipt. The
Redis runtime exposes this composition without implicitly starting it; a
concrete process entrypoint, lease-heartbeat integration, and Compose service
activation remain deferred.

The focused worker-service/runtime tests passed (9 tests). The full
Strategy Lab v2 package passed 751 tests with Ruff/MyPy green, and the exact
backend gate passed 2,400 tests with 83.78% combined coverage (required
threshold: 75%); branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Migration startup, worker service activation,
upstream contract reconciliation, stable Nautilus activation, and full
repository integration remain deferred.

## 2026-09-17 - Dedicated serial worker process boundary

`worker_process.py` now provides `SerialWorkerProcessExecutor`, which runs
each immutable execution handoff in a fresh `spawn` child process. A one-way
pipe transfers only the typed request and `WorkerExecutionResolution`; the
parent owns join, timeout, termination, and reaping, and child failures are
reduced to stable exception-type digests. The boundary does not acquire
leases, persist state, or run from FastAPI/the general ARQ worker; a concrete
Redis service entrypoint, lease-heartbeat integration, and Compose activation
remain deferred.

The full Strategy Lab v2 package passed 748 tests with Ruff/MyPy green. The
exact backend gate then passed 2,397 tests with 83.77% combined coverage
(required threshold: 75%); branch-scoped Docker resources were cleaned and no
retained testcontainer sessions remain. Migration startup, worker service
activation, upstream contract reconciliation, stable Nautilus activation,
and full repository integration remain deferred.

## 2026-09-17 - Artifact orphan reconciliation and scheduled cleanup

`LocalArtifactStore.cleanup_uncommitted()` now scans only the store's
sharded content-addressed entries and recognized crash-left publication
temporaries. PostgreSQL commit records are authoritative: digest-verified
uncommitted content and aged temporary files are deleted only after an
explicit minimum-age guard, while committed/fresh/unknown entries remain
untouched. Deletions fsync their shard directory and every result is returned
as deterministic audit evidence.

`LocalArtifactCleanupService` and `ArtifactCleanupScheduler` expose the
application and bounded periodic seams over the same persistence bundle. The
scheduler uses an injected clock/sleep, supports explicit cancellation and a
test cycle cap, and does not start workers or hide cleanup failures.

The full Strategy Lab v2 package passed 744 tests with Ruff/MyPy green. The
exact backend gate then passed 2,393 tests with 83.76% combined coverage
(required threshold: 75%); branch-scoped Docker resources were cleaned and no
retained testcontainer sessions remain. Isolated worker process/runtime
execution, migration startup, upstream contract reconciliation, stable
Nautilus activation, and full repository integration remain deferred.

## 2026-09-17 - Artifact path-integrity regression hardening

`LocalArtifactStore` now rejects broken target symlinks before treating a
content address as missing. The existing fail-closed path and digest checks
therefore cover both live and dangling symlink escapes, with a regression test
at the latest exact branch tip.

The full Strategy Lab v2 package remains at 739 passing tests; the exact
backend gate passed 2,388 tests with 83.75% combined coverage (required
threshold: 75%). Branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Isolated worker process/runtime execution,
migration startup, orphan/scheduled artifact cleanup, upstream contract
reconciliation, and stable Nautilus activation remain deferred.

## 2026-09-17 - Cancellable worker scheduling

`RedisDispatchWorkerScheduler` now runs one bounded Redis worker-pump cycle at
a time until an explicit stop signal or test cycle cap. Interval values are
finite and positive, sleep is injected for deterministic control, and callers
can select the authenticated durable-payload materializer before their
two-argument handler runs. `RedisDispatchRuntime.worker_scheduler()` exposes
the same composition on the application-owned Redis lifecycle; it does not
start a process, claim a lease, invoke Nautilus, or hide handler failures.

The full Strategy Lab v2 package passed 739 tests with Ruff/MyPy green. The
exact backend gate then passed 2,388 tests with 83.75% combined coverage
(required threshold: 75%); branch-scoped Docker resources were cleaned and no
retained testcontainer sessions remain. Isolated worker process/runtime
execution, migration startup, orphan/scheduled artifact cleanup, upstream
contract reconciliation, and stable Nautilus activation remain deferred.

## 2026-09-17 - Retention-authorized artifact byte lifecycle

`artifact_store.py` now exposes a guarded `collect()` operation that verifies
manifest-bound bytes and an authenticated `ArtifactRetentionResolution` before
deleting content. Only `TIER_ELIGIBLE` or `EXPIRE_ELIGIBLE` resolutions may
remove bytes; pinned/permanent/not-yet-eligible content is reported retained,
missing content is idempotent, and digest/path corruption fails closed with a
directory fsync after deletion. `LocalArtifactRetentionService` evaluates the
existing PostgreSQL retention adapter at an explicit instant before collection,
and both the standalone and shared-persistence factories expose this wiring.

Focused artifact/application/persistence tests passed (13 tests), and the full
Strategy Lab v2 package passed 737 tests with Ruff/MyPy green. The exact
backend gate then passed 2,386 tests with 83.75% combined coverage (required
threshold: 75%); branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Orphan discovery, scheduled cleanup, migration
startup, worker process/runtime execution, upstream contract reconciliation,
and stable Nautilus activation remain deferred.

## 2026-09-17 - Durable dispatch-payload materialization

`dispatch_payload.py` now defines immutable canonical payload records with
byte-length and decoded-content authentication. The additive
`ff1a2b3c4d5e` migration creates a content-addressed PostgreSQL payload table;
submission receipt, dispatch intent, payload bytes, and execution outbox are
staged in one transaction, with shared-payload deduplication and tamper
rejection. `PostgresSubmissionDispatchAdapter.load_payload()` is the
worker-facing lookup surface, and `RedisDispatchWorker.handle_materialized_once()`
resolves that record by stream digest before invoking a handler. Missing or
malformed records stay unacknowledged for retry/poison-message policy.

Focused payload/submission/worker/migration tests passed (18 tests), the full
Strategy Lab v2 package passed 734 tests, and Ruff/MyPy were green. The exact
backend gate then passed 2,383 tests with 83.74% combined coverage (required
threshold: 75%); branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Worker process/runtime execution, migration
startup, artifact byte/retention lifecycle, upstream contract reconciliation,
and stable Nautilus activation remain deferred.

## 2026-09-17 - Atomic submission-to-outbox staging

`postgres_submission.py` now binds each accepted API submission to the shared
`strategy_lab_v2_execution_outbox` in the same PostgreSQL transaction as its
owner-scoped receipt and dispatch intent. The outbox request/event identities
are derived from both owner and request content, preventing cross-owner
collisions while preserving idempotent retries. Missing dispatch or outbox rows
are repaired on replay; contradictory durable content fails with a typed
idempotency conflict. The existing Redis relay can therefore observe API
submissions as authoritative pending work.

The full declared branch suite passed 729 Strategy Lab v2 tests plus the
migration structural test, Ruff, MyPy, diff, and workstream validation. The
exact-worktree backend gate passed 2,377 tests with 83.77% combined coverage
(required threshold: 75%), and branch-scoped Docker resources were cleaned
afterward. Worker payload materialization, isolated execution, and stable
Nautilus activation remain deferred.

## 2026-09-17 - Application-owned Redis runtime lifecycle

`redis_application.py` now owns the concrete Redis boundary without leaking a
client dependency into the engine-neutral transport. `RedisDispatchRuntime`
validates explicit `redis://`/`rediss://` URLs, constructs a text-decoding
`redis.asyncio` client, composes outbox-relay and bounded worker-pump factories,
and closes the client idempotently. Connection health checks, process/task
lifecycle, migration startup, and worker execution remain caller-owned.

The full Strategy Lab v2 package passed 729 tests with Ruff and MyPy green. The
exact-worktree backend gate passed 2,377 tests with 83.77% combined coverage
(required threshold: 75%), and branch-scoped Docker resources were cleaned
afterward. Production worker activation and stable Nautilus execution remain
deferred.

## 2026-09-17 - Bounded outbox relay scheduling

`outbox_application.py` now includes `OutboxRelayScheduler`, an application
owned loop that executes bounded relay cycles at an injected clock instant and
stops on an explicit cancellation event. Interval and batch limits are finite
and validated; clock/sleep injection keeps scheduling deterministic in tests,
while the underlying Redis enqueue and PostgreSQL acknowledgement remain
idempotent and authoritative respectively. Redis client construction and
process lifecycle are still caller-owned.

The full Strategy Lab v2 package passed 727 tests with Ruff and MyPy green.
The exact-worktree backend gate passed 2,375 tests with 83.78% combined coverage
(required threshold: 75%), and branch-scoped Docker resources were cleaned
afterward. Production Redis lifecycle, migration startup, worker entrypoints,
isolated execution, and stable Nautilus activation remain deferred.

## 2026-09-17 - Owner-scoped artifact resource projection

`postgres_result_materialization.py` now exposes authenticated artifact
references by narrowly decoding the tagged canonical `output_artifacts` field
from each retained result manifest. The decoder rejects malformed envelopes,
duplicate/missing fields, wrong tags, and non-canonical integers before
rebuilding immutable `ArtifactManifest` values. `persistence.py` projects those
references into deterministic `/artifacts` resources, deduplicating shared
content digests while retaining manifest, attempt, and trial provenance plus
attempt relationships; owner scoping remains inherited from the manifest
adapter.

The focused result-materialization/persistence suite passed 5 tests, the full
Strategy Lab v2 package passed 725 tests, and Ruff/MyPy were green. The exact
worktree backend gate passed 2,373 tests with 83.77% combined coverage (required
threshold: 75%), and branch-scoped Docker resources were cleaned afterward.
Artifact-byte reads, retention/pin projections, migration startup, worker
scheduling, and stable Nautilus execution remain deferred.

## 2026-09-17 - PostgreSQL outbox to Redis relay

`postgres_event_transaction.py` now exposes an authenticated complete-outbox
reader and compare-and-set publication acknowledgement. The new
`outbox_application.py` composes that authoritative persistence surface with
`RedisDispatchTransport`: each bounded relay cycle selects currently available
messages, safely enqueues or replays them by semantic identity, and only then
marks the PostgreSQL row published with its state fingerprint. A crash or lost
acknowledgement leaves the row pending for idempotent retry; Redis remains
transport-only. The shared persistence bundle exposes the relay factory.

The focused outbox/event/persistence tests passed 8 tests; the branch-declared
checks passed 725 Strategy Lab v2 tests plus the migration structural test,
Ruff, MyPy, `git diff --check`, and workstream validation. The exact-worktree
backend gate passed 2,373 tests with 83.80% combined coverage (required
threshold: 75%), and branch-scoped Docker resources were cleaned afterward.
Worker-pump scheduling, production Redis client lifecycle, migration startup,
application activation, isolated workers, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Relational API resource projections

`postgres_resources.py` now supports application-owned projection loaders in
addition to the aggregate store. `persistence.py` registers authenticated
PostgreSQL projections for attempts (latest execution summaries), metric sets,
and forward instances; each is converted into the immutable REST resource
envelope with a canonical revision digest. Projection collections retain
deterministic ordering, duplicate-ID rejection, cursor snapshot binding, and
owner scoping, while strategy/package/portfolio/snapshot/experiment/trial
resources continue through the aggregate projection path. Focused projection,
application, and persistence tests plus the branch and exact coverage gates are
green. Remaining resource projections, migration startup, worker scheduling,
and runtime activation remain deferred.

## 2026-09-17 - Forward-instance collection read surface

`postgres_forward_state.py` now exposes `load_all(principal=...)`, returning
every owner-scoped `ForwardInstance` in stable instance-id order. The query
reuses the checkpoint decoder and authenticates owner, instance, instance
fingerprint, and checkpoint fingerprint for every row before returning it, so
future `/forward-instances` pagination cannot disclose another owner or accept
tampered state. Focused tests cover multiple-instance ordering and owner
isolation; the full branch and exact coverage gates are green. Resource-route
projection, startup migration, worker scheduling, and runtime activation remain
deferred.

## 2026-09-17 - Shared PostgreSQL persistence bundle

`backend/app/strategy_lab_v2/persistence.py` now owns construction of the
complete registration-neutral PostgreSQL v2 adapter graph over one async session
factory. The bundle shares the aggregate store with resource reads and the
execution-state context with command receipts, while exposing acquisition,
coverage, capability, forward/search, runtime/result, artifact, lineage, and
worker-state adapters for subsequent application and worker slices.
`application.py` consumes the bundle for its initial authenticated API seam and
keeps the existing private aliases for compatibility. Artifact publication can
be created from the same graph with an explicit local/NAS-mountable root.
Focused application/persistence tests, Ruff, MyPy, and the complete branch test
collection are green. API projection completion, migration startup, worker
scheduling/activation, and stable Nautilus execution remain deferred.

## 2026-09-17 - Local artifact publication application wiring

`backend/app/strategy_lab_v2/artifact_application.py` now composes the
immutable `LocalArtifactStore` with `PostgresArtifactCommitAdapter`. Publication
verifies the manifest bytes, uses the store's atomic create-if-absent/reuse
behavior, and finalizes the matching commit ledger record with explicit
committed/replayed/rejected evidence. A factory accepts an explicit artifact
root so a later Compose/NAS volume can be selected without a hidden host path.
Focused tests cover first publication, exact replay/deduplication, rejection
before commit, and factory composition. Crash-orphan reconciliation,
retention/pinning coordination, result-completion wiring, worker activation,
and startup configuration remain deferred.

## 2026-09-17 - Initial authenticated API/application wiring

`backend/app/strategy_lab_v2/application.py` now composes the existing
`get_current_user` dependency and `AsyncSessionLocal` with the additive
PostgreSQL resource, submission/dispatch, execution-state, and command
adapters. Integer-backed ORM user IDs are normalized once at the application
boundary to the opaque string owner keys used by the engine-neutral contracts.
`backend/app/main.py` registers the resulting router additively at
`/api/v1/strategy-lab/v2`; the legacy Strategy Lab router remains unchanged.
Focused application tests cover identity normalization, adapter composition,
and the versioned route factory. Remaining resource projections, startup
migration rollout, worker scheduling/activation, and stable Nautilus execution
remain deferred integration gates.

## 2026-09-17 - Additive Strategy Lab v2 schema migration

Alembic revision `ff0a1b2c3d4e_add_strategy_lab_v2_storage.py` now creates the
complete additive schema consumed by the registration-neutral PostgreSQL v2
adapters: aggregate/storage receipts, submissions and dispatch, execution and
audit/outbox state, forward state and replays, runtime/outcome/progress/result
records, search/capability/coverage/acquisition projections, artifact lineage,
retention and commits, legacy imports, and worker profiles/reservations/leases.
It also creates the partial unique index that enforces one active reservation
per worker/attempt. Offline Alembic rendering, migration graph, Python compile,
and Ruff validation are green; legacy Strategy Lab tables are untouched.
Application startup migration execution, authentication, route registration,
worker activation, and stable Nautilus execution remain deferred.

## 2026-09-17 - Restricted strategy invocation runner

The new owned `backend/strategy_runtime/` package executes one strategy event
inside the already-hardened worker boundary. It verifies the source digest
against the immutable SDK manifest, repeats static source preflight, executes
with a restricted builtin/import surface, injects only engine-neutral SDK
symbols, and validates emitted intents against declared instrument scope and
per-event limits. Source/entrypoint/output failures return typed,
content-addressed evidence without exposing exception text. Four focused tests
cover success, digest/static rejection, typed failures, and import restriction;
the full package suite now passes 627 tests with Ruff and MyPy. Docker image,
worker entrypoint, and application wiring remain deferred shared integration
gates.

## 2026-09-17 - Strategy runtime wire protocol and CLI

`backend/strategy_runtime/protocol.py` now defines a canonical, versioned JSON
envelope for mounted invocation requests and typed results. It preserves
Decimal/datetime/date/float and collection values, reconstructs the immutable
engine-neutral SDK records, encodes only typed order/target-position intents,
and verifies the result content fingerprint on decode. The package CLI
(`python -m strategy_runtime --request <absolute-path> --result <absolute-path>`)
invokes one event in the already-isolated process, atomically publishes the
result file, returns `0` for success, `2` for typed rejection/failure, and `1`
for malformed input or output setup without printing strategy exception text.
The focused runtime/protocol suite passes 9 tests; worker image wiring,
container activation, and application scheduling remain deferred shared gates.

## 2026-09-17 - Stateful strategy runtime session checkpoint

`StrategyInvocationSession` now loads one source-bound strategy instance for an
entire worker lifetime instead of rebuilding the strategy for every event. It
revalidates manifest scope for direct typed contexts, preserves state across
monotonically advancing events, pins random-seed and parameter identity, and
turns context drift or a terminal strategy error into deterministic typed
evidence. The existing one-event API remains a compatibility wrapper over a
fresh session, while the mounted CLI continues to execute one request/event.

The complete Strategy Lab v2 package passed 655 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The Docker-backed combined
coverage gate passed 2,302 tests with 83.61% total coverage (required threshold:
75%); setup and cleanup completed successfully. Worker image/entrypoint,
application scheduling, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Deterministic frozen-tape replay checkpoint

`backend/app/strategy_lab_v2/replay.py` now builds one typed SDK context for
each same-time batch in a bound frozen tape. Histories are truncated to each
dependency's declared lookback, optional position snapshots are keyed to batch
sequences, and the replay adapter invokes one stateful strategy session in
chronological order. Snapshot/manifest binding is repeated at the execution
boundary; tape, binding, source, parameters, and typed invocation outcomes are
retained as content-addressed provenance. Replays stop at the first typed
rejection or failure and never apply intents or model fills.

The exact Strategy Lab package gate passes 659 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The combined Docker-backed
coverage gate is the remaining validation step for this checkpoint; worker
image/entrypoint, application scheduling, migrations, upstream reconciliation,
and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Stateful batch runtime wire checkpoint

The runtime now exposes `run_strategy_events()` as a reusable primitive that
creates one `StrategyInvocationSession`, invokes a non-empty context sequence,
and stops at the first typed rejection or failure. The versioned protocol adds
strict batch request and result envelopes with typed context reconstruction,
per-invocation fingerprints, duplicate/non-finite JSON rejection, and an
independently verified batch fingerprint. This lets a future isolated worker
retain strategy state over a frozen replay while preserving the existing
single-event CLI contract.

The exact Strategy Lab package gate passes 661 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The combined Docker-backed
coverage gate remains the repository-level validation step for this checkpoint;
worker image/entrypoint, application scheduling, migrations, upstream
reconciliation, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Stateful batch runtime CLI checkpoint

`python -m strategy_runtime` now detects the strict batch request envelope while
retaining the existing single-event path. Batch requests are reconstructed into
typed contexts, executed through one `StrategyInvocationSession`, and published
atomically as a fingerprinted batch-result envelope. A non-successful typed
invocation returns exit status 2; malformed input or output setup remains exit
status 1, and no strategy exception text crosses the process boundary.

The focused CLI/protocol tests pass, with the complete branch gate and
Docker-backed combined coverage gate recorded below after this exact-tip
checkpoint. Worker image/entrypoint, application scheduling, migrations,
upstream reconciliation, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Manifest-bound runtime result provenance

`StrategyInvocationResult` now carries the SDK manifest fingerprint used during
source loading, context admission, and intent validation. The single and batch
JSON result envelopes preserve and validate this identity, so a host adapter can
bind returned intents to the exact immutable strategy contract rather than
trusting source/context digests alone. Existing single-event and batch callers
remain compatible through the updated typed protocol constructors.

The full Strategy Lab package gate passes 665 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The Docker-backed combined
coverage gate passes 2,312 tests with 83.62% total coverage (required threshold:
75%); setup and cleanup completed successfully. Worker image/entrypoint,
application scheduling, migrations, upstream reconciliation, and authoritative
Nautilus execution remain deferred.

## 2026-09-17 - Typed strategy-validation request metadata errors

The registration-neutral strategy-validation route now catches malformed or
overlong `X-Request-ID` values and returns the same typed validation envelope
used by the other v2 routes. Invalid request metadata therefore cannot escape
before raw-body validation and static source preflight, while valid request IDs
and existing 422 body errors remain unchanged.

The focused API-router suite passes 13 tests and the complete Strategy Lab v2
package passes 693 tests with Ruff and MyPy green. The exact-worktree combined
coverage gate passes 2,340 tests with 83.71% total coverage (required
threshold: 75%); Docker services were branch-scoped and cleaned afterward.
Authentication, application registration, and shared persistence remain
deferred behind the existing gates.

## 2026-09-17 - Bounded strategy-runtime wire payloads

The restricted runtime protocol now rejects inbound single, batch, and result
envelopes larger than 16 MiB before JSON decoding. This bounds mounted request
parsing independently of the sandbox's memory and output limits while leaving
valid typed envelopes and the existing atomic CLI publication behavior intact.

The focused runtime protocol suite passes 12 tests and the complete Strategy
Lab v2 package passes 694 tests. The exact-worktree combined coverage gate
passes 2,341 tests with 83.71% total coverage (required threshold: 75%); Docker
services were branch-scoped and cleaned afterward. Worker image activation,
application wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Attempt and lease temporal identities

`RunAttempt` creation/transition timestamps and `ExecutionAttemptLease`
acquisition, heartbeat, expiry, and release timestamps now normalize aware
offsets to UTC during immutable construction. Retry lineage and worker-capacity
comparisons therefore remain stable across offset-changing persistence or
transport boundaries. Attempt/lease regression coverage is green and the
complete Strategy Lab v2 package passes 712 tests; persistence migration,
worker activation, application wiring, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Bounded mounted runtime request reads

Both mounted strategy and custom-metric CLIs now read request files through a
bounded binary reader, consuming at most the 16 MiB wire limit plus one byte
before strict UTF-8 decoding. Oversized files therefore fail before an
unbounded `read_text()` allocation can bypass the protocol decoder guard, while
valid single and batch requests retain their existing atomic result publication.
Regression coverage verifies that neither CLI publishes a result for an
oversized request. The focused runtime/custom-metric protocol suite passes 23
tests, and the complete Strategy Lab v2 package passes 696 tests; worker image
activation, application wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Deterministic sandbox start-failure evidence

Sandbox process-start failures now publish a versioned digest of the fully
qualified exception type instead of hashing the OS error string. Host-specific
paths and launcher details therefore cannot create divergent run identities or
leak through evidence, while timeout and output-limit evidence remains unchanged.
Regression coverage confirms two different missing launch paths produce the same
typed start-failure digest. The package and exact-worktree coverage gates remain
green; worker activation, application wiring, and stable Nautilus execution
remain deferred.

## 2026-09-17 - Forward observation admission integrity

Forward live admission now validates the shape of every event observation and
recomputes its expected disposition from the persisted cursor before applying
state. Forged accepted observations cannot skip sequence gaps, non-accepted
observations cannot move the cursor, and missing bounds/buffering/replay flags
are checked against their disposition. Buffered event IDs are content-bound on
first receipt, so a changed retry conflicts instead of replacing the buffered
event. Focused forward admission/transaction/dispatch/correction tests pass 27
tests and the complete package gate passes 698 tests; persistence, canonical
event-stream wiring, worker activation, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Bounded runtime wire serialization

The canonical strategy and custom-metric protocol serializers now enforce the
same 16 MiB UTF-8 byte limit used by inbound decoders for single and batch
request/result envelopes. Oversized generated payloads fail before a mounted
artifact is emitted, while canonical ordering and typed fingerprints remain
unchanged. Focused runtime protocol coverage passes 23 tests and the complete
Strategy Lab v2 package passes 700 tests; worker activation, application
wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Canonical forward event-time identities

`CanonicalForwardEvent` and `ForwardCursor` now normalize every aware
`event_time`, `arrived_at`, and cursor timestamp to UTC during construction.
Offset-equivalent canonical events therefore compare and fingerprint
identically, preventing false content conflicts and replay divergence at the
forward boundary. Focused forward lifecycle/admission coverage passes 28 tests
and the complete Strategy Lab v2 package passes 701 tests; persistence migration,
event-stream wiring, worker activation, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Forward lifecycle temporal identities

Forward instance `created_at`/`updated_at`, warm-up receipt `completed_at`,
correction command `requested_at`, and counterfactual replay-plan `planned_at`
now normalize aware offsets to UTC during immutable construction. Restart,
warm-up, and correction records therefore retain one identity for equivalent
instants regardless of transport offset formatting. Regression coverage adds
three identity tests; the complete Strategy Lab v2 package passes 704 tests.
Persistence migration, event-stream wiring, worker activation, and stable
Nautilus execution remain deferred.

## 2026-09-17 - Execution lifecycle temporal identities

Asynchronous submission and admission receipts, strategy-runtime requests and
updates, execution outcomes and progress, retry/cancellation commands,
authorization records, and execution-summary projections now normalize aware
timestamps to UTC during immutable construction. Equivalent instants therefore
retain one retry and read-model identity through the complete local execution
handoff. Focused lifecycle coverage passes 50 tests and the complete Strategy
Lab v2 package passes 711 tests; persistence migration, worker activation,
application wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Runtime wire source-binding hardening

Single and batch invocation serializers and decoders now verify that the source
bytes match the SDK manifest's declared source digest. Contradictory envelopes
are rejected at the wire boundary, before a mounted bundle or strategy session
can be created. Regression coverage includes both serializer-side mismatch and
tampered single/batch payloads.

The full Strategy Lab package gate passes 665 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The Docker-backed combined
coverage gate passes 2,312 tests with 83.62% total coverage (required threshold:
75%); setup and cleanup completed successfully. Worker image/entrypoint,
application scheduling, migrations, upstream reconciliation, and authoritative
Nautilus execution remain deferred.

## 2026-09-17 - Deterministic runtime identity hardening

The strategy runtime wire protocol now normalizes every timezone-aware
timestamp to UTC before serialization and after decoding. Equivalent instants
therefore produce byte-identical single and batch envelopes even when callers
use different source offsets. Failure evidence is now bound to a versioned,
fully-qualified exception type only; private exception text, strategy data, and
process-specific object representations cannot change the published digest.

The focused runtime/protocol tests pass, with the complete branch gate and
Docker-backed combined coverage gate recorded below after this exact-tip
checkpoint. Worker image/entrypoint, application scheduling, migrations,
upstream reconciliation, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Strict strategy-runtime batch chronology

Batch invocation envelopes and the direct `run_strategy_events()` primitive now
preflight strict `(event_time, event_sequence)` ordering before a strategy
session can execute. Duplicate or out-of-order contexts therefore fail as a
typed malformed batch at the serializer/decoder or direct-call boundary instead
of partially invoking a stateful strategy and returning a late monotonic
rejection. The existing single-event API and valid chronological batches are
unchanged.

The focused runtime/protocol suite passes 18 tests and the complete Strategy
Lab v2 package passes 692 tests with Ruff and MyPy green. The Docker-backed
combined coverage gate passes 2,339 tests with 83.71% total coverage (required
threshold: 75%) when run directly from this exact worktree; the first Makefile
wrapper attempt incorrectly collected the provider-platform checkout and is
recorded as a non-authoritative cross-worktree failure. Worker image/entrypoint,
application scheduling, migrations, upstream reconciliation, and authoritative
Nautilus execution remain deferred.

## 2026-09-17 - Replay-safe wall-clock preflight hardening

Static strategy validation now rejects wall-clock method references at the
attribute-access site as well as direct calls. This closes the aliasing escape
where a strategy could bind `datetime.now`/`date.today`/`utcnow` first and call
the alias later, preserving deterministic replay requirements. A regression
test covers the aliased method form; the exact package suite passes 633 tests,
with Ruff, MyPy, branch checks, and Docker-backed combined coverage also green.

## 2026-09-17 - Canonical runtime JSON integrity hardening

Runtime envelope decoding now rejects duplicate JSON object fields and
non-standard `NaN`/`Infinity` constants before any manifest, context, or result
record is reconstructed. This keeps serialized identities unambiguous and
preserves the finite-number guarantees of the engine-neutral SDK. Five focused
protocol tests cover canonical round trips, fingerprint tampering, unknown
fields/versions, duplicate fields, and non-finite constants; the exact package
suite remains green at 633 tests and the Docker-backed gate remains green at
2,280 tests with 83.54% coverage.

## 2026-09-17 - Module-introspection preflight hardening

The restricted source preflight now rejects module-introspection attributes
such as `sys`, `modules`, `environ`, and `builtins`, along with private
attributes generally. This closes the public-attribute escape exposed by
allowed modules such as `typing` (`typing.sys`) while preserving the intended
engine-neutral SDK surface. A regression test covers the allowed-module case;
the exact package suite passes 634 tests and the Docker-backed gate passes
2,281 tests with 83.54% coverage.

## 2026-09-17 - Private import-form hardening

Import validation now applies the same private/introspection policy to every
syntax form: dotted imports, `from ... import ...`, aliases, and star imports.
This prevents allowed-module private bindings such as `from collections import
_sys` (or direct `sys` bindings from an allowed module) from bypassing the
attribute checks. The exact package suite passes 635 tests; the Docker-backed
gate passes 2,282 tests with 83.55% coverage.

## 2026-09-17 - Engine-neutral SDK boundary hardening

`sdk.py` now validates public input types before dereferencing them: manifests
must contain typed strategy/dependency records, market events and context maps
are immutable typed mappings, positions require finite Decimal values, and order
intents require the declared enum types. The context builder repeats event
shape checks before applying dependency lookback/field rules, preventing
malformed values from crossing into strategy code. Eight focused malformed-input
assertions were added; the package suite passes 623 tests with Ruff and MyPy.
This remains package-only and does not alter the shared runtime, router,
migration, worker, provider, ETF, TC2000, Compose, or Nautilus paths.

## 2026-09-17 - Paired-inference scope reconciliation

The durable plan and documentation now distinguish the implemented bounded
exact paired sign-flip inference from intentionally out-of-scope
approximate/bootstrap inference and inferential ranking. The canonical feature
ref `origin/feat/strategy-lab-v2` is synchronized at the session checkpoint;
an accidental duplicate hyphenated remote ref was removed. No shared provider,
ETF, TC2000, migration, router, worker, Compose, or Nautilus path was changed.

## 2026-09-17 - Trusted paired-inference checkpoint

`paired_inference.py` now provides a bounded, deterministic exact two-sided
sign-flip test for the mean of aligned metric deltas. It requires the existing
verified keyed-stream pairing receipt, sorts and content-addresses observation
keys, records the exact tail/permutation counts and statistical assumptions,
and exposes a versioned `calculate_paired_inference_metrics()` projection.
Requests above the configured 20-observation exact-enumeration bound return
typed unavailable evidence rather than silently using an approximate or
unseeded method. This is statistical evidence only and does not issue a
profitability verdict; migrations, API wiring, workers, and stable Nautilus
execution remain separate gates.

The focused inference suite passes 4 tests; the full package suite passes 622
tests with Ruff and MyPy. Combined coverage is 2,269 backend tests at 83.51%,
and all five exact-tip branch checks pass.

## 2026-09-17 - Durable metric-set checkpoint

`postgres_metrics.py` now retains immutable `MetricSet` summaries as
owner-scoped canonical projections. Full metric-set payloads and compact value
summaries are content-addressed; one attempt cannot silently replace a prior
metric set, exact retries replay, and payload/record tampering is detected
before metric data can be read by later result/API adapters. Metric calculation,
artifact bytes, migrations, authorization, and application wiring remain
separate integration gates.

The focused metric persistence suite passes 3 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable runtime-receipts checkpoint

`postgres_runtime_receipts.py` now retains immutable strategy-runtime request
and isolation-preflight evidence as owner-scoped canonical projections. Request
and preflight payloads carry independent content-addressed identities; exact
retries replay, changed content conflicts against the same attempt/request, and
rejected preflight reasons remain inspectable without exposing secrets or
starting a process. The adapter is registration-neutral and does not mutate
runtime execution state; process execution, migrations, authorization, and
application wiring remain open gates.

The focused runtime-receipts suite passes 4 tests. Package/static and combined
coverage evidence will be recorded after this boundary is committed and rerun;
upstream reconciliation and stable Nautilus execution remain open gates.

## 2026-09-17 - Durable result-manifest checkpoint

`postgres_result_materialization.py` now retains immutable `RunResultManifest`
values as owner-scoped canonical JSON projections. Pure manifest validation is
run before registration; one attempt binds to one manifest identity, exact
retries replay, changed candidates conflict, and payload plus record
fingerprints are authenticated on every read. The adapter exposes the compact
identity projection for later API reads without attempting nested contract
decoding, and does not write artifact bytes or publish official results.

The focused result-manifest persistence suite passes 4 tests; the exact package
suite passes 611 tests with Ruff and MyPy, all 5 branch-declared checks pass,
and the Docker-backed combined gate passes 2,258 backend tests at 83.44%
coverage. Upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable runtime-execution checkpoint

`postgres_runtime_execution.py` now maps accepted `RuntimeExecutionState`
values and immutable `RuntimeExecutionUpdate` receipts to owner-scoped additive
PostgreSQL tables. Initialization is idempotent, every update is resolved by
the pure monotonic runtime contract and committed with a compare-and-set state
write, and exact sequence/fingerprint retries replay while conflicting content
is rejected. Sandbox result materialization verifies request/plan evidence and
commits running plus terminal receipts atomically, preserving bounded output or
typed failure identity for restart recovery. Process execution, artifact bytes,
migrations, authorization, and official result publication remain separate
integration gates.

The focused runtime persistence suite passes 5 tests in addition to the
existing runtime contract coverage; its exact package suite passed 607 tests,
all 5 branch-declared checks passed, and the Docker-backed combined gate passed
2,254 backend tests at 83.42% coverage. Upstream reconciliation and stable
Nautilus execution remain open gates.

## 2026-09-17 - Durable result-publication checkpoint

`postgres_result_publication.py` now maps immutable publish/replay/reject
`ResultPublicationPlan` values to an owner-scoped additive PostgreSQL evidence
table. Plan fingerprints, attempt/result/reproduction/build identities, and
deterministic rejection reasons are authenticated on reads; exact retries
replay while changed decisions remain separate immutable audit evidence. The
adapter does not publish bytes, coordinate completion, apply migrations, or
register authorization and routes.

The focused result-publication-adapter suite passes 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable result-completion checkpoint

`postgres_result_completion.py` now maps terminal result completion and the
shared content-addressed artifact commit ledger to one additive PostgreSQL
transaction. It locks and authenticates both ledgers, delegates terminal
runtime/outcome/progress/publication and artifact-plan validation to
`finalize_execution_result()`, then inserts all new artifact commits and the
owner-scoped completion receipt atomically. Exact retries replay the stored
completion; artifact conflicts or rejected terminal evidence leave both ledgers
unchanged. Artifact bytes, migrations, authorization, and worker/application
wiring remain outside this registration-neutral adapter.

The focused result-completion-adapter suite passes 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable execution-summary checkpoint

`postgres_execution_summary.py` now maps immutable `ExecutionSummary`
projections to an owner-scoped additive PostgreSQL read model. Each
submission/attempt outcome-progress state identity is append-only and
fingerprint-authenticated; exact retries replay, changed content for an
existing checkpoint conflicts, and latest-attempt reads retain deterministic
history without overwriting prior status. Error payloads and timezone-aware
timestamps are encoded and revalidated on every read. Submission/outcome
state wiring, result publication, migrations, authorization, API registration,
and worker integration remain outside this adapter.

The focused execution-summary-adapter suite passes 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable snapshot-coverage checkpoint

`postgres_snapshot_coverage.py` now maps snapshot-level verified/rejected
coverage resolutions to an owner-scoped additive PostgreSQL table. Per-series
reports, missing/unexpected series digests, rejection reasons, and the complete
resolution fingerprint are authenticated on reads; exact retries replay while
changed resolutions conflict. Provider fetch/repair, attestation lookup,
snapshot creation, execution admission, shared migrations, authorization, and
application wiring remain outside this adapter.

The focused snapshot-coverage-adapter suite passed 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable acquisition-receipt checkpoint

`postgres_acquisition.py` now maps provider-produced acquisition receipts to an
owner-scoped additive PostgreSQL handoff registry keyed by the preflight request
identity. Snapshot, provider-snapshot, coverage-resolution, and opaque provider
receipt digests are authenticated before reuse; exact retries replay while
changed handoffs conflict. Provider fetching/repair, snapshot creation,
execution admission, shared migrations, authorization, and application wiring
remain outside this adapter.

The focused acquisition-adapter suite passed 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable capability-summary checkpoint

`postgres_capability.py` now maps immutable data/engine capability summaries to
an owner-scoped additive PostgreSQL read model keyed by report and binding
identity. Gaps, degradations, executable/ranking flags, and authoritative
publication eligibility are serialized and re-authenticated; exact retries
replay while a changed projection for the same preflight identities conflicts.
Capability calculation, provider entitlements, engine registration, shared
migrations, authorization, and API wiring remain outside this adapter.

The focused capability-adapter suite passed 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable coverage-attestation checkpoint

`postgres_coverage.py` now maps provider-supplied coverage attestations to an
owner-scoped additive PostgreSQL evidence registry. Series/evidence digests,
interval, row-count, adjustment/session/feed semantics, and attestation
fingerprints are authenticated on reads; exact registration retries replay,
changed series content conflicts, and deterministic owner listings support the
later snapshot-coverage admission flow. Provider fetching/repair, snapshot
admission, shared migrations, authorization, and application wiring remain
outside this registration-neutral adapter.

The focused coverage-adapter suite passed 4 tests. The complete Strategy Lab v2
package and combined coverage gate will be recorded after this boundary is
committed and rerun; shared migrations, API/worker wiring, upstream
reconciliation, and stable Nautilus execution remain open gates.

## 2026-09-17 - Durable legacy-import checkpoint

`postgres_legacy.py` now maps digest-only legacy import records and their exact
compatibility assessments to an owner-scoped additive PostgreSQL registry.
Original metadata, mapping evidence, and record fingerprints are authenticated
on every read. Supported and unsupported imports are both preserved; exact
retries replay, changed payload or mapping content returns an explicit conflict,
and the adapter never reads legacy payload bytes or claims replay equivalence.

The focused legacy-adapter suite passed 4 tests. The complete Strategy Lab v2
package passed 574 tests with Ruff, MyPy, and `git diff --check` clean. Shared
migrations, authorization, API/worker wiring, upstream reconciliation, and
stable Nautilus execution remain open gates.

## 2026-09-17 - Durable forward-state checkpoint

`postgres_forward_state.py` now maps owner-scoped forward instances, immutable
checkpoint event-id sets, one-time historical warm-up receipts, and
content-addressed seen-event identities to additive PostgreSQL tables. Lifecycle
transitions, warm-up activation, and live-event admission lock state and use
authenticated compare-and-set updates. Exact retries replay; duplicate, gap,
out-of-order, and correction observations remain represented in restart-safe
checkpoint state. The adapter is registration-neutral: it does not consume
providers, submit broker orders, start workers, apply migrations, or register
application routes.

The same adapter now exposes an atomic event-transaction path that stores a
correction's counterfactual replay plan beside the admitted event checkpoint.
Correction retries return the original replay identity and cannot leave a live
correction admitted without replay evidence.

The focused forward-state adapter suite passed 4 tests. The complete
Strategy Lab v2 package passed 565 tests with Ruff, MyPy, and `git diff --check`
clean. All five declared branch checks passed, and the Docker-backed combined
gate passed 2,213 tests with 83.24% total coverage (required threshold: 75%),
with setup and cleanup successful. Cross-record cursor/checkpoint integrity was
also revalidated after the initial adapter checkpoint. Schema migration,
event-stream/worker
wiring, application authorization, upstream reconciliation, and stable Nautilus
execution remain open shared-path gates.

## 2026-09-17 - Durable search-state checkpoint

`postgres_search_state.py` now maps immutable experiment queues and candidate
checkpoints to additive PostgreSQL tables. Candidate starts/retries, terminal
receipts, and cancellation requests delegate to the pure search state machine,
then update candidate and experiment fingerprints through one owner-scoped
compare-and-set transaction. Exact retries replay, while missing, foreign,
malformed, or tampered candidate rows fail closed; dispatch transport, worker
execution, migrations, and application wiring remain outside this adapter.

The focused search-state adapter suite passed 4 tests. The complete Strategy
Lab v2 package passed 570 tests with Ruff, MyPy, and `git diff --check` clean.
All five declared branch checks passed, and the Docker-backed combined gate
passed 2,217 tests with 83.26% total coverage (required threshold: 75%), with
setup and cleanup successful. Shared migrations, API/worker integration,
upstream reconciliation, and stable Nautilus execution remain open gates.

## 2026-09-17 - Durable artifact-lineage checkpoint

`postgres_lineage.py` now maps owner-scoped immutable artifact-lineage edges to
an additive PostgreSQL table. Semantic keys provide exact replay and changed
edge conflicts; rows are locked, fingerprint-authenticated, and ordered
deterministically before the pure lineage index is returned. The adapter does
not certify manifest existence, create foreign-key migrations, authorize
owners, or publish artifact bytes.

The focused lineage-adapter suite passed 4 tests. The complete Strategy Lab v2
package passed 561 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed, and the Docker-backed combined gate passed 2,208
tests with 83.22% total coverage (required threshold: 75%), with setup and
cleanup successful. Schema migrations, application wiring, worker entrypoints,
Compose integration, upstream reconciliation, and stable Nautilus execution
remain open shared-path gates.

## 2026-09-17 - Durable artifact-commit checkpoint

`postgres_artifact_commit.py` now maps immutable artifact-publication commit
records to an additive PostgreSQL ledger. It locks and authenticates the
complete commit set, preserves create-if-absent and exact-replay semantics,
and protects storage-key uniqueness so a different manifest cannot reuse an
immutable address. The adapter only stages commit evidence; artifact-byte
publication, manifest validation, retention policy, migration application, and
application wiring remain outside this package-local boundary.

The focused artifact-commit suite passed 4 tests. The complete Strategy Lab v2
package passed 557 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed, and the Docker-backed combined gate passed
2,204 tests with 83.20% total coverage (required threshold: 75%), with setup
and cleanup successful. Schema migrations, application wiring, worker
entrypoints, Compose integration, upstream reconciliation, and stable Nautilus
execution remain open shared-path gates.

## 2026-09-17 - Durable artifact-retention checkpoint

`postgres_artifact_retention.py` now maps manifest-bound retention state and
owner-scoped immutable pins to additive PostgreSQL rows. Initial state and pin
rows are authenticated by canonical fingerprints; pin add/release updates the
pin and state identity atomically with compare-and-set, and exact retries
replay without rewriting immutable bytes. Retention eligibility is resolved at
an explicit observation instant, preserving pinned, tiered, ephemeral, and
permanent decisions without a wall clock or deletion side effect. Malformed,
foreign, tampered, and uniqueness-racing rows fail closed; migration
application, authorization, artifact storage lifecycle, and runtime wiring
remain shared gates.

The focused retention-adapter suite passed 4 tests. The complete Strategy Lab
v2 package passed 553 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed, and the Docker-backed combined gate passed
2,200 tests with 83.18% total coverage (required threshold: 75%), with setup
and cleanup successful. Schema migrations, application wiring, worker
entrypoints, Compose integration, upstream reconciliation, and stable Nautilus
execution remain open shared-path gates.

## 2026-09-17 - Durable worker and lease state checkpoint

`postgres_worker_state.py` now maps immutable worker profiles, serial
reservation capacity, execution-attempt leases, and ordered heartbeat/release
observations to additive PostgreSQL schema statements. Profile, reservation,
lease, and observation bytes are re-authenticated by canonical fingerprints;
active worker/attempt uniqueness is guarded by a partial unique index; release
and lease-observation updates use compare-and-set inside one async transaction.
Exact retries replay, while saturation, gaps, stale sequences, identity drift,
tampering, and uniqueness races fail closed. No process scheduling, engine
disposal, queue publication, migration application, or shared runtime wiring is
performed by this package-local adapter.

The focused worker-state suite passed 5 tests. The complete Strategy Lab v2
package passed 549 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed, and the Docker-backed combined gate passed 2,196
tests with 83.16% total coverage (required threshold: 75%), with setup and
cleanup successful. Schema migrations, application wiring, worker entrypoints,
Compose integration, upstream reconciliation, and stable Nautilus execution
remain open shared-path gates.

## 2026-09-17 - Durable execution-state checkpoint

`postgres_execution_state.py` now maps owner-scoped execution outcomes and
progress checkpoints to additive PostgreSQL rows. It locks both records for an
attempt, validates their shared identity and stored fingerprints, preserves
monotonic outcome transitions, retains every applied progress-update digest
for restart-safe replay, and applies combined outcome/progress/cancellation
observations atomically. `read_context` returns the authenticated pair needed
by the command adapter. Partial/tampered state, gaps, illegal transitions,
cross-owner reads, and compare-and-set races fail closed; no queue, worker, or
broker effect is performed.

The focused state-adapter suite passed 4 tests; the full Strategy Lab v2
package passed 544 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed. The Docker-backed combined gate passed
2,191 tests with 83.12% total coverage (required threshold: 75%), with setup
and cleanup successful.

## 2026-09-16 - Atomic execution-event transaction staging checkpoint

`postgres_event_transaction.py` now maps the canonical execution-event,
append-only audit, transactional-outbox, and stream-cursor contracts to one
SQLAlchemy async transaction. It locks the attempt stream, re-authenticates
stored event/audit/outbox/cursor fingerprints, enforces contiguous sequence
and cursor identity, persists all linked rows atomically, and supports exact
replay plus an optional caller cursor compare-and-set witness. Malformed state,
sequence gaps, stale cursors, and uniqueness races fail closed; Redis
publication and worker effects remain outside this adapter. The explicit DDL
is additive and registration-neutral, so migrations and application wiring
remain gated behind upstream reconciliation.

The focused adapter suite passed 4 tests; the full Strategy Lab v2 package
passed 540 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,187
tests with 83.13% total coverage (required threshold: 75%), with setup and
cleanup successful.

## 2026-09-16 - Durable command-receipt staging checkpoint

`postgres_commands.py` now maps retry/cancellation intents to an owner-scoped
PostgreSQL command ledger. The adapter locks the attempt ledger inside one
transaction, resolves the latest injected outcome/progress context through the
engine-neutral command state machine, persists accepted receipts, replays exact
idempotent requests without writes, and returns typed conflict/precondition/not-
found errors. Receipt fingerprints are stored and revalidated so tampered rows
fail closed. The adapter deliberately performs no worker cancellation/retry
effect; schema migration, application wiring, Redis/outbox dispatch, and worker
integration remain gated.

The focused command-adapter suite passed 5 tests; the full Strategy Lab v2
package passed 536 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed. The Docker-backed combined gate passed
2,183 tests with 83.12% total coverage (required threshold: 75%), with setup
and cleanup successful.

## 2026-09-16 - Durable submission/dispatch staging checkpoint

`postgres_submission.py` now maps owner-scoped idempotent submission receipts
and dispatch intents to one async PostgreSQL transaction. It authenticates
canonical payload digests, revalidates stored request/dispatch fingerprints,
replays exact retries without writes, repairs a missing dispatch from an
existing receipt, isolates principals by owner key, and returns typed API
conflicts for content drift. The adapter only stages a durable dispatch intent;
Redis publication, worker effects, migrations, application wiring, and route
registration remain outside this package-owned slice. The API router now passes
the generated request ID into submission and command adapters for error lineage.

The focused submission adapter suite passed 5 tests; the full Strategy Lab v2
package passed 531 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,178
tests with 83.09% total coverage (required threshold: 75%), with setup and
cleanup successful. Shared migrations/application wiring, worker entrypoints,
Compose, upstream reconciliation, and stable Nautilus execution remain open.

## 2026-09-16 - Persisted revision-bound resource identity checkpoint

Resource projection now derives a missing API `revision_digest` from the
authenticated aggregate state fingerprint. Every projected document therefore
identifies the exact canonical persisted state, while explicitly supplied
revision digests remain format-validated. This is still a read-only,
registration-neutral adapter; no migrations, model registration, auth wiring,
worker dispatch, or shared provider paths were changed.

Focused route/read validation passed 13 tests, the full Strategy Lab v2 package
passed 526 tests, and Ruff, MyPy, and `git diff --check` were clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,173
tests with 83.06% total coverage (required threshold: 75%), with setup and
cleanup successful. Durable submission/command adapters, schema migrations,
application wiring, worker entrypoints, Compose, upstream reconciliation, and
stable Nautilus execution remain open.

## 2026-09-16 - Request-correlated API collection checkpoint

The registration-neutral router now passes its generated request identity into
collection adapters and rejects a collection envelope that returns a different
identity. This closes a response-lineage gap between the API request and the
PostgreSQL resource reader, while retaining the existing owner, cursor, and
snapshot checks. No application registration, authentication dependency,
migration, worker, or shared provider path was changed.

The focused route/read set passed 13 tests; the complete Strategy Lab v2
package passed 526 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,173
tests with 83.06% total coverage (required threshold: 75%), including setup
and cleanup. The change is committed and published; durable submission/command
adapters, schema migrations, application wiring, worker entrypoints, Compose,
upstream reconciliation, and stable Nautilus execution remain open.

## 2026-09-16 - PostgreSQL resource-read adapter checkpoint

`postgres_storage.py` now exposes read-only `get` and deterministic `list_type`
aggregate snapshots. Rows are decoded through the canonical JSON codec and
their state fingerprints are re-authenticated before being returned.
`postgres_resources.py` projects those snapshots into immutable API resource
documents scoped to the authenticated principal. Collection pages sort by a
stable `(sort_value, id)` key and bind opaque cursors to the complete visible
resource-set digest; foreign rows, malformed owner/resource/relationship state,
duplicate identities, and snapshot drift fail closed. The adapter is structural
and registration-neutral, so it does not add migrations, route registration,
authentication dependencies, worker effects, or writes.

Focused validation passed 11 persistence/read-adapter tests; the package tree
passed 525 Strategy Lab v2 tests with Ruff, MyPy, and `git diff --check` clean.
The declared branch checks passed all five checks. The Docker-backed combined
backend gate passed 2,172 tests with 83.05% total coverage (required threshold:
75%), including successful setup and cleanup. This slice is committed and
published; schema migrations, application wiring, router/auth registration,
worker entrypoints, Compose services, upstream reconciliation, and stable
Nautilus execution remain open behind the shared-path gates.

## 2026-09-16 - PostgreSQL resource-read adapter context (in progress)

This changeset owns only the package-local PostgreSQL aggregate read helpers,
the owner-scoped resource projection adapter, focused tests, and the related
documentation/workstream receipts. It must not add migrations, register models
or routes, change authentication, alter existing Strategy Lab services, enqueue
work, or touch provider/ETF/TC2000/frontend paths. The adapter will fail closed
on malformed state, owner mismatch, cursor snapshot drift, and ambiguous
resource identity; writes and state-changing API operations remain behind the
existing compare-and-set and staging gates.

## 2026-09-16 - Registration-neutral API boundary context (in progress)

This changeset owns only the new package-local API adapter/router and its
focused tests, plus the Strategy Lab v2 documentation and workstream receipts.
It will expose deterministic resource/error serialization, cursor-bound reads,
static strategy validation, idempotent asynchronous submissions, and
retry/cancellation command intents through an injected adapter. It must not
register a router in `backend/app/main.py`, touch existing Strategy Lab routes,
models, migrations, authentication dependencies, worker entrypoints, Compose,
provider/ETF/TC2000 paths, or frontend code. The adapter remains responsible for
authorization, persistence, atomic compare-and-set, dispatch, and execution.

## 2026-09-16 - Registration-neutral API boundary checkpoint

`api_router.py` now provides a package-local `create_strategy_lab_router()`
factory. The router exposes cursor-bound resource collection/read endpoints,
static strategy-source validation, idempotent asynchronous submission, and
retry/cancellation command intents. It serializes frozen resource envelopes,
Decimal/timestamp values, submission/command receipts, and stable typed errors;
all state-changing behavior is delegated to an injected adapter scoped by the
authenticated principal. Invalid cursors, resource types, bodies, source size,
missing idempotency keys, and adapter conflicts fail closed. The router is
deliberately not registered in `main.py`, so no shared application/auth/model
path was changed.

Focused validation passed 7 API-router tests. The exact package tree passed 519
Strategy Lab v2 tests, Ruff, MyPy, and `git diff --check`; the declared branch
checks passed all five checks. The Docker-backed combined backend gate passed
2,166 tests with 83.04% total coverage (required threshold: 75%), including
successful setup and cleanup. This remains an adapter boundary: durable
PostgreSQL/API wiring, authentication dependency selection, Redis dispatch,
worker effects, router registration, and full upstream reconciliation remain
open behind the existing gates.

The implementation context is complete. The next action is to reconcile the
provider-platform, ETF, and TC2000 shared contracts after their branches reach
staging, then register this router and add additive persistence/API/worker
integration without changing the engine-neutral contracts. No other worktree
or shared path was modified.

## 2026-09-15 - Approved implementation plan

The human explicitly activated implementation of the agreed Strategy Lab v2
plan. The assigned worktree is `feat/strategy-lab-v2`, created through the
repository's guarded workflow from synchronized `staging` at
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`. Bootstrap commit
`52a67c6cc74e4b8e4efe95e9d608bce821b8bd02` is published and synchronized.

The initial implementation is limited to new engine-neutral backend package
paths and package-co-located focused tests. A read-only ownership audit found
that the active provider workstream owns `backend/tests/`; v2 tests therefore
stay under `backend/app/strategy_lab_v2/tests/` and are run by explicit pytest
path. The package may define contracts for later adapters but must not
modify provider-platform, ETF, or TC2000 worktrees; current Strategy Lab routes
and services; shared models, migrations, application registration, worker/task
entrypoints, global dependencies, Compose, or frontend until the three parallel
branches reach staging and every overlap is semantically reconciled. The next
phase consumes their staged capability, point-in-time membership, and immutable
CodeVersion/Study Lab contracts without duplicating their ownership.

Nautilus v2 remains the sole authoritative engine target, gated on stable
publication and the branch conformance suite. Current official release evidence
still identifies the v2 line as release candidates; no candidate is eligible
for production enablement. The engine-neutral core can progress independently.
The eventual runtime uses a separate isolated worker environment and a Rust
adapter for canonical forward events. Backtests and persistent broker-free
shadow instances have separate worker capacity. The frontend remains a later
TC2000-native dockable suite in a separately authorized branch.

The branch-owned plan records the architecture, all final acceptance criteria,
the current parallel-safe boundary, deferred shared-path gates, and
`full_stack_browser` completion profile. Initial focused package work can use
unit checks; the complete branch must pass the repository's full backend,
database/Redis, migration, Compose, worker, API, browser, and exact-tip gates.
`make branch-validate` currently validates all workstream records. The
session-local goal is active.

Session `603da09c-b640-4018-9f40-c62f4564b074` owns this worktree. Do not edit
another worktree, even if dependency work advances in parallel; reconcile its
staged changes here only after an authorized staging update.

## 2026-09-15 - Engine-neutral core checkpoint

The initial engine-neutral implementation is committed locally as
`4f265239c1b736e50ba7bf514f0986ca663eebc9`; a separate focused documentation
correction is `1d934e578cb3a75f37d31ec30b6d551d004452b5`. Both commits are in the
assigned worktree. They add only `backend/app/strategy_lab_v2/` and
`docs/strategy-lab-v2.md`. No active provider, ETF, TC2000, model, migration,
router, worker, dependency, Compose, or frontend path was changed.

Focused evidence on the code checkpoint: `cd backend && rtk uv run pytest
app/strategy_lab_v2/tests -q --override-ini addopts=` passed (9 tests),
`rtk uv run ruff check app/strategy_lab_v2` passed, and
`rtk uv run mypy app/strategy_lab_v2` passed. The focused pytest override avoids
applying the repository-wide coverage threshold to this package-only slice; it
does not satisfy the final full-suite gate.

The core now includes typed immutable domain and strategy-package contracts,
canonical content fingerprints, preflight classification and degradation,
semantic snapshot-to-requirement matching, SDK input/intent contracts,
deterministic search and walk-forward planning, Decimal baseline metrics,
attempt/forward-event lifecycle helpers, and result provenance binding trial,
successful attempt, package/strategy, portfolio, snapshot, metric, engine/build,
dependency, assumptions, seed, and output artifact identities.

Important trust boundary: `DataSeriesManifest` binds an upstream
`coverage_evidence_digest`, but the engine-neutral package cannot resolve or
validate that evidence document. `DataSnapshot` checks manifest semantics and
range continuity only; it trusts the upstream attestation reference. Before any
execution path exists, the provider-platform adapter must validate the attested
series content, range, row count, calendar, and semantic dimensions. Host-side
portfolio allocation/shared-risk execution, complete metrics, persistence, API,
isolated strategy runtime, workers, local Compose services, and authoritative
Nautilus execution remain unfinished. Do not treat this checkpoint as a usable
simulator or sandbox.

Publication hold: after the implementation commit, the exact command
`rtk git push origin feat/strategy-lab-v2` was denied by the elevated execution
approval reviewer. Its stated issue was that the transcript did not establish
the private `origin` destination as a trusted organization-owned repository or
contain explicit authorization for that destination. The pre-operational local
implementation/doc tip is `1d934e578cb3a75f37d31ec30b6d551d004452b5`; after
this workstream-record checkpoint, verify its enclosing commit externally with
`rtk git rev-parse HEAD`. The remote `origin/feat/strategy-lab-v2` remains
`d2497f43084d52d3e66b40a91be25dd2678620be`. Do not retry through another shell,
API, plugin, or indirect route. Continue independent local work; ask the human
to explicitly authorize this exact remote destination before attempting normal
publication again.

## 2026-09-15 - Shared-account allocation and metrics checkpoint

The second parallel-safe implementation slice is committed locally as
`6def980311f7c5aef05ffcc13646d9beeae5c5aa`. It adds event-aligned component
target resolution, deterministic conflict policies, cash-equity-only signed
notional risk checks, all-or-nothing shared limits, explicit flat targets, and
34-digit deterministic Decimal arithmetic. Product classes without a registered
and policy-allowed risk model fail closed. Raw order sizing and engine routing
remain unsupported.

Metrics v2 now adds explicit-currency account P&L/return, drawdown duration,
Ulcer, annualized return/volatility, Sharpe/Sortino/Calmar, monetary recovery
factor, empirical nearest-rank VaR/expected shortfall, and trade-quality/streak
summaries. Each value records its calculation and basis conventions. Equity
curves currently mean equally spaced post-start marks; timestamps and
irregular-time annualization remain unsupported. Exposure/capital, execution
cost, attribution, rolling, distribution, sensitivity, calendar metrics,
persistence, APIs, workers, isolated execution, and Nautilus integration remain
open.

Validation on the exact implementation tree: focused package pytest passed 30
tests; Ruff and mypy passed; `git diff --check` passed. `make branch-validate`
is rerun after this operational checkpoint. The package-only checks do not
satisfy the planned full-stack completion profile.

Publication remains a transport hold, not a product blocker. The current
implementation tip is `6def980311f7c5aef05ffcc13646d9beeae5c5aa`; the recorded
remote tip is `d2497f43084d52d3e66b40a91be25dd2678620be`, so the local branch is
four commits ahead after this implementation commit. The previous elevated
push for an earlier payload was rejected by the private-repository egress
review. No push of the current range has been attempted. Do not retry
`rtk git push origin feat/strategy-lab-v2` until the human explicitly authorizes
the exact current destination and range; continue independently scoped local
work and never claim synchronization.

The prior next-action context has been completed at the checkpoint below. Keep
shared integration deferred until provider, ETF, and TC2000 reach staging and
their exact contracts are reconciled. Maintain `in_progress`; closure,
integration, promotion, and deployment are not authorized.

## 2026-09-15 - Run-scoped observations and result metrics checkpoint

The next engine-neutral result slice is committed locally as
`82749796ac520a227288e7fa54dfed3a589a3983`. It adds normalized event-time and
sequence points, account exposure snapshots, fill cost observations, and
component P&L observations. All run observations carry a run-attempt identity;
component P&L is bound to one common result bundle and reconciles exactly to
portfolio gross/net P&L, including an explicit unallocated residual when needed.

Metrics v3 now provides event-sampled cash-equity notional/equity and cash/equity
ratios, run-scoped fill-cost summaries, and reconciled component P&L
contributions. Exposure measures are sample-weighted, not time-weighted or
margin utilization. Cost totals and bps are null unless every fill has an
explicit complete cost report; partial/unavailable reports are counted and
reported category values are labelled as observed rather than complete. FX,
slippage, cost models, and attribution methods require adapter-provided evidence;
the core infers none of them. Stable canonical observation digests travel with
metric calculation bases. Independent review found no remaining actionable
P0-P2 findings after the run-identity and incomplete-cost fixes.

Exact-tip package validation at the implementation commit passed: focused
package pytest (39 tests), Ruff, mypy (16 files), and `git diff --check`. This is
not the planned full-stack validation profile. Existing deferred gaps include
calendar-aware rebalance semantics, irregular-time/rolling/distribution/
sensitivity/calendar metrics, product-specific risk models beyond cash
equities, verified provider coverage evidence, persistence, APIs, workers,
isolated strategy execution, Compose services, and authoritative Nautilus v2
execution/conformance.

The branch remains local and is six commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; no push of this current range was
attempted. The previous private-repository egress hold remains unchanged. Do not
publish through another route; continue local work under this session. Next:
define and test immutable calendar-versioned rebalance policy and schedule
semantics in package-owned paths. Keep provider, ETF, TC2000, shared runtime,
migration, API registration, Compose, and frontend ownership boundaries intact.

## 2026-09-15 - Calendar-aware rebalance scheduling checkpoint

The next engine-neutral slice is committed locally as
`32019aa8518114f1ca658d2b9e9f24c8c2f53083`. `PortfolioComposition` now binds an
optional typed, versioned `CalendarRebalancePolicy`. The new `rebalance.py`
contract pins that policy to an immutable content-addressed session calendar
with explicit trading/closed dates, timezone/tzdb versions, source evidence,
venue-assigned session labels, and UTC session segments (including split
sessions, overnight trading dates, DST, and early closes).

The pure planner supports each-session, ISO-weekly, monthly, quarterly, and
yearly cadence, first/last actual session selection, open-before-events or
close-after-events decision boundaries, and explicit misfire policy. Weekly and
larger cadences require complete calendar period coverage; requested ranges use
inclusive venue session labels. No calendar is fetched or inferred. The planner
does not map boundaries to engine event sequences, apply component capital
weights, emit orders, or imply fills at open/close prices; those remain adapter
and execution work.

Exact-tip package validation passed: focused pytest (48 tests), Ruff, mypy (18
files), and `git diff --check`. Independent review found no remaining actionable
P0-P2 findings after correcting the stale rebalancing documentation. This is
still package-only validation, not the planned full-stack browser/DB/Redis/
worker/Compose gate.

The local branch is eight commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; no push of this current range was
attempted, and the previous private-repository egress hold is unchanged. Next
bounded work: add run-attempt-scoped timestamped account-equity observations
and rigorous calendar-period metric inputs, explicitly preserving irregular
event timing and rejecting unsupported external-cash-flow assumptions. Keep
all parallel provider, ETF, TC2000, shared runtime, migration, API, Compose, and
frontend boundaries unchanged. Maintain `in_progress`; closure, integration,
promotion, and deployment remain unauthorized.

This operational checkpoint updates only the following branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/plan.yaml`
- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Replicate seed and sensitivity evidence checkpoints

The seed-provenance implementation is committed locally as
`6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`, with its separate ops record at
`cefa6c468501c990676587f0e39287f9976bc56b`. It adds deterministic replicate
seed schedules while preserving the default single-trial identity and legacy
seed path. Focused validation passed 60 package tests, Ruff, MyPy (18 source
files), and `git diff --check`.

The sensitivity-evidence implementation is committed locally as
`69faca1941157ff1597e209ce6d2679af08fcd70`, with its separate ops record at
`f19db3e634b822f1cf27257e18d7ea33b3332137`. It distinguishes unpaired runs,
shared-seed provenance, and unverified keyed-stream pairing claims; it does not
assert statistical independence or calculate numeric deltas. Focused validation
passed 60 package tests, Ruff, MyPy (18 source files), and `git diff --check`;
the workstream validator passed all 30 records after the checkpoint update.

The recorded origin remains
`d2497f43084d52d3e66b40a91be25dd2678620be`. The private-origin publication
hold remains unchanged: no push was attempted for these exact ranges and no
alternate publication route is authorized.

## Scope recorded - stable metric calculation identity and run evidence

This bounded engine-neutral context owns only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/tests/test_metrics.py`,
`backend/app/strategy_lab_v2/tests/test_observations.py`, and
`docs/strategy-lab-v2.md`. It introduces a versioned structured
calculation definition and typed evidence references on calculated metrics.
The stable calculation fingerprint excludes observed values, sample sizes,
display strings, and run evidence; per-family effective parameters are recorded
where they change calculation semantics. Formula version v6 remains unchanged.
No metric deltas, statistical inference, comparator, API, persistence, worker,
runtime, Compose, frontend, provider, ETF, TC2000, or shared path is included.

Exact focused checks pass: 62 Strategy Lab v2 tests (`--no-cov` to avoid the
repository-wide coverage threshold on this focused selection), Ruff, MyPy (18
source files), and `git diff --check`. Independent read-only review initially
found an overbroad annualization parameter on cadence-independent metrics; it
was narrowed to annualized/risk-adjusted metrics and re-reviewed with no
remaining P0-P2 issue. The formula compatibility test now confirms that changing
`periods_per_year` preserves total-return identity while changing annualized
return identity.

The five product files listed above were committed locally in
`f34fb2564d62c8721f1b518ca093876271f3e3ca`; the later checkpoint below records
that completed changeset. Keep the existing publication hold; do not push
without exact-payload authorization. The enclosing operational checkpoint SHA
will be verified externally with `git rev-parse` rather than written into
itself.

## Completed context - Trial seed-sharing and replicate provenance

This implementation context owned only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/experiments.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`, and
`docs/strategy-lab-v2.md`. Preserve the existing per-candidate seed output as
the default, and add an explicit shared-seed-per-scenario-and-replicate policy
plus typed trial randomization provenance (master seed, effective seed,
replicate index, seed-group fingerprint, derivation version). This is a seed
assignment contract only: equal initial seeds do not prove event-level paired
randomness or statistical comparability when an engine consumes sequential or
otherwise unkeyed random streams. One-factor paired sensitivity, engine RNG
attestation, API/persistence, workers, and runtime integration remain deferred.
Keep provider, ETF, TC2000, shared runtime, migration, route, Compose, and
frontend ownership unchanged.

Compatibility review: preserve the old `ScientificTrial.trial_id` for the
default per-candidate, single-replicate, unscoped schedule. Its typed assignment
retains master/effective seed, seed-group fingerprint, and derivation version,
but excludes the legacy schedule metadata from trial identity. Explicit shared,
scoped, or replicated schedules bind the group provenance and replicate count
into trial identity. The regression compares builder output with the prior
explicit-effective-seed construction. A subsequent independent review also
found that callers could pair a valid digest with the wrong effective seed; the
contract now checks derived seeds against supported versioned digests and
rejects unknown derivation versions. Explicit-seed records are separately
validated and cannot claim generated schedule provenance.

The implementation is committed locally as
`6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`. It preserves legacy default seed
values and trial IDs, adds deterministic shared-per-scenario/replicate seed
assignments, carries replicate count and seed-group provenance, validates the
effective seed against the supported digest version, and rejects unsupported or
inconsistent assignments. Equal initial seeds still do not claim paired draws.

Exact focused validation passed: 60 package tests, Ruff, MyPy (18 source files),
`git diff --check`, and `make branch-validate` (30 workstream records).
Independent review found no remaining P0-P2 issue. This is package-level
evidence only; the full-stack/DB/Redis/API/worker/Compose/Nautilus completion
gates remain outstanding.

Publication state is `committed_locally_pending_push`. At the implementation
commit boundary, `HEAD` is `6ec5074e696a4333dd9fe5b59ec0f693fb0477f9` and
`origin/feat/strategy-lab-v2` is
`d2497f43084d52d3e66b40a91be25dd2678620be`; the exact range is
`d2497f43084d52d3e66b40a91be25dd2678620be..6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`.
No push of this range was attempted because exact-payload authorization for the
private origin is unavailable. Do not use an alternate transport. The separate
ops checkpoint for this seed-provenance slice was committed locally before the
next sensitivity-evidence implementation recorded below. Do not treat this
implementation-only range as a new authorization to publish the full branch.

## 2026-09-16 - Sensitivity randomization-evidence checkpoint

The implementation is committed locally as
`69faca1941157ff1597e209ce6d2679af08fcd70`. It adds an engine-neutral
`SensitivityComparisonEvidence` contract that requires successful results to
share their fixed execution context and distinguishes `unpaired`,
`shared_seed_only`, and `pairing_claim_unverified`. An equal integer seed alone
does not establish a common randomization group; matched scenario/replicate seed
provenance is required for the shared-seed-only label. A structurally complete
keyed-stream claim binds both attempts, the engine build, trace artifacts, and a
matched-draw artifact, but the contract deliberately cannot authenticate these
artifacts or prove engine conformance. No verified paired-stream or statistical
independence classification is emitted until a trusted verifier/registration
receipt exists. Retries of one scientific trial are not treated as sensitivity
replicates. This contract classifies randomization provenance only; it does not
compare metric semantics, calculate metric deltas, or perform paired inference.

Independent review initially identified overclaims around independence and
unverified paired evidence, plus an invalid exact comparison of run-dependent
metric calculation-basis strings. The implementation now uses neutral
`unpaired` and unverified-claim levels, and separates provenance classification
from metric compatibility. Re-review found no remaining P0-P2 issue.

Exact implementation-commit validation passed: 60 package tests, Ruff, MyPy
(18 source files), and `git diff --check`. `make branch-validate` passed all 30
records on an elevated retry after the default sandbox denied UV cache metadata
access; this was the repository validator only. These focused checks do not
satisfy the DB/Redis/API/worker/Compose/Nautilus/security/full-stack acceptance
gates.

At this implementation boundary, local HEAD is
`69faca1941157ff1597e209ce6d2679af08fcd70`, 18 commits ahead of recorded
`origin/feat/strategy-lab-v2`
(`d2497f43084d52d3e66b40a91be25dd2678620be`). No push was attempted because
exact-payload authorization for the private origin is unavailable; do not
publish through another route. The separate ops checkpoint will be committed
after these implementation results are recorded.

The next bounded slice in that handoff, separating stable calculation identity
from run-specific evidence, was implemented in
`f34fb2564d62c8721f1b518ca093876271f3e3ca` and is recorded below. Numeric
one-factor descriptive sensitivity deltas remain the next metric slice. Keep
paired statistical inference deferred until the worker has a trusted keyed-
stream verifier and aligned per-observation outputs. Preserve all provider,
ETF, TC2000, shared runtime, persistence, API, worker, Compose, and frontend
boundaries.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Metric calculation identity and evidence checkpoint

The implementation changeset is committed locally as
`f34fb2564d62c8721f1b518ca093876271f3e3ca`. It adds a versioned structured
calculation definition and typed evidence references to metric values. Stable
fingerprints bind metric identity, units, basis, formula version, and only
effective calculation parameters; observed values, sample sizes, display text,
null state, and run-specific evidence do not alter that calculation identity.
All eight current metric families emit stable formula IDs, Decimal context,
effective parameters where semantically relevant, and typed input/calendar/fill/
attribution evidence. The catalog remains v6 because estimator formulas did
not change. This is an identity primitive, not a metric comparator.

Exact focused validation passed: 62 package tests with `--no-cov`, Ruff, MyPy
(18 source files), and `git diff --check`. The initial focused pytest invocation
ran under the repository-wide coverage threshold and exited nonzero at 7.24%
coverage versus the required 55%; it was rerun successfully with `--no-cov`.
`make branch-validate` passed all 30 workstream records on the documented
elevated retry after the default sandbox blocked UV cache metadata access.
Independent review caught an overbroad `periods_per_year` parameter on
cadence-independent metrics; the implementation was narrowed and re-reviewed
with no remaining P0-P2 issue. This package-only evidence does not satisfy the
full-stack/DB/Redis/API/worker/Compose/Nautilus acceptance gates.

The local branch is 20 commits ahead of recorded
`origin/feat/strategy-lab-v2` at
`d2497f43084d52d3e66b40a91be25dd2678620be`. The exact pending range ends at
`f34fb2564d62c8721f1b518ca093876271f3e3ca`. No push was attempted: exact-payload
authorization for the private origin remains unavailable, and no alternate
transport is authorized. The default sandbox denied UV cache metadata access
for repository workflow commands; the exact session-status command succeeded
on the documented narrow elevated retry. No sandbox setting was changed, and
no other worktree or shared/provider/frontend path was touched.

Next bounded implementation context: add run-scoped descriptive one-factor
metric deltas using `MetricValue.calculation_fingerprint` to require compatible
calculation semantics. Preserve unpaired/shared-seed provenance labels; do not
claim statistical significance or paired inference without trusted keyed-stream
verification and aligned per-observation outputs. Only the three branch-owned
workstream records below remain in this checkpoint; stop this session after
the ops checkpoint per the repository soft-stop rule.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

The soft-stop `agent-session-checkpoint` completed under the existing session
claim. Its `dirty_paths` capture dropped the leading `b` from the first modified
path (`backend/...` appeared as `ackend/...`), because the helper strips leading
status whitespace before removing the porcelain prefix. Raw `git status` confirms
the correct path. I corrected only this workstream's `session.json`; the helper
implementation is outside this branch's owned scope and was not changed.

## 2026-09-15 - Calendar-period equity metrics checkpoint

The next engine-neutral slice is committed locally as
`5a5177ea28d5a1b50d225aaa5b400d46f4a411aa`. It adds immutable,
run-attempt-scoped account-equity intervals bound to a versioned session
calendar. Calendar metrics reconcile account equity deltas less explicit
external cash flows and support each-session, ISO-weekly, monthly, quarterly,
and yearly buckets. Period completeness requires the prior actual session
close through the period's final actual session close; returns are null for
incomplete coverage or external flows (time-weighted returns are not inferred).

Independent review identified and resolved one P2 comparison risk: a partial
window could otherwise emit a value named as a full calendar-period return.
The partial-period test now asserts the null and its explicit reason. Exact-tip
focused validation passed: 51 package tests, Ruff, mypy (18 source files), and
`git diff --check`. `ruff format --check` would reformat ten package files,
including existing code, so broad formatter churn was not applied. The focused
checks do not satisfy the planned database/Redis, API, worker, Compose, Nautilus,
security, or full-stack validation gates.

The branch is ten commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; this slice has not been pushed and
the prior private-repository publication hold remains unchanged. No shared or
parallel branch was touched. Next bounded engine-neutral slice: implement
run-scoped rolling return/risk series with explicit session sampling, complete
window coverage, and minimum-observation rules. Keep provider, ETF, TC2000,
shared runtime, persistence, API, worker, Compose, and frontend boundaries
unchanged. Maintain `in_progress`; closure, integration, promotion, and
deployment remain unauthorized.

This checkpoint updates only these dirty branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-15 - Rolling and calendar-period equity metrics checkpoint

The implementation changeset is committed locally as
`2d9d8865bc69292dcd1c48719fa6ab803686af3f`. It adds typed rolling session-close
metric points, exact session-window coverage, explicit annualization and
risk-free assumptions, and rolling P&L/return/volatility/Sharpe/Sortino/drawdown/
duration/Ulcer metrics. Calendar-period and rolling aggregators now require
complete external-flow reports for adjusted net P&L and explicit flow-occurrence
evidence for return/risk eligibility. Independent review found and resolved the
zero-net offsetting-flow case; a zero net amount with any flow event now withholds
return and equity-path risk metrics. An intermediate focused run also exposed an
unavailable-flow test fixture that retained stale occurrence evidence; the
fixture was corrected to omit both amount and occurrence, and the final exact-tip
checks pass.

Exact-tip focused validation passed: 56 package tests, Ruff, MyPy (18 source
files), and `git diff --check`. Independent review found no remaining concrete
defect. This is package-only evidence, not the planned full-stack/DB/Redis/API/
worker/Compose/Nautilus completion gates.

The implementation commit remains pending publication at
`2d9d8865bc69292dcd1c48719fa6ab803686af3f`; the separate ops checkpoint is
being committed on top of it. The recorded remote tip is
`d2497f43084d52d3e66b40a91be25dd2678620be`. No push of the current range was
attempted because the prior private-repository egress review rejected a payload
and the exact current range has not been authorized. Do not retry through an
alternate route. Verify the enclosing ops commit with `git rev-parse` after
commit rather than creating a self-referential hash update. No parallel worktree
or shared/provider/frontend path was modified.

Next bounded slice: run-scoped session-return distribution metrics over the
validated account-equity intervals and exact session calendar. Keep sensitivity
analysis deferred until common-random-seed/matched-trial semantics are defined.
Continue to preserve provider, ETF, TC2000, shared runtime, migration, API,
worker, Compose, and frontend boundaries. Maintain `in_progress`; closure,
integration, promotion, and deployment remain unauthorized.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## Scope recorded before implementation - Run-scoped session-return distributions

The implementation context owned only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`,
`backend/app/strategy_lab_v2/tests/test_observations.py`, and
`docs/strategy-lab-v2.md`. It added typed, run-scoped close-to-close return
quantiles and empirical VaR/expected-shortfall outputs, using explicit inclusive
session-label bounds, exact calendar adjacency and predecessor-close evidence,
minimum sample rules, and the current external-flow fail-closed contract. The
global metric catalog advanced to v6 without changing the v5 equity-curve
estimator semantics. No histogram bins, sensitivity ranking, APIs, persistence,
workers, runtime, Compose, frontend, provider, ETF, TC2000, or shared paths are
in scope. The prior private-repository egress hold remains: continue locally
from the verified clean boundary; do not publish without exact-payload
authorization.

## 2026-09-16 - Run-scoped session-return distribution checkpoint

The implementation is committed locally as
`444193415f0236536767892d6f28effaec39d4ec`. It adds a typed, run-scoped
distribution summary and exact-calendar-bounded close-to-close session-return
quantiles, empirical VaR, and expected shortfall. Inclusive trading-session
bounds require every actual session observation and its preceding actual
session-close mark. Nearest-rank calculations record their effective ranks/tail
counts and use exact integer-rational ceiling arithmetic so high-precision
probabilities cannot move a rank at a Decimal rounding boundary. Incomplete
coverage, incomplete flow reports, or any flow event (including zero-net
offsetting flows) withholds the entire distribution. The catalog is v6; existing
equity-curve estimator semantics are unchanged. Histogram bins and sensitivity
analysis remain out of scope for this slice.

Exact implementation-commit validation passed: focused package pytest (59
tests), Ruff, MyPy (18 source files), and `git diff --check`. Independent
read-only review found no remaining concrete defect. `make branch-validate`
passed all 30 records on an elevated retry after the default sandbox denied UV
cache metadata access; the retry ran only that repository validator. These
package checks do not satisfy the final full-stack/DB/Redis/API/worker/Compose/
Nautilus acceptance gates.

Publication remains a transport hold. Local HEAD is
`444193415f0236536767892d6f28effaec39d4ec`; recorded
`origin/feat/strategy-lab-v2` remains
`d2497f43084d52d3e66b40a91be25dd2678620be`, so this branch is 14 commits ahead.
No push of this exact current range was attempted. The earlier private-repository
egress review rejected a prior payload, and the current remote/range does not
have exact-payload authorization; do not publish through another route.

Next bounded context: define and test deterministic common-random-seed and
replicate semantics for matched one-factor sensitivity analysis. Only after
those semantics are pinned should the comparison contract be added; do not
silently compare trials with independently derived seeds. Keep all active
provider, ETF, TC2000, shared runtime, persistence, API, worker, Compose, and
frontend ownership boundaries unchanged. This separate checkpoint updates only
the branch-owned handoff, session state, and validation journal below.

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Descriptive one-factor metric delta (in progress)

The bounded implementation context owns only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/sensitivity.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`,
`backend/app/strategy_lab_v2/tests/test_sensitivity.py`, and
`docs/strategy-lab-v2.md`. It adds a run-scoped descriptive delta that requires
exactly one canonical parameter change, a matching structured metric
calculation fingerprint, and identical projected measurement-scope identities.
The scope binds the frozen snapshot and its referenced coverage claims,
experiment/scenario, portfolio currency, execution context, formula identity,
and applicable session-calendar evidence. It does not authenticate upstream
coverage claims. Null/incompatible cases are explicit unavailable outcomes;
sample sizes and the existing unpaired/shared-seed/unverified-pairing labels
are preserved. This context makes no significance, ranking, replicate-aggregate,
or paired-inference claim.

The product changeset is committed locally as
`9da8d667e327aca619cc93bd8d22eac123e688a5`. Post-commit focused validation
passed at this exact SHA: 75 Strategy Lab v2 tests, Ruff, focused Ruff formatting
checks for the new comparator/test files, MyPy (20 source files), and
`git diff --check`. Independent read-only review found two missing contract
invariants; both were fixed with direct-construction tests, and the re-review
found no remaining concrete issue. This is package-level evidence, not the final
database/Redis/API/worker/Compose/Nautilus/full-stack acceptance gates.

The ordinary sandbox denied creation of the worktree `.git/index.lock` on the
first commit attempt. Read-only checks found the worktree index owned by the
current user and no stale lock. The repository's narrow elevated Git retry then
committed the already-reviewed staged changeset successfully. No sandbox setting
was changed. This is the documented workflow recovery, not a product blocker.

The required schema-4 session checkpoint initially needed the repository
`agent-session-goal-state` helper to move the takeover marker from
`resumed_after_takeover` to `active`, matching the still-active thread goal.
The checkpoint then passed on the narrow elevated retry after default UV cache
metadata access was denied. Its known dirty-path helper bug removed the leading
`o` from the first path; raw `git status` showed the exact three branch-owned ops
files, and `session.json` was corrected manually. No other path is dirty.

The local branch was 22 commits ahead of
`origin/feat/strategy-lab-v2` at `d2497f43084d52d3e66b40a91be25dd2678620be`
after the product commit. No push was attempted: the private-origin exact-payload
authorization hold remains, and this agent will not use an alternate transport.
The separate ops checkpoint will add one commit above the last recorded
pre-checkpoint SHA; verify the enclosing final SHA externally with `git
rev-parse` rather than chasing a self-referential session hash.

`make branch-validate` passed all 30 workstream records on the narrow elevated
retry after the default sandbox denied UV cache metadata access, including a
final pass after the checkpoint refresh, exact dirty-path correction, and
validation-journal update. The required schema-4 session checkpoint is current
for the product SHA, with the active goal recorded. Exact next action: stage and
review only the three branch-owned ops files, commit the separate checkpoint,
then verify clean status and the exact final `HEAD`/remote hashes externally.
Do not publish the branch while the exact-payload hold remains.

Next bounded action after this ops checkpoint: from a verified clean local
boundary, inspect remaining parallel-safe Strategy Lab v2 core gaps and choose
the next backend-owned slice. Keep paired inference/profitability ranking
deferred until trusted aligned observations exist. This ops checkpoint updates
only these branch-owned files:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

Do not mutate another worktree or provider, ETF, TC2000, shared runtime, API,
persistence, Compose, or frontend path.

## 2026-09-16 - Descriptive one-factor replicate summaries (in progress)

The next bounded implementation context owns only
`backend/app/strategy_lab_v2/sensitivity.py`,
`backend/app/strategy_lab_v2/tests/test_sensitivity.py`, and
`docs/strategy-lab-v2.md`. It adds a deterministic descriptive comparison over
complete baseline and variant replicate groups of successful
`RunResultManifest` values. The groups must differ in exactly one canonical
parameter, contain one result for each distinct scientific trial, and cover
every planned replicate index exactly once. Fixed experiment, scenario,
snapshot, capability, portfolio, engine/build, dependency, assumption, metric
calculation, and measurement-calendar scopes must agree. Missing, duplicate,
null, or incompatible replicates fail closed rather than silently shrinking the
sample. Results retain the per-arm randomization provenance and report
descriptive per-arm summaries plus the difference of sample means. Equal
replicate indices or seeds are not treated as verified paired draws; no
significance, confidence interval, candidate ranking, or independence claim is
made.

Read-only gap audit confirmed that the current v6 package already has account
performance, trade-quality, cash-equity exposure, fill-cost, component
attribution, calendar/rolling, session-return-distribution, and one-run metric
delta calculators. This replicate-level summary is the next parallel-safe
metric gap. Time-weighted returns requiring external-flow boundary valuations,
irregular-time annualization, true margin/capital utilization, financing outside
fill reports, and trusted paired inference remain deferred. Provider, ETF,
TC2000, persistence, API, worker, runtime, migration, Compose, and frontend work
remain outside this context.

The preceding one-factor delta product commit is
`9da8d667e327aca619cc93bd8d22eac123e688a5`; its separate ops checkpoint is
`dfe93ae7014074be066ef677a3c7b985a500956e`. External verification after that
checkpoint found local `HEAD` at `dfe93ae7014074be066ef677a3c7b985a500956e`,
`origin/feat/strategy-lab-v2` at
`d2497f43084d52d3e66b40a91be25dd2678620be`, and a clean worktree (23 commits
ahead). The private-origin exact-payload export hold remains; no push of this
current range was attempted, and no alternate transport is authorized. Continue
from the clean local boundary without claiming remote synchronization.

This scope-selection checkpoint updates only this branch's `plan.yaml`,
`handoff.md`, `session.json`, and `validation.jsonl`. Validate and commit those
records separately before changing the three implementation-context paths
listed above. The session checkpoint helper rejects a changed plan until
`agent-session-plan-ready` runs; the repository helper requires the plan update
to be committed and the local branch head to match its remote before it can mark
the plan ready. Because the exact private-origin range is still under its
authorization hold, the replicate implementation must not start until that
plan-ready gate is satisfied. After this scope checkpoint is locally committed,
the next action is to obtain exact-payload authorization for the resulting
`origin/feat-strategy-lab-v2..HEAD` range, publish only through the approved Git
path, verify synchronized hashes, then run the required plan-ready/session-state
reconciliation. Do not bypass the gate or use another transport.

## 2026-09-16 - Synchronization and plan-ready reconciliation

The human explicitly authorized the exact current export after the prior
private-origin safeguard. The approved elevated command
`rtk git push origin feat/strategy-lab-v2` succeeded for
`d2497f43084d52d3e66b40a91be25dd2678620be..0f0d85c214de6828d8e15b6d03d60adcb1551c2a`.
Post-push verification found a clean worktree and matching local/remote HEAD at
`0f0d85c214de6828d8e15b6d03d60adcb1551c2a`.

`make agent-session-plan-ready SESSION_ID=e2731935-179c-4c35-b5d2-aadf7b4857f7`
passed after synchronization. The resumed session goal was recorded as active
with `make agent-session-goal-state ... STATE=active`, and the required
`make agent-session-checkpoint SESSION_ID=e2731935-179c-4c35-b5d2-aadf7b4857f7`
passed through the approved elevated UV path. The session record now reflects
the synchronized publication state. This operational reconciliation is being
committed separately; verify its enclosing commit externally with
`git rev-parse` rather than writing a self-referential SHA into the record.

The next bounded implementation action is the already scoped descriptive
one-factor replicate summary in the engine-neutral package. Keep the strict
complete-replicate, fixed-context, no-ranking/no-inference boundary and all
provider, ETF, TC2000, persistence, API, worker, runtime, migration, Compose,
and frontend ownership gates intact.

## 2026-09-16 - Descriptive replicate-summary implementation checkpoint

The scoped engine-neutral metric slice is complete in product commit
`3767730ec32ee7cf19b0e4d44fac7caf664f8baf`. It adds immutable typed
`ReplicateRandomizationSummary`, `NearestRankStatistic`,
`ReplicateMetricStatistics`, `OneFactorReplicateMetricSummary`, and explicit
`ReplicateMetricSummaryUnavailable` outcomes in `sensitivity.py`, plus the
`summarize_one_factor_metric_replicates()` API and compatibility alias
`compare_one_factor_metric_replicates()`.

The summary requires successful results covering every planned replicate index
exactly once on each arm, rejects duplicate trials/attempts and inconsistent
arm parameters, enforces exactly one canonical parameter change, and binds one
fixed execution and metric-measurement scope. It preserves each arm's realized
observation sample sizes and full seed provenance, computes Decimal means,
nearest-rank median/minimum/maximum and configured quantiles, and exposes only
the signed difference of arm means. It never ranks candidates or claims
significance, independence, or verified pairing. Focused sensitivity tests now
cover deterministic ordering/statistics, shared-seed-only labeling, incomplete
groups, and null values.

Validation on the exact implementation tree passed 18 focused sensitivity
tests, 80 package tests, Ruff for the changed package files, MyPy for the
changed source and tests, and `git diff --check`. A package-wide Ruff format
check still reports seven pre-existing formatting differences in unrelated
files; no unrelated formatting was changed.

The implementation commit was pushed once through the approved elevated Git
path, but the private-origin safeguard rejected the newer payload before Git
because exact authorization for `0f0d85c214de6828d8e15b6d03d60adcb1551c2a..3767730ec32ee7cf19b0e4d44fac7caf664f8baf` was not established. No alternate
transport or retry was used. The current clean local boundary is
`3767730ec32ee7cf19b0e4d44fac7caf664f8baf`; the remote remains
`0f0d85c214de6828d8e15b6d03d60adcb1551c2a`. The operational record below is
being committed separately; derive the full pending range externally before
any authorized retry.

Next action is blocked only on exact authorization to publish the current
range, followed by plan-ready/session reconciliation for the changed plan. Do
not begin another implementation context, integrate, promote, deploy, or
touch provider, ETF, TC2000, shared runtime, persistence, API, worker, Compose,
or frontend paths while this synchronization gate is unresolved.

## 2026-09-16 - Standing authorization and synchronized implementation boundary

The human granted standing authorization to publish the current Strategy Lab
v2 implementation and its branch-owned operational records. The approved
elevated `rtk git push origin feat/strategy-lab-v2` succeeded for the full
pending range `37a293bc691325460fe75eac4ff9138438da1a54..6b8b6b68a6fd41abcca28f3ca6c9a5e3fbe16669`.
Post-push verification found a clean worktree and matching local/remote HEAD
at `6b8b6b68a6fd41abcca28f3ca6c9a5e3fbe16669`.

The required `agent-session-plan-ready`, `agent-session-goal-state ...
STATE=active`, and `agent-session-checkpoint` workflow gates all passed under
the authorized elevated path. Session metadata now records the synchronized
boundary and an active goal. The next bounded action is to inspect and
implement the next engine-neutral metric slice; no provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths are opened by this authorization.

## 2026-09-16 - Flow-adjusted return implementation checkpoint

The next package-owned metric slice is complete in product commit
`ec670600a3eda08eea7ee40ea05b61becb45ed83`. It adds the immutable
`ExternalCashFlowBoundaryObservation` and binds ordered interior pre-flow and
post-flow marks to each `AccountEquityIntervalObservation`. Boundary amounts
must reconcile the parent interval's reported flow; zero and offsetting flows
remain observable rather than being collapsed into a false no-flow claim.

`calculate_time_weighted_return_metrics()` now geometrically links the
subperiod factors around every explicit flow, withholds results when native flow
reports are incomplete or boundary evidence is missing, and emits an explicit
elapsed-UTC annualized return using a caller-supplied days-per-year convention.
Existing calendar, rolling, and distribution aggregators remain intentionally
unchanged and fail closed for flow-bearing inputs until they consume this
boundary evidence directly.

Validation on the exact implementation tree passed all 83 Strategy Lab v2
package tests, Ruff checks for the changed files, MyPy for the package, and
`git diff --check`. No provider, ETF, TC2000, persistence, API, worker,
Compose, Nautilus, frontend, integration, promotion, or deployment paths were
changed. The next bounded slice is the boundary-aware wiring for those existing
calendar/rolling/distribution aggregators.

## 2026-09-16 - Calendar-period boundary wiring checkpoint

Product commit `88cc14dda12aa43f49a18e5199248ec25e05283e` wires the explicit
flow-boundary path into `calculate_calendar_period_metrics()`. Complete
flow-bearing periods now report the geometrically linked return when all
pre/post marks are present; missing boundary evidence remains an explicit null
reason. Net P&L continues to reconcile the reported flow independently.

The exact package tree still passes all 83 tests, Ruff, and MyPy. The remaining
boundary-aware metric work is limited to rolling-window and session-distribution
aggregators; no shared provider, ETF, TC2000, persistence, API, worker,
Compose, Nautilus, frontend, integration, promotion, or deployment paths were
changed.

## 2026-09-16 - Rolling and distribution boundary wiring checkpoint

Product commit `f7bb6383bcdafb3695c07061b313fc7c71f6e9b5` completes the
boundary-aware metric wiring. Rolling windows now use geometrically linked
flow-adjusted returns and normalized wealth marks for volatility, Sharpe,
Sortino, drawdown, duration, and Ulcer calculations. Session-return
distributions use the same per-session factors and retain
`returns_flow_adjusted` provenance on the typed summary contract.

The exact implementation tree passed all 83 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`; the consolidated range was published under
the explicit destination authorization and local/remote HEAD match at
`f7bb6383bcdafb3695c07061b313fc7c71f6e9b5`. The next bounded engine-neutral
metric slice is capital/margin utilization or financing evidence. No provider,
ETF, TC2000, persistence, API, worker, Compose, Nautilus, frontend,
integration, promotion, or deployment paths were changed.

## 2026-09-16 - Engine-reported capital and margin utilization checkpoint

The next package-owned metric slice adds immutable
`AccountCapitalMarginObservation` records and
`calculate_capital_margin_utilization_metrics()`. Each observation binds a
portfolio version, run attempt, ordered engine point, positive account equity,
initial and maintenance requirements, supplied capacities, base currency, and
valuation evidence. The calculator emits equally sample-weighted means and
observed maxima for requirement-to-capacity and requirement-to-equity ratios.
It accepts ratios above one as diagnostics and never infers margin, leverage,
or buying power from notional exposure.

The exact implementation tree passed 85 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Financing evidence outside fill reports and
trusted paired inference remain open metric gaps. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Trial-bound evaluation-window checkpoint

The metric-scope slice adds immutable `EvaluationWindow` records with explicit
evaluation start/end, purpose, and optional warm-up start. The window is bound
into `ScientificTrial` identity and projected into `SensitivityMetricScope`;
`SensitivityComparisonEvidence` now rejects variants that use different
evaluation or warm-up windows. Offset-aware timestamps normalize to UTC and
invalid ranges fail closed.

The exact implementation tree passed 94 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Additional risk evidence and all persistence,
API, worker, and runtime gates remain open. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Explicit stress-scenario evidence checkpoint

The next engine-neutral risk slice adds `StressScenarioObservation` and
`calculate_stress_scenario_metrics()`. Adapter-supplied initial/stressed equity
and P&L must reconcile exactly and bind a shock-definition digest plus engine
evidence. The calculator emits descriptive scenario/loss counts, average and
worst stressed returns and P&L, and minimum stressed equity. It does not
construct shocks, extrapolate outcomes, or issue a solvency/risk verdict.

The exact implementation tree passed 94 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Metric-scope completeness and all persistence,
API, worker, and runtime gates remain open. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Explicit financing-cost evidence checkpoint

The next package-owned metric slice adds immutable
`FinancingCostObservation` events and bounded `FinancingCostReport` records.
`calculate_financing_cost_metrics()` keeps financing outside fill-cost reports,
tracks complete/partial/unavailable coverage explicitly, and publishes the
signed reported cash effect for all supplied events. It publishes derived net
financing cost only when every supplied report is complete; incomplete coverage
cannot be interpreted as zero financing. Report and event digests, model
identity, base currency, ordered points, and scope are bound to the metrics.

The exact implementation tree passed 88 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Trusted paired-stream inference remains the next
metric gap. No provider, ETF, TC2000, persistence, API, worker, Compose,
Nautilus, frontend, integration, promotion, or deployment paths were changed.

## 2026-09-16 - Aligned paired-observation metrics checkpoint

The next metric slice adds `PairedMetricObservation` and
`calculate_paired_metric_metrics()`. A verified keyed-stream receipt is
required; observations are keyed, deduplicated, canonically ordered, and
validated as finite Decimal baseline/variant values. The calculator emits
descriptive baseline/variant means, signed mean delta, nearest-rank median,
minimum/maximum delta, and sample standard deviation with receipt and input
digests. It intentionally does not rank candidates, estimate significance, or
claim an inferential model.

The exact implementation tree passed 91 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Metric-scope completeness, risk/stress evidence,
and all persistence/API/worker/runtime gates remain open. No provider, ETF,
TC2000, persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Keyed common-random stream verification checkpoint

The next engine-neutral slice adds `pairing.py` with typed
`KeyedRandomDraw` inputs and `verify_keyed_random_stream_pairing()`. The
verifier requires registered engine-build/conformance and stream-contract
digests, rejects empty, duplicate, unmatched, or value-mismatched draws, and
emits a deterministic `KeyedRandomStreamPairingReceipt`. Sensitivity evidence
can bind that receipt and is classified as `verified_paired`; the downstream
comparison remains descriptive and makes no significance or ranking claim.

The exact implementation tree passed 90 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Aligned per-observation inferential metrics,
ranking, significance, and all shared persistence/API/worker/runtime gates
remain open. No provider, ETF, TC2000, persistence, API, worker, Compose,
Nautilus, frontend, integration, promotion, or deployment paths were changed.

## 2026-09-16 - Static strategy-source preflight checkpoint

Product commit `ddac66de4` adds `strategy_validation.py`, a deterministic AST
preflight that binds every result to the exact source digest and rejects
disallowed or relative imports, filesystem/network roots, dynamic-code calls,
aliases of dangerous builtins, and private-object introspection. A forbidden
root remains rejected even when a caller attempts to broaden the allowlist. The
preflight is intentionally an early rejection layer, not the runtime security
boundary: isolated execution, no-network/read-only filesystem enforcement,
resource limits, secret exclusion, and adversarial container tests remain open.

The exact implementation tree passed all 100 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`; the product commit is published at the
authorized `origin/feat-strategy-lab-v2` destination. Persistence, API, worker,
artifact, Compose, Nautilus, frontend, integration, promotion, and deployment
paths remain unchanged. The next bounded slice is an engine-neutral
artifact/result-integrity contract while preserving this static-preflight and
runtime-isolation boundary.

## 2026-09-16 - Artifact payload integrity checkpoint

The next engine-neutral slice adds `artifacts.py` with raw-byte SHA-256 content
addressing and `ArtifactIntegrityReceipt`. `verify_artifact_payload()` compares
an already-read payload to its immutable manifest's digest and exact byte
length, returning deterministic `digest_mismatch` and/or
`byte_length_mismatch` evidence without retaining bytes or performing storage
I/O. Invalid payload types fail fast; retrieval, atomic publication, retention,
and worker/storage ownership remain deferred.

The exact implementation tree passed all 104 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Static source preflight remains an early
rejection layer rather than the runtime security boundary. Persistence, API,
worker, artifact-store, Compose, Nautilus, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Artifact publication-plan checkpoint

`artifact_publication.py` adds a storage-neutral publication decision that can
only be produced from a verified `ArtifactIntegrityReceipt`. It requires
immutable create-if-absent semantics, reuses an already-present content
address without overwriting it, and exposes pin requirements from the manifest
retention class. It performs no storage I/O and does not claim atomicity until a
future adapter implements and tests that operation.

The exact implementation tree passed all 107 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Runtime artifact storage, retention
enforcement, persistence, API, worker, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Result artifact integrity checkpoint

`result_integrity.py` adds a pure result-level verification contract for
successful `RunResultManifest` records. It requires one unique, verified
payload receipt for every referenced output artifact, reports missing,
unexpected, foreign, or unverified digests deterministically, and binds the
coverage result to the full manifest fingerprint. It performs no storage I/O
and does not certify engine semantics or publication atomicity.

The exact implementation tree passed all 107 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Execution-attempt lifecycle, persistence,
API, worker, artifact-store, Compose, Nautilus, frontend, integration,
promotion, and deployment paths remain unchanged.

## 2026-09-16 - Execution-attempt lease checkpoint

`lifecycle.py` now includes typed `ExecutionAttemptLease` records and
`acquire_attempt_lease()`. Leases can be acquired only by running attempts,
renew only while active with monotonic timestamps, and transition explicitly to
released or expired states. The pure contract supplies worker-side lease
evidence without persistence, scheduling, or automatic clock access; result
publication must still be guarded by a live lease in the future worker.

The exact implementation tree passed all 110 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Capability execution preflight, persistence,
API, worker, artifact-store, Compose, Nautilus, frontend, integration,
promotion, and deployment paths remain unchanged.

## 2026-09-16 - Engine capability-binding checkpoint

`execution_capabilities.py` adds a typed binding between the strict/degraded
data preflight and a registered engine build/conformance identity. Product,
execution-model, and account-model gaps fail closed; a non-authoritative engine
can provide compatibility evidence but cannot publish authoritative results.
The binding is engine-neutral and performs no runtime loading or execution.

The exact implementation tree passed all 113 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-event/result-state handling,
persistence, API, worker, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Forward event-state application checkpoint

`apply_forward_event_observation()` now applies classified canonical events to a
`ForwardInstance` without implicit replay or state loss. Contiguous accepted
events advance the stored event identity/sequence; gaps, duplicates, and
out-of-order events preserve the cursor; corrections increment an append-only
counter and retain the prior decision cursor. Event arrival timestamps remain
monotonic, and the function performs no persistence or external event I/O.

The exact implementation tree passed all 113 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-state persistence/idempotency,
database/API, workers, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Execution authorization-gate checkpoint

`execution.py` adds `authorize_execution()`, which composes accepted static
source validation, trial-bound capability evidence, matching running-attempt
identity, and an active worker lease into one immutable authorization record.
The gate fails closed on unsupported capability, mismatched trial/lease, bad
source, non-running attempts, expired leases, or non-monotonic timestamps. It
does not import or invoke an engine, access storage, or carry secrets.

The exact implementation tree passed all 116 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-state persistence/idempotency,
database/API, workers, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Forward checkpoint idempotency checkpoint

`forward_state.py` adds immutable, fingerprinted `ForwardStateCheckpoint`
records containing the `ForwardInstance`, processed/buffered/correction event
sets, and duplicate/out-of-order counters. `apply_checkpoint_observation()`
replays accepted, gap, and correction records idempotently, removes buffered
events only after contiguous acceptance, and never rewrites the decision
cursor for anomalies or corrections. It performs no persistence or event I/O.

The exact implementation tree passed all 120 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Worker dispatch/idempotency, database/API,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Worker dispatch idempotency checkpoint

`dispatch.py` adds immutable `DispatchRequest` and content-addressed
`DispatchEnvelope` records plus `resolve_idempotent_dispatch()`. Identical
idempotency keys replay the same attempt/payload/queue request; differing
payload or queue content returns an explicit conflict, and contradictory prior
records fail closed. The contract performs no Redis, outbox, or worker I/O;
atomic compare-and-set remains an adapter responsibility.

The exact implementation tree passed all 125 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Progress/cancellation, database/API,
workers, artifact-store, Compose, Nautilus, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Progress and cancellation checkpoint

`progress.py` adds typed ordered worker progress updates, idempotent
`CancellationRequest` records, and `ExecutionProgressState`. Progress totals
and completed units are monotonic, terminal states cannot be updated, and a
requested cancellation can only finish with an explicit cancelled terminal
update. These are storage-neutral control semantics for future resumable
workers; Redis, database persistence, and process interruption remain open.

The exact implementation tree passed all 129 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Retry/recovery, database/API, worker,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Attempt recovery and retry checkpoint

`recovery.py` adds a storage-neutral `RetryPolicy` and
`plan_attempt_recovery()` decision contract. Recovery validates one contiguous
terminal attempt chain, distinguishes retry/no-op/terminal outcomes, allows
only explicitly retryable infrastructure causes, caps deterministic exponential
backoff, content-addresses the resulting plan for idempotent scheduling, and
fails closed on active attempts, malformed chains, stale
timestamps, cancellation retries, or exhausted limits. A retry plan can
materialize a queued `RunAttempt` against the same immutable scientific trial;
durable scheduling, compare-and-set, worker restart, and engine disposal remain
adapter responsibilities.

The exact implementation tree passed all 133 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API, durable worker recovery,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Canonical execution event-stream checkpoint

`events.py` adds content-addressed `ExecutionEvent` envelopes, typed
`EventStreamCursor` records, and `resolve_event_append()`. Exact prior events
are replayable; a new event must be the next contiguous sequence, while gaps,
stale sequences, foreign streams, and identity conflicts fail closed or return
an explicit decision. The contract is storage- and transport-neutral so future
PostgreSQL/outbox/Redis adapters can perform atomic compare-and-set without
altering trial identity or invoking an engine.

The exact implementation tree passed all 137 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - API cursor and typed-error checkpoint

`api_contracts.py` adds snapshot-bound `ApiCursor` tokens, consistent
`CursorPage` envelopes, and immutable `ApiError` values. Cursor tokens are
deterministic URL-safe JSON envelopes with a content checksum and strict field
validation; pages cannot claim continuation without a matching cursor, and
errors expose stable codes, HTTP status, retryability, request identity, and
frozen details. These are router/persistence-neutral boundary contracts; the
checksum is not an authorization mechanism.

The exact implementation tree passed all 142 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Asynchronous submission/idempotency checkpoint

`submissions.py` adds immutable `SubmissionRequest`, `SubmissionReceipt`, and
`SubmissionResolution` contracts. Request fingerprints bind operation, attempt,
idempotency key, and payload digest while excluding submission timestamps, so a
transport retry replays the same accepted request. Resolution distinguishes
202 acceptance/replay from 409 idempotency conflict and fails closed when prior
receipts disagree; durable compare-and-set and dispatch remain adapter work.

The exact implementation tree passed all 147 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Asynchronous outcome/idempotency checkpoint

`outcomes.py` adds ordered `OutcomeUpdate` and `ExecutionOutcome` values for
accepted, running, succeeded, failed, and cancelled execution states. Updates
are bound to the original submission and attempt; successful outcomes require
an immutable result digest, failures carry a typed API error, and exact repeats
replay while stale, foreign, regressive, or conflicting updates fail closed.
The state transition helper performs no persistence or engine I/O.

The exact implementation tree passed all 151 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Artifact lineage/idempotency checkpoint

`lineage.py` adds immutable `ArtifactLineageEntry` edges and owner-scoped
`ArtifactLineageIndex` records. Semantic keys bind owner, role, parent, and
manifest identity while excluding recording time; exact edges replay, changed
metadata returns an explicit conflict, duplicate semantic keys are rejected,
and index ordering/fingerprints are deterministic. Persistence adapters remain
responsible for manifest foreign keys and atomic writes.

The exact implementation tree passed all 155 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Runtime-isolation preflight checkpoint

`runtime.py` adds pinned `RuntimeIsolationProfile` and execution-request
contracts plus `preflight_runtime_isolation()`. The preflight requires a
content-addressed runtime image, exact dependency pins, disabled network and
secrets, read-only root, dropped capabilities, and positive resource limits;
requested network/filesystem/secret access or unvetted dependencies produce
explicit rejection evidence. No container is started and no OS enforcement is
claimed; those remain isolated worker/runtime adapter responsibilities.

The exact implementation tree passed all 159 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Engine conformance and authoritative-release checkpoint

`conformance.py` adds `EngineConformanceEvidence` and
`EngineConformanceReport` with explicit required checks for multi-instrument
accounting, native order/fill/cost behavior, deterministic replay, lifecycle,
and forward event-tape parity. Missing checks fail closed; a complete release
candidate is compatible evidence only, while `authoritative` is true only for
a complete stable release. No engine is imported or started by this contract.

The exact implementation tree passed all 163 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus runtime, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Authoritative result-publication checkpoint

`result_publication.py` adds `plan_result_publication()`, composing stable
engine conformance, runtime isolation, exact result-manifest artifact coverage,
and engine-build identity. A valid plan publishes or replays an immutable
manifest; candidate/non-authoritative builds, mismatched evidence, failed
runtime isolation, and incomplete artifact receipts reject with explicit
reasons. No artifact store, database, queue, or engine is invoked.

The exact implementation tree passed all 166 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus runtime, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Restart-safe progress checkpoint

`progress_checkpoint.py` adds `ProgressCheckpoint` and
`apply_progress_checkpoint()`. Applied progress update identities are retained
for exact replay; only the next contiguous sequence advances the state, while
gaps and stale/conflicting updates return explicit decisions without mutation.
Terminal and cancellation semantics continue to be enforced by the existing
progress state machine, and persistence/transport remain adapter-owned.

The exact implementation tree passed all 170 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus runtime, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Worker lifecycle and serial-capacity checkpoint

`workers.py` adds immutable `WorkerProfile`, `WorkerReservation`, and
`WorkerPoolState` records for separately typed backtest and forward workers.
Each process is constrained to one concurrent engine node and must declare
runtime isolation and engine disposal. `reserve_worker_slot()` returns explicit
accept/replay/saturated/reject decisions with content-addressed reservation
identities; `release_worker_slot()` is idempotent and deterministically reopens
capacity. Unsafe profiles, reused identities, foreign reservations, and invalid
timestamps fail closed. Scheduling, durable compare-and-set, heartbeats,
restart recovery, process interruption, and actual engine disposal remain
adapter-owned.

The exact implementation tree passed all 174 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is
artifact retention/pinning semantics; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Artifact retention and pinning checkpoint

`artifact_retention.py` adds immutable `ArtifactRetentionPin` and
`ArtifactRetentionState` records bound to the exact artifact manifest. Pin
creation and release have explicit add/replay/conflict and idempotent-release
semantics. `resolve_artifact_retention()` evaluates permanent, pinned, tiered,
and ephemeral classes at a caller-supplied timestamp: pinned classes fail
closed without an active pin, active pins override expiry, and tier/expiry
eligibility is observable without deleting or moving bytes. Pin identities and
state ordering are deterministic; foreign manifests and invalid deadlines are
rejected.

The exact implementation tree passed all 182 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
worker heartbeat/lease-observation contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Worker lease-observation checkpoint

`lease_observations.py` adds ordered `LeaseObservation` envelopes for worker
heartbeats and releases plus `LeaseObservationState` and
`apply_lease_observation()`. Per-lease sequences apply only contiguously; exact
observation retries replay, reused identities conflict, and gaps/stale records
return explicit non-mutating decisions. Heartbeats fail closed after expiry or
release, release is terminal and replay-safe, and state validates monotonic
timestamps plus lease/heartbeat identity. Durable compare-and-set, process
clocks, scheduling, and persistence remain adapter-owned.

The exact implementation tree passed all 190 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
forward warm-up/replay handoff contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Forward warm-up handoff checkpoint

`forward_warmup.py` adds immutable `ForwardWarmupReceipt` values and
`resolve_forward_warmup()`. Receipts bind the forward instance, frozen warm-up
snapshot, declared carry-in mode, completion timestamp, and engine-state
fingerprint. A receipt can complete only a `WARMING_UP` instance once and seeds
the historical cursor; an exact existing receipt replays without rewriting
live state. Snapshot/mode mismatches, stale completion, existing cursor
overwrite, invalid final sequence identity, and changed receipt content fail
closed. No engine, storage, or event transport is invoked.

The exact implementation tree passed all 198 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
forward live-event admission/replay contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Forward live-event admission checkpoint

`forward_admission.py` adds `ForwardLiveAdmissionState`, content-addressed
`ForwardSeenEvent` identities, and `admit_forward_event()`. Live admission is
allowed only for an active post-warm-up instance and seeds its checkpoint from
the exact warm-up receipt. Newly observed events are retained by identity so
exact retries replay and changed content conflicts; contiguous events advance,
gaps buffer and later reconcile, and duplicate/out-of-order/correction
outcomes remain observable without rewriting prior decisions.

The exact implementation tree passed all 204 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
result-artifact commit/finalization contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Result-artifact commit/finalization checkpoint

`artifact_commit.py` adds immutable `ArtifactCommitRecord` and
`ArtifactCommitLedger` records plus `finalize_artifact_commit()`. A verified
create-if-absent plan commits one content-addressed storage key; the same
manifest/content retries replay the committed record independent of timestamp.
Storage-key collisions with another manifest conflict, and a reuse-existing
plan fails closed until a committed record is present. Ledger ordering and
commit keys are deterministic; no bytes, storage metadata, or retention state
are mutated by the pure contract.

The exact implementation tree passed all 209 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
execution-summary/read-model contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Execution summary/read-model checkpoint

`execution_summary.py` adds `ExecutionSummary` and
`build_execution_summary()`, projecting a submission receipt, typed outcome,
progress checkpoint, and optional authoritative publication plan into one
immutable machine-facing view. Submission/attempt identities and
outcome/progress phases must agree; successful summaries require a published or
replayed result whose digest matches the outcome, while failed/cancelled
summaries require matching terminal progress and never expose a result. The
summary exposes ready/in-progress/terminal decisions and a deterministic
fingerprint without mutable engine handles.

The exact implementation tree passed all 217 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
retry/cancellation command contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Retry and cancellation command checkpoint

`commands.py` adds content-addressed `ExecutionCommand` intents,
`ExecutionCommandReceipt` records, and an idempotent command ledger. A cancel
command is accepted only for a non-terminal execution, while a retry command
requires failed outcome and progress. Exact command retries replay, changed
content conflicts, terminal/non-failed preconditions and identity mismatches
reject, and accepted receipts describe a requested effect without claiming
that cancellation, scheduling, or worker interruption has occurred.

The exact implementation tree passed all 224 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
capability/report projection contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Capability/report projection checkpoint

`capability_summary.py` adds `CapabilitySummary` and
`build_capability_summary()`, composing the existing data `PreflightReport`
with `ExecutionCapabilityPreflight`. Instrument-scoped data gaps and engine
model gaps remain separate, degradation evidence is retained, and executable,
ranking-eligible, and authoritative-publication flags are derived only from
the underlying fail-closed decisions. Report identity mismatches reject before
projection; no providers or engines are invoked.

The exact implementation tree passed all 229 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
forward correction/replay command contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Forward counterfactual-replay checkpoint

`forward_corrections.py` adds `ForwardCorrectionCommand`,
`CounterfactualReplayPlan`, and `resolve_forward_correction()`. Only an
admitted correction event can produce a plan; the command binds the original
and correction identities, warm-up receipt, and an immutable pre-correction
checkpoint fingerprint. Exact existing plans replay, changed identities
conflict, and unadmitted, mismatched, or non-correction observations reject.
The live admission state is never rewritten and no replay engine is invoked.

The exact implementation tree passed all 235 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
execution-audit/event-journal contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Execution audit journal checkpoint

`audit.py` adds immutable aggregate-scoped `AuditEntry` and `AuditJournal`
records plus `append_audit_entry()`. Entries bind typed audit kinds, payload
digests, actor/correlation identity, timestamps, and contiguous sequence
numbers. Exact entries replay idempotently; missing sequence numbers produce a
gap, same-sequence content conflicts remain explicit, and foreign aggregates
or timestamp regressions reject without changing the journal. The contract is
storage/outbox neutral and does not claim that an audit record was durably
written or transported.

The exact implementation tree passed all 242 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable-adapter boundary for this journal; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Transactional outbox checkpoint

`outbox.py` adds immutable `OutboxMessage` and `OutboxState` records plus pure
enqueue and acknowledgement resolutions. Request identities conflict when
their semantic payload changes, identical content deduplicates even across
request retries, pending messages have deterministic availability ordering,
and publish acknowledgements are idempotent. Scheduling timestamps are retained
in the record but excluded from content identity. Unknown acknowledgements and
invalid state are rejected without mutation; PostgreSQL transactionality and
Redis transport remain future adapter responsibilities.

The exact implementation tree passed all 250 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable-adapter boundary over the journal/outbox contracts; preserve all
shared-path and execution-authorization gates.

## 2026-09-16 - Atomic audit/outbox staging checkpoint

`audit_outbox.py` adds `stage_audit_outbox()`, linking one audit entry to its
content-addressed outbox envelope. The event identity must match exactly;
append/enqueue gaps, conflicts, and rejects return the original journal and
outbox states so a future database adapter cannot commit only one side. Safe
append/enqueue combinations produce a single pair of states for one database
transaction, and exact retries replay without mutation. No persistence,
transport, or delivery claim is made here.

The exact implementation tree passed all 256 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Legacy preservation/import checkpoint

`legacy.py` adds digest-only `LegacyRecord` preservation, explicit import
requests, adapter-supplied compatibility assessments, an immutable import
registry, and `LegacyImportReport` results. Supported definitions/results retain
the original record and expose a converted identity; unsupported records remain
inspectable with explicit notes. Exact retries replay, changed payload or
mapping content conflicts, preservation cannot be disabled, and reports reject
any replay-equivalence claim. The contract never replays legacy strategies or
reads legacy storage.

The exact implementation tree passed all 263 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Resumable search-candidate checkpoint

`search_state.py` adds immutable `SearchCandidateState` and
`SearchExecutionState` records plus start, terminal-receipt, and cancellation
resolutions. Candidate scientific trial identities remain fixed while failed
infrastructure attempts can retry with incremented attempt lineage. Active
attempt and terminal-receipt conflicts reject, exact repeats replay, and
monotonic timestamps are enforced. Cancellation is idempotent, blocks new
starts, and requires workers to publish explicit cancelled receipts; it does
not rank candidates or issue profitability claims.

The exact implementation tree passed all 270 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Coverage attestation verification checkpoint

`coverage.py` adds immutable `CoverageAttestation` and
`CoverageVerificationReport` records plus `verify_coverage_attestation()`.
Provider-adapter claims are compared against every frozen series identity:
evidence/content digests, instrument and event semantics, interval, row count,
session/feed, adjustment and corporate-action policy, completeness, and gap
status. Any mismatch or incomplete/gapped claim rejects with stable reasons;
matching evidence verifies deterministically. No provider, repair, calendar, or
execution I/O is performed, and a report is not an execution authorization by
itself.

The exact implementation tree passed all 288 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
strategy-runtime contract only within the package-owned boundary; preserve all
execution-authorization and ownership gates.

## 2026-09-16 - Strategy-runtime request/receipt checkpoint

`runtime_execution.py` adds immutable `StrategyRuntimeRequest`,
`StrategyRuntimePreflight`, `RuntimeExecutionState`, and ordered update
receipts. Requests bind package/source/input digests, declared entrypoint,
attempt, and isolation profile; preflight reuses the fail-closed isolation
report and rejects profile identity drift. Runtime states require an allowed
preflight, replay exact updates, reject sequence/time/identity conflicts, and
enforce the output-byte budget before a success can be recorded. This is an
engine-neutral protocol only: container limits, process lifecycle, and engine
execution remain future isolated-worker adapter responsibilities.

The exact implementation tree passed all 295 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Conformance fixture evidence checkpoint

`conformance_fixtures.py` adds typed expected/observed digest observations and a
deterministically ordered fixture suite for all required engine checks. Passed
checks require matching identities, failed checks require differing identities,
duplicate/partial suites fail closed, and complete suites build the existing
`EngineConformanceEvidence` with a suite-bound fingerprint. This strengthens the
Nautilus stable-release gate without importing, starting, or enabling an engine.

The exact implementation tree passed all 301 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Execution admission checkpoint

`admission.py` adds an immutable admission intent, receipt, ledger, and
resolution that compose the existing execution authorization, accepted strategy
runtime preflight, and serial worker-capacity contracts. An admission binds one
attempt to one worker profile and reservation, preserves authoritative-result
eligibility, and returns ledger/pool states together for an adapter-side atomic
write. Exact retries replay only when the matching reservation remains active;
capacity saturation, profile or worker drift, conflicting attempt content, an
unaccepted runtime, and a reservation without a receipt fail closed. No queue,
persistence, process, or engine I/O is performed.

The exact implementation tree passed all 306 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic search-dispatch checkpoint

`search_dispatch.py` adds a storage-neutral composition of candidate start,
execution admission, serial worker capacity, and dispatch idempotency. The
resolution returns the original search, admission, and worker states whenever a
later gate rejects, saturates, or conflicts, so adapters cannot persist an
orphaned running candidate or worker reservation. Exact retries replay all
three layers; a newly admitted attempt cannot reuse an existing queue message
without an admission receipt. Queue/database publication remains outside this
package.

The exact implementation tree passed all 310 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker recovery checkpoint

`worker_recovery.py` adds a pure composition of admission evidence, lease
identity/status, serial worker reservation release, and the existing bounded
retry planner. Crash, expiry, transient, and artifact-publication failures
release the worker slot and can materialize a new queued attempt linked to the
same scientific trial. Successful attempts become no-ops; cancellation and
exhausted/non-retryable failures become terminal without retry. Missing
admission/worker evidence, invalid lease-expiry claims, and absent retry
identities fail closed. Attempt persistence, scheduling, and engine lifecycle
remain adapter responsibilities.

The exact implementation tree passed all 314 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic result-completion checkpoint

`result_completion.py` adds terminal completion evidence for a backtest attempt
and its output artifacts. It requires successful runtime, outcome, and complete
progress states plus an accepted publication plan; it then resolves every
content-addressed artifact commit against a working ledger while returning the
original ledger on any conflict or rejection. Completion receipts bind the
attempt, result, runtime/outcome/progress identities, publication, and commit
keys; exact retries replay only when all referenced commits are still present,
and publication replay without a completion receipt fails closed. No bytes,
database rows, queues, processes, or engines are touched.

The exact implementation tree passed all 318 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic forward-event transaction checkpoint

`forward_event_transaction.py` adds an all-or-nothing live-event boundary over
the existing forward admission and counterfactual-correction contracts.
Accepted, gap, duplicate, and out-of-order events retain their explicit
decisions. A correction event requires a matching replay command and a
content-addressed replay plan; command/event conflicts, missing evidence, and
invalid non-correction replay input return the original live checkpoint. Exact
correction retries replay the plan without incrementing correction state again.
This remains broker-free and storage/engine neutral.

The exact implementation tree passed all 323 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Forward event dispatch checkpoint

`forward_event_dispatch.py` composes the forward event/correction transaction
with content-bound worker dispatch. Accepted events and buffered gaps enqueue
worker envelopes; duplicates and out-of-order observations remain
non-dispatching. Correction envelopes bind the separately identified replay
plan, and payload drift or queue idempotency conflicts return the original live
checkpoint rather than publishing an orphaned message. Exact retries replay the
dispatch evidence. Queue transport and persistence remain adapter-owned.

The exact implementation tree passed all 327 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic execution-event transaction checkpoint

`execution_event_transaction.py` links canonical execution-event append
resolution with the append-only audit journal and transactional outbox. The
contract enforces event-to-audit correlation and audit-to-outbox identity,
returns the original cursor/journal/outbox on any gap, conflict, or rejection,
and exposes exact all-stream replay only when every linked record is already
present. It remains an immutable adapter boundary: compare-and-set persistence,
outbox transport, worker entrypoints, and engine execution are not performed.

The exact implementation tree passed all 334 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Typed API resource envelope checkpoint

`api_resources.py` adds immutable public resource identifiers/documents and
snapshot-bound collection envelopes over the existing cursor and typed-error
contracts. Resource types, item identities, relationship targets, opaque
cursor resource, and snapshot digest must agree; mutable JSON fields are
recursively frozen and every envelope has a deterministic content identity.
The module remains route- and persistence-neutral, so no shared router or
frontend path was modified.

The exact implementation tree passed all 339 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Compare-and-set storage contract checkpoint

`storage.py` adds the persistence-facing boundary for versioned aggregate
snapshots. Mutations carry create or compare-and-set preconditions, transaction
requests are content-addressed and deterministically ordered, and receipts make
retries idempotent. Missing aggregates, version/state drift, create collisions,
and contradictory historical receipts fail closed while preserving the
original aggregate set. A future PostgreSQL adapter can map this plan to one
transaction; no database, Redis, or filesystem I/O occurs here.

The exact implementation tree passed all 346 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Local content-addressed artifact store checkpoint

`artifact_store.py` adds the local filesystem adapter for immutable raw-byte
artifacts. It verifies the requested manifest before writing, publishes through
same-directory temporary files and atomic hard-links without replacing an
existing digest, deduplicates races, sets published files read-only, and
re-verifies bytes on every read. Corrupt, non-regular, symlinked, or escaping
paths fail closed; manifest/commit metadata remains the responsibility of the
existing pure contracts.

The exact implementation tree passed all 352 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Hardened sandbox command-plan checkpoint

`sandbox.py` adds the worker-facing Docker invocation plan after the existing
runtime isolation preflight. It pins the image digest and emits argv without a
shell, disables networking, makes the root read-only, drops all capabilities,
blocks privilege escalation and secrets, runs unprivileged, mounts input
read-only, and applies memory/CPU/file/PID/output limits. Host timeout handling
and process execution remain explicit adapter responsibilities; no container is
started by this module.

The exact implementation tree passed all 356 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Bounded sandbox execution adapter checkpoint

`sandbox_execution.py` closes the worker-side process boundary after sandbox
command planning. It executes only argv with `shell=False`, starts a separate
process group, passes a minimal environment without inherited secrets, caps
captured stdout/stderr, kills the group on output overflow or wall timeout, and
returns typed content-addressed run evidence for success, failure, timeout,
overflow, or start errors. Docker invocation and engine lifecycle remain
adapter-owned; no Nautilus process is started by the tests.

The exact implementation tree passed all 361 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Nautilus execution-gating checkpoint

`engine_execution.py` adds the final pre-invocation gate for the authoritative
simulator. It binds execution authorization, accepted runtime isolation,
content-matched sandbox argv, data-snapshot identity, and complete engine
conformance evidence. Non-Nautilus engines, failed/incomplete conformance,
runtime or sandbox drift, and non-authoritative stable-release attempts fail
closed; compatible release candidates may run only when explicitly requested as
non-authoritative. The contract does not start an engine.

The exact implementation tree passed all 366 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic Redis dispatch transport checkpoint

`redis_transport.py` adds the transport-side Redis Streams adapter for dispatch
envelopes. A Lua compare-and-set script binds each idempotency key to the exact
envelope content and appends one stream entry atomically; retries replay,
changed content conflicts, and failed stream writes roll back their marker.
Redis carries transport evidence only—the authoritative outbox and aggregate
state remain PostgreSQL adapter responsibilities.

The exact implementation tree passed all 372 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Redis consumer-group transport checkpoint

`redis_transport.py` now completes the Redis-side worker transport contract
around the atomic publisher. Consumer groups are created idempotently (including
`BUSYGROUP` replay), new entries are decoded into typed content-addressed
records, idle pending entries can be reclaimed after restart or lease expiry,
and acknowledgements return typed success/failure evidence. Redis remains
transport-only; PostgreSQL persistence and the transactional outbox remain the
authoritative state boundary.

The exact implementation tree passed all 375 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Outbox-to-Redis relay checkpoint

`outbox_relay.py` binds the authoritative outbox contract to the Redis Streams
publisher. It derives a deterministic transport envelope from an outbox
message's semantic identity, publishes through the existing atomic enqueue
adapter, and proposes the outbox `published_message_ids` update only after an
enqueue or exact replay. If Redis rejects or conflicts, the original pending
outbox state is returned unchanged; if a worker crashes after Redis publication
but before the database compare-and-set, the next relay observes a replay and
can safely stage the acknowledgement.

The exact implementation tree passed all 383 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Bounded Redis worker-pump checkpoint

`worker_consumer.py` adds the bounded consumer-side orchestration around the
Redis group/relay contracts. Each poll ensures the group, reclaims idle pending
entries before reading new work, and caps the batch. Each handler must return a
content-matched receipt; only a completed receipt is acknowledged. Retry,
rejection, handler-content drift, and acknowledgement failures preserve the
pending delivery and return typed evidence, leaving authoritative state and
isolated engine execution to the handler/worker adapter.

The exact implementation tree passed all 389 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - PostgreSQL compare-and-set adapter checkpoint

`postgres_storage.py` maps the package-owned aggregate transaction contract to
one SQLAlchemy async transaction. It locks requested aggregate and receipt rows,
round-trips canonical state (including tuples and `None`) without changing its
content identity, uses guarded inserts/updates and idempotent receipts, and
rolls back when a concurrent write wins. The module exposes the future additive
schema contract but never creates tables or registers shared ORM models; schema
migrations and application wiring remain explicitly deferred gates.

The exact implementation tree passed all 394 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Gated Nautilus runner checkpoint

`nautilus_runner.py` closes the process handoff after `plan_nautilus_execution`
and before a future isolated Nautilus worker. It refuses rejected plans,
non-Nautilus identities, and sandbox-plan drift without spawning; ready plans
delegate exclusively to the bounded sandbox adapter. Sandbox success/failure,
timeouts, output limits, and start errors remain content-bound, and the
authoritative flag is preserved only for a successful plan already cleared by
the stable-conformance gate.

The exact implementation tree passed all 399 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Runtime-result materialization checkpoint

`runtime_result_adapter.py` materializes one bounded sandbox terminal result into
the existing monotonic runtime state. It verifies command-plan and runtime-
request identity, records bounded stdout digest/size for success or typed error
identity for failure, transitions through running to terminal state, replays
exact terminal evidence, and rejects conflicting terminal evidence. This
remains runtime evidence only; official result artifacts still require result
publication gates.

The exact implementation tree passed all 403 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Execution-handoff orchestration checkpoint

`execution_orchestration.py` binds authorization, worker admission, runtime
preflight/state, sandbox planning, and the gated Nautilus plan into one
immutable worker handoff. The plan verifies every cross-contract identity,
requires an accepted sequence-zero runtime state, keeps the declared output
limit unchanged, and preserves authoritative eligibility only when admission
and the engine gate agree. Identity drift, an already-started runtime,
unauthorized authority, and rejected engine plans fail closed before a process
or queue adapter is invoked.

The exact implementation tree passed all 407 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Nautilus-result runtime bridge checkpoint

`runtime_result_adapter.py` now accepts an executed `NautilusRunResult` only
after verifying the execution-plan and sandbox-plan identities, matching the
runner and sandbox statuses, and checking the authoritative flag against the
gated plan. Rejected pre-process Nautilus plans are refused without a synthetic
runtime failure; executed evidence then follows the existing bounded,
idempotent sandbox-to-runtime materialization path.

The exact implementation tree passed all 409 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Engine-result materialization checkpoint

`result_materialization.py` adds an engine-neutral result adapter that binds
typed engine evidence to the immutable `RunResultManifest` required by the
publication and completion gates. It verifies trial/attempt, metric, snapshot,
strategy-package, and output-artifact identities, preserves engine/build and
dependency provenance, replays an exact existing manifest, and conflicts on
changed content. It performs no artifact writes or publication and does not
claim engine authority by itself.

The exact implementation tree passed all 413 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Canonical result-evidence ordering checkpoint

Result materialization now canonicalizes strategy-package and output-artifact
ordering before provenance comparison, matching the manifest's deterministic
ordering. A regression test confirms artifact evidence is order-independent
while preserving content identity and conflict detection.

The exact implementation tree passed all 414 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Terminal outcome/progress materialization checkpoint

`execution_terminal.py` projects one terminal `RuntimeExecutionState` into the
public `ExecutionOutcome` and `ExecutionProgressState` streams as an atomic
storage-neutral proposal. Successful runtimes require an attempt-bound
`RunResultManifest`; failures require a typed `ApiError`; cancellation requires
the persisted cancellation request. Matching terminal evidence replays without
rewriting state, while half-terminal, contradictory, stale, or cross-attempt
records fail closed.

The exact implementation tree passed all 418 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker-handoff execution checkpoint

`worker_execution.py` composes the immutable execution handoff with the gated
Nautilus runner and runtime-result bridge. It revalidates every handoff
identity immediately before process creation, refuses stale or rejected plans
without spawning, and returns typed Nautilus plus runtime evidence for a future
compare-and-set transaction. Process failures become runtime failures; no queue,
database, result publication, or engine bypass is introduced.

The exact implementation tree passed all 422 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker-capacity settlement checkpoint

`worker_settlement.py` closes one admitted worker reservation after a bounded
worker handoff. It binds the execution evidence to the admission and
orchestration plan, checks the worker profile and reservation identity, and
returns an immutable pool plus append-only settlement ledger proposal. Both
successful process results and pre-process handoff rejections release capacity,
while exact retries replay only when the reservation is already released with
matching evidence. Changed release evidence, a missing or mismatched
reservation, an active pool alongside an existing receipt, and release times
before acquisition are rejected without partial state changes.

The exact implementation tree passed all 426 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Active worker reservation launch gate checkpoint

`worker_execution.py` now requires the current `WorkerPoolState` at the process
boundary. Immediately before the gated Nautilus runner is invoked it verifies
the admission's worker id, kind, runtime profile, and active reservation, and
rejects released, missing, mismatched, or not-yet-acquired capacity without
spawning a process. This keeps serial capacity a launch-time invariant rather
than relying only on an earlier admission receipt; settlement remains the
storage-neutral release path after the handoff completes.

The exact implementation tree passed all 427 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

The worker resolution contract also now rejects a contradictory terminal
decision/runtime-result pair, so a forged success/failure label cannot reach
capacity settlement or later result publication.

## 2026-09-16 - Atomic lease-release settlement checkpoint

Worker settlement now also applies a deterministic ordered
`LeaseObservationKind.RELEASE` to the supplied `LeaseObservationState` and
returns that state alongside the released pool and settlement ledger. Exact
retries require both the pool reservation and lease observation to be already
released with matching evidence. Expired or already-released leases are
rejected and left for the existing recovery path, preventing a late process
from presenting itself as an authoritative normal completion.

The exact implementation tree passed all 428 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Launch-time lease gate checkpoint

`execute_worker_handoff` now accepts an explicit start instant and
`LeaseObservationState`. It verifies the lease is active at process creation,
rejects observations that precede the start, and refuses to materialize process
evidence after lease expiry; late results retain process evidence for explicit
recovery instead of becoming normal runtime success/failure. Worker pool,
reservation, and lease identities remain checked together immediately before
the runner call.

The exact implementation tree passed all 429 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Lease-expiry completion rejection checkpoint

When a bounded Nautilus process returns after its lease has expired,
`execute_worker_handoff` preserves the process evidence but returns a typed
rejection without materializing runtime state. This keeps late output available
to the explicit crash/expiry recovery path while preventing an expired lease
from publishing normal success or failure. Launch-time and completion-time
lease checks are both exercised without starting any process for stale launch
inputs.

The exact implementation tree passed all 430 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic worker-terminal settlement checkpoint

`worker_terminal.py` composes terminal outcome/progress materialization with
worker pool and lease settlement. It returns one committed storage-neutral
proposal only when both sides accept, preserving every original state when a
result is missing, a lease has expired, capacity conflicts, or the handoff has
no runtime terminal evidence. Exact retries replay only when the terminal
public states and worker settlement receipts both match; pre-process worker
rejections remain owned by recovery.

The exact implementation tree passed all 433 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Lease-aware idempotent recovery checkpoint

The recovery ledger now binds an ordered lease-release observation as well as
the worker reservation release. Recovery returns the updated lease state, so
crash, expiry, transient, cancellation, and successful/no-op paths cannot leave
capacity and lease records split. Exact retries replay against the released
pool and matching observation; changed recovery content or an active/missing
lease observation is rejected. Expired leases remain eligible only for the
explicit recovery reason and never become normal successful completions.

The exact implementation tree passed all 428 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Idempotent recovery ledger checkpoint

`worker_recovery.py` now accepts an append-only `WorkerRecoveryLedger` and
records the recovery plan, reservation release, retry identity, and observation
time as one content-addressed receipt. An exact repeated crash/expiry/transient
resolution replays the existing released pool and queued retry; changed plan,
reason, retry identity, or release evidence returns a conflict, and a receipt
cannot replay against a still-active pool reservation. Recovery remains
infrastructure-only and never transitions attempts, schedules queues, or starts
an engine.

The exact implementation tree passed all 428 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker-terminal release ordering checkpoint

`materialize_worker_terminal` now rejects a first-time worker release whose
timestamp precedes terminal evidence, preventing capacity and lease state from
appearing released before process completion was observed. Existing terminal
and settlement receipts remain replayable when a later retry arrives, while
changed release evidence still follows the settlement conflict path.

The exact implementation tree passed all 434 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic submission-dispatch staging checkpoint

`submission_dispatch.py` now composes asynchronous submission idempotency with
the matching worker dispatch envelope. It requires the same attempt,
idempotency key, and payload identity on both sides; a receipt retry can repair
a dispatch lost after receipt persistence, while a dispatch without a tracked
submission is rejected. The immutable receipt ledger and dispatch proposal are
returned together for one future compare-and-set transaction; no route, queue,
or database I/O is performed by the package contract.

The exact implementation tree passed all 439 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Snapshot coverage verification checkpoint

`snapshot_coverage.py` now composes per-series coverage attestation checks into
one snapshot-bound admission result. It requires exactly one attestation for
each frozen series, rejects missing, duplicate, unexpected, incomplete, or
semantically mismatched evidence, and preserves deterministic report and
attestation identities. Provider acquisition and execution adapters still own
fetching the evidence and enforcing this receipt before a run starts.

The exact implementation tree passed all 443 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Cash-equity order sizing and routing checkpoint

`order_routing.py` now accepts explicit `OrderIntent` values only after an
adapter supplies digest-bound instrument economics. It validates base/quote
currency, lot and tick alignment, minimum quantity, supported product risk
model, snapshot/economics identity, and declared component scope, then computes
an auditable estimated signed base notional. The pre-order exposure is combined
with all order deltas and passed through the shared all-or-nothing gross, net,
concentration, leverage, open-instrument, and short-position gate. A risk
breach withholds every routed order; approved values remain engine-neutral
estimates and never imply a fill or submit an order. Only the registered
cash-equity market-value model is supported; futures, options, FX, crypto, and
other product models remain explicitly rejected pending their own semantics.

The exact implementation tree passed all 451 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Registered product-risk valuation checkpoint

`contracts.py` now publishes exact content-addressed risk-model definitions for
cash equity, crypto spot, futures contract notional, option delta-adjusted
underlying notional, and FX pair notional. `risk_models.py` applies those
versioned formulas only to adapter-verified economics and emits a signed
base-notional receipt; option exposure explicitly binds underlying mark and
delta, while all formulas remain estimates rather than fills or margin/liquidity
claims. Allocation and order routing accept only these exact registered models
and the policy/snapshot binding must agree, so arbitrary digests and other
products still fail closed.

The exact implementation tree passed all 458 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied margin-capacity gate checkpoint

`margin_risk.py` now layers a deterministic margin gate over a routed order
decision. An adapter supplies event-aligned initial/maintenance requirements and
capacities with a valuation-evidence digest; the contract computes both
utilization ratios, records capacity and policy breaches, and withholds every
order when the upstream order-risk or margin gate fails. Snapshot, portfolio,
event, and policy identities must match exactly. The gate deliberately does not
infer margin from notional exposure and does not issue a solvency, liquidity, or
profitability verdict.

The exact implementation tree passed all 463 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Descriptive result-ranking checkpoint

`ranking.py` now provides a deterministic analysis view over completed
`RunResultManifest` values. It anchors one experiment and compatible snapshot,
portfolio, engine, allocation, metric-set, unit, and structured calculation
context; ties use immutable trial identities. Degraded preflight results remain
excluded by default, and missing, null, unversioned, incompatible, and duplicate
scientific-trial results are retained as explicit exclusions. The output is a
descriptive ordering only and makes no profitability, significance, or paired-
inference claim.

The exact implementation tree passed all 468 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied stress-risk gate checkpoint

`stress_risk.py` now layers an explicit stressed-equity gate over the margin and
order-routing decisions. Each scenario binds a shock-definition digest,
base/stressed equity values, and valuation evidence at the same event boundary;
loss-fraction and minimum-equity ceilings are evaluated deterministically, and
any breach withholds every routed order. Upstream margin/order rejection is
preserved without fabricating stress evidence. Shock construction, liquidity,
settlement, and solvency/profitability verdicts remain outside this contract.

The exact implementation tree passed all 473 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied liquidity gate checkpoint

`liquidity_risk.py` now layers an explicit liquidity gate over stress, margin,
and order routing. Each instrument capacity binds available quantity, available
base notional, estimated slippage, and valuation evidence. The gate aggregates
the full routed batch per instrument, rejects missing capacity, and withholds
every order on participation or slippage breaches while preserving upstream
rejections. It does not infer volume, construct fills, or promise execution
quality.

The exact implementation tree passed all 478 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied settlement-cash gate checkpoint

`settlement_risk.py` now layers an explicit settlement gate over liquidity,
stress, margin, and order routing. Adapters bind each exact routed order to a
signed settlement cash delta, currency, settlement time, and valuation evidence,
alongside per-currency free-cash capacity. The gate withholds the complete
batch on missing estimates/capacity, gross debit exhaustion, or a configured
minimum remaining-cash buffer while preserving upstream rejection. It does not
infer product cash flows, conversions, or settlement behavior.

The exact implementation tree passed all 484 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Deterministic shock-definition checkpoint

`shock_construction.py` now expands caller-supplied typed shock dimensions into
stable Cartesian-product definitions. Every scenario and leg is immutable and
content-addressed, duplicate or ambiguous dimensions are rejected, and matrix
size is bounded explicitly. The package does not apply shocks to prices or
positions, infer cross-asset effects, or calculate stressed equity; adapters
must use these identities when producing stress observations.

The exact implementation tree passed all 489 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Composed pre-engine risk-admission checkpoint

`risk_pipeline.py` now evaluates the fixed routing, margin, stress, liquidity,
and settlement sequence and verifies each decision's content-addressed parent.
The resulting immutable `TradeRiskAdmission` exposes every layer for audit but
only releases the complete routed batch when all gates approve; no partial order
approval, engine submission, or fill claim is possible.

The exact implementation tree passed all 493 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Combined backend coverage audit

`make test-backend-coverage` completed all 1,647 unit/integration tests, but the
repository's required 75% combined coverage gate failed at 58.77%. The new
`app/strategy_lab_v2` tests are deliberately kept in their package-owned test
tree and are not collected by the existing `tests/unit` plus `tests/integration`
target, so the v2 package is reported as uncovered by that command. This is a
real shared-gate reconciliation item; no coverage exclusion or product-code
change was made to conceal it. The focused v2 evidence remains 493 passing tests
with Ruff, MyPy, and diff checks green.

The next implementation context must reconcile how package-owned v2 tests enter
the full backend coverage gate without violating provider/ETF/TC2000 ownership
or changing the required coverage meaning. Until then, the branch remains
ready-for-human-review only, not full-integration green.

## 2026-09-16 - Combined backend coverage gate reconciled

The shared `Makefile` `test-backend-coverage` target now includes the
package-owned `app/strategy_lab_v2/tests` path alongside `tests/unit` and
`tests/integration`. This is a collection-only change: it preserves the
repository's 75% threshold, adds no exclusions, and leaves provider/ETF/TC2000
test ownership unchanged.

The exact target completed 2,140 tests with 86 warnings and total coverage of
82.98%, exceeding the required 75% gate. Docker-backed setup and cleanup both
completed successfully. Focused package tests, Ruff, MyPy, and diff checks remain
green. This closes the collection gap but does not claim full integration:
schema/API/worker/Compose wiring, stable Nautilus activation, upstream
reconciliation, frontend work, promotion, and deployment remain deferred.

The next bounded slice remains inside the engine-neutral package-owned boundary;
the Makefile change is shared-path material that must be reconciled line by line
when this branch enters staging.

## 2026-09-16 - Branch-declared test runner repaired

The workstream `branch_tests` entries were previously prose descriptions, but
`scripts/run-branch-tests.py` executes each entry as a shell command. That made
the branch CI test stage fail before reaching any Strategy Lab checks. The plan
now declares only executable checks for the implemented scope: the 493-test v2
package suite, Ruff, MyPy, `git diff --check`, and workstream validation. The
deferred database/migration, API, worker, Nautilus, Compose, and full exact-tip
integration requirements remain documented as gates rather than pretending to
be runnable branch commands.

`make branch-tests INTEGRATION_BRANCH=feat/strategy-lab-v2` now passes all five
checks. This repair changes only the branch-owned plan metadata; no provider,
ETF, TC2000, or runtime source paths were modified.

## 2026-09-16 - Engine-neutral core review boundary

The package-owned implementation context is green and the workstream is now
`ready_for_human_review`. The branch contains the immutable engine-neutral
domain/SDK, deterministic search and walk-forward contracts, provenance-bound
metrics and artifacts, forward-state semantics, execution isolation/admission,
worker/retry/outbox contracts, and the composed pre-engine risk pipeline. The
combined backend coverage and executable branch-test gates are green at the
exact synchronized tip.

This status is a review boundary, not a claim that the production backend is
complete. Additive schema/API registration, provider acquisition wiring,
durable worker entrypoints, Compose services, isolated runtime deployment, and
stable Nautilus v2 execution remain open. They must begin only after the
provider-platform, ETF, and TC2000 branches reach staging and their shared
paths are reconciled line by line.

## 2026-09-16 - Provider-neutral acquisition handoff checkpoint

`data_acquisition.py` now defines the package-owned handoff between a typed
capability preflight and a provider-produced frozen snapshot. A receipt binds
the request, snapshot IDs/fingerprint, snapshot-level coverage verification,
opaque provider evidence, and acquisition time. Verification fails closed on
unsupported preflight, preflight/snapshot drift, incomplete or misaligned
coverage, receipt identity drift, and stale acquisition evidence, returning
stable reason codes without performing I/O or mutating any input.

The exact package tree passed 503 focused Strategy Lab v2 tests, Ruff, MyPy,
and `git diff --check`. This remains an engine-neutral adapter boundary: the
provider-platform branch still owns data fetching, repair, and evidence
retrieval, while schema migrations, application/API wiring, workers, Compose,
stable Nautilus execution, frontend integration, promotion, and deployment stay
deferred behind their existing gates.

## 2026-09-16 - Acquisition checkpoint combined-gate evidence

The exact synchronized acquisition checkpoint passed all five executable branch
checks and the repository-wide Docker-backed coverage gate. The focused suite
now contains 503 passing tests; the combined backend suite completed 2,150
tests with 83.00% total coverage (required threshold: 75%), and Docker setup
and cleanup completed successfully. Ruff, MyPy, `git diff --check`, and
workstream validation also passed. No shared provider, ETF, TC2000, runtime,
migration, API, worker, Compose, or frontend path was changed.

## 2026-09-16 - Data-bound execution admission checkpoint

`execution_data_admission.py` now composes the verified acquisition handoff
with a scientific trial, frozen snapshot, and ready Nautilus execution plan.
It rejects unverified coverage, request/snapshot drift, trial or plan snapshot
drift, and non-ready engine plans before a worker can consume the plan. The
result is immutable, content-addressed evidence and does not start a process or
perform persistence/network I/O.

The exact package tree passed 509 focused Strategy Lab v2 tests, Ruff, MyPy,
and `git diff --check`. Provider fetching/repair, schema/API registration,
workers, Compose, stable Nautilus execution, frontend integration, promotion,
and deployment remain deferred behind the existing staging and release gates.

The exact data-bound execution checkpoint also passed the repository-wide
Docker-backed coverage gate: 2,156 tests completed with 83.02% total coverage
(required threshold: 75%), with Docker setup and cleanup successful. The branch
checks and workstream validation remain green.

## 2026-09-16 - Deterministic strategy wall-clock preflight checkpoint

Static strategy-source validation now rejects calls to `now`, `today`, and
`utcnow`, including aliased receivers, while continuing to allow typed datetime
values as declared inputs. The violation is content-addressed and deterministic;
this closes a replay-integrity loophole without treating static analysis as the
runtime sandbox boundary.

The exact package tree passed 510 focused Strategy Lab v2 tests, Ruff, MyPy,
and `git diff --check`. The subsequent Docker-backed combined coverage gate
completed successfully and reports 83.03% total coverage (required threshold:
75%), with the existing setup/cleanup path intact. Provider/API/database/worker/
Compose integration and stable Nautilus execution remain deferred behind the
existing gates.

## 2026-09-16 - Hardened sandbox argv execution checkpoint

`SandboxCommandPlan` values are now revalidated at the execution boundary,
not only when built by the convenience factory. The validator requires the
complete network-disabled, read-only, capability-dropped, unprivileged,
resource-bounded invocation shape, pinned image/input identities, and explicit
read-only input plus writable output mounts. A manually forged plan therefore
cannot introduce privileged Docker flags or bypass the declared output limit.

The focused isolation/worker regression set passed 35 tests, and the complete
Strategy Lab v2 package passed 511 tests with Ruff, MyPy, and `git diff --check`.
The Docker-backed combined gate then completed 2,158 tests with 83.02% total
coverage (required threshold: 75%), with setup and cleanup successful.
Schema/API/worker/Compose integration and stable Nautilus execution remain
deferred behind the existing gates.

## 2026-09-17 - Execution and audit event-time canonicalization checkpoint

`events.py` and `audit.py` now normalize every aware occurrence timestamp to
UTC at immutable-contract construction. This closes an identity/replay edge
case where the same instant arriving with a different offset compared unequal
to the already persisted record and could be reported as a content collision.
The append and journal monotonicity semantics remain unchanged; persistence,
outbox/Redis transport, and application wiring remain deferred behind the
existing shared-path gates.

Regression coverage verifies equality, content-address identity, and exact
replay for offset-equivalent execution and audit records. Focused validation
passed 13 tests, Ruff, and MyPy for the changed modules. The branch remains
`ready_for_human_review`; provider/API/database/worker/Compose integration,
stable Nautilus execution, frontend work, promotion, and deployment remain
deferred.

## 2026-09-17 - Restricted custom-metric boundary checkpoint

`custom_metrics.py` now provides a source-bound, process-local custom-metric
runner for result analysis. It accepts only recursively frozen finite Decimal
observations and canonical JSON parameters, validates source identity and
static restrictions, requires a finite Decimal scalar output, and emits a
versioned `MetricValue` with source/input evidence. Static violations, source
drift, malformed outputs, and runtime exceptions return typed rejection/failure
evidence without exception text. The containing worker still must use the
hardened no-network sandbox; container activation, persistence, and API wiring
remain deferred behind the existing shared-path gates.

The focused custom-metric suite passed 4 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate: 681 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip then
passed the Docker-backed combined coverage gate: 2,328 tests with 83.68% total
coverage, above the required 75% threshold; setup and cleanup completed
successfully. The branch remains `ready_for_human_review`.

## 2026-09-17 - Custom-metric wire protocol and CLI checkpoint

`custom_metric_protocol.py` now provides a strict tagged-JSON request/result
boundary for isolated custom-metric workers. It preserves Decimal and other
typed values through the existing runtime codec, rejects duplicate fields and
non-finite JSON constants, binds source and definition identity, and verifies
the content-addressed result fingerprint. `custom_metric_runner.py` reads a
mounted request, runs the restricted metric boundary, and atomically publishes
the typed result with status-based exit codes; it does not start Docker or
weaken the containing no-network sandbox. Worker image activation, persistence,
API wiring, and scheduling remain deferred behind the existing shared-path
gates.

Focused protocol/CLI coverage passed 4 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate and combined coverage gate recorded
above; no worker image, persistence, API, or scheduling gate was opened.

## 2026-09-17 - Custom-metric entrypoint and export hardening checkpoint

Custom-metric definitions now reject non-string entrypoints explicitly and the
restricted loader resolves the declared dotted callable path instead of only
top-level names. The `strategy_runtime` package exposes its custom-metric wire
helpers lazily, preserving the earlier import-cycle fix while retaining a
convenient public API. Focused coverage passed 10 tests with Ruff and MyPy
green. The exact pushed tip passed the branch gate: 683 package tests, Ruff,
MyPy across 237 source files, diff check, and workstream validation. The same
tip passed the Docker-backed combined coverage gate: 2,330 tests with 83.68%
total coverage, above the required 75% threshold; setup and cleanup completed
successfully.

## 2026-09-17 - Custom-metric batch runtime checkpoint

Custom metrics now have an immutable `CustomMetricInvocation` record and an
ordered `run_custom_metrics()` batch primitive. Duplicate invocation identities
are rejected, inputs are frozen at the boundary, and each typed result retains
its own source/definition/input evidence. The strict wire protocol adds a
content-addressed batch request/result envelope, while the mounted-file CLI
supports `--batch` with all-or-nothing success status and atomic publication.
This is intended for exhaustive local metric sweeps; the containing no-network
worker and durable application scheduling remain deferred.

Focused batch coverage passed 13 tests with Ruff and MyPy green. The exact
pushed tip passed the branch gate: 686 package tests, Ruff, MyPy across 237
source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,333 tests with 83.69% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Strict REST cursor decoding checkpoint

`ApiCursor.from_token()` now parses its base64 JSON envelope with duplicate-field
rejection and non-finite-number rejection before checksum and snapshot validation.
This keeps cursor identity deterministic under hostile or ambiguous transport
payloads while preserving the existing boundary that checksums are integrity
signals, not authorization. Route ownership and persistence integration remain
deferred behind the shared-path gates.

The focused API contract suite passed 6 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate: 687 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip passed
the Docker-backed combined coverage gate: 2,334 tests with 83.69% total
coverage, above the required 75% threshold; setup and cleanup completed
successfully.

## 2026-09-17 - Strict REST JSON serialization checkpoint

The registration-neutral API serializer now emits date values as ISO strings,
normalizes aware timestamps to UTC, preserves finite floats and exact Decimal
values, and rejects non-finite or unsupported scalar values before a response
can be published. This prevents JSONResponse from silently accepting ambiguous
numeric values or leaking an application object representation; router
registration, authentication, and persistence remain deferred behind the
shared-path gates.

Focused REST serialization coverage passed 15 tests with Ruff and MyPy green.
The exact pushed tip passed the branch gate: 688 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,335 tests with 83.70% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Strict REST request metadata checkpoint

The registration-neutral API boundary now rejects control characters in
`X-Request-ID` and `Idempotency-Key` values before they can reach response
headers, adapter calls, or durable idempotency fingerprints. Header values are
trimmed and bounded consistently across submissions and retry/cancellation
commands; authentication and persistence ownership remain unchanged.

Focused request-metadata coverage passed 10 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate: 689 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,336 tests with 83.70% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Strict REST JSON request-body checkpoint

The POST routes now reparse raw request bytes with duplicate-object-field and
non-finite-constant rejection before FastAPI-normalized bodies reach strategy
validation, submission idempotency, or command dispatch. This preserves one
canonical request identity even when a transport parser would otherwise silently
collapse ambiguous JSON. Shared router registration, authentication, and
persistence remain deferred behind the existing gates.

Focused raw-body coverage passed 11 tests with Ruff and MyPy green. The exact
pushed tip passed the branch gate: 690 package tests, Ruff, MyPy across 237
source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,337 tests with 83.70% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Snapshot-bound REST pagination checkpoint

Cursor-paginated collection responses now reject an adapter page whose visible
snapshot digest differs from the incoming cursor's snapshot. This prevents a
continuation token from silently traversing a different result set between
requests; the existing resource/type/request identity checks remain in force.
Persistence-backed reads and application registration remain deferred behind
the shared-path gates.

Focused pagination coverage passed 12 tests with Ruff and MyPy green. The exact
pushed tip passed the branch gate: 691 package tests, Ruff, MyPy across 237
source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,338 tests with 83.71% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Combined backend coverage revalidation

The exact pushed checkpoint tip passed the Docker-backed combined coverage gate:
2,318 tests passed with 83.65% total coverage, above the required 75% threshold.
PostgreSQL/Redis setup and cleanup completed successfully, and the run produced
the combined coverage reports. This supersedes the earlier transient connection
refusal record; no product or shared-path integration gates were changed.

## 2026-09-17 - Artifact manifest and integrity hardening checkpoint

`ArtifactManifest` now rejects boolean/non-integer byte lengths and untyped
retention classes. `ArtifactIntegrityReceipt` validates all digest and length
fields, canonicalizes failure reasons, and rejects a forged receipt that claims
verification while observed bytes differ from the manifest. Publication and
local-store adapters therefore receive only typed, content-consistent evidence;
durable byte lifecycle, migrations, authorization, and application wiring
remain deferred behind the existing shared-path gates.

The focused artifact/core regression set passed 31 tests with Ruff and MyPy
green. The exact pushed tip then passed the Docker-backed combined coverage
gate: 2,320 tests with 83.66% total coverage, above the required 75% threshold;
setup and cleanup completed successfully. The branch remains
`ready_for_human_review`; provider/API/database/worker/Compose integration,
stable Nautilus execution, frontend work, promotion, and deployment remain
deferred.

## 2026-09-17 - SDK UTC event-time normalization checkpoint

`MarketEvent` and `StrategyContext` now normalize every aware event time to
UTC at construction while retaining strict rejection of naive datetimes. This
keeps direct SDK callers aligned with the runtime wire protocol: event/context
scope checks, frozen-tape replay, and content fingerprints all operate on one
canonical instant representation. The focused Strategy Lab package passed 666
tests with Ruff, MyPy, `git diff --check`, and workstream validation green.

The repository-level Docker-backed coverage attempt reached the integration
suite but could not start the configured PostgreSQL test service on port 52440;
it ended with 2,087 passed, 1 failed (a worker contract test that passes in
isolation), and 226 setup errors from connection refusal. The integration
environment failure is independent of this SDK change and Docker cleanup
completed. Provider/API/database/worker/Compose integration and stable Nautilus
execution remain deferred behind the existing ownership and release gates.

## 2026-09-17 - SDK manifest identity canonicalization checkpoint

`StrategySdkManifest` now canonicalizes data dependencies by dependency ID,
model dependencies by distribution/version/artifact identity, and each data
dependency's declared fields lexically. Equivalent declarations therefore
produce the same immutable manifest fingerprint regardless of caller input
ordering, while duplicate IDs/fields remain rejected. The complete Strategy
Lab v2 package passed 667 tests with Ruff, MyPy, `git diff --check`, and
workstream validation green. Worker image/entrypoint, application scheduling,
migrations, upstream reconciliation, and authoritative Nautilus execution
remain deferred behind the existing gates.

## 2026-09-17 - Scientific identity canonicalization checkpoint

`StrategyVersion` now validates and canonically orders exact dependency
artifacts. `ExperimentDefinition` now rejects duplicate strategy identities and
orders the strategy collection by fingerprint. Equivalent scientific
declarations therefore produce one stable identity before trial expansion,
seed derivation, and result provenance. The complete Strategy Lab v2 package
passed 668 tests with Ruff, MyPy, `git diff --check`, and workstream validation
green. Worker image/entrypoint, application scheduling, migrations, upstream
reconciliation, and authoritative Nautilus execution remain deferred behind
the existing gates.

## 2026-09-17 - Metric-set identity canonicalization checkpoint

`MetricSet` now requires typed `MetricValue` records, validates that every
value uses the declared metric-set definition version, and canonically orders
records by metric identity. Equivalent result payloads therefore produce the
same metric-set fingerprint regardless of calculation order, while duplicate
`(name, basis)` values remain rejected. The complete Strategy Lab v2 package
passed 669 tests with Ruff, MyPy, `git diff --check`, and workstream validation
green. Worker image/entrypoint, application scheduling, migrations, upstream
reconciliation, and authoritative Nautilus execution remain deferred behind
the existing gates.

## 2026-09-17 - Snapshot-bound event-tape/SDK binding checkpoint

`bind_event_tape()` now verifies that a frozen replay tape belongs to the exact
`DataSnapshot` and `StrategySdkManifest` it is about to drive. It checks the
snapshot's preflight decisions and explicit degradations, matches effective
series semantics and effective dependency intervals, requires declared
instruments and exact event fields, rejects missing/unsupported dependencies, and emits a
content-addressed `EventTapeBinding` with deterministic per-dependency counts.
The SDK's `build_strategy_context()` applies the same declared-history interval
boundary for direct callers, so a context cannot bypass replay scope merely by
avoiding the binder. This keeps provider acquisition, coverage attestation,
strategy execution, order routing, and fills behind their existing adapter/
runtime gates.

The focused event-tape suite and complete Strategy Lab v2 package passed 653
tests with Ruff, MyPy, `git diff --check`, and workstream validation green. The
Docker-backed combined coverage gate passed 2,300 tests with 83.60% total
coverage (required threshold: 75%); setup and cleanup completed successfully.
Provider/API/database/worker/Compose integration and stable Nautilus execution
remain deferred behind the existing shared-path and release gates.

## 2026-09-17 - Schedule-gated target allocation checkpoint

`rebalance_allocation.py` now composes the immutable calendar schedule with
the engine-neutral target allocator. It validates the portfolio policy,
calendar, trigger, misfire-policy, and canonical occurrence identities,
normalizes only typed strategy intents, and applies them through the existing
all-or-nothing allocation/risk checks only when the exposure snapshot is at the
exact scheduled UTC boundary. Events before the boundary return an explicit
`not_due` decision. Events after it return either `misfired` or `skipped`
according to the occurrence's declared policy; no later-event catch-up or
implicit fill assumption is possible. Each decision is content-addressed and
retains the allocation fingerprint chain when applied.

The focused rebalance-gate suite passed 7 tests; the full package suite passed
642 tests with Ruff, MyPy, `git diff --check`, and workstream validation green.
The combined Docker-backed coverage gate passed 2,289 tests with 83.57% total
coverage (required threshold: 75%); Docker setup and cleanup completed
successfully.
Provider/API/database/worker/Compose integration, stable Nautilus execution,
frontend work, promotion, and deployment remain deferred behind the existing
ownership and release gates.

## 2026-09-17 - Frozen deterministic event-tape checkpoint

`event_tape.py` now provides a content-addressed, snapshot-bound replay tape
for later backtest and forward adapters. It canonicalizes cross-series event
ordering, groups same-time events into stable batches, exposes explicit
non-interpolating boundary slices, rejects duplicate event identities, prevents
one dependency from switching instruments, and requires each dependency's
sequence and event time to advance monotonically. Empty tapes remain explicit
inputs rather than being mistaken for complete coverage; provider acquisition,
coverage attestation, strategy execution, order routing, and fills remain
outside this contract.

The focused event-tape suite passed 7 tests; the full package suite passed 649
tests with Ruff, MyPy, `git diff --check`, and workstream validation green. The
Docker-backed combined coverage gate passed 2,296 tests with 83.59% total
coverage (required threshold: 75%), and setup/cleanup completed successfully.
The provider/API/database/worker/Compose integration and stable Nautilus
execution gates remain deferred.

## 2026-09-16 - Sandbox-gated planner checkpoint

The engine and worker orchestration gates now validate the hardened sandbox
argv before returning a ready plan. A manually constructed plan with missing
isolation controls is rejected during planning and cannot be persisted or
dispatched as ready; the executor retains its independent last-mile check.

The focused gate/worker regression set passed 26 tests, and the complete
Strategy Lab v2 package passed 512 tests with Ruff, MyPy, and `git diff --check`.
The Docker-backed combined gate completed 2,159 tests with 83.03% total
coverage (required threshold: 75%), and Docker setup/cleanup succeeded.
Schema/API/worker/Compose integration and stable Nautilus execution remain
deferred behind the existing gates.

## 2026-09-25 - Failed worker runtime evidence checkpoint

`worker_evidence_resolution.py` now maps a failed runtime receipt that has not
yet received a durable API error projection to a deterministic typed
`ApiError`. The fallback carries only the persisted runtime `error_digest`,
uses the request fingerprint as its stable request identity, and never
reconstructs exception text or filesystem paths. Existing application-owned
errors still take precedence; successful and cancelled runtime evidence retain
their strict manifest/error rules.

The focused resolver suite passed 7 tests. The exact branch validation passed
841 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage
gate passed 2,492 tests with 83.75% total coverage (required threshold: 75%);
the referenced runtime env file was absent in this checkout and `.env.dev`
supplied test configuration. Two cleanup passes retained zero testcontainer
sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Authenticated search worker materializer checkpoint

`search_worker_handoff.py` now provides an explicit worker materializer for
search-dispatch queues. Before decoding a Redis payload, it resolves the
request fingerprint through the owner-agnostic PostgreSQL search-dispatch
lookup and verifies request, attempt, payload, and queue identities. It then
validates the decoded immutable worker request's attempt binding and all
orchestration component fingerprints, failing closed on drift or missing
records.

`worker_callbacks.create_search_dispatch()` exposes this binding as an
explicit callback-factory choice using the worker's existing
`STRATEGY_LAB_V2_QUEUE` setting. The ordinary submission-backed callback
factory remains unchanged; no queue is treated as search-dispatch-backed by
default. Focused coverage passed 10 tests, and the complete branch gate passed
874 package tests, 2 migration tests, Ruff, MyPy across 276 files, diff
validation, and workstream validation. The exact backend coverage gate passed
2,525 tests with 83.78% total coverage (required threshold: 75%) and 86
warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Two cleanup passes retained zero
testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Enabling this callback in the
actual dedicated worker entrypoint still requires host configuration,
migration/schema reconciliation, stable Nautilus release conformance,
upstream provider/ETF/TC2000 reconciliation, and full shared-path integration.

## 2026-09-25 - Dispatch-identity terminal evidence checkpoint

Worker terminal evidence now resolves the Redis `DispatchRequest` fingerprint
from `WorkerCompletionContext.entry`, rather than incorrectly using the
separately content-addressed `WorkerExecutionRequest` fingerprint. The
submission adapter joins dispatch and submission rows by owner/idempotency key,
authenticates both identities, and rejects ambiguous or drifted bindings.

Search-dispatch workers now have a durable fallback: the authenticated search
dispatch record is projected into the existing typed submission receipt
contract, preserving owner, attempt, payload, queue, and candidate identity
without inventing a principal or requiring a duplicate submission row. Focused
coverage passed 25 tests, and the complete branch gate passed 875 package
tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation, and
workstream validation. The exact backend coverage gate passed 2,526 tests with
83.78% total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent in this checkout and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Dedicated worker activation,
shared migration/application reconciliation, stable Nautilus v2 conformance,
and upstream provider/ETF/TC2000 integration remain gated.

## 2026-09-25 - Explicit search terminal binding correction

The search-dispatch terminal-evidence path now fails closed unless the host
supplies an explicit resolver from the durable `SearchDispatchRecord` to the
authoritative `WorkerSubmissionBinding`. The resolver is checked for owner and
attempt consistency before evidence loads, and the persistence bundle threads
it through the worker terminal resolver. No synthetic `SubmissionReceipt` is
constructed from queue metadata, so `ExecutionOutcome.submission_id` remains
the authoritative submission identity for settlement.

Focused persistence and worker-evidence coverage passed 20 tests. The complete
branch and exact backend coverage gates remain the next validation step for
this correction; the branch stays `ready_for_human_review` pending host
callback registration, shared-path reconciliation, stable Nautilus v2
conformance, and upstream provider/ETF/TC2000 integration.

## 2026-09-25 - Search terminal binding callback registration

The dedicated search callback factory now carries the authoritative terminal
binding seam all the way through application composition. It resolves a
`SearchDispatchRecord` owner/attempt via the persisted submission adapter and
passes that callback to the configured evidence resolver factory. A search
resolver that does not accept the explicit callback is rejected; ordinary
submission-backed workers retain their existing two-argument factory path.
Missing submissions return `None`, preserving the persistence layer's
fail-closed terminal retry behavior and keeping `ExecutionOutcome.submission_id`
authoritative. Focused callback coverage passed 9 tests; the complete branch
gate passed 876 package tests, 2 migration tests, Ruff, MyPy across 276 files,
diff validation, and workstream validation. The exact backend coverage gate
passed 2,527 tests with 83.78% total coverage and 86 warnings; the referenced
runtime env file was absent and `.env.dev` supplied test configuration. Two
cleanup passes retained zero testcontainer resources.

The branch remains `ready_for_human_review`. Host callback activation, shared
migration/application reconciliation, stable Nautilus v2 conformance, and
upstream provider/ETF/TC2000 integration remain gated.

## 2026-09-25 - Authoritative Nautilus image binding checkpoint

The final Nautilus execution gate now extracts the validated sandbox image
digest and compares it with the stable release pin's runtime-image digest
before producing an authoritative execution plan. A mismatched, unreadable,
or absent pinned image is rejected without process creation; compatibility-only
release-candidate plans retain their non-authoritative path. Focused sandbox
and engine-gate coverage passed 11 tests. The complete branch gate passed 878
package tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation,
and workstream validation. The exact backend coverage gate passed 2,529 tests
with 83.79% total coverage and 86 warnings; the referenced runtime env file
was absent and `.env.dev` supplied test configuration. Two cleanup passes
retained zero testcontainer resources.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
isolated runtime activation, shared worker/database reconciliation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Recovery timestamp identity checkpoint

Recovery retry plans and worker-release receipts now normalize all aware
observation, retry, and release timestamps to UTC at their contract boundaries.
Offset-equivalent observations therefore produce identical retry/release
identities, and replay comparisons no longer reject equivalent instants.
Focused recovery coverage passed 10 tests. The complete branch gate passed 880
package tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation,
and workstream validation. The exact backend coverage gate passed 2,531 tests
with 83.79% total coverage (required threshold: 75%) and 86 warnings; the
referenced runtime env file was absent and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Shared worker/database
reconciliation, stable Nautilus v2 publication, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Legacy import inspection checkpoint

Preserved digest-only legacy records are now exposed through the read-only
`legacy-imports` API resource in addition to `POST /legacy/imports`. The shared
PostgreSQL persistence bundle loads and authenticates the owner-scoped registry,
projects stable record fingerprints, and explicitly retains
`replay_equivalent: false`; payload bytes are never returned.

The focused API/persistence suite passed 26 tests and the full package suite
passed 853 tests. Exact branch validation passed 853 package tests, 2 migration
tests, Ruff, MyPy across 272 files, diff validation, and workstream validation.
The Docker-backed combined coverage gate passed 2,504 tests with 83.78% total
coverage (required threshold: 75%) and 86 warnings; the referenced runtime env
file was absent in this checkout and `.env.dev` supplied test configuration.
Two cleanup passes retained zero testcontainer sessions, containers, images, or
volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Capability-summary API projection checkpoint

Persisted capability summaries are now exposed as the read-only
`capability-summaries` resource in the registration-neutral v2 API. The shared
PostgreSQL persistence bundle projects authenticated summaries with stable
fingerprint identities and preserves data/execution gaps, degradations,
ranking eligibility, executability, and authoritative-publication eligibility.
No provider entitlement or engine registration is inferred by this projection;
preflight calculation remains owned by its existing adapters.

The focused API/resource/persistence suite passed 35 tests and the full package
suite passed 851 tests. Exact branch validation passed 851 package tests, 2
migration tests, Ruff, MyPy across 272 files, diff validation, and workstream
validation. The Docker-backed combined coverage gate passed 2,502 tests with
83.77% total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent in this checkout and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Legacy import API checkpoint

The registration-neutral Strategy Lab v2 router now exposes strict
`POST /legacy/imports` handling. Requests require an idempotency key, preserve
only digest-backed legacy metadata, validate mapping/support evidence, and
return a typed compatibility report that permanently carries
`replay_equivalent: false`. Conflicting legacy identities return a typed
conflict rather than overwriting prior evidence. The application adapter now
delegates the route to the existing owner-scoped PostgreSQL legacy registry;
legacy payload bytes remain outside this boundary.

The focused API/legacy/application suite passed 34 tests and the full package
suite passed 849 tests. Exact branch validation passed 849 package tests, 2
migration tests, Ruff, MyPy across 272 files, diff validation, and workstream
validation. The Docker-backed combined coverage gate passed 2,500 tests with
83.76% total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent in this checkout and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Request-bound host failure evidence checkpoint

Injected host runtime-error classification is now bound to the immutable worker
request fingerprint. A custom failure factory that returns an `ApiError` for a
different request is rejected before terminal evidence can be persisted,
preventing application policy from detaching failure state from the execution
attempt being settled. The digest-only fallback and existing durable-error
precedence remain unchanged.

The focused resolver/persistence suite passed 17 tests. Exact branch validation
passed 847 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage gate
passed 2,498 tests with 83.76% total coverage (required threshold: 75%) and 86
warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Two cleanup passes retained zero
testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Complete multi-artifact mapping coverage checkpoint

The resolver coverage now includes a positive two-artifact host mapping in
addition to the fail-closed cases. A complete host-supplied plan set is
accepted only when both output artifact identities, byte digests, lengths, and
retention classes match the immutable result manifest; the package still does
not guess mounted paths or publish bytes on the host's behalf.

The focused resolver suite passed 12 tests. The exact branch validation passed
846 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage
gate passed 2,497 tests with 83.76% total coverage (required threshold: 75%);
the referenced runtime env file was absent in this checkout and `.env.dev`
supplied test configuration. Two cleanup passes retained zero testcontainer
sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Exact artifact-plan coverage checkpoint

Successful `WorkerTerminalEvidence` now validates publication plans against the
complete `RunResultManifest.output_artifacts` set before terminal persistence.
Every output artifact must have exactly one plan with matching manifest
fingerprint, content digest, storage key, byte length, and retention class;
unknown, duplicate, substituted, or missing plans fail closed. The host still
owns mapping mounted files to plans, and the existing single-output mapper
continues to reject multi-artifact manifests unless an explicit host mapper is
provided.

The focused resolver suite passed 11 tests. The exact branch validation passed
845 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage
gate passed 2,496 tests with 83.76% total coverage (required threshold: 75%);
the referenced runtime env file was absent in this checkout and `.env.dev`
supplied test configuration. Two cleanup passes retained zero testcontainer
sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Injectable worker failure policy checkpoint

The package-owned worker evidence resolver now accepts an optional host
`runtime_error_factory` through both the resolver callback and
`PostgresStrategyLabV2Persistence.worker_terminal_evidence_resolver()`. This
keeps retryability and typed failure classification application-owned while
retaining the deterministic digest-only `ApiError` fallback when no policy is
provided. The factory is invoked only for failed runtime evidence that lacks a
durable projected error; authenticated lookup and artifact mapping remain
separate seams.

The focused resolver/persistence set passed 13 tests. The exact branch
validation passed 843 package tests, 2 migration tests, Ruff, MyPy across 272
files, diff validation, and workstream validation. The Docker-backed combined
coverage gate passed 2,494 tests with 83.75% total coverage (required
threshold: 75%); the referenced runtime env file was absent in this checkout
and `.env.dev` supplied test configuration. Two cleanup passes retained zero
testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.
## 2026-09-25 - Forward-event admission API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/events` as a strict, application-owned admission boundary. The route reparses raw JSON with duplicate/non-finite rejection, reconstructs canonical forward events, cursors, observations, and optional correction commands, then delegates atomic event/counterfactual-replay persistence to the application adapter. Responses retain the authenticated state and replay-plan fingerprints, and missing host persistence fails closed. API JSON conversion now serializes checkpoint sets deterministically. Focused parser/serializer and forward-state regression validation passed (21 tests); Ruff, MyPy (293 source files), and whitespace validation passed. This remains a host/provider event-ingestion seam; it does not activate provider acquisition or Nautilus execution.
## 2026-09-25 - Forward-event dispatch API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/events/dispatch`, reconstructing strict canonical event/observation/correction inputs plus a typed `DispatchRequest` and bounded payload. It delegates atomic admission, content-addressed payload staging, idempotent dispatch, and transactional-outbox evidence to the application adapter, returning typed dispatch/envelope/replay fingerprints and failing closed when host persistence is absent. Four focused API/parser/serializer tests pass for this slice; Ruff, MyPy (293 source files), and whitespace validation pass. Provider acquisition, live event resolution, Redis activation, and Nautilus execution remain explicit host/upstream gates.
## 2026-09-25 - Forward warm-up API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/warmup`. It strictly reconstructs the immutable warm-up receipt, verifies route/receipt instance identity and carry-in mode, delegates the one-time durable warm-up boundary, and serializes receipt/instance fingerprints. This keeps activation evidence separate from live event admission and does not fetch provider data or start Nautilus. Five focused forward API/parser/serializer tests pass in the current slice; Ruff, MyPy (293 source files), and whitespace validation pass.
## 2026-09-25 - Forward lifecycle API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/lifecycle`, strictly parses a target state and timezone-aware transition timestamp, delegates owner-scoped compare-and-set persistence, and serializes applied/replay/conflict evidence. This completes the API-side lifecycle seam around the already durable forward-state adapter; provider event acquisition, worker activation, and Nautilus execution remain gated. Six focused forward API/parser/serializer tests pass in the current slice; Ruff, MyPy (293 source files), and whitespace validation pass.
## 2026-09-25 - Forward API ASGI route evidence

The warm-up endpoint now has executable ASGI-level coverage using an in-process HTTP transport, proving request parsing, dependency injection, application delegation, typed serialization, and the 202 response at the registered route. The focused forward/API suite now passes 25 tests; Ruff, MyPy (293 source files), and whitespace validation remain green.
## 2026-09-25 - Forward dispatch/lifecycle ASGI evidence

ASGI-level route coverage now exercises the atomic forward dispatch/outbox and lifecycle compare-and-set endpoints in addition to warm-up. The focused forward/API suite passes 27 tests, proving the registered HTTP boundaries delegate typed requests through the application seams and return typed 202 responses. Ruff, MyPy (293 source files), and whitespace validation remain green.
## 2026-09-25 - Counterfactual replay observability checkpoint

Persisted forward correction replay plans now have an authenticated owner-scoped read bridge and `GET /forward-instances/{instance_id}/replays` projection. The adapter returns `404` for unknown instances, verifies deterministic replay ordering, and the API exposes immutable plan identities without changing live state. ASGI route, serializer, and forward-state tests pass; the focused suite now passes 29 tests with Ruff, MyPy (293 source files), and whitespace validation green.
## 2026-09-25 - Durable replay read-back evidence

The replay observability slice now includes direct PostgreSQL-adapter coverage: persisted correction plans load deterministically for the owning principal, while another owner receives no instance evidence. The focused forward/API suite remains at 29 passing tests with Ruff, MyPy (293 source files), and whitespace validation green.

## 2026-09-25 - Replay instance-binding hardening

Replay serialization now rejects any persisted plan whose instance identity does
not match the route resource being projected. This closes a local resource
binding gap while preserving deterministic replay ordering and immutable plan
identity. The focused forward/API suite passes 30 tests, with Ruff, MyPy (293
source files), and whitespace validation green.

## 2026-09-25 - Forward projection identity hardening

Forward event-transaction serialization now rejects counterfactual replay plans
bound to a different instance than the projected checkpoint. Warm-up projection
also rejects receipts whose instance, snapshot, or carry-in mode differs from
the resolved forward instance. These checks keep host adapter output fail
closed at the API boundary rather than trusting a malformed resolution. The
focused forward/API suite passes 32 tests; Ruff, MyPy (293 source files), and
whitespace validation remain green.

## 2026-09-25 - Forward dispatch projection hardening

Dispatch responses now verify that their nested event transaction carries the
same state fingerprint as the outer dispatch resolution and that any nested
counterfactual replay plan belongs to that state's forward instance. This
prevents a malformed host resolution from publishing mixed-instance dispatch
evidence. The focused forward/API suite passes 33 tests; Ruff, MyPy (293
source files), and whitespace validation remain green.

## 2026-09-25 - Async dedicated-worker spawn checkpoint

Dedicated worker services now use an asynchronous process-executor path that
starts the fresh spawn child on the worker event-loop thread and cooperatively
polls it, preserving lease-heartbeat scheduling without invoking Python spawn
from `asyncio.to_thread` (which stalled in this runtime). The synchronous
executor remains available for direct callers. The API test helper now uses a
synchronous facade over `httpx.ASGITransport`, removing the hanging Starlette
`TestClient` portal while retaining the same route assertions.

The complete Strategy Lab v2 package suite passes 949 tests, including 124
PostgreSQL adapter tests and 3 migration-startup tests. Ruff, MyPy (293 source
files), and whitespace validation remain green.

The repository-authoritative Docker-backed combined backend coverage gate also
passes at the exact implementation tip: 2,600 tests, 83.76% total coverage
(required threshold 75%), and 86 warnings. Integration containers were cleaned
up after the run; no containers, images, or volumes were retained.

## 2026-09-25 - Worker timeout escalation checkpoint

Both synchronous and asynchronous dedicated-worker execution now escalate a
timed-out child from `terminate()` to `kill()` when necessary, then reap the
process handle before returning typed timeout evidence. This closes the last
local orphan-process path in the serial Nautilus worker boundary. The full
Strategy Lab package suite passes 949 tests, and the exact-tip Docker-backed
combined gate passes 2,600 tests with 83.76% coverage (threshold 75%).

## 2026-09-25 - Async worker timeout regression evidence

The serial worker process suite now directly covers the asynchronous timeout
path in addition to synchronous timeout handling. A real spawned child that
outlives the deadline is escalated, reaped, and returned as typed timeout
evidence without leaving the event loop blocked. The complete Strategy Lab v2
package suite passes 950 tests; focused worker coverage passes 12 tests.

The repository-authoritative Docker-backed combined gate also passes at the
current exact tip: 2,601 tests, 83.76% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-09-25 - Cooperative async timeout cleanup

Async timed-out worker cleanup now performs terminate/kill escalation with
cooperative zero-time joins and event-loop yields. A stubborn child therefore
cannot block lease-heartbeat scheduling while the parent waits for cleanup.
The focused worker suite passes 13 tests, including a fake stubborn-process
regression that proves kill escalation and event-loop progress.

## 2026-09-25 - Cancellation-safe async worker cleanup

Cancelling an in-flight asynchronous worker handoff now terminates and reaps
the spawned child before propagating cancellation, preventing orphaned
simulation processes during worker shutdown or lease cancellation. The focused
worker suite passes 14 tests and the complete Strategy Lab v2 package suite
passes 952 tests.

The repository-authoritative Docker-backed combined gate passes at this exact
implementation tip: 2,603 tests, 83.78% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-09-25 - Heartbeat-failure execution cancellation

Dedicated worker services now monitor the process handoff and lease-heartbeat
task together. A rejected or failed heartbeat immediately cancels the
simulation task, which invokes the cancellation-safe process reaper before the
entry is returned for retry. Focused worker coverage passes 15 tests and the
complete Strategy Lab v2 package suite passes 953 tests.

The repository-authoritative Docker-backed combined gate passes at this exact
implementation tip: 2,604 tests, 83.78% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-09-25 - Service-shutdown execution cancellation

Cancelling the dedicated worker service handler itself now cancels its
separately scheduled execution task and awaits its cleanup, so shutdown cannot
leave a running simulation child behind. Focused worker coverage passes 16
tests and the complete Strategy Lab v2 package suite passes 954 tests.

The repository-authoritative Docker-backed combined gate passes at this exact
implementation tip: 2,605 tests, 83.78% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-10-02 - Resumed session and transport synchronization audit

The assigned implementation session was resumed after the previous blocked
audit. The required UV-managed `agent-context` and session bootstrap completed
through the repository-approved elevated execution path; the initial
unprivileged attempt was blocked only by the shared read-only UV cache. The
existing local implementation range was pushed successfully to
`origin/feat/strategy-lab-v2`: remote `6dbb206a4` now matches implementation
tip `a6a98b122`.

The provider-platform, ETF, and TC2000 branches have advanced since the prior
checkpoint, but `staging` remains `8b885a2ff` and none of those dependency refs
is an ancestor of staging. Their overlapping provider/migration/application
paths remain outside this feature branch's ownership. The next product action
remains gated on approved staging promotion, stable Nautilus v2 release and
conformance evidence, and host runtime evidence configuration; no
cross-worktree integration was performed.

The active operational context owns the following pending record files until
the checkpoint commit closes them: `ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## Active context - forward worker Compose entrypoint

Intent: add the explicit opt-in local forward-worker entrypoint and Compose
service, keeping host event/materializer and account/engine callbacks required
and fail-closed. Add the forward payload-loader seam needed by that entrypoint.
Owned paths: `backend/app/strategy_lab_v2/forward_worker_entrypoint.py`,
`backend/app/strategy_lab_v2/postgres_forward_dispatch.py`, their focused tests,
`docker-compose.yml`, and this handoff/validation record.

## 2026-10-02 - Dedicated forward worker Compose boundary

The local forward-testing boundary is now explicit and opt-in. The new
`forward_worker_entrypoint` performs startup migration, builds the persistence
adapter, loads a host-supplied materializer/handler callback factory, consumes
the dedicated `forward-events` Redis queue, rehydrates payloads through the
PostgreSQL forward-dispatch adapter, and shuts down the runtime and scheduler
cleanly. Callback configuration is mandatory at runtime and fails closed; the
entrypoint does not select a provider, broker, or Nautilus implementation.

`docker-compose.yml` now declares a separate `strategy-lab-v2-forward-worker`
service under the existing `strategy-lab-v2` profile with a read-only root,
dropped capabilities, no-new-privileges, bounded temporary storage, an
artifact volume, and PostgreSQL/Redis health dependencies. This is a local
execution boundary only; host event resolution, account semantics, and engine
callbacks remain an explicit deployment concern. `PostgresForwardDispatch` now
exposes the content-addressed payload loader consumed by the worker.

Validation for this slice: focused forward-entrypoint/dispatch/service/compose
tests passed (17 tests); the complete Strategy Lab v2 package suite passed
(960 tests); targeted Ruff, Ruff format checks, MyPy, and `make
test-compose-contract` passed. `UV_CACHE_DIR=/tmp/strategy-lab-v2-uv-cache make
validate-integration` reached the repository lint stage but stopped because
the branch baseline reports 232 files requiring `ruff format --check`,
including untouched files; no mass formatting was applied. This is a
repository-wide validation baseline issue, not a failure in the focused slice.

The implementation remains gated from authoritative activation by stable
Nautilus v2 release/conformance evidence, host callback/event configuration,
approved provider/ETF/TC2000 promotion to staging, and shared migration and
application-path reconciliation. No other worktree was changed.

## 2026-10-02 - Exact external blocker audit after forward-worker push

At the post-push audit, `origin/staging` is still `8b885a2ffd9c`, while the
current dependency refs are market-data `366fdd4f4276`, ETF
`52814f95bd0e`, and TC2000 `63d64bfe95c9`; none is an ancestor of staging.
Therefore shared provider, ETF, frontend, migration, and application-path
reconciliation is not yet admissible under AC-UPSTREAM.

The checked-out backend still pins `nautilus-trader==1.226.0`, while the
Strategy Lab v2 conformance contract rejects release pins that do not start
with `2.`. A stable Nautilus v2 package/build plus the required multi-account,
native order/fill/cost, deterministic replay, lifecycle, and backtest/forward
event-tape evidence is therefore still missing. The worker Compose boundary
is intentionally unable to claim authoritative activation without that
evidence. The remaining runtime-specific dependency is an explicitly
configured host callback factory that resolves admitted canonical events and
account/engine semantics; an empty Compose value fails closed by design.

## 2026-10-02 - Forward worker configuration isolation hardening

The forward Compose service now uses the namespaced
`STRATEGY_LAB_V2_FORWARD_DATABASE_URL_SYNC` variable rather than inheriting
the generic worker database key, and its contract test asserts that the
forward service has no Docker socket. Namespaced configuration keeps the
forward boundary explicit and the absence of a Docker socket prevents a
forward-event worker from acquiring backtest sandbox authority. Focused
entrypoint/Compose coverage passes 5 tests and `make test-compose-contract`
passes.

## 2026-10-02 - Backtest worker configuration boundary hardening

The isolated backtest worker now uses the namespaced
`STRATEGY_LAB_V2_DATABASE_URL_SYNC` key, matching its explicit worker
configuration contract rather than inheriting the generic database variable.
The new Compose contract test verifies that the backtest worker remains
profile-gated, read-only, capability-dropped, health-gated on PostgreSQL and
Redis, and artifact-volume-backed, while retaining its intentionally explicit
Docker socket because sandbox execution launches separately pinned runtime
containers. Focused backtest/forward entrypoint and Compose coverage passes 12
tests; `make test-compose-contract` passes.

## 2026-10-02 - Current dependency and runtime-boundary audit

The current remote refs are market-data `1b51877881ce`, ETF
`52814f95bd0e`, and TC2000 `63d64bfe95c9`; `origin/staging` remains
`8b885a2ffd9c`, and none of those dependency refs is a staging ancestor.
The implementation therefore remains prohibited from shared provider, ETF,
TC2000, migration, or application-path reconciliation. The backtest and
forward worker boundaries are now both documented and tested locally, but
authoritative activation still requires the stable Nautilus v2 release and
host callback evidence described above.

The complete Strategy Lab v2 package suite was rerun at the current exact
implementation tip and passes 961 tests. This includes the package-owned
backtest and forward worker entrypoint/Compose contracts; it does not claim
provider-backed acquisition, stable Nautilus execution, or full repository
integration.

## 2026-10-02 - Nautilus v2 release-candidate compatibility track

The absence of a stable Nautilus v2 release no longer blocks all engine work.
The branch now treats the exact `2.0.0rc5` package/tag as an isolated
compatibility track. Complete RC conformance evidence may run local backtest,
replay, and forward event-tape compatibility checks, but the resulting plan is
always non-authoritative and cannot publish official results, participate in
official rankings, or activate a deployed shadow instance. Stable v2 remains
mandatory for those authority boundaries.

The conformance gate now requires a valid isolated v2 release pin for every
actual Nautilus process, including RC execution; an unpinned or shared-runtime
build is rejected before sandbox invocation. The current backend
`nautilus-trader==1.226.0` dependency remains untouched for the legacy runtime.
The RC runtime must be a separate exact-pinned Python/Rust/runtime-image
environment and must not use the backend's v1 environment.

Current blockers are therefore narrower and concrete: the provider-platform,
ETF, and TC2000 refs are still not staging ancestors; host canonical-event,
account, and engine callback evidence is not configured for forward execution;
shared migration/application reconciliation is not admissible; and the
repository-wide formatter baseline still prevents the full integration gate.
None of these blocks pure contracts, RC conformance fixtures, or isolated
compatibility-run plumbing. Stable Nautilus remains only the blocker for
authoritative publication/live shadow, not for continued implementation.

## 2026-10-02 - Exact RC runtime declaration

`nautilus_runtime.py` now provides the immutable
`NautilusRcCompatibilityRuntime` adapter contract. It hard-codes the current
`2.0.0rc5` package/tag, requires source and runtime-image SHA-256 digests,
records Python/Rust versions, rejects any attempt to share the legacy runtime,
and produces the `NautilusReleasePin` consumed by conformance evidence. It
does not import Nautilus or install/discover packages.

The focused runtime/conformance/engine suite passes 21 tests, and Ruff plus
MyPy pass for the new adapter and probe. The exact x86_64 CPython 3.12 wheel
was verified against PyPI's published SHA-256
`eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`; the
probe then constructed and disposed a real `BacktestEngine` from
`2.0.0rc5`, yielding `engine_lifecycle=passed`. The complete package suite
passes 970 tests at this checkpoint. The exact isolated runtime image was then
built from `python:3.12.4-slim@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85`
with the verified x86_64 wheel and published checksum, producing image digest
`sha256:94d1bedef43b8b627b68ae8d4f43a79e47be635c7cd61fa9ddf8508d3b89b22e`.
The image probe passed with network disabled, read-only root, all Linux
capabilities dropped, `no-new-privileges`, and bounded tmpfs mounts; it emitted
`engine_lifecycle=passed` for Python 3.12.4 / Nautilus `2.0.0rc5`. This proves
isolated RC compatibility only; it does not grant authoritative publication or
live-shadow status.

The probe receipt is now parsed by `NautilusRuntimeProbeEvidence`, which binds
the exact package/Python fields and image digest back to the immutable runtime
fingerprint and rejects extra fields, version drift, failed lifecycle output,
or any attempt to treat the RC receipt as authoritative. The focused runtime,
probe, and fixture suite passes 16 tests with Ruff, MyPy, and diff validation
green.

## 2026-10-02 - RC probe/conformance identity binding

`require_runtime_probe_binding(...)` now joins a complete executable fixture
resolution to the exact `NautilusRuntimeProbeEvidence` receipt. It requires
Nautilus identity, the RC package/channel, the exact release pin, matching image
digest, and execution-eligible fixture evidence, while explicitly rejecting
authority claims. This is an identity/reproducibility gate around the injected
fixture harness; it does not claim that synthetic fixtures are real Nautilus
multi-instrument or event-tape conformance.

The full Strategy Lab v2 package suite passes 976 tests, with Ruff, targeted
formatting, MyPy across 302 files, and diff validation green.

## 2026-10-02 - Image-backed RC deterministic engine fixtures

The isolated image was rebuilt with `nautilus_rc_fixture_probe.py`, producing
digest `sha256:1e8a1c33b58ac216027b777dc025e833f5bc5c93bf10e9b550985e0024847c3f`.
Under network-disabled, read-only, capability-dropped, no-new-privileges
execution, the real Nautilus `2.0.0rc5` engine completed deterministic
synthetic fixtures: one instrument produced one native order and position with
account total `98899.78 USD`; two instruments produced two orders and two
positions with account total `97799.56 USD`; two identical runs matched exactly.
The fixture explicitly reports `forward_event_tape_parity` as
`deferred_authoritative_fixture`, because the canonical event adapter and host
forward callback are not yet available. This is genuine RC compatibility
evidence, not stable authority or a live-shadow claim.

The resulting JSON was parsed through `NautilusRcFixtureReceipt` with source
digest `sha256:dd30e7817784d1a9eec556c15b846f93040a7a4e8694cab4771d0ba0c24c6c06`,
image digest above, and fixture digest
`sha256:8432ac13ee7e24b526ca8efeadf3d20370eb3aadf362fa947e2f7ab4579d7540`.
The typed receipt records passed checks for engine lifecycle, native
order/fill/cost, multi-instrument accounting, and deterministic replay, with
only `forward_event_tape_parity` deferred. It remains compatible evidence and
is explicitly non-authoritative.

## 2026-10-02 - Provider-neutral canonical-event materialization boundary

Added `nautilus_event_adapter.py` and focused tests for the next safe slice of
the RC compatibility track. `NautilusEventRecord` converts validated
engine-neutral `MarketEvent` values into an immutable wire record with exact
UTC nanosecond timestamps, required OHLCV/quote/trade fields, and content
fingerprints. `NautilusEventTape` preserves the source frozen-tape identity,
canonicalizes deterministic replay order, and rejects duplicate identities.
`materialize_nautilus_event_tape(...)` reuses the existing snapshot/manifest
binding before materializing records, so no provider fetch, inference, or
Nautilus import is introduced. This is the host/Rust adapter contract only;
forward event-tape parity, account callbacks, stable-release authority, and
shared-path integration remain explicitly gated.

The focused adapter suite passes 6 tests with package-local Ruff, formatting,
MyPy, and diff checks as the next validation receipt; the complete package
suite and repository integration checks are rerun at the checkpoint commit.

## 2026-10-02 - Canonical event-tape parity receipt

Extended `nautilus_event_adapter.py` with a strict observed-wire schema and
`verify_nautilus_event_tape_parity(...)`. The verifier canonicalizes event
order, rejects duplicate or malformed records, and returns content-addressed
field-level mismatch evidence. `NautilusEventParityReceipt` is explicitly
compatible-only and non-authoritative, so it can become the forward-parity
conformance input once a real host/Rust callback is available without making a
synthetic adapter claim stable Nautilus authority.

The focused adapter suite now passes 9 tests; package-wide validation follows
after the documentation and workstream receipt are committed.

## 2026-10-02 - Event parity conformance projection

`build_event_tape_parity_observation(...)` now converts a
`NautilusEventParityReceipt` into the existing
`FORWARD_EVENT_TAPE_PARITY` conformance observation. Successful receipts use
their content fingerprint; failed receipts receive a distinct failure digest,
so an expected-digest configuration cannot manufacture a pass. This keeps the
future real host/Rust callback on the same conformance path as the other engine
checks without claiming that the current RC fixture is authoritative.

The complete package suite passes 987 tests, with package Ruff, targeted
formatting, MyPy, diff, and workstream validation green.

## 2026-10-02 - Effective event-type substitution binding

`materialize_nautilus_event_tape(...)` now resolves each dependency's effective
event type from the snapshot's verified preflight decision, including explicit
degraded substitutions. The adapter therefore cannot silently label a
materialized record with the requested event type when the bound snapshot used
another supported type. A focused regression covers the degraded substitution
path and the complete package suite passes 988 tests.

## 2026-10-02 - Forward canonical-event envelope

Added `NautilusForwardEventEnvelope` and
`materialize_nautilus_forward_event(...)`. The envelope binds the admitted
`CanonicalForwardEvent` stream identity to the payload-bearing `MarketEvent`
and resulting Nautilus wire record, rejecting event-ID, sequence, or timestamp
drift before a host/Rust live adapter can invoke the engine. This closes the
identity seam without inventing provider/account callbacks or claiming RC
forward parity.

The focused adapter suite passes 12 tests with Ruff, formatting, and MyPy
green; package-wide validation is rerun for the checkpoint.

## 2026-10-02 - Feature-ref/session receipt alignment

The checkout's Git upstream metadata was pointing at the legacy hyphenated
`origin/feat-strategy-lab-v2` ref instead of the actual slash-named
`origin/feat/strategy-lab-v2` feature ref. This made a synchronized checkout
appear 297 commits ahead and left the session receipt at the prior
implementation tip. Upstream tracking now resolves to the slash-named feature
ref, the branch is exactly synchronized, and the session checkpoint records
the current forward-envelope checkpoint. This was workflow metadata drift, not
a Strategy Lab product or Nautilus dependency failure.

## 2026-10-02 - Non-authoritative result provenance and ranking boundary

`RunResultManifest` and `EngineResultEvidence` now carry an explicit
`engine_authoritative` bit, included in reproduction identity and propagated
through result materialization. Publication rejects manifests that are not
bound to authoritative conformance evidence or whose authority bit disagrees
with that evidence. Descriptive ranking excludes non-authoritative engine
output by default with a typed exclusion reason; an explicit exploratory
`include_non_authoritative=True` opt-in is available for RC compatibility
analysis without confusing it with official ranking.

Focused provenance/ranking/publication/materialization coverage passed 52
tests. Package-wide validation passed 991 tests, Ruff, MyPy across 305 source
files, diff validation, and workstream validation. This makes the existing
RC policy enforceable in result data rather than relying only on runtime
documentation or the publication gate.

The elevated combined backend gate subsequently passed 2,642 tests with
83.77% total coverage against the repository's 75% threshold, and the backend
and RPI Compose configuration contracts rendered successfully. This removes
the earlier sandbox-only runtime-registry diagnostic from the validation
picture; it was an execution-environment boundary, not a product failure.

## 2026-10-02 - RC fixture receipt/conformance binding

`require_rc_fixture_binding(...)` now joins the parsed real-image
`NautilusRcFixtureReceipt` to the exact runtime probe, release pin, and partial
conformance suite. It requires passed and deferred check sets to match exactly
and rejects image/version/channel drift or any authority claim. This lets the
current `2.0.0rc5` fixture evidence feed compatibility analysis without
silently satisfying the stable or forward-parity authority gates.

The focused RC fixture/probe suite passes 22 tests; the complete package suite
passes 993 tests, Ruff, MyPy across 305 source files, diff validation, and
workstream validation.

## 2026-10-02 - Forward event-tape batch callback boundary

`NautilusForwardEventTape` and `materialize_nautilus_forward_tape(...)` now
bind an instance-scoped batch of admitted `CanonicalForwardEvent` values to
their payload-bearing `MarketEvent` records. The boundary canonicalizes
sequence order, rejects duplicate identities or sequences, requires an exact
dependency-to-event-type map, and remains provider- and Nautilus-free. It is
the batch seam a future host/Rust callback can consume; it does not claim that
the callback or forward parity implementation exists.

The focused event-adapter suite passes 14 tests; the complete package suite
passes 995 tests, Ruff, MyPy across 305 source files, diff validation, and
workstream validation.

## 2026-10-02 - Forward event-tape parity receipt

`NautilusForwardEventParityReceipt` and
`verify_nautilus_forward_event_tape_parity(...)` now verify the strict wire
records emitted for an admitted forward batch against the instance-scoped
canonical-event envelopes. The receipt preserves the forward-tape identity,
canonicalizes callback order, reports field-level drift, and remains explicitly
non-authoritative. It is the evidence seam a future host/Rust callback can
produce without importing Nautilus or acquiring provider data.

The focused event-adapter suite passes 17 tests; the complete package suite
passes 998 tests, Ruff, MyPy, diff validation, and workstream validation.

## 2026-10-02 - Forward parity conformance projection

`build_event_tape_parity_observation(...)` now accepts both the existing
historical `NautilusEventParityReceipt` and the instance-scoped
`NautilusForwardEventParityReceipt`. Forward callback evidence can therefore
feed the existing `FORWARD_EVENT_TAPE_PARITY` conformance check with the same
fail-closed digest and pass-bit rules; no authority is inferred from a parity
receipt.

The focused conformance/event-adapter suites pass 33 tests; the complete
package suite passes 999 tests, Ruff, MyPy across 305 source files, diff
validation, and workstream validation.

The exact-tip Docker-backed combined backend gate then passed 2,650 tests with
83.77% total coverage against the 75% threshold, and the backend/RPI Compose
contract rendered successfully. The gate emitted 86 dependency warnings but no
test failures; resources were cleaned after completion.

The durable plan next action now reflects that the implementation-side tape,
parity, and conformance projection seams are complete. The remaining action is
to invoke them from the real host/Rust canonical-event callback once that
callback and approved staging contracts exist; worker activation, publication,
and live shadow remain fail-closed until their independent gates pass.

## 2026-10-02 - Upstream gate refresh after parity completion

Remote refs were refreshed after the forward-parity implementation. `origin/staging`
remains `8b885a2ffd9c`; market-data `f9be6bfdb71d`, ETF `1a256e78d0d1`, and
TC2000 `63d64bfe95c9` are still not staging ancestors. No shared-path
reconciliation is admissible yet, and no parallel worktree was changed.

The official Nautilus release list was also rechecked on 2026-10-02: the 2.x
line still exposes `2.0.0rc5` as a pre-release and no stable 2.x release. The
RC compatibility track therefore remains the correct local path; stable release
authority is still fail-closed rather than inferred.

## 2026-10-02 - RC backtest execution scope

`NautilusExecutionScope` now distinguishes full, forward-compatibility, and
backtest-compatibility process gates. A non-authoritative exact-pinned RC
backtest/replay plan may proceed when multi-instrument accounting, native
order/fill/cost, deterministic replay, and lifecycle checks pass while forward
event-tape parity remains explicitly deferred. Forward compatibility and every
authoritative plan still require the complete check set; no authority is gained
from selecting the narrower scope.

The focused engine-execution suite passes 10 tests; the complete Strategy Lab v2
package suite passes 1,001 tests, Ruff, MyPy across 305 source files, and diff
validation.

## 2026-10-02 - RC receipt-to-execution evidence bridge

`resolve_nautilus_rc_conformance(...)` now turns the parsed exact-image RC
fixture receipt plus runtime probe into the ordinary engine evidence/report
pair consumed by the execution gate. The resolver authenticates runtime,
probe, image, package, release-pin, build, and fixture identities, preserves
the four passed checks and deferred forward-parity check, and cannot emit
authoritative evidence. The focused conformance-fixture and engine-gate suites
pass 29 tests; the complete Strategy Lab v2 package suite passes 1,004 tests,
Ruff, MyPy across 305 source files, and diff validation. The engine-gate test
now consumes the resolver output directly through the backtest-compatible
execution scope.

## 2026-10-02 - Forward parity adapter resolution

`resolve_nautilus_forward_parity(...)` now composes strict forward-wire
verification with the existing conformance projection. It returns a typed
resolution binding the instance-scoped tape, parity receipt, and
`FORWARD_EVENT_TAPE_PARITY` observation, while preserving mismatch evidence
and the non-authoritative boundary for the eventual host/Rust callback.
The focused conformance-fixture suite passes 18 tests and the complete
Strategy Lab v2 package suite passes 1,004 tests, Ruff, MyPy, and diff
validation.

## 2026-10-02 - Nautilus sandbox engine binding

Added an explicit Nautilus sandbox builder that binds
`STRATEGY_ENGINE_ID=nautilus` into the hardened Docker argv. The final
`run_nautilus_plan` process boundary now validates that marker and rejects
missing or non-Nautilus engine identities before invoking Docker, closing the
gap where a plan could claim Nautilus evidence while carrying a generic runtime
command. Generic sandbox plans remain available to engine-neutral runtime
paths. Focused sandbox/runner coverage passes 11 tests; the complete Strategy
Lab v2 package suite passes 1,006 tests, Ruff, MyPy, and diff validation.

## 2026-10-02 - Nautilus engine-input catalog boundary

Added `nautilus_engine_input.py`, an engine-neutral immutable input contract
for the eventual Nautilus runtime adapter. It binds an already materialized
event tape to provider-supplied instrument precision/increment/lifecycle
metadata, one shared venue/account model with initial cash, and the strategy
source/manifest/parameter identities. It rejects missing instruments,
cross-venue events, duplicate definitions, invalid cash/base currency, and
malformed entrypoints before native engine construction. The focused engine
input/event-adapter suite passes 22 tests; the complete Strategy Lab v2 package
suite passes 1,011 tests, Ruff, MyPy, and diff validation.

## 2026-10-02 - Isolated Nautilus engine-input runtime adapter

Added the image-local `nautilus_runtime_data.py` materializers and
`nautilus_runtime_adapter.py`. The adapter consumes a strict serialized
`NautilusEngineInput`, validates digest/catalog/tape identities before native
imports, constructs RC5-native instruments, venue/account balances, and quote,
trade, or OHLCV values, then invokes `BacktestEngine` and emits scalar
digest-bound execution evidence. The evidence is explicitly non-authoritative;
the forward event-tape parity field remains deferred and no worker/publication
authority is enabled.

The hardened exact `2.0.0rc5` image built successfully and the adapter probe
ran network-disabled, read-only, capability-dropped, and no-new-privileges.
Its two native quote events produced two iterations, one native order, one
open position, and deterministic scalar account/cost evidence. The existing
RC lifecycle and fixture probes remain green. Focused adapter/image tests pass
6 tests; Ruff, MyPy, and diff validation pass. The next slice is to bind this
runtime adapter to the worker's serialized strategy invocation/result protocol
without changing the generic Compose worker or claiming RC authority.

## 2026-10-02 - RC5 serialized strategy invocation bridge

The isolated adapter now consumes the existing serialized strategy invocation
batch instead of an in-process strategy factory. `nautilus_strategy_bridge.py`
authenticates the batch source/manifest/entrypoint/parameters/seed against the
engine input, binds each SDK context to exactly one canonical tape event, and
invokes the existing `StrategyInvocationSession` from native quote/trade/bar
callbacks. Position snapshots come from the native portfolio; supported
`OrderIntent` values are converted to native orders, and the typed batch result
is returned with input/result digests and invocation count. Missing and
source-mismatched batches fail before native engine imports. Target-position
intents deliberately fail closed until the platform allocator/risk bridge is
connected.

The exact pinned RC5 image (`sha256:725c63134aa77fd53d58ac73153ab9bf93377cd0b9c0e550b152c6578782ec88`)
was rebuilt from this source and passed the hardened no-network, read-only,
capability-dropped probe. Two quote events invoked two SDK contexts and
produced two successful serialized results, one native order, and one open
position. The receipt remains `authoritative: false`; forward parity remains
deferred. Focused runtime/image tests pass 9 tests, the complete package suite
passes 1,018 tests, Ruff and MyPy across 312 source files pass, and the
workstream validator accepts all 30 records.

Stable Nautilus v2 is not blocking further isolated implementation. The live
release line is still pre-release `2.0.0rc5`; stable conformance remains an
authority gate. The next local seam is to connect the validated worker handoff
and result/artifact lifecycle to this adapter, then route target-position
intents through allocation/risk and broaden product/accounting/report tests.
Provider, ETF, and TC2000 contracts remain gated only for their respective
shared-path integrations until those branches reach staging.

Session progress and exact command receipts are recorded in
`ops/workstreams/feat-strategy-lab-v2/session.json` and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-02 - RC worker CLI and result-artifact path

Stable Nautilus v2 is not a prerequisite for this implementation. The isolated
RC5 compatibility path now has a fixed `nautilus_runtime_cli` command, built
through `build_nautilus_runtime_sandbox_command`. The runner rejects arbitrary
commands and binds the attempt, exact engine version, frozen snapshot, and
memory-derived input bound to the immutable execution/sandbox plans. The CLI
checks the mounted bundle's canonical digest, attempt, snapshot, exact installed
package version, strict JSON shape, and bounded input before invoking the
serialized engine-neutral SDK strategy batch. It writes deterministic native
execution evidence into the already-mounted result file; the existing sandbox
adapter captured its file digest/length for the artifact publication path.

The RC image now defaults to the CLI's non-authoritative version probe while
remaining command-overridable for actual backtests. Its small wire-protocol
module is separated from host-only typed bundle contracts so the image does not
load legacy backend contract modules. The Nautilus sandbox builder uses the
image's packaged working directory. The Docker output bind mount now uses
Docker's valid read-write default rather than an unsupported `rw` mount token.

An end-to-end run through the real host builder/`run_nautilus_plan` and the
locally built digest-pinned RC5 image succeeded with networking disabled,
read-only root, all capabilities dropped, `no-new-privileges`, an unprivileged
UID, 512 MiB memory, and bounded CPU/output. Two frozen quote events produced
two serialized SDK invocations, one native order, and one open position. The
captured 3,016-byte result file had digest
`sha256:27995118ac75efa6b8c60c3663ee43e0e28cc9e77c15cb523b88fa155bf87c3d`;
its internal execution-evidence digest verified and its authority bit remained
false. The exact local RC5 image was rebuilt as
`sha256:89ec7792a4b6c15aae6752f2cd9d5c503df23e8e48f876a0bdbdf80a96ab9203`.

The Strategy Lab v2 package suite passes 1,026 tests, Ruff passes, and MyPy
passes across 316 source files. The current host has no Docker BuildKit/buildx
plugin, so the image was built with the established legacy-builder fallback
and a temporary package-only `.dockerignore`; that temporary file was removed.
The current code path proves CLI and result capture, but production worker
request assembly/materialization of `NautilusRuntimeBundle` is still open, as
are target-position allocation/risk routing and broader native product,
accounting, report, and stable-authority conformance. RC results remain
non-authoritative. Provider, ETF, and TC2000 staging boundaries remain scoped
to those shared-contract integrations and do not block this isolated work.

Files changed in this slice: `backend/app/strategy_lab_v2/nautilus_runner.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_bundle.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_cli.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_protocol.py`,
`backend/app/strategy_lab_v2/sandbox.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile.dockerignore`,
and the focused tests `test_engine_execution.py`, `test_execution_orchestration.py`,
`test_nautilus_runner.py`, `test_nautilus_runtime_cli.py`,
`test_nautilus_runtime_image.py`, `test_sandbox.py`, and
`test_sandbox_execution.py` under `backend/app/strategy_lab_v2/tests/`.

## 2026-10-02 - Verified local strategy-package resolution

The implementation no longer waits for a stable Nautilus v2 tag. Exact-pinned
v2 prereleases are eligible for authoritative local backtests only after the
complete platform conformance suite; prereleases remain barred from broker
connections and real-capital control. Forward shadow additionally requires
backtest/forward event-tape parity. RC5's current compatibility probe alone is
still non-authoritative.

Added the v1 source-archive contract and `StrategyPackageArtifactResolver`.
Source packages are bounded ZIPs containing exactly the versioned SDK manifest,
canonical exact dependency lock, and the entrypoint module. Resolution checks
the raw archive/manifest/lock digests and declared lengths, strategy and SDK
identity, exact worker runtime ABI, source digest, archive member types and
compression limits, then applies static strategy validation. It never extracts
files or installs dependencies; wheel packages fail closed until the isolated
runtime supports them. A verified package result can now feed the existing
Nautilus trial-input assembler, and both package and runtime artifacts must use
the same content-addressed store.

`LocalArtifactStore.read_manifest` now optionally enforces its bound during a
no-follow regular-file read, preventing oversized or special-file inputs from
being buffered before integrity checks. The full Strategy Lab v2 package passed
1,057 tests; Ruff passed across `app/strategy_lab_v2` and `strategy_runtime`;
MyPy passed across 323 source files. This validation was run against source
commit `f3d6077752733ce73be7b1d16359b3ce9897ba8e`.

Next: define the frozen event-tape artifact boundary using the platform's
content-addressed Parquet/Arrow artifacts, then hydrate owner-scoped trial
resources and inject canonical instrument/venue/account adapters before binding
the assembled runtime reference into worker evidence and atomic dispatch.
Target-position allocation/risk and broad native product/accounting/report
conformance remain open. No external release or upstream branch blocks this
isolated implementation. Fresh status through the authorized workflow reports
Docker available and ready. The required `full_stack_browser` profile has not
yet been run; it remains a final validation gate, not a current development
blocker. No parallel worktree was accessed or changed.

## 2026-10-02 - Verified frozen event-tape artifact boundary

Added `LocalArtifactStore.open_verified` for seekable streaming access to
content-addressed artifacts. It opens a no-follow regular-file descriptor,
checks the digest before decoding, enforces an optional byte bound, and checks
the same descriptor again after consumption so the resolver does not need to
buffer an entire Parquet/Arrow artifact before integrity verification.

Added `FrozenEventTapeArtifactResolver` and a typed decoder boundary. It selects
series using the same effective preflight semantics as `bind_event_tape`, checks
decoded row counts and series time bounds, projects only strategy-declared
fields, and binds the final immutable tape to the snapshot and SDK manifest.
The decoder is injected deliberately: the provider workstream owns the actual
Parquet/Arrow schema, and this branch does not add a second market-data format
or fetch path. Missing/corrupt artifacts and malformed decoded rows fail
closed.

The Strategy Lab v2 package passes 1,066 tests; Ruff passes and MyPy passes
across 325 source files. The full-stack browser profile has not yet been run;
fresh workflow status says Docker is ready, so this is pending final acceptance
validation rather than an environment blocker. Next is owner-scoped trial
resource hydration, canonical instrument/account adapter injection, runtime
reference binding into worker evidence and atomic dispatch, then portfolio risk
and full Nautilus v2 conformance. Exact-pinned 2.0.0rc5 remains eligible after
that conformance; no stable release wait is required.

Scale boundary still open: `FrozenEventTapeArtifactResolver` currently retains
decoded rows and constructs an in-memory `FrozenEventTape`; the existing
Nautilus runtime bundle serializes that tape into a single JSON input. Verified
artifact reads are chunked, but end-to-end replay is not yet bounded-memory for
very long histories. The next implementation slice must replace this with a
chunked content-addressed runtime data-plane handoff before claiming broad
history-scale readiness.

## 2026-10-02 - Immutable experiment package binding

Experiments now optionally bind each declared strategy-version fingerprint to
one exact immutable `StrategyPackage` fingerprint. The binding is part of the
experiment fingerprint and is preserved by resource normalization/rehydration.
Trial runtime assembly rejects packages that are missing from the experiment
binding or differ from the pinned package, preventing a retry from silently
changing source archives or dependency locks. Draft experiments may remain
unbound; execution fails closed until each strategy version is package-bound.

Validation at source commit `0a257187ae4ae86619257c3c99cf16ed586e5eba`:
1,069 Strategy Lab v2 tests passed, Ruff passed, MyPy passed across 325 source
files, formatting checks passed for the touched files that are formatter-clean,
and `git diff --check` passed. The workstream validator passed before the
implementation commit; it is rerun with this checkpoint.

Nautilus v2 does not require waiting for a stable tag. The exact isolated
`2.0.0rc5` wheel/runtime image and a basic native-engine probe already pass, but
that probe is not the complete platform conformance suite and cannot authorize
authoritative results yet. Prerelease builds remain prohibited from broker
connections and real-capital control. The legacy backend pin remains 1.226.0;
the v2 runtime stays isolated rather than changing that global dependency.

There is no external release blocker to isolated implementation. Provider,
ETF, and TC2000 branch tips are still not ancestors of staging, so consuming
their shared contracts remains gated; this does not block parallel-safe core
work. Docker is ready, while `full_stack_browser` remains a final acceptance
gate. Next implementation context: replace full event-tape and JSON-bundle
materialization with a bounded, chunked content-addressed replay data plane,
then continue owner-scoped resource hydration and runtime dispatch assembly.

## 2026-10-02 - Disk-spooled frozen event-tape stream

Added `FrozenEventTapeArtifactResolver.resolve_streaming(...)`. It verifies
provider-owned source artifacts while decoding rows individually, uses a
bounded-cache SQLite sort spool with unique event identity and canonical event
ordering, then writes ordered canonical NDJSON to a pinned content-addressed
artifact. Event-line size, temporary disk use, and SQLite page cache are
bounded/configurable. The generated `tape_fingerprint` matches the existing
`FrozenEventTape.fingerprint` byte-for-byte; the verifier checks raw artifact
integrity, event ordering, sequence monotonicity, per-dependency counts, and
semantic tape identity before a second pass yields events.

Added `iter_materialized_nautilus_event_records(...)` to feed that verified
stream into the existing engine-neutral Nautilus event adapter one record at a
time, preserving effective event-type, instrument, field, interval, and
snapshot-coverage checks without constructing a `NautilusEventTape` tuple.
This is not yet the end-to-end runtime path: `NautilusTrialAssembly`, the JSON
runtime bundle, worker mount contract, runtime CLI, and strategy-context batch
still materialize complete inputs. Do not claim long-history bounded-memory
readiness until those consumers use the stream directly and exact RC5 replay
parity is demonstrated.

Validation at source commit `df28ac88e9bd2f58915404d76ad4b9c6ca128543`:
1,075 Strategy Lab v2 tests passed; Ruff passed; MyPy passed across 325 source
files; formatter checks passed for the new streaming module and its tests; and
`git diff --check` passed.

No stable Nautilus release is required. Exact-pinned RC5 remains eligible after
the complete platform conformance suite, and prereleases remain barred from
broker connections and real-capital control. Shared provider/ETF/TC2000
contract consumption remains staged behind those branches reaching staging;
it does not block this independent data-plane work. Docker is ready and
`full_stack_browser` remains a final acceptance gate.

Next: extend the content-addressed stream reference through trial assembly and
the isolated worker mount/CLI, then run it through Nautilus's catalog-backed
chunked path while streaming SDK contexts/results. Preserve same-time event
ordering; verify it against exact RC5 before any authoritative activation.

## 2026-10-02 - RC5 streamed strategy contexts on native callbacks

`build_native_strategy_bridge(...)` and the isolated runtime adapter now accept
either the existing serialized invocation batch or a seekable v2 context
stream. Stream bytes are fingerprinted with bounded reads. Before importing
Nautilus, the bridge exhausts a validation pass that authenticates event IDs,
history membership, chronology, same-time coverage, parameter/seed binding,
and canonical native event order. The callback path then reopens the verified
stream and advances one timestamp group at a time, invoking batched contexts
only on the last native callback in that group. Native callbacks are checked
against the exact frozen tape order; the legacy batch input and output
contracts remain available.

The exact isolated Nautilus 2.0.0rc5 image, built with the pinned wheel
`sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`,
ran the streamed-context path by immutable image ID under no-network,
read-only, capability-dropped, no-new-privileges, and unprivileged-UID
restrictions. Two same-time native quote events yielded one SDK invocation, one
native order, and one open position. The evidence recorded engine version
`2.0.0rc5`, input protocol `context-stream`, and `authoritative: false`; the
execution evidence digest was
`sha256:f72bd113a8d6d2b903a29d0f96a39bdde691d1c2bdae3bb39de2e50f5eb5d14e`.
The immutable local image ID was
`sha256:e7d704d5e7b54f685b3a01ebe4a774285a21572016f97a41a083e3ed8d8c7f14`.

Validation at source commit `bfa77138f00bcd571bcfacbd17132ba14d7c432c`:
1,089 Strategy Lab v2 tests passed; Ruff passed; all four changed Python files
passed format checks; MyPy passed across 325 source files; `git diff --check`
passed; and the RC5 streamed-context probe passed. The source commit was pushed
to `origin/feat/strategy-lab-v2`.

This is an adapter seam, not yet the full bounded-memory runtime: the worker
request and CLI still carry a JSON batch, frozen event/native-event inputs
remain materialized, and native invocation results remain accumulated for the
legacy wire response. Continue by binding the context stream as a verified
content-addressed sidecar through trial assembly, worker mount, and CLI, then
stream results into the artifact path and convert native events to RC5 catalog
chunks. Stable Nautilus v2 is not a blocker; full platform conformance still
gates authoritative results, and prereleases remain barred from broker/live
real-capital control.

## 2026-10-02 - RC5 native-event sidecar and chunked catalog replay

Completed the bounded handoff from frozen event tapes into the isolated runtime.
Trial assembly now emits verified content-addressed strategy-context and native
event sidecars; the worker plan binds and mounts the native sidecar read-only,
and the CLI checks its regular-file type, exact length, and SHA-256 before
streaming it to the adapter. The native sidecar has canonical event ordering,
monotonic native init timestamps for deterministic same-time ordering, bounded
row/stream sizes, record-count validation, and a records digest. The RC adapter
converts records into bounded 10,000-event batches in Nautilus's Parquet catalog
and executes them through `BacktestNode` with configurable replay chunking.
Strategy contexts and invocation results remain streamed; callback context
indexes are replayed from the authenticated rolling histories so two readers do
not race on one file cursor.

The exact pinned Nautilus 2.0.0rc5 image passed the hardened no-network runtime
probe for 10,005 events across the 10,000-record input boundary and 1,000-event
replay chunks. All 10,004 strategy invocation results succeeded. It also passed
the two-event same-time baseline. Both results remain `authoritative: false`;
the probe image ID was
`sha256:775cb0b38fac096bd2058312e4194434f734ab9aa98080d1b0d93821f4491d98`,
built with wheel digest
`sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`.

Validation at source commit `295262626a280604675ccf2d83f3c30d6013c784`:
1,109 Strategy Lab v2 tests passed; Ruff passed; all 17 changed Python files
passed format checks; MyPy passed across 327 source files; `git diff --check`
passed; and both exact-image RC5 probes passed. Commits `52e7605` and
`2952626` are synchronized with `origin/feat/strategy-lab-v2`.

No external dependency blocks further implementation, and stable Nautilus v2
is not required. AC-NAUTILUS conformance remains incomplete and therefore still
gates authoritative result publication: expand checks for multi-instrument
accounting, native order/fill/cost/report behavior, deterministic replay, and
engine lifecycle. The full-stack-browser profile is a final acceptance gate.
Provider-platform, ETF, and TC2000 contract consumption remains gated on their
approved work reaching staging, but does not block the owned Strategy Lab
runtime work. Pre-release builds remain forbidden from broker connections or
real-capital control.

Next: extend the RC5 conformance matrix and mixed quote/trade/bar catalog probes,
preserving the same isolated, non-authoritative status until the full suite
passes.

## 2026-10-02 - Backtest authority separated from forward parity

The execution gate now has an explicit `BACKTEST_AUTHORITATIVE` scope. It
requires multi-instrument accounting, native order/fill/cost, deterministic
replay, and lifecycle checks, exact isolated v2 pin validation, authorization,
and a sandbox image digest matching the pinned image. It does not wait for
`FORWARD_EVENT_TAPE_PARITY`; `FULL` and `FORWARD_COMPATIBILITY` still require
all checks. Development builds remain ineligible, and release candidates remain
local-only with no broker connection or real-capital control.

The planner now recomputes the conformance report from its evidence before
accepting it, preventing a caller-supplied report from overstating passed
checks. Regression coverage verifies that a parsed RC5 four-check receipt may
feed the backtest-authoritative scope while the global full-suite report remains
incomplete, that a missing simulator check still rejects, that forward scope
still requires parity, and that a forged report is rejected. This changes only
the scope policy; runtime execution evidence remains non-authoritative until the
actual simulator conformance and publication gates pass.

Validation at source commit `881a77e3d4800c2c34ddec2598003fde6eaea7e8`:
1,112 Strategy Lab v2 tests passed; Ruff passed; both changed Python files
passed format checks; MyPy passed across 327 source files; and `git diff --check`
passed. The source commit is pushed to `origin/feat/strategy-lab-v2`.

No external release or workstream dependency blocks continued implementation.
The remaining engine gate is evidence quality: the current image fixture proves
multi-instrument replay and order/account changes but does not yet inspect native
fills, explicit commission/slippage models, and reports with enough detail for
the accepted four-check suite. Forward parity remains a separate forward-only
gate; provider-platform, ETF, and TC2000 contracts remain staging-gated.

Next: strengthen the exact-RC5 native fill/cost/report fixture and bind its
durable receipt to the backtest authority and result-publication path.

## 2026-10-03 - RC5 native fill, cost, and report conformance

The pinned Nautilus `2.0.0rc5` image now exercises the native `OneTickSlippageFillModel`
and `FixedFeeModel`, then reads Nautilus order/fill reports. The isolated image
contains an exactly pinned pandas reporting stack instead of inheriting optional
packages from the legacy backend. Its final image is
`sha256:5b6c4d268f38337b50ec813906f6bbc8fd41895a6ea8b561f601e44e4308a9b8`,
built from the `nautilus_trader-2.0.0rc5` wheel pinned at
`sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`.

Under a network-disabled, read-only, unprivileged container, both repeated
single-instrument runs reported one order and one fill, filled all 1,000 units,
executed one tick above the `1.10020` ask at `1.10021`, charged the configured
`2.00 USD` fee, and reconciled the cash account to `98,897.79 USD`. The shared
two-instrument account reported two distinct instruments, two complete fills,
`4.00 USD` total fees, and a reconciled balance of `97,795.58 USD`. Deterministic
replay matched, and the engine lifecycle passed.

The actual JSON output was consumed by `NautilusRcFixtureReceipt`; its digest is
`sha256:b233d6aa9953894f65628247455f6b349590c21946fac0a84797e3e9a78eee3e`.
The receipt records four passed simulator checks (multi-instrument accounting,
native order/fill/cost, deterministic replay, and lifecycle), explicitly defers
forward event-tape parity, and remains non-authoritative itself. The scoped
backtest planner can separately authorize local backtests from those four
checks; prereleases remain unable to connect to a broker or control real
capital.

Validation at source commit `f9f646f873149959ecfbba9b51e0f0c2285fb924`:
1,118 Strategy Lab v2 tests passed; Ruff and format checks passed; MyPy passed
across 327 files; and `git diff --check` passed. The implementation commit is
pushed to `origin/feat/strategy-lab-v2`.

Stable Nautilus 2.0 is not a prerequisite, and no external release or workstream
dependency blocks continued implementation. The remaining immediate internal
gate is publication integration: `plan_result_publication()` still requires
the global conformance report itself to be authoritative, so it rejects a
backtest-authoritative scope whose only missing check is forward parity. Result
materialization/publication must also retain exact release channel, wheel/image
digests, conformance identity, and authority scope. Forward parity remains a
separate forward-only check; provider-platform, ETF, and TC2000 contract use
remains gated on those approved workstreams reaching staging. Full-stack-browser
remains the final branch acceptance gate.

Next: bind the backtest-authoritative execution plan and exact engine provenance
through result materialization/publication without weakening the independent
forward parity gate.
