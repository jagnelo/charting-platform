from __future__ import annotations

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.resource_domains import normalize_resource_attributes

SOURCE_DIGEST = content_digest("strategy-source")
ARTIFACT_DIGEST = content_digest("dependency-wheel")


def _attributes() -> dict:
    return {
        "strategy_id": "momentum",
        "version_id": "2026-09-17",
        "sdk_version": "strategy-sdk.v2",
        "source_digest": SOURCE_DIGEST,
        "dependencies": [
            {
                "distribution": "numpy",
                "version": "2.0.0",
                "artifact_digest": ARTIFACT_DIGEST,
            }
        ],
        "parameter_schema": {"lookback": {"type": "integer"}},
        "default_parameters": {"lookback": 20},
    }


def test_strategy_attributes_are_normalized_and_domain_fingerprinted() -> None:
    result = normalize_resource_attributes(ApiResourceType.STRATEGY, _attributes())

    assert result.domain_fingerprint is not None
    assert result.attributes["strategy_id"] == "momentum"
    assert result.attributes["dependencies"][0]["distribution"] == "numpy"
    assert result.attributes["dependencies"][0]["version"] == "2.0.0"
    assert result.attributes["parameter_schema"]["lookback"]["type"] == "integer"

    reordered = _attributes()
    reordered["dependencies"] = list(reversed(reordered["dependencies"]))
    assert normalize_resource_attributes(ApiResourceType.STRATEGY, reordered) == result


def test_strategy_resource_id_aliases_must_agree() -> None:
    attributes = _attributes()
    attributes.update({"id": "one", "resource_id": "two"})

    try:
        normalize_resource_attributes(ApiResourceType.STRATEGY, attributes)
    except ValueError as error:
        assert "must agree" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("conflicting strategy resource IDs should be rejected")


def test_strategy_rejects_unknown_or_invalid_dependency_fields() -> None:
    unknown = _attributes()
    unknown["network"] = True
    try:
        normalize_resource_attributes(ApiResourceType.STRATEGY, unknown)
    except ValueError as error:
        assert "unsupported fields" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("unknown strategy fields should be rejected")

    malformed = _attributes()
    malformed["dependencies"] = [{"distribution": "numpy"}]
    try:
        normalize_resource_attributes(ApiResourceType.STRATEGY, malformed)
    except ValueError as error:
        assert "distribution" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("malformed strategy dependencies should be rejected")


def test_non_strategy_resources_remain_frozen_until_their_domain_adapter_exists() -> None:
    attributes = {"name": "trial", "nested": {"values": [1, 2]}}

    result = normalize_resource_attributes(ApiResourceType.TRIAL, attributes)

    assert result.domain_fingerprint is None
    assert result.attributes["nested"]["values"] == (1, 2)
