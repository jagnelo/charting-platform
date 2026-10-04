"""Fail-closed native Nautilus P&L attribution for one frozen OOS window."""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    METRIC_CALCULATION_CONTRACT_VERSION,
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
    PortfolioComposition,
)
from app.strategy_lab_v2.metrics import calculate_component_attribution_metrics
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceReference
from app.strategy_lab_v2.nautilus_native_reports import (
    NautilusNativeReportsReference,
    iter_nautilus_native_report_records,
)
from app.strategy_lab_v2.nautilus_result_metrics import (
    METRIC_DEFINITION_VERSION,
    _reported_money,
    _row_timestamp_ns,
)
from app.strategy_lab_v2.observations import (
    UNALLOCATED_COMPONENT_ID,
    ComponentPnlObservation,
    ObservationPoint,
    PortfolioPnlObservation,
)

_COMPONENT_ORDER_TAG_PREFIX = "strategy-lab-v2:component:"
_ATTRIBUTION_METHOD_DIGEST = content_digest(
    {
        "method": "nautilus-native-position-cycle-pnl-plus-fill-commission-v1",
        "scope": "closed-position-cycles-opened-and-closed-inside-oos-window",
        "position_currency": "attribute-only-when-native-realized-pnl-is-in-account-base-currency",
        "mixed_component_position": "unallocated",
        "non_position_and_open_pnl": "unallocated-account-equity-residual",
        "costs": "complete-native-fill-commissions-in-account-base-currency-only",
    }
)


class _AttributionUnavailable(Exception):
    """The reports are valid, but do not support exact gross/net attribution."""


