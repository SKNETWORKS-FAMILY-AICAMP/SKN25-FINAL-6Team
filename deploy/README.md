# Deploy

루트 `deploy/` 아래에 서비스별 Compose 파일을 분리했다.

## Files

- `docker-compose.cs_auto.yml`: `cs_auto` 웹/API 배포
- `docker-compose.chatbot.yml`: `chatbot` 웹/API 배포
- `docker-compose.airflow.yml`: `cs_auto` Airflow 배포
- `.env.example`: 공통 환경변수 예시

## Usage

프로젝트 루트에서:

```powershell
copy .\deploy\.env.example .\.env
docker-compose -f .\deploy\docker-compose.cs_auto.yml --env-file .\.env up -d --build
docker-compose -f .\deploy\docker-compose.chatbot.yml --env-file .\.env up -d --build
docker-compose -f .\deploy\docker-compose.airflow.yml --env-file .\.env up -d --build
```

Linux에서는 한 번에 올리는 스크립트를 사용할 수 있다.

```bash
cp deploy/.env.example .env
chmod +x deploy/manage-all.sh
./deploy/manage-all.sh up
./deploy/manage-all.sh ps
```

기본 포트는 동시에 올려도 충돌하지 않게 분리되어 있다.

- `cs_auto`: `http://<HOST>:8081`
- `chatbot`: `http://<HOST>:8082/chatbot/`
- `airflow`: `http://<HOST>:18080`

각 서비스 상태 확인:

```powershell
docker-compose -f .\deploy\docker-compose.cs_auto.yml --env-file .\.env ps
docker-compose -f .\deploy\docker-compose.chatbot.yml --env-file .\.env ps
docker-compose -f .\deploy\docker-compose.airflow.yml --env-file .\.env ps
```

같은 EC2에서 여러 서비스를 동시에 띄우는 기본값:

```env
CS_AUTO_HTTP_PORT=8081
CHATBOT_HTTP_PORT=8082
CS_AUTO_AIRFLOW_PORT=18080
```

80/443 앞단 도메인 라우팅이 필요하면 이후 공용 nginx 또는 ALB를 별도로 두는 편이 낫다.
