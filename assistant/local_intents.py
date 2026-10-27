from assistant.command_registry import Command, CommandRegistry
from commands.applications import (
    open_calculator,
    open_chrome,
    open_notepad,
)
from commands.system import get_battery, get_date, get_time

# Patterns are written for NORMALIZED text: lowercase, no punctuation,
# so "what's" becomes "whats". Filler like "can you please ... for me"
# is handled by assistant/intent_matcher.py, not here.


def build_registry() -> CommandRegistry:
    registry = CommandRegistry()

    registry.register(Command(
        name="open chrome",
        description="Open Google Chrome",
        aliases=("launch chrome", "start chrome", "open google chrome"),
        handler=open_chrome,
        patterns=(r"(?:open|launch|start)(?: up)?(?: the)?(?: google)? chrome(?: browser)?",),
    ))
    registry.register(Command(
        name="open notepad",
        description="Open Notepad",
        aliases=(
            "launch notepad", "start notepad", "open nose pad", "open notes pad",
            "open noth spot", "open noth pad", "open notepad app",
        ),
        handler=open_notepad,
        patterns=(
            r"(?:open|launch|start)(?: up)?(?: the)?(?: windows)? notepad",
            r"(?:open|launch|start)(?: up)?(?: the)? nose pad",
            r"(?:open|launch|start)(?: up)?(?: the)? notes pad",
            r"(?:open|launch|start)(?: up)?(?: the)? noth spot",
            r"(?:open|launch|start)(?: up)?(?: the)? noth pad",
        ),
    ))
    registry.register(Command(
        name="open calculator",
        description="Open Calculator",
        aliases=("launch calculator", "start calculator", "open calc"),
        handler=open_calculator,
        patterns=(r"(?:open|launch|start)(?: up)?(?: the)? (?:calculator|calc)",),
    ))
    registry.register(Command(
        name="what time is it",
        description="Tell the current time",
        aliases=("time", "whats the time", "tell me the time"),
        handler=get_time,
        patterns=(
            r"what(?:s| is)(?: the)? time(?: is it)?",
            r"what time is it(?: now)?",
            r"tell me the (?:current )?time",
            r"(?:do you know )?what time it is",
            r"current time",
        ),
    ))
    registry.register(Command(
        name="what is the date",
        description="Tell today's date",
        aliases=("date", "whats the date", "what day is it", "todays date"),
        handler=get_date,
        patterns=(
            r"what(?:s| is)(?: the| todays)? date(?: today)?",
            r"what day is it(?: today)?",
            r"tell me (?:the|todays) date",
            r"todays date",
        ),
    ))
    registry.register(Command(
        name="battery status",
        description="Report the battery level",
        aliases=("battery", "how much battery", "check battery"),
        handler=get_battery,
        patterns=(
            r"(?:check|show|tell me)(?: my| the)? battery(?: status| level| percentage)?",
            r"how much battery(?: do i have| is left| left)?",
            r"what(?:s| is)(?: my| the) battery(?: status| level| percentage)?",
            r"battery(?: status| level| percentage)",
        ),
    ))

    def list_commands() -> str:
        names = [c.name for c in registry.all_commands()]
        return (
            "I can do these: " + ", ".join(names) + ". I can also search the web or YouTube, "
            "open websites and installed apps, take a screenshot, change the volume, "
            "and type for you, for example: open Notepad and type hello."
        )

    registry.register(Command(
        name="help",
        description="List available commands",
        aliases=("what can you do", "list commands", "commands"),
        handler=list_commands,
        patterns=(
            r"what can you do",
            r"what commands do you have",
            r"(?:list|show)(?: me)?(?: all)?(?: the)? commands",
            r"help(?: me)?",
        ),
    ))

    return registry
