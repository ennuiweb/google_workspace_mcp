FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.29

COPY . .
RUN uv sync --frozen --no-dev --extra disk

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app /app

RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/store_creds \
    && chown -R app:app /app \
    && chmod 755 /app/store_creds

USER app

EXPOSE 8000
ARG PORT
EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD sh -c 'curl -f http://localhost:${PORT:-8000}/health || exit 1'

ENV TOOL_TIER=""
ENV TOOLS=""

ENTRYPOINT ["/bin/sh", "-c"]
CMD [".venv/bin/python main.py --transport streamable-http ${TOOL_TIER:+--tool-tier \"$TOOL_TIER\"} ${TOOLS:+--tools $TOOLS}"]
