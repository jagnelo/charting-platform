from app.models.provider_runtime import ProviderCapability
from app.services.provider_availability import (
    classify_exception,
    classify_response,
    representative_request,
)


def test_representative_contract_covers_each_capability():
    for capability in ProviderCapability:
        request = representative_request(capability)
        assert request
        assert "symbol" in request or "query" in request or "quote_type" in request


def test_classification_is_deterministic_for_empty_and_transport_failures():
    assert classify_response([]) == "empty_partial_response"
    assert classify_response({"rows": [1]}) == "success"
    assert classify_exception(TimeoutError()) == "timeout"
    assert classify_exception(ConnectionError("DNS lookup failed")) == "dns_transport"
