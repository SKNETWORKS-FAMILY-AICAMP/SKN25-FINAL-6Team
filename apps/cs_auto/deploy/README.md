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

Airflow 컨테이너는 `apps/cs_auto/backend/airflow`의 DAG를 읽고, 이미지에 포함된 `data/keywords`와 LLM 환경변수로 분석 agent를 실행한다. `cs-auto` 컨테이너는 nginx가 정적 HTML을 제공하면서 FastAPI/Uvicorn으로 `/api/cs-auto/*`를 프록시한다.


http://localhost/cs-auto/cs_automation.html
