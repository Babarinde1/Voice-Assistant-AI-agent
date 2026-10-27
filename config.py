from dataclasses import dataclass
import os

# Optional: loads KEY=value lines from a .env file into the environment.
# The assistant still runs without python-dotenv; you just set variables yourself.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Config:
    assistant_name: str = "Jarvis"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Local-first routing. The router only uses AI when this is True
    # AND an AI client could be created (key + model configured).
    enable_ai_fallback: bool = True

    # AI provider settings come from the environment, never from source code.
    ai_api_key: str | None = os.getenv("AI_API_KEY")
    ai_model: str | None = os.getenv("AI_MODEL")
    # Optional. Leave empty for the provider's default cloud endpoint.
    # For a local server (Ollama, LM Studio...) set it, e.g. http://localhost:11434/v1
    ai_base_url: str | None = os.getenv("AI_BASE_URL")
    ai_timeout_seconds: float = 20.0

    # Speech recognition (Stage 3). Runs fully on this computer.
    # "base.en" is a starting point for an i5 with no GPU; benchmark with
    # benchmark_stt.py and pick the best size for you. Drop ".en" for
    # other languages, e.g. STT_MODEL=base and STT_LANGUAGE=yo.
    stt_model_size: str = os.getenv("STT_MODEL", "base.en")
    stt_language: str = os.getenv("STT_LANGUAGE", "en")
    stt_cpu_threads: int = int(os.getenv("STT_CPU_THREADS", "4"))

    # Microphone: leave empty for the Windows default input device.
    # Run audio_check.py to see device numbers.
    audio_input_device: str | None = os.getenv("AUDIO_INPUT_DEVICE") or None
    max_recording_seconds: float = 15.0

    # Stage 4: local openWakeWord detector. Scores range from 0 to 1.
    wake_word_threshold: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))
    # Software volume boost for a quiet microphone (1.0 = none, 3.0 = three times louder).
    # Run `python wake_test.py` to get a recommended value.
    mic_gain: float = float(os.getenv("MIC_GAIN", "1.0"))

    # Stage 5: local offline speech output (Windows SAPI via pyttsx3).
    tts_enabled: bool = os.getenv("TTS_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    tts_rate: int = int(os.getenv("TTS_RATE", "175"))
    tts_volume: float = float(os.getenv("TTS_VOLUME", "1.0"))

    # Stage 8: automatic start/stop of speech. When on, you never press Enter:
    # Jarvis hears you start talking and stops when you pause.
    auto_endpoint: bool = os.getenv("AUTO_ENDPOINT", "true").strip().lower() not in {"0", "false", "no", "off"}
    vad_engine: str = os.getenv("VAD_ENGINE", "auto")            # auto | silero | energy
    vad_threshold: float = float(os.getenv("VAD_THRESHOLD", "0.5"))
    end_silence_ms: int = int(os.getenv("END_SILENCE_MS", "900"))  # pause that ends a request
    no_speech_timeout_s: float = float(os.getenv("NO_SPEECH_TIMEOUT_S", "6"))
    wake_grace_ms: int = int(os.getenv("WAKE_GRACE_MS", "200"))    # ignore the tail of "Jarvis"
    wake_chime: bool = os.getenv("WAKE_CHIME", "true").strip().lower() not in {"0", "false", "no", "off"}

    # Stage 8: on-screen orb. auto | qt (transparent) | tk (simple) | off
    orb_style: str = os.getenv("ORB_STYLE", "auto")

    # Stage 9: the "do what I ask" agent. It only ever calls approved tools
    # (assistant/tools.py); it can never run free-form commands.
    enable_agent: bool = os.getenv("AGENT_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    agent_max_rounds: int = int(os.getenv("AGENT_MAX_ROUNDS", "4"))
    # After Jarvis asks you a question, keep listening for the answer (no wake word needed).
    follow_up_enabled: bool = os.getenv("FOLLOW_UP_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    follow_up_max_turns: int = int(os.getenv("FOLLOW_UP_MAX_TURNS", "3"))
    follow_up_wait_seconds: float = float(os.getenv("FOLLOW_UP_WAIT_SECONDS", "8"))
    # Extra folders (separated by ;) that file tools may use, besides
    # Desktop, Documents, Downloads, Pictures, Music and Videos.
    allowed_folders: tuple = tuple(
        p.strip() for p in os.getenv("ALLOWED_FOLDERS", "").split(";") if p.strip()
    )

    # Dangerous actions are OFF by default. Even when on, each one still asks
    # you to say "yes" first, and the question is written by the program, not by the AI.
    allow_power_actions: bool = os.getenv("ALLOW_POWER_ACTIONS", "false").strip().lower() in {"1", "true", "yes", "on"}
    allow_file_deletion: bool = os.getenv("ALLOW_FILE_DELETION", "false").strip().lower() in {"1", "true", "yes", "on"}
    allow_shutdown: bool = False  # kept for compatibility; use allow_power_actions


config = Config()
