"""Canonical local-database analysis endpoints for workstation tools."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.user import User
from app.models.workstation import MarketGroup
from app.routers.market_groups import etf_industry_proxies
from app.schemas.analysis import (
    AnalysisCell,
    AnalysisPoint,
    AnalysisWarning,
    BreadthHistoryOut,
    BreadthHistoryPoint,
    BreadthOut,
    ETFConstituentSnapshotOut,
    GroupSnapshotOut,
    GroupSnapshotRow,
    IndustryProxySnapshotOut,
    IndustryProxySnapshotRow,
    MarketGaugeOut,
    RelativeRotationOut,
    RelativeRotationRow,
    RelativeRotationTailPoint,
    RelativeStrengthOut,
    TechnicalSnapshotOut,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])

_PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "YTD": 252, "1Y": 252}


@router.get("/gauges/{screener_id}", response_model=MarketGaugeOut)
async def market_gauge(
    screener_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Expose a Market Gauge from a retained local-only EasyScan result."""
    screener = (
        await db.execute(
            select(ScreenerDefinition).where(
                ScreenerDefinition.id == screener_id,
                ScreenerDefinition.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if screener is None:
        raise HTTPException(404, detail={"code": "screener_not_found"})
    latest = (
        await db.execute(
            select(ScreenerResult)
            .where(ScreenerResult.screener_id == screener.id)
            .order_by(ScreenerResult.run_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return MarketGaugeOut(
            screener_id=screener.id,
            screener_name=screener.name,
            run_at=None,
            matched_count=0,
            evaluated_count=0,
            universe_count=0,
            percentage=None,
            exclusions=[
                AnalysisWarning(
                    code="scan_not_run", message="Run this EasyScan before using it as a gauge."
                )
            ],
        )
    coverage = latest.result_data.get("_coverage", {})
    excluded = coverage.get("excluded", {}) if isinstance(coverage, dict) else {}
    universe_count = int(coverage.get("universe_count", 0)) if isinstance(coverage, dict) else 0
    evaluated_count = int(coverage.get("evaluated_count", 0)) if isinstance(coverage, dict) else 0
    warnings = [
        AnalysisWarning(
            code=value.get("code", "excluded"),
            message=value.get("message", "Excluded"),
            instrument_id=int(key),
        )
        for key, value in excluded.items()
        if isinstance(value, dict) and key.isdigit()
    ]
    return MarketGaugeOut(
        screener_id=screener.id,
        screener_name=screener.name,
        run_at=latest.run_at,
        matched_count=len(latest.matched_ids),
        evaluated_count=evaluated_count,
        universe_count=universe_count,
        percentage=(len(latest.matched_ids) / evaluated_count) if evaluated_count else None,
        exclusions=warnings,
    )


async def _instrument(db: AsyncSession, symbol: str) -> Instrument:
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})
    return instrument


async def _bars_by_instrument(
    db: AsyncSession, instrument_ids: list[int], timeframe: Timeframe, adjusted: bool
) -> dict[int, list[OHLCVBar]]:
    if not instrument_ids:
        return {}
    bars = (
        await db.execute(
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id.in_(instrument_ids),
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_adjusted.is_(adjusted),
            )
            .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
        )
    ).scalars()
    result: dict[int, list[OHLCVBar]] = defaultdict(list)
    for bar in bars:
        result[bar.instrument_id].append(bar)
    return result


def _cell(
    value: float | None, bar: OHLCVBar | None, warning: AnalysisWarning | None = None
) -> AnalysisCell:
    return AnalysisCell(value=value, observation_time=bar.ts if bar else None, warning=warning)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


@router.get("/instruments/{symbol}/technical", response_model=TechnicalSnapshotOut)
async def instrument_technical_snapshot(
    symbol: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return local, reproducible technical values without a provider fetch."""
    instrument = await _instrument(db, symbol)
    bars = (await _bars_by_instrument(db, [instrument.id], timeframe, adjusted)).get(
        instrument.id, []
    )
    latest = bars[-1] if bars else None
    warnings: list[AnalysisWarning] = []

    def required(period: int, label: str) -> bool:
        if len(bars) >= period:
            return True
        warnings.append(
            AnalysisWarning(
                code="insufficient_history",
                message=f"{label} requires {period} bars.",
                instrument_id=instrument.id,
            )
        )
        return False

    if latest is None:
        warnings.append(
            AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
        )
        return TechnicalSnapshotOut(
            symbol=instrument.symbol,
            timeframe=timeframe.value,
            as_of=None,
            adjustment="split_adjusted" if adjusted else "raw",
            last=None,
            rsi14=None,
            sma20=None,
            sma50=None,
            sma200=None,
            position_52w=None,
            volume_ratio_50=None,
            warnings=warnings,
        )

    closes = [float(bar.close) for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    rsi14 = None
    if required(15, "RSI(14)"):
        changes = [
            closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
        ]
        average_gain = _mean([max(change, 0.0) for change in changes])
        average_loss = _mean([max(-change, 0.0) for change in changes])
        rsi14 = 100.0 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))

    averages: dict[int, float | None] = {}
    for period in (20, 50, 200):
        averages[period] = _mean(closes[-period:]) if required(period, f"SMA({period})") else None
    position_52w = None
    if required(252, "52-week position"):
        window = closes[-252:]
        span = max(window) - min(window)
        position_52w = (closes[-1] - min(window)) / span if span else 1.0
    volume_ratio_50 = None
    if required(51, "50-day volume ratio"):
        average_volume = _mean(volumes[-51:-1])
        volume_ratio_50 = volumes[-1] / average_volume if average_volume else None
        if average_volume == 0:
            warnings.append(
                AnalysisWarning(
                    code="zero_average_volume",
                    message="50-day average volume is zero.",
                    instrument_id=instrument.id,
                )
            )
    return TechnicalSnapshotOut(
        symbol=instrument.symbol,
        timeframe=timeframe.value,
        as_of=latest.ts,
        adjustment="split_adjusted" if adjusted else "raw",
        last=closes[-1],
        rsi14=rsi14,
        sma20=averages[20],
        sma50=averages[50],
        sma200=averages[200],
        position_52w=position_52w,
        volume_ratio_50=volume_ratio_50,
        warnings=warnings,
    )


@router.get("/relative-strength", response_model=RelativeStrengthOut)
async def relative_strength(
    symbol: str,
    benchmark: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    primary, comparator = await _instrument(db, symbol), await _instrument(db, benchmark)
    grouped = await _bars_by_instrument(db, [primary.id, comparator.id], timeframe, adjusted)
    primary_by_time = {bar.ts: bar for bar in grouped.get(primary.id, [])}
    comparator_by_time = {bar.ts: bar for bar in grouped.get(comparator.id, [])}
    timestamps = sorted(primary_by_time.keys() & comparator_by_time.keys())
    points = [
        AnalysisPoint(
            timestamp=timestamp,
            value=float(primary_by_time[timestamp].close / comparator_by_time[timestamp].close),
        )
        for timestamp in timestamps
        if comparator_by_time[timestamp].close != 0
    ]
    maximum = max(len(primary_by_time), len(comparator_by_time), 1)
    warnings: list[AnalysisWarning] = []
    if not points:
        warnings.append(
            AnalysisWarning(
                code="no_aligned_bars", message="No aligned bars are available for this ratio."
            )
        )
    elif len(points) < maximum:
        warnings.append(
            AnalysisWarning(
                code="partial_overlap",
                message="Only intersecting timestamps were used; gaps were not forward-filled.",
            )
        )
    return RelativeStrengthOut(
        symbol=primary.symbol,
        benchmark=comparator.symbol,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        points=points,
        overlap_start=points[0].timestamp if points else None,
        overlap_end=points[-1].timestamp if points else None,
        coverage=len(points) / maximum,
        warnings=warnings,
    )


@router.get("/groups/{group_key}/relative-rotation", response_model=RelativeRotationOut)
async def group_relative_rotation(
    group_key: str,
    benchmark: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    lookback: int = Query(default=20, ge=2, le=252),
    tail_length: int = Query(default=10, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transparent relative trend/momentum states from locally aligned ratios.

    Trend is the ratio return over ``lookback`` bars. Momentum is its change from
    the preceding lookback observation. This is deliberately not a JdK calculation.
    """
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    benchmark_instrument = await _instrument(db, benchmark)
    instrument_ids = [member.instrument_id for member in group.members]
    instruments = {
        instrument.id: instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars()
    }
    bars_by_id = await _bars_by_instrument(
        db, [*instrument_ids, benchmark_instrument.id], timeframe, adjusted
    )
    benchmark_bars = {bar.ts: bar for bar in bars_by_id.get(benchmark_instrument.id, [])}
    rows: list[RelativeRotationRow] = []
    for member in sorted(group.members, key=lambda item: item.position):
        instrument = instruments.get(member.instrument_id)
        if instrument is None:
            continue
        bars = bars_by_id.get(instrument.id, [])
        aligned = [
            (bar.ts, float(bar.close / benchmark_bars[bar.ts].close))
            for bar in bars
            if bar.ts in benchmark_bars and benchmark_bars[bar.ts].close != 0
        ]
        maximum = max(len(bars), len(benchmark_bars), 1)
        warnings: list[AnalysisWarning] = []
        if not aligned:
            warnings.append(
                AnalysisWarning(
                    code="no_aligned_bars",
                    message="No aligned ratio bars are available.",
                    instrument_id=instrument.id,
                )
            )
        elif len(aligned) < maximum:
            warnings.append(
                AnalysisWarning(
                    code="partial_overlap",
                    message="Only intersecting timestamps were used; gaps were not forward-filled.",
                    instrument_id=instrument.id,
                )
            )
        coordinates: list[RelativeRotationTailPoint] = []
        for index in range(lookback * 2, len(aligned)):
            ratio = aligned[index][1]
            prior_ratio = aligned[index - lookback][1]
            prior_prior_ratio = aligned[index - lookback * 2][1]
            if prior_ratio == 0 or prior_prior_ratio == 0:
                continue
            trend = ratio / prior_ratio - 1
            previous_trend = prior_ratio / prior_prior_ratio - 1
            coordinates.append(
                RelativeRotationTailPoint(
                    timestamp=aligned[index][0], trend=trend, momentum=trend - previous_trend
                )
            )
        if not coordinates:
            warnings.append(
                AnalysisWarning(
                    code="insufficient_history",
                    message=f"Relative rotation requires {lookback * 2 + 1} aligned bars.",
                    instrument_id=instrument.id,
                )
            )
            rows.append(
                RelativeRotationRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    coverage=len(aligned) / maximum,
                    warnings=warnings,
                )
            )
            continue
        latest = coordinates[-1]
        state = (
            "leading"
            if latest.trend >= 0 and latest.momentum >= 0
            else "weakening"
            if latest.trend >= 0
            else "improving"
            if latest.momentum >= 0
            else "lagging"
        )
        rows.append(
            RelativeRotationRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                trend=latest.trend,
                momentum=latest.momentum,
                state=state,
                coverage=len(aligned) / maximum,
                tail=coordinates[-tail_length:],
                warnings=warnings,
            )
        )
    return RelativeRotationOut(
        group_key=group.stable_key,
        benchmark=benchmark_instrument.symbol,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        lookback=lookback,
        tail_length=tail_length,
        membership_version=group.id,
        rows=rows,
    )


@router.get(
    "/etf/{symbol}/industries/{industry}/proxies/snapshot",
    response_model=IndustryProxySnapshotOut,
)
async def industry_proxy_snapshot(
    symbol: str,
    industry: str,
    market_benchmark: str = Query(default="SPY"),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rank only independently verified industry-proxy ETFs from local bars.

    The sector ETF is the primary benchmark and ``market_benchmark`` is returned as
    a second aligned ratio.  The proxy list comes from the holdings-evidence gate;
    ticker names alone can never enter this batch universe.
    """
    sector = await _instrument(db, symbol)
    evidence = await etf_industry_proxies(
        symbol=sector.symbol, industry=industry, as_of=None, _=current_user, db=db
    )
    proxy_symbols = [item.symbol for item in evidence.proxies]
    market = await _instrument(db, market_benchmark)
    instruments = {
        item.symbol: item
        for item in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(proxy_symbols)))
        ).scalars()
    }
    ordered = [instruments[item.symbol] for item in evidence.proxies if item.symbol in instruments]
    bars_by_id = await _bars_by_instrument(
        db, [*(item.id for item in ordered), sector.id, market.id], timeframe, adjusted
    )
    sector_bars = {bar.ts: bar for bar in bars_by_id.get(sector.id, [])}
    market_bars = {bar.ts: bar for bar in bars_by_id.get(market.id, [])}
    rows: list[IndustryProxySnapshotRow] = []
    exclusions: list[AnalysisWarning] = []
    covered = 0
    for instrument in ordered:
        bars = bars_by_id.get(instrument.id, [])
        latest = bars[-1] if bars else None
        if latest is None:
            warning = AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
            exclusions.append(warning)
            rows.append(
                IndustryProxySnapshotRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    last=_cell(None, None, warning),
                    performance={period: _cell(None, None, warning) for period in _PERIODS},
                )
            )
            continue
        covered += 1
        closes = [float(bar.close) for bar in bars]
        volumes = [float(bar.volume) for bar in bars]
        performance = {
            period: _cell(
                float(latest.close / bars[-offset - 1].close - 1) if len(bars) > offset else None,
                latest,
                None
                if len(bars) > offset
                else AnalysisWarning(
                    code="insufficient_history",
                    message=f"{period} requires more history.",
                    instrument_id=instrument.id,
                ),
            )
            for period, offset in _PERIODS.items()
        }
        technical: dict[str, AnalysisCell] = {}
        for period in (20, 50, 200):
            technical[f"above_ma{period}"] = _cell(
                1.0
                if closes[-1] > _mean(closes[-period:])
                else 0.0
                if len(closes) >= period
                else None,
                latest,
                None
                if len(closes) >= period
                else AnalysisWarning(
                    code="insufficient_history",
                    message=f"Price versus SMA({period}) requires {period} bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 15:
            changes = [
                closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
            ]
            gain, loss = (
                _mean([max(change, 0.0) for change in changes]),
                _mean([max(-change, 0.0) for change in changes]),
            )
            technical["rsi14"] = _cell(
                100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)), latest
            )
        else:
            technical["rsi14"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="RSI(14) requires 15 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 252:
            window = closes[-252:]
            spread = max(window) - min(window)
            technical["position_52w"] = _cell(
                (closes[-1] - min(window)) / spread if spread else 1.0, latest
            )
        else:
            technical["position_52w"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="52-week position requires 252 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(volumes) >= 51:
            average_volume = _mean(volumes[-51:-1])
            technical["volume_ratio_50"] = _cell(
                volumes[-1] / average_volume if average_volume else None, latest
            )
        else:
            technical["volume_ratio_50"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="50-day volume ratio requires 51 bars.",
                    instrument_id=instrument.id,
                ),
            )

        def ratio(reference: dict) -> AnalysisCell:
            reference_bar = reference.get(latest.ts)
            return (
                _cell(float(latest.close / reference_bar.close), latest)
                if reference_bar and reference_bar.close
                else _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="unaligned_benchmark",
                        message="No aligned benchmark bar is available.",
                        instrument_id=instrument.id,
                    ),
                )
            )

        rows.append(
            IndustryProxySnapshotRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                last=_cell(float(latest.close), latest),
                performance=performance,
                technical=technical,
                relative_to_benchmark=ratio(sector_bars),
                relative_to_market=ratio(market_bars),
            )
        )
    return IndustryProxySnapshotOut(
        group_key=f"industry-proxy:{sector.symbol}:{industry}",
        etf_symbol=sector.symbol,
        industry=industry,
        market_benchmark=market.symbol,
        timeframe=timeframe.value,
        as_of=max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=sum(
            sum(ord(char) for char in f"{item.symbol}:{item.composition_date}:{item.known_at}")
            for item in evidence.proxies
        ),
        coverage=covered / max(len(ordered), 1),
        exclusions=exclusions,
        rows=rows,
        proxy_evidence=[item.model_dump(mode="json") for item in evidence.proxies],
    )


@router.get("/etf/{symbol}/constituents/snapshot", response_model=ETFConstituentSnapshotOut)
async def etf_constituent_snapshot(
    symbol: str,
    benchmark: str | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch technical/rank values for one source-labelled ETF holdings snapshot.

    The selected snapshot is the newest local disclosure known to the platform. Its
    resolved rows are an ETF-proxy universe, not a claim about official index membership.
    """
    etf = await _instrument(db, symbol)
    profile = (
        await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == etf.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(404, detail={"code": "etf_profile_not_found", "symbol": etf.symbol})
    snapshot = (
        await db.execute(
            select(ETFHoldingsSnapshot)
            .options(selectinload(ETFHoldingsSnapshot.rows))
            .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
            .order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            404, detail={"code": "etf_holdings_snapshot_not_found", "symbol": etf.symbol}
        )
    holdings = [
        row
        for row in snapshot.rows
        if row.is_resolved and row.constituent_instrument_id is not None
    ]
    instrument_ids = [
        row.constituent_instrument_id for row in holdings if row.constituent_instrument_id
    ]
    instruments = {
        item.id: item
        for item in (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars()
    }
    benchmark_instrument = await _instrument(db, benchmark) if benchmark else etf
    bars_by_id = await _bars_by_instrument(
        db, [*instrument_ids, benchmark_instrument.id], timeframe, adjusted
    )
    benchmark_bars = {bar.ts: bar for bar in bars_by_id.get(benchmark_instrument.id, [])}
    rows: list[GroupSnapshotRow] = []
    exclusions: list[AnalysisWarning] = []
    covered = 0
    for holding in sorted(holdings, key=lambda item: item.position):
        instrument = instruments.get(holding.constituent_instrument_id)
        if instrument is None:
            exclusions.append(
                AnalysisWarning(
                    code="missing_instrument",
                    message="Holding refers to an unavailable canonical instrument.",
                    instrument_id=holding.constituent_instrument_id,
                )
            )
            continue
        bars = bars_by_id.get(instrument.id, [])
        latest = bars[-1] if bars else None
        if latest is None:
            warning = AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
            exclusions.append(warning)
            rows.append(
                GroupSnapshotRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    last=_cell(None, None, warning),
                    performance={period: _cell(None, None, warning) for period in _PERIODS},
                )
            )
            continue
        covered += 1
        performance = {
            period: _cell(
                float(latest.close / bars[-offset - 1].close - 1) if len(bars) > offset else None,
                latest,
                None
                if len(bars) > offset
                else AnalysisWarning(
                    code="insufficient_history",
                    message=f"{period} requires more history.",
                    instrument_id=instrument.id,
                ),
            )
            for period, offset in _PERIODS.items()
        }
        closes, volumes = [float(bar.close) for bar in bars], [float(bar.volume) for bar in bars]
        technical: dict[str, AnalysisCell] = {}
        for period in (20, 50, 200):
            technical[f"above_ma{period}"] = _cell(
                1.0
                if closes[-1] > _mean(closes[-period:])
                else 0.0
                if len(closes) >= period
                else None,
                latest,
                None
                if len(closes) >= period
                else AnalysisWarning(
                    code="insufficient_history",
                    message=f"Price versus SMA({period}) requires {period} bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 15:
            changes = [
                closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
            ]
            gain, loss = (
                _mean([max(change, 0.0) for change in changes]),
                _mean([max(-change, 0.0) for change in changes]),
            )
            technical["rsi14"] = _cell(
                100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)), latest
            )
        else:
            technical["rsi14"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="RSI(14) requires 15 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 252:
            window = closes[-252:]
            spread = max(window) - min(window)
            technical["position_52w"] = _cell(
                (closes[-1] - min(window)) / spread if spread else 1.0, latest
            )
        else:
            technical["position_52w"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="52-week position requires 252 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(volumes) >= 51:
            average_volume = _mean(volumes[-51:-1])
            technical["volume_ratio_50"] = _cell(
                volumes[-1] / average_volume if average_volume else None, latest
            )
        else:
            technical["volume_ratio_50"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="50-day volume ratio requires 51 bars.",
                    instrument_id=instrument.id,
                ),
            )
        benchmark_bar = benchmark_bars.get(latest.ts)
        relative = (
            _cell(float(latest.close / benchmark_bar.close), latest)
            if benchmark_bar is not None and benchmark_bar.close != 0
            else _cell(
                None,
                latest,
                AnalysisWarning(
                    code="unaligned_benchmark",
                    message="No aligned benchmark bar is available.",
                    instrument_id=instrument.id,
                ),
            )
        )
        rows.append(
            GroupSnapshotRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                last=_cell(float(latest.close), latest),
                performance=performance,
                relative_to_benchmark=relative,
                technical=technical,
            )
        )
    return ETFConstituentSnapshotOut(
        group_key=f"etf-proxy:{etf.symbol}",
        timeframe=timeframe.value,
        as_of=max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=snapshot.id,
        coverage=covered / max(len(holdings), 1),
        exclusions=exclusions,
        rows=rows,
        etf_symbol=etf.symbol,
        composition_date=snapshot.composition_date,
        known_at=snapshot.known_at,
        provenance=snapshot.provenance,
        source_provider=snapshot.source_provider,
        completeness_status=snapshot.completeness_status,
    )


@router.get("/groups/{group_key}/snapshot", response_model=GroupSnapshotOut)
async def group_snapshot(
    group_key: str,
    benchmark: str | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    instrument_ids = [member.instrument_id for member in group.members]
    instruments = {
        item.id: item
        for item in (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars()
    }
    benchmark_instrument = await _instrument(db, benchmark) if benchmark else None
    all_ids = instrument_ids + ([benchmark_instrument.id] if benchmark_instrument else [])
    bars_by_id = await _bars_by_instrument(db, all_ids, timeframe, adjusted)
    benchmark_bars = (
        {bar.ts: bar for bar in bars_by_id.get(benchmark_instrument.id, [])}
        if benchmark_instrument
        else {}
    )
    rows: list[GroupSnapshotRow] = []
    exclusions: list[AnalysisWarning] = []
    covered = 0
    for member in sorted(group.members, key=lambda item: item.position):
        instrument = instruments.get(member.instrument_id)
        if instrument is None:
            exclusions.append(
                AnalysisWarning(
                    code="missing_instrument",
                    message="Membership refers to an unavailable canonical instrument.",
                    instrument_id=member.instrument_id,
                )
            )
            continue
        bars = bars_by_id.get(instrument.id, [])
        latest = bars[-1] if bars else None
        if latest is None:
            warning = AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
            exclusions.append(warning)
            rows.append(
                GroupSnapshotRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    last=_cell(None, None, warning),
                    performance={period: _cell(None, None, warning) for period in _PERIODS},
                )
            )
            continue
        covered += 1
        performance: dict[str, AnalysisCell] = {}
        for period, offset in _PERIODS.items():
            if len(bars) <= offset:
                performance[period] = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="insufficient_history",
                        message=f"{period} requires more history.",
                        instrument_id=instrument.id,
                    ),
                )
            else:
                performance[period] = _cell(
                    float(latest.close / bars[-offset - 1].close - 1), latest
                )
        closes = [float(bar.close) for bar in bars]
        volumes = [float(bar.volume) for bar in bars]
        technical: dict[str, AnalysisCell] = {}
        for period in (20, 50, 200):
            key = f"above_ma{period}"
            if len(closes) < period:
                technical[key] = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="insufficient_history",
                        message=f"Price versus SMA({period}) requires {period} bars.",
                        instrument_id=instrument.id,
                    ),
                )
            else:
                average = _mean(closes[-period:])
                technical[key] = _cell(1.0 if closes[-1] > average else 0.0, latest)
        if len(closes) >= 15:
            changes = [
                closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
            ]
            gain = _mean([max(change, 0.0) for change in changes])
            loss = _mean([max(-change, 0.0) for change in changes])
            technical["rsi14"] = _cell(
                100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)), latest
            )
        else:
            technical["rsi14"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="RSI(14) requires 15 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 252:
            window = closes[-252:]
            spread = max(window) - min(window)
            technical["position_52w"] = _cell(
                (closes[-1] - min(window)) / spread if spread else 1.0, latest
            )
        else:
            technical["position_52w"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="52-week position requires 252 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(volumes) >= 51:
            average_volume = _mean(volumes[-51:-1])
            technical["volume_ratio_50"] = _cell(
                volumes[-1] / average_volume if average_volume else None, latest
            )
        else:
            technical["volume_ratio_50"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="50-day volume ratio requires 51 bars.",
                    instrument_id=instrument.id,
                ),
            )
        relative: AnalysisCell | None = None
        if benchmark_instrument:
            benchmark_bar = benchmark_bars.get(latest.ts)
            if benchmark_bar is None or benchmark_bar.close == 0:
                relative = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="unaligned_benchmark",
                        message="No aligned benchmark bar is available.",
                        instrument_id=instrument.id,
                    ),
                )
            else:
                relative = _cell(float(latest.close / benchmark_bar.close), latest)
        rows.append(
            GroupSnapshotRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                last=_cell(float(latest.close), latest),
                performance=performance,
                relative_to_benchmark=relative,
                technical=technical,
            )
        )
    return GroupSnapshotOut(
        group_key=group.stable_key,
        timeframe=timeframe.value,
        as_of=max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=group.id,
        coverage=covered / max(len(group.members), 1),
        exclusions=exclusions,
        rows=rows,
    )


