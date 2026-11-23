// ELPAT Simulator — Android app layer.
//
// The exam page (../../index.html) talks to its environment only through window.claude.use(name). On claude.ai the
// platform provides those capabilities; in this app this file does, on the phone itself:
//   sample     → Claude Messages API with the candidate's own Anthropic key (kept on the phone only)
//   stt        → OpenAI Whisper for recorded answers (optional key) — enables RECORD with PLAYBACK
//   dictation  → the phone's speech recognition (free, text only) when no Whisper key is set
//   tts        → the phone's text-to-speech engine for the examiner, ATC and pilot voices
//   downloads  → write the file to the app cache and open Android's share sheet
// It also adds a Settings screen for the keys.
import Anthropic from "@anthropic-ai/sdk";
import { Capacitor } from "@capacitor/core";
import { TextToSpeech } from "@capacitor-community/text-to-speech";
import { SpeechRecognition } from "@capacitor-community/speech-recognition";
import { Filesystem, Directory } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";

const NATIVE = Capacitor.isNativePlatform();
const SETTINGS_KEY = "elpat-app-settings";
const MODEL = "claude-opus-5-5";
const EFFORT = { quick: "low", default: "medium", complex: "high" };

function loadSettings() {
  try { return Object.assign({ anthropicKey: "", stt: "phone", openaiKey: "" }, JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}")); }
  catch { return { anthropicKey: "", stt: "phone", openaiKey: "" }; }
}
const settings = loadSettings();
const whisper = settings.stt === "openai" && !!settings.openaiKey;

// Read synchronously by index.html before its own script runs.
window.ELPAT_STANDALONE = true;
window.ELPAT_APP = true;
// The phone's recognizer needs the microphone to itself, so MediaRecorder is used only together with Whisper.
window.ELPAT_DISABLE_RECORDER = NATIVE && !whisper;

// ------------------------------------------------------------------ Claude
let client = null;
function anthropic() {
  if (!settings.anthropicKey) throw { code: "no_key", message: "No Anthropic API key." };
  if (!client) client = new Anthropic({ apiKey: settings.anthropicKey, dangerouslyAllowBrowser: true, maxRetries: 2, timeout: 180000 });
  return client;
}
function toMessages(input) {
  if (typeof input === "string") return [{ role: "user", content: input }];
  return input.map((m) => ({ role: m.role, content: m.content }));
}
async function complete(input, tier) {
  let message;
  try {
    message = await anthropic().beta.messages.create({
      model: MODEL,
      max_tokens: 16000,
      output_config: { effort: EFFORT[tier] || "medium" },
      // If a safety classifier declines, the API re-runs the request on a fallback model inside the same call.
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      messages: toMessages(input),
    });
  } catch (e) {
    if (e && e.code && !e.status) throw e;
    if (e instanceof Anthropic.AuthenticationError || e instanceof Anthropic.PermissionDeniedError) throw { code: "bad_key", message: "The Anthropic API key was rejected." };
    if (e instanceof Anthropic.RateLimitError) throw { code: "rate_limited", message: "Claude is busy or your usage limit was reached." };
    if (e instanceof Anthropic.APIConnectionError) throw { code: "upstream_error", message: "No connection to Claude. Check the internet connection." };
    if (e instanceof Anthropic.APIError) throw { code: "upstream_error", message: "Claude API error " + (e.status || "") };
    throw { code: "upstream_error", message: String((e && e.message) || e) };
  }
  if (message.stop_reason === "refusal") throw { code: "refusal", message: "The request was declined." };
  return { text: message.content.filter((b) => b.type === "text").map((b) => b.text).join(""), truncated: message.stop_reason === "max_tokens" };
}
function parseJson(text) {
  const t = String(text).trim(), candidates = [];
  const fence = /```(?:json)?\s*([\s\S]*?)```/i.exec(t);
  if (fence) candidates.push(fence[1]);
  candidates.push(t);
  for (const [a, b] of [["{", "}"], ["[", "]"]]) { const i = t.indexOf(a), j = t.lastIndexOf(b); if (i !== -1 && j > i) candidates.push(t.slice(i, j + 1)); }
  for (const c of candidates) { try { return JSON.parse(c); } catch {} }
  throw { code: "invalid_json", message: "The examiner's answer was not valid JSON." };
}
const sample = Object.assign(
  async (input, options = {}) => {
    const out = await complete(input, options.modelTier);
    if (typeof options.onText === "function") { try { options.onText({ text: out.text, delta: out.text }); } catch {} }
    return out;
  },
  { json: async (input, options = {}) => parseJson((await complete(input, options.modelTier)).text), limits: async () => ({ maxPromptBytes: 262144 }) },
);

// ------------------------------------------------------------------ Whisper (recorded answers)
const stt = {
  transcribe: async (blob, options = {}) => {
    const type = (blob.type || "audio/webm").split(";")[0];
    const ext = /mp4|aac/.test(type) ? "m4a" : /ogg/.test(type) ? "ogg" : "webm";
    const form = new FormData();
    form.append("file", blob, "answer." + ext);
    form.append("model", "whisper-1");
    form.append("language", "en");
    form.append("response_format", "json");
    if (options.prompt) form.append("prompt", options.prompt.slice(0, 800));
    let response;
    try { response = await fetch("https://api.openai.com/v1/audio/transcriptions", { method: "POST", headers: { Authorization: "Bearer " + settings.openaiKey }, body: form }); }
    catch { throw { code: "upstream_error", message: "No connection to the speech-to-text service." }; }
    if (response.status === 401 || response.status === 403) throw { code: "stt_unavailable", message: "The OpenAI key was rejected. Check Settings." };
    if (response.status === 429) throw { code: "rate_limited", message: "Speech-to-text is busy or the quota is used up." };
    if (!response.ok) throw { code: "upstream_error", message: "Speech-to-text error " + response.status };
    const body = await response.json();
    return { text: String(body.text || "").trim(), provider: "openai" };
  },
};

// ------------------------------------------------------------------ phone speech recognition (Claude-dictation-shaped)
// Android's recognizer ends each utterance after a pause; while an answer is being recorded it is restarted, and each
// finished utterance is delivered as a final phrase, so a 2-minute answer comes through whole.
const dictation = (() => {
  const partialCbs = [], finalCbs = [], stateCbs = [];
  let active = false, lastPartial = "", restartT = null, listening = false, wired = false;
  const emitState = (state, reason) => { listening = state === "listening"; stateCbs.forEach((f) => { try { f(reason ? { state, reason } : { state }); } catch {} }); };
  const commit = () => {
    if (!lastPartial) return;
    const text = " " + lastPartial; lastPartial = "";
    partialCbs.forEach((f) => f({ text: "" }));
    finalCbs.forEach((f) => f({ text }));
  };
  async function wire() {
    if (wired) return; wired = true;
    await SpeechRecognition.addListener("partialResults", (d) => { const t = (d && d.matches && d.matches[0]) || ""; if (!t) return; lastPartial = t; partialCbs.forEach((f) => f({ text: t })); });
    await SpeechRecognition.addListener("listeningState", (d) => {
      if (d.status === "started") { if (active) emitState("listening"); return; }
      commit();
      if (active) { clearTimeout(restartT); restartT = setTimeout(engine, 120); }
    });
  }
  async function engine() {
    if (!active) return;
    try { await SpeechRecognition.start({ language: "en-US", partialResults: true, popup: false, maxResults: 1 }); if (active && !listening) emitState("listening"); }
    catch { if (active) { clearTimeout(restartT); restartT = setTimeout(engine, 400); } }
  }
  return {
    start: async () => {
      const ok = await SpeechRecognition.available().then((r) => r.available, () => false);
      if (!ok) throw { code: "unavailable", message: "Speech recognition is not available on this phone." };
      const perm = await SpeechRecognition.requestPermissions();
      if (perm.speechRecognition !== "granted") throw { code: "not_granted", message: "Microphone permission was not granted." };
      await wire();
      active = true; emitState("starting");
      await engine();
    },
    stop: async () => {
      active = false; clearTimeout(restartT);
      try { await SpeechRecognition.stop(); } catch {}
      await new Promise((r) => setTimeout(r, 300)); // last partial result
      commit(); emitState("idle", "stopped");
    },
    active: () => active,
    onPartial: (f) => { partialCbs.push(f); return () => partialCbs.splice(partialCbs.indexOf(f), 1); },
    onFinal: (f) => { finalCbs.push(f); return () => finalCbs.splice(finalCbs.indexOf(f), 1); },
    onState: (f) => { stateCbs.push(f); return () => stateCbs.splice(stateCbs.indexOf(f), 1); },
  };
})();

// ------------------------------------------------------------------ phone text-to-speech (Claude-tts-shaped)
// Different pitch per role, so examiner, controller and pilots sound distinct.
const PITCH = { rounded: 1.0, glassy: 0.86, airy: 1.16, buttery: 0.95 };
const tts = (() => {
  let lineCb = null, gen = 0;
  return {
    onLine: (f) => { lineCb = f; return () => { lineCb = null; }; },
    speak: async (what, opts = {}) => {
      const mine = ++gen;
      const lines = typeof what === "string" ? [{ text: what }] : what;
      try { await TextToSpeech.stop(); } catch {}
      for (let i = 0; i < lines.length; i++) {
        if (mine !== gen) throw { code: "stopped" };
        const l = lines[i];
        if (lineCb) { try { lineCb({ line: i, id: l.id }); } catch {} }
        await TextToSpeech.speak({ text: l.text, lang: "en-US", rate: opts.rate || 1, pitch: PITCH[l.voice || opts.voice] || 1, volume: 1, category: "playback" });
      }
      if (mine !== gen) throw { code: "stopped" };
      return { playedMs: 0 };
    },
    stop: async () => { gen++; try { await TextToSpeech.stop(); } catch {} },
  };
})();

// ------------------------------------------------------------------ files: report and recordings → share sheet
const toBase64 = (blob) => new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(String(r.result).split(",")[1] || ""); r.onerror = () => reject(r.error); r.readAsDataURL(blob); });
const downloads = {
  save: async ({ filename, data }) => {
    const blob = data instanceof Blob ? data : new Blob([data], { type: "text/markdown;charset=utf-8" });
    if (!NATIVE) {
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
      return;
    }
    const written = await Filesystem.writeFile({ path: filename, data: await toBase64(blob), directory: Directory.Cache });
    await Share.share({ title: filename, files: [written.uri], dialogTitle: "Save or share " + filename });
  },
};

