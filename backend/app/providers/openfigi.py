from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.providers.base import IdentifierRecord

logger = logging.getLogger(__name__)


class OpenFigiProvider:
    name = "openfigi"
    base_url = "https://api.openfigi.com"
    description = "OpenFIGI mapping API for stable instrument identifiers"

    def fetch_stable_identifiers(self, symbol: str) -> list[IdentifierRecord]:
        headers = {"Content-Type": "application/json"}
        if settings.OPENFIGI_API_KEY:
            headers["X-OPENFIGI-APIKEY"] = settings.OPENFIGI_API_KEY

        try:
            with httpx.Client(timeout=settings.OPENFIGI_TIMEOUT_SECONDS) as client:
                response = client.post(
                    f"{self.base_url}/v3/mapping",
                    json=[{"idType": "TICKER", "idValue": symbol}],
                    headers=headers,
                )
            if response.status_code != 200:
                return []

            payload = response.json()
            if not payload or not isinstance(payload, list):
                return []
            results = payload[0].get("data") or []
            if not results:
                return []

            first = results[0]
            identifiers: list[IdentifierRecord] = []
            composite_figi = first.get("compositeFIGI")
            figi = first.get("figi")
            ticker = first.get("ticker")
            exch_code = first.get("exchCode")

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
                            "security_type": first.get("securityType"),
                            "market_sector": first.get("marketSector"),
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
                            "name": first.get("name"),
                            "share_class_figi": first.get("shareClassFIGI"),
                        },
                    )
                )
            return identifiers
        except Exception as exc:
            logger.debug("OpenFIGI lookup failed for %s: %s", symbol, exc)
            return []
