docker compose --env-file .env -f docker-compose.airflow.yml up -d --build
중지:
docker compose --env-file .env -f docker-compose.airflow.yml down
상태 확인:
docker compose --env-file .env -f docker-compose.airflow.yml ps


cd deploy
docker compose --env-file .env -f docker-compose.chatbot.yml up -d --build
중지:
docker compose --env-file .env -f docker-compose.chatbot.yml down
상태 확인:
docker compose --env-file .env -f docker-compose.chatbot.yml ps


docker compose --env-file .env -f docker-compose.cs-auto.yml up -d
중지:
docker compose --env-file .env -f docker-compose.cs-auto.yml down
상태 확인:
docker compose --env-file .env -f docker-compose.cs-auto.yml ps
