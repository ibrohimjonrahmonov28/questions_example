"""Server tests. Run from elpat_simulator/standalone:  DJANGO_DEBUG=1 python manage.py test exam"""
import json
from types import SimpleNamespace
from unittest import mock

import httpx
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings

from . import claude_client, stt

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 200          # EBML header: what Chrome / Samsung MediaRecorder produce
MP4 = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 200   # what Safari MediaRecorder produces


def fake_message(text, stop_reason="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)


@override_settings(SECURE_SSL_REDIRECT=False, ELPAT_FAKE_AI=False, ELPAT_STT_PROVIDER="fake", ELPAT_ACCESS_CODE="",
                   ELPAT_RATE_CLAUDE=100, ELPAT_RATE_STT=100)
class ServerTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    # ---------------------------------------------------------------- page
    def test_index_wraps_frontend_with_shim_and_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("elpat/standalone.js", html)
        self.assertIn("ELPAT Simulator", html)                 # the shared index.html
        self.assertIn('id="btn-record"', html)                 # recording controls are part of the page
        self.assertIn("csrftoken", response.cookies)
        self.assertIn("microphone=(self)", response["Permissions-Policy"])
        self.assertIn("media-src 'self' blob:", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_pictures_are_whitelisted(self):
        self.assertEqual(self.client.get("/pics/v5a.jpg").status_code, 200)
        self.assertEqual(self.client.get("/pics/v9a.jpg").status_code, 404)
        self.assertEqual(self.client.get("/pics/..%2Findex.html").status_code, 404)

    def test_config_reports_capabilities(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            body = self.client.get("/api/config").json()
        self.assertEqual(body["claude"], True)
        self.assertEqual(body["stt"], True)
        self.assertEqual(body["stt_provider"], "fake")

    # ---------------------------------------------------------------- Claude proxy
    def _claude(self, payload, client=None):
        return (client or self.client).post("/api/claude", data=json.dumps(payload), content_type="application/json")

    @mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    def test_claude_text_call_uses_model_effort_and_fallbacks(self):
        create = mock.Mock(return_value=fake_message("Hello candidate"))
        with mock.patch.object(claude_client, "get_client", return_value=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))):
            response = self._claude({"input": "Say hello", "tier": "complex"})
        self.assertEqual(response.json(), {"text": "Hello candidate", "truncated": False})
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["output_config"], {"effort": "high"})
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertEqual(kwargs["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "Say hello"}])

    @mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    def test_claude_json_mode_parses_fenced_json(self):
        create = mock.Mock(return_value=fake_message('Here you are:\n```json\n{"questions": ["Q1?"]}\n```'))
        with mock.patch.object(claude_client, "get_client", return_value=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))):
            response = self._claude({"input": [{"role": "user", "content": "x"}], "tier": "quick", "json": True})
        self.assertEqual(response.json(), {"value": {"questions": ["Q1?"]}})
        self.assertEqual(create.call_args.kwargs["output_config"], {"effort": "low"})

    @mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    def test_claude_invalid_json_and_refusal(self):
        for message, code, status in [(fake_message("not json"), "invalid_json", 502), (fake_message("", "refusal"), "refusal", 422)]:
            with mock.patch.object(claude_client, "get_client", return_value=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=mock.Mock(return_value=message))))):
                response = self._claude({"input": "x", "json": True})
            self.assertEqual((response.status_code, response.json()["code"]), (status, code))

    def test_claude_input_validation(self):
        for bad in [{}, {"input": ""}, {"input": [{"role": "system", "content": "x"}]}, {"input": [{"role": "assistant", "content": "x"}]}]:
            self.assertEqual(self._claude(bad).status_code, 400, bad)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_claude_without_key_is_reported(self):
        response = self._claude({"input": "x"})
        self.assertEqual((response.status_code, response.json()["code"]), (503, "no_sample"))

    def test_csrf_is_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(self._claude({"input": "x"}, client=strict).status_code, 403)
        strict.get("/")
        token = strict.cookies["csrftoken"].value
        response = strict.post("/api/transcribe", {"audio": SimpleUploadedFile("a.webm", WEBM, "audio/webm")}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)

    # ---------------------------------------------------------------- speech-to-text
    def test_transcribe_accepts_webm_and_mp4(self):
        for data, mime in [(WEBM, "audio/webm"), (MP4, "audio/mp4")]:
            response = self.client.post("/api/transcribe", {"audio": SimpleUploadedFile("a", data, "application/octet-stream"), "prompt": "Q"})
            self.assertEqual(response.status_code, 200)
            self.assertIn(mime, response.json()["text"])

    def test_transcribe_rejects_bad_uploads(self):
        self.assertEqual(self.client.post("/api/transcribe", {}).status_code, 400)
        self.assertEqual(self.client.post("/api/transcribe", {"audio": SimpleUploadedFile("a.webm", b"<html>" * 50, "audio/webm")}).status_code, 415)
        with override_settings(ELPAT_MAX_AUDIO_MB=0):
            self.assertEqual(self.client.post("/api/transcribe", {"audio": SimpleUploadedFile("a.webm", WEBM, "audio/webm")}).status_code, 413)

    @override_settings(ELPAT_STT_PROVIDER="")
    def test_transcribe_unconfigured(self):
        response = self.client.post("/api/transcribe", {"audio": SimpleUploadedFile("a.webm", WEBM, "audio/webm")})
        self.assertEqual((response.status_code, response.json()["code"]), (503, "stt_unavailable"))

    @override_settings(ELPAT_STT_PROVIDER="openai", OPENAI_API_KEY="sk-o", OPENAI_STT_MODEL="whisper-1")
    def test_openai_provider_request(self):
        reply = httpx.Response(200, json={"text": " Tower, ready for departure ", "duration": 2.5}, request=httpx.Request("POST", "https://x"))
        with mock.patch("exam.stt.httpx.post", return_value=reply) as post:
            body = stt.transcribe(WEBM, "audio/webm", "aviation")
        self.assertEqual(body["text"], "Tower, ready for departure")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.openai.com/v1/audio/transcriptions")
        self.assertEqual(kwargs["data"]["response_format"], "verbose_json")
        self.assertEqual(kwargs["files"]["file"][0], "answer.webm")

    @override_settings(ELPAT_STT_PROVIDER="deepgram", DEEPGRAM_API_KEY="dg", DEEPGRAM_MODEL="nova-3")
    def test_deepgram_provider_request_and_errors(self):
        ok = httpx.Response(200, json={"results": {"channels": [{"alternatives": [{"transcript": "Mayday Mayday"}]}]}, "metadata": {"duration": 3}}, request=httpx.Request("POST", "https://x"))
        with mock.patch("exam.stt.httpx.post", return_value=ok) as post:
            self.assertEqual(stt.transcribe(MP4, "audio/mp4")["text"], "Mayday Mayday")
        self.assertEqual(post.call_args.kwargs["headers"]["Content-Type"], "audio/mp4")
        denied = httpx.Response(401, json={}, request=httpx.Request("POST", "https://x"))
        with mock.patch("exam.stt.httpx.post", return_value=denied), self.assertRaises(stt.STTError) as ctx:
            stt.transcribe(MP4, "audio/mp4")
        self.assertEqual(ctx.exception.code, "stt_unavailable")

    # ---------------------------------------------------------------- limits and access
    @override_settings(ELPAT_RATE_STT=2)
    def test_rate_limit(self):
        codes = [self.client.post("/api/transcribe", {"audio": SimpleUploadedFile("a.webm", WEBM, "audio/webm")}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    @override_settings(ELPAT_ACCESS_CODE="pilot2026")
    def test_access_code_gate(self):
        self.assertRedirects(self.client.get("/"), "/access", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/api/config").status_code, 401)
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertContains(self.client.post("/access", {"code": "wrong"}), "not correct")
        self.assertRedirects(self.client.post("/access", {"code": "pilot2026"}), "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/api/config").status_code, 200)
