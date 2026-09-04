"""Study Lab run lifecycle; only the isolated runner executes source."""

import hashlib
import json
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.research import CodeAsset, CodeVersion, ResearchRun
from app.models.screener import ScreenerDefinition
from app.models.strategy import StrategyDefinition, StrategyVersion
from app.models.user import User
from app.schemas.code import ResearchBatchResultOut, ResearchRunCreate, ResearchRunOut
from app.schemas.strategy import StrategyDefinitionDetailOut
from app.services.breadth import build_equal_reference_series
from app.services.parameter_validation import validate_parameter_values
from app.services.research_jobs import (
    cancel_research_run,
    collect_research_result,
    enqueue_research_run,
    read_research_progress,
)
from app.services.watchlist_sources import resolve_watchlist_source

router = APIRouter(prefix="/research", tags=["research"])

# Interactive workstation lists may contain 10,000 symbols. Batch execution is
# bounded independently from a single-instrument study: enough daily history for
# normal column/condition lookbacks, but never an unbounded 10,000 × full-history
# JSON payload handed to the isolated worker.
# The workstation's canonical US universe is already larger than 10,000
# active listings. Keep batch materialisation bounded, but do not reject a
# legitimate "All instruments" EasyScan merely because the current security
# master has crossed the old 10k threshold.
MAX_BATCH_SYMBOLS = 25_000
BATCH_HISTORY_LIMIT = 500
MAX_HISTORY_LIMIT = 5_000
BATCH_QUERY_SIZE = 500
RESEARCH_ADJUSTMENTS = {"split_adjusted": True, "raw": False}


