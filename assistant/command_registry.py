import re
from dataclasses import dataclass
from collections.abc import Callable

from assistant.intent_matcher import build_intent_regex


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse spaces.

    "What time is it?" -> "what time is it"
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text)


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    aliases: tuple[str, ...]
    handler: Callable[[], str]
    # Optional "core" regex patterns for local intent matching (Stage 2).
    patterns: tuple[str, ...] = ()


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._intents: list[tuple[re.Pattern, Command]] = []

    def register(self, command: Command):
        for key in (command.name, *command.aliases):
            normalized = normalize(key)

            if normalized in self._commands:
                raise ValueError(f"Duplicate command alias: {normalized}")

            self._commands[normalized] = command

        for core in command.patterns:
            self._intents.append((build_intent_regex(core), command))

    def find(self, text: str) -> Command | None:
        """Level 1: exact alias match."""
        return self._commands.get(normalize(text))

    def find_by_intent(self, text: str) -> Command | None:
        """Level 2: local intent match using the commands' patterns."""
        normalized = normalize(text)
        for regex, command in self._intents:
            if regex.match(normalized):
                return command
        return None

    def all_commands(self) -> list[Command]:
        """Each command once, in registration order."""
        unique: dict[str, Command] = {}
        for command in self._commands.values():
            unique.setdefault(command.name, command)
        return list(unique.values())
