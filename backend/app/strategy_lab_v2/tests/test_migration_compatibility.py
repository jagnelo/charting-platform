from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.strategy_lab_v2.migration_compatibility import (
    LEGACY_STRATEGY_REVISIONS,
    STRATEGY_REVISION_MAPPING,
    MigrationHistoryCompatibilityError,
    assert_unambiguous_migration_history,
)


@pytest.mark.parametrize("revision", LEGACY_STRATEGY_REVISIONS)
def test_legacy_strategy_history_is_rejected_without_touching_rows(revision: str) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (revision,))
        connection.exec_driver_sql("CREATE TABLE strategy_lab_v2_aggregates (payload TEXT)")
        connection.exec_driver_sql(
            "INSERT INTO strategy_lab_v2_aggregates VALUES (?)", ('{"immutable": "keep"}',)
        )
    statements: list[str] = []
    sa.event.listen(engine, "before_cursor_execute", lambda _c, _u, s, *_a: statements.append(s))
    with engine.connect() as connection:
        with pytest.raises(MigrationHistoryCompatibilityError, match="reviewed recovery"):
            assert_unambiguous_migration_history(connection, SimpleNamespace())
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == revision
        )
        assert (
            connection.exec_driver_sql("SELECT payload FROM strategy_lab_v2_aggregates").scalar()
            == '{"immutable": "keep"}'
        )
    assert all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements)
    engine.dispose()


@pytest.mark.parametrize("revision", [None, "fe4f5a6b7c8d", "slv2_0007"])
def test_new_or_noncolliding_history_needs_no_rewrite(revision: str | None) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        if revision is not None:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (revision,))
        assert_unambiguous_migration_history(connection, SimpleNamespace())
    engine.dispose()


def test_collision_without_installed_owner_or_schema_fails_closed() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('ff0a1b2c3d4e')")
        for path in ("unrecognized.py", "ff0a1b2c3d4e_add_ohlcv_derivation_provenance.py"):
            scripts = SimpleNamespace(get_revision=lambda _r: SimpleNamespace(path=path))
            with pytest.raises(MigrationHistoryCompatibilityError):
                assert_unambiguous_migration_history(connection, scripts)
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == "ff0a1b2c3d4e"
        )
    engine.dispose()


@pytest.mark.parametrize(
    "revision,filename,ddl",
    [
        (
            "ff1a2b3c4d5e",
            "ff1a2b3c4d5e_add_adjustment_factor_observations.py",
            (
                "CREATE TABLE adjustment_factor_observation (id INTEGER, instrument_id INTEGER, "
                "data_source_id INTEGER, provider_symbol TEXT, factor_type TEXT, effective_at TEXT, "
                "factor NUMERIC, amount NUMERIC, source_event_key TEXT, observed_at TEXT, "
                "factor_version TEXT, raw_payload TEXT, created_at TEXT, updated_at TEXT)",
            ),
        ),
        (
            "ff2a3b4c5d6e",
            "ff2a3b4c5d6e_add_provider_adjustment_factor_fields.py",
            (
                "CREATE TABLE instrument_event (adjustment_factor NUMERIC)",
                "CREATE TABLE adjustment_factor_observation (factor_kind TEXT)",
            ),
        ),
        (
            "ff5a6b7c8d9e",
            "ff5a6b7c8d9e_make_provider_limits_explicit.py",
            (
                "CREATE TABLE provider_policy (quota_contract TEXT, quota_scope TEXT, "
                "quota_source TEXT, quota_verified_at TEXT)",
                "CREATE TABLE provider_quota_window (dimension TEXT)",
            ),
        ),
    ],
)
def test_other_upstream_markers_require_installed_owner_and_schema(
    revision: str, filename: str, ddl: tuple[str, ...]
) -> None:
    engine = sa.create_engine("sqlite://")
    scripts = SimpleNamespace(get_revision=lambda _r: SimpleNamespace(path=filename))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (revision,))
        with pytest.raises(MigrationHistoryCompatibilityError, match="schema evidence"):
            assert_unambiguous_migration_history(connection, scripts)
        for statement in ddl:
            connection.exec_driver_sql(statement)
        assert_unambiguous_migration_history(connection, scripts)
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == revision
        )
    engine.dispose()


