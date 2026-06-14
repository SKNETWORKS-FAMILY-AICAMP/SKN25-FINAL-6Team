# Deploy

AWS 서버에서 `deploy/` 디렉터리 기준으로 공통 `nginx`와 `chatbot`, `cs_auto`, `airflow`를 각각 독립적으로 올리는 배포 구조입니다.

## Files

- `docker-compose.nginx.yml`: 공통 `nginx`
- `docker-compose.chatbot.yml`: `chatbot-backend`
- `docker-compose.cs-auto.yml`: `cs-auto-backend`
- `docker-compose.airflow.yml`: `cs_auto` Airflow
- `docker-compose.web_0614.yml`: 이전 묶음 실행 방식 백업
- `.env.example`: 공통 환경 변수 예시
- `init-shared-network.sh`: 공통 Docker network 생성 스크립트

## First Run

```sh
cd deploy
cp .env.example .env
sh ./init-shared-network.sh
```

`.env`에서 최소한 아래 값들은 채워야 합니다.

- `DB_HOST`
- `DB_PASSWORD`
- `LLM_API_KEY`

## Start

공통 `nginx`:

```sh
docker-compose --env-file .env -f docker-compose.nginx.yml up -d --build
```

`chatbot`:

```sh
docker-compose --env-file .env -f docker-compose.chatbot.yml up -d --build
```

`cs_auto`:

```sh
docker-compose --env-file .env -f docker-compose.cs-auto.yml up -d --build
```

`airflow`:

```sh
docker-compose --env-file .env -f docker-compose.airflow.yml up -d --build
```

필요한 서비스만 따로 올려도 되고, 네 개를 순서대로 모두 올려도 됩니다.

## Status

```sh
docker-compose --env-file .env -f docker-compose.nginx.yml ps
docker-compose --env-file .env -f docker-compose.chatbot.yml ps
docker-compose --env-file .env -f docker-compose.cs-auto.yml ps
docker-compose --env-file .env -f docker-compose.airflow.yml ps
```

## Stop

```sh
docker-compose --env-file .env -f docker-compose.nginx.yml down
docker-compose --env-file .env -f docker-compose.chatbot.yml down
docker-compose --env-file .env -f docker-compose.cs-auto.yml down
docker-compose --env-file .env -f docker-compose.airflow.yml down
```

## Runtime Paths

- `http://<HOST>:<WEB_HTTP_PORT>/chatbot/`
- `http://<HOST>:<WEB_HTTP_PORT>/chatbot/api/health`
- `http://<HOST>:<WEB_HTTP_PORT>/cs-auto/`
- `http://<HOST>:<WEB_HTTP_PORT>/cs-auto/api/health`
- `http://<HOST>:<CS_AUTO_AIRFLOW_PORT>/`

## Notes

- `nginx`는 공통 정적 파일과 라우팅만 담당합니다.
- `chatbot-backend`와 `cs-auto-backend`는 공통 외부 network(`DEPLOY_SHARED_NETWORK`)를 통해 연결됩니다.
- `nginx`는 백엔드가 아직 떠 있지 않아도 먼저 실행되도록 설정했습니다.
- 컨테이너 안에서 `DB_HOST=localhost`는 컨테이너 자기 자신이므로, 외부 DB를 쓰는 경우 실제 DB 호스트를 넣어야 합니다.
