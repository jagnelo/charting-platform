from app.config import settings


def test_health_exposes_fixture_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "E2E_SEED_INSTRUMENTS", True)
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "2.0.0",
        "e2e_seed_instruments": True,
        "e2e_seed_market_data": True,
    }
