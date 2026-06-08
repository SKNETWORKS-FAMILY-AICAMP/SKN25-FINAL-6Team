# DB Info

Last verified from the live database on 2026-06-06.

## Connection

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit` |
| Host | `100.97.235.15` |
| Server Address | `100.97.235.15/32` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Password | `DB_PASSWORD` environment variable |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |
| Public Tables | 39 |
| Public Columns | 323 |
| Main Tables | 20 |
| `_ex` Tables | 19 |

## Test Connection

The connection test loads environment variables with `python-dotenv` and uses `psycopg`.

```powershell
$env:DB_PASSWORD = "<password>"
python -m unittest packages.common-python.tests.test_db_connection
```

If `DB_PASSWORD` is not set, the DB smoke test is skipped.

## Schema Reference

See `docs/DB/descriptions.md` for exact table counts, data types, nullability, defaults, primary keys, primary-key defaults, foreign keys, indexes, relationships, and operation workflow usage.

See `docs/DB/notion_data.md` for a Notion-friendly summary of the same schema, current row counts, workflow-oriented table grouping, and ERD snippets.

## Data Generation Reference

For reduced dataset generation and presentation-facing rationale, use the companion documents under `docs/data_generation/`.

- `docs/data_generation/plan.md`: reduced dataset scope, target counts, hard-case quota, and generation policy
- `docs/data_generation/paper_description.md`: research-grounded rationale for seed-based generation, hard-case supplementation, and privacy/style considerations
- `docs/data_generation/repopulate_reduced_dataset.py`: reproducible script that repopulates the reduced dataset tables
- `docs/data_generation/ppt_data_generation_narrative.md`: presentation narrative for methodology and game-domain considerations

## Verification Scope

- Live metadata checked: PostgreSQL version, current database/user/schema, extensions, public tables, columns, constraints, primary-key defaults, foreign-key rules, and indexes.
- Current public schema includes 20 main tables and 19 `_ex` template/mirror tables.
- Row counts are exact `COUNT(*)` results at verification time.
- Local load and generation references checked by path only; live schema and row counts come directly from PostgreSQL.
