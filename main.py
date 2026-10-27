import argparse
import logging
import time

from ai.fallback import create_ai_client
from assistant.local_intents import build_registry
from assistant.agent import Agent, build_tool_registry
from assistant.confirm import parse_yes_no
from assistant.logging_setup import configure_logging
from assistant.router import AssistantRouter
from assistant.state import AssistantState, StateManager
from audio.microphone import (
    MicrophoneError,
    is_silent,
    is_too_short,
    record_until_enter,
)
from audio.speaker import Speaker
from audio.speech_recognition import create_recognizer
from commands.desktop_actions import set_screenshot_hooks
from config import config
from ui.orb import create_orb

logger = logging.getLogger(__name__)

REASON_MESSAGES = {
    "no_speech": "I didn't hear anything. Say 'Hey Jarvis' again when you're ready.",
    "too_short": "That was too short to be a request. Try again.",
}


def transcribe(recognizer, audio) -> str:
    started = time.monotonic()
    text = recognizer.transcribe(audio)
    print(f"(transcribed in {time.monotonic() - started:.1f}s)")
    if not text:
        print("Assistant: I didn't catch any words. Try again, a little closer to the microphone.")
    return text


def listen_with_enter(recognizer) -> str:
    """Old behaviour (AUTO_ENDPOINT=false): press Enter to stop recording."""
    print("Listening... speak, then press Enter.")
    try:
        audio = record_until_enter(
            device=config.audio_input_device,
            max_seconds=config.max_recording_seconds,
        )
    except MicrophoneError as error:
        print(f"Assistant: {error}")
        return ""
    if is_too_short(audio):
        print("Assistant: That was too short. Speak for a little longer and try again.")
        return ""
    if is_silent(audio):
        print("Assistant: I recorded silence. Check your microphone (run audio_check.py).")
        return ""
    return transcribe(recognizer, audio)


def listen_auto(recognizer, vad, orb, no_speech_timeout_s: float | None = None) -> str:
    """Record one request; start and stop are detected automatically."""
    import sounddevice as sd

    from audio.listener import ListenerError, record_utterance

    print("Listening... just speak.")
    try:
        capture = record_utterance(
            sd, vad,
            device=config.audio_input_device,
            end_silence_ms=config.end_silence_ms,
            no_speech_timeout_s=no_speech_timeout_s or config.no_speech_timeout_s,
            max_seconds=config.max_recording_seconds,
            on_level=orb.set_level,
        )
    except ListenerError as error:
        print(f"Assistant: {error}")
        return ""
    return handle_capture(capture, recognizer)


def handle_capture(capture, recognizer) -> str:
    if capture.audio.size == 0:
        print("Assistant: " + REASON_MESSAGES.get(capture.reason, "I didn't catch that."))
        return ""
    return transcribe(recognizer, capture.audio)


class InputMode:
    """Remembers whether the current request was spoken, so yes/no questions use the same way."""

    voice = False


def make_confirmer(recognizer, vad, orb, speaker, states):
    """Ask a yes/no question aloud (or in the console) and return True only for a clear yes."""

    def confirm(question: str) -> bool:
        for attempt in range(2):
            prompt = question if attempt == 0 else "Please answer yes or no."
            print(f"Assistant: {prompt} (yes/no)")
            if speaker.enabled:
                states.set(AssistantState.SPEAKING)
                speaker.speak(prompt)
            if InputMode.voice and recognizer is not None:
                states.set(AssistantState.RECORDING)
                answer = (listen_auto(recognizer, vad, orb, no_speech_timeout_s=config.follow_up_wait_seconds)
                          if vad is not None else listen_with_enter(recognizer))
                if answer:
                    print(f"You said: {answer}")
            else:
                try:
                    answer = input("You (yes/no): ").strip()
                except (EOFError, KeyboardInterrupt):
                    return False
            decision = parse_yes_no(answer)
            if decision is not None:
                states.set(AssistantState.PROCESSING)
                return decision
        states.set(AssistantState.PROCESSING)
        return False  # silence or unclear is always NO

    return confirm


def setup_agent(router, speaker, recognizer, vad, orb, states):
    """Give the router the Stage 9 agent. Returns a status line."""
    if not config.enable_agent:
        return "Agent is off (AGENT_ENABLED=false)."
    if not router.ai_active or not hasattr(router.ai_client, "chat"):
        return "Agent is off: it needs the AI connection (AI_API_KEY and AI_MODEL)."

    def notify(message: str) -> None:  # timers call this from a background thread
        print(f"\nAssistant: {message}")
        try:
            import winsound

            winsound.Beep(1000, 200)
        except Exception:
            pass
        speaker.speak(message)

    registry = build_tool_registry(config, notify)
    folders = ", ".join(registry_files_roots(config))
    router.agent = Agent(
        router.ai_client, registry, folders_text=folders,
        confirm=make_confirmer(recognizer, vad, orb, speaker, states),
        max_rounds=config.agent_max_rounds,
    )
    extras = []
    extras.append("file deletion ON" if config.allow_file_deletion else "file deletion off")
    extras.append("power actions ON" if config.allow_power_actions else "power actions off")
    return f"Agent is on: Jarvis can use {len(registry.names())} approved tools ({', '.join(extras)})."


