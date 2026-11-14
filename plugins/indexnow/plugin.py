"""IndexNow: publish a key file and ping api.indexnow.org with the URLs changed by each publish."""
import hashlib
import json
import logging
import threading
import urllib.request
from urllib.parse import urlparse

from django.conf import settings

log = logging.getLogger(__name__)


def key():
    return hashlib.sha256(("indexnow:" + settings.SECRET_KEY).encode()).hexdigest()[:32]


def register(api):
    def write_key(target, ctx, **_):
        (target / f"{key()}.txt").write_text(key(), encoding="utf-8")

    def ping(log=None, changed_urls=(), **_):
        urls = [u for u in changed_urls if u.startswith(settings.TECHNTING_CMS_SITE_URL)][:1000]
        if not urls or settings.DEBUG:
            return
        host = urlparse(settings.TECHNTING_CMS_SITE_URL).netloc
        body = json.dumps({"host": host, "key": key(), "keyLocation": f"{settings.TECHNTING_CMS_SITE_URL}/{key()}.txt", "urlList": urls}).encode()

        def send():
            req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                         headers={"Content-Type": "application/json; charset=utf-8"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    logging.getLogger(__name__).info("IndexNow: %s URLs, HTTP %s", len(urls), r.status)
            except Exception as exc:
                logging.getLogger(__name__).warning("IndexNow ping failed: %s", exc)
        threading.Thread(target=send, daemon=True).start()

    api.add_action("publish_build", write_key)
    api.add_action("publish_after", ping)
