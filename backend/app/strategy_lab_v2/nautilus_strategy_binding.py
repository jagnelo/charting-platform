"""Runtime-safe, digest-bound strategy identity for portfolio components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


@dataclass(frozen=True, slots=True)
class NautilusComponentStrategyBinding:
    """Authenticated strategy runtime identity and parameters for one component."""

    component_id: str
    strategy_fingerprint: str
    strategy_source_digest: str
    strategy_manifest_fingerprint: str
    entrypoint: str
    parameters_digest: str
    max_intents_per_event: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        if any(character in self.component_id for character in "\x00\r\n"):
            raise ValueError("component_id must not contain control characters")
        for name in (
            "strategy_fingerprint",
            "strategy_source_digest",
            "strategy_manifest_fingerprint",
            "parameters_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.entrypoint, str):
            raise ValueError("entrypoint must use module.path:callable syntax")
        parts = self.entrypoint.split(":")
        if len(parts) != 2 or any(
            not part or any(not token.isidentifier() for token in part.split(".")) for part in parts
        ):
            raise ValueError("entrypoint must use module.path:callable syntax")
        if (
            not isinstance(self.max_intents_per_event, int)
            or isinstance(self.max_intents_per_event, bool)
            or self.max_intents_per_event < 1
        ):
            raise ValueError("max_intents_per_event must be a positive integer")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def component_strategy_binding_to_wire(
    binding: NautilusComponentStrategyBinding,
) -> dict[str, object]:
    """Serialize one authenticated component strategy binding."""

    if not isinstance(binding, NautilusComponentStrategyBinding):
        raise TypeError("binding must be a NautilusComponentStrategyBinding")
    return {
        "component_id": binding.component_id,
        "strategy_fingerprint": binding.strategy_fingerprint,
        "strategy_source_digest": binding.strategy_source_digest,
        "strategy_manifest_fingerprint": binding.strategy_manifest_fingerprint,
        "entrypoint": binding.entrypoint,
        "parameters_digest": binding.parameters_digest,
        "max_intents_per_event": binding.max_intents_per_event,
    }


def component_strategy_bindings_from_wire(
    value: object,
) -> tuple[NautilusComponentStrategyBinding, ...]:
    """Strictly decode and canonically order component strategy bindings."""

    if not isinstance(value, list):
        raise ValueError("engine input strategy bindings must be a list")
    bindings: list[NautilusComponentStrategyBinding] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "component_id",
            "strategy_fingerprint",
            "strategy_source_digest",
            "strategy_manifest_fingerprint",
            "entrypoint",
            "parameters_digest",
            "max_intents_per_event",
        }:
            raise ValueError("component strategy binding fields are invalid")
        component_id = item["component_id"]
        digests = (
            item["strategy_fingerprint"],
            item["strategy_source_digest"],
            item["strategy_manifest_fingerprint"],
            item["parameters_digest"],
        )
        entrypoint = item["entrypoint"]
        max_intents = item["max_intents_per_event"]
        if not isinstance(component_id, str) or any(
            not isinstance(digest, str) for digest in digests
        ):
            raise ValueError("component strategy binding text fields are invalid")
        if not isinstance(entrypoint, str):
            raise ValueError("component strategy binding entrypoint is invalid")
        if not isinstance(max_intents, int) or isinstance(max_intents, bool):
            raise ValueError("component strategy max_intents_per_event is invalid")
        bindings.append(
            NautilusComponentStrategyBinding(
                component_id=component_id,
                strategy_fingerprint=digests[0],
                strategy_source_digest=digests[1],
                strategy_manifest_fingerprint=digests[2],
                entrypoint=entrypoint,
                parameters_digest=digests[3],
                max_intents_per_event=max_intents,
            )
        )
    component_ids = [binding.component_id for binding in bindings]
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("component strategy binding ids must be unique")
    return tuple(sorted(bindings, key=lambda binding: binding.component_id))
