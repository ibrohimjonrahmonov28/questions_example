"""Settings for the standalone ELPAT simulator server.

Everything is configured through environment variables (see ../.env.example).
The server is stateless: no database, sessions in signed cookies, recordings stay in the
candidate's browser (IndexedDB). Audio is only sent to the server to be transcribed.
"""
from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
# Folder that holds the shared frontend (index.html + pics/). Defaults to the parent of standalone/.
FRONTEND_DIR = Path(os.environ.get("ELPAT_FRONTEND_DIR", BASE_DIR.parent)).resolve()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=1 for local development).")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "exam",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "exam.access.SecurityHeadersMiddleware",
    "exam.access.AccessCodeMiddleware",
]

ROOT_URLCONF = "elpat_server.urls"
WSGI_APPLICATION = "elpat_server.wsgi.application"
DATABASES: dict = {}

# Sessions only carry the "access code accepted" flag, so signed cookies are enough.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
CSRF_COOKIE_HTTPONLY = False  # the page reads it to send X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"

# HTTPS: microphone access in browsers requires a secure context.
ELPAT_TRUST_PROXY = env_bool("ELPAT_TRUST_PROXY", not DEBUG)  # behind Render/Railway/Fly/nginx
if ELPAT_TRUST_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", not DEBUG)
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}}
WHITENOISE_USE_FINDERS = DEBUG

# Rate limiting uses the cache. LocMem is per process; set REDIS_URL when running several instances.
if os.environ.get("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": os.environ["REDIS_URL"]}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Uploads: answers are short, but allow long ones (2-minute picture comparison ≈ 1 MB of Opus).
ELPAT_MAX_AUDIO_MB = int(os.environ.get("ELPAT_MAX_AUDIO_MB", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024  # JSON bodies (Claude prompts are capped at 256 KB anyway)
FILE_UPLOAD_MAX_MEMORY_SIZE = ELPAT_MAX_AUDIO_MB * 1024 * 1024

# ---- ELPAT
ELPAT_MODEL = os.environ.get("ELPAT_MODEL", "claude-opus-5-5")
ELPAT_FAKE_AI = env_bool("ELPAT_FAKE_AI", False)  # canned examiner replies, for tests and demos only
ELPAT_STT_PROVIDER = os.environ.get("ELPAT_STT_PROVIDER", "").strip().lower()  # openai | deepgram | fake
ELPAT_FAKE_TRANSCRIPT = os.environ.get("ELPAT_FAKE_TRANSCRIPT", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_STT_MODEL = os.environ.get("OPENAI_STT_MODEL", "whisper-1")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = os.environ.get("DEEPGRAM_MODEL", "nova-3")
ELPAT_ACCESS_CODE = os.environ.get("ELPAT_ACCESS_CODE", "")
ELPAT_RATE_CLAUDE = int(os.environ.get("ELPAT_RATE_CLAUDE", "120"))  # requests per 10 minutes per client
ELPAT_RATE_STT = int(os.environ.get("ELPAT_RATE_STT", "120"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"elpat": {"handlers": ["console"], "level": os.environ.get("ELPAT_LOG_LEVEL", "INFO")}},
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
