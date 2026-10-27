"""Turn AI-service exceptions into a clear, speakable reason.

Only the error CLASS and HTTP status are used; the message text is never shown or
logged because some providers echo part of the API key in it.
"""
from __future__ import annotations

import re

_KEYLIKE = re.compile(r"\b(?:sk|gsk|key|tok)[-_][A-Za-z0-9_\-]{6,}", re.I)


def safe_detail(error: BaseException) -> str:
    """Provider's error code/message for REQUEST problems (HTTP 400/413/422) only,
    with anything that looks like an API key removed. Empty for other errors."""
    if getattr(error, "status_code", None) not in (400, 413, 422):
        return ""
    body = getattr(error, "body", None)
    parts = []
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict):
            parts = [str(inner.get("code") or ""), str(inner.get("message") or "")]
    text = " - ".join(p for p in parts if p)
    return _KEYLIKE.sub("[hidden]", text)[:200]


def describe_ai_error(error: BaseException) -> tuple[str, str]:
    """-> (what Jarvis says, short technical label for the console and log)."""
    name = type(error).__name__
    status = getattr(error, "status_code", None)
    label = f"{name}" + (f" (HTTP {status})" if status else "")
    detail = safe_detail(error)
    if detail:
        label += f": {detail}"

    if "Timeout" in name or isinstance(error, TimeoutError):
        return ("The AI took too long to answer. Try again, or use a faster model.", label)
    if name in {"AuthenticationError", "PermissionDeniedError"} or status in (401, 403):
        return ("The AI service rejected my API key. Check AI_API_KEY in your settings file.", label)
    if name == "NotFoundError" or status == 404:
        return ("The AI service doesn't know that model name. Check AI_MODEL in your settings file.", label)
    if name == "RateLimitError" or status == 429:
        return ("The AI service says I'm asking too fast or out of quota. Wait a minute and try again.", label)
    if name == "APIConnectionError" or isinstance(error, (ConnectionError, OSError)):
        return ("I can't reach the AI service. Check your internet connection and AI_BASE_URL.", label)
    if name in {"BadRequestError", "UnprocessableEntityError"} or status in (400, 413, 422):
        return ("The AI service refused my request. The model may be too small or not support this.", label)
    return (f"The AI request failed. The error type was {name}.", label)
