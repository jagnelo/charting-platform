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
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
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


def _compute_stoch(data: OHLCVSeries, k_period: int = 14, d_period: int = 3, smooth_k: int = 3) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close = pd.Series(data.closes)
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    k = raw_k.rolling(window=smooth_k, min_periods=smooth_k).mean() if smooth_k > 1 else raw_k
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


def _compute_volume_ratio(data: OHLCVSeries, period: int = 20) -> dict:
    vol = pd.Series(data.volumes)
    avg = vol.rolling(window=period, min_periods=period).mean()
    ratio = vol / avg.replace(0, np.nan)
    return {"volume_ratio": ratio.to_numpy()}


def _compute_ichimoku(
    data: OHLCVSeries,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
    displacement: int = 26,
) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close = pd.Series(data.closes)

    def _midpoint(highs: pd.Series, lows: pd.Series, period: int) -> pd.Series:
        return (
            highs.rolling(period, min_periods=period).max()
            + lows.rolling(period, min_periods=period).min()
        ) / 2

    tenkan_sen = _midpoint(high, low, tenkan)
    kijun_sen = _midpoint(high, low, kijun)
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(displacement)
    senkou_b_line = _midpoint(high, low, senkou_b).shift(displacement)
    chikou = close.shift(-displacement)

    return {
        "ichimoku_tenkan": tenkan_sen.to_numpy(),
        "ichimoku_kijun": kijun_sen.to_numpy(),
        "ichimoku_senkou_a": senkou_a.to_numpy(),
        "ichimoku_senkou_b": senkou_b_line.to_numpy(),
        "ichimoku_chikou": chikou.to_numpy(),
    }


def _compute_psar(data: OHLCVSeries, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2) -> dict:
    high = data.highs
    low = data.lows
    n = len(high)
    psar = np.full(n, np.nan)
    if n < 2:
        return {"psar": psar}

    # Initialise: assume uptrend
    bull = True
    ep = high[0]  # extreme point
    af = af_start
    psar[0] = low[0]

    for i in range(1, n):
        prev_psar = psar[i - 1]
        if bull:
            psar[i] = prev_psar + af * (ep - prev_psar)
            # SAR must be below prior two lows
            if i >= 2:
                psar[i] = min(psar[i], low[i - 1], low[i - 2])
            if low[i] < psar[i]:
                # Reversal to bearish
                bull = False
                psar[i] = ep
                ep = low[i]
                af = af_start
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_step, af_max)
        else:
            psar[i] = prev_psar + af * (ep - prev_psar)
            # SAR must be above prior two highs
            if i >= 2:
                psar[i] = max(psar[i], high[i - 1], high[i - 2])
            if high[i] > psar[i]:
                # Reversal to bullish
                bull = True
                psar[i] = ep
                ep = high[i]
                af = af_start
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_step, af_max)

    return {"psar": psar}


def _compute_donchian(data: OHLCVSeries, period: int = 20) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    upper = high.rolling(window=period, min_periods=period).max()
    lower = low.rolling(window=period, min_periods=period).min()
    mid = (upper + lower) / 2
    return {
        "donchian_upper": upper.to_numpy(),
        "donchian_mid": mid.to_numpy(),
        "donchian_lower": lower.to_numpy(),
    }


