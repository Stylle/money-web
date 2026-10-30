# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data WEB_DIR=/app/web
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --no-compile -r requirements.lock \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app \
    && mkdir /data && chown app:app /data
COPY --chown=app:app backend/app ./app
COPY --from=web --chown=app:app /web/dist ./web
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 CMD ["python", "-m", "app.healthcheck"]
CMD ["python", "-m", "app.container"]
