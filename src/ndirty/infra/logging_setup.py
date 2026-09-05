"""Privacy-preserving local error logging."""

import logging
from pathlib import Path

from ndirty.infra.paths import application_root


def configure_logging() -> Path:
    directory = application_root() / "logs"
    directory.mkdir(exist_ok=True)
    path = directory / "ndirty.log"
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    return path
