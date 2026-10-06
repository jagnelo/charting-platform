"""Small durable receipt ledger shared by exact-process recovery probes."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class DurableReplayLedger:
    """Model the settlement-before-ACK crash window with SQLite durability."""

    def __init__(self, path: Path) -> None:
        self._path = path
        with sqlite3.connect(path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS settlements (
                       instance_id TEXT NOT NULL,
                       event_id TEXT NOT NULL,
                       event_fingerprint TEXT NOT NULL,
                       result_fingerprint TEXT NOT NULL,
                       next_checkpoint TEXT NOT NULL,
                       acked INTEGER NOT NULL DEFAULT 0,
                       PRIMARY KEY (instance_id, event_id)
                   )"""
            )

    def settle_once(
        self,
        *,
        instance_id: str,
        event_id: str,
        event_fingerprint: str,
        result_fingerprint: str,
        next_checkpoint: str,
    ) -> str:
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT event_fingerprint, result_fingerprint
                   FROM settlements WHERE instance_id = ? AND event_id = ?""",
                (instance_id, event_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO settlements
                       (instance_id, event_id, event_fingerprint, result_fingerprint,
                        next_checkpoint, acked)
                       VALUES (?, ?, ?, ?, ?, 0)""",
                    (instance_id, event_id, event_fingerprint, result_fingerprint, next_checkpoint),
                )
                return result_fingerprint
            if existing[0] != event_fingerprint:
                raise ValueError("durable event identity conflicts with the prior settlement")
            if existing[1] != result_fingerprint:
                raise ValueError("durable replay produced different native account effects")
            return str(existing[1])

    def acknowledge_once(self, *, instance_id: str, event_id: str) -> bool:
        with sqlite3.connect(self._path) as connection:
            cursor = connection.execute(
                """UPDATE settlements SET acked = 1
                   WHERE instance_id = ? AND event_id = ? AND acked = 0""",
                (instance_id, event_id),
            )
            if cursor.rowcount == 1:
                return True
            existing = connection.execute(
                """SELECT acked FROM settlements WHERE instance_id = ? AND event_id = ?""",
                (instance_id, event_id),
            ).fetchone()
            if existing is None:
                raise ValueError("cannot acknowledge a forward event without durable settlement")
            return False

    def receipt(self, *, instance_id: str, event_id: str) -> tuple[str, bool] | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """SELECT result_fingerprint, acked FROM settlements
                   WHERE instance_id = ? AND event_id = ?""",
                (instance_id, event_id),
            ).fetchone()
        return None if row is None else (str(row[0]), bool(row[1]))
