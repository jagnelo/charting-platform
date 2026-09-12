from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import UUID

import pytest

from tests.live import live_usage

_MERGER_SPEC = importlib.util.spec_from_file_location(
    "merge_provider_live_usage",
    Path(__file__).resolve().parents[3] / "scripts/merge-provider-live-usage.py",
)
assert _MERGER_SPEC and _MERGER_SPEC.loader
_MERGER = importlib.util.module_from_spec(_MERGER_SPEC)
_MERGER_SPEC.loader.exec_module(_MERGER)


def test_live_usage_ledger_aggregates_observed_counts_without_payloads(
    tmp_path: Path, monkeypatch
):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "run-test")
    live_usage._reset_for_test()
    live_usage.record_observation(
        "fred",
        http_requests=2,
        response_bytes=100,
        response_headers={
            "X-RateLimit-Remaining": "17",
            "X-Api-Ratelimit-Remaining": "87",
            "Total-Records-On-Page": "2",
            "Authorization": "secret",
        },
    )
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
            "response_headers": {},
            "usage_scope": "unspecified",
        },
        {
            "at": rows[1]["at"],
            "exit_status": 0,
            "http_requests": 3,
            "operations": 2,
            "provider": "fred",
            "response_bytes": 150,
            "run_id": "run-test",
            "response_headers": {
                "x-api-ratelimit-remaining": "87",
                "x-ratelimit-remaining": "17",
                "total-records-on-page": "2",
            },
            "usage_scope": "unspecified",
        },
    ]
    assert live_usage.flush_observations(0) is None


def test_live_usage_generates_fresh_uuid_when_run_id_is_not_supplied(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.delenv("PROVIDER_LIVE_RUN_ID", raising=False)
    live_usage._reset_for_test()
    live_usage.record_observation("fred", http_requests=1, response_bytes=10)

    assert live_usage.flush_observations(0) == ledger
    row = json.loads(ledger.read_text())
    generated = UUID(row["run_id"])
    assert str(generated) == row["run_id"]
    assert not row["run_id"].startswith("pid-")


def test_live_usage_preflight_opens_configured_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "unit-test")

    assert live_usage.ensure_usage_scope_configured() == "unit-test"
    assert live_usage.ensure_ledger_writable() == ledger
    assert ledger.exists()
    assert ledger.read_text() == ""
    assert ledger.stat().st_mode & 0o077 == 0


def test_live_usage_preflight_hardens_existing_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    ledger.write_text("existing receipt\n")
    ledger.chmod(0o644)
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))

    assert live_usage.ensure_ledger_writable() == ledger
    assert ledger.stat().st_mode & 0o077 == 0
    assert ledger.read_text() == "existing receipt\n"


def test_live_usage_preflight_fails_before_provider_calls_when_ledger_unwritable(
    tmp_path, monkeypatch
):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("blocker")
    ledger = parent_file / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))

    with pytest.raises(RuntimeError, match="ledger is not writable"):
        live_usage.ensure_ledger_writable()


@pytest.mark.parametrize("scope", ["", "x" * 129, "x\nlabel"])
def test_live_usage_preflight_rejects_missing_or_invalid_scope(monkeypatch, scope):
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", scope)

    with pytest.raises(RuntimeError, match="scope is missing or invalid"):
        live_usage.ensure_usage_scope_configured()


def test_merge_provider_live_usage_sanitizes_and_deduplicates_receipts(tmp_path: Path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    destination = tmp_path / "owner" / "provider-live-usage.jsonl"
    first.write_text(
        json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "run_id": "github-1",
                "provider": "fred",
                "operations": 1,
                "http_requests": 2,
                "response_bytes": 100,
                "exit_status": 0,
                "response_headers": {
                    "x-api-ratelimit-limit": "100",
                    "x-api-ratelimit-remaining": "96",
                    "x-api-ratelimit-reset": "1700000000",
                    "x-api-ratelimit-consumed": "4",
                },
                "payload": "must-not-be-copied",
            }
        )
        + "\n"
    )
    second.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "at": "2026-09-10T05:00:01+00:00",
                        "run_id": "github-1",
                        "provider": "fred",
                        "operations": 9,
                        "http_requests": 9,
                        "response_bytes": 9,
                        "exit_status": 0,
                    }
                ),
                json.dumps(
                    {
                        "at": "2026-09-10T05:00:02+00:00",
                        "run_id": "github-1",
                        "provider": "coinbase",
                        "operations": 1,
                        "http_requests": 1,
                        "response_bytes": 20,
                        "exit_status": 0,
                    }
                ),
                json.dumps(
                    {
                        "at": "2026-09-10T05:00:03+00:00",
                        "provider": "invalid-fraction",
                        "operations": 1.5,
                        "http_requests": 1,
                        "response_bytes": 20,
                        "exit_status": 0,
                    }
                ),
            ]
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([first, second], destination)

    assert result["accepted"] == 2
    assert result["duplicates"] == 1
    assert result["rejected"] == 1
    rows = [json.loads(line) for line in destination.read_text().splitlines()]
    assert len(rows) == 2
    assert all("payload" not in row for row in rows)
    assert {row["provider"] for row in rows} == {"fred", "coinbase"}
    fred_row = next(row for row in rows if row["provider"] == "fred")
    assert fred_row["response_headers"] == {
        "x-api-ratelimit-consumed": "4",
        "x-api-ratelimit-limit": "100",
        "x-api-ratelimit-remaining": "96",
        "x-api-ratelimit-reset": "1700000000",
    }
    assert destination.stat().st_mode & 0o077 == 0


def test_merge_provider_live_usage_keeps_same_run_separate_by_usage_scope(tmp_path: Path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    base = {
        "at": "2026-09-10T05:00:00+00:00",
        "run_id": "shared-run-id",
        "provider": "fred",
        "operations": 1,
        "http_requests": 1,
        "response_bytes": 10,
        "exit_status": 0,
    }
    first.write_text(json.dumps({**base, "usage_scope": "local-dev"}) + "\n")
    second.write_text(json.dumps({**base, "usage_scope": "github-provider-live"}) + "\n")

    result = _MERGER.merge_receipts([first, second], destination)

    assert result["accepted"] == 2
    assert result["duplicates"] == 0
    rows = [json.loads(line) for line in destination.read_text().splitlines()]
    assert {row["usage_scope"] for row in rows} == {
        "local-dev",
        "github-provider-live",
    }


def test_merge_provider_live_usage_rejects_malformed_rows_without_exposing_values(
    tmp_path: Path,
):
    source = tmp_path / "receipt.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    source.write_text(
        "not-json\n"
        + json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "provider": "fred",
                "operations": 1,
                "http_requests": 1,
                "response_bytes": 10,
                "exit_status": 0,
            }
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([source], destination)

    assert result["accepted"] == 1
    assert result["rejected"] == 1
    assert len(destination.read_text().splitlines()) == 1


def test_merge_provider_live_usage_rejects_non_capacity_headers(tmp_path: Path):
    source = tmp_path / "receipt.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    source.write_text(
        json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "provider": "fred",
                "operations": 1,
                "http_requests": 1,
                "response_bytes": 10,
                "exit_status": 0,
                "response_headers": {"authorization": "secret"},
            }
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([source], destination)

    assert result["accepted"] == 0
    assert result["rejected"] == 1
    assert not destination.read_text()
