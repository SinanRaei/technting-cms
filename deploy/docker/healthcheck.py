"""Container health check: the dashboard answers its public status endpoint (no sign-in, no database writes)."""
import os
import sys
import urllib.request

hosts = [h.strip().lstrip(".") for h in os.environ.get("TECHNTING_CMS_ALLOWED_HOSTS", "localhost").split(",") if h.strip()]
host = next((h for h in hosts if h != "*"), "localhost")
req = urllib.request.Request("http://127.0.0.1:8000/api/contact/status", headers={"Host": host, "X-Forwarded-Proto": "https"})
try:
    with urllib.request.urlopen(req, timeout=4) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception as exc:
    print(f"unhealthy: {type(exc).__name__}", file=sys.stderr)
    sys.exit(1)