def test_recognized_upstream_history_is_not_rewritten_and_mixed_schema_is_rejected() -> None:
    engine = sa.create_engine("sqlite://")
    scripts = SimpleNamespace(
        get_revision=lambda _r: SimpleNamespace(
            path="ff0a1b2c3d4e_add_ohlcv_derivation_provenance.py"
        )
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('ff0a1b2c3d4e')")
        connection.exec_driver_sql(
            "CREATE TABLE ohlcv_bar (is_derived BOOLEAN, source_timeframe TEXT, "
            "derivation_method TEXT, derived_at TEXT, source_bar_count INTEGER, "
            "source_start TEXT, source_end TEXT)"
        )
        assert_unambiguous_migration_history(connection, scripts)
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == "ff0a1b2c3d4e"
        )
        connection.exec_driver_sql("CREATE TABLE strategy_lab_v2_dispatch_payloads (payload TEXT)")
        with pytest.raises(MigrationHistoryCompatibilityError, match="mixed"):
            assert_unambiguous_migration_history(connection, scripts)
    engine.dispose()


def test_strategy_chain_has_unique_ids_and_preserves_shared_base() -> None:
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[3] / "alembic"))
    declared = []
    for path in (Path(scripts.dir) / "versions").glob("*.py"):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "revision" for target in node.targets
            ):
                declared.append(ast.literal_eval(node.value))
    assert len(declared) == len(set(declared))
    revisions = list(scripts.walk_revisions())
    assert len(revisions) == len({revision.revision for revision in revisions})
    assert scripts.get_heads() == ["d4a5b6c7e812"]
    assert scripts.get_revision("d4a5b6c7e812").down_revision == "slv2_0011"
    merge = scripts.get_revision("slv2_0011")
    assert merge.down_revision == ("e9c23a7b1d40", "slv2_0010")
    ancestry = {revision.revision for revision in scripts.iterate_revisions("d4a5b6c7e812", None)}
    assert {
        "e9c23a7b1d40",
        "a7c91e03d54b",
        "ff2a3b4c5d6e",
        "ff1a2b3c4d5e",
        "ff0a1b2c3d4e",
        "d1e7f2a9c4b6",
        "b6e9a42d1c73",
        "slv2_0009",
        "slv2_0008",
        "slv2_0001",
        "fe4f5a6b7c8d",
    }.issubset(ancestry)
    assert "slv2_0010" not in STRATEGY_REVISION_MAPPING.values()
    assert "slv2_0011" not in STRATEGY_REVISION_MAPPING.values()
    expected_parent = "fe4f5a6b7c8d"
    for revision in STRATEGY_REVISION_MAPPING.values():
        assert scripts.get_revision(revision).down_revision == expected_parent
        expected_parent = revision
    # The released Provider branch now legitimately owns some historical IDs
    # in the combined graph; only Strategy's new namespace must remain distinct.
    assert not set(STRATEGY_REVISION_MAPPING.values()).intersection(LEGACY_STRATEGY_REVISIONS)


@pytest.mark.parametrize("legacy", [False, True])
def test_real_alembic_environment_guards_before_ddl_and_commits_safe_upgrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: bool
) -> None:
    """Use real SQLite/Alembic transactions; no Docker or external database."""
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    scripts = tmp_path / "alembic"
    versions = scripts / "versions"
    versions.mkdir(parents=True)
    source = Path(__file__).resolve().parents[3] / "alembic" / "env.py"
    (scripts / "env.py").write_text(source.read_text())
    (versions / "probe.py").write_text(
        "from alembic import op\n"
        "revision = 'safe_probe'\ndown_revision = None\n"
        "def upgrade():\n"
        "    op.execute('CREATE TABLE migration_probe (payload TEXT)')\n"
        "    op.execute(\"INSERT INTO migration_probe VALUES ('preserved')\")\n"
        "def downgrade():\n    raise RuntimeError('not used')\n"
    )
    url = f"sqlite:///{tmp_path / 'state.sqlite'}"
    engine = sa.create_engine(url)
    if legacy:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('ff5a6b7c8d9e')")
            connection.exec_driver_sql("CREATE TABLE strategy_lab_v2_aggregates (payload TEXT)")
            connection.exec_driver_sql("INSERT INTO strategy_lab_v2_aggregates VALUES ('keep')")
    config = Config()
    config.set_main_option("script_location", str(scripts))
    config.set_main_option("sqlalchemy.url", url)
    if legacy:
        with pytest.raises(MigrationHistoryCompatibilityError):
            command.upgrade(config, "head")
    else:
        command.upgrade(config, "head")
    with engine.connect() as connection:
        if legacy:
            assert not sa.inspect(connection).has_table("migration_probe")
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                == "ff5a6b7c8d9e"
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT payload FROM strategy_lab_v2_aggregates"
                ).scalar()
                == "keep"
            )
        else:
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                == "safe_probe"
            )
            assert (
                connection.exec_driver_sql("SELECT payload FROM migration_probe").scalar()
                == "preserved"
            )
    engine.dispose()
