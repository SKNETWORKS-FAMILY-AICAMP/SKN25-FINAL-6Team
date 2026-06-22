# DB Info

Last verified from the live database on 2026-06-18.

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
| Public Tables | 19 |
| Public Columns | 151 |
| Workflow Write Tables | 7 |
| RAG Tables | 3 |

## Test Connection

The connection test loads environment variables with `python-dotenv` and uses `psycopg`.

```powershell
$env:DB_PASSWORD = "<password>"
python -m unittest common.tests.test_db_connection
```

If `DB_PASSWORD` is not set, the DB smoke test is skipped.

## Schema Reference

See `docs/DB/descriptions.md` for exact table counts, data types, nullability, defaults, primary keys, foreign keys, indexes, and per-table column layouts.

See `docs/DB/notion_data.md` for a shorter summary oriented toward Notion and project handoff.

## Current Live-Schema Notes

- The live `public` schema currently has 19 tables and no `_ex` mirror tables.
- The document/RAG store in the live DB is `documents -> documents_chunks -> documents_embeddings`.
- Older docs and some handoff notes still reference `sj_documents`, `test_documents_chunks`, and `test_documents_embeddings_large/small`; those table names are not present in the live `public` schema at this verification point.
- `apps/weekly_report/db/top_requests.py` still references `voc_feedback.topic_keywords` as an optional keyword source, but `voc_feedback` is not part of the live schema described here.
- Workflow write tables now expose database-generated PKs via `IDENTITY`: `answer_draft`, `evidence_docs`, `failed_queries`, `final_response`, `safety_results`, and `ticket_analysis`.

## Data Generation Reference

The local references under `docs/data_generation/` still exist in the repo, but they describe an earlier reduced-dataset workflow and do not match the current live `public` schema one-to-one.

- `docs/data_generation/plan.md`
- `docs/data_generation/paper_description.md`
- `docs/data_generation/repopulate_reduced_dataset.py`
- `docs/data_generation/ppt_data_generation_narrative.md`

## Verification Scope

- Live metadata checked: PostgreSQL version, current database/user/schema, extensions, public tables, columns, primary keys, primary-key defaults, foreign-key rules, and indexes.
- Row counts are exact `COUNT(*)` results at verification time.
- This document reflects the live DB only; repo-local notebooks and generation notes may describe older schema variants.
