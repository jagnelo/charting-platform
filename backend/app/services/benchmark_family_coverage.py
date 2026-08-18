"""Pure diagnostics for observed benchmark-family holdings coverage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

# Issuer disclosures are not guaranteed to arrive on a documented cadence.  This
# threshold is therefore only an observed-continuity diagnostic, never proof of
# official rebalance completeness.
OBSERVED_CONTINUITY_MAX_INTERVAL_DAYS = 45


@dataclass(frozen=True)
class HoldingsContinuityGap:
    """One interval between distinct observed composition dates."""

    from_date: date
    to_date: date
    interval_days: int


@dataclass(frozen=True)
class HoldingsContinuityAssessment:
    """Conservative continuity state for the dates returned by a coverage query."""

    status: str
    gaps: tuple[HoldingsContinuityGap, ...] = ()

    @property
    def max_interval_days(self) -> int | None:
        return max((gap.interval_days for gap in self.gaps), default=None)


def assess_observed_holdings_continuity(
    composition_dates: Iterable[date],
    *,
    max_interval_days: int = OBSERVED_CONTINUITY_MAX_INTERVAL_DAYS,
) -> HoldingsContinuityAssessment:
    """Assess only the distinct composition dates present in the response.

    Same-date revisions are deliberately collapsed before intervals are built.
    The result describes observed disclosure spacing; it does not infer missing
    official holdings files or guarantee that the requested ``limit`` contains
    the complete historical record.
    """

    if max_interval_days < 1:
        raise ValueError("max_interval_days must be positive")

    dates = sorted(set(composition_dates))
    if not dates:
        return HoldingsContinuityAssessment(status="no_snapshot")
    if len(dates) == 1:
        return HoldingsContinuityAssessment(status="single_snapshot")

    gaps = tuple(
        HoldingsContinuityGap(
            from_date=previous,
            to_date=current,
            interval_days=(current - previous).days,
        )
        for previous, current in zip(dates, dates[1:])
        if (current - previous).days > max_interval_days
    )
    return HoldingsContinuityAssessment(
        status="gapped" if gaps else "observed_continuity",
        gaps=gaps,
    )
