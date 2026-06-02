# cs_auto Airflow Refactor

## Goal

- Stop depending on graph orchestration for scheduled execution.
- Expose direct Python function entrypoints that Airflow can call per `ticket_id`.
- Keep LLM usage, prompt schemas, and DB writes, but remove graph orchestration from the batch path.

## New Entrypoints

Implemented in:

- [service/batch/operation.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/service/batch/operation.py:1)

Primary functions:

- `run_analysis_step(ticket_id, persist=True)`
- `run_draft_step(ticket_id, persist_analysis=True, persist_draft=True)`
- `run_review_step(ticket_id, persist_analysis=True, persist_draft=True, persist_review=True)`

Lower-level functions:

- `load_ticket_payload(ticket_id)`
- `classify_ticket(ticket)`
- `persist_analysis_result(result)`
- `build_draft_inputs(ticket, analysis_result)`
- `persist_draft_result(result, analysis_id)`
- `review_draft_result(result)`
- `persist_review_result(result, retry_count=0)`

## Intended Airflow Usage

### 02:00 analysis

```python
from service.batch.operation import run_analysis_step

def analyze_ticket(ticket_id: int) -> dict:
    result = run_analysis_step(ticket_id, persist=True)
    return {
        "ticket_id": result.ticket_id,
        "analysis_id": result.analysis_id,
        "query_route": result.analysis.query_route,
        "target_route": result.analysis.target_route,
    }
```

### 03:00 draft

```python
from service.batch.operation import run_draft_step

def draft_ticket(ticket_id: int) -> dict:
    result = run_draft_step(
        ticket_id,
        persist_analysis=True,
        persist_draft=True,
    )
    return {
        "ticket_id": result.ticket_id,
        "draft_id": result.draft_id,
        "has_customer_answer": bool(result.answer_draft),
        "has_urgent_alert": bool(result.urgent_draft),
    }
```

### Optional review/safety step

```python
from service.review.operation import run_review_step

def review_ticket(ticket_id: int) -> dict:
    result = run_review_step(ticket_id, persist_review=True)
    return {
        "ticket_id": result.ticket_id,
        "approval_route": result.approval_route,
        "safety_id": result.safety_id,
    }
```

## What Changed

- The batch path no longer requires a graph runtime.
- The API path was also switched to direct service execution instead of graph invocation.
- Ticket loading, classification, context enrichment, drafting, review, and persistence now have callable service boundaries.

## Scheduled Jobs In Docker Airflow

- `cs_auto_ticket_analysis_daily`
  - Schedule: every day at `02:00` Asia/Seoul
  - Task: `run_ticket_analysis_batch(limit=500)`
  - Candidate rule: `qa_ticket.status IN ('pending', 'human_review_pending')` and no latest `ticket_analysis`
- `cs_auto_naver_cafe_draft_daily`
  - Schedule: every day at `03:00` Asia/Seoul
  - Task: `run_naver_cafe_draft_batch(limit=500)`
  - Candidate rule: `qa_ticket.source_type = 'naver_cafe'`, latest `ticket_analysis` exists, and no latest `answer_draft` or `final_response`
- Airflow files:
  - DAGs: `apps/cs_auto/deploy/airflow/dags/`
  - Python batch entrypoints: `apps/cs_auto/backend/batch/airflow_jobs.py`
  - Docker image: `apps/cs_auto/deploy/docker/airflow.Dockerfile`
  - Compose services: root `docker-compose.yml` under profile `airflow`
- Result log files:
  - default path: `logs/operation/airflow/*.json`
  - override: `CS_AUTO_BATCH_LOG_DIR`
- Python test entrypoint:
  - `apps/tests/cs_auto_tests/test_airflow_jobs.py`

## Frontend Review Flow

- The batch writes into the same tables the frontend already reads:
  - `ticket_analysis`
  - `answer_draft`
  - `evidence_docs`
- The existing frontend keeps working:
  - operators see batch-created analysis and draft via `GET /tickets`, `GET /tickets/today`, `GET /tickets/{ticket_id}`
  - operators can still edit via `PATCH /drafts/{draft_id}`
  - operators can still approve via `POST /drafts/{draft_id}/approve`
  - operators can still regenerate via `POST /drafts/{draft_id}/reject` then `POST /tickets/{ticket_id}/run-workflow`

## What Did Not Change

- Existing prompt models in [prompts.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/workflow/prompts.py:14)
- Existing LLM agent implementations in:
  - [intake.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/workflow/agents/intake.py:13)
  - [context.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/workflow/agents/context.py:125)
  - [drafting.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/workflow/agents/drafting.py:13)
  - [review.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/workflow/agents/review.py:13)
- Existing DB target tables:
  - `ticket_analysis`
  - `answer_draft`
  - `evidence_docs`
  - `safety_results`

## Current Limitation

- The new service layer still reuses `OperationState` as an internal DTO when calling the existing LLM step functions.
- That is a state-model dependency, not a graph-orchestration dependency.
- If we want a stricter separation, the next step is to replace `OperationState` with smaller batch DTOs for each step.

## Next Refactor

1. Move route-query SQL helpers out of `workflow.nodes` entirely.
2. Replace `OperationState` usage inside the batch service with smaller step-specific DTOs.
3. Add retry / alert policy per Airflow task failure mode.
4. Split operator-triggered regenerate into "reuse latest analysis" and "force reanalysis" options if needed.
