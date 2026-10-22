from __future__ import annotations

from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_equity_trace import (
    NautilusAccountEquityTraceReference,
    NautilusAccountEquityTraceWriter,
    iter_verified_nautilus_account_equity_observations,
    verify_nautilus_account_equity_trace_file,
)


def _writer(path):
    return NautilusAccountEquityTraceWriter(
        path,
        engine_input={
            "trial_id": "trial-1",
            "attempt_id": "attempt-1",
            "data_snapshot_fingerprint": content_digest("snapshot"),
            "event_tape": {"source_tape_fingerprint": content_digest("tape")},
            "evaluation_window": {
                "fingerprint": content_digest("window"),
                "start_ns": 100,
                "end_ns": 200,
            },
        },
        portfolio={
            "fingerprint": content_digest("portfolio"),
            "base_currency": "USD",
            "initial_capital": "1000.00",
        },
    )


def _event(event_id: str, timestamp: int, sequence: int) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_time_ns": timestamp,
        "sequence": sequence,
    }


def _write_mark(
    writer,
    event,
    index: int,
    equity: str,
    *,
    gross: str | None = None,
    signed_net: str | None = None,
) -> None:
    writer.write(
        event_id=event["event_id"],
        event_time_ns=event["event_time_ns"],
        event_index=index,
        source_sequence=event["sequence"],
        account_equity=Decimal(equity),
        account_cash_balance=Decimal("1000.00"),
        gross_base_exposure=None if gross is None else Decimal(gross),
        signed_net_base_exposure=None if signed_net is None else Decimal(signed_net),
    )


def test_native_equity_trace_is_bounded_oos_and_bound_to_tape(tmp_path) -> None:
    path = tmp_path / "account-equity.parquet"
    writer = _writer(path)
    events = (
        _event("warmup", 99, 1),
        _event("scoring-1", 100, 2),
        _event("scoring-2", 150, 3),
    )
    _write_mark(writer, events[0], 0, "1000")
    _write_mark(writer, events[1], 1, "1001.25", gross="500", signed_net="-250")
    _write_mark(writer, events[2], 2, "998.75", gross="800", signed_net="400")

    reference = writer.finish()

    assert reference.observation_count == 2
    assert reference.scoring_start_ns == 100
    assert reference.scoring_end_ns == 200
    assert NautilusAccountEquityTraceReference.from_wire(reference.to_wire()) == reference
    verify_nautilus_account_equity_trace_file(
        reference,
        path,
        expected_events=tuple(
            {"index": index, "event": event} for index, event in enumerate(events)
        ),
    )


def test_verified_equity_observations_preserve_canonical_event_times(tmp_path) -> None:
    path = tmp_path / "account-equity.parquet"
    writer = _writer(path)
    events = (_event("scoring-1", 100, 1), _event("scoring-2", 150, 2))
    _write_mark(writer, events[0], 0, "1000", gross="500", signed_net="-250")
    _write_mark(writer, events[1], 1, "999.5", gross="800", signed_net="400")
    reference = writer.finish()

    observations = tuple(
        iter_verified_nautilus_account_equity_observations(
            reference,
            path,
            expected_events=tuple(
                {"index": index, "event": event} for index, event in enumerate(events)
            ),
        )
    )

    assert tuple(item.event_time_ns for item in observations) == (100, 150)
    assert tuple(item.account_equity for item in observations) == (
        Decimal("1000"),
        Decimal("999.5"),
    )
    assert tuple(item.account_cash_balance for item in observations) == (
        Decimal("1000.00"),
        Decimal("1000.00"),
    )
    assert tuple(item.gross_base_exposure for item in observations) == (
        Decimal("500.000000000000000000"),
        Decimal("800.000000000000000000"),
    )
    assert tuple(item.signed_net_base_exposure for item in observations) == (
        Decimal("-250.000000000000000000"),
        Decimal("400.000000000000000000"),
    )


def test_native_equity_trace_requires_exposure_fields_as_a_valid_pair(tmp_path) -> None:
    writer = _writer(tmp_path / "account-equity.parquet")
    event = _event("scoring-1", 100, 1)

    with pytest.raises(ValueError, match="both be present or unavailable"):
        writer.write(
            event_id=event["event_id"],
            event_time_ns=event["event_time_ns"],
            event_index=0,
            source_sequence=event["sequence"],
            account_equity=Decimal("1000"),
            account_cash_balance=Decimal("1000"),
            gross_base_exposure=Decimal("100"),
        )

    with pytest.raises(ValueError, match="absolute net exposure cannot exceed gross"):
        _write_mark(writer, event, 0, "1000", gross="100", signed_net="101")


def test_native_equity_trace_rejects_omitted_scoring_marks(tmp_path) -> None:
    path = tmp_path / "account-equity.parquet"
    writer = _writer(path)
    first = _event("scoring-1", 100, 1)
    second = _event("scoring-2", 150, 2)
    _write_mark(writer, first, 0, "1000")
    reference = writer.finish()

    with pytest.raises(ValueError, match="omitted scoring tape events"):
        verify_nautilus_account_equity_trace_file(
            reference,
            path,
            expected_events=(
                {"index": 0, "event": first},
                {"index": 1, "event": second},
            ),
        )


def test_native_equity_trace_rejects_tape_mismatch_and_byte_drift(tmp_path) -> None:
    path = tmp_path / "account-equity.parquet"
    writer = _writer(path)
    event = _event("scoring-1", 100, 1)
    _write_mark(writer, event, 0, "1000")
    reference = writer.finish()

    with pytest.raises(ValueError, match="differs from its tape event"):
        verify_nautilus_account_equity_trace_file(
            reference,
            path,
            expected_events=({"index": 0, "event": _event("other", 100, 1)},),
        )

    with path.open("ab") as output:
        output.write(b"drift")
    with pytest.raises(ValueError, match="file length differs"):
        verify_nautilus_account_equity_trace_file(
            reference,
            path,
            expected_events=({"index": 0, "event": event},),
        )


def test_native_equity_trace_requires_at_least_one_scoring_observation(tmp_path) -> None:
    writer = _writer(tmp_path / "account-equity.parquet")
    _write_mark(writer, _event("warmup", 99, 1), 0, "1000")

    with pytest.raises(ValueError, match="no scoring observations"):
        writer.finish()


def test_native_equity_trace_rejects_values_unrepresentable_at_fixed_scale(tmp_path) -> None:
    writer = _writer(tmp_path / "account-equity.parquet")

    with pytest.raises(ValueError, match="exceeds the account-equity Arrow precision"):
        _write_mark(writer, _event("scoring-1", 100, 1), 0, "1E20")
