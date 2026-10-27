import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from assistant.desktop_intents import DesktopAction, parse_desktop_action
from assistant.local_intents import build_registry
from assistant.router import AssistantRouter
from audio.endpointing import Endpointer, Rechunker
from audio.listener import HandsFreeListener, block_level, record_utterance
from audio.vad import EnergyVAD, SileroVAD, create_vad
from commands import desktop_actions as da

LOUD = np.full(480, 6000, dtype=np.int16)
QUIET = np.zeros(480, dtype=np.int16)


def fake_vad(frame):
    return int(np.max(np.abs(frame))) > 1000


def run(pattern, **kwargs):
    """pattern: list of (frame, count). Returns the finished Endpointer."""
    ep = Endpointer(fake_vad, **kwargs)
    for frame, count in pattern:
        for _ in range(count):
            if ep.feed(frame):
                return ep
    return ep


class EndpointerTests(unittest.TestCase):
    def test_speech_then_pause_finishes(self):
        ep = run([(QUIET, 10), (LOUD, 30), (QUIET, 60)], end_silence_ms=900)
        self.assertEqual(ep.reason, "done")
        self.assertGreater(ep.audio.size, 30 * 480)

    def test_pre_roll_keeps_first_syllable(self):
        ep = run([(QUIET, 20), (LOUD, 30), (QUIET, 60)])
        # voiced frames + at most the pre-roll, never the whole 20 quiet frames
        self.assertLess(ep.audio.size, (30 + 10 + 10 + 1) * 480)
        self.assertGreaterEqual(ep.audio.size, 30 * 480)

    def test_trailing_silence_is_trimmed(self):
        ep = run([(LOUD, 30), (QUIET, 60)], end_silence_ms=900)
        quiet_frames_kept = ep.audio.size // 480 - 30
        self.assertLessEqual(quiet_frames_kept, 10)

    def test_nobody_speaks(self):
        ep = run([(QUIET, 1000)], no_speech_timeout_s=2.0)
        self.assertEqual(ep.reason, "no_speech")
        self.assertEqual(ep.audio.size, 0)

    def test_click_is_too_short(self):
        ep = run([(LOUD, 4), (QUIET, 60)], end_silence_ms=600)
        self.assertEqual(ep.reason, "too_short")
        self.assertEqual(ep.audio.size, 0)

    def test_two_frame_blip_never_starts(self):
        ep = run([(LOUD, 2), (QUIET, 300)], no_speech_timeout_s=3.0)
        self.assertEqual(ep.reason, "no_speech")

    def test_keeps_going_through_short_pauses(self):
        ep = run([(LOUD, 20), (QUIET, 10), (LOUD, 20), (QUIET, 60)], end_silence_ms=900)
        self.assertEqual(ep.reason, "done")
        self.assertGreaterEqual(ep.audio.size, 50 * 480)

    def test_max_length(self):
        ep = run([(LOUD, 5000)], max_seconds=2.0)
        self.assertEqual(ep.reason, "max_length")

    def test_rechunker_carries_remainder(self):
        r = Rechunker(480)
        frames = list(r.feed(np.zeros(1280, np.int16))) + list(r.feed(np.zeros(1280, np.int16)))
        self.assertEqual([f.size for f in frames], [480] * 5)  # 2560 // 480, 160 left over


class VadTests(unittest.TestCase):
    def test_energy_vad_learns_noise_and_hears_speech(self):
        rng = np.random.default_rng(1)
        vad = EnergyVAD()
        hum = lambda: (rng.normal(0, 150, 480)).astype(np.int16)
        self.assertFalse(any(vad.is_speech(hum()) for _ in range(40)))
        voice = (rng.normal(0, 4000, 480)).astype(np.int16)
        self.assertTrue(vad.is_speech(voice))

    def test_energy_vad_silence_is_not_speech(self):
        vad = EnergyVAD()
        self.assertFalse(any(vad.is_speech(QUIET) for _ in range(20)))

    def test_silero_wrapper_applies_threshold(self):
        class FakeSilero:
            def __init__(self, p): self.p = p
            def predict(self, frame, frame_size): return self.p
            def reset_states(self): pass
        self.assertTrue(SileroVAD(0.5, vad=FakeSilero(0.8)).is_speech(QUIET))
        self.assertFalse(SileroVAD(0.5, vad=FakeSilero(0.2)).is_speech(QUIET))

    def test_factory_energy_and_auto_never_raise(self):
        vad, name = create_vad("energy")
        self.assertIsInstance(vad, EnergyVAD)
        vad, name = create_vad("auto")
        self.assertTrue(callable(vad.is_speech))