class ResearchEventSignalPromotionRequest(BaseModel):
    """Optional naming metadata for a lineage-preserving event promotion."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


def _research_manifest_fingerprint(manifest: object) -> str:
    """Fingerprint the exact persisted dataset manifest used by one research run."""

    try:
        encoded = json.dumps(
            manifest if isinstance(manifest, dict) else {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    except (TypeError, ValueError):
        encoded = "{}"
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _research_manifest_summary(manifest: dict) -> dict:
    """Keep small, human-readable manifest fields beside the immutable run link."""

    keys = (
        "source",
        "timeframe",
        "adjustment",
        "session",
        "start_date",
        "end_date",
        "as_of",
        "membership_version",
        "requested_symbols",
        "batch_history_limit",
        "exclusions",
    )
    return {key: manifest[key] for key in keys if key in manifest}


def _parse_dataset_bound(value: object, *, end: bool) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_dataset_date", "value": text},
            ) from exc
        parsed = datetime.combine(parsed_date, time.max if end else time.min)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _dataset_options(run_config: dict, manifest: dict) -> dict:
    timeframe_value = str(
        run_config.get("timeframe") or manifest.get("timeframe") or Timeframe.D1.value
    ).upper()
    try:
        timeframe = Timeframe(timeframe_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_dataset_timeframe", "value": timeframe_value},
        ) from exc

    adjustment = str(
        run_config.get("adjustment") or manifest.get("adjustment") or "split_adjusted"
    ).lower()
    if adjustment not in RESEARCH_ADJUSTMENTS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_dataset_adjustment",
                "value": adjustment,
                "supported": sorted(RESEARCH_ADJUSTMENTS),
            },
        )

    session = str(run_config.get("session") or manifest.get("session") or "regular").lower()
    if session not in {"regular", "all"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "unsupported_dataset_session", "value": session},
        )
    start = _parse_dataset_bound(
        run_config.get("start_date") or manifest.get("start_date"), end=False
    )
    end = _parse_dataset_bound(run_config.get("end_date") or manifest.get("end_date"), end=True)
    as_of = _parse_dataset_bound(run_config.get("as_of") or manifest.get("as_of"), end=True)
    if as_of and start and start > as_of:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "dataset_as_of_before_start",
                "as_of": as_of.isoformat(),
                "start_date": start.isoformat(),
            },
        )
    if as_of and (end is None or as_of < end):
        end = as_of
    if start and end and start > end:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "dataset_date_range_reversed",
                "start_date": start.date().isoformat(),
                "end_date": end.date().isoformat(),
            },
        )
    benchmark = run_config.get("benchmark") or manifest.get("benchmark")
    if benchmark is not None and (not isinstance(benchmark, str) or not benchmark.strip()):
        raise HTTPException(status_code=422, detail={"code": "invalid_dataset_benchmark"})
    return {
        "timeframe": timeframe,
        "adjustment": adjustment,
        "is_adjusted": RESEARCH_ADJUSTMENTS[adjustment],
        "session": session,
        "start": start,
        "end": end,
        "as_of": as_of,
        "benchmark": benchmark.strip().upper() if isinstance(benchmark, str) else None,
    }


def _dataset_manifest_fields(manifest: dict, options: dict) -> dict:
    fields = {
        **manifest,
        "source": "canonical_database",
        "timeframe": options["timeframe"].value,
        "adjustment": options["adjustment"],
        "session": options["session"],
    }
    if options["benchmark"]:
        fields["benchmark"] = options["benchmark"]
    if options["start"]:
        fields["start_date"] = options["start"].date().isoformat()
    if options["end"]:
        fields["end_date"] = options["end"].date().isoformat()
    if options.get("as_of"):
        fields["as_of"] = options["as_of"].isoformat()
    return fields


def _bar_series(bars: list[OHLCVBar]) -> dict[str, list[float | None] | list[str]]:
    """Serialize the canonical OHLCV fields needed by the isolated market SDK."""
    return {
        "opens": [float(bar.open) for bar in bars],
        "highs": [float(bar.high) for bar in bars],
        "lows": [float(bar.low) for bar in bars],
        "closes": [float(bar.close) for bar in bars],
        "volumes": [float(bar.volume) if bar.volume is not None else None for bar in bars],
        "vwaps": [float(bar.vwap) if bar.vwap is not None else None for bar in bars],
        "sessions": [bar.session for bar in bars],
    }


def _instrument_metadata(instrument: Instrument) -> dict[str, object | None]:
    equity = instrument.equity_detail
    stats = instrument.stats
    return {
        "instrument_id": instrument.id,
        "symbol": instrument.symbol,
        "name": instrument.name,
        "currency": instrument.currency,
        "is_active": instrument.is_active,
        "is_synthetic": instrument.is_synthetic,
        "primary_identifier_type": instrument.primary_identifier_type,
        "primary_identifier_value": instrument.primary_identifier_value,
        # These are deliberately flattened into the prepared, read-only
        # metadata object so visual Python conditions can compare the same
        # supported fields as the legacy condition editor without opening a
        # second data path in the sandbox.
        "sector": equity.sector if equity else None,
        "industry": equity.industry if equity else None,
        "country": equity.country if equity else None,
        "exchange_mic": equity.exchange_mic if equity else None,
        "market_cap_tier": equity.market_cap_tier if equity else None,
        "employees": equity.employees if equity else None,
        "market_cap": float(stats.market_cap) if stats and stats.market_cap is not None else None,
        "pe_ratio": float(stats.pe_ratio) if stats and stats.pe_ratio is not None else None,
        "beta": float(stats.beta) if stats and stats.beta is not None else None,
        "avg_volume_30d": float(stats.avg_volume_30d)
        if stats and stats.avg_volume_30d is not None
        else None,
        "dividend_yield": float(stats.dividend_yield)
        if stats and stats.dividend_yield is not None
        else None,
    }


async def _load_instrument_bars(
    db: AsyncSession, instrument: Instrument, options: dict, *, limit: int
) -> list[OHLCVBar]:
    conditions = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == options["timeframe"],
        OHLCVBar.is_adjusted.is_(options["is_adjusted"]),
    ]
    if options["session"] == "regular":
        conditions.append(OHLCVBar.session == "regular")
    if options["start"]:
        conditions.append(OHLCVBar.ts >= options["start"])
    if options["end"]:
        conditions.append(OHLCVBar.ts <= options["end"])
    bars = (
        (
            await db.execute(
                select(OHLCVBar).where(*conditions).order_by(OHLCVBar.ts.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    bars.reverse()
    return bars


async def _materialize_instrument_dataset(
    db: AsyncSession,
    instrument: Instrument,
    manifest: dict,
    options: dict,
    *,
    history_limit: int = MAX_HISTORY_LIMIT,
) -> dict:
    bars = await _load_instrument_bars(db, instrument, options, limit=history_limit)
    return {
        **_dataset_manifest_fields(manifest, options),
        "symbol": instrument.symbol,
        "instrument_id": instrument.id,
        "metadata": _instrument_metadata(instrument),
        "timestamps": [bar.ts.isoformat() for bar in bars],
        **_bar_series(bars),
    }


async def _materialize_benchmark_dataset(
    db: AsyncSession, options: dict, *, history_limit: int = MAX_HISTORY_LIMIT
) -> dict | None:
    benchmark = options["benchmark"]
    if not benchmark:
        return None
    instrument = (
        await db.execute(
            select(Instrument)
            .options(selectinload(Instrument.equity_detail), selectinload(Instrument.stats))
            .where(Instrument.symbol == benchmark)
        )
    ).scalar_one_or_none()
    if instrument is None:
        return {
            "status": "unavailable",
            "symbol": benchmark,
            "reason": "benchmark_instrument_not_found",
        }
    bars = await _load_instrument_bars(db, instrument, options, limit=history_limit)
    if not bars:
        return {
            "status": "unavailable",
            "symbol": benchmark,
            "instrument_id": instrument.id,
            "reason": "benchmark_history_unavailable",
        }
    return {
        "status": "ready",
        "source": "canonical_database",
        "symbol": instrument.symbol,
        "instrument_id": instrument.id,
        "metadata": _instrument_metadata(instrument),
        "timeframe": options["timeframe"].value,
        "adjustment": options["adjustment"],
        "session": options["session"],
        "timestamps": [bar.ts.isoformat() for bar in bars],
        **_bar_series(bars),
    }


async def _load_bars_for_ids(
    db: AsyncSession, instrument_ids: list[int], options: dict, *, limit: int
) -> dict[int, list[OHLCVBar]]:
    """Load a bounded, per-instrument bar window for derived reference targets."""
    if not instrument_ids:
        return {}
    conditions = [
        OHLCVBar.instrument_id.in_(instrument_ids),
        OHLCVBar.timeframe == options["timeframe"],
        OHLCVBar.is_adjusted.is_(options["is_adjusted"]),
    ]
    if options["session"] == "regular":
        conditions.append(OHLCVBar.session == "regular")
    if options["start"]:
        conditions.append(OHLCVBar.ts >= options["start"])
    if options["end"]:
        conditions.append(OHLCVBar.ts <= options["end"])
    ranked_bars = (
        select(
            OHLCVBar.id.label("bar_id"),
            func.row_number()
            .over(
                partition_by=OHLCVBar.instrument_id,
                order_by=OHLCVBar.ts.desc(),
            )
            .label("bar_rank"),
        )
        .where(*conditions)
        .subquery()
    )
    bars = (
        await db.execute(
            select(OHLCVBar)
            .join(ranked_bars, OHLCVBar.id == ranked_bars.c.bar_id)
            .where(ranked_bars.c.bar_rank <= limit)
            .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
        )
    ).scalars()
    result: dict[int, list[OHLCVBar]] = {}
    for bar in bars:
        result.setdefault(bar.instrument_id, []).append(bar)
    return result


async def _materialize_reference_dataset(
    db: AsyncSession,
    options: dict,
    run_config: dict,
    *,
    history_limit: int,
) -> dict | None:
    """Materialize a canonical equal-weight peer index for Python comparisons."""
    raw_ids = run_config.get("reference_instrument_ids")
    if raw_ids is None:
        return None
    if not isinstance(raw_ids, list):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_reference_universe_membership"},
        )
    instrument_ids = list(
        dict.fromkeys(
            value
            for value in raw_ids
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        )
    )
    if not instrument_ids:
        return {
            "status": "unavailable",
            "reason": "reference_universe_empty",
            "target": "derived_equal_weight_return_index",
        }
    if len(instrument_ids) > MAX_BATCH_SYMBOLS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "reference_universe_too_large",
                "maximum": MAX_BATCH_SYMBOLS,
            },
        )
    bars_by_id = await _load_bars_for_ids(
        db, instrument_ids, options, limit=max(1, min(history_limit, MAX_HISTORY_LIMIT))
    )
    series, summary = build_equal_reference_series(bars_by_id)
    target = run_config.get("reference_target")
    target = dict(target) if isinstance(target, dict) else {}
    summary = {
        **summary,
        "requested_member_count": len(instrument_ids),
        "covered_member_count": sum(bool(bars) for bars in bars_by_id.values()),
        "universe": run_config.get("reference_universe"),
        "provenance": target,
    }
    if not series:
        return {
            "status": "unavailable",
            "reason": "reference_history_unavailable",
            "target": "derived_equal_weight_return_index",
            "summary": summary,
        }
    timestamps = [point.ts.isoformat() for point in series]
    closes = [float(point.close) for point in series]
    return {
        "status": "ready",
        "source": "canonical_database",
        "symbol": "REFERENCE:EQUAL_WEIGHT",
        "instrument_id": None,
        "metadata": {
            "name": "Derived equal-weight reference index",
            "reference_target": summary,
        },
        "timeframe": options["timeframe"].value,
        "adjustment": options["adjustment"],
        "session": options["session"],
        "timestamps": timestamps,
        # The aggregate is a close-only return index.  Non-close fields remain
        # explicit and unavailable rather than being inferred from members.
        "opens": closes,
        "highs": closes,
        "lows": closes,
        "closes": closes,
        "volumes": [None] * len(closes),
        "vwaps": [None] * len(closes),
        "sessions": [options["session"]] * len(closes),
    }


async def _materialize_declared_dataset(
    db: AsyncSession,
    manifest: dict,
    run_config: dict,
    *,
    lookback: int | None = None,
    user_id: int | None = None,
) -> dict:
    """Materialize only an explicitly declared canonical local dataset for the runner."""
    options = _dataset_options(run_config, manifest)
    if lookback is not None and (
        isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1
    ):
        raise HTTPException(
            status_code=422, detail={"code": "invalid_code_lookback", "lookback": lookback}
        )
    if lookback is not None and lookback >= MAX_HISTORY_LIMIT:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "code_lookback_exceeds_dataset_limit",
                "lookback": lookback,
                "maximum": MAX_HISTORY_LIMIT - 1,
            },
        )
    history_limit = max(
        BATCH_HISTORY_LIMIT, (lookback + 1) if lookback is not None else BATCH_HISTORY_LIMIT
    )
    benchmark_history_limit = max(
        MAX_HISTORY_LIMIT if lookback is None else history_limit, history_limit
    )
    benchmark_dataset = await _materialize_benchmark_dataset(
        db, options, history_limit=benchmark_history_limit
    )
    reference_dataset = await _materialize_reference_dataset(
        db, options, run_config, history_limit=benchmark_history_limit
    )
    comparison_dataset = reference_dataset if reference_dataset is not None else benchmark_dataset
    source_metadata: dict[str, object] = {}
    source_id_value = run_config.get("universe_source_id")
    if source_id_value not in (None, ""):
        if user_id is None:
            raise HTTPException(
                status_code=422, detail={"code": "universe_source_user_context_required"}
            )
        source_id = str(source_id_value).strip()
        if source_id.isdigit():
            source_id = f"watchlist:{source_id}"
        try:
            resolved_source = await resolve_watchlist_source(
                db,
                user_id,
                source_id,
                as_of=options["as_of"],
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": str(exc), "source_id": source_id}
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": str(exc), "source_id": source_id}
            ) from exc
        source_member_ids = list(
            dict.fromkeys(member.instrument_id for member in resolved_source.members)
        )
        source_instruments = (
            (
                (
                    await db.execute(
                        select(Instrument)
                        .options(
                            selectinload(Instrument.equity_detail), selectinload(Instrument.stats)
                        )
                        .where(Instrument.id.in_(source_member_ids))
                    )
                )
                .scalars()
                .all()
            )
            if source_member_ids
            else []
        )
        source_by_id = {instrument.id: instrument for instrument in source_instruments}
        source_symbols = [
            source_by_id[member.instrument_id].symbol
            for member in resolved_source.members
            if member.instrument_id in source_by_id
        ]
        source_metadata = {
            "universe_source_id": source_id,
            "universe_source": resolved_source.descriptor.model_dump(mode="json"),
            "universe_membership_version": resolved_source.descriptor.membership_version,
            "universe_source_exclusions": list(resolved_source.exclusions),
        }
        # A source declaration is authoritative. Do not let stale/manual symbols
        # in an imported configuration silently widen or replace its membership.
        symbols = source_symbols
    else:
        symbols = run_config.get("symbols")
    if isinstance(symbols, list):
        requested = list(
            dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip())
        )
        if not requested:
            result = {
                **_dataset_manifest_fields(manifest, options),
                **source_metadata,
                "datasets": [],
                "exclusions": [],
            }
            if benchmark_dataset is not None:
                result["benchmark_coverage"] = benchmark_dataset
            return result
        if len(requested) > MAX_BATCH_SYMBOLS:
            raise HTTPException(
                status_code=422,
                detail={"code": "batch_universe_too_large", "maximum": MAX_BATCH_SYMBOLS},
            )
        instruments: list[Instrument] = []
        for offset in range(0, len(requested), BATCH_QUERY_SIZE):
            instruments.extend(
                (
                    await db.execute(
                        select(Instrument)
                        .options(
                            selectinload(Instrument.equity_detail), selectinload(Instrument.stats)
                        )
                        .where(Instrument.symbol.in_(requested[offset : offset + BATCH_QUERY_SIZE]))
                    )
                )
                .scalars()
                .all()
            )
        by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
        bars_by_instrument: dict[int, list[OHLCVBar]] = {}
        instrument_ids = [instrument.id for instrument in instruments]
        for offset in range(0, len(instrument_ids), BATCH_QUERY_SIZE):
            ids = instrument_ids[offset : offset + BATCH_QUERY_SIZE]
            bar_conditions = [
                OHLCVBar.instrument_id.in_(ids),
                OHLCVBar.timeframe == options["timeframe"],
                OHLCVBar.is_adjusted.is_(options["is_adjusted"]),
            ]
            if options["session"] == "regular":
                bar_conditions.append(OHLCVBar.session == "regular")
            if options["start"]:
                bar_conditions.append(OHLCVBar.ts >= options["start"])
            if options["end"]:
                bar_conditions.append(OHLCVBar.ts <= options["end"])
            ranked_bars = (
                select(
                    OHLCVBar.id.label("bar_id"),
                    func.row_number()
                    .over(
                        partition_by=OHLCVBar.instrument_id,
                        order_by=OHLCVBar.ts.desc(),
                    )
                    .label("bar_rank"),
                )
                .where(*bar_conditions)
                .subquery()
            )
            bars = (
                (
                    await db.execute(
                        select(OHLCVBar)
                        .join(ranked_bars, OHLCVBar.id == ranked_bars.c.bar_id)
                        .where(ranked_bars.c.bar_rank <= history_limit)
                        .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
                    )
                )
                .scalars()
                .all()
            )
            for bar in bars:
                bars_by_instrument.setdefault(bar.instrument_id, []).append(bar)
        datasets = []
        exclusions = []
        for symbol in requested:
            instrument = by_symbol.get(symbol)
            if instrument is None:
                exclusions.append({"symbol": symbol, "code": "declared_instrument_not_found"})
                continue
            bars = bars_by_instrument.get(instrument.id, [])
            if not bars:
                exclusions.append(
                    {
                        "symbol": symbol,
                        "instrument_id": instrument.id,
                        "code": "declared_history_unavailable",
                    }
                )
                continue
            datasets.append(
                {
                    "source": "canonical_database",
                    "symbol": instrument.symbol,
                    "instrument_id": instrument.id,
                    "metadata": _instrument_metadata(instrument),
                    "timeframe": options["timeframe"].value,
                    "adjustment": options["adjustment"],
                    "session": options["session"],
                    "timestamps": [bar.ts.isoformat() for bar in bars],
                    **_bar_series(bars),
                    **(
                        {"benchmark_dataset": comparison_dataset}
                        if comparison_dataset and comparison_dataset.get("status") == "ready"
                        else {}
                    ),
                }
            )
        result = {
            **_dataset_manifest_fields(manifest, options),
            **source_metadata,
            "datasets": datasets,
            "requested_symbols": requested,
            "batch_history_limit": history_limit,
            "exclusions": exclusions,
        }
        if benchmark_dataset is not None:
            result["benchmark_coverage"] = benchmark_dataset
        if reference_dataset is not None:
            result["reference_coverage"] = reference_dataset
        if comparison_dataset is not None and comparison_dataset.get("status") == "ready":
            # Batch members consume the selected comparison source through the
            # per-member ``benchmark_dataset`` field, while callers also need
            # the same immutable source at the manifest level for inspection
            # and provenance assertions.
            result["benchmark_dataset"] = comparison_dataset
        return result
    symbol = str(run_config.get("symbol") or manifest.get("symbol") or "").upper()
    if not symbol:
        return dict(manifest)
    instrument = (
        await db.execute(
            select(Instrument)
            .options(selectinload(Instrument.equity_detail), selectinload(Instrument.stats))
            .where(Instrument.symbol == symbol)
        )
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            status_code=422, detail={"code": "declared_instrument_not_found", "symbol": symbol}
        )
    result = await _materialize_instrument_dataset(
        db, instrument, manifest, options, history_limit=benchmark_history_limit
    )
    result.update(source_metadata)
    if benchmark_dataset is not None:
        result["benchmark_coverage"] = benchmark_dataset
        if benchmark_dataset.get("status") == "ready":
            result["benchmark_dataset"] = benchmark_dataset
    if reference_dataset is not None:
        result["reference_coverage"] = reference_dataset
        if reference_dataset.get("status") == "ready":
            result["benchmark_dataset"] = reference_dataset
    return result


@router.post("/runs", response_model=ResearchRunOut, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: ResearchRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = (
        await db.execute(
            select(CodeVersion)
            .join(CodeAsset)
            .where(CodeVersion.id == body.code_version_id, CodeAsset.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Code version not found")
    run_config = dict(body.run_config)
    provided_parameters = run_config.get("parameters", {})
    if not isinstance(provided_parameters, dict):
        raise HTTPException(status_code=422, detail={"code": "parameters_must_be_object"})
    parameters = {**(version.default_parameters or {}), **provided_parameters}
    parameter_errors = validate_parameter_values(version.parameter_schema, parameters)
    if parameter_errors:
        raise HTTPException(
            status_code=422,
            detail={"code": "parameter_validation_failed", "errors": parameter_errors},
        )
    run_config["parameters"] = parameters
    dataset_manifest = await _materialize_declared_dataset(
        db, body.dataset_manifest, run_config, lookback=version.lookback, user_id=current_user.id
    )
    run = ResearchRun(
        user_id=current_user.id,
        code_version_id=version.id,
        run_config=run_config,
        dataset_manifest=dataset_manifest,
    )
    run.code_version = version
    db.add(run)
    await db.flush()
    enqueue_research_run(run)
    # A freshly flushed instance may still have a lazy ``artifacts`` loader.
    # FastAPI serializes the response outside SQLAlchemy's greenlet, so return
    # an explicitly eager-loaded instance rather than leaking MissingGreenlet.
    return (
        await db.execute(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.artifacts),
                selectinload(ResearchRun.code_version),
            )
            .where(ResearchRun.id == run.id)
        )
    ).scalar_one()


@router.get("/runs", response_model=list[ResearchRunOut])
async def list_runs(
    limit: int = 25,
    include_artifacts: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the current user's newest persisted research runs for result panes."""
    bounded_limit = max(1, min(limit, 100))
    runs = (
        (
            await db.execute(
                select(ResearchRun)
                .options(
                    selectinload(ResearchRun.artifacts),
                    selectinload(ResearchRun.code_version),
                )
                .where(ResearchRun.user_id == current_user.id)
                .order_by(desc(ResearchRun.created_at), desc(ResearchRun.id))
                .limit(bounded_limit)
            )
        )
        .scalars()
        .all()
    )
    for run in runs:
        collect_research_result(run)
        run.progress = read_research_progress(run.id)
    await db.flush()
    # Result payloads can contain large series/tables. The workstation list only
    # needs status and artifact counts; full payloads remain available through
    # /runs/{id}. Keep an explicit opt-in for older clients that need list payloads.
    return [
        {
            "id": run.id,
            "code_version_id": run.code_version_id,
            "output_contract": run.code_version.output_contract if run.code_version else None,
            "status": run.status,
            "run_config": run.run_config if include_artifacts else {},
            "dataset_manifest": run.dataset_manifest if include_artifacts else {},
            "reproducibility_hash": run.reproducibility_hash,
            "diagnostics": run.diagnostics if include_artifacts else [],
            "warnings": run.warnings if include_artifacts else [],
            "resource_usage": run.resource_usage if include_artifacts else {},
            "logs": run.logs if include_artifacts else "",
            "progress": run.progress if include_artifacts else {},
            "artifact_count": len(run.artifacts),
            "artifacts": run.artifacts if include_artifacts else [],
        }
        for run in runs
    ]


