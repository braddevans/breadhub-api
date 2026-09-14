from flask import jsonify, Response
from datetime import datetime
from app.logging_config import logger

def error_response(message, status_code):
    if status_code < 500:
        logger.warning("HTTP {}: {}", status_code, message)
    else:
        logger.error("HTTP {}: {}", status_code, message)
        
    response = jsonify({
        'error': message,
        'status': 'error',
        'status_code': status_code,
        'timestamp': datetime.now().isoformat()
    })
    response.status_code = status_code
    return response

def init_error_handlers(app):
    @app.errorhandler(400)
    def bad_request_error(error):
        return error_response(str(error) or 'Bad request', 400)
    
    @app.errorhandler(404)
    def not_found_error(error):
        return error_response('Resource not found', 404)
        
    @app.errorhandler(405)
    def method_not_allowed_error(error):
        return error_response('Method not allowed', 405)
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Internal server error")
        return error_response('Internal server error', 500)
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Unexpected error occurred")
        return error_response('An unexpected error occurred', 500)
