"""
Gunicorn settings for BreadHub API. Picked up automatically by `gunicorn wsgi:app`
when run from the project root; every value can be overridden from the environment.
"""
import os

bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5000')

# Barcode rendering and image resizing are CPU-bound, so processes provide the
# parallelism. Threads let each worker keep serving while one request is busy
# (Pillow releases the GIL while resizing and encoding) or waiting on a slow
# client upload, instead of the sync worker's one request at a time.
workers = int(os.environ.get('GUNICORN_WORKERS', 4))
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', 4))

# Load the app once in the master before forking. Loguru's enqueued sinks are
# then created in the master, so every worker feeds the same writer thread and
# the log files are only ever rotated by one process.
preload_app = True

timeout = int(os.environ.get('GUNICORN_TIMEOUT', 30))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
worker_tmp_dir = '/dev/shm'

loglevel = os.environ.get('LOG_LEVEL', 'info').lower()
accesslog = None
