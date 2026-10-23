import os

from flask import Flask, request

from app.config import Config
from app.logging_config import setup_logging, setup_flask_logging, logger
from app.middleware import init_error_handlers
from app.routes import init_app as init_routes
from app.routes.pages import init_pages


def get_real_ip():
    """Get real client IP from headers if behind proxy/Docker."""
    real_ip = request.headers.get('X-Forwarded-For', request.headers.get('X-Real-IP', request.remote_addr))
    return real_ip.split(',')[0].strip() if real_ip else real_ip


def should_skip_logging():
    """Check if request should be skipped from logging."""
    return request.path == '/favicon.ico' or request.headers.get('X-Healthcheck') == 'true'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.testing:
        log_level = app.config['LOG_LEVEL']
        setup_logging(level=log_level, log_dir=app.config['LOG_DIR'])
        setup_flask_logging(app, level=log_level)

    init_error_handlers(app)
    init_pages(app)
    init_routes(app)

    @app.before_request
    def log_request():
        if not should_skip_logging():
            logger.debug("Request: {} {} - {}", request.method, request.path, get_real_ip())

    @app.after_request
    def log_response(response):
        if not should_skip_logging():
            logger.debug("Response: {} {} - {}", request.method, request.path, response.status_code)
        return response

    return app


def run_development_server():
    """Run the threaded development server."""
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=True,
        threaded=True,
        use_reloader=False,
        use_debugger=False,
    )


if __name__ == '__main__':
    run_development_server()
