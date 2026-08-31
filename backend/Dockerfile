FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN addgroup --system hive && adduser --system --ingroup hive hive

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY backend ./backend
COPY docs/project-brain ./docs/project-brain
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY scripts/migrate.py ./scripts/migrate.py

RUN mkdir -p /var/lib/hive && chown -R hive:hive /app /var/lib/hive
USER hive

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
