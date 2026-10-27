import unittest
from unittest.mock import patch
from assistant.local_intents import build_registry
from assistant.router import AssistantRouter

class Stage7DesktopControlTests(unittest.TestCase):
    def setUp(self):
        self.router = AssistantRouter(build_registry())

    def test_generic_app_launch_uses_local_discovery(self):
        with patch("assistant.router.open_application", return_value="Opening Paint.") as launch:
            self.assertEqual(self.router.handle("open Paint"), "Opening Paint.")
            launch.assert_called_once_with("Paint")

    def test_type_into_named_window(self):
        with patch("assistant.router.type_text", return_value="Typed your text into the active window.") as typer:
            result = self.router.handle("type in Notepad: Hello from Jarvis")
            self.assertEqual(result, "Typed your text into the active window.")
            typer.assert_called_once_with("Hello from Jarvis", "Notepad")

    def test_type_into_active_window(self):
        with patch("assistant.router.type_text", return_value="Typed your text into the active window.") as typer:
            self.router.handle("type: Hello world")
            typer.assert_called_once_with("Hello world", None)

if __name__ == "__main__":
    unittest.main()
