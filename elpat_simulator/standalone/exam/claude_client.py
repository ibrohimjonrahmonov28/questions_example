"""Claude calls for the exam engine.

The browser never sees the API key: the page sends the prompt it built (the same prompts the
claude.ai version uses) and this module calls the Messages API on its behalf.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import anthropic
from django.conf import settings

log = logging.getLogger("elpat")

# The page asks for a "tier" per call; all tiers use the configured model, with effort scaled to the job:
# quick = short examiner replies, default = question/script generation and RT turns, complex = drawings and the final rating.
EFFORT = {"quick": "low", "default": "medium", "complex": "high"}
MAX_INPUT_BYTES = 262_144
MAX_TOKENS = 16_000

_client: anthropic.Anthropic | None = None


class ClaudeError(Exception):
    def __init__(self, code: str, status: int = 502, message: str = "") -> None:
        super().__init__(message or code)
        self.code, self.status, self.message = code, status, message


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=2, timeout=180.0)
    return _client


def configured() -> bool:
    if settings.ELPAT_FAKE_AI:
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def to_messages(raw: Any) -> list[dict[str, str]]:
    """Validate the page's input: a prompt string, or alternating user/assistant turns ending on a user turn."""
    if isinstance(raw, str) and raw.strip():
        messages = [{"role": "user", "content": raw}]
    elif isinstance(raw, list) and raw:
        messages = []
        for item in raw:
            if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
                raise ValueError("Each message needs role 'user' or 'assistant'.")
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Each message needs non-empty text content.")
            messages.append({"role": item["role"], "content": content})
        if messages[0]["role"] != "user" or messages[-1]["role"] != "user":
            raise ValueError("The conversation must start and end with a user turn.")
    else:
        raise ValueError("'input' must be a non-empty string or a list of messages.")
    if sum(len(m["content"].encode("utf-8")) for m in messages) > MAX_INPUT_BYTES:
        raise ValueError("The prompt is too large.")
    return messages


def complete(messages: list[dict[str, str]], tier: str) -> tuple[str, bool]:
    """Return (text, truncated)."""
    if settings.ELPAT_FAKE_AI:
        from .fake_ai import respond

        return respond(messages[-1]["content"]), False
    if not configured():
        raise ClaudeError("no_sample", 503, "The server has no Anthropic API key (set ANTHROPIC_API_KEY).")
    try:
        response = get_client().beta.messages.create(
            model=settings.ELPAT_MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT.get(tier, "medium")},
            # If a safety classifier declines, the API re-runs the request on a fallback model inside the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=messages,
        )
    except anthropic.RateLimitError as exc:
        log.warning("claude rate limited: %s", exc)
        raise ClaudeError("rate_limited", 429, "Claude is busy right now. Wait a moment and retry.") from exc
    except anthropic.AuthenticationError as exc:
        raise ClaudeError("no_sample", 503, "The server's Anthropic API key was rejected.") from exc
    except anthropic.BadRequestError as exc:
        log.error("claude bad request: %s", exc)
        raise ClaudeError("invalid_request", 400, "The request was rejected by the Claude API.") from exc
    except anthropic.APIStatusError as exc:
        log.error("claude api error %s", exc.status_code)
        raise ClaudeError("upstream_error", 502, f"Claude API error {exc.status_code}.") from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeError("upstream_error", 502, "Could not reach the Claude API.") from exc

    if response.stop_reason == "refusal":
        raise ClaudeError("refusal", 422, "The request was declined.")
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.stop_reason == "max_tokens"


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def parse_json(text: str) -> Any:
    """Parse a JSON answer that may be wrapped in a code fence or surrounded by a sentence."""
    stripped = text.strip()
    candidates = []
    fence = _FENCE.search(stripped)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(stripped)
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = stripped.find(open_ch), stripped.rfind(close_ch)
        if start != -1 and end > start:
            candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    raise ValueError("No JSON found in the model's answer.")
