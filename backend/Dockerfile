# Development Dockerfile for CodeMop
# Uses same Python version as production for consistency

FROM python:3.13-slim

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and switch to a non-root user for security (same as production)
RUN useradd -m appuser
USER appuser
WORKDIR /app

# Copy requirements first for better caching
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Add user's local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Environment variables for development
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=development
ENV DEBUG=True

# Copy application code
COPY --chown=appuser:appuser . .

# Development command (will be overridden by docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]