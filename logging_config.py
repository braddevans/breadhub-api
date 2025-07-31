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

def setup_logging(level='INFO', log_dir='/var/log/breadhub'):
    """
    Configure Loguru logging for the application with both console and file outputs.
    
    Args:
        level: Logging level (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_dir: Directory to store log files
    """
    # Remove default handler
    logger.remove()
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Standard log format
    log_format = (
        '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
        '<level>{level: <8}</level> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
        '<level>{message}</level>'
    )
    
    # Add stderr handler with colored output
    logger.add(
        sys.stderr,
        format=log_format,
        level=level.upper(),
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # Add file handler with rotation
    log_file = Path(log_dir) / 'breadhub.log'
    logger.add(
        str(log_file),
        rotation='100 MB',           # Rotate when file reaches 100MB
        retention='30 days',         # Keep logs for 30 days
        compression='zip',           # Compress rotated logs
        enqueue=True,               # Thread-safe logging
        backtrace=True,             # Include stack traces in logs
        diagnose=True,              # Include variable values in traceback
        level=level.upper(),
        format=log_format,
        colorize=False              # No color in file logs
    )
    
    # Add error log file with more detailed logging
    error_log_file = Path(log_dir) / 'breadhub-error.log'
    logger.add(
        str(error_log_file),
        rotation='50 MB',           # Rotate when file reaches 50MB
        retention='90 days',        # Keep error logs longer
        compression='zip',
        enqueue=True,
        backtrace=True,
        diagnose=True,
        level='WARNING',            # Only log warnings and above
        format=log_format,
        colorize=False
    )
    
    logger.info(f"Logging configured. Logs will be written to {log_dir}")
    return logger
