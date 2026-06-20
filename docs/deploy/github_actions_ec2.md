# GitHub Actions -> AWS EC2 자동 배포

이 저장소는 Docker Compose 기반 배포 파일이 이미 있으므로, 가장 단순한 자동 배포 방식은 아래 흐름이다.

1. GitHub에 `main` 브랜치로 push
2. GitHub Actions에서 테스트 실행
3. 테스트가 성공하면 EC2에 SSH 접속
4. 서버에서 최신 `main`을 pull
5. `docker compose up -d --build`로 서비스 재기동

## 추가된 워크플로

- `.github/workflows/ci.yml`
- `.github/workflows/deploy-chatbot.yml`
- `.github/workflows/deploy-cs-auto.yml`

## GitHub Secrets

### Chatbot EC2

- `AWS_CHATBOT_HOST`
- `AWS_CHATBOT_USER`
- `AWS_CHATBOT_SSH_KEY`
- `AWS_CHATBOT_PORT`
- `AWS_CHATBOT_APP_DIR`

### CS Auto EC2

- `AWS_CS_AUTO_HOST`
- `AWS_CS_AUTO_USER`
- `AWS_CS_AUTO_SSH_KEY`
- `AWS_CS_AUTO_PORT`
- `AWS_CS_AUTO_APP_DIR`

`AWS_*_APP_DIR` 는 EC2 안에서 이 저장소가 clone 되어 있는 경로다. 예시는 `/home/ubuntu/SKN25-FINAL-6Team`.

## EC2 선행 작업

각 EC2 서버에 아래가 먼저 되어 있어야 한다.

1. Docker / Docker Compose 설치
2. 저장소 clone
3. `deploy/.env` 구성
4. Git pull 이 가능한 인증 구성

서버에서 직접 `git pull` 하므로, EC2 쪽에도 GitHub 접근 권한이 있어야 한다. 보통 아래 둘 중 하나를 쓴다.

- 저장소 Deploy Key
- GitHub Personal Access Token

## 추천 구조

처음에는 아래 구조가 가장 단순하다.

- `chatbot` EC2 1대
- `cs_auto` EC2 1대
- `main` push 시 각 서버에서 해당 compose만 재기동

## 주의점

- 이 방식은 "서버에서 직접 pull 후 재기동" 방식이라 단순하지만, 서버 working tree가 더러우면 `git pull --ff-only` 가 실패할 수 있다.
- 서버에서 수동 수정은 하지 않는 운영 규칙이 필요하다.
- 더 안정적으로 가려면 다음 단계에서 ECR + immutable image tag 배포로 바꾸는 게 좋다.

## main에 바로 반영되게 운영할 때 권장

`main`에 push만 하면 바로 배포되게 할 수는 있지만, 최소한 아래는 같이 두는 게 안전하다.

1. `main` 브랜치 보호
2. Pull Request 머지로만 `main` 반영
3. CI 성공 필수
4. 필요한 경우 수동 승인 환경(`environment`) 추가

지금 추가한 워크플로는 "CI 성공 시 main 자동 배포" 기준이다.
