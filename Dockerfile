# ── Stage: local development (FastAPI, native ARM64/AMD64) ───────────────────
FROM python:3.11-slim AS local

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn

COPY src/ src/
COPY cicd_contexts/ cicd_contexts/
COPY infrastructure/local_server.py app.py

ENV PYTHONUNBUFFERED=1 LOG_LEVEL=INFO

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7071"]


# ── Stage: production (App Service, linux/amd64, FastAPI) ─────────────────────
FROM --platform=linux/amd64 python:3.11-slim AS production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn

COPY src/ src/
COPY cicd_contexts/ cicd_contexts/
COPY infrastructure/local_server.py app.py

ENV PYTHONUNBUFFERED=1 LOG_LEVEL=INFO

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
