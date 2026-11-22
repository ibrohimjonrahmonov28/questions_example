"""HTTP endpoints: the exam page, its pictures, and the two server-side services (Claude, speech-to-text)."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.templatetags.static import static
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import claude_client, ratelimit, stt

log = logging.getLogger("elpat")

# The shared index.html is written for the claude.ai artifact, which wraps it in a document skeleton.
# The same wrapper is applied here, plus the shim that gives the page its server-backed capabilities.
PAGE_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0d0f">
<style>:root{{color-scheme:dark;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0;font:14px system-ui,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
<script src="{shim}"></script>
</head><body>
"""
PICTURE_NAME = re.compile(r"^v[1-8][ab]\.jpg$")


@lru_cache(maxsize=4)
def _read_frontend(path: str, mtime_ns: int) -> str:
    return Path(path).read_text(encoding="utf-8")


def _error(code: str, status: int, message: str = "") -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status)


@require_GET
@ensure_csrf_cookie
def index(request):
    path = settings.FRONTEND_DIR / "index.html"
    body = _read_frontend(str(path), path.stat().st_mtime_ns)
    response = HttpResponse(PAGE_HEAD.format(shim=static("elpat/standalone.js")) + body + "\n</body></html>", content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def picture(request, name: str):
    if not PICTURE_NAME.match(name):
        raise Http404
    path = settings.FRONTEND_DIR / "pics" / name
    if not path.is_file():
        raise Http404
    response = FileResponse(path.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def config(request):
    return JsonResponse({
        "claude": claude_client.configured(),
        "stt": stt.configured(),
        "stt_provider": settings.ELPAT_STT_PROVIDER or None,
        "max_audio_mb": settings.ELPAT_MAX_AUDIO_MB,
    })


@require_POST
def claude(request):
    if not ratelimit.allow("claude:" + ratelimit.client_ip(request), settings.ELPAT_RATE_CLAUDE):
        return _error("rate_limited", 429, "Too many requests. Wait a few minutes.")
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return _error("invalid_request", 400, "The body must be JSON.")
    if not isinstance(payload, dict):
        return _error("invalid_request", 400, "The body must be a JSON object.")
    try:
        messages = claude_client.to_messages(payload.get("input"))
    except ValueError as exc:
        return _error("invalid_request", 400, str(exc))
    tier = payload.get("tier") if payload.get("tier") in claude_client.EFFORT else "default"
    try:
        text, truncated = claude_client.complete(messages, tier)
    except claude_client.ClaudeError as exc:
        return _error(exc.code, exc.status, exc.message)
    if payload.get("json"):
        try:
            return JsonResponse({"value": claude_client.parse_json(text)})
        except ValueError:
            return _error("invalid_json", 502, "The examiner's answer was not valid JSON. Retry.")
    return JsonResponse({"text": text, "truncated": truncated})


@require_POST
def transcribe(request):
    if not ratelimit.allow("stt:" + ratelimit.client_ip(request), settings.ELPAT_RATE_STT):
        return _error("rate_limited", 429, "Too many requests. Wait a few minutes.")
    upload = request.FILES.get("audio")
    if upload is None:
        return _error("invalid_request", 400, "Send the recording as the 'audio' form field.")
    if upload.size > settings.ELPAT_MAX_AUDIO_MB * 1024 * 1024:
        return _error("too_large", 413, f"Recordings are limited to {settings.ELPAT_MAX_AUDIO_MB} MB.")
    if upload.size < 64:
        return _error("empty_audio", 400, "The recording is empty.")
    data = upload.read()
    mime = stt.sniff(data[:16])
    if mime is None:
        return _error("unsupported_media", 415, "Unsupported audio format. Use WebM/Opus, MP4/AAC or Ogg.")
    prompt = (request.POST.get("prompt") or "")[:800]
    try:
        result = stt.transcribe(data, mime, prompt)
    except stt.STTError as exc:
        return _error(exc.code, exc.status, exc.message)
    log.info("transcribed %s bytes (%s) via %s", len(data), mime, result.get("provider"))
    return JsonResponse(result)


@require_GET
def healthz(request):
    return JsonResponse({"ok": True})
