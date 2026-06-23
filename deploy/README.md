docker compose --env-file .env -f docker-compose.chatbot.yml up -d --build
docker compose --env-file .env -f docker-compose.cs-auto.yml up -d --build
docker compose --env-file .env -f docker-compose.airflow.yml up -d --build

docker compose --env-file .env -f docker-compose.chatbot.yml ps
docker compose --env-file .env -f docker-compose.cs-auto.yml ps
docker compose --env-file .env -f docker-compose.airflow.yml ps

docker compose --env-file .env -f docker-compose.chatbot.yml down
docker compose --env-file .env -f docker-compose.cs-auto.yml down
docker compose --env-file .env -f docker-compose.airflow.yml down