class FakeStream:
    def __init__(self, blocks):
        self.blocks = list(blocks)

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def read(self, n):
        block = self.blocks.pop(0) if self.blocks else np.zeros(n, np.int16)
        return block.reshape(-1, 1), False


class FakeSD:
    def __init__(self, blocks): self.stream = FakeStream(blocks)
    def InputStream(self, **kw): return self.stream


class FakeWake:
    def __init__(self, scores): self.scores, self.resets = list(scores), 0
    def reset(self): self.resets += 1
    def predict(self, block): return {"hey_jarvis": self.scores.pop(0)}


def blk(value): return np.full(1280, value, dtype=np.int16)


class ListenerTests(unittest.TestCase):
    def test_wake_then_request_then_pause(self):
        blocks = [blk(0)] * 3 + [blk(0)] + [blk(6000)] * 14 + [blk(0)] * 25
        wake = FakeWake([0.0, 0.1, 0.2, 0.9])
        levels, woke = [], []
        listener = HandsFreeListener(
            wake, types.SimpleNamespace(is_speech=fake_vad), FakeSD(blocks),
            wake_grace_ms=0, chime=False,
            on_level=levels.append, on_wake=lambda: woke.append(1),
        )
        capture = listener.listen()
        self.assertEqual(wake.resets, 1)
        self.assertEqual(woke, [1])
        self.assertEqual(capture.reason, "done")
        self.assertGreater(capture.audio.size, 14 * 1280 * 0.8)
        self.assertTrue(levels and max(levels) > 0.5)

    def test_wake_then_silence_times_out(self):
        blocks = [blk(0)] * 200
        wake = FakeWake([0.9])
        listener = HandsFreeListener(
            wake, types.SimpleNamespace(is_speech=fake_vad), FakeSD(blocks),
            no_speech_timeout_s=1.0, wake_grace_ms=0, chime=False,
        )
        self.assertEqual(listener.listen().reason, "no_speech")

    def test_record_utterance_without_wake_word(self):
        blocks = [blk(0)] * 3 + [blk(6000)] * 12 + [blk(0)] * 25
        cap = record_utterance(FakeSD(blocks), types.SimpleNamespace(is_speech=fake_vad))
        self.assertEqual(cap.reason, "done")

    def test_block_level_range(self):
        self.assertEqual(block_level(np.zeros(1280, np.int16)), 0.0)
        self.assertGreater(block_level(blk(8000)), 0.7)
        self.assertLessEqual(block_level(blk(32000)), 1.0)


class ParseTests(unittest.TestCase):
    def check(self, sentence, kind, **fields):
        action = parse_desktop_action(sentence)
        self.assertIsNotNone(action, sentence)
        self.assertEqual(action.kind, kind, sentence)
        for key, value in fields.items():
            self.assertEqual(getattr(action, key), value, (sentence, key))

    def test_web_search(self):
        self.check("Hey Jarvis, search for the best jollof rice recipe", "search_web", text="the best jollof rice recipe")
        self.check("google weather in Ibadan", "search_web", text="weather in Ibadan")
        self.check("look up Python tutorials", "search_web", text="Python tutorials")
        self.check("search the web for solar panels please", "search_web", text="solar panels")

    def test_youtube(self):
        self.check("search youtube for afrobeats mix", "search_youtube", text="afrobeats mix")
        self.check("play burna boy on youtube", "search_youtube", text="burna boy")

    def test_local_searches_are_not_web_searches(self):
        self.assertIsNone(parse_desktop_action("search my computer for photos"))

    def test_screenshot(self):
        for t in ["take a screenshot", "Take a screenshot please.", "screenshot", "capture my screen", "grab the screen shot"]:
            self.check(t, "screenshot")

    def test_typing_forms(self):
        self.check("open notes pad and type Hello world, this is a test.", "type",
                   text="Hello world, this is a test.", target="notepad")
        self.check("type in notepad hello there", "type", text="hello there", target="notepad")
        self.check("type hello world in notepad.", "type", text="hello world", target="notepad")
        self.check("Type in Notepad: Hello from Jarvis", "type", text="Hello from Jarvis", target="Notepad")
        self.check("type: Hello world", "type", text="Hello world", target=None)
        self.check("dictate good morning everyone", "type", text="good morning everyone", target=None)

    def test_ordinary_requests_are_never_typed(self):
        for t in ["write a poem about my school", "enter the date", "type in", "what is typing speed"]:
            self.assertIsNone(parse_desktop_action(t), t)

    def test_volume_and_desktop(self):
        self.check("turn the volume up", "volume_up")
        self.check("make it quieter", "volume_down")
        self.check("mute", "mute")
        self.check("show desktop", "show_desktop")

    def test_websites_and_apps(self):
        self.check("open youtube", "open_site", text="youtube.com")
        self.check("go to wikipedia.org", "open_site", text="wikipedia.org")
        self.check("open example dot com", "open_site", text="example.com")
        self.check("open Paint", "open_app", text="Paint")
        self.check("launch Microsoft Word", "open_app", text="Microsoft Word")

    def test_builtin_apps_stay_with_the_registry(self):
        for t in ["open chrome", "open notepad", "open calculator", "open notes pad", "what time is it"]:
            self.assertIsNone(parse_desktop_action(t), t)

    def test_dangerous_things_are_not_actions(self):
        for t in ["delete all my files", "shut down the computer", "open C:\\Windows\\System32\\cmd.exe"]:
            action = parse_desktop_action(t)
            self.assertTrue(action is None or action.kind == "open_app", t)


