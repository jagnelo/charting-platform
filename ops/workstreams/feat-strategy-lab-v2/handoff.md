# feat/strategy-lab-v2

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Human authorization

- Recorded at: 2026-09-15T19:48:24.815519+00:00
- Request: Implement the approved Strategy Lab v2 plan; honor the repository AI-driven workflow rules and active branch boundaries.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; the plan remains at `ready_for_human_review` and the
  session-local goal is held at its plan-ready guard.

Update this handoff at each coherent boundary.

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
