"""AI client for ANSWERING questions. It never executes anything.

Works with any OpenAI-compatible chat endpoint: a cloud provider, or a
local server such as Ollama or LM Studio (set AI_BASE_URL). The router does
not care which one is used.
"""

SYSTEM_PROMPT = (
    "You are a helpful Windows voice assistant. "
    "Give concise, clear answers suitable for being spoken aloud: "
    "short sentences, no markdown, no lists, no code blocks unless asked. "
    "You can only answer questions. You cannot open programs, change files, "
    "or control the computer, so never claim to have performed an action."
)

MAX_REPLY_CHARS = 1200  # keeps spoken answers from running on (used again in Stage 5)


class AIClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 20.0,
    ):
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from error

        self.model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout,
        )

    def answer(self, user_text: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )

        text = (response.choices[0].message.content or "").strip()
        if not text:
            return "I couldn't generate a response."
        return text[:MAX_REPLY_CHARS]

    def chat(self, messages: list[dict]) -> str:
        """Send a full message list (used by the Stage 9 agent). Returns raw text.

        The caller is responsible for treating the reply as untrusted input.
        """
        # Agent prompts are longer than plain questions, so allow more time.
        response = self._client.with_options(timeout=45.0).chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return (response.choices[0].message.content or "").strip()
