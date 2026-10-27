import unittest
from unittest.mock import patch

from ai.fallback import create_ai_client
from assistant.local_intents import build_registry
from assistant.router import ACTION_REFUSED, NOT_RECOGNIZED, AssistantRouter


class FakeAI:
    def __init__(self, reply="AI answer", error=None):
        self.calls = []
        self.reply = reply
        self.error = error

    def answer(self, text):
        self.calls.append(text)
        if self.error:
            raise self.error
        return self.reply


def make_router(ai=None, enabled=True):
    return AssistantRouter(build_registry(), ai_client=ai, enable_ai_fallback=enabled)


class IntentMatching(unittest.TestCase):
    def test_polite_phrasing_matches_locally(self):
        ai = FakeAI()
        router = make_router(ai)
        for phrase in [
            "Can you please start Chrome for me?",
            "hey jarvis could you launch google chrome",
            "i want you to open up the notepad",
        ]:
            with patch("commands.applications.subprocess.Popen"), \
                 patch("commands.applications.os.path.exists", return_value=True):
                reply = router.handle(phrase)
            self.assertTrue(reply.startswith("Opening"), (phrase, reply))
        self.assertEqual(ai.calls, [])

    def test_time_and_date_phrasings(self):
        router = make_router(FakeAI())
        self.assertTrue(router.handle("What's the time right now?").startswith("It is"))
        self.assertTrue(router.handle("could you tell me the current time please").startswith("It is"))
        self.assertTrue(router.handle("what day is it today").startswith("Today is"))

    def test_questions_about_apps_are_not_hijacked(self):
        ai = FakeAI()
        router = make_router(ai)
        reply = router.handle("Why does Chrome not open on my laptop?")
        self.assertEqual(reply, "AI answer")
        self.assertEqual(len(ai.calls), 1)


class AIFallback(unittest.TestCase):
    def test_unknown_question_goes_to_ai(self):
        ai = FakeAI("Paris.")
        self.assertEqual(make_router(ai).handle("What is the capital of France?"), "Paris.")

    def test_known_command_never_calls_ai(self):
        ai = FakeAI()
        make_router(ai).handle("what time is it")
        self.assertEqual(ai.calls, [])

    def test_flag_off_means_no_ai(self):
        ai = FakeAI()
        reply = make_router(ai, enabled=False).handle("What is the capital of France?")
        self.assertEqual(reply, NOT_RECOGNIZED)
        self.assertEqual(ai.calls, [])

    def test_no_client_means_local_only(self):
        self.assertEqual(make_router(None).handle("tell me a joke"), NOT_RECOGNIZED)

    def test_ai_failure_is_graceful_and_local_still_works(self):
        router = make_router(FakeAI(error=TimeoutError()))
        self.assertIn("couldn't reach the AI", router.handle("tell me a joke"))
        self.assertTrue(router.handle("time").startswith("It is"))


class ActionSafety(unittest.TestCase):
    def test_action_requests_never_reach_ai(self):
        ai = FakeAI()
        router = make_router(ai)
        for phrase in [
            "delete all my files",
            "please shut down the computer",
            "install python",
            "create a new folder called projects",
            "run notepad.exe",
        ]:
            self.assertEqual(router.handle(phrase), ACTION_REFUSED, phrase)
        self.assertEqual(ai.calls, [])

    def test_unknown_app_gets_a_helpful_answer_not_the_ai(self):
        ai = FakeAI()
        reply = make_router(ai).handle("open spotify")
        self.assertIn("could not find", reply)   # Stage 7+: says what went wrong
        self.assertEqual(ai.calls, [])

    def test_how_to_questions_are_allowed_through(self):
        ai = FakeAI("Use os.remove.")
        router = make_router(ai)
        self.assertEqual(router.handle("how do I delete a file in Python"), "Use os.remove.")


class Factory(unittest.TestCase):
    def test_not_configured_returns_none(self):
        class Cfg:
            enable_ai_fallback = True
            ai_api_key = None
            ai_model = None
            ai_base_url = None
            ai_timeout_seconds = 5.0

        client, status = create_ai_client(Cfg())
        self.assertIsNone(client)
        self.assertIn("AI_API_KEY", status)


if __name__ == "__main__":
    unittest.main()
