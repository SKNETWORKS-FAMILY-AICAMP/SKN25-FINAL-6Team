# DB Info

Last verified from the live database on 2026-05-21.

## Connection

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Version | `16.13` |
| Host | `100.97.235.15` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Password | `DB_PASSWORD` environment variable |
| Schema | `public` |
| Extensions | `plpgsql 1.0`, `vector 0.6.0` |

## Test Connection

The connection test loads environment variables with `python-dotenv` and uses `psycopg`.

```powershell
$env:DB_PASSWORD = "<password>"
python -m unittest tests.common.test_db_connection
```

If `DB_PASSWORD` is not set, the test is skipped.

## Schema Reference

See `docs/DB/descriptions.md` for table counts, columns, keys, relationships, and operation workflow usage.

## Verification Scope

- Live metadata checked: PostgreSQL version, public table row estimates, and public indexes.
- Local load artifacts checked: `data/processed/community_users.csv`, `data/processed/qa_ticket.csv`, `notebooks/insert_processed_data.ipynb`, and `notebooks/generate_operation_workflow_sample_data.ipynb`.
