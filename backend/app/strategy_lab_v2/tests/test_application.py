from dataclasses import dataclass

from app.strategy_lab_v2.application import (
    PostgresStrategyLabV2Adapter,
    _principal_identity,
    create_registered_strategy_lab_v2_router,
    get_strategy_lab_v2_adapter,
)
from app.strategy_lab_v2.postgres_commands import PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter


@dataclass
class _User:
    id: int


def test_principal_identity_normalizes_existing_integer_user_ids() -> None:
    assert _principal_identity(_User(42)).id == "42"
    assert _principal_identity("owner-a").id == "owner-a"


def test_principal_identity_rejects_missing_or_boolean_identity() -> None:
    for principal in (None, object(), True, " "):
        try:
            _principal_identity(principal)
        except ValueError as error:
            assert "principal identity" in str(error)
        else:  # pragma: no cover - assertion branch
            raise AssertionError("principal identity should be rejected")


def test_application_adapter_composes_all_durable_api_adapters() -> None:
    adapter = PostgresStrategyLabV2Adapter(lambda: object())

    assert isinstance(adapter._resources, PostgresResourceReader)
    assert isinstance(adapter._submissions, PostgresSubmissionDispatchAdapter)
    assert isinstance(adapter._execution_state, PostgresExecutionStateAdapter)
    assert isinstance(adapter._commands, PostgresCommandAdapter)


def test_registered_router_uses_versioned_prefix_and_application_dependencies() -> None:
    router = create_registered_strategy_lab_v2_router()

    assert router.prefix == "/strategy-lab/v2"
    assert {route.path for route in router.routes} >= {
        "/strategy-lab/v2/strategies/validate",
        "/strategy-lab/v2/submissions",
        "/strategy-lab/v2/attempts/{attempt_id}/commands",
    }
    assert get_strategy_lab_v2_adapter() is get_strategy_lab_v2_adapter()
