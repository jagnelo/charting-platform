from __future__ import annotations

import pytest

from app.strategy_lab_v2.nautilus_forward_native_runtime import (
    NautilusBacktestForwardSession,
    _NativeEngineState,
)


class _FakeEngine:
    def __init__(self, order: list[str], name: str) -> None:
        self.order = order
        self.name = name

    def dispose(self) -> None:
        self.order.append(f"dispose:{self.name}")


def _state(order: list[str], name: str) -> _NativeEngineState:
    return _NativeEngineState(
        engine=_FakeEngine(order, name),
        bridge=None,
        windows={},
        native_init_time_ns=0,
        instrument_definitions={},
    )


def _session(
    state: _NativeEngineState,
    rebuild_state,
) -> NautilusBacktestForwardSession:
    session = object.__new__(NautilusBacktestForwardSession)
    session._state = state
    session._history = []
    session._rebuild_state = rebuild_state
    session._closed = False
    return session


def test_restore_disposes_previous_native_engine_before_rebuilding() -> None:
    order: list[str] = []
    old_state = _state(order, "old")
    replacement = _state(order, "replacement")

    def rebuild() -> _NativeEngineState:
        assert order == ["dispose:old"]
        order.append("rebuild")
        return replacement

    session = _session(old_state, rebuild)
    session._replace_state_with_replay(0)

    assert session._state is replacement
    assert session._closed is False
    assert order == ["dispose:old", "rebuild"]


def test_failed_restore_rebuild_leaves_session_closed() -> None:
    order: list[str] = []
    session = _session(
        _state(order, "old"),
        lambda: (_ for _ in ()).throw(RuntimeError("rebuild failed")),
    )

    with pytest.raises(RuntimeError, match="rebuild failed"):
        session._replace_state_with_replay(0)

    assert session._closed is True
    assert order == ["dispose:old"]
