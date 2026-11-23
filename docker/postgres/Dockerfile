FROM postgres:19-alpine@sha256:8b0ff4cdf221f0c53d7fcda681d3b461be725c492cd881c5ec9c0ad25023f188
# Keep upstream initialization, but use Alpine's small account-switching binary.
# Explicit removal also makes the old executable absent from the final image/SBOM.
RUN apk upgrade --no-cache \
    && apk add --no-cache su-exec \
    && grep -q 'exec gosu postgres' /usr/local/bin/docker-entrypoint.sh \
    && sed -i 's/exec gosu postgres/exec su-exec postgres/' /usr/local/bin/docker-entrypoint.sh \
    && rm /usr/local/bin/gosu
