FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 videomind

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services services
COPY eval eval

ENV PYTHONPATH=/app/services:/app/services/api \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    WORKER_BACKEND=poll

RUN mkdir -p /data && chown -R videomind:videomind /data /app
USER videomind

CMD ["python", "-m", "pipeline"]
