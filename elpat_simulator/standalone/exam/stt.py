"""Speech-to-text for recorded answers.

Providers (ELPAT_STT_PROVIDER):
  openai    OpenAI audio transcriptions (whisper-1 by default; OPENAI_API_KEY)
  deepgram  Deepgram pre-recorded API (nova-3 by default; DEEPGRAM_API_KEY)
  fake      fixed text, for tests and demos
Both real providers accept the WebM/Opus (Chrome, Samsung) and MP4/AAC (Safari) files MediaRecorder produces.
"""
from __future__ import annotations

import httpx
from django.conf import settings

EXTENSION = {"audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/aac": "aac"}
# Terms that general speech models often mis-hear in aviation English.
KEYTERMS = ["Mayday", "Pan-Pan", "wilco", "roger", "affirm", "readback", "QNH", "squawk", "helideck", "helipad", "H215", "niner"]


class STTError(Exception):
    def __init__(self, code: str, status: int = 502, message: str = "") -> None:
        super().__init__(message or code)
        self.code, self.status, self.message = code, status, message


def sniff(head: bytes) -> str | None:
    """Identify the container from its first bytes; never trust the client's Content-Type."""
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"  # EBML header (WebM / Matroska)
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xF6) == 0xF0:
        return "audio/aac"  # ADTS frame header
    return None


def configured() -> bool:
    provider = settings.ELPAT_STT_PROVIDER
    return (
        provider == "fake"
        or (provider == "openai" and bool(settings.OPENAI_API_KEY))
        or (provider == "deepgram" and bool(settings.DEEPGRAM_API_KEY))
    )


def transcribe(data: bytes, mime: str, prompt: str = "") -> dict:
    if not configured():
        raise STTError("stt_unavailable", 503, "Speech-to-text is not configured on the server.")
    provider = settings.ELPAT_STT_PROVIDER
    if provider == "fake":
        text = settings.ELPAT_FAKE_TRANSCRIPT or f"Test transcript of {len(data)} bytes of {mime}."
        return {"text": text, "provider": "fake"}
    try:
        return _openai(data, mime, prompt) if provider == "openai" else _deepgram(data, mime)
    except httpx.TimeoutException as exc:
        raise STTError("upstream_error", 504, "Speech-to-text timed out.") from exc
    except httpx.HTTPError as exc:
        raise STTError("upstream_error", 502, "Could not reach the speech-to-text service.") from exc


def _openai(data: bytes, mime: str, prompt: str) -> dict:
    model = settings.OPENAI_STT_MODEL
    form = {"model": model, "language": "en", "response_format": "verbose_json" if model.startswith("whisper") else "json"}
    if prompt:
        form["prompt"] = prompt[:800]
    response = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        data=form,
        files={"file": (f"answer.{EXTENSION.get(mime, 'webm')}", data, mime)},
        timeout=120.0,
    )
    _raise_for_status(response)
    body = response.json()
    return {"text": (body.get("text") or "").strip(), "duration": body.get("duration"), "provider": "openai"}


def _deepgram(data: bytes, mime: str) -> dict:
    params = [("model", settings.DEEPGRAM_MODEL), ("language", "en"), ("smart_format", "true"), ("punctuate", "true")]
    params += [("keyterm", term) for term in KEYTERMS]
    response = httpx.post(
        "https://api.deepgram.com/v1/listen",
        params=params,
        headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}", "Content-Type": mime},
        content=data,
        timeout=120.0,
    )
    _raise_for_status(response)
    body = response.json()
    alternative = body["results"]["channels"][0]["alternatives"][0]
    return {"text": (alternative.get("transcript") or "").strip(), "duration": body.get("metadata", {}).get("duration"), "provider": "deepgram"}


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise STTError("rate_limited", 429, "Speech-to-text is busy. Try again shortly.")
    if response.status_code in (401, 403):
        raise STTError("stt_unavailable", 503, "The speech-to-text API key was rejected.")
    if response.status_code >= 400:
        raise STTError("upstream_error", 502, f"Speech-to-text error {response.status_code}.")
