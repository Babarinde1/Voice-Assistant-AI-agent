"""Check that the AI connection works and the model can plan actions.

Run:  python agent_check.py
Nothing is executed on your PC. It only asks the AI what it WOULD do.
"""
from __future__ import annotations

import time

from ai.errors import describe_ai_error
from assistant.agent import Agent, build_tool_registry, extract_json, normalize_plan
from config import config


def main() -> None:
    if not config.ai_api_key or not config.ai_model:
        raise SystemExit("AI_API_KEY and AI_MODEL are not set in .env, so the agent cannot run.")
    from ai.client import AIClient

    client = AIClient(config.ai_api_key, config.ai_model, config.ai_base_url, config.ai_timeout_seconds)
    print(f"Model: {config.ai_model}   Base URL: {config.ai_base_url or '(provider default)'}\n")

    print("1) Simple question...")
    started = time.monotonic()
    try:
        reply = client.chat([{"role": "user", "content": "Reply with the single word: ready"}])
        print(f"   OK in {time.monotonic() - started:.1f}s: {reply[:60]!r}")
    except Exception as error:
        spoken, label = describe_ai_error(error)
        raise SystemExit(f"   FAILED: {label}\n   {spoken}")

    print("2) Planning a task (nothing is run)...")
    registry = build_tool_registry(config, notify=print)
    agent = Agent(client, registry)
    for request in ("find my CV and open it", "set a timer for two minutes", "what is the capital of Nigeria"):
        started = time.monotonic()
        try:
            raw = client.chat(agent._messages(request))
        except Exception as error:
            spoken, label = describe_ai_error(error)
            print(f"   '{request}' FAILED: {label}\n   {spoken}")
            continue
        plan = extract_json(raw)
        took = time.monotonic() - started
        if plan is None:
            print(f"   '{request}' ({took:.1f}s): model did NOT return JSON -> {raw[:100]!r}")
        else:
            actions, say = normalize_plan(plan)
            print(f"   '{request}' ({took:.1f}s): actions={[a['tool'] for a in actions]} say={say[:60]!r}")
    print("\nIf step 2 shows sensible tools (search_files, set_timer) the agent will work.")


if __name__ == "__main__":
    main()
