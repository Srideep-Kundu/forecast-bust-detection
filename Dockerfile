FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FORECAST_BUST_DATA_ROOT=/app/data \
    COPILOT_CACHE_PATH=/tmp/forecast-bust-copilot.sqlite

RUN groupadd --system forecast && useradd --system --gid forecast --create-home forecast
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels forecast-bust && rm -rf /wheels

WORKDIR /app
USER forecast
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','10000')+'/health', timeout=3)" || exit 1
CMD ["/bin/sh", "-c", "exec uvicorn forecast_bust.api:app --host 0.0.0.0 --port ${PORT:-10000}"]
