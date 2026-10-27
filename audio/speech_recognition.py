"""Local speech-to-text with faster-whisper. Runs fully offline after the
model has been downloaded once."""
import re

# Whisper sometimes "hears" these in near-silence or noise. A one-word
# hallucination must not be sent on to the AI as if you had asked it.
KNOWN_HALLUCINATIONS = {
    "you",
    "thank you",
    "thanks for watching",
    "thank you for watching",
}


def _clean(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


class SpeechRecognizer:
    def __init__(
        self,
        model_size: str,
        language: str | None = "en",
        cpu_threads: int = 4,
        compute_type: str = "int8",
        model=None,  # lets tests inject a fake model
    ):
        self.language = language

        if model is not None:
            self._model = model
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "The 'faster-whisper' package is not installed. "
                "Run: pip install faster-whisper"
            ) from error

        # int8 uses less memory and is faster on a CPU than the default.
        self._model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )

    def transcribe(self, audio) -> str:
        """audio: float32 numpy array, 16 kHz, mono."""
        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=True,                   # skip silent stretches
            condition_on_previous_text=False,  # avoids runaway repetition
        )

        # `segments` is lazy: the actual work happens as we loop over it.
        text = " ".join(segment.text.strip() for segment in segments).strip()

        if _clean(text) in KNOWN_HALLUCINATIONS:
            return ""

        return text


def create_recognizer(config) -> tuple[SpeechRecognizer | None, str]:
    """Return (recognizer, status). (None, reason) keeps typed mode working."""
    try:
        recognizer = SpeechRecognizer(
            model_size=config.stt_model_size,
            language=config.stt_language,
            cpu_threads=config.stt_cpu_threads,
        )
    except Exception as error:
        return None, f"Voice input is off: {error}"

    return recognizer, f"Voice input is on (model: {config.stt_model_size})."
