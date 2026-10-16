"""Shared, durable provider subscription cost commitments.

These records govern recurring subscription commitments only. They do not
authorize provider activation or route paid requests.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ProviderRecurringCostBudget(Base, TimestampMixin):
    """Explicitly reviewed ceiling and denomination; no implicit defaults."""

    __tablename__ = "provider_recurring_cost_budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    monthly_ceiling: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revisions = relationship(
        "ProviderRecurringCostBudgetRevision",
        back_populates="budget",
        passive_deletes="all",
        order_by="ProviderRecurringCostBudgetRevision.revision",
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_provider_recurring_cost_budget_singleton"),
        CheckConstraint("monthly_ceiling > 0", name="ck_provider_recurring_cost_budget_positive"),
    )


class ProviderRecurringCostBudgetRevision(Base, TimestampMixin):
    """Append-only record of every reviewed ceiling/currency change."""

    __tablename__ = "provider_recurring_cost_budget_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("provider_recurring_cost_budget.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    monthly_ceiling: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    budget = relationship("ProviderRecurringCostBudget", back_populates="revisions")

    __table_args__ = (
        UniqueConstraint(
            "budget_id", "revision", name="uq_provider_recurring_cost_budget_revision"
        ),
    )


class ProviderRecurringCostCommitment(Base, TimestampMixin):
    """One recurring plan per provider billing account and environment.

    ``billing_account_scope_digest`` is a stable one-way digest of an opaque,
    non-secret account scope. API keys/capabilities are deliberately not the
    identity, so a shared account plan is counted only once.
    """

    __tablename__ = "provider_recurring_cost_commitment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(40), nullable=False)
    billing_account_scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    configured_plan: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    interval_unit: Mapped[str] = mapped_column(String(12), nullable=False)
    interval_count: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_equivalent: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    post_trial_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    post_trial_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    post_trial_interval_unit: Mapped[str | None] = mapped_column(String(12), nullable=True)
    post_trial_interval_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_source: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    data_source = relationship("DataSource")
    revisions = relationship(
        "ProviderRecurringCostCommitmentRevision",
        back_populates="commitment",
        passive_deletes="all",
        order_by="ProviderRecurringCostCommitmentRevision.revision",
    )

    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "environment",
            "billing_account_scope_digest",
            name="uq_provider_recurring_cost_account_environment",
        ),
        CheckConstraint(
            "state IN ('proposed','active','trial','expired','cancelled')",
            name="ck_provider_recurring_cost_state",
        ),
        CheckConstraint("amount >= 0", name="ck_provider_recurring_cost_amount_nonnegative"),
        CheckConstraint(
            "monthly_equivalent >= 0", name="ck_provider_recurring_cost_monthly_nonnegative"
        ),
        CheckConstraint("interval_count > 0", name="ck_provider_recurring_cost_interval_positive"),
        CheckConstraint(
            "interval_unit IN ('month','year')",
            name="ck_provider_recurring_cost_interval_unit",
        ),
    )


class ProviderRecurringCostCommitmentRevision(Base, TimestampMixin):
    """Append-only evidence snapshot for changes to a cost commitment."""

    __tablename__ = "provider_recurring_cost_commitment_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commitment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("provider_recurring_cost_commitment.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    commitment = relationship("ProviderRecurringCostCommitment", back_populates="revisions")

    __table_args__ = (
        UniqueConstraint(
            "commitment_id", "revision", name="uq_provider_recurring_cost_revision_number"
        ),
    )
