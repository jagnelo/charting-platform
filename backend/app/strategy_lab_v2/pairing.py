"""Deterministic verification of keyed common-random streams."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.strategy_lab_v2.canonical import (
    canonical_json,
    content_digest,
    freeze_json,
    require_sha256_digest,
)
from app.strategy_lab_v2.contracts import (
    KeyedRandomStreamPairingClaim,
    KeyedRandomStreamPairingReceipt,
)

KEYED_STREAM_VERIFIER_VERSION = "strategy-lab.keyed-stream-verifier.v1"


@dataclass(frozen=True, slots=True)
class KeyedRandomDraw:
    """One decoded random-stream draw identified by a stable draw key."""

    draw_key: str
    draw_value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.draw_key, str) or not self.draw_key.strip():
            raise ValueError("draw_key must not be empty")
        object.__setattr__(self, "draw_value", freeze_json(self.draw_value))


@dataclass(frozen=True, slots=True)
class PairedMetricObservation:
    """One aligned baseline/variant metric observation keyed by its event."""

    observation_key: str
    baseline_value: Decimal
    variant_value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.observation_key, str) or not self.observation_key.strip():
            raise ValueError("observation_key must not be empty")
        for name in ("baseline_value", "variant_value"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")

    @property
    def delta(self) -> Decimal:
        return self.variant_value - self.baseline_value


def verify_keyed_random_stream_pairing(
    *,
    baseline_attempt_id: str,
    variant_attempt_id: str,
    engine_build_digest: str,
    engine_conformance_fingerprint: str,
    stream_contract_fingerprint: str,
    baseline_draws: Sequence[KeyedRandomDraw],
    variant_draws: Sequence[KeyedRandomDraw],
) -> KeyedRandomStreamPairingReceipt:
    """Verify exact keyed draw alignment and emit a reproducible receipt.

    The caller supplies decoded content from both content-addressed trace
    artifacts and the registered engine/stream conformance identities. The
    verifier rejects duplicate or unmatched keys and any differing draw value;
    only an exact key/value alignment can produce a verified receipt. It does
    not compare strategy metrics or claim statistical significance.
    """

    for name, value in (
        ("baseline_attempt_id", baseline_attempt_id),
        ("variant_attempt_id", variant_attempt_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must not be empty")
    if baseline_attempt_id == variant_attempt_id:
        raise ValueError("paired stream verification requires distinct run attempts")
    for name, value in (
        ("engine_build_digest", engine_build_digest),
        ("engine_conformance_fingerprint", engine_conformance_fingerprint),
        ("stream_contract_fingerprint", stream_contract_fingerprint),
    ):
        require_sha256_digest(value, field_name=name)

    baseline = tuple(baseline_draws)
    variant = tuple(variant_draws)
    if not baseline or not variant:
        raise ValueError("paired stream verification requires non-empty draw streams")
    if any(not isinstance(item, KeyedRandomDraw) for item in (*baseline, *variant)):
        raise TypeError("draw streams must contain KeyedRandomDraw values")

    def index(draws: tuple[KeyedRandomDraw, ...], stream_name: str) -> dict[str, KeyedRandomDraw]:
        indexed = {item.draw_key: item for item in draws}
        if len(indexed) != len(draws):
            raise ValueError(f"{stream_name} draw keys must be unique")
        return indexed

    baseline_by_key = index(baseline, "baseline")
    variant_by_key = index(variant, "variant")
    baseline_keys = set(baseline_by_key)
    variant_keys = set(variant_by_key)
    if baseline_keys != variant_keys:
        raise ValueError(
            "paired stream draw keys must align exactly: "
            f"unmatched baseline={len(baseline_keys - variant_keys)}, "
            f"unmatched variant={len(variant_keys - baseline_keys)}"
        )
    for key in sorted(baseline_keys):
        if canonical_json(baseline_by_key[key].draw_value) != canonical_json(
            variant_by_key[key].draw_value
        ):
            raise ValueError(f"paired stream draw value mismatch for key {key!r}")

    ordered_keys = tuple(sorted(baseline_keys))
    paired_draws = tuple(
        (key, baseline_by_key[key].draw_value) for key in ordered_keys
    )
    claim = KeyedRandomStreamPairingClaim(
        baseline_attempt_id=baseline_attempt_id,
        variant_attempt_id=variant_attempt_id,
        engine_build_digest=engine_build_digest,
        engine_conformance_fingerprint=engine_conformance_fingerprint,
        stream_contract_fingerprint=stream_contract_fingerprint,
        baseline_trace_digest=content_digest(baseline),
        variant_trace_digest=content_digest(variant),
        paired_draws_digest=content_digest(paired_draws),
        matched_draw_count=len(ordered_keys),
    )
    verification_digest = content_digest(
        {"claim": claim, "verifier_version": KEYED_STREAM_VERIFIER_VERSION}
    )
    return KeyedRandomStreamPairingReceipt(
        claim=claim,
        verifier_version=KEYED_STREAM_VERIFIER_VERSION,
        verification_digest=verification_digest,
    )
