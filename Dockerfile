FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY scripts ./scripts

RUN pip install --no-cache-dir .

USER appuser
ENV PORT=8321 GARMIN_TOKENSTORE_PATH=/data
EXPOSE 8321
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8321') + '/health', timeout=3)"

CMD ["python", "-m", "garmin_mcp.server"]
