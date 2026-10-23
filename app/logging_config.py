import inspect
import logging
import os
import sys
from pathlib import Path

from loguru import logger

# Stdlib loggers whose output is redirected into loguru.
INTERCEPTED_LOGGERS = ('werkzeug', 'gunicorn.access', 'gunicorn.error')

# {process} is evaluated in the process that emits the record, so each line is
# tagged with the worker that produced it even though, under gunicorn with
# preload_app, a single sink in the master writes every worker's output.
LOG_FORMAT = (
    '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
    '<level>{level: <8}</level> | '
    '<cyan>pid-{process}:{thread.name}</cyan> | '
    '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
    '<level>{message}</level>'
)

_logging_configured = False


class InterceptHandler(logging.Handler):
    """Intercept standard logging messages and redirect them to Loguru."""

    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk out of the logging module so loguru reports the real caller.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level='INFO', log_dir=None):
    """
    Configure Loguru with a console sink and, when log_dir is writable, file sinks.

    Safe to call more than once; only the first call per process has any effect.

    Every sink uses enqueue=True, which hands records to a single writer thread
    in the process that configured logging. Under gunicorn with preload_app the
    workers are forked from that process, so all of them feed one writer and
    file rotation is done by exactly one process. Without that, each worker
    would rotate the same files independently and clobber them.
    """
    global _logging_configured

    if _logging_configured:
        return logger
    _logging_configured = True

    level = level.upper()
    logger.remove()

    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )

    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            logger.warning("File logging disabled, cannot create {}: {}", log_dir, e)
            return logger

        logger.add(
            str(Path(log_dir) / 'breadhub.log'),
            rotation='100 MB',
            retention='30 days',
            compression='zip',
            enqueue=True,
            backtrace=True,
            diagnose=False,  # Don't include variable values in production
            level=level,
            format=LOG_FORMAT,
            colorize=False,
        )

        logger.add(
            str(Path(log_dir) / 'breadhub-error.log'),
            rotation='50 MB',
            retention='90 days',
            compression='zip',
            enqueue=True,
            backtrace=True,
            diagnose=False,
            level='WARNING',
            format=LOG_FORMAT,
            colorize=False,
        )
        logger.info("File logging enabled in {}", log_dir)

    return logger


def setup_flask_logging(app, level='INFO'):
    """Route Flask, Werkzeug, Gunicorn and other stdlib logging into Loguru."""
    level = level.upper()
    intercept_handler = InterceptHandler()

    for std_logger in (app.logger, *map(logging.getLogger, INTERCEPTED_LOGGERS)):
        std_logger.handlers = [intercept_handler]
        std_logger.setLevel(level)
        std_logger.propagate = False

    logging.basicConfig(handlers=[intercept_handler], level=level, force=True)
