# ── Stage: local development (FastAPI, native ARM64/AMD64, no Azure runtime) ──
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


# ── Stage: production (Azure Functions, linux/amd64) ─────────────────────────
FROM --platform=linux/amd64 mcr.microsoft.com/azure-functions/python:4-python3.11 AS production

WORKDIR /home/site/wwwroot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY cicd_contexts/ cicd_contexts/
COPY infrastructure/function_app.py .
COPY infrastructure/host.json .

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO
