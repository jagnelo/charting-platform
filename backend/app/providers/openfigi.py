from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.providers.base import IdentifierRecord

logger = logging.getLogger(__name__)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


class OpenFigiIdentifierProvider:
    name = "openfigi"

    async def map_ticker(self, symbol: str) -> list[IdentifierRecord]:
        headers = {"Content-Type": "application/json"}
        if settings.OPENFIGI_API_KEY:
            headers["X-OPENFIGI-APIKEY"] = settings.OPENFIGI_API_KEY

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    OPENFIGI_URL,
                    json=[{"idType": "TICKER", "idValue": symbol}],
                    headers=headers,
                )
            if resp.status_code != 200:
                return []
            payload = resp.json()
            if not payload or not isinstance(payload, list):
                return []
            results = payload[0].get("data") or []
            if not results:
                return []

            first = results[0]
            identifiers: list[IdentifierRecord] = []
            composite_figi = first.get("compositeFIGI")
            figi = first.get("figi")
            if composite_figi:
                identifiers.append(
                    IdentifierRecord(
                        identifier_type="COMPOSITE_FIGI",
                        identifier_value=str(composite_figi),
                        is_primary=True,
                        source=self.name,
                    )
                )
            if figi:
                identifiers.append(
                    IdentifierRecord(
                        identifier_type="FIGI",
                        identifier_value=str(figi),
                        source=self.name,
                    )
                )
            return identifiers
        except Exception as exc:
            logger.debug("OpenFIGI lookup failed for %s: %s", symbol, exc)
            return []
