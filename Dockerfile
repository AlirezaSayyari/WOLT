FROM node:24-alpine AS web-build

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.12-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin wolt \
    && install -d -o wolt -g wolt /home/wolt/.ssh

COPY --chown=wolt:wolt app ./app
COPY --chown=wolt:wolt migrations ./migrations
COPY --chown=wolt:wolt alembic.ini ./alembic.ini
COPY --from=web-build --chown=wolt:wolt /web/dist ./app/web/static

USER wolt

CMD ["python", "-m", "app.main"]

FROM runtime-base AS test

USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=wolt:wolt tests ./tests
COPY --chown=wolt:wolt scripts ./scripts
USER wolt
CMD ["pytest", "-q"]

FROM runtime-base AS production
