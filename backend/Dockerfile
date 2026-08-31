FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN addgroup --system hive && adduser --system --ingroup hive hive

COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY backend ./backend
COPY docs/project-brain ./docs/project-brain

RUN mkdir -p /var/lib/hive && chown -R hive:hive /app /var/lib/hive
USER hive

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