def registry_files_roots(cfg) -> list[str]:
    from commands.files import FileTools

    return list(FileTools(cfg.allowed_folders).roots) or ["Documents"]


def build_router():
    ai_client, ai_status = create_ai_client(config)
    router = AssistantRouter(
        registry=build_registry(),
        ai_client=ai_client,
        enable_ai_fallback=config.enable_ai_fallback,
    )
    return router, ai_status


def respond(router, text, speaker, states):
    states.set(AssistantState.PROCESSING)
    reply = router.handle(text)
    print(f"Assistant: {reply}")
    if speaker.enabled:
        states.set(AssistantState.SPEAKING)
        speaker.speak(reply)


def converse(router, text, speaker, states, listen_again, max_turns: int) -> None:
    """Answer, and if Jarvis asked you a question keep listening for your reply.

    listen_again() returns your next spoken text, or "" if you said nothing,
    in which case Jarvis goes back to waiting. The agent remembers the earlier
    turns, so a short answer like "Johnson" is understood.
    """
    respond(router, text, speaker, states)
    turns = 0
    while router.wants_followup and turns < max_turns:
        turns += 1
        states.set(AssistantState.RECORDING)
        print("Listening for your answer...")
        answer = listen_again()
        if not answer:
            break
        print(f"You said: {answer}")
        respond(router, answer, speaker, states)


def make_follow_up_listener(recognizer, vad, orb):
    if not config.follow_up_enabled or recognizer is None or vad is None:
        return None
    return lambda: listen_auto(recognizer, vad, orb, no_speech_timeout_s=config.follow_up_wait_seconds)


def setup_auto_endpointing():
    """Returns (vad, description) or (None, reason) when it cannot be used."""
    try:
        from audio.listener import set_input_gain

        set_input_gain(config.mic_gain)
    except ImportError:
        pass
    if not config.auto_endpoint:
        return None, "Press Enter to stop recording (AUTO_ENDPOINT=false)."
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return None, "Automatic speech detection needs sounddevice."
    from audio.vad import create_vad

    vad, name = create_vad(config.vad_engine, config.vad_threshold)
    return vad, f"Automatic start/stop of speech is on ({name})."


def run_typed_mode(router, recognizer, ai_status, stt_status, speaker, states, orb, vad, vad_status):
    print("Jarvis is ready (typed + push-to-talk mode).")
    for line in (ai_status, stt_status, speaker.status, orb.status, vad_status):
        print(line)

    if recognizer is not None:
        print("Press Enter on an empty line to speak, or type a command. 'exit' quits.")
    else:
        print("Type a command or a question. 'exit' quits.")

    states.set(AssistantState.IDLE)
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if text.lower() in {"exit", "quit"}:
            break

        if not text and recognizer is not None:
            states.set(AssistantState.RECORDING)
            text = listen_auto(recognizer, vad, orb) if vad is not None else listen_with_enter(recognizer)
            if not text:
                states.set(AssistantState.IDLE)
                continue
            print(f"You said: {text}")
            InputMode.voice = True
        else:
            InputMode.voice = False

        listen_again = make_follow_up_listener(recognizer, vad, orb) if InputMode.voice else None
        converse(router, text, speaker, states, listen_again or (lambda: ""), config.follow_up_max_turns)
        states.set(AssistantState.IDLE)

    states.set(AssistantState.STOPPED)


