from __future__ import annotations

import json
from pathlib import Path

from tests.live import live_usage


def test_live_usage_ledger_aggregates_observed_counts_without_payloads(
    tmp_path: Path, monkeypatch
):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "run-test")
    live_usage._reset_for_test()
    live_usage.record_observation("fred", http_requests=2, response_bytes=100)
    live_usage.record_observation("fred", http_requests=1, response_bytes=50)
    live_usage.record_observation("coinbase", http_requests=1, response_bytes=25)

    assert live_usage.flush_observations(0) == ledger
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert rows == [
        {
            "at": rows[0]["at"],
            "exit_status": 0,
            "http_requests": 1,
            "operations": 1,
            "provider": "coinbase",
            "response_bytes": 25,
            "run_id": "run-test",
        },
        {
            "at": rows[1]["at"],
            "exit_status": 0,
            "http_requests": 3,
            "operations": 2,
            "provider": "fred",
            "response_bytes": 150,
            "run_id": "run-test",
        },
    ]
    assert live_usage.flush_observations(0) is None
