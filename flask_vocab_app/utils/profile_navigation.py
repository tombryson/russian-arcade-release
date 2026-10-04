"""Keep profile-selection continuations inside the application."""
import re
from urllib.parse import unquote, urlsplit


def profile_return_url(value):
    fallback = '/#home'
    if not isinstance(value, str) or not value.startswith('/') or len(value) > 4096:
        return fallback
    if re.search(r'%(?![0-9a-fA-F]{2})', value):
        return fallback
    try:
        decoded = unquote(value, errors='strict')
        if (decoded.startswith('//') or '\\' in decoded
                or any(ord(char) < 32 or ord(char) == 127 for char in decoded)):
            return fallback
        parts = urlsplit(decoded)
    except (UnicodeError, ValueError):
        return fallback
    if parts.scheme or parts.netloc:
        return fallback
    return value
