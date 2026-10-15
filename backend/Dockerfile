FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 mcxus
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY migrations ./migrations
# media: public listing photos. blobs: encrypted chat photos/voice notes (private). evidence: dispute photos
# (private, parties and staff only). Both are Docker volumes and
# must belong to the app user, or uploads fail with "permission denied".
RUN mkdir -p /app/media /app/blobs /app/evidence /app/status && chown mcxus /app/media /app/blobs /app/evidence /app/status
ENV MCXUS_MEDIA_DIR=/app/media MCXUS_BLOB_DIR=/app/blobs MCXUS_EVIDENCE_DIR=/app/evidence MCXUS_STATUS_DIR=/app/status
USER mcxus
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
