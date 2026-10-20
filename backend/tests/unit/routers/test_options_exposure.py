from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.providers.errors import ProviderRateLimitError, ProviderResponseError
from app.routers import options_exposure
from app.services.provider_runtime import ProviderNoDataError, ProviderQuotaUnknownError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    [
        ProviderNoDataError("no provider is routable"),
        ProviderRateLimitError("marketdata_app", "daily credits exhausted"),
        ProviderResponseError("marketdata_app", "upstream unavailable"),
        ProviderQuotaUnknownError("provider operation charge is unknown"),
    ],
)
async def test_expiration_endpoint_degrades_to_empty_coverage_on_provider_failure(
    monkeypatch, provider_error
):
    underlying = SimpleNamespace(symbol="SPY")
    monkeypatch.setattr(options_exposure, "_load_underlying", AsyncMock(return_value=underlying))
    monkeypatch.setattr(
        options_exposure,
        "list_exposure_expirations",
        AsyncMock(side_effect=provider_error),
    )

    result = await options_exposure.get_instrument_exposure_expirations(
        "SPY", db=object(), current_user=object()
    )

    assert result == []
