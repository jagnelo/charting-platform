"""Durable shared admission for recurring provider subscription commitments.

This service is intentionally independent of provider-route entitlement. A
successful cost admission records a budgeted commitment; it never enables a
provider, changes paid-route configuration, or authorizes transport.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.provider_recurring_cost import (
    ProviderRecurringCostBudget,
    ProviderRecurringCostBudgetRevision,
    ProviderRecurringCostCommitment,
    ProviderRecurringCostCommitmentRevision,
)

_ACTIVE_STATES = ("proposed", "active", "trial")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_MONEY_QUANTUM = Decimal("0.0001")
_MAX_STORED_MONEY = Decimal("9999999999.9999")
_POSTGRES_ADMISSION_LOCK_KEY = 5785248893121753940


@dataclass(frozen=True)
class RecurringCostDecision:
    allowed: bool
    reason_code: str
    currency: str | None
    monthly_ceiling: Decimal | None
    committed_monthly: Decimal | None
    proposed_monthly: Decimal | None
    remaining_monthly: Decimal | None
    commitment_id: int | None = None
    revision: int | None = None
    paid_activation_authorized: Literal[False] = False


def _lock_cost_governance(session: Session) -> None:
    """Serialize rare admin cost mutations, including first-row creation.

    PostgreSQL row locks do not protect a singleton budget before it exists,
    and all commitment admissions must share the same lock to prevent two
    transactions from independently observing pre-admission totals.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _POSTGRES_ADMISSION_LOCK_KEY},
        )


