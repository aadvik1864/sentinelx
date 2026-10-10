FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home sentinelx
COPY --chown=sentinelx:sentinelx backend/ /app/
COPY --chown=sentinelx:sentinelx detection-rules/ /detection-rules/
COPY --chown=sentinelx:sentinelx collectors/ /app/collectors/
USER sentinelx
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
