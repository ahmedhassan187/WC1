import sys
import ssl
from supabase import create_client, Client
from app.config import get_settings

# ──────────────────────────────────────────────────────────────
# SSL workaround for Supabase certificate hostname mismatch
# ──────────────────────────────────────────────────────────────
# The Supabase project URL (gwktagvusyaqzsibsmxv.supabase.co) sits behind
# Cloudflare which presents a certificate with CN=supabase.co. Python 3.14+
# is stricter about hostname validation and rejects this as a mismatch.
#
# We override the default SSL context globally so that ALL outgoing HTTPS
# connections (including the supabase-py *auth* module which creates its own
# internal httpx clients) inherit the relaxed hostname check.
# ──────────────────────────────────────────────────────────────

_original_context = ssl.create_default_context


def _relaxed_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that skips hostname checking but still verifies the cert."""
    ctx = _original_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED  # certificate itself must still be valid
    return ctx


# Apply the override globally — this affects ALL HTTPS connections made by this process,
# including the internal httpx clients created by supabase-py's auth and REST modules.
ssl._create_default_https_context = _relaxed_ssl_context  # noqa: E402


def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_admin() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)
