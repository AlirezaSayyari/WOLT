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

# Keep release metadata after dependency installation so changing a version or
# commit SHA does not invalidate the expensive Python dependency layer.
ARG WOLT_VERSION=v1.1.0
ARG WOLT_COMMIT_SHA=local
ARG WOLT_BUILD_DATE=unknown

ENV WOLT_VERSION=${WOLT_VERSION} \
    WOLT_COMMIT_SHA=${WOLT_COMMIT_SHA} \
    WOLT_BUILD_DATE=${WOLT_BUILD_DATE}

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin wolt \
    && install -d -o wolt -g wolt /home/wolt/.ssh

COPY --chown=wolt:wolt app ./app
COPY --chown=wolt:wolt migrations ./migrations
COPY --chown=wolt:wolt alembic.ini ./alembic.ini
COPY --from=web-build --chown=wolt:wolt /web/dist ./app/web/static
COPY --chown=root:root compose.web.yml compose.host-agent.yml VERSION /opt/wolt-runtime/
COPY --chown=root:root scripts/init-web-env.sh scripts/install-cosign.sh scripts/install-host-agent.sh /opt/wolt-runtime/scripts/
COPY --chown=root:root host_agent /opt/wolt-runtime/host_agent

USER wolt

CMD ["python", "-m", "app.main"]

FROM runtime-base AS test

USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=wolt:wolt tests ./tests
COPY --chown=wolt:wolt scripts ./scripts
COPY --chown=wolt:wolt host_agent ./host_agent
COPY --chown=wolt:wolt install.sh compose.web.yml compose.host-agent.yml Dockerfile ./
USER wolt
CMD ["pytest", "-q"]

FROM runtime-base AS production
