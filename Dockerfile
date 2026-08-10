FROM python:3.12-slim

# Unbuffered so logs reach the platform's log drain as they happen rather than
# when the buffer flushes; no .pyc files since the layer is immutable anyway.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Runtime dependencies only. Test and lint tooling lives in requirements-dev.txt
# and is deliberately absent from this image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

# Drop root. Nothing in this app writes to the filesystem or binds a privileged
# port, so running as root buys nothing but blast radius if the process is
# compromised — and this process fetches attacker-supplied URLs by design.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Self-contained: there is no curl or wget in the slim image, so urllib does it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4).status == 200 else 1)"

# $PORT is honoured when the platform injects one (DigitalOcean App Platform
# does), falling back to 8000 for a plain `docker run`. exec form keeps uvicorn
# as PID 1 so it receives SIGTERM directly and shuts down cleanly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
