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

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_flask_logging(app, level='INFO'):
    """Configure Flask's logging to use Loguru."""
    # Only configure logging once
    if hasattr(app, '_logging_configured'):
        return
        
    # Disable default Flask logging
    app.logger.handlers = []
    
    # Set the log level
    log_level = level.upper()
    app.logger.setLevel(log_level)
    
    # Add the intercept handler to Flask's logger
    intercept_handler = InterceptHandler()
    app.logger.addHandler(intercept_handler)
    
    # Disable propagation to avoid duplicate logs
    app.logger.propagate = False
    
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
    log_format = (
        '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
        '<level>{level: <8}</level> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
        'Worker {process.identity} | '
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
