from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_native_reports import (
    NAUTILUS_NATIVE_REPORT_KINDS,
    NautilusNativeReportsReference,
    NautilusNativeReportsWriter,
    iter_nautilus_native_report_records,
    verify_nautilus_native_reports_file,
)


def _engine_input() -> dict[str, object]:
    return {
        "trial_id": "trial-1",
        "attempt_id": "attempt-1",
        "data_snapshot_fingerprint": content_digest("snapshot"),
        "event_tape": {"source_tape_fingerprint": content_digest("tape")},
        "evaluation_window": {
            "fingerprint": content_digest("window"),
            "start_ns": 100,
            "end_ns": 200,
        },
    }


def _portfolio() -> dict[str, str]:
    return {"fingerprint": content_digest("portfolio")}


def _reports() -> dict[str, pd.DataFrame]:
    return {
        "account": pd.DataFrame([{"currency": "USD", "total": Decimal("998.25")}]),
        "fills": pd.DataFrame(
            [
                {
                    "instrument_id": "AAPL.SIM",
                    "last_qty": Decimal("2"),
                    "commission": "2.00 USD",
                    "ts_event": pd.Timestamp("2026-01-02T15:00:00Z"),
                }
            ]
        ),
        "orders": pd.DataFrame([{"client_order_id": "order-1", "status": "FILLED"}]),
        "positions": pd.DataFrame(columns=["instrument_id", "quantity"]),
    }


def test_native_reports_are_bounded_window_bound_and_host_verifiable(tmp_path) -> None:
    path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        path,
        engine_input=_engine_input(),
        portfolio=_portfolio(),
    )
    writer.write_reports(_reports())
    reference = writer.finish()

    assert reference.row_counts == (("account", 1), ("fills", 1), ("orders", 1), ("positions", 0))
    assert reference.scoring_start_ns == 100
    assert reference.scoring_end_ns == 200
    assert NautilusNativeReportsReference.from_wire(reference.to_wire()) == reference
    verify_nautilus_native_reports_file(reference, path)
    assert tuple(iter_nautilus_native_report_records(reference, path)) == (
        ("account", 0, {"currency": "USD", "total": "998.25"}),
        (
            "fills",
            0,
            {
                "commission": "2.00 USD",
                "instrument_id": "AAPL.SIM",
                "last_qty": "2",
                "ts_event": "2026-01-02T15:00:00+00:00",
            },
        ),
        ("orders", 0, {"client_order_id": "order-1", "status": "FILLED"}),
    )

    table = pq.read_table(path)
    records = table.column("record_json").to_pylist()
    assert json.loads(records[1]) == {
        "commission": "2.00 USD",
        "instrument_id": "AAPL.SIM",
        "last_qty": "2",
        "ts_event": "2026-01-02T15:00:00+00:00",
    }
    assert (
        table.schema.metadata[b"evaluation_window_fingerprint"] == content_digest("window").encode()
    )


def test_native_reports_rejects_unknown_report_kind_and_nonfinite_row(tmp_path) -> None:
    writer = NautilusNativeReportsWriter(
        tmp_path / "native-reports.parquet",
        engine_input=_engine_input(),
        portfolio=_portfolio(),
    )
    with pytest.raises(ValueError, match="must contain account"):
        writer.write_reports({"unknown": pd.DataFrame([{"value": 1}])})
    writer.abort()

    writer = NautilusNativeReportsWriter(
        tmp_path / "nonfinite.parquet",
        engine_input=_engine_input(),
        portfolio=_portfolio(),
    )
    reports = _reports()
    reports["orders"] = pd.DataFrame([{"price": float("inf")}])
    with pytest.raises(ValueError, match="non-finite"):
        writer.write_reports(reports)
    writer.abort()


def test_native_reports_preserve_bounded_structured_values(tmp_path) -> None:
    path = tmp_path / "structured-native-reports.parquet"
    reports = _reports()
    reports["account"] = pd.DataFrame(
        [
            {
                "currency": "USD",
                "state_events": [{"balances": ["1000.00 USD"], "sequence": 1}],
            }
        ]
    )
    writer = NautilusNativeReportsWriter(
        path,
        engine_input=_engine_input(),
        portfolio=_portfolio(),
    )
    writer.write_reports(reports)
    reference = writer.finish()

    assert tuple(iter_nautilus_native_report_records(reference, path))[0] == (
        "account",
        0,
        {
            "currency": "USD",
            "state_events": [{"balances": ["1000.00 USD"], "sequence": 1}],
        },
    )


def test_native_reports_verify_rejects_byte_drift_and_incomplete_reference(tmp_path) -> None:
    path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        path,
        engine_input=_engine_input(),
        portfolio=_portfolio(),
    )
    writer.write_reports(_reports())
    reference = writer.finish()
    path.write_bytes(path.read_bytes() + b"drift")

    with pytest.raises(ValueError, match="byte length differs"):
        verify_nautilus_native_reports_file(reference, path)


def test_native_report_reader_rejects_noncanonical_or_duplicate_json_keys(tmp_path) -> None:
    path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(path, engine_input=_engine_input(), portfolio=_portfolio())
    writer.write_reports(_reports())
    reference = writer.finish()

    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["record_json"] = '{"currency":"USD","currency":"EUR","total":"1"}'
    changed = pa.Table.from_pylist(rows, schema=table.schema)
    pq.write_table(changed, path, compression="zstd", use_dictionary=False)
    data = path.read_bytes()
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    artifact = reference.artifact
    changed_artifact = type(artifact)(
        content_digest=digest,
        byte_length=len(data),
        media_type=artifact.media_type,
        schema_version=artifact.schema_version,
        storage_key=digest,
        retention_class=artifact.retention_class,
    )
    changed_reference = NautilusNativeReportsReference(
        artifact=changed_artifact,
        trial_id=reference.trial_id,
        attempt_id=reference.attempt_id,
        portfolio_fingerprint=reference.portfolio_fingerprint,
        snapshot_fingerprint=reference.snapshot_fingerprint,
        source_tape_fingerprint=reference.source_tape_fingerprint,
        evaluation_window_fingerprint=reference.evaluation_window_fingerprint,
        scoring_start_ns=reference.scoring_start_ns,
        scoring_end_ns=reference.scoring_end_ns,
        row_counts=reference.row_counts,
    )

    with pytest.raises(ValueError, match="duplicate JSON key"):
        tuple(iter_nautilus_native_report_records(changed_reference, path))

    wire = reference.to_wire()
    wire["row_counts"] = {kind: 0 for kind in NAUTILUS_NATIVE_REPORT_KINDS}
    with pytest.raises(ValueError, match="at least one report row"):
        NautilusNativeReportsReference.from_wire(wire)