@router.get("/runs/{run_id}", response_model=ResearchRunOut)
async def get_run(
    run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    run = (
        await db.execute(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.artifacts),
                selectinload(ResearchRun.code_version),
            )
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    collect_research_result(run)
    run.progress = read_research_progress(run.id)
    # ResearchRunOut exposes the immutable source contract so result surfaces can
    # offer only adapters that the source can execute safely.
    if run.code_version is not None:
        setattr(run, "output_contract", run.code_version.output_contract)
    await db.flush()
    return run


@router.post(
    "/runs/{run_id}/promote-event-signal",
    response_model=StrategyDefinitionDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def promote_event_artifact_to_strategy_signal(
    run_id: int,
    body: ResearchEventSignalPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote one completed event artifact while retaining its research lineage.

    This target is intentionally limited to a source CodeVersion whose declared contract is
    ``events``.  A multi-output ``study`` that happens to contain an events artifact must use an
    explicit adapter first; relabelling it as a signal would hide the other outputs and could
    change the runner's contract.  Strategy execution re-evaluates the immutable source code on
    current canonical data, so the originating run's manifest and reproducibility hash are
    disclosed as lineage rather than misrepresented as a snapshot replay.
    """
    run = (
        await db.execute(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.artifacts),
                selectinload(ResearchRun.code_version).selectinload(CodeVersion.asset),
            )
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "research_signal_promotion_requires_completed_run",
                "status": run.status,
            },
        )
    event_artifact = next(
        (item for item in run.artifacts if item.artifact_type == "events"),
        None,
    )
    if event_artifact is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_signal_promotion_events_artifact_required",
                "message": "The completed run does not contain an events artifact.",
            },
        )
    event_value = (
        event_artifact.payload.get("value") if isinstance(event_artifact.payload, dict) else None
    )
    if not isinstance(event_value, list):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_signal_promotion_events_artifact_invalid",
                "message": "The events artifact does not contain a persisted event list.",
            },
        )
    source_version = run.code_version
    source_asset = source_version.asset if source_version is not None else None
    if (
        source_version is None
        or source_asset is None
        or source_asset.user_id != current_user.id
        or source_asset.is_archived
        or source_asset.kind not in {"signal", "study"}
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "research_signal_promotion_source_unavailable"},
        )
    if source_version.output_contract != "events":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_signal_promotion_requires_events_contract",
                "message": "Only an events CodeVersion can be promoted directly to a Strategy signal; multi-output studies require an explicit adapter.",
                "output_contract": source_version.output_contract,
            },
        )

    base_name = body.name or f"{source_asset.name} Events Signal"
    name = base_name[:120]
    suffix = 2
    while (
        await db.execute(
            select(func.count())
            .select_from(StrategyDefinition)
            .where(
                StrategyDefinition.user_id == current_user.id,
                func.lower(StrategyDefinition.name) == name.lower(),
            )
        )
    ).scalar_one():
        suffix_text = f" ({suffix})"
        name = f"{base_name[:120 - len(suffix_text)]}{suffix_text}"
        suffix += 1

    manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    run_config = run.run_config if isinstance(run.run_config, dict) else {}
    lineage = {
        "origin": "research_run_event_promotion",
        "source_run_id": run.id,
        "source_code_asset_id": source_asset.id,
        "source_code_version_id": source_version.id,
        "source_artifact_id": event_artifact.id,
        "source_artifact_name": event_artifact.name,
        "source_reproducibility_hash": run.reproducibility_hash,
        "source_dataset_manifest_sha256": _research_manifest_fingerprint(manifest),
        "source_dataset_manifest": _research_manifest_summary(manifest),
        "source_run_config": run_config,
        "output_contract": source_version.output_contract,
        "semantics": "re_evaluate_current_data_event_source",
        "point_in_time_source_preserved": False,
    }
    strategy = StrategyDefinition(
        user_id=current_user.id,
        name=name,
        description=body.description
        or f"Event signal promoted from research run #{run.id}; current-data re-evaluation and source lineage are explicit.",
        source_type="custom",
        definition_type="python",
        is_active=True,
        tags=["study-lab", "python-signal", "events"],
        metadata_json={**lineage, "code_version_id": source_version.id},
    )
    strategy.versions.append(
        StrategyVersion(
            version_number=1,
            definition_snapshot={
                "kind": "python_event_signal",
                "code_version_id": source_version.id,
                "output_contract": "events",
                "source_run_id": run.id,
                "source_artifact_name": event_artifact.name,
                "source_dataset_manifest_sha256": lineage["source_dataset_manifest_sha256"],
                "semantics": lineage["semantics"],
            },
            parameter_schema=source_version.parameter_schema or {},
            default_parameters=source_version.default_parameters or {},
            notes="Event artifact promoted from a completed research run; execution re-evaluates current canonical data.",
            is_current=True,
        )
    )
    db.add(strategy)
    await db.commit()
    return (
        await db.execute(
            select(StrategyDefinition)
            .options(
                selectinload(StrategyDefinition.versions),
                selectinload(StrategyDefinition.run_batches),
                selectinload(StrategyDefinition.runs),
            )
            .where(
                StrategyDefinition.id == strategy.id,
                StrategyDefinition.user_id == current_user.id,
            )
        )
    ).scalar_one()


@router.post(
    "/runs/{run_id}/promote-event-filter",
    status_code=status.HTTP_201_CREATED,
)
async def promote_event_artifact_to_screener(
    run_id: int,
    body: ResearchEventSignalPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an explicit current-observation Boolean adapter for an event artifact.

    Event lists are not Boolean conditions by themselves.  This adapter keeps the source
    CodeVersion and selected artifact name intact, scopes the screener to the run's declared
    canonical member IDs, and asks the isolated runner to apply ``events_to_boolean``.  It
    therefore cannot widen a single-symbol run to the whole security master or silently
    reinterpret a multi-output study.
    """

    run = (
        await db.execute(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.artifacts),
                selectinload(ResearchRun.code_version).selectinload(CodeVersion.asset),
            )
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "research_filter_promotion_requires_completed_run",
                "status": run.status,
            },
        )
    event_artifact = next(
        (item for item in run.artifacts if item.artifact_type == "events"),
        None,
    )
    if event_artifact is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_filter_promotion_events_artifact_required",
                "message": "The completed run does not contain an events artifact.",
            },
        )
    event_value = (
        event_artifact.payload.get("value") if isinstance(event_artifact.payload, dict) else None
    )
    if not isinstance(event_value, list):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_filter_promotion_events_artifact_invalid",
                "message": "The events artifact does not contain a persisted event list.",
            },
        )
    source_version = run.code_version
    source_asset = source_version.asset if source_version is not None else None
    if (
        source_version is None
        or source_asset is None
        or source_asset.user_id != current_user.id
        or source_asset.is_archived
        or source_asset.kind not in {"signal", "study"}
        or source_version.output_contract != "events"
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_filter_promotion_source_unavailable",
                "message": "Only a user-owned single-output events source can become a watchlist condition.",
            },
        )

    manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    raw_datasets = manifest.get("datasets")
    declared_ids: list[int] = []
    if isinstance(raw_datasets, list):
        declared_ids.extend(
            item.get("instrument_id")
            for item in raw_datasets
            if isinstance(item, dict)
            and isinstance(item.get("instrument_id"), int)
            and not isinstance(item.get("instrument_id"), bool)
            and item.get("instrument_id") > 0
        )
    if isinstance(manifest.get("instrument_id"), int) and not isinstance(
        manifest.get("instrument_id"), bool
    ):
        declared_ids.append(manifest["instrument_id"])
    declared_ids = list(dict.fromkeys(declared_ids))
    if not declared_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "research_filter_promotion_universe_required",
                "message": "The source run has no declared canonical members; refusing to widen the filter universe.",
            },
        )

    run_config = run.run_config if isinstance(run.run_config, dict) else {}
    raw_timeframe = run_config.get("timeframe") or manifest.get("timeframe") or Timeframe.D1.value
    try:
        timeframe = Timeframe(str(raw_timeframe).strip().upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "research_filter_promotion_timeframe_invalid"},
        ) from exc

    base_name = body.name or f"{source_asset.name} {event_artifact.name} Filter"
    name = base_name[:100]
    suffix = 2
    while (
        await db.execute(
            select(func.count())
            .select_from(ScreenerDefinition)
            .where(
                ScreenerDefinition.user_id == current_user.id,
                func.lower(ScreenerDefinition.name) == name.lower(),
            )
        )
    ).scalar_one():
        suffix_text = f" ({suffix})"
        name = f"{base_name[:100 - len(suffix_text)]}{suffix_text}"
        suffix += 1

    lineage = {
        "origin": "research_run_event_filter_promotion",
        "source_run_id": run.id,
        "source_code_asset_id": source_asset.id,
        "source_code_version_id": source_version.id,
        "source_artifact_id": event_artifact.id,
        "source_artifact_name": event_artifact.name,
        "source_reproducibility_hash": run.reproducibility_hash,
        "source_dataset_manifest_sha256": _research_manifest_fingerprint(manifest),
        "source_dataset_manifest": _research_manifest_summary(manifest),
        "source_run_config": run_config,
        "output_contract": source_version.output_contract,
        "output_adapter": "events_to_boolean",
        "semantics": "event_presence_at_current_observation",
        "point_in_time_source_preserved": False,
    }
    screener = ScreenerDefinition(
        user_id=current_user.id,
        name=name,
        description=body.description
        or f"Event filter promoted from research run #{run.id}; current-data event presence and source lineage are explicit.",
        universe_type="custom",
        universe_instrument_ids=declared_ids,
        timeframe=timeframe,
        conditions={
            "type": "python_condition",
            "code_version_id": source_version.id,
            "output_name": event_artifact.name,
            "output_adapter": "events_to_boolean",
            "provenance": lineage,
        },
        is_active=True,
    )
    db.add(screener)
    await db.commit()
    return {
        "id": screener.id,
        "name": screener.name,
        "description": screener.description,
        "universe_type": screener.universe_type,
        "universe_instrument_ids": declared_ids,
        "timeframe": timeframe.value,
        "conditions": screener.conditions,
        "semantics": lineage["semantics"],
    }


