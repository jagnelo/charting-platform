from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.providers.base import IdentifierRecord, InstrumentProfile, ListingRecord

logger = logging.getLogger(__name__)

_OPENFIGI_ID_TYPES = {
    "isin": "ID_ISIN",
    "cusip": "ID_CUSIP",
    "sedol": "ID_SEDOL",
    "ticker": "TICKER",
}


class OpenFigiProvider:
    name = "openfigi"
    base_url = "https://api.openfigi.com"
    description = "OpenFIGI mapping API for stable instrument identifiers"

    def fetch_stable_identifiers(
        self,
        symbol: str,
        *,
        exchange_code: str | None = None,
        security_type: str | None = None,
    ) -> list[IdentifierRecord]:
        """Map a ticker only when the returned venue/type evidence is unambiguous."""

        ticker = str(symbol or "").strip().upper()
        if not ticker:
            return []
        results = self._mapping_results(
            [{"idType": _OPENFIGI_ID_TYPES["ticker"], "idValue": ticker}]
        )
        if not results:
            return []
        rows = [row for row in results[0] if isinstance(row, dict)]
        if exchange_code:
            expected_exchange = str(exchange_code).strip().upper()
            rows = [row for row in rows if str(row.get("exchCode") or "").upper() == expected_exchange]
        if security_type:
            expected_type = str(security_type).strip().upper()
            rows = [row for row in rows if str(row.get("securityType") or "").upper() == expected_type]
        if len(rows) != 1:
            return []
        return self._identifier_records_from_mapping(rows[0])

    def resolve_instrument_profile(
        self,
        *,
        isin: str | None = None,
        cusip: str | None = None,
        sedol: str | None = None,
    ) -> InstrumentProfile | None:
        requests_payload: list[dict[str, str]] = []
        identifier_values: list[tuple[str, str]] = []
        for identifier_type, identifier_value in (
            ("isin", isin),
            ("cusip", cusip),
            ("sedol", sedol),
        ):
            normalized = str(identifier_value or "").strip().upper()
            if not normalized:
                continue
            requests_payload.append(
                {
                    "idType": _OPENFIGI_ID_TYPES[identifier_type],
                    "idValue": normalized,
                }
            )
            identifier_values.append((identifier_type, normalized))

        if not requests_payload:
            return None

        responses = self._mapping_results(requests_payload)

        for index, mapping_rows in enumerate(responses):
            if not mapping_rows:
                continue
            profile = self._instrument_profile_from_mapping(
                mapping_rows[0],
                identifier_values[index][0],
                identifier_values[index][1],
            )
            if profile is not None:
                return profile
        return None

    def _mapping_results(self, payload: list[dict[str, str]]) -> list[list[dict[str, Any]]]:
        headers = {"Content-Type": "application/json"}
        if settings.OPENFIGI_API_KEY:
            headers["X-OPENFIGI-APIKEY"] = settings.OPENFIGI_API_KEY

        with httpx.Client(timeout=settings.OPENFIGI_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{self.base_url}/v3/mapping",
                json=payload,
                headers=headers,
            )
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        elif getattr(response, "status_code", 200) != 200:
            return []

        raw_payload = response.json()
        if isinstance(raw_payload, dict):
            raw_payload = [raw_payload]
        if not raw_payload or not isinstance(raw_payload, list):
            return []
        return [item.get("data") or [] for item in raw_payload if isinstance(item, dict)]

    def _identifier_records_from_mapping(
        self,
        mapping_row: dict[str, Any],
        *,
        include_ticker_identity: bool = False,
        original_identifier_type: str | None = None,
        original_identifier_value: str | None = None,
    ) -> list[IdentifierRecord]:
        identifiers: list[IdentifierRecord] = []
        composite_figi = mapping_row.get("compositeFIGI")
        figi = mapping_row.get("figi")
        share_class_figi = mapping_row.get("shareClassFIGI")
        ticker = mapping_row.get("ticker")
        exch_code = mapping_row.get("exchCode")

        if composite_figi:
            identifiers.append(
                IdentifierRecord(
                    identifier_type="COMPOSITE_FIGI",
                    identifier_value=str(composite_figi),
                    is_primary=True,
                    source=self.name,
                    extra_data={
                        "ticker": ticker,
                        "exchange_code": exch_code,
                        "security_type": mapping_row.get("securityType"),
                        "market_sector": mapping_row.get("marketSector"),
                    },
                )
            )
        if figi:
            identifiers.append(
                IdentifierRecord(
                    identifier_type="FIGI",
                    identifier_value=str(figi),
                    source=self.name,
                    extra_data={
                        "ticker": ticker,
                        "exchange_code": exch_code,
                        "name": mapping_row.get("name"),
                        "share_class_figi": share_class_figi,
                    },
                )
            )
        if share_class_figi:
            identifiers.append(
                IdentifierRecord(
                    identifier_type="FIGI",
                    identifier_value=str(share_class_figi),
                    source=self.name,
                    extra_data={"kind": "share_class_figi"},
                )
            )
        if original_identifier_type and original_identifier_value:
            identifiers.append(
                IdentifierRecord(
                    identifier_type=original_identifier_type.upper(),
                    identifier_value=str(original_identifier_value).strip().upper(),
                    source=self.name,
                )
            )
        if include_ticker_identity and ticker:
            identifiers.append(
                IdentifierRecord(
                    identifier_type="INTERNAL",
                    identifier_value=f"ticker:{str(ticker).strip().upper()}",
                    source=self.name,
                    extra_data={"exchange_code": exch_code},
                )
            )
        return identifiers

    def _instrument_profile_from_mapping(
        self,
        mapping_row: dict[str, Any],
        original_identifier_type: str,
        original_identifier_value: str,
    ) -> InstrumentProfile | None:
        ticker = str(mapping_row.get("ticker") or "").strip().upper()
        name = str(mapping_row.get("name") or "").strip()
        if not ticker or not name:
            return None

        market_sector = str(mapping_row.get("marketSector") or "").strip().upper()
        security_type = str(mapping_row.get("securityType") or "").strip().upper()
        quote_type = "ETF" if "ETF" in security_type else "EQUITY"
        if market_sector and market_sector not in {"EQUITY", "ETF"}:
            quote_type = market_sector

        exchange = str(mapping_row.get("exchCode") or "").strip().upper() or None
        identifiers = self._identifier_records_from_mapping(
            mapping_row,
            original_identifier_type=original_identifier_type,
            original_identifier_value=original_identifier_value,
        )
        return InstrumentProfile(
            provider=self.name,
            symbol=ticker,
            canonical_symbol=ticker,
            name=name,
            currency=None,
            quote_type=quote_type,
            exchange=exchange,
            identifiers=identifiers,
            listings=[
                ListingRecord(
                    provider_symbol=ticker,
                    exchange_code=exchange,
                    provider_instrument_type=quote_type,
                    is_primary=True,
                    extra_data={
                        "openfigi_security_type": mapping_row.get("securityType"),
                        "openfigi_market_sector": mapping_row.get("marketSector"),
                    },
                )
            ],
            raw_payload=mapping_row,
            extra={
                "security_type": mapping_row.get("securityType"),
                "market_sector": mapping_row.get("marketSector"),
            },
        )
