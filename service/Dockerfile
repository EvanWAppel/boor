# syntax=docker/dockerfile:1

# boor FastAPI rules-and-AI service (SETUP-05 / DATA-05).
#
# uv-managed Python 3.14. Migrations are NOT run here — they run as Railway's
# `preDeployCommand` (see railway.json: `uv run alembic upgrade head`) so the
# schema is up to date before the new container takes traffic. The image just
# serves, binding to Railway's injected $PORT.

FROM python:3.14-slim-bookworm

# uv from its published image, pinned for reproducible Railway builds (only the
# uv/uvx binaries are copied; the base Python is python:3.14 above).
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first as a cached layer, keyed only on the lock + manifest.
COPY pyproject.toml uv.lock ./
# Use Docker layer caching; Railway cache mounts require a service-specific ID.
RUN uv sync --frozen --no-install-project --no-dev --no-cache

# Then the source, and install the project itself into the venv.
COPY . .
RUN uv sync --frozen --no-dev --no-cache

EXPOSE 8000
# Railway injects $PORT at runtime; default to 8000 for a local `docker run`.
CMD ["sh", "-c", "uvicorn boor_service.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
