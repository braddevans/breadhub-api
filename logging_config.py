from loguru import logger
import sys
import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

class InterceptHandler(logging.Handler):
    """Intercept standard logging messages and redirect them to Loguru."""
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the logged message originated
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        try:
            # Get the message and format it if there are args
            msg = record.getMessage()
            logger.opt(depth=depth, exception=record.exc_info).log(level, msg)
        except Exception as e:
            # Fallback in case of any formatting errors
            logger.opt(depth=depth, exception=e).error(
                f"Error formatting log message: {record.msg} with args: {record.args}"
            )

def setup_flask_logging(app, level='INFO'):
    """Configure Flask's logging to use Loguru."""
    # Only configure logging once
    if hasattr(app, '_logging_configured'):
        return

    # Set the log level
    log_level = level.upper()

    # Add the intercept handler to Flask's logger
    intercept_handler = InterceptHandler()

    # Configure Flask app logger
    app.logger.handlers = []
    app.logger.setLevel(log_level)
    app.logger.addHandler(intercept_handler)
    app.logger.propagate = False

    # Configure Werkzeug logger (Flask's development server)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers = []
    werkzeug_logger.setLevel(log_level)
    werkzeug_logger.addHandler(intercept_handler)
    werkzeug_logger.propagate = False

    # Configure root logger to use our handler
    logging.basicConfig(handlers=[intercept_handler], level=0, force=True)

    # Mark as configured
    app._logging_configured = True

# Global variable to track if logging is configured
_logging_configured = False

def setup_logging(level='INFO', log_dir='/var/log/breadhub'):
    """
    Configure Loguru logging for the application with both console and file outputs.
    This function is safe to call multiple times and will only configure logging once.
    
    Args:
        level: Logging level (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_dir: Directory to store log files
    """
    global _logging_configured
    
    # Only configure logging once per process
    if _logging_configured:
        return logger
        
    _logging_configured = True
    
    # Remove default handler
    logger.remove()
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Standard log format
    # Get the worker ID from environment or use process ID
    worker_id = os.environ.get('GUNICORN_WORKER_ID', f'worker-{os.getpid()}')
    
    log_format = (
        '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
        '<level>{level: <8}</level> | '
        f'<cyan>{worker_id}</cyan> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
        '<level>{message}</level>'
    )
    
    # Add stderr handler with colored output
    logger.add(
        sys.stderr,
        format=log_format,
        level=level.upper(),
        colorize=True,
        backtrace=True,
        diagnose=True,
        enqueue=True  # Make thread and process safe
    )
    
    # Add file handler with rotation - use a unique file per worker
    worker_id = os.environ.get('GUNICORN_WORKER_ID', 'main')
    log_file = Path(log_dir) / f'breadhub-{worker_id}.log'
    
    logger.add(
        str(log_file),
        rotation='100 MB',
        retention='30 days',
        compression='zip',
        enqueue=True,  # Make thread and process safe
        backtrace=True,
        diagnose=False,  # Don't include variable values in production
        level=level.upper(),
        format=log_format,
        colorize=False,
        filter=lambda record: record['level'].no >= 20  # INFO and above
    )
    
    # Add error log file for warnings and above
    error_log_file = Path(log_dir) / 'breadhub-error.log'
    logger.add(
        str(error_log_file),
        rotation='50 MB',
        retention='90 days',
        compression='zip',
        enqueue=True,
        backtrace=True,
        diagnose=True,
        level='WARNING',
        format=log_format,
        colorize=False
    )
    
    logger.info(f"Logging configured for worker {worker_id}. Logs at {log_dir}")
    return logger
