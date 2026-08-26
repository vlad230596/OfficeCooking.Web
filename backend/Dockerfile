ARG APP_VERSION=dev
ARG BUILD_DATE=unknown

FROM python:3.13.15-slim-bookworm AS runtime

ARG APP_VERSION
ARG BUILD_DATE

LABEL org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.created=$BUILD_DATE

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    OFFICE_COOK_APP_VERSION=$APP_VERSION \
    OFFICE_COOK_BUILD_DATE=$BUILD_DATE

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev
RUN chown -R 65532:65532 /tmp/uv-cache

USER 65532:65532
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
