import os

class Config:
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    # Uploads. Flask enforces this itself when parsing a request body, so
    # without it the image grid endpoint will read a body of any size.
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 32 * 1024 * 1024))