def _compute_keltner(data: OHLCVSeries, period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> dict:
    close = pd.Series(data.closes)
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    mid = close.ewm(span=period, adjust=False, min_periods=period).mean()
    # ATR via EWM (same as _compute_atr)
    close_prev = close.shift(1)
    tr = pd.concat([(high - low), (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / atr_period, adjust=False, min_periods=atr_period).mean()
    return {
        "keltner_upper": (mid + multiplier * atr).to_numpy(),
        "keltner_mid": mid.to_numpy(),
        "keltner_lower": (mid - multiplier * atr).to_numpy(),
    }


def _compute_williams_r(data: OHLCVSeries, period: int = 14) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close = pd.Series(data.closes)
    hh = high.rolling(window=period, min_periods=period).max()
    ll = low.rolling(window=period, min_periods=period).min()
    wr = -100 * (hh - close) / (hh - ll).replace(0, np.nan)
    return {"williams_r": wr.to_numpy()}


def _compute_hma(data: OHLCVSeries, period: int = 20) -> dict:
    close = pd.Series(data.closes)
    weights_half = np.arange(1, period // 2 + 1, dtype=np.float64)
    weights_full = np.arange(1, period + 1, dtype=np.float64)
    sqrt_period = int(np.sqrt(period))
    weights_sqrt = np.arange(1, sqrt_period + 1, dtype=np.float64)

    def _wma(s: pd.Series, w: np.ndarray) -> pd.Series:
        p = len(w)
        return s.rolling(window=p).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

    wma_half = _wma(close, weights_half)
    wma_full = _wma(close, weights_full)
    raw = 2 * wma_half - wma_full
    hma = _wma(raw, weights_sqrt)
    return {"hma": hma.to_numpy()}


def _compute_aroon(data: OHLCVSeries, period: int = 25) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    aroon_up = high.rolling(window=period + 1, min_periods=period + 1).apply(
        lambda x: ((period - (period - np.argmax(x))) / period) * 100, raw=True
    )
    aroon_down = low.rolling(window=period + 1, min_periods=period + 1).apply(
        lambda x: ((period - (period - np.argmin(x))) / period) * 100, raw=True
    )
    aroon_osc = aroon_up - aroon_down
    return {
        "aroon_up": aroon_up.to_numpy(),
        "aroon_down": aroon_down.to_numpy(),
        "aroon_osc": aroon_osc.to_numpy(),
    }


def _compute_mfi(data: OHLCVSeries, period: int = 14) -> dict:
    typical = pd.Series((data.highs + data.lows + data.closes) / 3)
    vol = pd.Series(data.volumes)
    money_flow = typical * vol
    tp_diff = typical.diff()

    pos_flow = money_flow.where(tp_diff > 0, 0.0)
    neg_flow = money_flow.where(tp_diff < 0, 0.0)

    pos_sum = pos_flow.rolling(window=period, min_periods=period).sum()
    neg_sum = neg_flow.rolling(window=period, min_periods=period).sum().abs()

    mfr = pos_sum / neg_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mfr))
    return {"mfi": mfi.to_numpy()}


def _compute_roc(data: OHLCVSeries, period: int = 10) -> dict:
    close = pd.Series(data.closes)
    roc = ((close - close.shift(period)) / close.shift(period).replace(0, np.nan)) * 100
    return {"roc": roc.to_numpy()}


def _compute_momentum(data: OHLCVSeries, period: int = 10) -> dict:
    close = pd.Series(data.closes)
    mom = close - close.shift(period)
    return {"momentum": mom.to_numpy()}


def _compute_stddev(data: OHLCVSeries, period: int = 20) -> dict:
    close = pd.Series(data.closes)
    std = close.rolling(window=period, min_periods=period).std()
    return {"stddev": std.to_numpy()}


def _compute_pivot_points(data: OHLCVSeries, method: str = "classic") -> dict:
    """
    Compute daily pivot points using the prior bar's H/L/C.
    Returns PP, R1-R3, S1-S3 (or equivalent Fibonacci/Camarilla levels).
    Values are projected forward until the next pivot bar.
    """
    high = data.highs
    low = data.lows
    close = data.closes
    n = len(close)

    pp = np.full(n, np.nan)
    r1 = np.full(n, np.nan)
    r2 = np.full(n, np.nan)
    r3 = np.full(n, np.nan)
    s1 = np.full(n, np.nan)
    s2 = np.full(n, np.nan)
    s3 = np.full(n, np.nan)

    for i in range(1, n):
        h, lo, c = float(high[i - 1]), float(low[i - 1]), float(close[i - 1])
        pivot = (h + lo + c) / 3
        rng = h - lo

        if method == "fibonacci":
            pp[i] = pivot
            r1[i] = pivot + 0.382 * rng
            r2[i] = pivot + 0.618 * rng
            r3[i] = pivot + 1.000 * rng
            s1[i] = pivot - 0.382 * rng
            s2[i] = pivot - 0.618 * rng
            s3[i] = pivot - 1.000 * rng
        elif method == "camarilla":
            pp[i] = pivot
            r1[i] = c + rng * 1.1 / 12
            r2[i] = c + rng * 1.1 / 6
            r3[i] = c + rng * 1.1 / 4
            s1[i] = c - rng * 1.1 / 12
            s2[i] = c - rng * 1.1 / 6
            s3[i] = c - rng * 1.1 / 4
        else:  # classic
            pp[i] = pivot
            r1[i] = 2 * pivot - lo
            r2[i] = pivot + rng
            r3[i] = h + 2 * (pivot - lo)
            s1[i] = 2 * pivot - h
            s2[i] = pivot - rng
            s3[i] = lo - 2 * (h - pivot)

    return {"pp": pp, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}


def _compute_cmf(data: OHLCVSeries, period: int = 20) -> dict:
    high = pd.Series(data.highs)
    low = pd.Series(data.lows)
    close = pd.Series(data.closes)
    vol = pd.Series(data.volumes)

    clv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    mf_vol = clv * vol

    cmf = (
        mf_vol.rolling(window=period, min_periods=period).sum()
        / vol.rolling(window=period, min_periods=period).sum().replace(0, np.nan)
    )
    return {"cmf": cmf.to_numpy()}


def _compute_dema(data: OHLCVSeries, period: int = 20) -> dict:
    close = pd.Series(data.closes)
    ema1 = close.ewm(span=period, adjust=False, min_periods=period).mean()
    ema2 = ema1.ewm(span=period, adjust=False, min_periods=period).mean()
    dema = 2 * ema1 - ema2
    return {"dema": dema.to_numpy()}


def _compute_tema(data: OHLCVSeries, period: int = 20) -> dict:
    close = pd.Series(data.closes)
    ema1 = close.ewm(span=period, adjust=False, min_periods=period).mean()
    ema2 = ema1.ewm(span=period, adjust=False, min_periods=period).mean()
    ema3 = ema2.ewm(span=period, adjust=False, min_periods=period).mean()
    tema = 3 * ema1 - 3 * ema2 + ema3
    return {"tema": tema.to_numpy()}


def _compute_trix(data: OHLCVSeries, period: int = 15) -> dict:
    close = pd.Series(data.closes)
    ema1 = close.ewm(span=period, adjust=False, min_periods=period).mean()
    ema2 = ema1.ewm(span=period, adjust=False, min_periods=period).mean()
    ema3 = ema2.ewm(span=period, adjust=False, min_periods=period).mean()
    trix = ema3.pct_change() * 100
    return {"trix": trix.to_numpy()}


def _compute_ppo(data: OHLCVSeries, fast: int = 12, slow: int = 26) -> dict:
    close = pd.Series(data.closes)
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    ppo = 100 * (ema_fast - ema_slow) / ema_slow.replace(0, np.nan)
    return {"ppo": ppo.to_numpy()}


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
            ParamDef("smooth_k", int, 3, "%K smoothing", min_value=1),
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
    "volume_ratio": IndicatorDef(
        type="volume_ratio",
        label="Volume Spike Ratio",
        pane="separate",
        description="Current volume divided by rolling average volume",
        params=[ParamDef("period", int, 20, "Average volume lookback", min_value=1)],
        output_keys=["volume_ratio"],
        fn=_compute_volume_ratio,
        default_style={"color": "#4db6ac", "lineWidth": 1.5},
    ),
    "ichimoku": IndicatorDef(
        type="ichimoku",
        label="Ichimoku Cloud",
        pane="main",
        description="Ichimoku Kinko Hyo — Tenkan, Kijun, Senkou A/B, Chikou",
        params=[
            ParamDef("tenkan", int, 9, "Tenkan-sen (conversion) period", min_value=1),
            ParamDef("kijun", int, 26, "Kijun-sen (base) period", min_value=1),
            ParamDef("senkou_b", int, 52, "Senkou Span B period", min_value=1),
            ParamDef("displacement", int, 26, "Cloud displacement (forward shift)", min_value=1),
        ],
        output_keys=["ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a", "ichimoku_senkou_b", "ichimoku_chikou"],
        fn=_compute_ichimoku,
        default_style={"color": "#80cbc4", "lineWidth": 1.5},
    ),
    "psar": IndicatorDef(
        type="psar",
        label="Parabolic SAR",
        pane="main",
        description="Parabolic Stop and Reverse — trend-following indicator plotted as dots",
        params=[
            ParamDef("af_start", float, 0.02, "Initial acceleration factor", min_value=0.001, max_value=1.0),
            ParamDef("af_step", float, 0.02, "Acceleration factor step", min_value=0.001, max_value=1.0),
            ParamDef("af_max", float, 0.2, "Maximum acceleration factor", min_value=0.01, max_value=1.0),
        ],
        output_keys=["psar"],
        fn=_compute_psar,
        default_style={"color": "#ef9a9a", "lineWidth": 1},
    ),
    "donchian": IndicatorDef(
        type="donchian",
        label="Donchian Channels",
        pane="main",
        description="Donchian Channels — highest high / lowest low over a period",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["donchian_upper", "donchian_mid", "donchian_lower"],
        fn=_compute_donchian,
        default_style={"color": "#80deea", "lineWidth": 1},
    ),
    "keltner": IndicatorDef(
        type="keltner",
        label="Keltner Channels",
        pane="main",
        description="Keltner Channels — EMA ± ATR multiplier",
        params=[
            ParamDef("period", int, 20, "EMA period", min_value=1),
            ParamDef("atr_period", int, 10, "ATR period", min_value=1),
            ParamDef("multiplier", float, 2.0, "ATR multiplier", min_value=0.1),
        ],
        output_keys=["keltner_upper", "keltner_mid", "keltner_lower"],
        fn=_compute_keltner,
        default_style={"color": "#ce93d8", "lineWidth": 1},
    ),
    "williams_r": IndicatorDef(
        type="williams_r",
        label="Williams %R",
        pane="separate",
        description="Williams Percent Range — momentum oscillator (range: -100 to 0)",
        params=[ParamDef("period", int, 14, "Lookback period", min_value=1)],
        output_keys=["williams_r"],
        fn=_compute_williams_r,
        default_style={"color": "#ffcc80", "lineWidth": 1.5},
    ),
    "hma": IndicatorDef(
        type="hma",
        label="HMA",
        pane="main",
        description="Hull Moving Average — fast and smooth MA using WMA",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=4)],
        output_keys=["hma"],
        fn=_compute_hma,
        default_style={"color": "#a5d6a7", "lineWidth": 1.5},
    ),
    "aroon": IndicatorDef(
        type="aroon",
        label="Aroon",
        pane="separate",
        description="Aroon Up/Down/Oscillator — identifies trend changes and strength",
        params=[ParamDef("period", int, 25, "Lookback period", min_value=1)],
        output_keys=["aroon_up", "aroon_down", "aroon_osc"],
        fn=_compute_aroon,
        default_style={"color": "#81d4fa", "lineWidth": 1.5},
    ),
    "mfi": IndicatorDef(
        type="mfi",
        label="MFI",
        pane="separate",
        description="Money Flow Index — volume-weighted RSI (range: 0 to 100)",
        params=[ParamDef("period", int, 14, "Lookback period", min_value=2)],
        output_keys=["mfi"],
        fn=_compute_mfi,
        default_style={"color": "#f48fb1", "lineWidth": 1.5},
    ),
    "roc": IndicatorDef(
        type="roc",
        label="ROC",
        pane="separate",
        description="Rate of Change — percentage change over N periods",
        params=[ParamDef("period", int, 10, "Lookback period", min_value=1)],
        output_keys=["roc"],
        fn=_compute_roc,
        default_style={"color": "#ffb74d", "lineWidth": 1.5},
    ),
    "momentum": IndicatorDef(
        type="momentum",
        label="Momentum",
        pane="separate",
        description="Momentum — price difference over N periods",
        params=[ParamDef("period", int, 10, "Lookback period", min_value=1)],
        output_keys=["momentum"],
        fn=_compute_momentum,
        default_style={"color": "#b39ddb", "lineWidth": 1.5},
    ),
    "stddev": IndicatorDef(
        type="stddev",
        label="Std Dev",
        pane="separate",
        description="Standard Deviation of closing price over N periods",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=2)],
        output_keys=["stddev"],
        fn=_compute_stddev,
        default_style={"color": "#fff59d", "lineWidth": 1.5},
    ),
    "pivot_points": IndicatorDef(
        type="pivot_points",
        label="Pivot Points",
        pane="main",
        description="Pivot Points — support/resistance levels (Classic, Fibonacci, or Camarilla)",
        params=[
            ParamDef("method", str, "classic", "Method: classic | fibonacci | camarilla"),
        ],
        output_keys=["pp", "r1", "r2", "r3", "s1", "s2", "s3"],
        fn=_compute_pivot_points,
        default_style={"color": "#80cbc4", "lineWidth": 1},
    ),
    "cmf": IndicatorDef(
        type="cmf",
        label="CMF",
        pane="separate",
        description="Chaikin Money Flow — volume-weighted momentum oscillator",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["cmf"],
        fn=_compute_cmf,
        default_style={"color": "#80deea", "lineWidth": 1.5},
    ),
    "dema": IndicatorDef(
        type="dema",
        label="DEMA",
        pane="main",
        description="Double Exponential Moving Average — reduced lag EMA",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["dema"],
        fn=_compute_dema,
        default_style={"color": "#ffb74d", "lineWidth": 1.5},
    ),
    "tema": IndicatorDef(
        type="tema",
        label="TEMA",
        pane="main",
        description="Triple Exponential Moving Average — further reduced lag",
        params=[ParamDef("period", int, 20, "Lookback period", min_value=1)],
        output_keys=["tema"],
        fn=_compute_tema,
        default_style={"color": "#f48fb1", "lineWidth": 1.5},
    ),
    "trix": IndicatorDef(
        type="trix",
        label="TRIX",
        pane="separate",
        description="Triple Smoothed EMA ROC — filters noise, shows trend momentum",
        params=[ParamDef("period", int, 15, "Lookback period", min_value=1)],
        output_keys=["trix"],
        fn=_compute_trix,
        default_style={"color": "#a5d6a7", "lineWidth": 1.5},
    ),
    "ppo": IndicatorDef(
        type="ppo",
        label="PPO",
        pane="separate",
        description="Percentage Price Oscillator — like MACD but expressed as percentage",
        params=[
            ParamDef("fast", int, 12, "Fast EMA period", min_value=1),
            ParamDef("slow", int, 26, "Slow EMA period", min_value=1),
        ],
        output_keys=["ppo"],
        fn=_compute_ppo,
        default_style={"color": "#ce93d8", "lineWidth": 1.5},
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

_PARAM_ALIASES = {
    "anchorTime": "anchor_timestamp",
    "stdDev": "std_dev",
    "atrPeriod": "atr_period",
    "senkouB": "senkou_b",
    "afStart": "af_start",
    "afStep": "af_step",
    "afMax": "af_max",
    "smoothK": "smooth_k",
    "smoothD": "d_period",
}


def normalize_indicator_params(indicator_type: str, params: dict | None = None) -> dict:
    """Accept legacy/camelCase frontend keys while keeping registry params snake_case."""
    if not params:
        return {}

    normalized = {}
    for key, value in params.items():
        next_key = _PARAM_ALIASES.get(key, key)
        if indicator_type == "bb" and key == "multiplier":
            next_key = "std_dev"
        normalized[next_key] = value

    if indicator_type == "stoch" and "period" in normalized and "k_period" not in normalized:
        normalized["k_period"] = normalized["period"]

    return normalized


def _coerce_series(data: OHLCVSeries | list) -> OHLCVSeries:
    if isinstance(data, OHLCVSeries):
        return data
    return OHLCVSeries.from_orm_bars(data)


def compute_indicator(
    indicator_type: str,
    data: OHLCVSeries | list,
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

    series = _coerce_series(data)
    defn = INDICATOR_REGISTRY[indicator_type]
    params = normalize_indicator_params(indicator_type, params)
    resolved_params = {}
    try:
        for p in defn.params:
            if params and p.name in params:
                resolved_params[p.name] = p.type(params[p.name])
            else:
                resolved_params[p.name] = p.default
        return defn.fn(series, **resolved_params)
    except Exception as e:
        logger.error(f"Indicator computation failed for {indicator_type}: {e}")
        empty = np.full(len(series.closes), np.nan)
        return {k: empty.copy() for k in defn.output_keys}


def get_latest_value(
    indicator_type: str,
    data: OHLCVSeries | list,
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


def get_last_value(
    indicator_type: str,
    data: OHLCVSeries | list,
    params: dict | None = None,
    output_key: str | None = None,
) -> float | None:
    """Backward-compatible alias for older callers/tests."""
    return get_latest_value(indicator_type, data, params, output_key)


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
