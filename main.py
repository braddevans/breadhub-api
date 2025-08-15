from flask import Flask, jsonify, request
from config import Config
from logging_config import setup_logging, setup_flask_logging, logger
import os
from datetime import datetime

def create_app(config_class=Config):
    # Create the Flask application
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Configure logging only once
    if not app.debug and not app.testing:
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        setup_logging(level=log_level)
        setup_flask_logging(app, level=log_level)
    
    # Log all requests
    @app.before_request
    def log_request():
        if request.path == '/favicon.ico':
            return
        logger.info(f"Request: {request.method} {request.path} - {request.remote_addr}")
    
    # Log all responses
    @app.after_request
    def log_response(response):
        if request.path == '/favicon.ico':
            return response
        logger.info(f"Response: {request.method} {request.path} - {response.status_code}")
        return response
    
    # Import routes here to avoid circular imports
    from routes import init_app as init_routes
    
    # Initialize routes
    init_routes(app)
    
    @app.route('/')
    def index():
        return jsonify({
            'name': 'BreadHub API',
            'version': '1.0.0',
            'endpoints': [
                '/api/barcode',
                '/api/barcode/writer-options'
            ]
        })
    
    return app

def run_development_server():
    """Run the development server with proper configuration."""
    # Set environment variables for development
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = '1'
    
    # Create the application
    app = create_app()
    
    # Configure the development server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False,
        use_debugger=False,
        use_evalex=True
    )

if __name__ == '__main__':
    run_development_server()
