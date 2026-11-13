"""Missing or deleted baskets must answer 404, not 500, on synthetic history reads."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.ohlcv import Timeframe
from app.routers import baskets as baskets_router
from app.services import baskets as basket_service
from app.services.baskets import BasketNotFoundError, BasketValidationError


def _client(monkeypatch, *, pre_check_finds_basket: bool) -> TestClient:
    async def fake_get_basket(db, basket_id, user_id):
        return SimpleNamespace(id=basket_id) if pre_check_finds_basket else None

    async def fake_get_db():
        yield None

    async def fake_get_current_user():
        return SimpleNamespace(id=1)

    async def fake_series(*args, **kwargs):
        raise BasketNotFoundError("Basket not found.")

    monkeypatch.setattr(baskets_router, "get_basket", fake_get_basket)
    monkeypatch.setattr(baskets_router, "get_basket_synthetic_ohlcv", fake_series)

    app = FastAPI()
    app.include_router(baskets_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[get_current_user] = fake_get_current_user
    return TestClient(app)


def test_ohlcv_read_maps_basket_deleted_during_request_to_404(monkeypatch):
    client = _client(monkeypatch, pre_check_finds_basket=True)

    response = client.get("/api/v1/baskets/30/ohlcv/D1?adjusted=true&limit=500")

    assert response.status_code == 404
    assert response.json()["detail"] == "Basket not found."


def test_ohlcv_read_for_unknown_basket_returns_404_before_series(monkeypatch):
    client = _client(monkeypatch, pre_check_finds_basket=False)

    response = client.get("/api/v1/baskets/999/ohlcv/D1")

    assert response.status_code == 404
    assert response.json()["detail"] == "Basket not found"


def test_service_raises_not_found_subclass_for_missing_basket(monkeypatch):
    async def fake_get_basket(db, basket_id, user_id):
        return None

    monkeypatch.setattr(basket_service, "get_basket", fake_get_basket)

    with pytest.raises(BasketNotFoundError) as excinfo:
        asyncio.run(basket_service.get_basket_synthetic_ohlcv(None, 30, 1, Timeframe.D1))

    assert isinstance(excinfo.value, BasketValidationError)
    assert str(excinfo.value) == "Basket not found."
