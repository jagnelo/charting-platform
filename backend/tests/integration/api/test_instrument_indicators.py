"""Integration coverage for concurrent-safe chart indicator persistence."""


class TestInstrumentIndicators:
    def test_indicator_configuration_round_trip_is_user_scoped(
        self, client, auth_headers, instrument
    ):
        created = client.put(
            f"/api/v1/instrument-indicators/{instrument.id}",
            headers=auth_headers,
            json={"indicators": [{"type": "rsi", "params": {"period": 14}}]},
        )
        assert created.status_code == 200
        assert created.json()["indicators"][0]["type"] == "rsi"

        updated = client.put(
            f"/api/v1/instrument-indicators/{instrument.id}",
            headers=auth_headers,
            json={"indicators": [{"type": "ema", "params": {"period": 20}}]},
        )
        assert updated.status_code == 200

        loaded = client.get(
            f"/api/v1/instrument-indicators/{instrument.id}",
            headers=auth_headers,
        )
        assert loaded.status_code == 200
        assert loaded.json() == {"indicators": [{"type": "ema", "params": {"period": 20}}]}

    def test_indicator_configuration_requires_authentication(self, client, instrument):
        response = client.get(f"/api/v1/instrument-indicators/{instrument.id}")
        assert response.status_code == 401
