# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependências primeiro: a camada fica em cache enquanto só o código muda.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RAG_DB_PATH=/data/index.db \
    RAG_CORPUS_DIR=/corpus
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
WORKDIR /app
COPY --from=build --chown=app /app /app
COPY --chown=app corpus /corpus
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["rag", "serve", "--host", "0.0.0.0", "--port", "8000"]