class RouterDispatchTests(unittest.TestCase):
    def setUp(self):
        self.router = AssistantRouter(build_registry())

    def test_each_action_calls_its_approved_function(self):
        cases = {
            "search for cats": ("web_search", ("cats",), {}),
            "search youtube for cats": ("web_search", ("cats",), {"engine": "youtube"}),
            "open youtube": ("open_website", ("youtube.com",), {}),
            "take a screenshot": ("take_screenshot", (), {}),
            "turn the volume up": ("change_volume", ("up",), {}),
            "mute": ("toggle_mute", (), {}),
            "show desktop": ("show_desktop", (), {}),
            "type in notepad: hi": ("type_text", ("hi", "notepad"), {}),
        }
        for sentence, (func, args, kwargs) in cases.items():
            with patch(f"assistant.router.{func}", return_value="ok") as mocked:
                self.assertEqual(self.router.handle(sentence), "ok", sentence)
                mocked.assert_called_once()
                got_args, got_kwargs = mocked.call_args
                self.assertEqual(got_args, args, sentence)
                self.assertEqual(got_kwargs, kwargs, sentence)

    def test_failing_action_does_not_crash(self):
        with patch("assistant.router.take_screenshot", side_effect=RuntimeError("boom")):
            self.assertIn("went wrong", self.router.handle("take a screenshot"))

    def test_questions_still_reach_the_ai_and_actions_do_not(self):
        calls = []
        class AI:
            def answer(self, t): calls.append(t); return "answer"
        router = AssistantRouter(build_registry(), AI(), True)
        self.assertEqual(router.handle("why is the sky blue"), "answer")
        with patch("assistant.router.web_search", return_value="ok"):
            router.handle("search for why the sky is blue")
        self.assertEqual(calls, ["why is the sky blue"])


