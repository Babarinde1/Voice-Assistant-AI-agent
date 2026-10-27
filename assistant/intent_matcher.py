"""Local intent matching: rule-based, fast, offline, no model needed.

A command lists a few *core* patterns (what the user wants). This module
wraps each core pattern so that polite filler is allowed around it, but
nothing else is. That keeps matching strict:

    "can you please start chrome for me"   -> matches "open chrome"
    "why does chrome not open on my laptop" -> does NOT match (it's a question)
"""
import re

# Words allowed BEFORE the core pattern.
_PREFIX = (
    r"^(?:(?:hey|ok|okay|please|kindly|jarvis|can you|could you|"
    r"would you|will you|i want you to|i want to|i need you to)\s+)*"
)

# Words allowed AFTER the core pattern.
_SUFFIX = r"(?:\s+(?:right now|for me|please|now|thanks|thank you))*$"


def build_intent_regex(core: str) -> re.Pattern:
    """core must be written for already-normalized text (lowercase, no punctuation)."""
    return re.compile(_PREFIX + r"(?:" + core + r")" + _SUFFIX)


# Verbs that ask the assistant to CHANGE the computer. If a request starts
# like this and no approved local command matched, it must not be passed to
# the AI as if it were a chat question. (First-pass safety net. Stage 6
# replaces it with validated, structured actions.)
_ACTION_START = re.compile(
    _PREFIX
    + r"(?:delete|remove|erase|wipe|format|shut ?down|restart|reboot|"
    r"install|uninstall|kill|terminate|close|quit|run|execute|move|rename|"
    r"copy|download|upload|lock|sign out|log ?off|turn (?:off|on)|"
    r"open|launch|start|click|press|enable|disable|"
    r"create (?:a |an |the )?(?:new )?(?:folder|file|directory|project))\b"
)


def looks_like_action(normalized_text: str) -> bool:
    return _ACTION_START.match(normalized_text) is not None
