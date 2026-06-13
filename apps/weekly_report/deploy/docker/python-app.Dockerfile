# ──────────────────────────────────────────────────────────────
# 대시보드 백엔드 이미지
# Build context: 프로젝트 루트 (SKN25-FINAL-6Team/)
# 실행 예시:
#   docker compose -f apps/dashboard/deploy/docker-compose.yml up -d --build
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # 주간 리포트 모듈과 공통 패키지를 모두 import할 수 있도록 두 경로를 추가한다.
    PYTHONPATH=/app/packages/common-python/src:/app/apps/weekly_report

WORKDIR /app/apps/weekly_report

# ── 시스템 패키지 ─────────────────────────────────────────────────────────────
# fonts-nanum    : NanumGothic 한글 폰트 (pdf.py가 /usr/share/fonts/truetype/nanum/ 탐색)
# fontconfig     : fc-cache로 폰트 캐시 갱신 → matplotlib 인식
# build-essential: pycairo 소스 컴파일에 필요한 gcc 포함
#                  (xhtml2pdf → svglib → pycairo 의존성 체인)
# libcairo2-dev  : pycairo 빌드 시 Cairo 헤더 파일 제공
# libcairo2      : pycairo 런타임 의존성 (purge 후에도 유지)
# pkg-config     : pycairo가 Cairo 라이브러리 경로를 찾는 데 사용
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fontconfig \
        fonts-nanum \
        build-essential \
        libcairo2-dev \
        libcairo2 \
        pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

# 공통 패키지와 대시보드 백엔드 코드를 복사한다.
# requirements.txt는 WORKDIR(/app/apps/dashboard/backend) 기준으로 읽힌다.
COPY packages/ /app/packages/
COPY apps/weekly_report/ /app/apps/weekly_report/

# pip 설치 완료 후 빌드 도구만 제거해 이미지 크기를 줄인다.
# libcairo2는 pycairo 런타임에 필요하므로 남긴다.
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && apt-get purge -y build-essential libcairo2-dev pkg-config \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

# workers=1 필수:
#   APScheduler는 프로세스 안에서 백그라운드 스레드로 동작한다.
#   워커가 여러 개이면 각각 스케줄러를 시작해 DB advisory lock 경쟁이 발생한다.
#   락이 중복 전송을 막아주기는 하지만, 스케줄러 스레드를 낭비하는 구조가 된다.
#   수평 확장이 필요해지면 DASHBOARD_WEEKLY_REPORT_AUTOSTART=0으로 스케줄러를 끄고
#   별도 단일 스케줄러 컨테이너를 운영하는 방식으로 전환한다.
CMD ["python", "-m", "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
