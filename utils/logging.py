import logging
from contextvars import ContextVar
from typing import Optional, Iterable, Tuple

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request id into records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.request_id = request_id_var.get()
        return True


class RequestIdFormatter(logging.Formatter):
    """Formatter that ensures record.request_id exists (from context var) before formatting."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return super().format(record)


DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)s | %(module)s | %(threadName)s "
    "| req=%(request_id)s | %(message)s"
)


def setup_logging(level: int = logging.INFO, fmt: Optional[str] = None) -> None:
    """Configure the root logger for the running process.

    All services should call this once at start-up.  The default format
    includes the timestamp, severity, module name, thread name and the
    current request id (populated by :class:`RequestIdFilter`).  A custom
    format may be supplied if required.
    """
    fmt = fmt or DEFAULT_FORMAT
    root = logging.getLogger()
    root.setLevel(level)
    root.addFilter(RequestIdFilter())
    logging.basicConfig(level=level, format=fmt)
    # Use a formatter that injects request_id when missing (so third-party
    # loggers like Werkzeug that use handlers not going through our filter don't break).
    formatter = RequestIdFormatter(fmt)
    for h in root.handlers:
        h.setFormatter(formatter)


def set_request_id_from_context(context) -> None:
    """Extract request-id metadata from a gRPC ``context`` and store it.

    Call this at the beginning of every RPC handler so that the filter has a
    value to report.
    """
    rid = "-"
    if context is not None:
        metadata = context.invocation_metadata()
        for k, v in metadata:  # type: ignore[assignment]  # grpc metadata is Sequence[tuple]
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            if key.lower() == "request-id":
                rid = v.decode("utf-8") if isinstance(v, bytes) else v
                break
    request_id_var.set(rid)


def grpc_client_metadata_for_request_id() -> Iterable[Tuple[str, str]]:
    """Helper to build metadata tuple that includes the current request id.

    When making an outgoing gRPC call the caller should supply
    ``metadata=grpc_client_metadata_for_request_id()`` so the downstream
    service can propagate the identifier.
    """
    return (("request-id", request_id_var.get()),)
