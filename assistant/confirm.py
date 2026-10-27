"""Understand a spoken or typed yes/no answer. Anything unclear counts as 'unclear'."""
from __future__ import annotations

import re

_YES = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
    "correct", "affirmative", "proceed", "go ahead", "do it", "go for it",
    "yes please", "sure thing", "please do", "that's right", "thats right",
}
_NO = {
    "no", "nope", "nah", "cancel", "stop", "dont", "do not", "negative",
    "never mind", "nevermind", "abort", "no thanks", "no thank you", "dont do it",
    "dont do that", "wait", "not now",
}


def parse_yes_no(text: str | None) -> bool | None:
    """True = yes, False = no, None = could not tell."""
    if not text:
        return None
    t = re.sub(r"[^\w\s]", "", text.lower().replace("'", "")).strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        return None
    if t in _YES:
        return True
    if t in _NO:
        return False
    words = t.split()
    # "no" anywhere wins: "yes no wait" must never delete something.
    if any(w in {"no", "nope", "nah", "cancel", "stop", "dont", "never", "abort", "wait"} for w in words):
        return False
    if len(words) <= 4 and any(w in {"yes", "yeah", "yep", "yup", "sure", "confirm", "proceed"} for w in words):
        return True
    return None
