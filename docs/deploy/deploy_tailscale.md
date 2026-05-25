# Tailscale DB 기반 Docker 배포

## 1. 배포 전제

현재 배포 구조는 PostgreSQL/pgvector를 Docker Compose 내부에 띄우지 않는다. DB는 Windows 또는 별도 서버에서 Tailscale로 접근 가능한 외부 인프라로 둔다.

MVP 배포에서는 실제 구현이 있는 `operation`, `dashboard`만 Docker로 띄운다. `chatbot`은 실제 대화 API/UI 구현 전까지 `docker-compose.yml`과 Nginx 라우팅에서 주석 처리한다. Redis도 현재 코드에서 사용하지 않으므로 Compose 기본 실행에서 제외한다.

```text
Docker Compose
|-- nginx
|-- operation-frontend
|-- operation-backend
|-- dashboard-frontend
`-- dashboard-backend

External
`-- PostgreSQL / pgvector over Tailscale
```

## 2. 이유

현재 DB는 Tailscale ACL/네트워크 허용을 통해 Windows 환경에서 접근하고 있다. 이 DB를 계속 사용한다면 Compose에 `postgres` 컨테이너를 묶으면 안 된다.

- Compose 내부 `postgres`는 새 빈 DB다.
- 기존 Tailscale DB 데이터와 자동으로 연결되지 않는다.
- 앱 컨테이너의 `DB_HOST=postgres` 설정은 외부 DB가 아니라 Compose 내부 서비스를 바라보게 만든다.

따라서 백엔드 컨테이너는 `.env`의 Tailscale DB 접속 정보를 그대로 사용한다.

## 3. `.env` 설정

`DB_HOST`에는 `localhost`를 쓰지 않는다. 컨테이너 내부의 `localhost`는 컨테이너 자신이다.

```env
DB_HOST=100.x.y.z
DB_PORT=5432
DB_USER=...
DB_PASSWORD=...
DB_NAME=...
DB_CONNECT_TIMEOUT=15
```

Tailscale MagicDNS를 쓰는 경우:

```env
DB_HOST=my-db-machine.tailnet-name.ts.net
```

## 4. Compose 구성

`docker-compose.yml`에는 기본적으로 다음 서비스만 포함한다.

```text
nginx
operation-frontend
operation-backend
dashboard-frontend
dashboard-backend
```

백엔드 서비스는 공통으로 다음 형태를 따른다.

```yaml
env_file:
  - .env
```

`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`은 Compose에서 덮어쓰지 않는다.

## 5. 실행

```bash
docker compose up -d --build
docker compose ps
```

접속 주소:

```text
http://localhost/operation/
http://localhost/dashboard/
```

## 6. DB 연결 검증

컨테이너에서 외부 Tailscale DB가 보이는지 확인한다.

```bash
docker compose exec operation-backend python -c "import os, psycopg; psycopg.connect(host=os.environ['DB_HOST'], port=os.environ['DB_PORT'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], dbname=os.environ['DB_NAME'], connect_timeout=5).close(); print('db ok')"
```

성공하면 Compose 앱이 외부 DB를 사용할 수 있다.

실패하면 다음을 확인한다.

- Docker 컨테이너가 Tailscale 라우팅을 탈 수 있는지
- Tailscale ACL에서 Docker 실행 호스트 또는 Subnet route 접근이 허용되는지
- `DB_HOST`가 Windows 전용 `localhost`가 아닌 실제 Tailscale IP/MagicDNS인지
- DB 방화벽과 PostgreSQL `listen_addresses`, `pg_hba.conf`가 해당 경로를 허용하는지

## 7. 개발 기준

로컬 개발 중 Docker 컨테이너가 Tailscale DB를 보지 못하면 앱을 Windows에서 직접 실행한다.

```bash
python -m uvicorn src.operation.api.main:app --host 127.0.0.1 --port 8001
python -m streamlit run src/operation/frontend/app.py --server.port 8501
```

배포나 시연 환경에서는 Docker 실행 호스트에서 Tailscale DB 접근이 되는지 먼저 검증한 뒤 Compose를 올린다.
