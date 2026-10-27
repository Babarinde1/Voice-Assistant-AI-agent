from ai.client import AIClient


def create_ai_client(config) -> tuple[AIClient | None, str]:
    """Return (client, status_message).

    Returns (None, reason) when AI is off or not configured, so the
    assistant keeps working locally instead of crashing.
    """
    if not config.enable_ai_fallback:
        return None, "AI fallback is turned off in config.py."

    if not config.ai_api_key:
        return None, "AI fallback is off: AI_API_KEY is not set."

    if not config.ai_model:
        return None, "AI fallback is off: AI_MODEL is not set."

    try:
        client = AIClient(
            api_key=config.ai_api_key,
            model=config.ai_model,
            base_url=config.ai_base_url,
            timeout=config.ai_timeout_seconds,
        )
    except RuntimeError as error:
        return None, f"AI fallback is off: {error}"

    return client, f"AI fallback is on (model: {config.ai_model})."
