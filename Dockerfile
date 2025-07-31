# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    FLASK_APP=wsgi.py \
    FLASK_ENV=production

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (for better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install cron and other utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY . .

# Make the update script executable
RUN chmod +x /app/update_and_restart.sh

# Set up cron job for hourly updates
RUN echo "0 * * * * root /app/update_and_restart.sh" > /etc/cron.d/update-job
RUN chmod 0644 /etc/cron.d/update-job
RUN touch /var/log/cron.log

# Start cron service
RUN service cron start

# Create log directory and set permissions
RUN mkdir -p /var/log/breadhub && \
    chown -R appuser:appuser /var/log/breadhub && \
    chmod 755 /var/log/breadhub

# Create a non-root user and switch to it
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
# Using exec form for better signal handling
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "sync", "wsgi:app"]