class DesktopActionTests(unittest.TestCase):
    def setUp(self):
        sleep = patch.object(da.time, "sleep", lambda s: None)
        sleep.start(); self.addCleanup(sleep.stop)

    def test_web_search_url_is_encoded_and_https(self):
        with patch.object(da.webbrowser, "open", return_value=True) as opened:
            self.assertIn("Searching the web for", da.web_search("jollof & rice"))
        self.assertEqual(opened.call_args[0][0], "https://www.google.com/search?q=jollof+%26+rice")

    def test_youtube_search_url(self):
        with patch.object(da.webbrowser, "open", return_value=True) as opened:
            da.web_search("afrobeats", engine="youtube")
        self.assertEqual(opened.call_args[0][0], "https://www.youtube.com/results?search_query=afrobeats")

    def test_no_browser_is_reported(self):
        with patch.object(da.webbrowser, "open", return_value=False):
            self.assertIn("could not open", da.web_search("x"))

    def test_screenshot_saves_file_and_runs_hooks(self):
        from PIL import Image

        order = []
        da.set_screenshot_hooks(lambda: order.append("hide"), lambda: order.append("show"))
        self.addCleanup(da.set_screenshot_hooks)
        with tempfile.TemporaryDirectory() as home, \
             patch.object(Path, "home", return_value=Path(home)), \
             patch("PIL.ImageGrab.grab", side_effect=lambda **k: order.append("grab") or Image.new("RGB", (40, 30))):
            reply = da.take_screenshot()
            files = list((Path(home) / "Pictures" / "Jarvis Screenshots").glob("screenshot_*.png"))
        self.assertIn("Screenshot saved", reply)
        self.assertEqual(len(files), 1)
        self.assertEqual(order, ["hide", "grab", "show"])

    def _fake_gui(self, windows, clipboard="old clipboard"):
        pasted = []
        state = {"clip": clipboard, "active": None}
        class Win:
            def __init__(self, title): self.title = title
            def activate(self): state["active"] = self
            def minimize(self): pass
            def restore(self): state["active"] = self
        wins = [Win(t) for t in windows]
        gw = types.SimpleNamespace(getAllWindows=lambda: wins, getActiveWindow=lambda: state["active"])
        pc = types.SimpleNamespace(copy=lambda t: state.update(clip=t), paste=lambda: state["clip"])
        pa = types.SimpleNamespace(hotkey=lambda *k: pasted.append((state["clip"], k)))
        mods = {"pygetwindow": gw, "pyperclip": pc, "pyautogui": pa}
        return mods, pasted, state, wins, Win

    def test_type_into_open_notepad_and_restore_clipboard(self):
        mods, pasted, state, wins, _ = self._fake_gui(["Untitled - Notepad", "Other"])
        with patch.dict(sys.modules, mods):
            reply = da.type_text("Hello Jarvis", "notepad")
        self.assertEqual(pasted, [("Hello Jarvis", ("ctrl", "v"))])
        self.assertEqual(state["clip"], "old clipboard")
        self.assertIn("Typed your text", reply)

    def test_notepad_is_started_when_not_open(self):
        mods, pasted, state, wins, Win = self._fake_gui(["Other"])
        def launch(name):
            wins.append(Win("Untitled - Notepad")); return "Opening notepad."
        with patch.dict(sys.modules, mods), patch.object(da, "open_application", side_effect=launch) as opener:
            reply = da.type_text("Hi", "notepad")
        opener.assert_called_once_with("notepad")
        self.assertEqual(len(pasted), 1)

    def test_other_closed_app_is_not_started(self):
        mods, pasted, *_ = self._fake_gui(["Other"])
        with patch.dict(sys.modules, mods), patch.object(da, "open_application") as opener:
            reply = da.type_text("Hi", "Excel")
        opener.assert_not_called()
        self.assertEqual(pasted, [])
        self.assertIn("Open it first", reply)

    def test_empty_text(self):
        self.assertEqual(da.type_text("   "), "Tell me what text to type.")

    def test_volume_keys(self):
        pressed = []
        pa = types.SimpleNamespace(press=lambda k, presses=1, interval=0: pressed.append((k, presses)),
                                   hotkey=lambda *k: pressed.append(k))
        with patch.dict(sys.modules, {"pyautogui": pa}):
            da.change_volume("up"); da.change_volume("down"); da.toggle_mute(); da.show_desktop()
        self.assertEqual(pressed, [("volumeup", 5), ("volumedown", 5), ("volumemute", 1), ("win", "d")])


class OrbTests(unittest.TestCase):
    def test_off_style_is_silent(self):
        from ui.orb import NullOrb, create_orb
        orb = create_orb("off")
        self.assertIsInstance(orb, NullOrb)
        orb.set_state("RECORDING"); orb.set_level(0.5); orb.close()

    def test_qt_orb_paints_with_real_transparency(self):
        try:
            import PySide6  # noqa: F401
        except ImportError:
            self.skipTest("PySide6 not installed")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtWidgets import QApplication
        from ui.qt_orb import STYLES, OrbWidget

        app = QApplication.instance() or QApplication([])
        widget = OrbWidget(None)
        for state in STYLES:
            widget.set_state(state)
            image = QImage(260, 300, QImage.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 0))
            widget.render(image)
            self.assertEqual(image.pixelColor(2, 2).alpha(), 0, state)       # corner is see-through
            self.assertGreater(image.pixelColor(130, 122).alpha(), 100, state)  # orb is drawn


if __name__ == "__main__":
    unittest.main()
