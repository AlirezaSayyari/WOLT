FROM python:3.12-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin wolt \
    && install -d -o wolt -g wolt /home/wolt/.ssh

COPY --chown=wolt:wolt app ./app

USER wolt

CMD ["python", "-m", "app.main"]

FROM runtime-base AS test

USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=wolt:wolt tests ./tests
USER wolt
CMD ["pytest", "-q"]

FROM runtime-base AS production