def _money(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0 or amount > _MAX_STORED_MONEY:
        return None
    return amount


def _currency(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized if _CURRENCY_RE.fullmatch(normalized) else None


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _effective_end(end: datetime | None) -> datetime | None:
    if end is None:
        return None
    return end.replace(tzinfo=UTC) if end.tzinfo is None else end.astimezone(UTC)


def _currently_costed(commitment: ProviderRecurringCostCommitment, now: datetime) -> bool:
    return commitment.state in _ACTIVE_STATES and (
        commitment.ends_at is None or _effective_end(commitment.ends_at) > now
    )


def _monthly_equivalent(
    amount: Decimal | int | float | str | None,
    currency: str | None,
    interval_unit: str | None,
    interval_count: int | None,
) -> tuple[Decimal | None, str | None, str | None]:
    parsed_amount = _money(amount)
    parsed_currency = _currency(currency)
    if parsed_amount is None:
        return None, parsed_currency, "unknown_or_invalid_price"
    if parsed_currency is None:
        return None, None, "unknown_or_invalid_currency"
    if interval_unit not in {"month", "year"}:
        return None, parsed_currency, "unsupported_or_unknown_interval"
    if (
        isinstance(interval_count, bool)
        or not isinstance(interval_count, int)
        or interval_count <= 0
    ):
        return None, parsed_currency, "unknown_or_invalid_interval_count"
    divisor = Decimal(interval_count * (12 if interval_unit == "year" else 1))
    monthly = (parsed_amount / divisor).quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)
    return monthly, parsed_currency, None


def _snapshot(commitment: ProviderRecurringCostCommitment) -> dict:
    return {
        "data_source_id": commitment.data_source_id,
        "environment": commitment.environment,
        "billing_account_scope_digest": commitment.billing_account_scope_digest,
        "configured_plan": commitment.configured_plan,
        "state": commitment.state,
        "amount": str(commitment.amount),
        "currency": commitment.currency,
        "interval_unit": commitment.interval_unit,
        "interval_count": commitment.interval_count,
        "monthly_equivalent": str(commitment.monthly_equivalent),
        "post_trial_amount": (
            str(commitment.post_trial_amount) if commitment.post_trial_amount is not None else None
        ),
        "post_trial_currency": commitment.post_trial_currency,
        "post_trial_interval_unit": commitment.post_trial_interval_unit,
        "post_trial_interval_count": commitment.post_trial_interval_count,
        "effective_at": commitment.effective_at.isoformat(),
        "ends_at": commitment.ends_at.isoformat() if commitment.ends_at else None,
        "revision": commitment.revision,
    }


def configure_provider_recurring_cost_budget(
    session: Session,
    *,
    monthly_ceiling: Decimal | int | float | str,
    currency: str,
    evidence_source: str,
    evidence_version: str,
    reviewed_at: datetime,
    now: datetime | None = None,
) -> RecurringCostDecision:
    """Set the explicitly reviewed single-currency ceiling.

    Mixed-currency conversion is deliberately unsupported. A budget change that
    would put already admitted commitments over its ceiling is rejected.
    """
    ceiling = _money(monthly_ceiling)
    denomination = _currency(currency)
    if (
        ceiling is None
        or ceiling <= 0
        or denomination is None
        or not _nonempty(evidence_source)
        or not _nonempty(evidence_version)
        or not isinstance(reviewed_at, datetime)
        or reviewed_at.tzinfo is None
    ):
        return RecurringCostDecision(
            False, "budget_configuration_unreviewed", None, None, None, None, None
        )

    # The same lock is acquired by admissions so config changes cannot race
    # commitment totals, and first-time singleton creation is serialized.
    _lock_cost_governance(session)

    budget = session.scalar(
        select(ProviderRecurringCostBudget)
        .where(ProviderRecurringCostBudget.id == 1)
        .with_for_update()
    )
    commitments = list(
        session.scalars(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.state.in_(_ACTIVE_STATES)
            )
        )
    )
    current = (now or datetime.now(UTC)).astimezone(UTC)
    total = Decimal("0")
    for item in commitments:
        if not _currently_costed(item, current):
            continue
        if item.currency != denomination:
            return RecurringCostDecision(
                False,
                "existing_commitment_currency_mismatch",
                denomination,
                ceiling,
                None,
                None,
                None,
            )
        total += Decimal(item.monthly_equivalent)
    total = total.quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)
    if total > ceiling:
        return RecurringCostDecision(
            False,
            "existing_commitments_exceed_proposed_ceiling",
            denomination,
            ceiling,
            total,
            None,
            ceiling - total,
        )
    if budget is None:
        budget = ProviderRecurringCostBudget(
            id=1,
            currency=denomination,
            monthly_ceiling=ceiling,
            evidence_source=evidence_source.strip(),
            evidence_version=evidence_version.strip(),
            reviewed_at=reviewed_at,
            revision=1,
        )
        session.add(budget)
        session.flush()
    else:
        budget.currency = denomination
        budget.monthly_ceiling = ceiling
        budget.evidence_source = evidence_source.strip()
        budget.evidence_version = evidence_version.strip()
        budget.reviewed_at = reviewed_at
        budget.revision += 1
    session.flush()
    session.add(
        ProviderRecurringCostBudgetRevision(
            budget_id=budget.id,
            revision=budget.revision,
            currency=budget.currency,
            monthly_ceiling=budget.monthly_ceiling,
            evidence_source=budget.evidence_source,
            evidence_version=budget.evidence_version,
            reviewed_at=budget.reviewed_at,
        )
    )
    session.flush()
    return RecurringCostDecision(
        True, "budget_configured", denomination, ceiling, total, Decimal("0"), ceiling - total
    )


