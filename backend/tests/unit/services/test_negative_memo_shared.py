"""Negative memos survive restarts through Redis and degrade without it.

A worker restart used to forget every "no usable data" / "not listed" answer, so
free-tier providers were asked the same questions again. The memo is mirrored in
Redis; an unreachable Redis must only cost extra requests, never a failure.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.models.provider_runtime import ProviderCapability
from app.providers.errors import ProviderResponseError
from app.services import market_data, negative_memo, provider_runtime, tokenized_assets
from app.services.provider_runtime import ProviderNoDataError
from tests.unit.conftest import AsyncSessionAdapter

HISTORICAL_START = datetime(2023, 6, 1, tzinfo=UTC)
CACHED_END = datetime(2024, 5, 29, tzinfo=UTC)


class FakeRedis:
    def __init__(self):
        self.data: dict[str, tuple[bytes, int | None]] = {}

    async def mget(self, keys):
        return [self.data[k][0] if k in self.data else None for k in keys]

    def pipeline(self, transaction=False):
        return _Pipe(self)


class _Pipe:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def set(self, key, value, ex=None):
        self.ops.append((key, value, ex))

    async def execute(self):
        for key, value, ex in self.ops:
            self.redis.data[key] = (value, ex)


class BrokenRedis:
    def __init__(self):
        self.calls = 0

    async def mget(self, keys):
        self.calls += 1
        raise ConnectionError("redis down")

    def pipeline(self, transaction=False):
        self.calls += 1
        raise ConnectionError("redis down")


@pytest.fixture(autouse=True)
def _clear_memos():
    market_data._no_data_slices.clear()
    provider_runtime._provider_negative_memo.clear()
    yield
    market_data._no_data_slices.clear()
    provider_runtime._provider_negative_memo.clear()


def _use_redis(monkeypatch, redis):
    monkeypatch.setattr(negative_memo, "_get_client", lambda: redis)


def _fake_provider(monkeypatch, error):
    calls = []

    async def fetch(_db, _instrument, _timeframe, start, end, _adjusted, **_kwargs):
        calls.append((start, end))
        raise error

    monkeypatch.setattr(market_data, "_fetch_provider", fetch)
    return calls


async def _read(db, instrument):
    return await market_data._fetch_ohlcv_impl(
        AsyncSessionAdapter(db),
        instrument,
        Timeframe.D1,
        HISTORICAL_START,
        end=CACHED_END,
        adjusted=True,
    )


NO_DATA = "alpaca returned no usable data for fetch_ohlcv:D1"


@pytest.mark.asyncio
async def test_no_data_slice_survives_a_restart_via_redis(db, instrument, ohlcv_bars, monkeypatch):
    redis = FakeRedis()
    _use_redis(monkeypatch, redis)
    calls = _fake_provider(monkeypatch, ProviderNoDataError(NO_DATA))

    await _read(db, instrument)
    assert len(calls) == 1
    assert redis.data
    # These slices ended long ago, so they are settled: held a week, in whole minutes.
    settled = int(market_data._NO_DATA_SLICE_SETTLED_TTL.total_seconds())
    ttl = {ex for _value, ex in redis.data.values()}
    assert ttl and all(settled - 60 <= ex <= settled and ex % 60 == 0 for ex in ttl)

    market_data._no_data_slices.clear()  # simulated worker restart
    await _read(db, instrument)
    assert len(calls) == 1
    assert market_data._no_data_slices  # warmed back into the fast layer


@pytest.mark.asyncio
async def test_no_data_slice_memo_degrades_when_redis_is_down(
    db, instrument, ohlcv_bars, monkeypatch
):
    broken = BrokenRedis()
    _use_redis(monkeypatch, broken)
    calls = _fake_provider(monkeypatch, ProviderNoDataError(NO_DATA))

    first = await _read(db, instrument)
    second = await _read(db, instrument)

    assert len(first) == len(second) == len(ohlcv_bars)
    assert len(calls) == 1  # in-process layer still works
    assert broken.calls >= 1
    negative_memo.reset_shared_client()


@pytest.mark.asyncio
async def test_redis_not_consulted_for_recent_or_other_failures(
    db, instrument, ohlcv_bars, monkeypatch
):
    redis = FakeRedis()
    _use_redis(monkeypatch, redis)
    _fake_provider(monkeypatch, RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await _read(db, instrument)
    assert not redis.data


def test_profile_memo_ttl_classification():
    ttl = provider_runtime._negative_memo_ttl
    assert ttl(ProviderResponseError("xstocks", "HTTP 404: Client error '404 Not Found'")) == (
        provider_runtime._NEGATIVE_MEMO_TTL_NOT_LISTED
    )
    assert ttl(ProviderResponseError("finnhub", "Client error '403 Forbidden' for url")) == (
        provider_runtime._NEGATIVE_MEMO_TTL_PLAN_DENIED
    )
    assert ttl(ProviderResponseError("fmp", "x", status_code=402)) == (
        provider_runtime._NEGATIVE_MEMO_TTL_PLAN_DENIED
    )
    assert ttl(ProviderNoDataError("fmp returned no usable data for get_instrument_profile")) == (
        provider_runtime._NEGATIVE_MEMO_TTL_NO_DATA
    )
    assert ttl(ProviderResponseError("x", "Server error '502 Bad Gateway'")) is None
    assert ttl(ProviderResponseError("x", "HTTP 429 slow down")) is None
    assert ttl(ProviderNoDataError("No currently-supported providers available")) is None
    assert ttl(RuntimeError("boom")) is None


@pytest.mark.asyncio
async def test_provider_identity_memo_round_trips_through_redis(monkeypatch):
    redis = FakeRedis()
    _use_redis(monkeypatch, redis)
    cap = ProviderCapability.INSTRUMENT_METADATA
    exc = ProviderResponseError("finnhub", "Client error '403 Forbidden' for url")

    await provider_runtime.remember_provider_identity_missing(
        "finnhub", cap, "get_instrument_profile", "ABCDX", exc
    )
    assert len(redis.data) == 1
    provider_runtime._provider_negative_memo.clear()  # restart

    missing = await provider_runtime.provider_identity_known_missing(
        cap, "get_instrument_profile", ["finnhub", "fmp"], "abcdx"
    )
    assert missing == {"finnhub"}
    # Other operations and unmemoized operations are never skipped.
    assert not await provider_runtime.provider_identity_known_missing(
        cap, "fetch_ohlcv:D1", ["finnhub"], "ABCDX"
    )


@pytest.mark.asyncio
async def test_provider_identity_memo_ignores_redis_outage(monkeypatch):
    _use_redis(monkeypatch, BrokenRedis())
    cap = ProviderCapability.TOKENIZED_ASSETS
    await provider_runtime.remember_provider_identity_missing(
        "xstocks",
        cap,
        "get_tokenized_price",
        "tok-1",
        ProviderResponseError("xstocks", "HTTP 404: Client error '404 Not Found'"),
    )
    assert await provider_runtime.provider_identity_known_missing(
        cap, "get_tokenized_price", ["xstocks"], "tok-1"
    ) == {"xstocks"}
    negative_memo.reset_shared_client()


@pytest.mark.asyncio
async def test_unlisted_token_is_not_requested_again(db, instrument, monkeypatch):
    from app.providers.base import TokenizedAssetRecord
    from app.services.tokenized_assets import refresh_tokenized_prices, upsert_tokenized_asset

    await upsert_tokenized_asset(
        AsyncSessionAdapter(db),
        TokenizedAssetRecord(
            provider="xstocks",
            asset_id="unlisted-1",
            symbol="unlisted-1",
            name="Unlisted",
            underlying_symbol=instrument.symbol,
            raw_payload={"id": "unlisted-1"},
        ),
    )
    calls = []

    async def fake_execute(_db, _capability, _operation, **kwargs):
        calls.append(kwargs["provider_symbol"])
        exc = ProviderResponseError("xstocks", "HTTP 404: Client error '404 Not Found'")
        await provider_runtime.remember_provider_identity_missing(
            "xstocks", _capability, _operation, kwargs["provider_symbol"], exc
        )
        raise exc

    monkeypatch.setattr(tokenized_assets, "execute_provider_call", fake_execute)

    first = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=10)
    second = await refresh_tokenized_prices(AsyncSessionAdapter(db), max_assets=10)

    assert calls == ["unlisted-1"]
    assert first["failed"] == 1
    assert second["failed"] == 0
    assert second["skipped_not_listed"] == 1


@pytest.mark.asyncio
async def test_execute_provider_call_skips_memoized_provider(db, monkeypatch):
    """A remembered miss removes the provider from the chain without a request."""

    cap = ProviderCapability.INSTRUMENT_METADATA
    resolved = [SimpleNamespace(provider_name="finnhub"), SimpleNamespace(provider_name="fmp")]

    async def fake_chain(_db, _capability, **_kwargs):
        return list(resolved)

    monkeypatch.setattr(provider_runtime, "resolve_provider_chain", fake_chain)
    provider_runtime._provider_negative_memo[
        provider_runtime._negative_memo_identity("finnhub", cap, "get_instrument_profile", "ZZZZX")
    ] = datetime.now(UTC) + provider_runtime._NEGATIVE_MEMO_TTL_PLAN_DENIED
    provider_runtime._provider_negative_memo[
        provider_runtime._negative_memo_identity("fmp", cap, "get_instrument_profile", "ZZZZX")
    ] = datetime.now(UTC) + provider_runtime._NEGATIVE_MEMO_TTL_NO_DATA

    with pytest.raises(ProviderNoDataError):
        await provider_runtime.execute_provider_call(
            db,
            cap,
            "get_instrument_profile",
            instrument_id=1,
            provider_symbol="ZZZZX",
            invoke=lambda _provider, _symbol: pytest.fail("provider must not be called"),
        )


async def test_redis_copy_keeps_each_slice_ttl_class(monkeypatch):
    """A settled (long-past) slice is mirrored for a week, a recent one for 12h."""

    redis = FakeRedis()
    _use_redis(monkeypatch, redis)
    market_data._no_data_slices.clear()
    now = datetime.now(UTC)
    recent = ("recent",)
    settled = ("settled",)
    market_data._remember_no_data_slice(recent, end=now - timedelta(days=3), now=now)
    market_data._remember_no_data_slice(settled, end=now - timedelta(days=400), now=now)

    await market_data._persist_no_data_slices([recent, settled])

    ttls = sorted(ex for _value, ex in redis.data.values())
    short = int(market_data._NO_DATA_SLICE_TTL.total_seconds())
    long = int(market_data._NO_DATA_SLICE_SETTLED_TTL.total_seconds())
    assert len(ttls) == 2
    assert short - 60 <= ttls[0] <= short
    assert long - 60 <= ttls[1] <= long
