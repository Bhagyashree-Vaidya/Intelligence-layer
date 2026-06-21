"""Claude API client — used for nuanced reasoning, writing, analysis.

Handles: resume rewriting, cover letters, hiring post analysis,
outreach messages, outcome analysis, skill gap reasoning.
"""

import json
from typing import Any

import anthropic

from app.config import get_settings
from app.logger import log

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        s = get_settings()
        if not s.claude_api:
            raise RuntimeError("CLAUDE_API key not set")
        _client = anthropic.AsyncAnthropic(api_key=s.claude_api)
    return _client


async def complete(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> str:
    """Raw text completion from Claude. (Old claude-sonnet-4-20250514 was retired
    -> 404; this is the current Sonnet.)"""
    client = _get_client()
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


async def complete_json(
    system: str,
    user: str,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Get structured JSON from Claude. Prompt must request JSON output.
    Haiku 4.5 — cheap + fast for high-volume classify/enrich/score."""
    text = await complete(
        system=system + "\n\nRespond with valid JSON only. No markdown, no explanation.",
        user=user,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.error(f"Claude returned invalid JSON: {text[:200]}")
        return {}


def is_available() -> bool:
    """Check if Claude API key is configured."""
    return bool(get_settings().claude_api)
