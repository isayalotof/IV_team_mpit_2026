FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ffmpeg unzip \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -e .

COPY src/ ./src/
COPY config/ ./config/

ENV PYTHONPATH=/app/src
ENV META_DB_URL=sqlite+aiosqlite:////app/meta_data/meta.db

RUN mkdir -p /app/meta_data

CMD ["uvicorn", "askdata.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
