# ELPAT Simulator: standalone HTTPS app

This is the same exam page as the claude.ai artifact (`../index.html`, with the same questions, pictures, parts, scoring and design), served by a small Django server. It exists because **Claude artifacts block direct microphone recording**: the artifact runs inside a frame without microphone permission, so `getUserMedia`/MediaRecorder are refused there. On a normal HTTPS site the browser asks the candidate for permission and records real audio.

| | claude.ai artifact | This app |
|---|---|---|
| Recording (getUserMedia + MediaRecorder) | Blocked by the frame. The page detects this and says so. | Yes: WebM/Opus on Chrome and Samsung, MP4/AAC on Safari |
| PLAYBACK / RE-RECORD before SAVE ANSWER | RE-RECORD only (no audio file) | Yes |
| Recordings kept per question | – | Yes, in the browser (IndexedDB). Play or download them on the results page. |
| Speech-to-text | Claude dictation (live) | Server: OpenAI Whisper or Deepgram |
| Examiner | Claude on the viewer's account | Claude API with your key (`claude-opus-5-5`) |
| Who can use it | People with a Claude account you share it with | Anyone with the URL (optionally gated by an access code) |

## What the server does

```
browser (exam page + MediaRecorder) ──HTTPS──► Django
   GET  /                 the exam page (../index.html) + shim (exam/static/elpat/standalone.js)
   GET  /pics/v1a.jpg …   the 8 built-in picture pairs
   GET  /api/config       which services are configured
   POST /api/claude       the page's prompt → Claude Messages API (key stays on the server)
   POST /api/transcribe   one recorded answer → speech-to-text → text
```

- **Stateless:** there is no database. Recordings stay in the candidate's browser and are only uploaded to be transcribed; the server does not store them.
- **Security:** the API key lives only in the server environment. CSRF protection is on every POST. Uploads are checked by their file signature (WebM, MP4, Ogg or AAC only) and size. Requests are rate-limited per IP. Responses carry a CSP, `Permissions-Policy: microphone=(self)` and `X-Frame-Options: DENY`. Cookies are Secure, and HSTS plus an HTTPS redirect are on outside debug mode. An optional access code (`ELPAT_ACCESS_CODE`) keeps strangers from spending your credit.
- **Claude:** `claude-opus-5-5` on every call. The page's tier sets the effort: `quick` → low, `default` → medium, `complex` → high. Server-side refusal fallbacks are enabled (`fallbacks="default"`).

## Run locally

```bash
cd elpat_simulator/standalone
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=1 ANTHROPIC_API_KEY=sk-ant-... ELPAT_STT_PROVIDER=openai OPENAI_API_KEY=sk-...
python manage.py runserver 0.0.0.0:8000
```

Open `http://localhost:8000` on the same computer: `localhost` counts as a secure context, so the microphone works without HTTPS.

**On an Android phone (Samsung, Chrome)** the page must be served over HTTPS. Use one of these:

- **USB:** run `adb reverse tcp:8000 tcp:8000`, then open `http://localhost:8000` in Chrome on the phone (still `localhost`, so it is a secure context).
- **Quick public HTTPS tunnel:** run `cloudflared tunnel --url http://localhost:8000` and open the `https://….trycloudflare.com` URL it prints. Add that host to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- **Deploy** (below). This is the real option for "everyone can use it".

To try it with no API keys, set `ELPAT_FAKE_AI=1 ELPAT_STT_PROVIDER=fake`. The examiner then gives canned questions and the transcript is a fixed sentence, but recording and playback are real. This mode is for testing only.

## Deploy (HTTPS)

Any container host that provides HTTPS works: Render, Railway, Fly.io, Google Cloud Run, or a VPS behind Caddy or nginx.

```bash
cd elpat_simulator
docker build -f standalone/Dockerfile -t elpat .
docker run -p 8000:8000 --env-file standalone/.env elpat
```

Set these environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Long random string (required) |
| `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` | Your domain, e.g. `elpat.example.com` / `https://elpat.example.com` |
| `ANTHROPIC_API_KEY` | Claude examiner and rating |
| `ELPAT_STT_PROVIDER` + `OPENAI_API_KEY` or `DEEPGRAM_API_KEY` | Transcription of recorded answers |
| `ELPAT_ACCESS_CODE` | Optional shared code for candidates |
| `REDIS_URL` | Optional: shared rate limits when you run more than one instance |

Gunicorn runs 2 workers × 8 threads with a 180 s timeout, because the final rating call can take up to about 2 minutes. Add workers or instances as traffic grows: the app keeps no state, so it scales horizontally.

**Cost per full exam** (rough estimate): about 60 Claude calls, most of them short. On top of that, around 15 minutes of audio transcription (Whisper is about $0.006 per minute).

## Browser support

| Browser | Recording format | Notes |
|---|---|---|
| Chrome on Android (Samsung, Pixel, …) | `audio/webm;codecs=opus` | Recommended |
| Samsung Internet | `audio/webm;codecs=opus` | Works |
| Chrome / Edge / Firefox desktop | WebM/Opus or Ogg/Opus | Works |
| Safari iOS / macOS | `audio/mp4` (AAC) | Works. The examiner voice is the system voice. |

The page releases the microphone after every answer. This matters on Android, where an open microphone switches audio to call mode and makes the examiner quieter. The start screen's **Microphone diagnostics** panel shows:

- whether the page is in a secure context
- whether MediaRecorder exists, and which format it uses
- whether the hosting frame blocks the microphone
- the permission state
- whether speech-to-text is available

The page also explains the common errors in plain words: permission denied (with Chrome and Samsung settings paths), no microphone found, microphone in use by another app, and an insecure page.

## Tests

```bash
DJANGO_DEBUG=1 python manage.py test exam
```

The tests cover the following, with Claude and the speech-to-text providers mocked:

- the page wrapper and security headers
- the picture whitelist
- the Claude proxy: model, effort, fallbacks, JSON parsing, refusal and input validation
- CSRF
- uploads: file signature sniffing, size limit, missing configuration
- the OpenAI and Deepgram request shapes
- rate limiting and the access-code gate

Browser recording was tested end to end with Chromium's fake microphone. The test pressed RECORD, STOP, PLAYBACK, RE-RECORD and SAVE ANSWER, then checked that the WebM/Opus files were saved in IndexedDB and played back on the results page, across all four parts.