// ------------------------------------------------------------------ capabilities for index.html
const caps = { downloads };
if (settings.anthropicKey) caps.sample = sample;
if (whisper) caps.stt = stt;
if (NATIVE) { caps.tts = tts; if (!whisper) caps.dictation = dictation; }
window.claude = { use: async (name) => caps[name] || null };

// ------------------------------------------------------------------ Settings screen
const CSS = `
.app-settings-btn{position:fixed;right:max(12px,env(safe-area-inset-right,0px));bottom:calc(12px + env(safe-area-inset-bottom,0px));z-index:20;border:1px solid #2c3d4c;background:#15212b;color:#dbe4ec;border-radius:22px;padding:10px 14px;font:700 13px "B612 Mono",monospace;letter-spacing:.08em}
.app-sheet{position:fixed;inset:0;z-index:30;background:#090e13;color:#dbe4ec;overflow-y:auto;padding:calc(16px + env(safe-area-inset-top,0px)) max(16px,env(safe-area-inset-right,0px)) calc(24px + env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px));font:15px/1.5 "B612",system-ui,sans-serif}
.app-sheet .card{max-width:560px;margin:0 auto;display:grid;gap:14px;background:#0f1820;border:1px solid #243341;border-radius:10px;padding:18px}
.app-sheet h2{margin:0;font:700 28px "Barlow Condensed",sans-serif;letter-spacing:.03em}
.app-sheet label{display:grid;gap:6px;font:11px "B612 Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#8494a3}
.app-sheet input,.app-sheet select{border:1px solid #243341;background:#090e13;color:#dbe4ec;border-radius:6px;padding:11px 12px;font:15px "B612 Mono",monospace;width:100%;box-sizing:border-box;text-transform:none;letter-spacing:0}
.app-sheet p{margin:0;color:#8494a3;font-size:13px}
.app-sheet .row{display:flex;gap:8px;flex-wrap:wrap}
.app-sheet button{border:0;border-radius:6px;padding:12px 16px;font:700 15px system-ui,sans-serif}
.app-sheet .primary{background:#45cde4;color:#04212a}.app-sheet .ghost{background:transparent;color:#dbe4ec;border:1px solid #243341}
.app-sheet .status{font:13px "B612 Mono",monospace}.app-sheet .ok{color:#5ed28c}.app-sheet .bad{color:#ff5b4f}`;

