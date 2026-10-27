"""Turn a spoken/typed sentence into an approved desktop action.

This module only PARSES. It never touches the computer, so it is easy to
test. The router executes the returned DesktopAction through approved
functions in commands/desktop_actions.py. Anything not recognised here
returns None and continues to the normal router.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_TYPED_CHARS = 1000


@dataclass(frozen=True)
class DesktopAction:
    kind: str
    text: str | None = None
    target: str | None = None


# Names the original three registered commands already handle.
BUILTIN_APPS = {
    "chrome", "google chrome", "chrome browser", "notepad", "notepad app",
    "nose pad", "notes pad", "note pad", "noth spot", "noth pad",
    "calculator", "calc",
}

# Whisper often mishears "notepad"; all of these mean Notepad.
_NOTEPAD = r"note\s?pad|notes\s?pad|nose\s?pad|noth\s?pad|noth\s?spot"
_TARGETS = rf"(?:{_NOTEPAD}|wordpad|word\s?pad|microsoft word|word)"

SITES = {
    "youtube": "youtube.com", "google": "google.com", "gmail": "mail.google.com",
    "github": "github.com", "wikipedia": "wikipedia.org",
    "facebook": "facebook.com", "twitter": "x.com", "linkedin": "linkedin.com",
    "netflix": "netflix.com", "instagram": "instagram.com", "reddit": "reddit.com",
    "google maps": "maps.google.com", "google drive": "drive.google.com",
    "google docs": "docs.google.com", "google translate": "translate.google.com",
}

_PREFIX = re.compile(
    r"^(?:(?:hey|hi|ok|okay|please|kindly|jarvis|can you|could you|would you|"
    r"will you|i want you to|i need you to|i want to)[\s,]+)+",
    re.I,
)
_SUFFIX = re.compile(r"[\s,.!?]*(?:please|for me|thank you|thanks)?[\s,.!?]*$", re.I)


def _clean(text: str) -> str:
    text = text.strip()
    text = _PREFIX.sub("", text)
    for _ in range(3):
        text = _SUFFIX.sub("", text, count=1)
    return text.strip()


def canonical_target(name: str) -> str:
    low = re.sub(r"\s+", " ", name.lower()).strip()
    if re.fullmatch(_NOTEPAD, low):
        return "notepad"
    if low in {"wordpad", "word pad"}:
        return "wordpad"
    if low in {"word", "microsoft word"}:
        return "word"
    return low


def resolve_site(name: str) -> str | None:
    """'youtube' -> 'youtube.com';  'example dot com' -> 'example.com'."""
    low = re.sub(r"\s+", " ", name.lower()).strip().rstrip(".")
    low = re.sub(r"^(?:the )?(?:website |site |web page |page )", "", low)
    if low in SITES:
        return SITES[low]

    spoken = re.sub(r"\s+dot\s+", ".", low)
    spoken = spoken.replace(" ", "")
    spoken = re.sub(r"^https?://", "", spoken)
    spoken = re.sub(r"^www\.", "", spoken)
    match = re.fullmatch(r"([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?:/\S*)?", spoken)
    return match.group(1) if match else None


def _typed(text: str | None, target: str | None) -> DesktopAction | None:
    text = (text or "").strip()
    if not text:
        return None
    return DesktopAction("type", text[:MAX_TYPED_CHARS], target)


def parse_desktop_action(text: str) -> DesktopAction | None:
    body = _clean(text)
    if not body:
        return None
    low = body.lower()
    raw = _PREFIX.sub("", text.strip())  # typing keeps your punctuation

    # ---- typing -------------------------------------------------------
    # "open notepad and type hello"
    m = re.match(
        rf"^(?:open|launch|start)(?:\s+up)?(?:\s+the)?\s+({_TARGETS})(?:\s+app)?"
        r"\s+(?:and|then)\s+(?:type|write|dictate)[\s:,-]+(.+)$",
        raw, re.I | re.S,
    )
    if m:
        return _typed(m.group(2), canonical_target(m.group(1)))

    # "type in Notepad: hello"  /  "type in Foo: hello"  (explicit colon, any window)
    m = re.match(
        r"^(?:type|write|enter|dictate)(?:\s+in(?:to)?\s+(.+?))?\s*:\s*(.+)$",
        raw, re.I | re.S,
    )
    if m:
        return _typed(m.group(2), (m.group(1) or "").strip() or None)

    # "type in notepad hello world"
    m = re.match(
        rf"^(?:type|write|dictate)\s+(?:in|into|on)\s+(?:the\s+)?({_TARGETS})"
        r"(?:\s+(?:window|app|application))?[\s,-]+(.+)$",
        raw, re.I | re.S,
    )
    if m:
        return _typed(m.group(2), canonical_target(m.group(1)))

    # "type hello world in notepad"
    m = re.match(
        rf"^(?:type|write|dictate)\s+(.+?)\s+(?:in|into|on)\s+(?:the\s+)?({_TARGETS})"
        r"(?:\s+(?:window|app|application))?[\s.!?]*$",
        raw, re.I | re.S,
    )
    if m:
        return _typed(m.group(1), canonical_target(m.group(2)))

    # "type hello world" -> the window you are using.
    # Only "type"/"dictate" (not "write"/"enter"), so ordinary requests such as
    # "write a poem about my school" are never pasted into a window.
    m = re.match(r"^(?:type|dictate)\s+(.+)$", raw, re.I | re.S)
    if m and not re.match(r"^(?:in|into|on)\b", m.group(1), re.I):
        return _typed(m.group(1), None)

    # ---- screenshot ---------------------------------------------------
    if re.fullmatch(
        r"(?:(?:take|capture|grab|make|get)(?:\s+me)?(?:\s+a|\s+the|\s+my)?\s+"
        r"(?:screen\s?shot|screen capture|screen shot|picture of (?:the|my) screen)"
        r"|screen\s?shot|capture (?:the|my) screen)(?:\s+now)?",
        low,
    ):
        return DesktopAction("screenshot")

    # ---- volume / desktop ---------------------------------------------
    if re.fullmatch(
        r"(?:(?:turn|make|put)\s+(?:the\s+)?(?:volume|sound)\s+(?:up|higher|louder)"
        r"|(?:turn|make)\s+it\s+(?:up|louder)|volume up|louder|"
        r"(?:increase|raise)\s+(?:the\s+)?volume)",
        low,
    ):
        return DesktopAction("volume_up")
    if re.fullmatch(
        r"(?:(?:turn|make|put)\s+(?:the\s+)?(?:volume|sound)\s+(?:down|lower|quieter)"
        r"|(?:turn|make)\s+it\s+(?:down|quieter)|volume down|quieter|"
        r"(?:decrease|reduce|lower)\s+(?:the\s+)?volume)",
        low,
    ):
        return DesktopAction("volume_down")
    if re.fullmatch(r"(?:mute|unmute)(?:\s+(?:the\s+)?(?:sound|volume|audio|computer|pc))?", low):
        return DesktopAction("mute")
    if re.fullmatch(r"(?:show\s+(?:the\s+)?desktop|minimi[sz]e\s+(?:all|everything)(?:\s+windows)?)", low):
        return DesktopAction("show_desktop")

    # ---- web search ---------------------------------------------------
    m = re.match(
        r"^(?:search|look)\s+(?:on\s+|in\s+)?youtube(?:\s+for|\s+up)?\s+(.+)$"
        r"|^youtube\s+search\s+(.+)$"
        r"|^play\s+(.+?)\s+on\s+youtube$",
        body, re.I,
    )
    if m:
        return DesktopAction("search_youtube", next(g for g in m.groups() if g).strip())

    m = re.match(
        r"^(?:(?:search|look)(?:\s+(?:the\s+)?(?:web|internet|online|google))?"
        r"(?:\s+(?:for|up|about))?|google|web\s+search|look\s+up|search\s+up)\s+(.+)$",
        body, re.I,
    )
    if m:
        query = re.sub(r"\s+(?:on|in|using)\s+(?:the\s+)?(?:web|internet|google)$", "",
                       m.group(1).strip(), flags=re.I)
        if query and not re.match(r"^(?:my|this)\s+(?:computer|pc|laptop|files?)\b", query, re.I):
            return DesktopAction("search_web", query[:200])

    # ---- open website / app ---------------------------------------------
    m = re.match(
        r"^(?P<verb>open|launch|start|go\s+to|visit|browse\s+to)(?:\s+up)?"
        r"(?:\s+the)?(?:\s+(?:website|site|web\s+page|page))?\s+(?P<name>.+)$",
        body, re.I,
    )
    if m:
        name = m.group("name").strip()
        site = resolve_site(name)
        if site:
            return DesktopAction("open_site", site)

        if re.match(r"^(?:open|launch|start)$", m.group("verb"), re.I):
            key = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", name.lower())).strip()
            if key not in BUILTIN_APPS:
                return DesktopAction("open_app", name)

    return None
