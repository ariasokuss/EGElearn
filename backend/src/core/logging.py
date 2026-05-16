import logging
from collections.abc import Iterable

from src.config import Settings

QUIET_LOGGERS: tuple[str, ...] = (
    "aio_pika",
    "aiobotocore",
    "aiormq",
    "asyncio",
    "botocore",
    "grpc",
    "grpc._cython",
    "grpc._cython.cygrpc",
    "httpcore",
    "httpx",
    "multipart",
    "multipart.multipart",
    "openai",
    "python_multipart",
    "python_multipart.multipart",
    "qdrant_client",
    "s3transfer",
    "src.core.s3",
    "urllib3",
    "voyage",
    "voyageai",
    "uvicorn.asgi",
)


class SuppressInspectorStreamAccessFilter(logging.Filter):
    def __init__(self, *, api_prefix: str) -> None:
        super().__init__(name="uvicorn.access")
        self._stream_prefix = f"{api_prefix.rstrip('/')}/inspector/folders/"

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args if isinstance(record.args, tuple) else ()
        if len(args) < 5:
            return True

        path = str(args[2])
        status_code = str(args[4])
        if not isinstance(path, str):
            return True
        normalized_path = path.split("?", 1)[0]
        if not normalized_path.startswith(
            self._stream_prefix
        ) or not normalized_path.endswith("/stream"):
            return True

        try:
            return int(status_code) >= 400
        except (TypeError, ValueError):
            return True


def _resolve_level(raw_level: str | int | None) -> int:
    if isinstance(raw_level, int):
        return raw_level
    if isinstance(raw_level, str):
        level = getattr(logging, raw_level.upper(), None)
        if isinstance(level, int):
            return level
    return logging.INFO


def _set_logger_levels(names: Iterable[str], level: int) -> None:
    for name in names:
        logging.getLogger(name).setLevel(level)


def _configure_root_logger(level: int) -> None:
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _configure_access_logging(settings: Settings) -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if any(
        isinstance(log_filter, SuppressInspectorStreamAccessFilter)
        for log_filter in access_logger.filters
    ):
        return

    access_logger.addFilter(
        SuppressInspectorStreamAccessFilter(api_prefix=settings.app.api_prefix)
    )


def configure_logging(settings: Settings) -> None:
    level = _resolve_level(settings.app.log_level)
    quiet_level = logging.INFO if level <= logging.DEBUG else logging.WARNING

    _configure_root_logger(level)
    _set_logger_levels(QUIET_LOGGERS, quiet_level)
    _configure_access_logging(settings)
