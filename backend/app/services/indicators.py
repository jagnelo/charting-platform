"""
Backend indicator computation engine.

This is the canonical, authoritative source for all indicator calculations.
The frontend may mirror these for display performance, but the backend
is the source of truth — used by:
  - Alert engine (price + indicator alerts)
  - Screener engine
  - API endpoints that return pre-computed indicator series
  - Bulk historical analysis jobs

All computation functions accept pandas Series or numpy arrays and return
the same length output with NaN where insufficient history exists.

INDICATOR_REGISTRY maps indicator type strings → IndicatorDef.
Adding a new indicator = add one entry here + one computation function.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Data container passed to all indicator functions ─────────────────────────


@dataclass
class OHLCVSeries:
    """Normalised OHLCV data ready for indicator computation."""

    timestamps: np.ndarray  # unix seconds, int64
    opens: np.ndarray  # float64
    highs: np.ndarray  # float64
    lows: np.ndarray  # float64
    closes: np.ndarray  # float64
    volumes: np.ndarray  # float64

    @classmethod
    def from_orm_bars(cls, bars: list) -> "OHLCVSeries":
        if not bars:
            return cls(*[np.array([], dtype=np.float64)] * 6)
        return cls(
            timestamps=np.array([int(b.ts.timestamp()) for b in bars], dtype=np.int64),
            opens=np.array([float(b.open) for b in bars], dtype=np.float64),
            highs=np.array([float(b.high) for b in bars], dtype=np.float64),
            lows=np.array([float(b.low) for b in bars], dtype=np.float64),
            closes=np.array([float(b.close) for b in bars], dtype=np.float64),
            volumes=np.array([float(b.volume or 0) for b in bars], dtype=np.float64),
        )

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts": self.timestamps,
                "open": self.opens,
                "high": self.highs,
                "low": self.lows,
                "close": self.closes,
                "volume": self.volumes,
            }
        )


# ── Parameter definition ─────────────────────────────────────────────────────


@dataclass
class ParamDef:
    name: str
    type: type
    default: Any
    description: str = ""
    min_value: Any = None
    max_value: Any = None


# ── Indicator definition ─────────────────────────────────────────────────────


@dataclass
class IndicatorDef:
    """
    Full definition of an indicator including metadata and computation function.
    An indicator can return one or more named series (e.g. MACD returns macd, signal, histogram).
    """

    type: str  # Registry key, e.g. "rsi"
    label: str  # Human label, e.g. "RSI"
    description: str
    params: list[ParamDef]  # Ordered parameter definitions
    output_keys: list[str]  # Names of output series, e.g. ["rsi"] or ["macd","signal","histogram"]
    pane: str  # "main" (overlay) | "separate" (sub-pane)
    fn: Callable  # (data: OHLCVSeries, **params) → dict[str, np.ndarray]
    default_style: dict = field(default_factory=dict)


# ── Computation functions ─────────────────────────────────────────────────────


def _compute_sma(data: OHLCVSeries, period: int = 20) -> dict:
    s = pd.Series(data.closes)
    return {"sma": s.rolling(window=period, min_periods=period).mean().to_numpy()}


def _compute_ema(data: OHLCVSeries, period: int = 20) -> dict:
    s = pd.Series(data.closes)
    return {"ema": s.ewm(span=period, adjust=False, min_periods=period).mean().to_numpy()}


def _compute_wma(data: OHLCVSeries, period: int = 20) -> dict:
    weights = np.arange(1, period + 1, dtype=np.float64)
    s = pd.Series(data.closes)
    wma = s.rolling(window=period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    return {"wma": wma.to_numpy()}


def _compute_rsi(data: OHLCVSeries, period: int = 14) -> dict:
    s = pd.Series(data.closes)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return {"rsi": rsi.to_numpy()}


def _compute_macd(data: OHLCVSeries, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    s = pd.Series(data.closes)
    ema_fast = s.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = s.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return {
        "macd": macd_line.to_numpy(),
        "signal": signal_line.to_numpy(),
        "histogram": histogram.to_numpy(),
    }


def _compute_bb(data: OHLCVSeries, period: int = 20, std_dev: float = 2.0) -> dict:
    s = pd.Series(data.closes)
    mid = s.rolling(window=period, min_periods=period).mean()
    std = s.rolling(window=period, min_periods=period).std()
    return {
        "bb_upper": (mid + std_dev * std).to_numpy(),
        "bb_mid": mid.to_numpy(),
        "bb_lower": (mid - std_dev * std).to_numpy(),
    }


def _compute_vwap(data: OHLCVSeries, reset_daily: bool = True) -> dict:
    typical = (data.highs + data.lows + data.closes) / 3
    pv = typical * data.volumes
    result = np.full(len(data.closes), np.nan)
    cum_pv = 0.0
    cum_vol = 0.0
    last_day = -1

    for i in range(len(data.closes)):
        day = int(data.timestamps[i] // 86400)
        if reset_daily and day != last_day:
            cum_pv = 0.0
            cum_vol = 0.0
            last_day = day
        cum_pv += pv[i]
        cum_vol += data.volumes[i]
        result[i] = cum_pv / cum_vol if cum_vol > 0 else data.closes[i]

    return {"vwap": result}


def _compute_avwap(data: OHLCVSeries, anchor_timestamp: int = 0) -> dict:
    typical = (data.highs + data.lows + data.closes) / 3
    pv = typical * data.volumes
    result = np.full(len(data.closes), np.nan)
    cum_pv = 0.0
    cum_vol = 0.0
    anchored = False

    for i in range(len(data.closes)):
        if not anchored and data.timestamps[i] >= anchor_timestamp:
            anchored = True
        if not anchored:
            continue
        cum_pv += pv[i]
        cum_vol += data.volumes[i]
        result[i] = cum_pv / cum_vol if cum_vol > 0 else data.closes[i]

    return {"avwap": result}


def _compute_atr(data: OHLCVSeries, period: int = 14) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close_prev = pd.Series(data.closes).shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return {"atr": atr.to_numpy()}


def _compute_stoch(data: OHLCVSeries, k_period: int = 14, d_period: int = 3) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close = pd.Series(data.closes)
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return {"stoch_k": k.to_numpy(), "stoch_d": d.to_numpy()}


def _compute_obv(data: OHLCVSeries) -> dict:
    close = pd.Series(data.closes)
    vol = pd.Series(data.volumes)
    direction = np.sign(close.diff().fillna(0))
    obv = (direction * vol).cumsum()
    return {"obv": obv.to_numpy()}


def _compute_cci(data: OHLCVSeries, period: int = 20) -> dict:
    typical = pd.Series((data.highs + data.lows + data.closes) / 3)
    sma = typical.rolling(window=period, min_periods=period).mean()
    mad = typical.rolling(window=period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    cci = (typical - sma) / (0.015 * mad.replace(0, np.nan))
    return {"cci": cci.to_numpy()}


def _compute_volume(data: OHLCVSeries) -> dict:
    return {"volume": data.volumes.copy()}


def _compute_adx(data: OHLCVSeries, period: int = 14) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close = pd.Series(data.closes)

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    plus_dm = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    return {"adx": adx.to_numpy(), "plus_di": plus_di.to_numpy(), "minus_di": minus_di.to_numpy()}


# ── Registry ──────────────────────────────────────────────────────────────────

INDICATOR_REGISTRY: dict[str, IndicatorDef] = {
    "sma": IndicatorDef(
        type="sma",
        label="SMA",
        pane="main",
        description="Simple Moving Average",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["sma"],
        fn=_compute_sma,
        default_style={"color": "#ffb74d", "lineWidth": 1.5},
    ),
    "ema": IndicatorDef(
        type="ema",
        label="EMA",
        pane="main",
        description="Exponential Moving Average",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["ema"],
        fn=_compute_ema,
        default_style={"color": "#64b5f6", "lineWidth": 1.5},
    ),
    "wma": IndicatorDef(
        type="wma",
        label="WMA",
        pane="main",
        description="Weighted Moving Average",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["wma"],
        fn=_compute_wma,
        default_style={"color": "#a5d6a7", "lineWidth": 1.5},
    ),
    "rsi": IndicatorDef(
        type="rsi",
        label="RSI",
        pane="separate",
        description="Relative Strength Index",
        params=[ParamDef("period", int, 14, "Lookback period", min_value=2)],
        output_keys=["rsi"],
        fn=_compute_rsi,
        default_style={"color": "#ef9a9a", "lineWidth": 1.5},
    ),
    "macd": IndicatorDef(
        type="macd",
        label="MACD",
        pane="separate",
        description="Moving Average Convergence Divergence",
        params=[
            ParamDef("fast", int, 12, "Fast EMA period", min_value=1),
            ParamDef("slow", int, 26, "Slow EMA period", min_value=1),
            ParamDef("signal", int, 9, "Signal EMA period", min_value=1),
        ],
        output_keys=["macd", "signal", "histogram"],
        fn=_compute_macd,
        default_style={"color": "#ce93d8", "lineWidth": 1.5},
    ),
    "bb": IndicatorDef(
        type="bb",
        label="Bollinger Bands",
        pane="main",
        description="Bollinger Bands (SMA ± N standard deviations)",
        params=[
            ParamDef("period", int, 20, "Lookback period", min_value=1),
            ParamDef("std_dev", float, 2.0, "Standard deviations", min_value=0.1),
        ],
        output_keys=["bb_upper", "bb_mid", "bb_lower"],
        fn=_compute_bb,
        default_style={"color": "#80cbc4", "lineWidth": 1},
    ),
    "vwap": IndicatorDef(
        type="vwap",
        label="VWAP",
        pane="main",
        description="Volume Weighted Average Price (resets daily)",
        params=[ParamDef("reset_daily", bool, True, "Reset at session open")],
        output_keys=["vwap"],
        fn=_compute_vwap,
        default_style={"color": "#ce93d8", "lineWidth": 2},
    ),
    "avwap": IndicatorDef(
        type="avwap",
        label="AVWAP",
        pane="main",
        description="Anchored VWAP — accumulates from a user-defined anchor bar",
        params=[ParamDef("anchor_timestamp", int, 0, "Unix timestamp of anchor bar")],
        output_keys=["avwap"],
        fn=_compute_avwap,
        default_style={"color": "#80deea", "lineWidth": 2},
    ),
    "atr": IndicatorDef(
        type="atr",
        label="ATR",
        pane="separate",
        description="Average True Range — measures volatility",
        params=[ParamDef("period", int, 14, "Lookback period", min_value=1)],
        output_keys=["atr"],
        fn=_compute_atr,
        default_style={"color": "#ffcc80", "lineWidth": 1.5},
    ),
    "stoch": IndicatorDef(
        type="stoch",
        label="Stochastic",
        pane="separate",
        description="Stochastic Oscillator (%K and %D)",
        params=[
            ParamDef("k_period", int, 14, "%K period", min_value=1),
            ParamDef("d_period", int, 3, "%D period", min_value=1),
        ],
        output_keys=["stoch_k", "stoch_d"],
        fn=_compute_stoch,
        default_style={"color": "#a5d6a7", "lineWidth": 1.5},
    ),
    "obv": IndicatorDef(
        type="obv",
        label="OBV",
        pane="separate",
        description="On Balance Volume",
        params=[],
        output_keys=["obv"],
        fn=_compute_obv,
        default_style={"color": "#81d4fa", "lineWidth": 1.5},
    ),
    "cci": IndicatorDef(
        type="cci",
        label="CCI",
        pane="separate",
        description="Commodity Channel Index",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["cci"],
        fn=_compute_cci,
        default_style={"color": "#f48fb1", "lineWidth": 1.5},
    ),
    "adx": IndicatorDef(
        type="adx",
        label="ADX",
        pane="separate",
        description="Average Directional Index (trend strength)",
        params=[ParamDef("period", int, 14, "Lookback period", min_value=1)],
        output_keys=["adx", "plus_di", "minus_di"],
        fn=_compute_adx,
        default_style={"color": "#fff59d", "lineWidth": 1.5},
    ),
    "volume": IndicatorDef(
        type="volume",
        label="Volume",
        pane="separate",
        description="Raw volume bars",
        params=[],
        output_keys=["volume"],
        fn=_compute_volume,
        default_style={"color": "#4db6ac", "lineWidth": 1},
    ),
}

# Price field pass-throughs — treated as indicators for alert purposes so that
# alert conditions like "close crosses_above SMA(20)" work uniformly.
# The lambda captures `field` correctly via the default argument trick.
for _field in ("open", "high", "low", "close"):
    INDICATOR_REGISTRY[_field] = IndicatorDef(
        type=_field,
        label=_field.capitalize(),
        pane="main",
        description=f"Raw {_field} price",
        params=[],
        output_keys=[_field],
        fn=lambda series, field=_field, **_: {field: getattr(series, f"{field}s")},
        default_style={"color": "#ffffff", "lineWidth": 1},
    )


# ── Public API ────────────────────────────────────────────────────────────────


def compute_indicator(
    indicator_type: str,
    data: OHLCVSeries,
    params: dict | None = None,
) -> dict[str, np.ndarray]:
    """
    Compute an indicator by type string.
    Returns a dict mapping output_key → numpy array of the same length as data.
    NaN where insufficient history exists.
    Raises KeyError for unknown indicator types.
    """
    if indicator_type not in INDICATOR_REGISTRY:
        raise KeyError(
            f"Unknown indicator: '{indicator_type}'. Available: {list(INDICATOR_REGISTRY)}"
        )

    defn = INDICATOR_REGISTRY[indicator_type]
    resolved_params = {}
    for p in defn.params:
        if params and p.name in params:
            resolved_params[p.name] = p.type(params[p.name])
        else:
            resolved_params[p.name] = p.default

    try:
        return defn.fn(data, **resolved_params)
    except Exception as e:
        logger.error(f"Indicator computation failed for {indicator_type}: {e}")
        empty = np.full(len(data.closes), np.nan)
        return {k: empty.copy() for k in defn.output_keys}


def get_latest_value(
    indicator_type: str,
    data: OHLCVSeries,
    params: dict | None = None,
    output_key: str | None = None,
) -> float | None:
    """
    Return only the most recent non-NaN value of an indicator.
    If output_key is None, returns the first output key's value.
    Used by the alert engine for single-value comparisons.
    """
    result = compute_indicator(indicator_type, data, params)
    key = output_key or list(result.keys())[0]
    series = result[key]
    # Walk back from end to find most recent non-NaN
    for val in reversed(series):
        if not np.isnan(val):
            return float(val)
    return None


def list_indicators() -> list[dict]:
    """Return metadata for all registered indicators (for API / frontend registry sync)."""
    return [
        {
            "type": defn.type,
            "label": defn.label,
            "description": defn.description,
            "pane": defn.pane,
            "output_keys": defn.output_keys,
            "default_style": defn.default_style,
            "params": [
                {
                    "name": p.name,
                    "type": p.type.__name__,
                    "default": p.default,
                    "description": p.description,
                    "min_value": p.min_value,
                    "max_value": p.max_value,
                }
                for p in defn.params
            ],
        }
        for defn in INDICATOR_REGISTRY.values()
    ]
