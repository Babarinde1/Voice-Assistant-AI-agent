import unittest
from unittest.mock import Mock, patch

from assistant.state import AssistantState, StateManager
from assistant.local_intents import build_registry
from assistant.router import AssistantRouter
from audio.speaker import Speaker


class StateTests(unittest.TestCase):
    def test_state_manager_starts_idle_and_updates(self):
        states = StateManager()
        self.assertEqual(states.current, AssistantState.IDLE)
        states.set(AssistantState.SPEAKING)
        self.assertEqual(states.current, AssistantState.SPEAKING)


class Stage5RoutingTests(unittest.TestCase):
    def setUp(self):
        self.router = AssistantRouter(build_registry())

    def test_common_notepad_transcription_variants_are_approved_aliases(self):
        with patch("commands.applications.subprocess.Popen") as popen:
            for phrase in ("open nose pad", "open notes pad", "open noth spot"):
                self.assertEqual(self.router.handle(phrase), "Opening Notepad.")
        self.assertEqual(popen.call_count, 3)

    def test_exact_duplicate_transcript_is_cleaned(self):
        with patch("commands.applications.subprocess.Popen") as popen:
            reply = self.router.handle("Open calculator. Open calculator.")
        self.assertEqual(reply, "Opening Calculator.")
        popen.assert_called_once_with(["calc.exe"], shell=False)


class SpeakerTests(unittest.TestCase):
    def test_disabled_speaker_does_not_try_to_speak(self):
        speaker = Speaker(enabled=False)
        self.assertFalse(speaker.speak("Hello"))

    def test_speaks_using_engine(self):
        engine = Mock()
        with patch.dict("sys.modules", {"pyttsx3": Mock(init=Mock(return_value=engine))}):
            speaker = Speaker(enabled=True)
        self.assertTrue(speaker.speak("Hello"))
        engine.say.assert_called_once_with("Hello")
        engine.runAndWait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