def build_nautilus_component_pnl_metrics(
    equity_reference: NautilusAccountEquityTraceReference,
    native_reports_reference: NautilusNativeReportsReference,
    native_reports_path: str | Path,
    portfolio: PortfolioComposition,
    *,
    account_net_pnl: Decimal,
) -> tuple[MetricValue, ...]:
    """Attribute fully in-window native position cycles, reconciling all residue.

    The account result is the difference between the first and last verified
    event-aligned equity marks. Only closed position cycles wholly contained in
    the OOS interval, with one verifiably tagged component and base-currency
    native P&L, are assigned to that component. Open, crossing-window, mixed,
    foreign-currency, and otherwise ambiguous P&L remains explicitly unallocated.
    """

    if not isinstance(equity_reference, NautilusAccountEquityTraceReference):
        raise TypeError("equity_reference must be a NautilusAccountEquityTraceReference")
    if not isinstance(native_reports_reference, NautilusNativeReportsReference):
        raise TypeError("native_reports_reference must be a NautilusNativeReportsReference")
    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if not isinstance(account_net_pnl, Decimal) or not account_net_pnl.is_finite():
        raise ValueError("account_net_pnl must be a finite Decimal")
    if (
        equity_reference.portfolio_fingerprint != portfolio.fingerprint
        or native_reports_reference.portfolio_fingerprint != portfolio.fingerprint
    ):
        raise ValueError("component P&L portfolio differs from the verified result scope")
    start_ns = equity_reference.scoring_start_ns
    end_ns = equity_reference.scoring_end_ns
    if start_ns is None or end_ns is None:
        raise ValueError("component P&L requires an explicit OOS window")

    result_bundle_digest = content_digest(
        {
            "equity_trace_digest": equity_reference.artifact.content_digest,
            "native_reports_digest": native_reports_reference.artifact.content_digest,
            "portfolio_fingerprint": portfolio.fingerprint,
        }
    )
    evidence_digest = result_bundle_digest
    point = _result_point(end_ns)
    try:
        with tempfile.TemporaryDirectory(prefix="strategy-lab-component-pnl-") as temporary:
            database = Path(temporary) / "joins.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute("PRAGMA journal_mode=OFF")
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute(
                    "CREATE TABLE orders (client_order_id TEXT PRIMARY KEY, component_id TEXT)"
                )
                connection.execute(
                    """CREATE TABLE fills (
                        position_id TEXT,
                        client_order_id TEXT NOT NULL,
                        trade_id TEXT,
                        event_time_ns INTEGER NOT NULL,
                        commission_currency TEXT,
                        commission_amount TEXT
                    )"""
                )
                connection.execute("CREATE TABLE claimed_positions (position_id TEXT PRIMARY KEY)")
                connection.execute("CREATE TABLE claimed_trades (trade_id TEXT PRIMARY KEY)")
                _index_native_orders(
                    native_reports_reference,
                    native_reports_path,
                    portfolio,
                    connection,
                )
                total_costs, total_rebates = _index_native_fills_and_costs(
                    native_reports_reference,
                    native_reports_path,
                    start_ns,
                    end_ns,
                    portfolio.base_currency,
                    connection,
                )
                attributed = _attribute_closed_positions(
                    native_reports_reference,
                    native_reports_path,
                    start_ns,
                    end_ns,
                    portfolio,
                    connection,
                )
    except _AttributionUnavailable as error:
        return _null_attribution_metrics(
            portfolio,
            reason=str(error),
            result_bundle_digest=result_bundle_digest,
            reports_digest=native_reports_reference.artifact.content_digest,
        )

    portfolio_gross = account_net_pnl + total_costs - total_rebates
    portfolio_observation = PortfolioPnlObservation(
        portfolio_fingerprint=portfolio.fingerprint,
        run_attempt_id=equity_reference.attempt_id,
        point=point,
        gross_pnl=portfolio_gross,
        net_pnl=account_net_pnl,
        base_currency=portfolio.base_currency,
        component_ids=tuple(component.component_id for component in portfolio.components),
        result_bundle_digest=result_bundle_digest,
        engine_evidence_digest=evidence_digest,
    )

    components: list[ComponentPnlObservation] = []
    for component in portfolio.components:
        net_pnl, costs, rebates = attributed.get(
            component.component_id,
            (Decimal(0), Decimal(0), Decimal(0)),
        )
        components.append(
            ComponentPnlObservation(
                portfolio_fingerprint=portfolio.fingerprint,
                run_attempt_id=equity_reference.attempt_id,
                point=point,
                component_id=component.component_id,
                gross_pnl=net_pnl + costs - rebates,
                cost_deductions=costs,
                rebates=rebates,
                net_pnl=net_pnl,
                base_currency=portfolio.base_currency,
                result_bundle_digest=result_bundle_digest,
                attribution_method_digest=_ATTRIBUTION_METHOD_DIGEST,
                engine_evidence_digest=native_reports_reference.artifact.content_digest,
            )
        )

    attributed_gross = sum((item.gross_pnl for item in components), Decimal(0))
    attributed_costs = sum((item.cost_deductions for item in components), Decimal(0))
    attributed_rebates = sum((item.rebates for item in components), Decimal(0))
    unallocated_costs = total_costs - attributed_costs
    unallocated_rebates = total_rebates - attributed_rebates
    unallocated_gross = portfolio_gross - attributed_gross
    components.append(
        ComponentPnlObservation(
            portfolio_fingerprint=portfolio.fingerprint,
            run_attempt_id=equity_reference.attempt_id,
            point=point,
            component_id=UNALLOCATED_COMPONENT_ID,
            gross_pnl=unallocated_gross,
            cost_deductions=unallocated_costs,
            rebates=unallocated_rebates,
            net_pnl=unallocated_gross - unallocated_costs + unallocated_rebates,
            base_currency=portfolio.base_currency,
            result_bundle_digest=result_bundle_digest,
            attribution_method_digest=_ATTRIBUTION_METHOD_DIGEST,
            engine_evidence_digest=native_reports_reference.artifact.content_digest,
        )
    )
    return calculate_component_attribution_metrics(portfolio_observation, components)


