"""
WSGI config for BreadHub API.

This module contains the WSGI application used by the production server.
"""
import os
from main import create_app

# Ensure we're in production mode
os.environ['FLASK_ENV'] = 'production'

# Create the Flask application using the default config
app = create_app()

# This file should only be used as an entry point for WSGI servers like Gunicorn
# It should not be run directly in production
