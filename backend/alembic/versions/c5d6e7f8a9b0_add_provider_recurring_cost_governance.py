"""Add shared provider recurring-subscription cost governance."""

import sqlalchemy as sa

from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_recurring_cost_budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("monthly_ceiling", sa.Numeric(14, 4), nullable=False),
        sa.Column("evidence_source", sa.String(length=500), nullable=False),
        sa.Column("evidence_version", sa.String(length=120), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_provider_recurring_cost_budget_singleton"),
        sa.CheckConstraint(
            "monthly_ceiling > 0", name="ck_provider_recurring_cost_budget_positive"
        ),
    )
    op.create_table(
        "provider_recurring_cost_budget_revision",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "budget_id",
            sa.Integer(),
            sa.ForeignKey("provider_recurring_cost_budget.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("monthly_ceiling", sa.Numeric(14, 4), nullable=False),
        sa.Column("evidence_source", sa.String(length=500), nullable=False),
        sa.Column("evidence_version", sa.String(length=120), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "budget_id", "revision", name="uq_provider_recurring_cost_budget_revision"
        ),
    )
    op.create_index(
        "ix_provider_recurring_cost_budget_revision_budget_id",
        "provider_recurring_cost_budget_revision",
        ["budget_id"],
    )
    op.create_table(
        "provider_recurring_cost_commitment",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_source_id",
            sa.Integer(),
            sa.ForeignKey("data_source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(length=40), nullable=False),
        sa.Column("billing_account_scope_digest", sa.String(length=64), nullable=False),
        sa.Column("configured_plan", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("interval_unit", sa.String(length=12), nullable=False),
        sa.Column("interval_count", sa.Integer(), nullable=False),
        sa.Column("monthly_equivalent", sa.Numeric(14, 4), nullable=False),
        sa.Column("post_trial_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("post_trial_currency", sa.String(length=3), nullable=True),
        sa.Column("post_trial_interval_unit", sa.String(length=12), nullable=True),
        sa.Column("post_trial_interval_count", sa.Integer(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_source", sa.String(length=500), nullable=False),
        sa.Column("evidence_version", sa.String(length=120), nullable=False),
        sa.Column("evidence_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "data_source_id",
            "environment",
            "billing_account_scope_digest",
            name="uq_provider_recurring_cost_account_environment",
        ),
        sa.CheckConstraint(
            "state IN ('proposed','active','trial','expired','cancelled')",
            name="ck_provider_recurring_cost_state",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_provider_recurring_cost_amount_nonnegative"),
        sa.CheckConstraint(
            "monthly_equivalent >= 0",
            name="ck_provider_recurring_cost_monthly_nonnegative",
        ),
        sa.CheckConstraint(
            "interval_count > 0", name="ck_provider_recurring_cost_interval_positive"
        ),
        sa.CheckConstraint(
            "interval_unit IN ('month','year')",
            name="ck_provider_recurring_cost_interval_unit",
        ),
    )
    op.create_index(
        "ix_provider_recurring_cost_commitment_data_source_id",
        "provider_recurring_cost_commitment",
        ["data_source_id"],
    )
    op.create_table(
        "provider_recurring_cost_commitment_revision",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "commitment_id",
            sa.Integer(),
            sa.ForeignKey("provider_recurring_cost_commitment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_source", sa.String(length=500), nullable=False),
        sa.Column("evidence_version", sa.String(length=120), nullable=False),
        sa.Column("evidence_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "commitment_id", "revision", name="uq_provider_recurring_cost_revision_number"
        ),
    )
    op.create_index(
        "ix_provider_recurring_cost_commitment_revision_commitment_id",
        "provider_recurring_cost_commitment_revision",
        ["commitment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_recurring_cost_commitment_revision_commitment_id",
        table_name="provider_recurring_cost_commitment_revision",
    )
    op.drop_table("provider_recurring_cost_commitment_revision")
    op.drop_index(
        "ix_provider_recurring_cost_commitment_data_source_id",
        table_name="provider_recurring_cost_commitment",
    )
    op.drop_table("provider_recurring_cost_commitment")
    op.drop_index(
        "ix_provider_recurring_cost_budget_revision_budget_id",
        table_name="provider_recurring_cost_budget_revision",
    )
    op.drop_table("provider_recurring_cost_budget_revision")
    op.drop_table("provider_recurring_cost_budget")
