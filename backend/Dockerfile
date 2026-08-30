# Backend FastAPI — Cloud Run. Build thuần pip (không cần uv ở runtime).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
# Cài dependencies trước (cache layer) — code sau.
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic pydantic-settings \
    "sqlalchemy[asyncio]" asyncpg aiosqlite alembic anthropic httpx pyyaml jinja2 \
    tenacity mcp GitPython google-api-python-client google-auth

COPY app ./app
COPY config ./config
COPY profiles ./profiles
COPY templates ./templates

EXPOSE 8080
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
