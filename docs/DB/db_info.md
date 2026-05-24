# DB Info

Last verified from the live database on 2026-05-24.

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
| Public Tables | 20 |
| Public Columns | 165 |

## Test Connection

The connection test loads environment variables with `python-dotenv` and uses `psycopg`.

```powershell
$env:DB_PASSWORD = "<password>"
python -m unittest tests.common.test_db_connection
```

If `DB_PASSWORD` is not set, the test is skipped.

## Schema Reference

See `docs/DB/descriptions.md` for table counts, data types, nullability, defaults, primary keys, primary-key defaults, foreign keys, indexes, relationships, and operation workflow usage.

## Verification Scope

- Live metadata checked: PostgreSQL version, current database/user/schema, extensions, public tables, columns, constraints, primary-key defaults, foreign-key rules, and indexes.
- Row counts are PostgreSQL `pg_stat_user_tables.n_live_tup` estimates, not exact `COUNT(*)` results.
- Local load artifacts checked: `data/processed/community_users.csv`, `data/processed/qa_ticket.csv`, `notebooks/insert_processed_data.ipynb`, and `notebooks/generate_operation_workflow_sample_data.ipynb`.