function openSettings(first) {
  const sheet = document.createElement("div");
  sheet.className = "app-sheet"; sheet.setAttribute("role", "dialog"); sheet.setAttribute("aria-modal", "true");
  sheet.innerHTML = `<div class="card">
    <h2>App settings</h2>
    <p>${first ? "Welcome. The examiner runs on Claude, so the app needs your own Anthropic API key (create one at console.anthropic.com → API keys)." : "Keys are stored only on this phone and sent only to Anthropic and OpenAI."}</p>
    <label>Anthropic API key (required)<input id="s-ak" type="password" autocomplete="off" spellcheck="false" placeholder="sk-ant-..."></label>
    <label>Speech-to-text
      <select id="s-stt">
        <option value="phone">Phone speech recognition: free, no playback</option>
        <option value="openai">OpenAI Whisper: recording with playback</option>
      </select></label>
    <label id="s-ok-wrap">OpenAI API key<input id="s-ok" type="password" autocomplete="off" spellcheck="false" placeholder="sk-..."></label>
    <p>Phone recognition transcribes live but keeps no audio. Whisper records every answer, lets you listen back and re-record, and costs about $0.006 per minute.</p>
    <div class="row"><button class="primary" id="s-save">Save</button><button class="ghost" id="s-test">Test key</button>${first ? "" : '<button class="ghost" id="s-close">Close</button>'}</div>
    <div class="status" id="s-status" aria-live="polite"></div>
    <p>Keys never leave the phone except in requests to those two services. Uninstalling the app deletes them.</p>
  </div>`;
  document.body.appendChild(sheet);
  const $ = (id) => sheet.querySelector("#" + id);
  $("s-ak").value = settings.anthropicKey; $("s-stt").value = settings.stt; $("s-ok").value = settings.openaiKey;
  const sync = () => { $("s-ok-wrap").hidden = $("s-stt").value !== "openai"; };
  $("s-stt").addEventListener("change", sync); sync();
  const status = (text, ok) => { const s = $("s-status"); s.textContent = text; s.className = "status " + (ok === true ? "ok" : ok === false ? "bad" : ""); };
  $("s-test").addEventListener("click", async () => {
    const key = $("s-ak").value.trim();
    if (!key) return status("Enter the Anthropic key first.", false);
    status("Testing…");
    try {
      const c = new Anthropic({ apiKey: key, dangerouslyAllowBrowser: true, maxRetries: 0, timeout: 60000 });
      await c.beta.messages.create({ model: MODEL, max_tokens: 64, output_config: { effort: "low" }, betas: ["server-side-fallback-2026-07-01"], fallbacks: "default", messages: [{ role: "user", content: "Reply with the word OK." }] });
      status("Anthropic key works.", true);
    } catch (e) {
      status(e instanceof Anthropic.AuthenticationError ? "The key was rejected." : e instanceof Anthropic.APIConnectionError ? "No internet connection." : "Test failed: " + ((e && e.message) || e), false);
    }
  });
  $("s-save").addEventListener("click", () => {
    const next = { anthropicKey: $("s-ak").value.trim(), stt: $("s-stt").value, openaiKey: $("s-ok").value.trim() };
    if (!next.anthropicKey) return status("The Anthropic key is required.", false);
    if (next.stt === "openai" && !next.openaiKey) return status("Enter the OpenAI key, or choose phone recognition.", false);
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)); } catch { return status("Could not save on this phone.", false); }
    location.reload(); // capabilities are read once at start-up
  });
  if (!first) $("s-close").addEventListener("click", () => sheet.remove());
}

function installSettingsUi() {
  const style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
  const btn = document.createElement("button");
  btn.className = "app-settings-btn"; btn.type = "button"; btn.textContent = "⚙ SETTINGS"; btn.setAttribute("aria-label", "App settings");
  btn.addEventListener("click", () => openSettings(false));
  document.body.appendChild(btn);
  // only on the start screen, so it never covers the exam controls
  const start = document.getElementById("v-start");
  const sync = () => { btn.hidden = !start || start.hidden; };
  if (start) new MutationObserver(sync).observe(start, { attributes: true, attributeFilter: ["hidden"] });
  sync();
  if (!settings.anthropicKey) openSettings(true);
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", installSettingsUi); else installSettingsUi();
