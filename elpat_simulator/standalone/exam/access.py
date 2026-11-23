"""Security headers, and an optional shared access code so a public URL does not spend your API credit for strangers."""
import hmac
from html import escape

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",  # the exam page is one inline script
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",  # playback of the candidate's own recordings
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])
OPEN_PREFIXES = ("/access", "/healthz", "/static/")


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        # Explicitly allow the microphone for this origin only (the page records answers with MediaRecorder).
        response.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=(), payment=()")
        return response


class AccessCodeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.ELPAT_ACCESS_CODE or request.session.get("elpat_ok") or request.path.startswith(OPEN_PREFIXES):
            return self.get_response(request)
        if request.path.startswith("/api/"):
            return JsonResponse({"code": "access_required", "message": "Enter the access code first."}, status=401)
        return HttpResponseRedirect("/access")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ELPAT Simulator · Access</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#090e13;color:#dbe4ec;font:16px system-ui,sans-serif;padding:16px;box-sizing:border-box}}
form{{display:grid;gap:12px;width:min(360px,100%);background:#0f1820;border:1px solid #243341;border-radius:10px;padding:20px}}
input{{padding:12px;border-radius:6px;border:1px solid #243341;background:#090e13;color:inherit;font:inherit}}
button{{padding:12px;border:0;border-radius:6px;background:#45cde4;color:#04212a;font-weight:700;font:inherit}}
p{{margin:0;color:#8494a3;font-size:14px}} .err{{color:#ff5b4f}}</style></head><body>
<form method="post"><b>ELPAT Simulator</b><p>Enter the access code you were given.</p>{error}
<input type="hidden" name="csrfmiddlewaretoken" value="{token}">
<input name="code" type="password" autocomplete="current-password" aria-label="Access code" required autofocus>
<button type="submit">Continue</button></form></body></html>"""


@require_http_methods(["GET", "POST"])
def access_view(request):
    error = ""
    if request.method == "POST":
        given = (request.POST.get("code") or "").encode()
        if settings.ELPAT_ACCESS_CODE and hmac.compare_digest(given, settings.ELPAT_ACCESS_CODE.encode()):
            request.session["elpat_ok"] = True
            return HttpResponseRedirect("/")
        error = '<p class="err">That code is not correct.</p>'
    return HttpResponse(PAGE.format(error=error, token=escape(get_token(request))))
