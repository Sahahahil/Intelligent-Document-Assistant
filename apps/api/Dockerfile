# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/srv/.hf \
    UV_PYTHON=3.11 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /srv

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# --- dependencies (this layer is cached until pyproject.toml / uv.lock change) ---
# The lock pins the CUDA build of torch, which drags in 43 nvidia-* wheels
# (~3 GB). This image only ever runs on CPU, so torch comes from the PyTorch
# CPU index and the CUDA-only requirements are dropped from the export.
COPY pyproject.toml uv.lock ./
RUN pip install uv==0.13.6 \
 && uv export --frozen --no-dev --no-emit-project --no-hashes --no-annotate \
      --format requirements.txt -o /tmp/requirements.txt \
 && grep -viE '^(torch|triton|nvidia-|cuda-)' /tmp/requirements.txt > /tmp/requirements-cpu.txt \
 && TORCH_VERSION="$(grep -iE '^torch==' /tmp/requirements.txt | head -1 | cut -d= -f3)" \
 && pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}+cpu" \
 && pip install -r /tmp/requirements-cpu.txt \
 && rm -f /tmp/requirements.txt /tmp/requirements-cpu.txt

# --- application (this layer is cached until the code changes) ---
COPY . .
COPY scripts/docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000
CMD ["/usr/local/bin/entrypoint.sh"]