"""
WSGI config for BreadHub API.

This module contains the WSGI application used by the production server.
"""
import os
import sys
from main import create_app

# Ensure we're in production mode
os.environ['FLASK_ENV'] = 'production'

# Get the worker ID if running under Gunicorn
try:
    import multiprocessing
    worker_id = f"gunicorn-{multiprocessing.current_process().pid}"
except (ImportError, AttributeError):
    worker_id = f"worker-{os.getpid()}"

# Set worker ID for logging
os.environ['GUNICORN_WORKER_ID'] = worker_id

# Create the Flask application using the default config
app = create_app()

def when_ready(server):
    """Run when Gunicorn starts."""
    # This will be called in the master process
    pass

def on_starting(server):
    """Run when each worker starts."""
    # This will be called in each worker process
    pass

def worker_int(worker):
    """Run when a worker is about to exit."""
    pass

# This file should only be used as an entry point for WSGI servers like Gunicorn
