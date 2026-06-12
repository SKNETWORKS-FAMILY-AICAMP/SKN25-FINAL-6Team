FROM nginx:1.27-alpine

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY apps/chatbot/frontend/static /usr/share/nginx/html/chatbot

EXPOSE 80
