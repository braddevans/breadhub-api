# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    FLASK_APP=wsgi.py \
    FLASK_ENV=production \
    LOG_LEVEL=INFO

# Set work directory and create non-root user
WORKDIR /app

RUN useradd -m appuser && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser . .

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cron \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Setup scripts and permissions
RUN chmod +x /app/setup-git.sh /app/update_and_restart.sh && \
    echo "0 * * * * root /app/update_and_restart.sh" > /etc/cron.d/update-job && \
    chmod 0644 /etc/cron.d/update-job && \
    touch /var/log/cron.log && \
    mkdir -p /var/log/breadhub && \
    chown -Rv appuser:appuser /var/log && \
    chmod -Rv 777 /var/log

# Setup Git configuration and start services
USER root
RUN /app/setup-git.sh && service cron start

# Expose the port the app runs on
EXPOSE 5000

# Health check
HEALTHCHECK --interval=530s --timeout=3s \
    CMD curl -f http://localhost:5000/ || exit 1

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "sync", "wsgi:app"]
