# DB Info

Last verified from the live database on 2026-05-26.

## Connection

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)` |
| Host | `100.97.235.15` |
| Server Address | `100.97.235.15/32` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Password | `DB_PASSWORD` environment variable |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |
| Public Tables | 40 |
| Public Columns | 330 |

## Test Connection

The connection test loads environment variables with `python-dotenv` and uses `psycopg`.

```powershell
$env:DB_PASSWORD = "<password>"
python -m unittest tests.common.test_db_connection
```

If `DB_PASSWORD` is not set, the test is skipped.

## Schema Reference

See `docs/DB/descriptions.md` for table counts, data types, nullability, defaults, primary keys, primary-key defaults, foreign keys, indexes, relationships, and operation workflow usage.

See `docs/DB/notion_data.md` for a Notion-friendly summary of the same schema, current row counts, reduced dataset interpretation, and workflow-oriented table grouping.

## Data Generation Reference

For reduced dataset generation and presentation-facing rationale, use the companion documents under `docs/data_generation/`.

- `docs/data_generation/plan.md`: reduced dataset scope, target counts, hard-case quota, and generation policy
- `docs/data_generation/paper_description.md`: research-grounded rationale for seed-based generation, hard-case supplementation, and privacy/style considerations
- `docs/data_generation/repopulate_reduced_dataset.py`: reproducible script that repopulates the reduced dataset tables
- `docs/data_generation/ppt_data_generation_narrative.md`: presentation narrative for methodology and game-domain considerations

## Verification Scope

- Live metadata checked: PostgreSQL version, current database/user/schema, extensions, public tables, columns, constraints, primary-key defaults, foreign-key rules, and indexes.
- Current public schema includes 20 main tables and 20 `_ex` template/mirror tables.
- Row counts are PostgreSQL `pg_stat_user_tables.n_live_tup` estimates, not exact `COUNT(*)` results.
- Local load artifacts checked: `data/processed/community_users.csv`, `data/processed/qa_ticket.csv`, `notebooks/insert_processed_data.ipynb`, and `notebooks/generate_operation_workflow_sample_data.ipynb`.
- Reduced dataset planning references checked: `docs/data_generation/plan.md`, `docs/data_generation/paper_description.md`, and `docs/data_generation/repopulate_reduced_dataset.py`.
