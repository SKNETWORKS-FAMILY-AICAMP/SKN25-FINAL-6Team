FROM nginx:1.27-alpine

COPY deploy/nginx/chatbot.conf /etc/nginx/conf.d/default.conf
COPY apps/chatbot/frontend/static /usr/share/nginx/html/chatbot

EXPOSE 80
