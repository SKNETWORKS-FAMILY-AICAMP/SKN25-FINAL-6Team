# CS Auto Deploy

EC2에서는 이 디렉터리의 Compose 파일로 `cs-auto`와 `cs-auto-airflow` 두 컨테이너를 실행한다.

## Runtime

- UI: `http://<EC2_HOST>/cs-auto/`
- API health: `http://<EC2_HOST>/health`
- Airflow: `http://<EC2_HOST>:18080` (`CS_AUTO_AIRFLOW_PORT`로 변경 가능)

## Required `.env`

루트 `.env`에 DB 접속 값을 둔다. 비밀번호와 외부 연동 URL은 이미지에 넣지 않는다.
`apps/cs_auto/deploy/.env.example`을 기준으로 루트 `.env`를 채운다.

```env
DB_HOST=
DB_PORT=5432
DB_USER=game_cs_user
DB_PASSWORD=
DB_NAME=game_cs
LLM_API_KEY=
LLM_MODEL=
CS_AUTO_ROUTING_MODEL=
LLM_TIMEOUT_SECONDS=60
CS_AUTO_HTTP_PORT=80
CS_AUTO_AIRFLOW_PORT=18080
CS_AUTO_REGENERATION_LIMIT=3
NAVER_CAFE_COMMENT_ENDPOINT=
```

## Run

```bash
cd apps/cs_auto/deploy
docker-compose --env-file .\.env up -d --build
docker compose --env-file .\.env ps
```

## Split Deploy

If web/API and Airflow run on different EC2 instances, use separate compose files.
Use separate env files such as `.env.web` and `.env.airflow`. They are still ignored by git because the repo ignores `.env.*`.

### Web/API server

```bash
cd apps/cs_auto/deploy
copy .env.web.example .env.web
docker compose -f docker-compose.web.yml --env-file .\.env.web up -d --build
docker compose -f docker-compose.web.yml --env-file .\.env.web ps
```

### Airflow server

```bash
cd apps/cs_auto/deploy
copy .env.airflow.example .env.airflow
docker compose -f docker-compose.airflow.yml --env-file .\.env.airflow up -d --build
docker compose -f docker-compose.airflow.yml --env-file .\.env.airflow ps
```

Recommended env file names:

- Web/API server: `.env.web`
- Airflow server: `.env.airflow`

Airflow 컨테이너는 `apps/cs_auto/backend/airflow`의 DAG를 읽고, 이미지에 포함된 `data/keywords`와 LLM 환경변수로 분석 agent를 실행한다. `cs-auto` 컨테이너는 nginx가 정적 HTML을 제공하면서 FastAPI/Uvicorn으로 `/api/cs-auto/*`를 프록시한다.

## Airflow DAG Deploy

`apps/cs_auto/backend/airflow/analysis_agent_dag.py`와 `apps/cs_auto/backend/airflow/answer_agent_dag.py`는 현재 Docker 배포 경로에 포함된다.

`apps/cs_auto/backend/agents/answer_agent.py`도 같은 방식으로 Airflow 이미지에 포함된다. `answer_agent_dag.py`가 내부에서 `agents.answer_agent.run_answer_agent()`를 import하므로, DAG 파일만 올라가고 agent 파일이 빠지면 배포가 실패한다.

- `apps/cs_auto/deploy/docker/airflow.Dockerfile`이 `apps/cs_auto/backend` 전체를 `/opt/airflow/cs_auto_backend`로 복사한다.
- `AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/cs_auto_backend/airflow` 로 설정되어 있어 Airflow가 위 디렉터리의 DAG 파일을 자동으로 읽는다.
- 따라서 `analysis_agent_dag.py`를 수정한 뒤 `docker-compose --env-file .\.env up -d --build`로 이미지를 다시 빌드하면 변경 사항이 배포된다.

이미지 내부 포함 여부는 아래 스크립트로 바로 검증할 수 있다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-airflow-deploy.ps1
```

이 스크립트는 Airflow Docker 이미지를 새로 빌드한 뒤 아래 파일들이 이미지 안에 실제로 존재하는지 검사한다.

- `/opt/airflow/cs_auto_backend/agents/answer_agent.py`
- `/opt/airflow/cs_auto_backend/airflow/answer_agent_dag.py`

배포 후 Airflow UI에서 확인할 DAG:

- `cs_auto_analysis_agent_daily`
- `cs_auto_answer_agent_daily`

실행에 필요한 조건:

- 루트 `.env`에 `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`이 있어야 한다.
- `analysis_agent_dag.py`는 내부에서 `agents.analysis_agent.run_analysis_agent()`를 호출하므로 `LLM_API_KEY`, `LLM_MODEL`도 필요하다.
- 키워드 파일은 이미지 빌드 시 `data/keywords`가 `/opt/airflow/data/keywords`로 복사되고, `CS_AUTO_KEYWORD_DIR` 환경변수로 연결된다.

배포 후 점검 순서:

1. `docker-compose --env-file .\.env up -d --build`
2. Airflow UI(`http://<EC2_HOST>:18080`)에서 `cs_auto_analysis_agent_daily`가 보이는지 확인
3. DAG를 수동 실행하거나 스케줄 시각 이후 run log에서 `run_analysis_agent` task 성공 여부 확인


## Airflow old run 정리

`queued` 또는 `running` 상태로 남아 있는 예전 run 이 새 검증을 방해하면, Airflow 컨테이너 안에서 대상 DAG run 상태를 먼저 확인한 뒤 정리한다.

```powershell
docker compose --env-file .\.env exec airflow airflow dags list-runs -d cs_auto_answer_agent_daily
docker compose --env-file .\.env exec airflow airflow dags state cs_auto_answer_agent_daily <run_id> failed
```

특정 실행일 기준으로 task instance 를 다시 비워야 하면 아래처럼 정리한다.

```powershell
docker compose --env-file .\.env exec airflow airflow tasks clear cs_auto_answer_agent_daily --start-date <YYYY-MM-DDTHH:MM:SS+09:00> --end-date <YYYY-MM-DDTHH:MM:SS+09:00> --yes
```

재검증 순서는 다음 기준으로 맞춘다.

1. old run 을 `failed` 처리하거나 필요한 범위만 `clear` 한다.
2. `cs_auto_answer_agent_daily` 를 다시 trigger 한다.
3. `run_answer_agent` task log 에서 `draft`, `evidence`, `safety_results` 저장 완료 여부와 `StringDataRightTruncation` 재발 여부를 확인한다.

http://localhost/cs-auto/cs_automation.html
