# syntax=docker/dockerfile:1.7

# Stage 1: Build Stage
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

WORKDIR /app

# Copy pyproject.toml and uv.lock to install dependencies
COPY pyproject.toml uv.lock ./

# Install dependencies using uv (locked = use uv.lock)
RUN uv sync --locked --no-dev

# Copy the rest of the application code
COPY . .

# (optional) If your project itself is installable and needed in venv:
RUN uv sync --locked --no-dev

# Stage 2: Production Stage
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS production

WORKDIR /app

# Copy installed packages and application code from the builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /app ./

EXPOSE 8000

# FastAPI app run
CMD /app/.venv/bin/python -m uvicorn src.api:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
