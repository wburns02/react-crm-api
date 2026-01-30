FROM python:3.12-slim
# Build: v2.7.10 - Force Railway rebuild - 2026-01-30T17:15:00

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Railway provides PORT env var - expose a default but app uses $PORT
EXPOSE 8080

# Use shell form to enable environment variable expansion
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
