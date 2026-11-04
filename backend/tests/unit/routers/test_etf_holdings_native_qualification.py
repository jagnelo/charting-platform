from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import etf_holdings
from app.services.etf_issuer_catalog import IssuerCatalogError
from app.services.provider_runtime import ProviderNoDataError


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _QualificationDB:
    def __init__(self, profile, job=None):
        self.results = [_Result(profile), _Result(job)]

    async def execute(self, _statement):
        return self.results.pop(0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_error",
    [
        IssuerCatalogError("ambiguous issuer catalog"),
        ProviderNoDataError("no supported holdings source returned data"),
    ],
)
async def test_expected_native_source_failure_returns_durable_typed_job(monkeypatch, source_error):
    profile = SimpleNamespace(id=82)
    job = SimpleNamespace(
        id=2,
        status="failed",
        failure_reason="Native issuer catalog did not prove this fund.",
    )
    db = _QualificationDB(profile, job)
    monkeypatch.setattr(
        etf_holdings,
        "qualify_native_etf_fund",
        AsyncMock(side_effect=source_error),
    )

    with pytest.raises(HTTPException) as raised:
        await etf_holdings.qualify_initial_native_etf_fund(
            "IGV", db=db, current_user=SimpleNamespace(id=7)
        )

    assert raised.value.status_code == 409
    assert raised.value.detail == {
        "code": "native_qualification_not_qualified",
        "outcome": "not_qualified",
        "job_id": 2,
        "job_status": "failed",
        "reason": "Native issuer catalog did not prove this fund.",
    }


@pytest.mark.asyncio
async def test_expected_native_source_failure_without_terminal_job_is_unavailable(monkeypatch):
    db = _QualificationDB(SimpleNamespace(id=82), None)
    monkeypatch.setattr(
        etf_holdings,
        "qualify_native_etf_fund",
        AsyncMock(side_effect=ProviderNoDataError("no adapter")),
    )

    with pytest.raises(HTTPException) as raised:
        await etf_holdings.qualify_initial_native_etf_fund(
            "IGV", db=db, current_user=SimpleNamespace(id=7)
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "native_qualification_unavailable",
        "outcome": "unavailable",
        "reason": "The native source did not provide qualifying holdings evidence.",
    }


@pytest.mark.asyncio
async def test_expected_native_source_cancellation_returns_cancelled_job(monkeypatch):
    job = SimpleNamespace(id=3, status="cancelled", failure_reason="Operator cancelled.")
    db = _QualificationDB(SimpleNamespace(id=82), job)
    monkeypatch.setattr(
        etf_holdings,
        "qualify_native_etf_fund",
        AsyncMock(side_effect=ProviderNoDataError("source interrupted")),
    )

    with pytest.raises(HTTPException) as raised:
        await etf_holdings.qualify_initial_native_etf_fund(
            "IGV", db=db, current_user=SimpleNamespace(id=7)
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "native_qualification_cancelled"
    assert raised.value.detail["outcome"] == "cancelled"
    assert raised.value.detail["job_id"] == 3
    assert raised.value.detail["reason"] == "Operator cancelled."


@pytest.mark.asyncio
async def test_unexpected_native_qualification_programming_error_is_not_hidden(monkeypatch):
    db = _QualificationDB(SimpleNamespace(id=82))
    monkeypatch.setattr(
        etf_holdings,
        "qualify_native_etf_fund",
        AsyncMock(side_effect=RuntimeError("unexpected parser bug")),
    )

    with pytest.raises(RuntimeError, match="unexpected parser bug"):
        await etf_holdings.qualify_initial_native_etf_fund(
            "IGV", db=db, current_user=SimpleNamespace(id=7)
        )
