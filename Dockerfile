FROM node:24-bookworm-slim AS ui
WORKDIR /build/ui
COPY flask_vocab_app/ui/package*.json ./
RUN npm ci
COPY flask_vocab_app/ui/ ./
COPY flask_vocab_app/static/css/ /build/static/css/
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg poppler-utils tesseract-ocr tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/flask_vocab_app
COPY flask_vocab_app/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY flask_vocab_app/ ./
COPY --from=ui /build/ui/dist ./ui/dist
EXPOSE 8080
# Startup runs on the Machine with /data mounted, not a Fly release Machine.
CMD ["python", "hosted.py"]
