# Strategy migration identifier repair

Prepared under the explicit 2026-10-15 coordinator task. This is source repair
and compatibility admission, not permission to migrate any deployed database.
No upstream migration, database row, applied revision or sibling file was changed.

## Collision audit and new source namespace

| Prior Strategy ID | Unique Strategy ID | Strategy operation | Other owner of prior ID |
| --- | --- | --- | --- |
| ff0a1b2c3d4e | slv2_0001 | 43-table storage schema | TC2000 OHLCV derivation provenance |
| ff1a2b3c4d5e | slv2_0002 | Dispatch payload storage | TC2000 adjustment observations |
| ff2a3b4c5d6e | slv2_0003 | Worker settlements | TC2000 adjustment-factor fields |
| ff3a4b5c6d7e | slv2_0004 | Worker recoveries | No collision found; descendant chain renamed together |
| ff4a5b6c7d8e | slv2_0005 | Search-attempt uniqueness | No collision found; descendant chain renamed together |
| ff5a6b7c8d9e | slv2_0006 | Forward lifecycle receipts | Provider explicit quota/limit policy |
| ff6a7b8c9d0e | slv2_0007 | Dispatch checkpoint evidence | No collision found; descendant chain renamed together |
| ff7a8b9c0d1e | slv2_0008 | Active lease uniqueness | No collision found; descendant chain renamed together |

The shared parent remains `fe4f5a6b7c8d`; Strategy forms a separate unique
linear chain. Original upgrade/downgrade bodies and DDL are unchanged. The
pre-repair source `b85a4b9cb6a1bde93605f8f91c53add466782834` retains all original
scripts in Git for audit. Existing applied IDs are never treated as aliases
for the new IDs. No `stamp`, version UPDATE, reset, drop or replay against an
existing Strategy schema is performed by this repair.

## Interim accepted-ETF graph alignment

The accepted Provider+ETF staging release makes the actual current graph
available for an interim reconciliation. At Strategy source `b9906150`,
Alembic reports exactly two heads: accepted ETF `d1e7f2a9c4b6` (parent
`b6e9a42d1c73`) and Strategy `slv2_0009` (parents `b6e9a42d1c73` and
`slv2_0008`). Strategy adds `slv2_0010` as a no-DDL merge revision with those
two heads as parents. The migration graph regression requires exactly
`slv2_0010` as the interim single head and asserts both parent edges and shared
ancestry; it does not admit multiple heads or rewrite either revision.

This is not the final combined graph. TC2000 is not yet an accepted staged
dependency. After its exact green release, merge only that released source,
recompute ScriptDirectory heads and identifier uniqueness, and add another
Strategy-owned no-DDL merge only if the actual resulting graph requires one.
No migration is run against any database in this source-only context. Existing
revision rows, schema, data, and both histories remain untouched.

## Database compatibility before any upgrade

`alembic/env.py` calls the read-only compatibility check before migration DDL or
version bookkeeping, covering CLI/entrypoint and Strategy startup invocations.
The connection transaction encloses both admission and migrations so a normal
upgrade still commits and a refusal cannot mutate version/data rows.

| Database evidence | Admission and required action |
| --- | --- |
| Fresh database or noncolliding version | Normal Alembic graph processing; no version translation |
| Old Strategy head, including ff3/ff4/ff6/ff7 | Stop before migrations. Inventory schema, version rows and provenance; reviewed recovery required |
| Any colliding current head plus any Strategy table | Stop as legacy Strategy or mixed history; no guess based on the version string |
| Colliding current head without an installed matching upstream owner script | Stop; this branch alone cannot interpret that upstream history |
| Upstream owner script installed, no Strategy tables, distinguishing upstream columns present | Admit normal graph processing; leave upstream version and data untouched |
| Upstream script installed but expected schema markers missing | Stop as partial/unknown history |

The upstream signatures are admission sanity checks, not proof of complete
schema equivalence or an automatic recovery procedure. They refer to original
upstream filenames and column names only, without importing unstaged product
implementations. Combined source, types, constraints and runtime behavior still
need validation after accepted staging integration. Nonstandard version tables
or schemas require explicit configuration review before use.

## Conditional handling if an actual retained database is identified

No live or retained legacy/mixed database has been identified, and no database
inventory or upgrade has been performed. There is no current human decision
blocking this branch. The guard already fails closed for ambiguous legacy
histories, so unknown databases remain preserved and stopped rather than
rewritten.

If a concrete database is later found, first identify its exact source revision,
all current version rows, complete Strategy/upstream schema and an approved
backup/restore point. Preserve all existing data while gathering this evidence;
a revision row alone cannot establish which DDL history was executed. Only if
continued use requires converting that database should the owning
operator/coordinator decide on a narrowly specified, schema-verified metadata
transition or retain it on its original isolated migration history. Any
transition must prove row/schema preservation, map all current heads (including
descendants), prevent upstream migrations from being silently skipped and pass
PostgreSQL migration regression before operational use. Never blindly stamp a
common head or the new Strategy head.

## Regression evidence and integration boundary

Lightweight SQLite/Alembic tests exercise real version/data rows, read-only SQL
admission, each old Strategy marker, recognized upstream and mixed/partial
histories, early refusal through the real env.py, and committed ordinary upgrades.
Static graph tests check duplicate IDs, the unique head and parent chain.
Original migration ASTs excluding revision metadata match all eight new files.
Read-only scans found no slv2_0001–slv2_0008 IDs in Provider/ETF/TC migrations.

No heavy Docker gate or live database migration was started. PostgreSQL upgrade
compatibility and the required full application/CI profile remain pending for
the reconciled source. Actual combined consumers still require green accepted
Provider → ETF → TC2000 staging. No checkpoint acceptance or product integration
is implied by this repair.
