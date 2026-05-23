# DB Info

Source: `tests/common/test_db_connection.py`

## Connection

| Item | Value |
| --- | --- |
| DBMS | PostgreSQL |
| Host | `100.97.235.15` |
| Port | `5432` |
| Database | `game_cs` |
| User | `game_cs_user` |
| Password | `DB_PASSWORD` environment variable |

## Test Connection

The connection test loads environment variables with `python-dotenv` and uses `psycopg`.

```powershell
$env:DB_PASSWORD = "<password>"
python -m unittest tests.common.test_db_connection
```

If `DB_PASSWORD` is not set, the test is skipped.
