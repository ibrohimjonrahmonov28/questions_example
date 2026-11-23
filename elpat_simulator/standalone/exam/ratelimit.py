"""Fixed-window rate limiting on the Django cache (use Redis when running more than one instance)."""
import time

from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    if settings.ELPAT_TRUST_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def allow(key: str, limit: int, window: int = 600) -> bool:
    if limit <= 0:
        return True
    bucket = f"rl:{key}:{int(time.time() // window)}"
    if cache.add(bucket, 1, window + 5):
        return True
    try:
        count = cache.incr(bucket)
    except ValueError:  # expired between add() and incr()
        cache.set(bucket, 1, window + 5)
        count = 1
    return count <= limit
