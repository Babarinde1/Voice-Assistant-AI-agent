import logging

from ai.errors import describe_ai_error
from assistant.command_registry import CommandRegistry, normalize
from assistant.desktop_intents import DesktopAction, parse_desktop_action
from assistant.intent_matcher import looks_like_action
from commands.desktop_actions import (
    change_volume,
    open_application,
    open_website,
    show_desktop,
    take_screenshot,
    toggle_mute,
    type_text,
    web_search,
)

NOT_RECOGNIZED = "I don't recognize that command yet. Say 'help' to see what I can do."

logger = logging.getLogger(__name__)

ACTION_REFUSED = (
    "I can't do that yet. I only run approved commands, "
    "and I don't let the AI control the computer. Say 'help' to see what I can do."
)


class AssistantRouter:
    """Router:

    0. Approved desktop actions (search, screenshot, typing, apps...)  (local)
    1. Exact command match                                              (local)
    2. Local intent match                                               (local)
    3. Agent (Stage 9): approved tools, validated, risky ones need a spoken yes
    4. AI fallback, only for questions and only if enabled (used when the agent is off)
    """

    def __init__(
        self,
        registry: CommandRegistry,
        ai_client=None,
        enable_ai_fallback: bool = False,
        agent=None,
    ):
        self.registry = registry
        self.ai_client = ai_client
        self.enable_ai_fallback = enable_ai_fallback
        # Stage 9: optional agent that can use approved tools for anything
        # the fixed local commands do not cover. Set after construction in main.py.
        self.agent = agent
        # True when the last reply was a question to the user, so the program should
        # keep listening for the answer instead of going back to sleep.
        self.wants_followup = False

    @property
    def ai_active(self) -> bool:
        return self.enable_ai_fallback and self.ai_client is not None

    def handle(self, text: str) -> str:
        self.wants_followup = False
        text = text.strip()

        # Whisper can occasionally repeat an entire command in its transcript.
        words = normalize(text).split()
        if len(words) >= 2 and len(words) % 2 == 0:
            midpoint = len(words) // 2
            if words[:midpoint] == words[midpoint:]:
                text = " ".join(words[:midpoint])

        if not text:
            return "I didn't hear a command."

        # Approved desktop actions never go through the AI model.
        action = parse_desktop_action(text)
        if action is not None:
            return self._run_desktop(action)

        # Levels 1 and 2: local, offline, deterministic.
        command = self.registry.find(text) or self.registry.find_by_intent(text)

        if command is not None:
            logger.info("Approved local command matched: %s", command.name)
            return self._run(command)

        # Stage 9: the agent plans with approved, validated, confirm-gated tools.
        if self.agent is not None and self.enable_ai_fallback:
            try:
                logger.info("Handing request to the agent")
                reply = self.agent.handle(text)
                self.wants_followup = reply.rstrip().endswith("?")
                return reply
            except Exception as error:
                spoken, label = describe_ai_error(error)
                logger.warning("Agent failed: %s", label)
                print(f"[AI error] {label}")
                return spoken

        # Without the agent, requests to change the computer never go to the AI as chat.
        if looks_like_action(normalize(text)):
            logger.warning("Unapproved computer action refused")
            return ACTION_REFUSED

        # Level 3: AI fallback, if allowed.
        if not self.ai_active:
            logger.info("Unmatched request; AI fallback unavailable or disabled")
            return NOT_RECOGNIZED

        try:
            logger.info("Sending a non-action request to AI fallback")
            return self.ai_client.answer(text)
        except Exception as error:
            logger.warning("AI fallback failed: %s: %s", type(error).__name__, error)
            return (
                "I couldn't reach the AI service. "
                "My local commands are still available."
            )

    @staticmethod
    def _run_desktop(action: DesktopAction) -> str:
        # Only the action kind is logged, never what you typed or searched.
        logger.info("Desktop action: %s", action.kind)
        try:
            if action.kind == "open_app":
                return open_application(action.text)
            if action.kind == "open_site":
                return open_website(action.text)
            if action.kind == "search_web":
                return web_search(action.text)
            if action.kind == "search_youtube":
                return web_search(action.text, engine="youtube")
            if action.kind == "screenshot":
                return take_screenshot()
            if action.kind == "type":
                return type_text(action.text, action.target)
            if action.kind == "volume_up":
                return change_volume("up")
            if action.kind == "volume_down":
                return change_volume("down")
            if action.kind == "mute":
                return toggle_mute()
            if action.kind == "show_desktop":
                return show_desktop()
        except Exception as error:
            logger.error("Desktop action failed: %s (%s)", action.kind, type(error).__name__)
            return "Something went wrong while doing that."
        return NOT_RECOGNIZED

    @staticmethod
    def _run(command) -> str:
        try:
            return command.handler()
        except Exception as error:
            # A broken handler must never crash the assistant.
            logger.error("Approved command handler failed: %s (%s)", command.name, type(error).__name__)
            return f"Something went wrong while running '{command.name}'."
