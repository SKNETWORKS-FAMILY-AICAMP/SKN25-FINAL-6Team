# SJ Data Preprocessing Bundle

This folder bundles the source data, processed CSV files, and preprocessing scripts used before chunking/embedding handoff.

## Folder Structure

- `raw_data/`
  - Original or upstream source CSV/TXT files.
  - Includes Naver Cafe notice/guide data, policy text, privacy text, and FAQ source CSVs.
- `processed_data/`
  - Preprocessed outputs used for `sj_documents` and downstream chunk/embedding work.
  - Includes `test_documents_chunks_202606151549.csv`, which is the chunk CSV the team decided to keep using.
- `scripts/`
  - Preprocessing and loading scripts copied from the working data pipeline.

## Naming Replacements Already Applied

- Game name: old game names are normalized to `일상` / `Daily`.
- Company name: old company names are normalized to `유니버스`.
- Guide character name: old guide names are normalized to `일상이`.
- Service names with the `HoYo` prefix are normalized to `유니`, for example `HoYoSketch` -> `유니Sketch` and `HoYoWiki` -> `유니Wiki`.
- Broken placeholder text such as `???? 통행증`, `???? ???? APP`, and `???: 물` is normalized in preprocessing code.
- Other game names in cross-game support lists were removed, or generalized to:
  - `《일상》과 같은 유니버스 제공 게임 제품.`

These rules live in `scripts/make_ihy_documents_csv.py` so the processed CSVs can be regenerated instead of manually edited.

## Regenerating Processed CSVs

From the original workspace layout:

```powershell
python docs\data_pipeline-20260615T004219Z-3-001\data_pipeline\preprocess_documents.py
```

This regenerates:

- `hoyoverse_term_policy_notice.csv`
- `hoyoverse_term_policy_notice_chunked.csv`
- `hoyoverse_qna_chunked.csv`

It also normalizes the retained legacy chunk file:

- `test_documents_chunks_202606151549.csv`

## Contact/URL Sanitization

Real contact points were replaced with safe test values:

- Support email: `support@universe.example`
- Payment email: `payment@universe.example`
- Privacy email: `privacy@universe.example`
- Copyright email: `copyright@universe.example`
- Support URL: `https://support.universe.example`
- Account URL: `https://account.universe.example`
- Payment URL: `https://payment.universe.example`
- Privacy URL: `https://privacy.universe.example`
- Phone number: `000-0000-0000`

## DB Loading

To update only `sj_documents` without touching chunks or embeddings:

```powershell
python docs/sj_data_preprocessing/scripts/load_sj_documents_to_db.py --documents-only
```

From the original workspace layout, the currently tested command was:

```powershell
python docs\data_pipeline-20260615T004219Z-3-001\data_pipeline\load_sj_documents_to_db.py --documents-only
```

Result at handoff:

```text
upserted sj_documents: 1068
db sj_documents count: 1068
sj_documents_chunks and sj_documents_embeddings were not modified
```

## Handoff Note

Chunking and embedding are intentionally left for the next team member. Avoid running the loader without `--documents-only` unless the team explicitly wants to rebuild `sj_documents_chunks` and `sj_documents_embeddings`.

