"""Site stats beacon: one small request per page view to the dashboard host. See cms/stats.py."""
from markupsafe import Markup

from cms.stats import beacon_script


def register(api):
    def body_end(parts, page=None, lang=None, preview=False, **_):
        if preview:
            return parts
        status = 404 if (page or {}).get("key") == "404" else 200
        parts.append(Markup(beacon_script(status)))
        return parts
    api.add_filter("body_end_html", body_end)
