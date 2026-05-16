FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/src
ENV PATH=/src/.venv/bin:$PATH

WORKDIR /src

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY scripts ./scripts

RUN uv sync --frozen --no-dev

# Railway injects PORT; without CMD the container exits immediately after start.
EXPOSE 8080
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && exec uv run --no-dev uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
