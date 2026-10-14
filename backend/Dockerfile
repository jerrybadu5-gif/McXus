FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 mcxus
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY migrations ./migrations
RUN mkdir -p /app/media && chown mcxus /app/media
ENV MCXUS_MEDIA_DIR=/app/media
USER mcxus
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
