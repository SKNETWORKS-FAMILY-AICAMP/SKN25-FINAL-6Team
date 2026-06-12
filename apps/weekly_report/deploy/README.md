# Dashboard 배포 가이드

프론트엔드 없이 **백엔드 + 정기 Slack 리포트 발송**만 운영하는 구성입니다.

## 구성 서비스

| 서비스 | 역할 |
|--------|------|
| `dashboard-backend` | FastAPI + APScheduler (매주 월요일 09:00 KST 자동 발송) |
| `dashboard-nginx` | `/dashboard/api/` → `dashboard-backend:8000` 역방향 프록시 |

## 필수 환경변수

프로젝트 루트에 `.env` 파일을 만들거나 EC2 환경변수로 주입합니다.

```env
# Database (DB_HOST=localhost 는 컨테이너 환경에서 동작하지 않습니다)
DB_HOST=<RDS 엔드포인트 또는 EC2 내부 IP>
DB_PORT=5432
DB_USER=
DB_PASSWORD=
DB_NAME=

# Slack
DASHBOARD_SLACK_BOT_TOKEN=xoxb-...
DASHBOARD_WEEKLY_REPORT_CHANNEL=C0123456789   # 채널 ID 권장
DASHBOARD_WEEKLY_REPORT_COMMENT=              # 선택 — PDF 업로드 시 코멘트

# LLM (AI 해석 사용 시)
LLM_API_KEY=
LLM_MODEL=

# 포트 (선택)
DASHBOARD_BACKEND_PORT=8000
DASHBOARD_HTTP_PORT=80
```

## 배포 방법

프로젝트 루트(`SKN25-FINAL-6Team/`)에서 실행합니다.

```bash
# 최초 빌드 및 실행
docker compose -f apps/dashboard/deploy/docker-compose.yml up -d --build

# 상태 확인
docker compose -f apps/dashboard/deploy/docker-compose.yml ps

# 로그 확인
docker compose -f apps/dashboard/deploy/docker-compose.yml logs -f dashboard-backend

# 재시작
docker compose -f apps/dashboard/deploy/docker-compose.yml restart dashboard-backend
```

## 수동 발송 테스트

서버 실행 후 아래 엔드포인트로 즉시 발송을 확인합니다.

```bash
curl -X POST http://localhost:8000/reports/weekly/slack/now \
     -H "Content-Type: application/json" \
     -d '{"days": 7}'
```

## 스케줄러 동작 원리

- `DASHBOARD_WEEKLY_REPORT_CHANNEL` 환경변수가 설정되지 않으면 스케줄러가 시작되지 않습니다.
- `DASHBOARD_WEEKLY_REPORT_AUTOSTART=0` 으로 스케줄러를 비활성화할 수 있습니다.
- DB advisory lock(`pg_try_advisory_lock`)으로 동일 시각에 중복 전송을 방지합니다.
- `--workers 1` 강제 단일 프로세스: APScheduler는 프로세스당 하나여야 합니다.

## 한글 폰트

이미지 빌드 시 `fonts-nanum` (NanumGothic) 을 자동 설치합니다.  
커스텀 폰트를 사용하려면 환경변수로 경로를 지정합니다.

```env
DASHBOARD_WEEKLY_REPORT_FONT_REGULAR=/path/to/font-regular.ttf
DASHBOARD_WEEKLY_REPORT_FONT_BOLD=/path/to/font-bold.ttf
```

## 중단 절차 / 복구

```bash
# 중단 (데이터 보존)
docker compose -f apps/dashboard/deploy/docker-compose.yml stop

# 완전 제거
docker compose -f apps/dashboard/deploy/docker-compose.yml down
```

EC2 재시작 시 `restart: unless-stopped` 설정으로 컨테이너가 자동 재기동됩니다.
