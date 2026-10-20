"""Provider entitlement descriptions remain lossless beyond legacy varchar limits."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "c3d4e5f6a7b8_widen_provider_entitlement_descriptions.py"
    )
    spec = importlib.util.spec_from_file_location("provider_entitlement_text_width", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_entitlement_migration_preserves_long_descriptions_and_guards_downgrade():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for table_name in ("provider_entitlement", "provider_entitlement_revision"):
        Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            *(
                Column(name, String(160), nullable=True)
                for name in ("history_depth", "venue_coverage", "freshness_semantics")
            ),
        )
    metadata.create_all(engine)

    with engine.begin() as connection:
        old_values = ("history", "venue", "freshness")
        for table_name in ("provider_entitlement", "provider_entitlement_revision"):
            connection.execute(
                metadata.tables[table_name]
                .insert()
                .values(
                    id=1,
                    history_depth=old_values[0],
                    venue_coverage=old_values[1],
                    freshness_semantics=old_values[2],
                )
            )

        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        long_description = "Provider venue coverage with full provenance and regional notes. " * 8
        for table_name in ("provider_entitlement", "provider_entitlement_revision"):
            connection.execute(
                metadata.tables[table_name]
                .update()
                .where(metadata.tables[table_name].c.id == 1)
                .values(venue_coverage=long_description)
            )
            assert (
                connection.execute(
                    metadata.tables[table_name]
                    .select()
                    .with_only_columns(metadata.tables[table_name].c.venue_coverage)
                ).scalar_one()
                == long_description
            )

        text_columns = {
            column["name"]
            for column in inspect(connection).get_columns("provider_entitlement")
            if isinstance(column["type"], Text)
        }
        assert {"history_depth", "venue_coverage", "freshness_semantics"} <= text_columns

        try:
            module.downgrade()
        except RuntimeError as exc:
            assert "provider_entitlement.venue_coverage" in str(exc)
            assert "exceed 160 characters" in str(exc)
        else:
            raise AssertionError("downgrade must not narrow and truncate entitlement descriptions")

        assert (
            connection.execute(
                metadata.tables["provider_entitlement"]
                .select()
                .with_only_columns(metadata.tables["provider_entitlement"].c.venue_coverage)
            ).scalar_one()
            == long_description
        )
