FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build deps for bcrypt (requires cffi → gcc + libffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying app code so this layer is cached
# unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy application code (cache-busted only on code changes)
COPY . .

# Run as non-root
RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]
