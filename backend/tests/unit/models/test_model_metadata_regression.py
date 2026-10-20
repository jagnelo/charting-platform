"""Guard ORM metadata against accidental TYPE_CHECKING indentation changes."""

from sqlalchemy import inspect

from app.models.market_data_foundation import ExchangeCalendarException
from app.models.strategy import StrategyRunBatch


def _constraint_signature(model: type) -> set[tuple[str, str | None, tuple[str, ...]]]:
    return {
        (
            type(constraint).__name__,
            constraint.name,
            tuple(column.name for column in getattr(constraint, "columns", ())),
        )
        for constraint in model.__table__.constraints
    }


def _relationship_signature(model: type) -> dict[str, tuple[str, str | None]]:
    return {
        name: (relationship.mapper.class_.__name__, relationship.back_populates)
        for name, relationship in inspect(model).relationships.items()
    }


def test_exchange_calendar_exception_metadata_matches_published_schema() -> None:
    assert set(ExchangeCalendarException.__table__.columns.keys()) == {
        "id",
        "exchange_id",
        "session_date",
        "exception_kind",
        "session_code",
        "opens_at",
        "closes_at",
        "reason",
        "source",
        "source_version",
        "provenance",
        "created_at",
        "updated_at",
    }
    assert _constraint_signature(ExchangeCalendarException) == {
        ("PrimaryKeyConstraint", None, ("id",)),
        ("ForeignKeyConstraint", None, ("exchange_id",)),
        (
            "UniqueConstraint",
            "uq_exchange_calendar_exception",
            ("exchange_id", "session_date", "session_code"),
        ),
    }
    assert _relationship_signature(ExchangeCalendarException) == {"exchange": ("Exchange", None)}


def test_strategy_run_batch_metadata_matches_published_schema() -> None:
    assert set(StrategyRunBatch.__table__.columns.keys()) == {
        "id",
        "strategy_id",
        "strategy_version_id",
        "requested_by_user_id",
        "label",
        "test_mode",
        "status",
        "parameter_dimensions",
        "parameter_grid",
        "summary",
        "created_at",
        "updated_at",
    }
    assert _constraint_signature(StrategyRunBatch) == {
        ("PrimaryKeyConstraint", None, ("id",)),
        ("ForeignKeyConstraint", None, ("strategy_id",)),
        ("ForeignKeyConstraint", None, ("strategy_version_id",)),
        ("ForeignKeyConstraint", None, ("requested_by_user_id",)),
    }
    assert _relationship_signature(StrategyRunBatch) == {
        "requested_by": ("User", None),
        "runs": ("StrategyRun", "run_batch"),
        "strategy": ("StrategyDefinition", "run_batches"),
        "strategy_version": ("StrategyVersion", "run_batches"),
    }
