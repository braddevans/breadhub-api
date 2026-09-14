from flask import Flask, request, render_template
from app.config import Config
from app.logging_config import setup_logging, setup_flask_logging, logger
from app.middleware import init_error_handlers
from app.routes.pages import init_pages
import os

def create_app(config_class=Config):
    # Create the Flask application with absolute path to templates
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    app = Flask(__name__, template_folder=template_dir)
    app.config.from_object(config_class)
    
    # Configure logging only once
    if not app.debug and not app.testing:
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        setup_logging(level=log_level)
        setup_flask_logging(app, level=log_level)
    
    # Initialize error handlers
    init_error_handlers(app)
    
    # Initialize pages
    init_pages(app)

    # Log all requests and responses (skip favicon and healthcheck)
    def get_real_ip():
        """Get real client IP from headers if behind proxy/Docker."""
        real_ip = request.headers.get('X-Forwarded-For', request.headers.get('X-Real-IP', request.remote_addr))
        if ',' in real_ip:
            real_ip = real_ip.split(',')[0].strip()
        return real_ip

    def should_skip_logging():
        """Check if request should be skipped from logging."""
        return request.path == '/favicon.ico' or request.headers.get('X-Healthcheck') == 'true'

    @app.before_request
    def log_request():
        if should_skip_logging():
            return
        logger.debug(f"Request: {request.method} {request.path} - {get_real_ip()}")

    @app.after_request
    def log_response(response):
        if should_skip_logging():
            return response
        logger.debug(f"Response: {request.method} {request.path} - {response.status_code}")
        return response
    
    # Import routes here to avoid circular imports
    from app.routes import init_app as init_routes
    
    # Initialize routes
    init_routes(app)

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