@router.get("/runs/{run_id}/batch-results", response_model=ResearchBatchResultOut)
async def get_batch_results(
    run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    run = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.artifacts))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    collect_research_result(run)
    version = (
        await db.execute(select(CodeVersion).where(CodeVersion.id == run.code_version_id))
    ).scalar_one()
    artifact = next(
        (
            item
            for item in run.artifacts
            if item.artifact_type == "batch" and item.name == "batch_cells"
        ),
        None,
    )
    payload = artifact.payload.get("value", {}) if artifact else {}
    cells = payload.get("cells", []) if isinstance(payload, dict) else []
    await db.flush()
    return ResearchBatchResultOut(
        run_id=run.id,
        code_version_id=run.code_version_id,
        output_contract=version.output_contract,
        status=run.status,
        cells=cells if isinstance(cells, list) else [],
        dataset_manifest=run.dataset_manifest,
        progress=read_research_progress(run.id),
    )


@router.post(
    "/runs/{run_id}/rerun", response_model=ResearchRunOut, status_code=status.HTTP_202_ACCEPTED
)
async def rerun(
    run_id: int,
    snapshot: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a new immutable run using an exact snapshot or newly materialized local data."""
    source = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.code_version))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    manifest = (
        dict(source.dataset_manifest)
        if snapshot
        else await _materialize_declared_dataset(
            db,
            {},
            dict(source.run_config),
            lookback=source.code_version.lookback if source.code_version else None,
            user_id=current_user.id,
        )
    )
    run = ResearchRun(
        user_id=current_user.id,
        code_version_id=source.code_version_id,
        run_config=dict(source.run_config),
        dataset_manifest=manifest,
    )
    db.add(run)
    await db.flush()
    enqueue_research_run(run)
    return (
        await db.execute(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.artifacts),
                selectinload(ResearchRun.code_version),
            )
            .where(ResearchRun.id == run.id)
        )
    ).scalar_one()


@router.post("/runs/{run_id}/cancel", response_model=ResearchRunOut)
async def cancel_run(
    run_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    run = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.artifacts))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status in {"completed", "failed", "canceled"}:
        raise HTTPException(
            status_code=409, detail={"code": "research_run_terminal", "status": run.status}
        )
    cancel_research_run(run)
    await db.flush()
    return run
