import logging
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return application logger wired into Uvicorn's error logger.

    All logs go through `uvicorn.error` handlers, so they appear in
    docker/console output together with Uvicorn logs.

    Args:
        name: Optional child logger name.

    Returns:
        logging.Logger: Configured application logger.
    """
    base = logging.getLogger("uvicorn.error")

    if name:
        logger = base.getChild(name)
    else:
        logger = base

    logger.setLevel(base.level)
    return logger
