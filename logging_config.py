from loguru import logger
import sys
import os
from pathlib import Path

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
