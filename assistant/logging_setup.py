"""Privacy-conscious rotating file logging for Jarvis."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

def configure_logging(log_level: str = "INFO") -> Path:
    """Log operational events only; do not log transcripts, prompts, or secrets."""
    global _CONFIGURED
    log_path = Path(__file__).resolve().parent.parent / "logs" / "jarvis.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not _CONFIGURED:
        level = getattr(logging, str(log_level).upper(), logging.INFO)
        root = logging.getLogger()
        root.setLevel(level)
        handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ))
        root.addHandler(handler)
        _CONFIGURED = True
    return log_path
