"""
WSGI entry point for BreadHub API.

Run under Gunicorn with the settings in gunicorn.conf.py:

    gunicorn wsgi:app
"""
from app.main import create_app

app = create_app()
