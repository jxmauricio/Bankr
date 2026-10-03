FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY app ./app

RUN useradd --create-home bankr
USER bankr

ENV PORT=8000
EXPOSE 8000

# Migrations run on every boot so a deploy can't serve a schema mismatch.
# --proxy-headers so rate limiting sees the client IP, not the platform proxy.
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips="*"
