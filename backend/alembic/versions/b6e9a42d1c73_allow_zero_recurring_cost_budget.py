"""Allow an explicitly reviewed zero recurring-cost ceiling."""

from alembic import op

revision = "b6e9a42d1c73"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


_TABLE = "provider_recurring_cost_budget"
_OLD_CONSTRAINT = "ck_provider_recurring_cost_budget_positive"
_NEW_CONSTRAINT = "ck_provider_recurring_cost_budget_nonnegative"


def _replace_constraint(old_name: str, new_name: str, expression: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE, recreate="always") as batch:
            batch.drop_constraint(old_name, type_="check")
            batch.create_check_constraint(new_name, expression)
        return

    op.drop_constraint(old_name, _TABLE, type_="check")
    op.create_check_constraint(new_name, _TABLE, expression)


def upgrade() -> None:
    _replace_constraint(_OLD_CONSTRAINT, _NEW_CONSTRAINT, "monthly_ceiling >= 0")


def downgrade() -> None:
    _replace_constraint(_NEW_CONSTRAINT, _OLD_CONSTRAINT, "monthly_ceiling > 0")
