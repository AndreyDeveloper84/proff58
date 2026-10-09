"""Privacy retention invariants for file logging (DRF-2957)."""

from config.settings import base


def test_application_file_logs_do_not_rotate_inside_python():
    handlers = base.LOGGING["handlers"]
    for name in ("django_file", "onec_file", "payments_file"):
        handler = handlers[name]
        assert handler["class"] == "logging.FileHandler"
        assert "backupCount" not in handler
        assert "maxBytes" not in handler
