import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant.logging_setup import configure_logging
from assistant.state import AssistantState, StateManager
from assistant.local_intents import build_registry
from assistant.router import AssistantRouter, ACTION_REFUSED


class Stage6Tests(unittest.TestCase):
    def test_logging_setup_creates_log_directory_and_file_path(self):
        # The helper returns the intended log location; no secret values are needed.
        path = configure_logging("INFO")
        self.assertTrue(path.name == "jarvis.log")
        self.assertTrue(path.parent.name == "logs")

    def test_approved_command_still_runs_locally(self):
        router = AssistantRouter(build_registry())
        with patch("commands.applications.subprocess.Popen") as popen:
            self.assertEqual(router.handle("open calculator"), "Opening Calculator.")
        popen.assert_called_once_with(["calc.exe"], shell=False)

    def test_unknown_action_stays_blocked(self):
        class FakeAI:
            def answer(self, text):
                raise AssertionError("AI must not receive action requests")
        router = AssistantRouter(build_registry(), FakeAI(), True)
        self.assertEqual(router.handle("delete all files"), ACTION_REFUSED)

    def test_state_manager_updates_state(self):
        states = StateManager()
        states.set(AssistantState.PROCESSING)
        self.assertEqual(states.current, AssistantState.PROCESSING)


if __name__ == "__main__":
    unittest.main()
