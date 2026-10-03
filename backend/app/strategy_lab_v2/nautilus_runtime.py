"""Exact isolated Nautilus v2 release-candidate runtime declarations.

The application backend intentionally keeps the legacy Nautilus 1.x dependency
in its own environment.  This module gives an adapter a typed, immutable
declaration for the current v2 RC compatibility runtime without importing
Nautilus, discovering packages, or starting a process.  The adapter must still
provide content digests for the source checkout and runtime image after it has
resolved/builds those artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_RELEASE_PIN_VERSION,
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    NAUTILUS_V2_RC_WHEEL_SHA256,
    ConformanceCheck,
    EngineReleaseChannel,
    NautilusReleasePin,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _decimal(value: Any, field_name: str) -> Decimal:
    """Parse one finite fixture decimal, accepting Nautilus money display text."""

    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise TypeError(f"{field_name} must be a decimal-compatible scalar")
    try:
        parsed = Decimal(str(value).split()[0])
    except (InvalidOperation, IndexError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _decimal_strings(value: Any, field_name: str) -> tuple[Decimal, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    return tuple(_decimal(item, field_name) for item in value)


def _money_strings(value: Any, field_name: str, currency: str) -> tuple[Decimal, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    amounts: list[Decimal] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be native money report strings")
        parts = item.split()
        if len(parts) != 2 or parts[1] != currency:
            raise ValueError(f"{field_name} entries must use the expected {currency} currency")
        amounts.append(_decimal(parts[0], field_name))
    return tuple(amounts)


def _require_native_accounting_run(run: Any) -> None:
    if not isinstance(run, Mapping):
        raise ValueError("native accounting fixture must be a mapping")
    instrument_count = run.get("instrument_count")
    if (
        not isinstance(instrument_count, int)
        or isinstance(instrument_count, bool)
        or instrument_count < 1
    ):
        raise ValueError("native accounting fixture must identify its instrument count")
    if (
        run.get("total_orders") != instrument_count
        or run.get("total_positions") != instrument_count
        or _decimal(run.get("orders_total"), "orders_total") != instrument_count
        or _decimal(run.get("positions_total"), "positions_total") != instrument_count
    ):
        raise ValueError("native orders and positions must reconcile per instrument")

    reports = run.get("native_reports")
    report_fields = {
        "commission_total",
        "commissions",
        "expected_commission_per_fill",
        "expected_quantity_per_instrument",
        "expected_quantity_total",
        "execution_prices",
        "fee_currency",
        "fill_instrument_ids",
        "fill_quantities",
        "filled_quantity",
        "fills_report_rows",
        "initial_account_total",
        "best_ask",
        "orders_report_rows",
        "price_increment",
        "total_fills",
    }
    if not isinstance(reports, Mapping) or set(reports) != report_fields:
        raise ValueError("native fill/cost fixture must include exact native report evidence")

    total_fills = reports["total_fills"]
    fill_quantities = _decimal_strings(reports["fill_quantities"], "fill_quantities")
    execution_prices = _decimal_strings(reports["execution_prices"], "execution_prices")
    commissions = _money_strings(reports["commissions"], "commissions", reports["fee_currency"])
    instrument_ids = reports["fill_instrument_ids"]
    if (
        not isinstance(total_fills, int)
        or isinstance(total_fills, bool)
        or total_fills != instrument_count
        or reports["fills_report_rows"] != total_fills
        or len(fill_quantities) != total_fills
        or len(execution_prices) != total_fills
        or len(commissions) != total_fills
        or not isinstance(instrument_ids, list)
        or len(instrument_ids) != total_fills
        or len(set(instrument_ids)) != instrument_count
        or reports["orders_report_rows"] != run["total_orders"]
    ):
        raise ValueError("native order and fill report rows do not reconcile")

    expected_per_instrument = _decimal(
        reports["expected_quantity_per_instrument"], "expected_quantity_per_instrument"
    )
    expected_total_quantity = _decimal(
        reports["expected_quantity_total"], "expected_quantity_total"
    )
    filled_quantity = _decimal(reports["filled_quantity"], "filled_quantity")
    if (
        expected_per_instrument <= 0
        or expected_total_quantity != expected_per_instrument * instrument_count
        or filled_quantity != expected_total_quantity
        or sum(fill_quantities, Decimal(0)) != filled_quantity
        or any(quantity != expected_per_instrument for quantity in fill_quantities)
    ):
        raise ValueError("native fill report quantity does not reconcile per instrument")

    best_ask = _decimal(reports["best_ask"], "best_ask")
    price_increment = _decimal(reports["price_increment"], "price_increment")
    if price_increment <= 0 or any(
        execution_price != best_ask + price_increment for execution_price in execution_prices
    ):
        raise ValueError("native fill report did not apply the configured one-tick slippage")

    expected_commission = _decimal(
        reports["expected_commission_per_fill"], "expected_commission_per_fill"
    )
    commission_total = _decimal(reports["commission_total"], "commission_total")
    if (
        expected_commission <= 0
        or any(commission != expected_commission for commission in commissions)
        or sum(commissions, Decimal(0)) != commission_total
    ):
        raise ValueError("native fee report does not match the configured fixed fee")

    initial_account_total = _decimal(reports["initial_account_total"], "initial_account_total")
    account_total = _decimal(run.get("account_total"), "account_total")
    expected_account_total = (
        initial_account_total
        - sum(
            (quantity * price for quantity, price in zip(fill_quantities, execution_prices)),
            Decimal(0),
        )
        - commission_total
    )
    if account_total != expected_account_total:
        raise ValueError("native account report does not reconcile fills and commissions")


@dataclass(frozen=True, slots=True)
class NautilusRcCompatibilityRuntime:
    """One exact v2 RC runtime boundary.

    The package/tag are deliberately not caller-selectable: changing either
    value creates a different release track and requires a new reviewed
    contract. The exact package-wheel digest is pinned alongside source/image
    digests supplied by the image/build adapter.
    """

    source_digest: str
    runtime_image_digest: str
    python_version: str
    rust_version: str
    wheel_digest: str = NAUTILUS_V2_RC_WHEEL_SHA256
    legacy_runtime_isolated: bool = True
    contract_version: str = NAUTILUS_RELEASE_PIN_VERSION

    def __post_init__(self) -> None:
        require_sha256_digest(self.source_digest, field_name="source_digest")
        require_sha256_digest(self.runtime_image_digest, field_name="runtime_image_digest")
        require_sha256_digest(self.wheel_digest, field_name="wheel_digest")
        if self.wheel_digest != NAUTILUS_V2_RC_WHEEL_SHA256:
            raise ValueError("the exact Nautilus RC5 wheel digest cannot be overridden")
        for name in ("python_version", "rust_version", "contract_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.legacy_runtime_isolated, bool):
            raise TypeError("legacy_runtime_isolated must be a boolean")
        if not self.legacy_runtime_isolated:
            raise ValueError("the v2 RC runtime must be isolated from the legacy runtime")

    @property
    def package_version(self) -> str:
        return NAUTILUS_V2_RC_PACKAGE_VERSION

    @property
    def release_tag(self) -> str:
        return NAUTILUS_V2_RC_RELEASE_TAG

    @property
    def release_channel(self) -> EngineReleaseChannel:
        return EngineReleaseChannel.RELEASE_CANDIDATE

    @property
    def authoritative(self) -> bool:
        """A runtime pin declaration alone does not authorize any output."""

        return False

    @property
    def release_pin(self) -> NautilusReleasePin:
        """Build the exact release identity consumed by conformance evidence."""

        return NautilusReleasePin(
            package_version=self.package_version,
            release_tag=self.release_tag,
            source_digest=self.source_digest,
            wheel_digest=self.wheel_digest,
            runtime_image_digest=self.runtime_image_digest,
            python_version=self.python_version,
            rust_version=self.rust_version,
            legacy_runtime_isolated=self.legacy_runtime_isolated,
            contract_version=self.contract_version,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusRuntimeProbeEvidence:
    """Typed, non-authoritative receipt emitted by the isolated image probe."""

    runtime_fingerprint: str
    runtime_image_digest: str
    package_version: str
    python_version: str
    platform: str
    implementation: str
    engine_lifecycle: str

    def __post_init__(self) -> None:
        for name in ("runtime_fingerprint", "runtime_image_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "package_version",
            "python_version",
            "platform",
            "implementation",
        ):
            _nonempty(getattr(self, name), name)
        if self.package_version != NAUTILUS_V2_RC_PACKAGE_VERSION:
            raise ValueError("probe evidence must target the exact v2 RC package")
        if self.engine_lifecycle != "passed":
            raise ValueError("probe evidence requires a passed engine lifecycle")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        runtime: NautilusRcCompatibilityRuntime,
    ) -> NautilusRuntimeProbeEvidence:
        """Parse one strict probe JSON object against its declared runtime."""

        if not isinstance(payload, Mapping):
            raise TypeError("probe payload must be a mapping")
        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        required = {
            "engine_lifecycle",
            "implementation",
            "nautilus_package_version",
            "platform",
            "python_version",
        }
        if set(payload) != required:
            raise ValueError("probe payload fields must match the exact runtime schema")
        values = {key: payload[key] for key in required}
        if any(not isinstance(value, str) for value in values.values()):
            raise TypeError("probe payload fields must be strings")
        if values["nautilus_package_version"] != runtime.package_version:
            raise ValueError("probe package version does not match the declared runtime")
        if values["python_version"] != runtime.python_version:
            raise ValueError("probe Python version does not match the declared runtime")
        return cls(
            runtime_fingerprint=runtime.fingerprint,
            runtime_image_digest=runtime.runtime_image_digest,
            package_version=values["nautilus_package_version"],
            python_version=values["python_version"],
            platform=values["platform"],
            implementation=values["implementation"],
            engine_lifecycle=values["engine_lifecycle"],
        )

    @property
    def authoritative(self) -> bool:
        """RC probe output can never authorize published or live results."""

        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusRcFixtureReceipt:
    """Partial real-engine fixture receipt for the non-authoritative RC track."""

    runtime_fingerprint: str
    runtime_image_digest: str
    fixture_digest: str
    passed_checks: frozenset[ConformanceCheck]
    deferred_checks: frozenset[ConformanceCheck]

    def __post_init__(self) -> None:
        for name in ("runtime_fingerprint", "runtime_image_digest", "fixture_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        passed = frozenset(self.passed_checks)
        deferred = frozenset(self.deferred_checks)
        if any(not isinstance(check, ConformanceCheck) for check in passed | deferred):
            raise TypeError("fixture checks must contain ConformanceCheck values")
        if passed & deferred:
            raise ValueError("passed and deferred fixture checks must be disjoint")
        if passed | deferred != frozenset(ConformanceCheck):
            raise ValueError("fixture receipt must account for every conformance check")
        object.__setattr__(self, "passed_checks", passed)
        object.__setattr__(self, "deferred_checks", deferred)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        runtime: NautilusRcCompatibilityRuntime,
    ) -> NautilusRcFixtureReceipt:
        """Parse the real image fixture output without granting authority."""

        if not isinstance(payload, Mapping):
            raise TypeError("fixture payload must be a mapping")
        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        required = {
            "authoritative",
            "deterministic_replay",
            "engine_lifecycle",
            "forward_event_tape_parity",
            "multi_instrument_accounting",
            "native_order_fill_cost",
        }
        if set(payload) != required:
            raise ValueError("fixture payload fields must match the exact receipt schema")
        if payload["authoritative"] is not False:
            raise ValueError("release-candidate fixture receipts cannot be authoritative")
        if payload["engine_lifecycle"] != "passed":
            raise ValueError("fixture engine lifecycle must pass")
        replay = payload["deterministic_replay"]
        multi = payload["multi_instrument_accounting"]
        native = payload["native_order_fill_cost"]
        if not isinstance(replay, Mapping) or replay.get("equal") is not True:
            raise ValueError("deterministic replay fixture did not match")
        if not isinstance(multi, Mapping) or multi.get("instrument_count", 0) < 2:
            raise ValueError("multi-instrument fixture did not cover two instruments")
        _require_native_accounting_run(multi)
        _require_native_accounting_run(native)
        if multi["instrument_count"] < 2 or native["instrument_count"] != 1:
            raise ValueError("single- and multi-instrument fixtures must be distinct")
        if payload["forward_event_tape_parity"] != "deferred_authoritative_fixture":
            raise ValueError("forward event-tape parity must remain explicitly deferred")
        return cls(
            runtime_fingerprint=runtime.fingerprint,
            runtime_image_digest=runtime.runtime_image_digest,
            fixture_digest=content_digest(payload),
            passed_checks=frozenset(
                {
                    ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING,
                    ConformanceCheck.NATIVE_ORDER_FILL_COST,
                    ConformanceCheck.DETERMINISTIC_REPLAY,
                    ConformanceCheck.ENGINE_LIFECYCLE,
                }
            ),
            deferred_checks=frozenset({ConformanceCheck.FORWARD_EVENT_TAPE_PARITY}),
        )

    @property
    def compatible(self) -> bool:
        """Partial RC fixtures are compatible but not complete conformance."""

        return True

    @property
    def authoritative(self) -> bool:
        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


__all__ = [
    "NautilusRcCompatibilityRuntime",
    "NautilusRuntimeProbeEvidence",
    "NautilusRcFixtureReceipt",
]
