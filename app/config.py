import os

class Config:
    # Logging. LOG_DIR may be set empty to log to stderr only.
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_DIR = os.environ.get('LOG_DIR', '/var/log/breadhub')

    # Uploads. Flask enforces this itself when parsing a request body, so
    # without it the image grid endpoint will read a body of any size.
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 32 * 1024 * 1024))

    # Threads per process that decode and resize image grid uploads. They are
    # shared by every request the process serves, on top of gunicorn's threads.
    IMAGEGRID_THREADS = int(os.environ.get('IMAGEGRID_THREADS', min(4, os.cpu_count() or 1)))
