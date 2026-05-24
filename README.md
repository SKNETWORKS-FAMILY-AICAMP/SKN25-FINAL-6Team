# GameOps Multi-App Monorepo

이 레포지토리는 챗봇, 운영 검수, 대시보드를 한 저장소에서 관리하는 멀티앱 모노레포입니다.

현재 소스 구조는 다음과 같습니다.

```text
src/
├── chatbot
│   ├── frontend
│   └── api
├── operation
│   ├── frontend
│   └── api
└── dashboard
    ├── frontend
    └── api
```

최종 구조는 6개 앱 컨테이너와 공통 인프라를 목표로 합니다. 현재 MVP Docker 배포에서는 실제 구현이 있는 `operation`, `dashboard`만 우선 실행하고, `chatbot` 컨테이너와 라우팅은 주석 처리해 둡니다. PostgreSQL/pgvector는 Docker Compose 안에 띄우지 않고, Tailscale로 접근 가능한 외부 DB를 사용합니다.

```text
nginx
├── /operation      -> operation-frontend
├── /operation/api  -> operation-backend
├── /dashboard      -> dashboard-frontend
└── /dashboard/api  -> dashboard-backend

external PostgreSQL / pgvector over Tailscale
```

## 실행

`.env.example`을 기준으로 `.env`를 만든 뒤 실행합니다. `DB_HOST`에는 `localhost`나 `postgres`가 아니라 Tailscale IP 또는 MagicDNS 이름을 넣습니다.

```env
DB_HOST=100.x.y.z
DB_PORT=5432
DB_USER=...
DB_PASSWORD=...
DB_NAME=...
```

```bash
docker compose up -d --build
docker compose ps
```

접속 주소:

```text
http://localhost/operation/
http://localhost/dashboard/
```

API health check:

```text
http://localhost/operation/api/health
http://localhost/dashboard/api/health
```

## 배포 파일

| 경로 | 역할 |
| --- | --- |
| `docker-compose.yml` | MVP 기준 operation/dashboard 앱 컨테이너와 Nginx 실행. DB는 외부 Tailscale PostgreSQL 사용 |
| `deploy/docker/python-app.Dockerfile` | FastAPI와 Streamlit 앱 공통 Python 이미지 |
| `deploy/nginx/default.conf` | MVP 기준 `/operation`, `/dashboard` 경로 라우팅. `/chatbot` 라우팅은 주석 처리 |
| `deploy/README.md` | Tailscale 외부 DB 기준 배포 가이드 |
| `.dockerignore` | Docker build context 제외 규칙 |

## DB 연결 확인

컨테이너가 Tailscale DB 경로를 볼 수 있는지 확인합니다.

```bash
docker compose exec operation-backend python -c "import os, psycopg; psycopg.connect(host=os.environ['DB_HOST'], port=os.environ['DB_PORT'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], dbname=os.environ['DB_NAME'], connect_timeout=5).close(); print('db ok')"
```

이 명령이 실패하면 앱 문제가 아니라 Docker 컨테이너에서 Tailscale DB 네트워크 경로가 보이지 않는 상태입니다.

## 포트 정책

컨테이너 내부에서는 모든 FastAPI가 `8000`, 모든 Streamlit이 `8501`을 사용합니다. Docker Compose 네트워크에서는 서비스 이름으로 구분되므로 내부 포트가 같아도 충돌하지 않습니다.

로컬에서 컨테이너 없이 직접 실행할 때는 포트를 다르게 사용합니다.

```text
operation API/UI  -> 8001 / 8501
dashboard API/UI  -> 8010 / 8510
chatbot API/UI    -> 구현 시 별도 지정
```

## 현재 제약

`operation`과 `dashboard`는 FastAPI/Streamlit 구현이 있습니다. `chatbot`은 현재 최소 health API와 Streamlit 연결 확인 화면만 있으며, 실제 챗봇 대화 API와 UI는 추가 구현이 필요합니다.
