"""Search engine verification meta tags."""
import re

from markupsafe import escape

SAFE = re.compile(r"^[A-Za-z0-9_\-+=/.]{4,200}$")


def register(api):
    def head(parts, page=None, **_):
        if not page or page.get("key") != "home":
            return parts  # verification only needs the home page
        for setting, name in (("google", "google-site-verification"), ("bing", "msvalidate.01")):
            value = str(api.setting(setting, "")).strip()
            if SAFE.match(value):
                parts.append(f'<meta name="{name}" content="{escape(value)}">')
        return parts
    api.add_filter("head_html", head)
