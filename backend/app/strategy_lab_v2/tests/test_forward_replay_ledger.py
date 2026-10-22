from __future__ import annotations

import pytest

from app.strategy_lab_v2.tests.forward_replay_ledger import DurableReplayLedger


def test_durable_replay_ledger_settles_once_then_acknowledges_idempotently(tmp_path) -> None:
    ledger = DurableReplayLedger(tmp_path / "replay.sqlite3")
    values = {
        "instance_id": "forward-1",
        "event_id": "event-1",
        "event_fingerprint": "sha256:event",
        "result_fingerprint": "sha256:result",
        "next_checkpoint": "sha256:checkpoint",
    }

    assert ledger.settle_once(**values) == values["result_fingerprint"]
    assert ledger.receipt(instance_id="forward-1", event_id="event-1") == (
        values["result_fingerprint"],
        False,
    )
    assert ledger.settle_once(**values) == values["result_fingerprint"]
    assert ledger.acknowledge_once(instance_id="forward-1", event_id="event-1")
    assert not ledger.acknowledge_once(instance_id="forward-1", event_id="event-1")
    assert ledger.receipt(instance_id="forward-1", event_id="event-1") == (
        values["result_fingerprint"],
        True,
    )


def test_durable_replay_ledger_rejects_changed_execution_effects(tmp_path) -> None:
    ledger = DurableReplayLedger(tmp_path / "replay.sqlite3")
    ledger.settle_once(
        instance_id="forward-1",
        event_id="event-1",
        event_fingerprint="sha256:event",
        result_fingerprint="sha256:result",
        next_checkpoint="sha256:checkpoint",
    )

    with pytest.raises(ValueError, match="different native account effects"):
        ledger.settle_once(
            instance_id="forward-1",
            event_id="event-1",
            event_fingerprint="sha256:event",
            result_fingerprint="sha256:different-result",
            next_checkpoint="sha256:checkpoint",
        )
