# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/srv/.hf \
    UV_PYTHON=3.11 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

WORKDIR /srv

# Copy prebuilt uv binary (no install step needed)
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

# --- dependencies (cached until pyproject.toml / uv.lock change) ---
COPY apps/api/pyproject.toml apps/api/uv.lock ./

# Install torch CPU first (separate layer - only rebuilds on torch version change)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --index-url https://download.pytorch.org/whl/cpu torch==2.15.0+cpu

# Install remaining dependencies (rebuilds on any dependency change)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --no-hashes --no-annotate \
       --format requirements.txt -o /tmp/requirements.txt \
 && grep -viE '^(torch|triton|nvidia-|cuda-|cuda_)' /tmp/requirements.txt > /tmp/requirements-cpu.txt \
 && uv pip install --system -r /tmp/requirements-cpu.txt \
 && rm -f /tmp/requirements.txt /tmp/requirements-cpu.txt

# --- application (cached until code changes) ---
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY apps/api/ .
COPY --chmod=755 apps/api/scripts/docker-entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 8000
CMD ["/usr/local/bin/entrypoint.sh"]