"""The workstation must read the local security master without provider fan-out."""


class TestCanonicalInstrumentBoundary:
    def test_canonical_search_does_not_call_provider_discovery(
        self, client, auth_headers, instrument, monkeypatch
    ):
        async def fail_provider_search(*_args, **_kwargs):
            raise AssertionError("canonical workstation search must not fan out to providers")

        monkeypatch.setattr(
            "app.routers.instruments.search_provider_instruments_async", fail_provider_search
        )

        response = client.get(
            "/api/v1/instruments/search",
            params={"q": "AAPL", "canonical_only": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()[0]["symbol"] == instrument.symbol
        assert response.json()[0]["instrument_id"] == instrument.id

    def test_canonical_symbol_resolution_does_not_auto_create_missing_instrument(
        self, client, auth_headers, monkeypatch
    ):
        async def fail_provider_create(*_args, **_kwargs):
            raise AssertionError("canonical workstation resolution must not discover providers")

        monkeypatch.setattr("app.routers.instruments._create_from_provider", fail_provider_create)

        response = client.get(
            "/api/v1/instruments/UNKNOWN",
            params={"canonical_only": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "canonical security master" in response.json()["detail"]

    def test_canonical_batch_resolution_is_ordered_bounded_and_provider_free(
        self, client, auth_headers, instrument, monkeypatch
    ):
        async def fail_provider_create(*_args, **_kwargs):
            raise AssertionError("canonical batch resolution must not discover providers")

        monkeypatch.setattr("app.routers.instruments._create_from_provider", fail_provider_create)
        response = client.post(
            "/api/v1/instruments/resolve-canonical",
            json={"symbols": ["MISSING", instrument.symbol.lower(), instrument.symbol]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == {
            "resolved": [{"symbol": instrument.symbol, "instrument_id": instrument.id}],
            "missing": ["MISSING"],
        }

    def test_canonical_batch_resolution_rejects_more_than_500_symbols(self, client, auth_headers):
        response = client.post(
            "/api/v1/instruments/resolve-canonical",
            json={"symbols": [f"SYM{index}" for index in range(501)]},
            headers=auth_headers,
        )

        assert response.status_code == 422
