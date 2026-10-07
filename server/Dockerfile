# Development image for the CodeMop webhook server, used by docker-compose.yml (which mounts
# server/src over /app/src so changes reload). Build it from the repository root.
FROM python:3.14-slim

RUN useradd -m appuser
USER appuser
WORKDIR /app

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    APP_ENV=development \
    DEBUG=True

COPY --chown=appuser:appuser server/requirements.txt server/requirements-dev.txt ./
RUN pip install --user --no-cache-dir -r requirements-dev.txt

# The codemop package (rebuild the image after changing it)
COPY --chown=appuser:appuser pyproject.toml README.md LICENSE /tmp/codemop/
COPY --chown=appuser:appuser src /tmp/codemop/src
RUN pip install --user --no-cache-dir --no-deps /tmp/codemop && rm -rf /tmp/codemop

COPY --chown=appuser:appuser server/src /app/src

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
