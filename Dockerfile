# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
ARG PNPM_VERSION=11.25.0
RUN npm install --global pnpm@${PNPM_VERSION}
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WARDCAST_ROOT=/app
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 wardcast
COPY requirements.lock pyproject.toml README.md LICENSE DATA_LICENSE.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir --no-deps -e .
COPY artifacts/demo.json artifacts/models.joblib ./artifacts/
COPY data/source_manifest.json ./data/
COPY data/processed/panel.parquet data/processed/panel.csv data/processed/quality.json ./data/processed/
COPY --from=frontend /build/frontend/dist ./frontend/dist
USER wardcast
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8).read()"
CMD ["wardcast", "serve", "--host", "0.0.0.0", "--port", "8000"]