def admit_provider_recurring_cost(
    session: Session,
    *,
    data_source_id: int,
    environment: str,
    billing_account_scope: str,
    configured_plan: str,
    state: str,
    amount: Decimal | int | float | str | None,
    currency: str | None,
    interval_unit: str | None,
    interval_count: int | None,
    evidence_source: str,
    evidence_version: str,
    evidence_observed_at: datetime,
    effective_at: datetime,
    ends_at: datetime | None = None,
    post_trial_amount: Decimal | int | float | str | None = None,
    post_trial_currency: str | None = None,
    post_trial_interval_unit: str | None = None,
    post_trial_interval_count: int | None = None,
    now: datetime | None = None,
) -> RecurringCostDecision:
    """Atomically budget and persist one provider account/environment plan.

    The budget row is locked first, serializing competing admissions in
    PostgreSQL. One account scope is represented once regardless of the number
    of provider API keys or capabilities using it. Denials do not persist a
    commitment. Callers must still obtain separate provider activation
    authorization before enabling any paid service.
    """
    _lock_cost_governance(session)
    budget = session.scalar(
        select(ProviderRecurringCostBudget)
        .where(ProviderRecurringCostBudget.id == 1)
        .with_for_update()
    )
    if budget is None:
        return RecurringCostDecision(False, "budget_not_configured", None, None, None, None, None)
    if (
        not isinstance(data_source_id, int)
        or isinstance(data_source_id, bool)
        or data_source_id <= 0
        or not _nonempty(environment)
        or environment.strip().lower() in {"unknown", "unreviewed"}
        or not _nonempty(billing_account_scope)
        or not _nonempty(configured_plan)
        or configured_plan.strip().lower() in {"unknown", "unreviewed", "unknown-plan"}
        or not isinstance(state, str)
        or state not in {"proposed", "active", "trial", "expired", "cancelled"}
        or not _nonempty(evidence_source)
        or not _nonempty(evidence_version)
        or not isinstance(evidence_observed_at, datetime)
        or evidence_observed_at.tzinfo is None
        or not isinstance(effective_at, datetime)
        or effective_at.tzinfo is None
        or (ends_at is not None and (not isinstance(ends_at, datetime) or ends_at.tzinfo is None))
    ):
        return RecurringCostDecision(
            False,
            "commitment_evidence_incomplete",
            budget.currency,
            budget.monthly_ceiling,
            None,
            None,
            None,
        )
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if state in _ACTIVE_STATES and ends_at is not None and _effective_end(ends_at) <= current:
        return RecurringCostDecision(
            False,
            "commitment_already_ended",
            budget.currency,
            Decimal(budget.monthly_ceiling),
            None,
            None,
            None,
        )

    normalized_environment = environment.strip().lower()
    digest = hashlib.sha256(billing_account_scope.strip().encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(ProviderRecurringCostCommitment).where(
            ProviderRecurringCostCommitment.data_source_id == data_source_id,
            ProviderRecurringCostCommitment.environment == normalized_environment,
            ProviderRecurringCostCommitment.billing_account_scope_digest == digest,
        )
    )

    if state == "trial":
        monthly, commitment_currency, issue = _monthly_equivalent(
            post_trial_amount,
            post_trial_currency,
            post_trial_interval_unit,
            post_trial_interval_count,
        )
        if issue:
            return RecurringCostDecision(
                False,
                "trial_post_price_" + issue,
                budget.currency,
                budget.monthly_ceiling,
                None,
                None,
                None,
            )
        stored_amount = _money(amount)
        stored_currency = _currency(currency)
        stored_interval_unit = interval_unit
        stored_interval_count = interval_count
        if (
            stored_amount is None
            or stored_currency is None
            or interval_unit not in {"month", "year"}
            or stored_currency != commitment_currency
        ):
            return RecurringCostDecision(
                False,
                "trial_current_plan_evidence_incomplete",
                budget.currency,
                budget.monthly_ceiling,
                None,
                None,
                None,
            )
        if (
            not isinstance(interval_count, int)
            or isinstance(interval_count, bool)
            or interval_count <= 0
        ):
            return RecurringCostDecision(
                False,
                "trial_current_plan_evidence_incomplete",
                budget.currency,
                budget.monthly_ceiling,
                None,
                None,
                None,
            )
    elif state in {"active", "proposed"}:
        monthly, commitment_currency, issue = _monthly_equivalent(
            amount, currency, interval_unit, interval_count
        )
        if issue:
            return RecurringCostDecision(
                False, issue, budget.currency, budget.monthly_ceiling, None, None, None
            )
        stored_amount = _money(amount)
        stored_currency = _currency(currency)
        stored_interval_unit = interval_unit
        stored_interval_count = interval_count
    else:
        # Expiration/cancellation is a state transition, not a new price quote.
        monthly = Decimal("0")
        commitment_currency = _currency(currency) or budget.currency
        stored_amount = _money(amount) or Decimal("0")
        stored_currency = _currency(currency) or budget.currency
        stored_interval_unit = interval_unit if interval_unit in {"month", "year"} else "month"
        stored_interval_count = (
            interval_count if isinstance(interval_count, int) and interval_count > 0 else 1
        )

    if commitment_currency != budget.currency:
        return RecurringCostDecision(
            False,
            "currency_conversion_unreviewed",
            budget.currency,
            budget.monthly_ceiling,
            None,
            monthly,
            None,
        )

    active = list(
        session.scalars(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.state.in_(_ACTIVE_STATES)
            )
        )
    )
    active = [item for item in active if _currently_costed(item, current)]
    committed = sum(
        (
            Decimal(item.monthly_equivalent)
            for item in active
            if existing is None or item.id != existing.id
        ),
        start=Decimal("0"),
    ).quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)
    if any(
        item.currency != budget.currency
        for item in active
        if existing is None or item.id != existing.id
    ):
        return RecurringCostDecision(
            False,
            "existing_commitment_currency_mismatch",
            budget.currency,
            budget.monthly_ceiling,
            None,
            monthly,
            None,
        )
    total = (committed + monthly).quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)
    if total > Decimal(budget.monthly_ceiling):
        return RecurringCostDecision(
            False,
            "monthly_ceiling_exceeded",
            budget.currency,
            Decimal(budget.monthly_ceiling),
            committed,
            monthly,
            Decimal(budget.monthly_ceiling) - total,
        )

    if existing is None:
        existing = ProviderRecurringCostCommitment(
            data_source_id=data_source_id,
            environment=normalized_environment,
            billing_account_scope_digest=digest,
            configured_plan=configured_plan.strip(),
            state=state,
            amount=stored_amount,
            currency=stored_currency,
            interval_unit=stored_interval_unit,
            interval_count=stored_interval_count,
            monthly_equivalent=monthly,
            post_trial_amount=_money(post_trial_amount),
            post_trial_currency=_currency(post_trial_currency),
            post_trial_interval_unit=post_trial_interval_unit,
            post_trial_interval_count=post_trial_interval_count,
            effective_at=effective_at,
            ends_at=ends_at,
            evidence_source=evidence_source.strip(),
            evidence_version=evidence_version.strip(),
            evidence_observed_at=evidence_observed_at,
            revision=1,
        )
        session.add(existing)
        session.flush()
    else:
        existing.configured_plan = configured_plan.strip()
        existing.state = state
        existing.amount = stored_amount
        existing.currency = stored_currency
        existing.interval_unit = stored_interval_unit
        existing.interval_count = stored_interval_count
        existing.monthly_equivalent = monthly
        existing.post_trial_amount = _money(post_trial_amount)
        existing.post_trial_currency = _currency(post_trial_currency)
        existing.post_trial_interval_unit = post_trial_interval_unit
        existing.post_trial_interval_count = post_trial_interval_count
        existing.effective_at = effective_at
        existing.ends_at = ends_at
        existing.evidence_source = evidence_source.strip()
        existing.evidence_version = evidence_version.strip()
        existing.evidence_observed_at = evidence_observed_at
        existing.revision += 1
        session.flush()

    session.add(
        ProviderRecurringCostCommitmentRevision(
            commitment_id=existing.id,
            revision=existing.revision,
            snapshot=_snapshot(existing),
            evidence_source=evidence_source.strip(),
            evidence_version=evidence_version.strip(),
            evidence_observed_at=evidence_observed_at,
        )
    )
    session.flush()
    return RecurringCostDecision(
        True,
        "commitment_admitted",
        budget.currency,
        Decimal(budget.monthly_ceiling),
        committed,
        monthly,
        Decimal(budget.monthly_ceiling) - total,
        commitment_id=existing.id,
        revision=existing.revision,
    )


def provider_recurring_cost_status(session: Session) -> RecurringCostDecision:
    """Return current durable aggregate; unknown/mixed scope never looks green."""
    budget = session.get(ProviderRecurringCostBudget, 1)
    if budget is None:
        return RecurringCostDecision(False, "budget_not_configured", None, None, None, None, None)
    current = datetime.now(UTC)
    active = list(
        session.scalars(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.state.in_(_ACTIVE_STATES)
            )
        )
    )
    active = [item for item in active if _currently_costed(item, current)]
    if any(item.currency != budget.currency for item in active):
        return RecurringCostDecision(
            False,
            "existing_commitment_currency_mismatch",
            budget.currency,
            Decimal(budget.monthly_ceiling),
            None,
            None,
            None,
        )
    committed = sum(
        (Decimal(item.monthly_equivalent) for item in active), start=Decimal("0")
    ).quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)
    remaining = Decimal(budget.monthly_ceiling) - committed
    return RecurringCostDecision(
        remaining >= 0,
        "within_monthly_ceiling" if remaining >= 0 else "monthly_ceiling_exceeded",
        budget.currency,
        Decimal(budget.monthly_ceiling),
        committed,
        Decimal("0"),
        remaining,
    )
