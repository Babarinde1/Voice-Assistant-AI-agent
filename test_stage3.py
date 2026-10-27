import unittest
from types import SimpleNamespace

import numpy as np

from audio.microphone import SAMPLE_RATE, is_silent, is_too_short, peak_level
from audio.speech_recognition import SpeechRecognizer, create_recognizer


class FakeModel:
    def __init__(self, texts):
        self.texts = texts
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return (SimpleNamespace(text=t) for t in self.texts), None


class Recognizer(unittest.TestCase):
    def test_joins_segments_and_strips_spaces(self):
        model = FakeModel(["  Open ", " Chrome. "])
        text = SpeechRecognizer("x", model=model).transcribe(np.zeros(100, np.float32))
        self.assertEqual(text, "Open Chrome.")

    def test_uses_cpu_friendly_settings(self):
        model = FakeModel(["hi"])
        SpeechRecognizer("x", language="en", model=model).transcribe(np.zeros(100, np.float32))
        self.assertEqual(model.kwargs["beam_size"], 1)
        self.assertTrue(model.kwargs["vad_filter"])
        self.assertEqual(model.kwargs["language"], "en")

    def test_known_hallucinations_are_dropped(self):
        for phrase in ["Thank you.", "you", "Thanks for watching!"]:
            model = FakeModel([phrase])
            self.assertEqual(
                SpeechRecognizer("x", model=model).transcribe(np.zeros(10, np.float32)), ""
            )

    def test_no_speech_gives_empty_string(self):
        self.assertEqual(
            SpeechRecognizer("x", model=FakeModel([])).transcribe(np.zeros(10, np.float32)), ""
        )

    def test_factory_reports_failure_instead_of_crashing(self):
        cfg = SimpleNamespace(
            stt_model_size="base.en", stt_language="en", stt_cpu_threads=1
        )
        import audio.speech_recognition as sr

        original = sr.SpeechRecognizer

        def boom(*a, **k):
            raise RuntimeError("not installed")

        sr.SpeechRecognizer = boom
        try:
            recognizer, status = create_recognizer(cfg)
        finally:
            sr.SpeechRecognizer = original
        self.assertIsNone(recognizer)
        self.assertIn("Voice input is off", status)


class AudioChecks(unittest.TestCase):
    def test_silence_detection(self):
        self.assertTrue(is_silent(np.zeros(SAMPLE_RATE, np.float32)))
        self.assertFalse(is_silent(np.full(SAMPLE_RATE, 0.1, np.float32)))

    def test_too_short(self):
        self.assertTrue(is_too_short(np.zeros(100, np.float32)))
        self.assertFalse(is_too_short(np.zeros(SAMPLE_RATE, np.float32)))

    def test_peak_of_empty_audio(self):
        self.assertEqual(peak_level(np.zeros(0, np.float32)), 0.0)


if __name__ == "__main__":
    unittest.main()
