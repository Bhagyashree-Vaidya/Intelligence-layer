"""OpenAI API client — used for fast structured extraction and embeddings.

Handles: job enrichment, scoring, signal classification, embedding generation.
"""

import json
from typing import Any

import openai

from app.config import get_settings
from app.logger import log

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        s = get_settings()
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        _client = openai.AsyncOpenAI(api_key=s.openai_api_key)
    return _client


async def complete_json(
    system: str,
    user: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Get structured JSON from OpenAI using response_format."""
    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = response.choices[0].message.content or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.error(f"OpenAI returned invalid JSON: {text[:200]}")
        return {}


async def complete(
    system: str,
    user: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> str:
    """Raw text completion from OpenAI."""
    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


async def embed(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    client = _get_client()
    response = await client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


async def embed_one(text: str) -> list[float]:
    """Generate embedding for a single text."""
    result = await embed([text])
    return result[0]


def is_available() -> bool:
    """Check if OpenAI API key is configured."""
    return bool(get_settings().openai_api_key)
