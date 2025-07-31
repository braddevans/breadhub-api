"""
WSGI config for BreadHub API.

This module contains the WSGI application used by the production server.
"""
import os
from main import create_app

# Create the Flask application using the default config
app = create_app()

if __name__ == "__main__":
    # This block is for development only
    # In production, use a production WSGI server like Gunicorn or uWSGI
    app.run(host='0.0.0.0', port=5000)