def _index_native_orders(
    reference: NautilusNativeReportsReference,
    path: str | Path,
    portfolio: PortfolioComposition,
    connection: sqlite3.Connection,
) -> None:
    declared_ids = {component.component_id for component in portfolio.components}
    for kind, _, row in iter_nautilus_native_report_records(reference, path):
        if kind != "orders":
            continue
        client_order_id = row.get("client_order_id")
        if not isinstance(client_order_id, str) or not client_order_id:
            continue
        component_id = _component_id_from_tags(row.get("tags"), declared_ids)
        try:
            connection.execute(
                "INSERT INTO orders (client_order_id, component_id) VALUES (?, ?)",
                (client_order_id, component_id),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("native order report repeats a client_order_id") from error


def _component_id_from_tags(value: Any, declared_ids: set[str]) -> str | None:
    if isinstance(value, str):
        tags: Sequence[Any] = (value,)
    elif isinstance(value, list | tuple):
        tags = value
    else:
        return None
    component_tags = [
        tag.removeprefix(_COMPONENT_ORDER_TAG_PREFIX)
        for tag in tags
        if isinstance(tag, str) and tag.startswith(_COMPONENT_ORDER_TAG_PREFIX)
    ]
    if len(component_tags) != 1:
        return None
    component_id = component_tags[0]
    if component_id not in declared_ids:
        raise ValueError("native order tag names an undeclared portfolio component")
    return component_id


def _index_native_fills_and_costs(
    reference: NautilusNativeReportsReference,
    path: str | Path,
    start_ns: int,
    end_ns: int,
    base_currency: str,
    connection: sqlite3.Connection,
) -> tuple[Decimal, Decimal]:
    costs = Decimal(0)
    rebates = Decimal(0)
    for kind, _, row in iter_nautilus_native_report_records(reference, path):
        if kind != "fills":
            continue
        timestamp = _row_timestamp_ns(row, "ts_event")
        if timestamp is None:
            raise _AttributionUnavailable(
                "native fill timestamps are incomplete; gross commission scope is unknown"
            )
        money = _reported_money(row, "commission") if start_ns <= timestamp < end_ns else None
        if start_ns <= timestamp < end_ns:
            if money is None:
                raise _AttributionUnavailable(
                    "one or more OOS native fills lack an explicit commission amount and currency"
                )
            currency, amount = money
            if currency != base_currency:
                raise _AttributionUnavailable(
                    "OOS fill commissions are not all in the account base currency; no FX conversion is inferred"
                )
            if amount >= 0:
                costs += amount
            else:
                rebates += amount.copy_abs()

        position_id = row.get("position_id")
        client_order_id = row.get("client_order_id")
        trade_id = row.get("trade_id")
        if isinstance(client_order_id, str) and client_order_id:
            connection.execute(
                """INSERT INTO fills
                   (position_id, client_order_id, trade_id, event_time_ns,
                    commission_currency, commission_amount)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    position_id if isinstance(position_id, str) and position_id else None,
                    client_order_id,
                    trade_id if isinstance(trade_id, str) and trade_id else None,
                    timestamp,
                    None if money is None else money[0],
                    None if money is None else format(money[1], "f"),
                ),
            )
    connection.commit()
    connection.execute(
        "CREATE INDEX fills_by_position_order ON fills (position_id, client_order_id)"
    )
    connection.execute("CREATE INDEX fills_by_trade_id ON fills (trade_id)")
    return costs, rebates


def _attribute_closed_positions(
    reference: NautilusNativeReportsReference,
    path: str | Path,
    start_ns: int,
    end_ns: int,
    portfolio: PortfolioComposition,
    connection: sqlite3.Connection,
) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    attributed: dict[str, tuple[Decimal, Decimal, Decimal]] = {
        component.component_id: (Decimal(0), Decimal(0), Decimal(0))
        for component in portfolio.components
    }
    for kind, _, row in iter_nautilus_native_report_records(reference, path):
        if kind != "positions":
            continue
        opened = _row_timestamp_ns(row, "ts_opened")
        closed = _row_timestamp_ns(row, "ts_closed")
        if (
            opened is None
            or closed is None
            or not start_ns <= opened < end_ns
            or not start_ns <= closed < end_ns
        ):
            continue
        position_id = row.get("position_id")
        position_order_ids = _position_order_ids(row)
        if not isinstance(position_id, str) or not position_id:
            continue
        if position_order_ids is None:
            continue
        order_ids = position_order_ids
        if len(order_ids) != len(set(order_ids)):
            continue

        cycle_fills, trade_ids = _position_cycle_fills(
            row,
            position_id,
            order_ids,
            connection,
        )
        if cycle_fills is None:
            continue
        if not cycle_fills or any(
            not start_ns <= fill[0] < end_ns
            or fill[1] != portfolio.base_currency
            or fill[2] is None
            for fill in cycle_fills
        ):
            continue
        component_ids: set[str] = set()
        for client_order_id in order_ids:
            match = connection.execute(
                "SELECT component_id FROM orders WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
            if match is None or not isinstance(match[0], str):
                component_ids.clear()
                break
            component_ids.add(match[0])
        if len(component_ids) != 1:
            continue

        realized = _reported_money(row, "realized_pnl")
        if realized is None or realized[0] != portfolio.base_currency:
            continue
        try:
            connection.execute(
                "INSERT INTO claimed_positions (position_id) VALUES (?)",
                (position_id,),
            )
            connection.executemany(
                "INSERT INTO claimed_trades (trade_id) VALUES (?)",
                ((trade_id,) for trade_id in trade_ids),
            )
        except sqlite3.IntegrityError as error:
            raise _AttributionUnavailable(
                "native position rows overlap on position or fill identity"
            ) from error
        position_costs = sum(
            (max(Decimal(fill[2]), Decimal(0)) for fill in cycle_fills),
            Decimal(0),
        )
        position_rebates = sum(
            (max(-Decimal(fill[2]), Decimal(0)) for fill in cycle_fills),
            Decimal(0),
        )
        component_id = next(iter(component_ids))
        previous = attributed[component_id]
        attributed[component_id] = (
            previous[0] + realized[1],
            previous[1] + position_costs,
            previous[2] + position_rebates,
        )
    return attributed


def _position_cycle_fills(
    row: Mapping[str, Any],
    position_id: str,
    order_ids: tuple[str, ...],
    connection: sqlite3.Connection,
) -> tuple[list[tuple[Any, ...]] | None, tuple[str, ...]]:
    event_identities = _position_event_identities(row)
    if "events" in row and event_identities is None:
        return None, ()
    raw_trade_ids = row.get("trade_ids")
    if raw_trade_ids is not None or event_identities is not None:
        if not isinstance(raw_trade_ids, list | tuple):
            if raw_trade_ids is not None or event_identities is None:
                return None, ()
            trade_ids = event_identities[1]
        else:
            trade_ids = tuple(raw_trade_ids)
        if (
            not trade_ids
            or any(not isinstance(item, str) or not item for item in trade_ids)
            or len(trade_ids) != len(set(trade_ids))
        ):
            return None, ()
        if event_identities is not None and set(event_identities[1]) != set(trade_ids):
            return None, ()
        fills: list[tuple[Any, ...]] = []
        for trade_id in trade_ids:
            matches = list(
                connection.execute(
                    """SELECT event_time_ns, commission_currency, commission_amount,
                              client_order_id
                       FROM fills WHERE trade_id = ?""",
                    (trade_id,),
                )
            )
            if len(matches) != 1:
                return None, ()
            fills.append(matches[0])
        if {fill[3] for fill in fills} != set(order_ids):
            return None, ()
        return [(fill[0], fill[1], fill[2]) for fill in fills], trade_ids

    # Older report schemas may omit trade IDs. In that case require the
    # position identifier and the full order set to match exactly.
    observed_order_ids = {
        value[0]
        for value in connection.execute(
            "SELECT DISTINCT client_order_id FROM fills WHERE position_id = ?",
            (position_id,),
        )
    }
    if observed_order_ids != set(order_ids):
        return None, ()
    fills = [
        fill
        for client_order_id in order_ids
        for fill in connection.execute(
            """SELECT event_time_ns, commission_currency, commission_amount
               FROM fills WHERE position_id = ? AND client_order_id = ?""",
            (position_id, client_order_id),
        )
    ]
    return fills, ()


def _position_order_ids(row: Mapping[str, Any]) -> tuple[str, ...] | None:
    raw_order_ids = row.get("client_order_ids")
    order_ids: tuple[str, ...]
    if isinstance(raw_order_ids, str):
        order_ids = (raw_order_ids,)
    elif isinstance(raw_order_ids, list | tuple):
        order_ids = tuple(raw_order_ids)
    elif raw_order_ids is None:
        order_ids = ()
    else:
        return None
    if any(not isinstance(item, str) or not item for item in order_ids):
        return None

    event_identities = _position_event_identities(row)
    if "events" in row and event_identities is None:
        return None
    if event_identities is not None:
        event_order_ids = event_identities[0]
        if order_ids and set(order_ids) != set(event_order_ids):
            return None
        order_ids = event_order_ids
    return order_ids or None


def _position_event_identities(
    row: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    if "events" not in row:
        return None
    events = row["events"]
    if not isinstance(events, list | tuple) or not events:
        return None
    order_ids: list[str] = []
    trade_ids: list[str] = []
    for event in events:
        if not isinstance(event, Mapping) or event.get("type") != "OrderFilled":
            return None
        client_order_id = event.get("client_order_id")
        trade_id = event.get("trade_id")
        if (
            not isinstance(client_order_id, str)
            or not client_order_id
            or not isinstance(trade_id, str)
            or not trade_id
        ):
            return None
        order_ids.append(client_order_id)
        trade_ids.append(trade_id)
    if len(trade_ids) != len(set(trade_ids)):
        return None
    return tuple(dict.fromkeys(order_ids)), tuple(trade_ids)


def _result_point(end_ns: int) -> ObservationPoint:
    seconds, nanoseconds = divmod(end_ns, 1_000_000_000)
    event_time = datetime.fromtimestamp(seconds, UTC).replace(microsecond=nanoseconds // 1_000)
    return ObservationPoint(event_time=event_time, event_sequence=0)


def _null_attribution_metrics(
    portfolio: PortfolioComposition,
    *,
    reason: str,
    result_bundle_digest: str,
    reports_digest: str,
) -> tuple[MetricValue, ...]:
    evidence = (
        MetricEvidenceReference("result_bundle", result_bundle_digest),
        MetricEvidenceReference("native_execution_reports", reports_digest),
    )
    parameters = {
        "attribution_method_digest": _ATTRIBUTION_METHOD_DIGEST,
        "unavailable_reason": reason,
    }
    component_ids = tuple(
        sorted((*[item.component_id for item in portfolio.components], UNALLOCATED_COMPONENT_ID))
    )
    values = [
        (
            "portfolio_attributed_gross_pnl",
            f"currency:{portfolio.base_currency}",
            MetricBasis.GROSS,
        ),
        ("portfolio_attributed_net_pnl", f"currency:{portfolio.base_currency}", MetricBasis.NET),
    ]
    for component_id in component_ids:
        values.extend(
            (
                (
                    f"component_gross_pnl:{component_id}",
                    f"currency:{portfolio.base_currency}",
                    MetricBasis.GROSS,
                ),
                (
                    f"component_net_pnl:{component_id}",
                    f"currency:{portfolio.base_currency}",
                    MetricBasis.NET,
                ),
                (f"component_net_pnl_contribution:{component_id}", "fraction", MetricBasis.NET),
            )
        )
    return tuple(
        MetricValue(
            name=name,
            value=None,
            unit=unit,
            definition_version=METRIC_DEFINITION_VERSION,
            basis=basis,
            sample_size=0,
            calculation_basis="Nautilus component P&L attribution v1 could not be verified",
            null_reason=reason,
            calculation_definition=MetricCalculationDefinition(
                formula_id=f"strategy-lab.metrics/{name.partition(':')[0]}",
                contract_version=METRIC_CALCULATION_CONTRACT_VERSION,
                parameters=parameters,
            ),
            evidence_references=evidence,
        )
        for name, unit, basis in values
    )


__all__ = ["build_nautilus_component_pnl_metrics"]
