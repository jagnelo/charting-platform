"""Pure diagnostics for observed benchmark-family holdings coverage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from statistics import median

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


@dataclass(frozen=True)
class HoldingsCadenceAssessment:
    """Observed spacing statistics for the returned composition dates.

    These values describe only the snapshot dates available to the caller. They
    are intentionally not a claim about the issuer's official rebalance
    schedule or about disclosures missing outside the requested window.
    """

    status: str
    sample_count: int = 0
    median_interval_days: float | None = None
    min_interval_days: int | None = None
    max_interval_days: int | None = None


def assess_observed_holdings_cadence(
    composition_dates: Iterable[date],
) -> HoldingsCadenceAssessment:
    """Summarise intervals between distinct observed composition dates."""

    dates = sorted(set(composition_dates))
    if not dates:
        return HoldingsCadenceAssessment(status="no_snapshot")
    if len(dates) == 1:
        return HoldingsCadenceAssessment(status="single_snapshot")

    intervals = tuple(
        (current - previous).days
        for previous, current in zip(dates, dates[1:])
        if (current - previous).days > 0
    )
    if not intervals:
        return HoldingsCadenceAssessment(status="no_interval")
    return HoldingsCadenceAssessment(
        status="observed_cadence",
        sample_count=len(intervals),
        median_interval_days=float(median(intervals)),
        min_interval_days=min(intervals),
        max_interval_days=max(intervals),
    )


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
