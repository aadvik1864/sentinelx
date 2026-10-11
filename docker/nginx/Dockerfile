FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3
USER root
RUN apk upgrade --no-cache
COPY docker/nginx/gateway.conf /etc/nginx/conf.d/default.conf
COPY docker/nginx/server.conf docker/nginx/security-headers.conf /etc/nginx/sentinelx/
USER 101
EXPOSE 8080
