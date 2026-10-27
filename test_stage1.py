import unittest
from unittest.mock import patch

from assistant.command_registry import Command, CommandRegistry
from assistant.local_intents import build_registry
from assistant.router import AssistantRouter


class Stage1Tests(unittest.TestCase):
    def setUp(self):
        self.router = AssistantRouter(build_registry())

    def test_alias_and_punctuation_match(self):
        self.assertTrue(self.router.handle("What time is it?").startswith("It is"))
        self.assertTrue(self.router.handle("  WHATS   THE TIME ").startswith("It is"))

    def test_unknown_command(self):
        self.assertIn("don't recognize", self.router.handle("dance for me"))

    def test_empty_input(self):
        self.assertEqual(self.router.handle("   "), "I didn't hear a command.")

    def test_duplicate_alias_rejected(self):
        registry = CommandRegistry()
        cmd = Command("a", "d", ("b",), lambda: "x")
        registry.register(cmd)
        with self.assertRaises(ValueError):
            registry.register(Command("b", "d", (), lambda: "y"))

    def test_handler_crash_is_contained(self):
        registry = CommandRegistry()
        registry.register(Command("boom", "d", (), lambda: 1 / 0))
        reply = AssistantRouter(registry).handle("boom")
        self.assertIn("went wrong", reply)

    def test_app_launch_never_uses_shell(self):
        with patch("commands.applications.subprocess.Popen") as popen:
            reply = self.router.handle("open notepad")
        popen.assert_called_once_with(["notepad.exe"], shell=False)
        self.assertEqual(reply, "Opening Notepad.")

    def test_missing_app_reports_honestly(self):
        with patch("commands.applications.subprocess.Popen", side_effect=FileNotFoundError):
            reply = self.router.handle("open calculator")
        self.assertIn("couldn't find", reply)

    def test_help_lists_commands(self):
        self.assertIn("open chrome", self.router.handle("help"))


if __name__ == "__main__":
    unittest.main()
