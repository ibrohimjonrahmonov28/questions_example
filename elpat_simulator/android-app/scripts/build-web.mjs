// Assembles www/ for Capacitor from the shared exam page (../index.html) and pictures (../pics).
import { build } from "esbuild";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const app = path.resolve(here, "..");
const shared = path.resolve(app, "..");
const www = path.join(app, "www");

fs.rmSync(www, { recursive: true, force: true });
fs.mkdirSync(path.join(www, "pics"), { recursive: true });

await build({
  entryPoints: [path.join(app, "src/app.js")],
  bundle: true,
  format: "iife",
  target: ["chrome100"],
  minify: true,
  legalComments: "none",
  outfile: path.join(www, "app.js"),
});

fs.copyFileSync(path.join(app, "node_modules/dompurify/dist/purify.min.js"), path.join(www, "purify.min.js"));
for (const f of fs.readdirSync(path.join(shared, "pics"))) if (/^v[1-8][ab]\.jpg$/.test(f)) fs.copyFileSync(path.join(shared, "pics", f), path.join(www, "pics", f));

let page = fs.readFileSync(path.join(shared, "index.html"), "utf8");
const cdn = '<script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.1.6/purify.min.js"></script>';
if (!page.includes(cdn)) throw new Error("DOMPurify tag not found in index.html");
page = page.replace(cdn, '<script src="purify.min.js"></script>'); // bundled, works offline

// The shared page is written for a host that wraps it in a document skeleton; apply the same wrapper here.
// app.js must run before the page's inline script, because the page reads window.claude at start-up.
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0d0f">
<style>:root{color-scheme:dark;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
<script src="app.js"></script>
</head><body>
${page}
</body></html>
`;
fs.writeFileSync(path.join(www, "index.html"), html);
const size = (f) => Math.round(fs.statSync(path.join(www, f)).size / 1024) + " kB";
console.log(`www/ ready: index.html ${size("index.html")}, app.js ${size("app.js")}, ${fs.readdirSync(path.join(www, "pics")).length} pictures`);
