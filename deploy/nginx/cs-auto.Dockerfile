FROM nginx:1.27-alpine

COPY deploy/nginx/cs-auto.conf /etc/nginx/conf.d/default.conf
COPY apps/cs_auto/frontend /usr/share/nginx/html/cs-auto

EXPOSE 80
