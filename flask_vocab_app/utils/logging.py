import logging


def setup_logging():
    """Return a logger without changing the host application's logging policy."""
    return logging.getLogger(__name__)
