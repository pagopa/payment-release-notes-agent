# The Copilot SDK downloads its runtime binary on first use into a per-user
# cache. Baking it into the image at build time is what keeps that off the
# request path: with always_on=false the container is recycled often, so a lazy
# download would be paid on every cold start — and would fail outright if
# egress to the GitHub release CDN is not open from the integrated VNet.
#
# COPILOT_CLI_EXTRACT_DIR pins the location (the binary lands directly there,
# with no version subdirectory) and COPILOT_SKIP_CLI_DOWNLOAD=1 forbids the
# runtime fallback, so a broken bake fails loudly on the first job instead of
# silently reaching for the network in production.
ARG COPILOT_RUNTIME_DIR=/opt/copilot-cli


# ── Stage: local development (FastAPI, native ARM64/AMD64) ───────────────────
FROM python:3.11-slim@sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6 AS local

ARG COPILOT_RUNTIME_DIR
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn

ENV COPILOT_CLI_EXTRACT_DIR=${COPILOT_RUNTIME_DIR}
RUN python -m copilot download-runtime

COPY src/ src/
COPY cicd_contexts/ cicd_contexts/
COPY infrastructure/local_server.py app.py

ENV PYTHONUNBUFFERED=1 LOG_LEVEL=INFO COPILOT_SKIP_CLI_DOWNLOAD=1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7071"]


# ── Stage: production (App Service, linux/amd64, FastAPI) ─────────────────────
FROM --platform=linux/amd64 python:3.11-slim@sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6 AS production

ARG COPILOT_RUNTIME_DIR
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn

ENV COPILOT_CLI_EXTRACT_DIR=${COPILOT_RUNTIME_DIR}
RUN python -m copilot download-runtime

COPY src/ src/
COPY cicd_contexts/ cicd_contexts/
COPY infrastructure/local_server.py app.py

ENV PYTHONUNBUFFERED=1 LOG_LEVEL=INFO COPILOT_SKIP_CLI_DOWNLOAD=1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
