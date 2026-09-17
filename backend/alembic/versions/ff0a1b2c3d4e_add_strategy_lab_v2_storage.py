"""Additive storage schema for Strategy Lab v2 contracts.

The v2 adapters deliberately remain registration-neutral: they validate and
persist immutable contract projections but do not create tables themselves.
This migration is the single additive schema boundary for those adapters. It
does not alter the legacy ``strategy_definition``, ``strategy_version``, or
``strategy_run`` tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "ff0a1b2c3d4e"
down_revision: str | None = "fe4f5a6b7c8d"
branch_labels = None
depends_on = None


_DDL: tuple[tuple[str, str], ...] = (
    (
        "strategy_lab_v2_aggregates",
        """
        CREATE TABLE strategy_lab_v2_aggregates (
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            version BIGINT NOT NULL,
            state_json TEXT NOT NULL,
            state_fingerprint TEXT NOT NULL,
            PRIMARY KEY (aggregate_type, aggregate_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_storage_receipts",
        """
        CREATE TABLE strategy_lab_v2_storage_receipts (
            request_id TEXT PRIMARY KEY,
            request_fingerprint TEXT NOT NULL,
            outcome_fingerprint TEXT NOT NULL,
            committed_json TEXT NOT NULL
        )
        """,
    ),
    (
        "strategy_lab_v2_acquisition_receipts",
        """
        CREATE TABLE strategy_lab_v2_acquisition_receipts (
            owner_id TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            snapshot_fingerprint TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            provider_snapshot_id TEXT NOT NULL,
            coverage_resolution_fingerprint TEXT NOT NULL,
            provider_receipt_digest TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            receipt_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, request_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_artifact_commits",
        """
        CREATE TABLE strategy_lab_v2_artifact_commits (
            commit_key TEXT PRIMARY KEY,
            manifest_fingerprint TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            storage_key TEXT NOT NULL UNIQUE,
            byte_length BIGINT NOT NULL,
            committed_at TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL
        )
        """,
    ),
    (
        "strategy_lab_v2_artifact_retention",
        """
        CREATE TABLE strategy_lab_v2_artifact_retention (
            manifest_fingerprint TEXT PRIMARY KEY,
            content_digest TEXT NOT NULL,
            retention_class TEXT NOT NULL,
            retention_eligible_at TEXT NULL,
            state_fingerprint TEXT NOT NULL
        )
        """,
    ),
    (
        "strategy_lab_v2_artifact_retention_pins",
        """
        CREATE TABLE strategy_lab_v2_artifact_retention_pins (
            pin_id TEXT PRIMARY KEY,
            manifest_fingerprint TEXT NOT NULL,
            artifact_manifest_fingerprint TEXT NOT NULL,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NULL,
            released_at TEXT NULL,
            pin_fingerprint TEXT NOT NULL,
            UNIQUE (manifest_fingerprint, pin_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_capability_summaries",
        """
        CREATE TABLE strategy_lab_v2_capability_summaries (
            owner_id TEXT NOT NULL,
            report_fingerprint TEXT NOT NULL,
            binding_fingerprint TEXT NOT NULL,
            summary_fingerprint TEXT NOT NULL,
            decision TEXT NOT NULL,
            data_gaps_json TEXT NOT NULL,
            execution_gaps_json TEXT NOT NULL,
            degradations_json TEXT NOT NULL,
            ranking_eligible BOOLEAN NOT NULL,
            executable BOOLEAN NOT NULL,
            authoritative BOOLEAN NOT NULL,
            can_publish_authoritative_results BOOLEAN NOT NULL,
            PRIMARY KEY (owner_id, report_fingerprint, binding_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_commands",
        """
        CREATE TABLE strategy_lab_v2_execution_commands (
            owner_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            command_id TEXT NOT NULL,
            command_fingerprint TEXT NOT NULL,
            receipt_fingerprint TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            effect TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            PRIMARY KEY (owner_id, idempotency_key),
            UNIQUE (owner_id, command_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_coverage_attestations",
        """
        CREATE TABLE strategy_lab_v2_coverage_attestations (
            owner_id TEXT NOT NULL,
            series_content_digest TEXT NOT NULL,
            evidence_digest TEXT NOT NULL,
            instrument_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_granularity TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            session TEXT NOT NULL,
            feed TEXT NOT NULL,
            adjustment TEXT NOT NULL,
            corporate_action_semantics TEXT NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            row_count BIGINT NOT NULL,
            calendar_digest TEXT NOT NULL,
            complete BOOLEAN NOT NULL,
            gap_free BOOLEAN NOT NULL,
            provider_adapter TEXT NOT NULL,
            attested_at TEXT NOT NULL,
            attestation_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, series_content_digest)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_events",
        """
        CREATE TABLE strategy_lab_v2_execution_events (
            event_id TEXT PRIMARY KEY,
            event_fingerprint TEXT NOT NULL,
            trial_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            event_type TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            producer TEXT NOT NULL,
            causation_id TEXT NULL,
            UNIQUE (trial_id, attempt_id, sequence)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_event_cursors",
        """
        CREATE TABLE strategy_lab_v2_execution_event_cursors (
            trial_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            last_event_id TEXT NULL,
            cursor_fingerprint TEXT NOT NULL,
            PRIMARY KEY (trial_id, attempt_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_audit",
        """
        CREATE TABLE strategy_lab_v2_execution_audit (
            entry_id TEXT PRIMARY KEY,
            entry_fingerprint TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            entry_type TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            correlation_id TEXT NULL,
            UNIQUE (aggregate_type, aggregate_id, sequence)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_outbox",
        """
        CREATE TABLE strategy_lab_v2_execution_outbox (
            message_id TEXT PRIMARY KEY,
            message_fingerprint TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            published BOOLEAN NOT NULL DEFAULT FALSE
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_outcomes",
        """
        CREATE TABLE strategy_lab_v2_execution_outcomes (
            owner_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            submission_id TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            result_digest TEXT NULL,
            error_json TEXT NULL,
            state_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, attempt_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_progress",
        """
        CREATE TABLE strategy_lab_v2_execution_progress (
            owner_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            phase TEXT NOT NULL,
            completed_units BIGINT NOT NULL,
            total_units BIGINT NOT NULL,
            cancellation_requested BOOLEAN NOT NULL,
            updated_at TEXT NOT NULL,
            applied_update_fingerprints_json TEXT NOT NULL,
            checkpoint_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, attempt_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_summaries",
        """
        CREATE TABLE strategy_lab_v2_execution_summaries (
            owner_id TEXT NOT NULL,
            submission_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            state_key TEXT NOT NULL,
            outcome_sequence BIGINT NOT NULL,
            progress_sequence BIGINT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_phase TEXT NOT NULL,
            completed_units BIGINT NOT NULL,
            total_units BIGINT NOT NULL,
            cancellation_requested BOOLEAN NOT NULL,
            updated_at TEXT NOT NULL,
            result_digest TEXT NULL,
            publication_fingerprint TEXT NULL,
            error_json TEXT NULL,
            summary_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, state_key),
            UNIQUE (owner_id, summary_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_forward_instances",
        """
        CREATE TABLE strategy_lab_v2_forward_instances (
            owner_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            portfolio_fingerprint TEXT NOT NULL,
            warmup_snapshot_fingerprint TEXT NOT NULL,
            carry_in_mode TEXT NOT NULL,
            state TEXT NOT NULL,
            last_event_id TEXT NULL,
            last_event_sequence BIGINT NOT NULL,
            correction_count BIGINT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            processed_event_ids_json TEXT NOT NULL,
            buffered_event_ids_json TEXT NOT NULL,
            correction_event_ids_json TEXT NOT NULL,
            duplicate_count BIGINT NOT NULL,
            out_of_order_count BIGINT NOT NULL,
            instance_fingerprint TEXT NOT NULL,
            checkpoint_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, instance_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_forward_warmups",
        """
        CREATE TABLE strategy_lab_v2_forward_warmups (
            owner_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            warmup_snapshot_fingerprint TEXT NOT NULL,
            carry_in_mode TEXT NOT NULL,
            warmup_result_fingerprint TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            final_event_id TEXT NULL,
            final_event_sequence BIGINT NOT NULL,
            final_event_fingerprint TEXT NULL,
            receipt_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, instance_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_forward_seen_events",
        """
        CREATE TABLE strategy_lab_v2_forward_seen_events (
            owner_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_fingerprint TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            seen_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, instance_id, event_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_forward_replays",
        """
        CREATE TABLE strategy_lab_v2_forward_replays (
            owner_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            replay_id TEXT NOT NULL,
            correction_event_id TEXT NOT NULL,
            original_event_id TEXT NOT NULL,
            base_checkpoint_fingerprint TEXT NOT NULL,
            warmup_receipt_fingerprint TEXT NOT NULL,
            planned_at TEXT NOT NULL,
            replay_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, instance_id, replay_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_legacy_imports",
        """
        CREATE TABLE strategy_lab_v2_legacy_imports (
            owner_id TEXT NOT NULL,
            legacy_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            source_version TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            mapping_version TEXT NOT NULL,
            supported BOOLEAN NOT NULL,
            conversion_fingerprint TEXT NULL,
            notes_json TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, legacy_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_artifact_lineage",
        """
        CREATE TABLE strategy_lab_v2_artifact_lineage (
            semantic_key TEXT PRIMARY KEY,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            artifact_manifest_fingerprint TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            parent_manifest_fingerprint TEXT NULL,
            entry_fingerprint TEXT NOT NULL,
            UNIQUE (owner_type, owner_id, semantic_key)
        )
        """,
    ),
    (
        "strategy_lab_v2_metric_sets",
        """
        CREATE TABLE strategy_lab_v2_metric_sets (
            owner_id TEXT NOT NULL,
            metric_set_fingerprint TEXT NOT NULL,
            metric_set_id TEXT NOT NULL,
            trial_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            definition_version TEXT NOT NULL,
            values_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metric_set_json TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, metric_set_fingerprint),
            UNIQUE (owner_id, attempt_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_result_completions",
        """
        CREATE TABLE strategy_lab_v2_result_completions (
            owner_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            completion_fingerprint TEXT NOT NULL,
            result_fingerprint TEXT NOT NULL,
            runtime_state_fingerprint TEXT NOT NULL,
            outcome_fingerprint TEXT NOT NULL,
            progress_fingerprint TEXT NOT NULL,
            publication_fingerprint TEXT NOT NULL,
            artifact_commit_keys_json TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, attempt_id),
            UNIQUE (owner_id, completion_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_result_manifests",
        """
        CREATE TABLE strategy_lab_v2_result_manifests (
            owner_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            manifest_fingerprint TEXT NOT NULL,
            trial_id TEXT NOT NULL,
            metric_set_fingerprint TEXT NOT NULL,
            snapshot_fingerprint TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, attempt_id),
            UNIQUE (owner_id, manifest_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_result_publications",
        """
        CREATE TABLE strategy_lab_v2_result_publications (
            owner_id TEXT NOT NULL,
            publication_fingerprint TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            result_fingerprint TEXT NOT NULL,
            reproduction_fingerprint TEXT NOT NULL,
            engine_build_digest TEXT NOT NULL,
            decision TEXT NOT NULL,
            rejection_reasons_json TEXT NOT NULL,
            PRIMARY KEY (owner_id, publication_fingerprint),
            UNIQUE (owner_id, attempt_id, publication_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_runtime_execution",
        """
        CREATE TABLE strategy_lab_v2_runtime_execution (
            owner_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            profile_fingerprint TEXT NOT NULL,
            output_limit_bytes BIGINT NOT NULL,
            sequence BIGINT NOT NULL,
            phase TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            output_digest TEXT NULL,
            output_bytes BIGINT NULL,
            error_digest TEXT NULL,
            state_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, attempt_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_runtime_updates",
        """
        CREATE TABLE strategy_lab_v2_runtime_updates (
            owner_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            phase TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            output_digest TEXT NULL,
            output_bytes BIGINT NULL,
            error_digest TEXT NULL,
            update_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, attempt_id, sequence),
            UNIQUE (owner_id, attempt_id, update_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_runtime_requests",
        """
        CREATE TABLE strategy_lab_v2_runtime_requests (
            owner_id TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            request_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            package_fingerprint TEXT NOT NULL,
            source_digest TEXT NOT NULL,
            input_bundle_digest TEXT NOT NULL,
            runtime_profile_fingerprint TEXT NOT NULL,
            entrypoint TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            request_json TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, request_fingerprint),
            UNIQUE (owner_id, attempt_id)
        )
        """,
    ),
    (
        "strategy_lab_v2_runtime_preflights",
        """
        CREATE TABLE strategy_lab_v2_runtime_preflights (
            owner_id TEXT NOT NULL,
            preflight_fingerprint TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            profile_fingerprint TEXT NOT NULL,
            isolation_report_fingerprint TEXT NOT NULL,
            decision TEXT NOT NULL,
            rejection_reasons_json TEXT NOT NULL,
            preflight_json TEXT NOT NULL,
            record_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, preflight_fingerprint),
            UNIQUE (owner_id, request_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_search_states",
        """
        CREATE TABLE strategy_lab_v2_search_states (
            owner_id TEXT NOT NULL,
            experiment_fingerprint TEXT NOT NULL,
            cancellation_requested BOOLEAN NOT NULL,
            cancellation_request_id TEXT NULL,
            updated_at TEXT NULL,
            state_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, experiment_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_search_candidates",
        """
        CREATE TABLE strategy_lab_v2_search_candidates (
            owner_id TEXT NOT NULL,
            experiment_fingerprint TEXT NOT NULL,
            candidate_index BIGINT NOT NULL,
            trial_fingerprint TEXT NOT NULL,
            phase TEXT NOT NULL,
            attempt_id TEXT NULL,
            attempt_count BIGINT NOT NULL,
            result_fingerprint TEXT NULL,
            updated_at TEXT NULL,
            state_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, experiment_fingerprint, candidate_index)
        )
        """,
    ),
    (
        "strategy_lab_v2_snapshot_coverage",
        """
        CREATE TABLE strategy_lab_v2_snapshot_coverage (
            owner_id TEXT NOT NULL,
            snapshot_fingerprint TEXT NOT NULL,
            decision TEXT NOT NULL,
            reports_json TEXT NOT NULL,
            missing_series_digests_json TEXT NOT NULL,
            unexpected_series_digests_json TEXT NOT NULL,
            rejection_reason TEXT NULL,
            resolution_fingerprint TEXT NOT NULL,
            PRIMARY KEY (owner_id, snapshot_fingerprint)
        )
        """,
    ),
    (
        "strategy_lab_v2_submissions",
        """
        CREATE TABLE strategy_lab_v2_submissions (
            owner_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            operation TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            PRIMARY KEY (owner_id, idempotency_key)
        )
        """,
    ),
    (
        "strategy_lab_v2_submission_dispatches",
        """
        CREATE TABLE strategy_lab_v2_submission_dispatches (
            owner_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            queue_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (owner_id, idempotency_key)
        )
        """,
    ),
    (
        "strategy_lab_v2_worker_profiles",
        """
        CREATE TABLE strategy_lab_v2_worker_profiles (
            worker_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            runtime_profile_fingerprint TEXT NOT NULL,
            isolation_required BOOLEAN NOT NULL,
            engine_disposal_required BOOLEAN NOT NULL,
            max_concurrent_nodes BIGINT NOT NULL,
            profile_fingerprint TEXT NOT NULL
        )
        """,
    ),
    (
        "strategy_lab_v2_worker_reservations",
        """
        CREATE TABLE strategy_lab_v2_worker_reservations (
            reservation_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            released_at TEXT NULL,
            reservation_fingerprint TEXT NOT NULL,
            UNIQUE (worker_id, attempt_id, released_at)
        )
        """,
    ),
    (
        "strategy_lab_v2_execution_leases",
        """
        CREATE TABLE strategy_lab_v2_execution_leases (
            lease_id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            leased_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            released_at TEXT NULL,
            lease_fingerprint TEXT NOT NULL
        )
        """,
    ),
    (
        "strategy_lab_v2_lease_observations",
        """
        CREATE TABLE strategy_lab_v2_lease_observations (
            observation_id TEXT PRIMARY KEY,
            lease_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            sequence BIGINT NOT NULL,
            kind TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            expires_at TEXT NULL,
            observation_fingerprint TEXT NOT NULL,
            UNIQUE (lease_id, sequence)
        )
        """,
    ),
)


def upgrade() -> None:
    for _, statement in _DDL:
        op.execute(sa.text(statement))
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX strategy_lab_v2_worker_reservations_active_attempt_key
            ON strategy_lab_v2_worker_reservations (worker_id, attempt_id)
            WHERE released_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP INDEX IF EXISTS strategy_lab_v2_worker_reservations_active_attempt_key")
    )
    for table_name, _ in reversed(_DDL):
        op.execute(sa.text(f"DROP TABLE {table_name} CASCADE"))