@router.get("/groups/{group_key}/breadth", response_model=BreadthOut)
async def group_breadth(
    group_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    bars_by_id = await _bars_by_instrument(
        db, [member.instrument_id for member in group.members], timeframe, adjusted
    )
    counts = {20: 0, 50: 0, 200: 0}
    eligible = {20: 0, 50: 0, 200: 0}
    exclusions: list[AnalysisWarning] = []
    as_of = None
    for member in group.members:
        bars = bars_by_id.get(member.instrument_id, [])
        if bars:
            as_of = max(as_of, bars[-1].ts) if as_of else bars[-1].ts
        for period in counts:
            if len(bars) < period:
                continue
            eligible[period] += 1
            if float(bars[-1].close) > sum(float(bar.close) for bar in bars[-period:]) / period:
                counts[period] += 1
        if not bars:
            exclusions.append(
                AnalysisWarning(
                    code="no_bars",
                    message="No local bars are available.",
                    instrument_id=member.instrument_id,
                )
            )
    return BreadthOut(
        group_key=group_key,
        timeframe=timeframe.value,
        as_of=as_of,
        evaluated_count=len(group.members),
        coverage=sum(1 for bars in bars_by_id.values() if bars) / max(len(group.members), 1),
        above_ma={
            f"ma{period}": counts[period] / eligible[period] if eligible[period] else None
            for period in counts
        },
        exclusions=exclusions,
    )


@router.get("/groups/{group_key}/breadth/history", response_model=BreadthHistoryOut)
async def group_breadth_history(
    group_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    limit: int = Query(default=500, ge=1, le=5_000),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return date-aligned local breadth without filling missing constituent bars."""
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    periods = (20, 50, 200)
    buckets: dict = {}
    exclusions: list[AnalysisWarning] = []
    bars_by_id = await _bars_by_instrument(
        db, [member.instrument_id for member in group.members], timeframe, adjusted
    )
    for member in group.members:
        bars = bars_by_id.get(member.instrument_id, [])
        if not bars:
            exclusions.append(
                AnalysisWarning(
                    code="no_bars",
                    message="No local bars are available.",
                    instrument_id=member.instrument_id,
                )
            )
            continue
        closes = [float(bar.close) for bar in bars]
        for period in periods:
            rolling_total = sum(closes[:period])
            for index in range(period - 1, len(bars)):
                if index >= period:
                    rolling_total += closes[index] - closes[index - period]
                point = buckets.setdefault(bars[index].ts, {item: [0, 0] for item in periods})
                point[period][1] += 1
                if closes[index] > rolling_total / period:
                    point[period][0] += 1
    points = [
        BreadthHistoryPoint(
            timestamp=timestamp,
            above_ma={
                f"ma{period}": values[period][0] / values[period][1] if values[period][1] else None
                for period in periods
            },
            coverage={
                f"ma{period}": values[period][1] / max(len(group.members), 1) for period in periods
            },
        )
        for timestamp, values in sorted(buckets.items())
    ][-limit:]
    return BreadthHistoryOut(
        group_key=group.stable_key,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=group.id,
        points=points,
        exclusions=exclusions,
    )
