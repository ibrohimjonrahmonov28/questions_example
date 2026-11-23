# ELPAT Simulator: Android app

This is the ELPAT exam as an installable Android app (APK) for Samsung and any Android 7+ phone. Inside is the same exam page as the claude.ai version (`../index.html`): the same questions, the 8 picture pairs, all four parts, the scoring and the design, wrapped with [Capacitor](https://capacitorjs.com).

## What the app adds

| Capability | How the app provides it |
|---|---|
| Examiner (Claude) | Calls the Claude API directly with **your own Anthropic API key** (`claude-opus-5-5`, server-side refusal fallbacks on). |
| Examiner, ATC and pilot voices | The phone's text-to-speech engine, with a different pitch per role. Radio noise comes from Web Audio, as before. |
| Speech-to-text, option 1 | **Phone speech recognition**: free and live, but no audio is kept, so there is no playback. |
| Speech-to-text, option 2 | **OpenAI Whisper** (optional key): real recording with RECORD → STOP → PLAYBACK → RE-RECORD → SAVE ANSWER, and every answer's audio is kept. |
| Report and recordings | Saved through Android's share sheet (Files, Drive, Telegram, …). |

You enter the keys once, in **⚙ Settings** on the start screen (the screen opens by itself on first launch). They are stored only on the phone and sent only to Anthropic and OpenAI. Uninstalling the app deletes them.

**Getting an Anthropic API key:** sign up at `console.anthropic.com`, add credit, then go to **API keys** → **Create key**. A full exam is roughly 60 short Claude calls. A claude.ai subscription does not include API credit.

## Install on the phone

1. Open the repository on GitHub → **Actions** → **ELPAT Android app** → the latest green run.
2. Under **Artifacts**, download **ELPAT-Simulator-apk**. It is a `.zip`; Samsung's *My Files* app can extract it.
3. Open `ELPAT-Simulator-1.0.N.apk`. If Android asks, allow *Install unknown apps* for your browser or file manager.
4. Launch **ELPAT Simulator**, enter your key in Settings, and allow the microphone when you press RECORD the first time.

All builds are signed with the same key (`android/app/elpat-debug.keystore`, a debug key meant for sideloading), so a newer APK installs over the old one and keeps your settings.

## Build it yourself

GitHub Actions builds the APK on every push that touches the exam or the app (`.github/workflows/elpat-android.yml`). To build locally you need Node 22, JDK 21 and the Android SDK:

```bash
cd elpat_simulator/android-app
npm ci
npm run apk        # build:web → cap sync → gradlew assembleDebug
# → android/app/build/outputs/apk/debug/app-debug.apk
```

`npm run build:web` assembles `www/` from the shared files:

- `../index.html`, wrapped in a document skeleton
- `src/app.js`, bundled with esbuild: the app layer that provides `window.claude.use(...)`, plus the Settings screen
- DOMPurify, bundled so the page works offline
- the 8 picture pairs from `../pics`

Any change to the exam page is picked up on the next build.

## Notes

- **Permissions:** the app asks for INTERNET and RECORD_AUDIO (plus MODIFY_AUDIO_SETTINGS for the WebView microphone). The plugins add the speech-recognition and text-to-speech service queries.
- **Phone recognition and recording:** the phone recognizer needs the microphone to itself, so the app uses MediaRecorder only in Whisper mode. Phone recognition restarts after each pause, so long answers are captured whole. Some phones play a short tone when it restarts.
- **Security:** a key on a phone is acceptable for personal use. Do not share an APK together with your phone's data. For many candidates, deploy `../standalone/` instead, where the key stays on your server.
