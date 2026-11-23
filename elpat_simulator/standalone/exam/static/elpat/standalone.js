// Standalone shim: gives the shared exam page (index.html) the same window.claude.use() interface it has on claude.ai,
// backed by this server. sample → Claude via /api/claude; stt → /api/transcribe; downloads → a normal file download.
// Recording itself needs no shim: on a normal HTTPS page the browser allows getUserMedia + MediaRecorder directly.
(() => {
  "use strict";
  window.ELPAT_STANDALONE = true;

  const csrfToken = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || "";
  async function post(url, body) {
    const isForm = body instanceof FormData;
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: isForm ? { "X-CSRFToken": csrfToken() } : { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: isForm ? body : JSON.stringify(body),
      });
    } catch {
      throw { code: "upstream_error", message: "Network error. Check your connection." };
    }
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) throw { code: data.code || (response.status === 429 ? "rate_limited" : "upstream_error"), message: data.message || "HTTP " + response.status };
    return data;
  }

  const sample = Object.assign(
    async (input, options = {}) => {
      const data = await post("/api/claude", { input, tier: options.modelTier || "default", json: false });
      if (typeof options.onText === "function") { try { options.onText({ text: data.text, delta: data.text }); } catch {} }
      return { text: data.text || "", truncated: !!data.truncated };
    },
    {
      json: async (input, options = {}) => (await post("/api/claude", { input, tier: options.modelTier || "default", json: true })).value,
      limits: async () => ({ maxPromptBytes: 262144 }),
    },
  );

  const extensionFor = (type) => (/mp4|aac/.test(type) ? "m4a" : /ogg/.test(type) ? "ogg" : "webm");
  const stt = {
    transcribe: async (blob, options = {}) => {
      const form = new FormData();
      form.append("audio", blob, "answer." + extensionFor(blob.type || ""));
      form.append("prompt", options.prompt || "");
      return post("/api/transcribe", form);
    },
  };

  const downloads = {
    save: async ({ filename, data }) => {
      const blob = data instanceof Blob ? data : new Blob([data], { type: "text/markdown;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1500);
    },
  };

  const config = fetch("/api/config", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  const caps = { sample, stt, downloads };
  window.claude = {
    use: async (name) => {
      const c = await config;
      if (name === "sample" && !c.claude) return null;
      if (name === "stt" && !c.stt) return null;
      return caps[name] || null;
    },
  };
})();
