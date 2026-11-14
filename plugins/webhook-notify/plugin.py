"""Notify a Slack / Teams channel about new enquiries (minimal personal data: no email, phone or message)."""
import json
import logging
import threading
import urllib.request

ALLOWED_HOSTS = ("hooks.slack.com", ".webhook.office.com", ".logic.azure.com", ".powerplatform.com")


def register(api):
    def notify(submission=None, **_):
        url = str(api.setting("url", "")).strip()
        host = url.split("/")[2] if url.startswith("https://") and url.count("/") >= 3 else ""
        if not submission or not host or not any(host == h or host.endswith(h) for h in ALLOWED_HOSTS):
            return
        text = (f"New website enquiry from {submission.name}"
                f"{' (' + submission.organisation + ')' if submission.organisation else ''}"
                f" · {submission.interest or 'General'} · open the Technting CMS inbox to read it.")
        payload = {"text": text} if api.setting("format", "slack") == "slack" else {
            "type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {
                "type": "AdaptiveCard", "version": "1.4", "body": [{"type": "TextBlock", "text": text, "wrap": True}]}}]}

        def send():
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=10).close()
            except Exception as exc:
                logging.getLogger(__name__).warning("enquiry webhook failed: %s", type(exc).__name__)
        threading.Thread(target=send, daemon=True).start()

    api.add_action("form_submitted", notify)
