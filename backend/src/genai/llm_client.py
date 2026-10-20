"""OpenRouter LLM client, shared by POST /forecast/explain and POST /chat.

OpenRouter exposes an OpenAI-compatible API at https://openrouter.ai/api/v1,
so we use the standard `openai.OpenAI` client with a custom base_url.

Reads credentials from environment variables (loaded from .env locally via
python-dotenv) -- never hardcode a key here. See .env.example for the
required variable names.
"""

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

# This file lives at backend/src/genai/llm_client.py -- .env is 3 levels up.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

_client = None


class LLMConfigError(RuntimeError):
    """Raised when required LLM environment variables are missing."""


def get_client() -> OpenAI:
    """Return a cached OpenAI client pointed at OpenRouter, or raise LLMConfigError."""

    global _client

    if _client is None:
        if not OPENROUTER_API_KEY:
            raise LLMConfigError("Missing OPENROUTER_API_KEY environment variable.")

        _client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

    return _client


def call_chat_json(system_prompt: str, user_message: str) -> str:
    """Call the configured model in JSON mode via OpenRouter.

    Returns the raw response content (a JSON string).
    Raises LLMConfigError if credentials are missing; propagates the
    underlying openai SDK's exceptions on network/API failures.
    """

    client = get_client()

    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    return response.choices[0].message.content


def call_chat(
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    json_mode: bool = False,
) -> ChatCompletionMessage:
    """General-purpose chat completion call via OpenRouter, optionally with
    tool definitions and/or JSON-mode output. Used by the /chat tool-calling
    flow where the caller needs the raw assistant message to inspect
    .tool_calls.

    Raises LLMConfigError if credentials are missing; propagates the
    underlying openai SDK's exceptions on network/API failures.
    """

    client = get_client()

    kwargs: dict[str, Any] = {"model": OPENROUTER_MODEL, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quick manual test for the OpenRouter client.")
    parser.add_argument("--name", default="World", help="Name to greet in the test prompt")
    args = parser.parse_args()

    reply = call_chat_json(
        'You are a helpful assistant. Respond with JSON in this exact shape: {"message": "..."}.',
        f"Say hello to {args.name} in one short sentence.",
    )
    print(reply)
