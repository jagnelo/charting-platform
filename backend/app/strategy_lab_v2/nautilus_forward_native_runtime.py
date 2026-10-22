"""Persistent, isolated-side Nautilus BacktestEngine forward runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, BinaryIO, cast

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_account import ForwardAccountEventBinding
from app.strategy_lab_v2.forward_context import (
    ForwardPortfolioContextPreparation,
    ForwardStrategyContextPreparation,
    ForwardStrategyContextWindow,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventRecord
from app.strategy_lab_v2.nautilus_forward_bootstrap import (
    NautilusForwardRuntimeBootstrap,
)
from app.strategy_lab_v2.nautilus_forward_input import (
    NautilusForwardDeliveryInput,
    VerifiedForwardMarketPayload,
)
from app.strategy_lab_v2.nautilus_forward_result import NautilusForwardExecutionResult
from app.strategy_lab_v2.nautilus_forward_runtime_server import NautilusNativeForwardSession
from app.strategy_lab_v2.nautilus_runtime_data import (
    NautilusRuntimeDataError,
    materialize_native_event,
    materialize_native_fee_model,
    materialize_native_instrument,
    materialize_native_venue,
)
from app.strategy_lab_v2.nautilus_strategy_bridge import (
    NativeStrategyBridge,
    build_native_strategy_bridge,
)
from strategy_runtime import deserialize_component_invocation_context_stream

if TYPE_CHECKING:
    from app.strategy_lab_v2.nautilus_runtime_cli import ForwardSessionFactoryBuilder

StreamOpener = Callable[[], AbstractContextManager[BinaryIO]]
ForwardPreparation = ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation


@dataclass(slots=True)
class _NativeEngineState:
    engine: Any
    bridge: NativeStrategyBridge
    windows: dict[str, ForwardStrategyContextWindow]
    native_init_time_ns: int
    instrument_definitions: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class _SettledNativeInput:
    delivery: NautilusForwardDeliveryInput
    preparation: ForwardPreparation
    result: NautilusForwardExecutionResult


def _context_stream_contract(
    bundle: Mapping[str, Any],
) -> tuple[str, int, int, dict[str, int]]:
    reference = bundle.get("strategy_context_stream")
    if not isinstance(reference, Mapping):
        raise NautilusRuntimeDataError("forward runtime context reference is invalid")
    artifact = reference.get("artifact")
    if not isinstance(artifact, Mapping):
        raise NautilusRuntimeDataError("forward runtime context artifact reference is invalid")
    digest = artifact.get("content_digest")
    length = artifact.get("byte_length")
    count = reference.get("context_count")
    raw_counts = reference.get("component_counts")
    if (
        not isinstance(digest, str)
        or not isinstance(length, int)
        or isinstance(length, bool)
        or length < 1
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or not isinstance(raw_counts, list)
    ):
        raise NautilusRuntimeDataError("forward component context reference is incomplete")
    require_sha256_digest(digest, field_name="context_stream_digest")
    counts: dict[str, int] = {}
    for item in raw_counts:
        if not isinstance(item, Mapping):
            raise NautilusRuntimeDataError("forward component context count is invalid")
        component_id = item.get("component_id")
        component_count = item.get("context_count")
        if (
            not isinstance(component_id, str)
            or not component_id.strip()
            or not isinstance(component_count, int)
            or isinstance(component_count, bool)
            or component_count < 1
            or component_id in counts
        ):
            raise NautilusRuntimeDataError("forward component context counts are invalid")
        counts[component_id] = component_count
    if sum(counts.values()) != count:
        raise NautilusRuntimeDataError("forward component context counts differ from total")
    return digest, length, count, counts


def _native_stream_contract(bundle: Mapping[str, Any]) -> tuple[str, str, str, int]:
    reference = bundle.get("native_event_stream")
    if not isinstance(reference, Mapping):
        raise NautilusRuntimeDataError("forward runtime native event reference is invalid")
    artifact = reference.get("artifact")
    if not isinstance(artifact, Mapping):
        raise NautilusRuntimeDataError("forward runtime native artifact reference is invalid")
    digest = artifact.get("content_digest")
    source_tape_fingerprint = reference.get("source_tape_fingerprint")
    adapter_version = reference.get("adapter_version")
    event_count = reference.get("event_count")
    if (
        not isinstance(digest, str)
        or not isinstance(source_tape_fingerprint, str)
        or not isinstance(adapter_version, str)
        or not isinstance(event_count, int)
        or isinstance(event_count, bool)
        or event_count < 1
    ):
        raise NautilusRuntimeDataError("forward runtime native event reference is incomplete")
    require_sha256_digest(digest, field_name="native_event_stream_digest")
    require_sha256_digest(source_tape_fingerprint, field_name="source_tape_fingerprint")
    return digest, source_tape_fingerprint, adapter_version, event_count


def _event_record(record: NautilusEventRecord) -> dict[str, Any]:
    return {
        "dependency_id": record.dependency_id,
        "event_id": record.event_id,
        "instrument_id": record.instrument_id,
        "event_type": record.event_type,
        "event_time_ns": record.event_time_ns,
        "sequence": record.sequence,
        "values": dict(record.values),
    }


def _native_event_datetime_ns(event: CanonicalForwardEvent) -> int:
    value = event.event_time.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


class NautilusBacktestForwardSession(NautilusNativeForwardSession):
    """One process-local BacktestEngine shared by every portfolio component.

    A restore rebuilds from the immutable warm-up/bootstrap and deterministically
    replays settled in-process deliveries up to the requested external
    checkpoint. A fresh process is expected to receive a freshly resolved
    bootstrap from durable host state.
    """

    def __init__(
        self,
        *,
        instance_id: str,
        runtime_session_fingerprint: str,
        bootstrap: NautilusForwardRuntimeBootstrap,
        rebuild_state: Callable[[], _NativeEngineState],
        initial_state: _NativeEngineState,
    ) -> None:
        self.instance_id = instance_id
        self.runtime_session_fingerprint = runtime_session_fingerprint
        self._bootstrap = bootstrap
        self._rebuild_state = rebuild_state
        self._state = initial_state
        self._history: list[_SettledNativeInput] = []
        self._checkpoint_offsets = {bootstrap.processed_checkpoint_fingerprint: 0}
        self._closed = False

    @property
    def base_checkpoint_fingerprint(self) -> str:
        """Durable admission checkpoint authenticated by this process bootstrap."""

        return self._bootstrap.processed_checkpoint_fingerprint

    def execute(
        self,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> NautilusForwardExecutionResult:
        if self._closed:
            raise RuntimeError("Nautilus forward session is closed")
        if not isinstance(delivery, NautilusForwardDeliveryInput):
            raise TypeError("delivery must use NautilusForwardDeliveryInput")
        if delivery.delivery_binding.instance_id != self.instance_id:
            raise NautilusRuntimeDataError("forward delivery belongs to another instance")
        if self._history:
            prior = self._history[-1]
            if prior.delivery.delivery_binding.fingerprint == delivery.delivery_binding.fingerprint:
                if prior.preparation.fingerprint != preparation.fingerprint:
                    raise NautilusRuntimeDataError(
                        "duplicate forward delivery changed its context preparation"
                    )
                return prior.result
        checkpoint = delivery.delivery_binding.pre_event_checkpoint_fingerprint
        offset = self._checkpoint_offsets.get(checkpoint)
        if offset is None:
            raise NautilusRuntimeDataError(
                "forward delivery requires a process bootstrapped at its durable checkpoint"
            )
        if offset != len(self._history):
            raise NautilusRuntimeDataError(
                "forward session must restore its pre-event checkpoint before retry"
            )
        try:
            result = self._execute_on_state(self._state, delivery, preparation)
        except BaseException:
            self._replace_state_with_replay(len(self._history))
            raise
        self._history.append(_SettledNativeInput(delivery, preparation, result))
        return result

    def restore(self, *, checkpoint_fingerprint: str) -> str:
        require_sha256_digest(checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        offset = self._checkpoint_offsets.get(checkpoint_fingerprint)
        if offset is None:
            raise NautilusRuntimeDataError(
                "requested forward checkpoint is outside the authenticated runtime lineage"
            )
        if offset < 0 or offset > len(self._history):
            raise NautilusRuntimeDataError("forward checkpoint replay offset is invalid")
        self._replace_state_with_replay(offset)
        self._history = self._history[:offset]
        self._checkpoint_offsets = {
            fingerprint: known_offset
            for fingerprint, known_offset in self._checkpoint_offsets.items()
            if known_offset <= offset
        }
        return checkpoint_fingerprint

    def _replace_state_with_replay(self, offset: int) -> None:
        """Replace the disposed engine and replay only the settled prefix.

        Keep only one Nautilus BacktestEngine alive while restoring: the RC6
        runtime fixture showed that a replacement engine can miss its staged
        callback while the previous engine is still active.
        """

        previous = self._state
        self._dispose_state(previous)
        self._closed = True
        state = self._rebuild_state()
        try:
            for settled in self._history[:offset]:
                replayed = self._execute_on_state(state, settled.delivery, settled.preparation)
                if replayed.fingerprint != settled.result.fingerprint:
                    raise NautilusRuntimeDataError(
                        "native forward result changed while restoring its checkpoint"
                    )
        except BaseException:
            self._dispose_state(state)
            raise
        self._state = state
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._dispose_state(self._state)

    def _execute_on_state(
        self,
        state: _NativeEngineState,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> NautilusForwardExecutionResult:
        expected_contexts = self._prepare_live_contexts(state, delivery, preparation)
        envelope = delivery.tape.envelopes[0]
        event_time_ns = envelope.record.event_time_ns
        native_init_time_ns = max(event_time_ns + 1, state.native_init_time_ns + 1)
        state.bridge.stage_forward_event(
            _event_record(envelope.record),
            {component_id: item.context for component_id, item in expected_contexts.items()},
            instance_id=self.instance_id,
            canonical_event=envelope.canonical_event,
            native_init_time_ns=native_init_time_ns,
        )
        self._run_native_event(
            state.engine,
            envelope.record,
            state.instrument_definitions,
            native_init_time_ns=native_init_time_ns,
        )
        state.native_init_time_ns = native_init_time_ns
        state.bridge.result_output()
        account_event = state.bridge.take_forward_account_event()
        for component_id, context_preparation in expected_contexts.items():
            state.windows[component_id].commit(context_preparation)
        binding = ForwardAccountEventBinding(envelope.canonical_event, account_event)
        return NautilusForwardExecutionResult(
            delivery_binding_fingerprint=delivery.delivery_binding.fingerprint,
            context_preparation_fingerprint=preparation.fingerprint,
            pre_event_checkpoint_fingerprint=(
                delivery.delivery_binding.pre_event_checkpoint_fingerprint
            ),
            runtime_session_fingerprint=self.runtime_session_fingerprint,
            native_output_fingerprint=binding.fingerprint,
            account_event_binding=binding,
        )

    def _prepare_live_contexts(
        self,
        state: _NativeEngineState,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> dict[str, ForwardStrategyContextPreparation]:
        if preparation.instance_id != self.instance_id:
            raise NautilusRuntimeDataError(
                "forward context preparation belongs to another instance"
            )
        if preparation.delivery_binding_fingerprint != delivery.delivery_binding.fingerprint:
            raise NautilusRuntimeDataError("forward context preparation differs from delivery")
        if isinstance(preparation, ForwardStrategyContextPreparation):
            if len(state.windows) != 1:
                raise NautilusRuntimeDataError(
                    "a multi-component portfolio requires portfolio context preparation"
                )
            supplied = {next(iter(state.windows)): preparation}
        elif isinstance(preparation, ForwardPortfolioContextPreparation):
            supplied = dict(preparation.component_preparations)
        else:
            raise TypeError("forward context preparation has an unsupported type")

        dependency_id = delivery.market_event.dependency_id
        expected_component_ids = {
            component_id
            for component_id, window in state.windows.items()
            if dependency_id in window.dependency_ids
        }
        if set(supplied) != expected_component_ids:
            raise NautilusRuntimeDataError(
                "forward component contexts do not match the declared event dependencies"
            )
        expected: dict[str, ForwardStrategyContextPreparation] = {}
        for component_id in sorted(expected_component_ids):
            provided = supplied[component_id]
            local = state.windows[component_id].prepare_delivery(
                delivery,
                positions=provided.context.positions,
            )
            if local.fingerprint != provided.fingerprint:
                state.windows[component_id].discard(local)
                raise NautilusRuntimeDataError(
                    "forward context differs from the isolated authenticated history"
                )
            expected[component_id] = local
        return expected

    @staticmethod
    def _run_native_event(
        engine: Any,
        record: NautilusEventRecord,
        instrument_definitions: Mapping[str, Mapping[str, Any]],
        *,
        native_init_time_ns: int,
    ) -> None:
        definition = instrument_definitions.get(record.instrument_id)
        if definition is None:
            raise NautilusRuntimeDataError("forward event instrument has no engine definition")
        native_event = materialize_native_event(
            _event_record(record),
            definition,
            native_init_time_ns=native_init_time_ns,
        )
        engine.add_data([native_event], sort=True)
        engine.run(streaming=True)
        engine.clear_data()

    @staticmethod
    def _dispose_state(state: _NativeEngineState) -> None:
        dispose = getattr(state.engine, "dispose", None)
        if callable(dispose):
            dispose()


def build_native_forward_session_factory(
    bootstrap: NautilusForwardRuntimeBootstrap,
    bundle: Mapping[str, Any],
    *,
    open_context_stream: StreamOpener,
    open_native_event_stream: StreamOpener,
) -> Callable[[str], NautilusBacktestForwardSession]:
    """Build and warm one exact-plan persistent BacktestEngine session factory."""

    if not isinstance(bootstrap, NautilusForwardRuntimeBootstrap):
        raise TypeError("bootstrap must use NautilusForwardRuntimeBootstrap")
    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping")
    if not callable(open_context_stream) or not callable(open_native_event_stream):
        raise TypeError("forward runtime requires verified stream openers")
    from app.strategy_lab_v2.nautilus_runtime_adapter import (
        _validate_engine_input,
        runtime_package_version,
    )

    engine_input = bundle.get("engine_input")
    if not isinstance(engine_input, Mapping):
        raise NautilusRuntimeDataError("forward runtime engine input is invalid")
    (
        venue_definition,
        instrument_definitions,
        static_event_definitions,
        event_count,
        expects_stream,
    ) = _validate_engine_input(engine_input)
    if (
        not expects_stream
        or static_event_definitions
        or event_count != bootstrap.warmup_event_count
    ):
        raise NautilusRuntimeDataError("forward engine input differs from the warm-up stream")
    if content_digest(engine_input) != bootstrap.engine_input_fingerprint:
        raise NautilusRuntimeDataError("forward engine input fingerprint differs from bootstrap")
    if runtime_package_version() != "2.0.0rc6":
        raise NautilusRuntimeDataError("forward runtime requires the qualified Nautilus RC6 image")

    context_digest, _context_length, context_count, component_counts = _context_stream_contract(
        bundle
    )
    native_digest, warmup_tape_fingerprint, native_adapter_version, warmup_event_count = (
        _native_stream_contract(bundle)
    )
    if (
        bootstrap.native_event_stream_digest != native_digest
        or bootstrap.warmup_tape_fingerprint != warmup_tape_fingerprint
        or bootstrap.native_event_stream_adapter_version != native_adapter_version
        or bootstrap.warmup_event_count != warmup_event_count
    ):
        raise NautilusRuntimeDataError("forward bootstrap differs from native warm-up artifacts")
    if set(component_counts) != {component.component_id for component in bootstrap.components}:
        raise NautilusRuntimeDataError("forward context artifact differs from bootstrap components")

    runtime_fingerprint = content_digest(
        {
            "schema": "strategy-lab.nautilus-forward-runtime-session.v1",
            "engine_version": runtime_package_version(),
            "bootstrap_fingerprint": bootstrap.fingerprint,
            "bundle_digest": bootstrap.runtime_input_bundle_digest,
            "context_stream_digest": context_digest,
            "native_event_stream_digest": native_digest,
            "engine_input_fingerprint": bootstrap.engine_input_fingerprint,
        }
    )
    instrument_by_id = {
        definition["instrument_id"]: definition for definition in instrument_definitions
    }

    def rebuild_state() -> _NativeEngineState:
        with (
            open_context_stream() as seed_stream,
            open_context_stream() as bridge_context_stream,
            open_native_event_stream() as replay_native_stream,
            open_native_event_stream() as bridge_native_stream,
        ):
            windows, event_type_by_dependency = _seed_context_windows(
                seed_stream,
                bootstrap=bootstrap,
                engine_input=engine_input,
                context_stream_fingerprint=context_digest,
                expected_component_counts=component_counts,
            )
            bridge = build_native_strategy_bridge(
                engine_input,
                instrument_definitions,
                (),
                invocation_context_stream=bridge_context_stream,
                native_event_stream=bridge_native_stream,
                expected_context_count=context_count,
                expected_component_context_counts=component_counts,
                allow_forward_event_staging=True,
                retain_invocation_results=False,
            )
            engine = _create_backtest_engine(
                engine_input,
                venue_definition,
                instrument_definitions,
                bridge,
            )
            try:
                prior_native_init_time_ns = -1
                for record in _iter_warmup_events(
                    replay_native_stream,
                    source_tape_fingerprint=warmup_tape_fingerprint,
                    adapter_version=native_adapter_version,
                    event_count=warmup_event_count,
                ):
                    init_time = record["native_init_time_ns"]
                    if not isinstance(init_time, int) or isinstance(init_time, bool):
                        raise NautilusRuntimeDataError("native warm-up init time is invalid")
                    init_time_ns = cast(int, init_time)
                    prior_native_init_time_ns = max(prior_native_init_time_ns, init_time_ns)
                    NautilusBacktestForwardSession._run_native_event(
                        engine,
                        _record_from_wire(record),
                        instrument_by_id,
                        native_init_time_ns=init_time_ns,
                    )
                bridge.result_output()
                for prefix_event in bootstrap.processed_events:
                    event_type = event_type_by_dependency.get(
                        prefix_event.market_event.dependency_id
                    )
                    if event_type is None:
                        raise NautilusRuntimeDataError(
                            "processed prefix dependency has no declared native event type"
                        )
                    payload = VerifiedForwardMarketPayload(
                        prefix_event.canonical_event,
                        prefix_event.market_event,
                        prefix_event.verified_source_digest,
                    )
                    preparations: dict[str, ForwardStrategyContextPreparation] = {}
                    for component_id, window in windows.items():
                        if prefix_event.market_event.dependency_id in window.dependency_ids:
                            preparations[component_id] = window.prepare(
                                payload,
                                instance_id=bootstrap.instance_id,
                            )
                    event_time_ns = _native_event_datetime_ns(prefix_event.canonical_event)
                    wire_record = {
                        "dependency_id": prefix_event.market_event.dependency_id,
                        "event_id": prefix_event.market_event.event_id,
                        "instrument_id": prefix_event.market_event.instrument_id,
                        "event_type": event_type,
                        "event_time_ns": event_time_ns,
                        "sequence": prefix_event.canonical_event.sequence,
                        "values": dict(prefix_event.market_event.values),
                    }
                    prior_native_init_time_ns = max(
                        event_time_ns + 1,
                        prior_native_init_time_ns + 1,
                    )
                    bridge.stage_forward_event(
                        wire_record,
                        {key: item.context for key, item in preparations.items()},
                        instance_id=bootstrap.instance_id,
                        canonical_event=prefix_event.canonical_event,
                        native_init_time_ns=prior_native_init_time_ns,
                    )
                    record = _record_from_wire(wire_record)
                    NautilusBacktestForwardSession._run_native_event(
                        engine,
                        record,
                        instrument_by_id,
                        native_init_time_ns=prior_native_init_time_ns,
                    )
                    bridge.result_output()
                    bridge.take_forward_account_event()
                    for component_id, preparation in preparations.items():
                        windows[component_id].commit(preparation)
                return _NativeEngineState(
                    engine,
                    bridge,
                    windows,
                    prior_native_init_time_ns,
                    instrument_by_id,
                )
            except BaseException:
                engine.dispose()
                raise

    def session_factory(instance_id: str) -> NautilusBacktestForwardSession:
        if instance_id != bootstrap.instance_id:
            raise NautilusRuntimeDataError("forward session factory received another instance")
        return NautilusBacktestForwardSession(
            instance_id=instance_id,
            runtime_session_fingerprint=runtime_fingerprint,
            bootstrap=bootstrap,
            rebuild_state=rebuild_state,
            initial_state=rebuild_state(),
        )

    return session_factory


def _seed_context_windows(
    stream: BinaryIO,
    *,
    bootstrap: NautilusForwardRuntimeBootstrap,
    engine_input: Mapping[str, Any],
    context_stream_fingerprint: str,
    expected_component_counts: Mapping[str, int],
) -> tuple[dict[str, ForwardStrategyContextWindow], dict[str, str]]:
    raw_engine_bindings = engine_input.get("strategy_bindings")
    if not isinstance(raw_engine_bindings, list):
        raise NautilusRuntimeDataError("forward engine component bindings are invalid")
    engine_bindings = {
        item.get("component_id"): item for item in raw_engine_bindings if isinstance(item, Mapping)
    }
    bootstrap_components = {item.component_id: item for item in bootstrap.components}
    if set(engine_bindings) != set(bootstrap_components):
        raise NautilusRuntimeDataError("forward bootstrap component bindings differ from engine")
    context_bindings, contexts = deserialize_component_invocation_context_stream(
        stream,
        expected_component_counts=expected_component_counts,
    )
    if set(context_bindings) != set(bootstrap_components):
        raise NautilusRuntimeDataError("forward context stream differs from bootstrap components")
    windows: dict[str, ForwardStrategyContextWindow] = {}
    event_types: dict[str, str] = {}
    for component_id, context in contexts:
        component = bootstrap_components[component_id]
        binding = context_bindings[component_id]
        raw_binding = engine_bindings[component_id]
        if (
            binding.manifest.fingerprint != component.manifest_fingerprint
            or content_digest(binding.source) != component.source_digest
            or binding.entrypoint != raw_binding.get("entrypoint")
            or binding.manifest.fingerprint != raw_binding.get("strategy_manifest_fingerprint")
            or content_digest(context.parameters) != component.parameters_digest
            or context.random_seed != component.random_seed
        ):
            raise NautilusRuntimeDataError(
                "forward context identity differs from its immutable component binding"
            )
        window = windows.get(component_id)
        if window is None:
            window = ForwardStrategyContextWindow(
                bootstrap.instance_id,
                binding.manifest,
                parameters=context.parameters,
                random_seed=component.random_seed,
            )
            windows[component_id] = window
            for dependency in binding.manifest.data_dependencies:
                event_type = dependency.requirement.event_type
                prior_type = event_types.setdefault(dependency.dependency_id, event_type)
                if prior_type != event_type:
                    raise NautilusRuntimeDataError(
                        "portfolio components disagree on a native dependency event type"
                    )
        window.seed_from_authenticated_context(
            context,
            context_stream_fingerprint=context_stream_fingerprint,
        )
    if set(windows) != set(bootstrap_components):
        raise NautilusRuntimeDataError("forward context stream omitted a component")
    return windows, event_types


def _record_from_wire(value: Mapping[str, Any]) -> NautilusEventRecord:
    dependency_id = value.get("dependency_id")
    event_id = value.get("event_id")
    instrument_id = value.get("instrument_id")
    event_type = value.get("event_type")
    event_time_ns = value.get("event_time_ns")
    sequence = value.get("sequence")
    values = value.get("values")
    if not all(
        isinstance(item, str) and item
        for item in (dependency_id, event_id, instrument_id, event_type)
    ):
        raise NautilusRuntimeDataError("native event stream identity fields are invalid")
    if (
        not isinstance(event_time_ns, int)
        or isinstance(event_time_ns, bool)
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or not isinstance(values, Mapping)
    ):
        raise NautilusRuntimeDataError("native event stream record fields are invalid")
    return NautilusEventRecord(
        dependency_id=cast(str, dependency_id),
        event_id=cast(str, event_id),
        instrument_id=cast(str, instrument_id),
        event_type=cast(str, event_type),
        event_time_ns=cast(int, event_time_ns),
        sequence=cast(int, sequence),
        values=cast(Mapping[str, Any], values),
    )


def _iter_warmup_events(
    stream: BinaryIO,
    *,
    source_tape_fingerprint: str,
    adapter_version: str,
    event_count: int,
):
    from app.strategy_lab_v2.nautilus_native_event_stream import (
        deserialize_nautilus_native_event_stream,
    )

    yield from deserialize_nautilus_native_event_stream(
        stream,
        expected_source_tape_fingerprint=source_tape_fingerprint,
        expected_adapter_version=adapter_version,
        expected_event_count=event_count,
    )


def _create_backtest_engine(
    engine_input: Mapping[str, Any],
    venue_definition: Mapping[str, Any],
    instrument_definitions: list[Mapping[str, Any]],
    bridge: NativeStrategyBridge,
) -> Any:
    from nautilus_trader.backtest import BacktestEngine  # type: ignore[attr-defined]
    from nautilus_trader.common import LoggerConfig  # type: ignore[attr-defined]
    from nautilus_trader.config import BacktestEngineConfig  # type: ignore[attr-defined]
    from nautilus_trader.model import Currency  # type: ignore[attr-defined]

    native_venue, oms_type, account_type, balances = materialize_native_venue(venue_definition)
    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggerConfig(bypass_logging=True),
            bypass_logging=True,  # type: ignore[call-arg]
        )
    )
    engine.add_venue(
        native_venue,
        oms_type,
        account_type,
        balances,
        base_currency=Currency.from_str(venue_definition["base_currency"]),
        fee_model=materialize_native_fee_model(
            venue_definition["fee_model"],
            zero_fee_currency=venue_definition["base_currency"],
        ),
    )
    for definition in instrument_definitions:
        engine.add_instrument(materialize_native_instrument(definition))
    engine.add_strategy(bridge.strategy)
    return engine


def create_native_forward_session_factory_builder() -> ForwardSessionFactoryBuilder:
    """Adapt the verified CLI stream-openers to the concrete native session."""

    def build(
        bootstrap: NautilusForwardRuntimeBootstrap,
        bundle: Mapping[str, Any],
        open_context_stream: StreamOpener,
        open_native_event_stream: StreamOpener,
    ) -> Callable[[str], NautilusBacktestForwardSession]:
        return build_native_forward_session_factory(
            bootstrap,
            bundle,
            open_context_stream=open_context_stream,
            open_native_event_stream=open_native_event_stream,
        )

    return build


__all__ = [
    "NautilusBacktestForwardSession",
    "build_native_forward_session_factory",
    "create_native_forward_session_factory_builder",
]
