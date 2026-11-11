import logging

from src.logging_config import SecretsFilter, setup_logging


def test_secret_values_redacted_from_log_records():
    filt = SecretsFilter(secrets=("super-secret-token",))
    record = logging.LogRecord(
        "t", logging.INFO, "path", 1, "auth failed for token=super-secret-token", None, None
    )
    assert filt.filter(record) is True
    assert "super-secret-token" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_empty_secrets_are_ignored():
    filt = SecretsFilter(secrets=(""))
    record = logging.LogRecord("t", logging.INFO, "path", 1, "hello", None, None)
    assert filt.filter(record) is True
    assert record.getMessage() == "hello"


def test_setup_logging_installs_single_filtered_handler():
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    setup_logging(secrets=())
    try:
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert any(isinstance(f, SecretsFilter) for f in handler.filters)
    finally:
        root.removeHandler(handler)  # don't leak the test handler into other tests
