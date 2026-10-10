FROM nginxinc/nginx-unprivileged:stable-alpine
COPY docker/nginx/gateway.conf /etc/nginx/conf.d/default.conf
COPY docker/nginx/server.conf docker/nginx/security-headers.conf /etc/nginx/sentinelx/
USER 101
EXPOSE 8080
