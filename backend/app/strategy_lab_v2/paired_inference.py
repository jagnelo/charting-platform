"""Deterministic exact inference for verified paired observations.

The inference boundary is deliberately narrow: it performs a two-sided exact
sign-flip randomization test for the mean of aligned metric deltas.  A verified
keyed-stream pairing receipt is required, and the observation keys are sorted
and content-addressed before enumeration.  The result is statistical evidence,
not a profitability verdict or a substitute for engine conformance.

Exact enumeration is bounded so a worker cannot accidentally turn a metric
request into an unbounded CPU operation.  Inputs above the bound return typed
unavailable evidence instead of falling back to an approximate or unseeded
method.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import KeyedRandomStreamPairingReceipt
from app.strategy_lab_v2.decimal_math import deterministic_decimal_math
from app.strategy_lab_v2.pairing import (
    PairedMetricObservation,
)

PAIRED_INFERENCE_CONTRACT_VERSION = "strategy-lab.paired-inference.v1"
DEFAULT_MAX_EXACT_OBSERVATIONS = 20


class PairedInferenceUnavailableReason(StrEnum):
    """Why exact paired inference was withheld."""

    EXACT_ENUMERATION_LIMIT = "exact_enumeration_limit"


@dataclass(frozen=True, slots=True)
class ExactPairedInference:
    """A deterministic two-sided exact sign-flip test result."""

    metric_name: str
    observation_digest: str
    pairing_receipt_fingerprint: str
    sample_size: int
    mean_delta: Decimal
    observed_absolute_sum: Decimal
    extreme_permutation_count: int
    permutation_count: int
    maximum_exact_observations: int
    method: str = "exact_sign_flip_two_sided_mean"
    null_hypothesis: str = "mean_delta_equals_zero"
    alternative: str = "two_sided"
    contract_version: str = PAIRED_INFERENCE_CONTRACT_VERSION

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        for name in (
            "metric_name",
            "method",
            "null_hypothesis",
            "alternative",
            "contract_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        require_sha256_digest(self.observation_digest, field_name="observation_digest")
        require_sha256_digest(
            self.pairing_receipt_fingerprint,
            field_name="pairing_receipt_fingerprint",
        )
        if (
            not isinstance(self.sample_size, int)
            or isinstance(self.sample_size, bool)
            or self.sample_size < 1
        ):
            raise ValueError("sample_size must be a positive integer")
        for name in ("mean_delta", "observed_absolute_sum"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        for name in ("extreme_permutation_count", "permutation_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.extreme_permutation_count > self.permutation_count:
            raise ValueError("extreme permutations cannot exceed total permutations")
        if self.permutation_count != 1 << self.sample_size:
            raise ValueError("permutation_count must equal two to the sample_size")
        if (
            not isinstance(self.maximum_exact_observations, int)
            or isinstance(self.maximum_exact_observations, bool)
            or self.maximum_exact_observations < 1
        ):
            raise ValueError("maximum_exact_observations must be positive")
        if self.sample_size > self.maximum_exact_observations:
            raise ValueError("sample_size exceeds maximum_exact_observations")

    @property
    def two_sided_p_value(self) -> Decimal:
        """Return the exact inclusive-tail probability as a Decimal."""

        return Decimal(self.extreme_permutation_count) / Decimal(self.permutation_count)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PairedInferenceUnavailable:
    """Typed evidence that exact inference was intentionally withheld."""

    metric_name: str
    observation_digest: str
    pairing_receipt_fingerprint: str
    sample_size: int
    maximum_exact_observations: int
    reason: PairedInferenceUnavailableReason
    contract_version: str = PAIRED_INFERENCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must not be empty")
        require_sha256_digest(self.observation_digest, field_name="observation_digest")
        require_sha256_digest(
            self.pairing_receipt_fingerprint,
            field_name="pairing_receipt_fingerprint",
        )
        if not isinstance(self.sample_size, int) or isinstance(self.sample_size, bool) or self.sample_size < 1:
            raise ValueError("sample_size must be a positive integer")
        if (
            not isinstance(self.maximum_exact_observations, int)
            or isinstance(self.maximum_exact_observations, bool)
            or self.maximum_exact_observations < 1
        ):
            raise ValueError("maximum_exact_observations must be positive")
        if not isinstance(self.reason, PairedInferenceUnavailableReason):
            raise TypeError("reason must be a PairedInferenceUnavailableReason")
        if not isinstance(self.contract_version, str) or not self.contract_version.strip():
            raise ValueError("contract_version must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


PairedInferenceOutcome = ExactPairedInference | PairedInferenceUnavailable


def _validated_observations(
    observations: Sequence[PairedMetricObservation],
    *,
    pairing_receipt: KeyedRandomStreamPairingReceipt,
    metric_name: str,
    maximum_exact_observations: int,
) -> tuple[tuple[PairedMetricObservation, ...], str]:
    if not isinstance(observations, Sequence) or isinstance(observations, str | bytes):
        raise TypeError("observations must be a sequence")
    if not isinstance(pairing_receipt, KeyedRandomStreamPairingReceipt):
        raise TypeError("pairing_receipt must use KeyedRandomStreamPairingReceipt")
    if not isinstance(metric_name, str) or not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    if (
        not isinstance(maximum_exact_observations, int)
        or isinstance(maximum_exact_observations, bool)
        or not 1 <= maximum_exact_observations <= DEFAULT_MAX_EXACT_OBSERVATIONS
    ):
        raise ValueError(
            "maximum_exact_observations must be an integer between 1 and "
            f"{DEFAULT_MAX_EXACT_OBSERVATIONS}"
        )
    values = tuple(observations)
    if not values:
        raise ValueError("at least one paired metric observation is required")
    if any(not isinstance(item, PairedMetricObservation) for item in values):
        raise TypeError("observations must contain PairedMetricObservation values")
    ordered = tuple(sorted(values, key=lambda item: item.observation_key))
    keys = tuple(item.observation_key for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("paired metric observation keys must be unique")
    return ordered, content_digest(ordered)


@deterministic_decimal_math
def infer_paired_mean(
    observations: Sequence[PairedMetricObservation],
    *,
    metric_name: str,
    pairing_receipt: KeyedRandomStreamPairingReceipt,
    maximum_exact_observations: int = DEFAULT_MAX_EXACT_OBSERVATIONS,
) -> PairedInferenceOutcome:
    """Run a bounded exact two-sided sign-flip test over paired deltas.

    The null is that the paired metric-delta mean is zero and the alternative
    is two-sided.  Every one of the ``2**n`` sign assignments is enumerated;
    inclusive ties are counted in the tail.  Larger samples return explicit
    unavailable evidence instead of an approximate test with unrecorded
    randomness.
    """

    ordered, observation_digest = _validated_observations(
        observations,
        pairing_receipt=pairing_receipt,
        metric_name=metric_name,
        maximum_exact_observations=maximum_exact_observations,
    )
    sample_size = len(ordered)
    receipt_fingerprint = pairing_receipt.fingerprint
    if sample_size > maximum_exact_observations:
        return PairedInferenceUnavailable(
            metric_name=metric_name,
            observation_digest=observation_digest,
            pairing_receipt_fingerprint=receipt_fingerprint,
            sample_size=sample_size,
            maximum_exact_observations=maximum_exact_observations,
            reason=PairedInferenceUnavailableReason.EXACT_ENUMERATION_LIMIT,
        )

    deltas: tuple[Decimal, ...] = tuple(item.delta for item in ordered)
    observed_sum = sum(deltas, Decimal(0))
    observed_absolute_sum = abs(observed_sum)
    permutation_count = 1 << sample_size
    extreme_count = 0
    for mask in range(permutation_count):
        signed_sum: Decimal = sum(
            (
                delta if mask & (1 << index) else -delta
                for index, delta in enumerate(deltas)
            ),
            Decimal(0),
        )
        if abs(signed_sum) >= observed_absolute_sum:
            extreme_count += 1
    return ExactPairedInference(
        metric_name=metric_name,
        observation_digest=observation_digest,
        pairing_receipt_fingerprint=receipt_fingerprint,
        sample_size=sample_size,
        mean_delta=observed_sum / Decimal(sample_size),
        observed_absolute_sum=observed_absolute_sum,
        extreme_permutation_count=extreme_count,
        permutation_count=permutation_count,
        maximum_exact_observations=maximum_exact_observations,
    )


__all__ = [
    "DEFAULT_MAX_EXACT_OBSERVATIONS",
    "ExactPairedInference",
    "PAIRED_INFERENCE_CONTRACT_VERSION",
    "PairedInferenceOutcome",
    "PairedInferenceUnavailable",
    "PairedInferenceUnavailableReason",
    "infer_paired_mean",
]
