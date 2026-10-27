"""Simple explicit runtime states for the voice assistant."""
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AssistantState(str, Enum):
    IDLE = "IDLE"
    WAITING_FOR_WAKE_WORD = "WAITING_FOR_WAKE_WORD"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    STOPPED = "STOPPED"


class StateManager:
    def __init__(self, on_state_change=None):
        self.current = AssistantState.IDLE
        self.on_state_change = on_state_change

    def set(self, state: AssistantState) -> None:
        if state != self.current:
            self.current = state
            print(f"[STATE] {state.value}")
            logger.info("State changed to %s", state.value)
            if self.on_state_change is not None:
                try:
                    self.on_state_change(state)
                except Exception as error:
                    logger.warning("State-change UI callback failed (%s)", type(error).__name__)
