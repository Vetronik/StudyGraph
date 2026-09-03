import logging

from studygraph.config import get_log_level

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    logging.basicConfig(
        level=get_log_level(),
        format=LOG_FORMAT,
    )
