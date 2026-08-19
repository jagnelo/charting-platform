from datetime import date, timedelta

import pytest

from app.services.benchmark_family_holdings_runs import (
    MAX_HOLDINGS_REFRESH_DATES,
    completed_month_end_dates,
    plan_benchmark_family_holdings_refresh,
)


def test_completed_month_end_dates_are_strictly_before_current_month_and_bounded():
    assert completed_month_end_dates(as_of=date(2026, 8, 19), count=3) == [
        date(2026, 7, 31),
        date(2026, 6, 30),
        date(2026, 5, 31),
    ]

    with pytest.raises(ValueError, match="At most"):
        completed_month_end_dates(count=MAX_HOLDINGS_REFRESH_DATES + 1)


def test_plan_normalizes_dates_families_and_roles_without_provider_calls():
    plan = plan_benchmark_family_holdings_refresh(
        requested_dates=[date(2026, 6, 30), date(2026, 3, 31), date(2026, 6, 30)],
        family_keys=["nasdaq100", "sp500", "sp500"],
        roles=["VALUE", "value"],
    )

    assert plan["requested_dates"] == [date(2026, 3, 31), date(2026, 6, 30)]
    assert plan["family_keys"] == ["sp500", "nasdaq100"]
    assert plan["roles"] == ["value"]
    assert plan["total_units"] == 4


def test_plan_rejects_unknown_scope():
    with pytest.raises(ValueError, match="Unknown benchmark family key"):
        plan_benchmark_family_holdings_refresh(
            requested_dates=[date(2026, 6, 30)],
            family_keys=["not-a-family"],
        )

    with pytest.raises(ValueError, match="Unsupported benchmark family role"):
        plan_benchmark_family_holdings_refresh(
            requested_dates=[date(2026, 6, 30)],
            roles=["not-a-role"],
        )


def test_plan_rejects_empty_and_over_bound_dates():
    with pytest.raises(ValueError, match="At least one requested"):
        plan_benchmark_family_holdings_refresh(requested_dates=[])

    with pytest.raises(ValueError, match="At most"):
        plan_benchmark_family_holdings_refresh(
            requested_dates=[
                date(2020, 1, 1) + timedelta(days=offset)
                for offset in range(MAX_HOLDINGS_REFRESH_DATES + 1)
            ]
        )