def run_wake_mode(router, recognizer, ai_status, stt_status, speaker, states, orb, vad, vad_status):
    if recognizer is None:
        print("Wake-word mode needs speech recognition. " + stt_status)
        print("Use 'python main.py' for typed mode, or fix the STT installation first.")
        return

    from audio.wake_word import WakeWordDetector, WakeWordError

    try:
        detector = WakeWordDetector(
            device=config.audio_input_device,
            threshold=config.wake_word_threshold,
        )
    except (WakeWordError, ValueError) as error:
        print(f"Could not start wake-word mode: {error}")
        return

    print("Jarvis is ready (hands-free wake-word mode).")
    for line in (ai_status, stt_status, speaker.status, orb.status, vad_status):
        print(line)

    hands_free = None
    if vad is not None:
        import sounddevice as sd

        from audio.listener import HandsFreeListener

        hands_free = HandsFreeListener(
            wake_model=detector.model,
            vad=vad,
            sd=sd,
            device=config.audio_input_device,
            wake_threshold=config.wake_word_threshold,
            end_silence_ms=config.end_silence_ms,
            no_speech_timeout_s=config.no_speech_timeout_s,
            max_seconds=config.max_recording_seconds,
            wake_grace_ms=config.wake_grace_ms,
            chime=config.wake_chime,
            on_level=orb.set_level,
            on_wake=lambda: states.set(AssistantState.RECORDING),
        )
        print("Say 'Hey Jarvis', then speak your request. Jarvis stops listening when you pause.")
    else:
        print("Say 'Hey Jarvis', pause, speak, then press Enter.")
    print("Press Ctrl+C to stop.\n")

    from audio.listener import ListenerError

    follow_up = make_follow_up_listener(recognizer, vad, orb)
    while True:
        try:
            states.set(AssistantState.WAITING_FOR_WAKE_WORD)
            if hands_free is not None:
                capture = hands_free.listen()
                text = handle_capture(capture, recognizer)
            else:
                detector.wait()
                states.set(AssistantState.RECORDING)
                text = listen_with_enter(recognizer)
            if not text:
                continue
            print(f"You said: {text}")
            InputMode.voice = True
            converse(router, text, speaker, states, follow_up or (lambda: ""), config.follow_up_max_turns)
        except KeyboardInterrupt:
            print("\nJarvis stopped listening.")
            states.set(AssistantState.STOPPED)
            break
        except (WakeWordError, ListenerError) as error:
            print(f"Assistant: {error}")
            states.set(AssistantState.STOPPED)
            break


def run_diagnostics(ai_status, stt_status, speaker, log_path, orb_status, vad_status):
    """Report setup status without displaying secrets or contacting the AI provider."""
    print("Jarvis diagnostics")
    print(f"Python environment: {__import__('sys').executable}")
    print(f"AI fallback: {ai_status}")
    print(f"Speech recognition: {stt_status}")
    print(f"Speech start/stop: {vad_status}")
    print(f"Local text-to-speech: {speaker.status}")
    print(f"Agent: {'on (needs AI settings above)' if config.enable_agent else 'off'}; "
          f"file deletion {'ON' if config.allow_file_deletion else 'off'}; "
          f"power actions {'ON' if config.allow_power_actions else 'off'}")
    print(f"Orb: {orb_status}")
    print(f"Log file: {log_path}")
    print("Security: computer actions are limited to approved, registered actions.")
    print("Privacy: logs contain operational events, not transcripts, typed text or API keys.")


def main():
    log_path = configure_logging(config.log_level)
    logger.info("Jarvis starting")
    parser = argparse.ArgumentParser(description="Local-first Windows voice assistant")
    parser.add_argument("--wake", action="store_true",
                        help="listen for the local 'Hey Jarvis' wake phrase")
    parser.add_argument("--diagnostics", action="store_true",
                        help="show local setup status without starting the microphone")
    parser.add_argument("--no-overlay", action="store_true",
                        help="disable the floating desktop orb")
    parser.add_argument("--say-time", action="store_true",
                        help="speak the current time once, to test the voice")
    args = parser.parse_args()

    router, ai_status = build_router()
    recognizer, stt_status = create_recognizer(config)
    speaker = Speaker(enabled=config.tts_enabled, rate=config.tts_rate, volume=config.tts_volume)
    vad, vad_status = setup_auto_endpointing()

    if args.diagnostics:
        orb_note = "Run without --diagnostics to start the orb (style: %s)." % config.orb_style
        run_diagnostics(ai_status, stt_status, speaker, log_path, orb_note, vad_status)
        logger.info("Diagnostics completed")
        return

    if args.say_time:
        from commands.system import get_time

        message = get_time()
        print(f"Assistant: {message}")
        print(f"Voice: {speaker.status}")
        print("Spoke it." if speaker.speak(message) else "Could not speak it. Run: python main.py --diagnostics")
        speaker.close()
        return

    orb = create_orb("off" if args.no_overlay else config.orb_style)
    states = StateManager(on_state_change=orb.set_state)
    ai_status = ai_status + " " + setup_agent(router, speaker, recognizer, vad, orb, states)
    # Hide the orb for a moment so it is not in your screenshots.
    set_screenshot_hooks(before=lambda: orb.set_visible(False), after=lambda: orb.set_visible(True))

    try:
        if args.wake:
            run_wake_mode(router, recognizer, ai_status, stt_status, speaker, states, orb, vad, vad_status)
        else:
            run_typed_mode(router, recognizer, ai_status, stt_status, speaker, states, orb, vad, vad_status)
    finally:
        states.set(AssistantState.STOPPED)
        orb.close()
        speaker.close()
    logger.info("Jarvis stopped")


if __name__ == "__main__":
    main()
