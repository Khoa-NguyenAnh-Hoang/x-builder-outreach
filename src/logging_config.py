"""Logging setup: uniform format + a redaction filter so secret values never reach output (policy I9)."""

import logging
import sys


class SecretsFilter(logging.Filter):
    """Scrub configured secret values from every log record passing through."""

    def __init__(self, secrets: tuple[str, ...] = ()):
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for secret in self._secrets:
            if secret in msg:
                msg = msg.replace(secret, "***REDACTED***")
        record.msg = msg
        record.args = None
        return True


def setup_logging(level: int = logging.INFO, secrets: tuple[str, ...] = ()) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(SecretsFilter(secrets))
    root.handlers[:] = [handler]
