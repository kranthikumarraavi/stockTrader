# ─── Trading Service ─────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgomp1 && rm -rf /var/lib/apt/lists/*

COPY packages/ packages/
RUN pip install --no-cache-dir \
    packages/common-config \
    packages/common-logging \
    packages/common-utils \
    packages/common-types \
    packages/common-db

COPY services/trading-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY models/ models/
COPY storage/ storage/
COPY services/trading-service/app/ app/
COPY .env* ./

ENV PYTHONPATH=/app
EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
