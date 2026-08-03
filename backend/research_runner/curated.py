"""Curated numerical/research facades exposed to isolated user programs.

The runner deliberately does not expose Python's import machinery or the full
SciPy/statsmodels modules.  These small wrappers provide the useful, pure
numerical subset while keeping module internals, file access, and arbitrary
object graphs outside the user namespace.
"""

from __future__ import annotations

import numpy as _numpy

try:  # Optional locally; the locked runner image installs both packages.
    from scipy import stats as _scipy_stats
except ImportError:  # pragma: no cover - exercised by the lightweight local venv
    _scipy_stats = None

try:  # Optional locally; the locked runner image installs both packages.
    import statsmodels.api as _statsmodels_api
except ImportError:  # pragma: no cover - exercised by the lightweight local venv
    _statsmodels_api = None


def _numeric(values: object) -> _numpy.ndarray:
    array = _numpy.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("curated numerical functions require a non-empty one-dimensional series")
    if not _numpy.isfinite(array).all():
        raise ValueError("curated numerical functions require finite values")
    return array


def _pearson_fallback(left: object, right: object) -> tuple[float, float]:
    x = _numeric(left)
    y = _numeric(right)
    if x.size != y.size or x.size < 2:
        raise ValueError("correlation requires equal-length series with at least two values")
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    denominator = float(_numpy.sqrt(_numpy.sum(x_centered**2) * _numpy.sum(y_centered**2)))
    if denominator == 0:
        raise ValueError("correlation is undefined for a constant series")
    return float(_numpy.sum(x_centered * y_centered) / denominator), float("nan")


class _ScipyStatsFacade:
    """Safe subset of ``scipy.stats`` used by market studies."""

    @staticmethod
    def zscore(values: object) -> object:
        data = _numeric(values)
        if _scipy_stats is not None:
            return _scipy_stats.zscore(data)
        deviation = float(data.std())
        return (data - data.mean()) / deviation if deviation else _numpy.zeros_like(data)

    @staticmethod
    def rankdata(values: object) -> object:
        data = _numeric(values)
        if _scipy_stats is not None:
            return _scipy_stats.rankdata(data)
        order = _numpy.argsort(data, kind="stable")
        ranks = _numpy.empty(data.size, dtype=float)
        ranks[order] = _numpy.arange(1, data.size + 1, dtype=float)
        return ranks

    @staticmethod
    def percentileofscore(values: object, score: float) -> float:
        data = _numeric(values)
        if not isinstance(score, int | float) or isinstance(score, bool):
            raise ValueError("score must be numeric")
        if _scipy_stats is not None:
            return float(_scipy_stats.percentileofscore(data, float(score), kind="weak"))
        return float(_numpy.count_nonzero(data <= float(score)) / data.size * 100)

    @staticmethod
    def pearsonr(left: object, right: object) -> tuple[float, float]:
        if _scipy_stats is not None:
            result = _scipy_stats.pearsonr(_numeric(left), _numeric(right))
            return float(result.statistic), float(result.pvalue)
        return _pearson_fallback(left, right)

    @staticmethod
    def spearmanr(left: object, right: object) -> tuple[float, float]:
        if _scipy_stats is not None:
            result = _scipy_stats.spearmanr(_numeric(left), _numeric(right))
            return float(result.statistic), float(result.pvalue)
        return _pearson_fallback(_ScipyStatsFacade.rankdata(left), _ScipyStatsFacade.rankdata(right))

    @staticmethod
    def linregress(left: object, right: object) -> dict[str, float]:
        x = _numeric(left)
        y = _numeric(right)
        if x.size != y.size or x.size < 2:
            raise ValueError("linear regression requires equal-length series with at least two values")
        if _scipy_stats is not None:
            result = _scipy_stats.linregress(x, y)
            return {
                "slope": float(result.slope),
                "intercept": float(result.intercept),
                "rvalue": float(result.rvalue),
                "pvalue": float(result.pvalue),
                "stderr": float(result.stderr),
            }
        slope, intercept = _numpy.polyfit(x, y, 1)
        correlation, _ = _pearson_fallback(x, y)
        return {
            "slope": float(slope),
            "intercept": float(intercept),
            "rvalue": correlation,
            "pvalue": float("nan"),
            "stderr": float("nan"),
        }


class _ScipyFacade:
    stats = _ScipyStatsFacade()


class _OLSResult:
    def __init__(self, result: object) -> None:
        self._result = result

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError("private regression result attributes are unavailable")
        return object.__getattribute__(self, name)

    @property
    def params(self) -> list[float]:
        return _numeric(object.__getattribute__(self, "_result").params).tolist()

    @property
    def fittedvalues(self) -> list[float]:
        return _numeric(object.__getattribute__(self, "_result").fittedvalues).tolist()

    @property
    def resid(self) -> list[float]:
        return _numeric(object.__getattribute__(self, "_result").resid).tolist()

    @property
    def rsquared(self) -> float:
        return float(object.__getattribute__(self, "_result").rsquared)

    @property
    def bse(self) -> list[float]:
        return _numeric(object.__getattribute__(self, "_result").bse).tolist()

    @property
    def pvalues(self) -> list[float]:
        return _numeric(object.__getattribute__(self, "_result").pvalues).tolist()


class _OLSModel:
    def __init__(self, endog: object, exog: object) -> None:
        self._endog = _numeric(endog)
        self._exog = _numpy.asarray(exog, dtype=float)
        matrix = object.__getattribute__(self, "_exog")
        target = object.__getattribute__(self, "_endog")
        if matrix.ndim != 2 or matrix.shape[0] != target.size or matrix.shape[1] == 0:
            raise ValueError("OLS exog must be a non-empty two-dimensional matrix matching endog")
        if not _numpy.isfinite(matrix).all():
            raise ValueError("OLS exog must contain finite values")

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError("private regression model attributes are unavailable")
        return object.__getattribute__(self, name)

    def fit(self) -> _OLSResult:
        endog = object.__getattribute__(self, "_endog")
        exog = object.__getattribute__(self, "_exog")
        if _statsmodels_api is not None:
            return _OLSResult(_statsmodels_api.OLS(endog, exog).fit())
        params, _, _, _ = _numpy.linalg.lstsq(exog, endog, rcond=None)
        fitted = exog @ params
        residuals = endog - fitted
        total = float(_numpy.sum((endog - endog.mean()) ** 2))
        rsquared = 1.0 - float(_numpy.sum(residuals**2)) / total if total else 0.0
        return _OLSResult(
            _FallbackOLSResult(
                params=params,
                fittedvalues=fitted,
                resid=residuals,
                rsquared=rsquared,
                bse=_numpy.full(params.shape, float("nan")),
                pvalues=_numpy.full(params.shape, float("nan")),
            )
        )


class _FallbackOLSResult:
    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)


class _StatsmodelsApiFacade:
    OLS = _OLSModel


class _StatsmodelsFacade:
    api = _StatsmodelsApiFacade()


SCIPY = _ScipyFacade()
STATSMODELS = _StatsmodelsFacade()
