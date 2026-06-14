FROM nginx:1.27-alpine

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY apps/chatbot/frontend/static /usr/share/nginx/html/chatbot
COPY apps/cs_auto/frontend /usr/share/nginx/html/cs-auto

EXPOSE 80
