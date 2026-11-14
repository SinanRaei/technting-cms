"""Newsletter sign-up box at the end of articles. The form posts to /api/subscribe on the dashboard host; see crm/newsletter.py."""
import json

from django.conf import settings
from markupsafe import Markup

DEFAULTS = {
    "en": {"title": "Get new insights by email", "text": "One email when we publish something useful. No spam; leave any time.",
           "button": "Subscribe", "placeholder": "Work email", "label": "Email address", "sending": "Sending…"},
    "ar": {"title": "تصلكم مقالاتنا الجديدة بالبريد", "text": "رسالة واحدة عند نشر ما يفيدكم، بلا إزعاج، ويمكنكم إلغاء الاشتراك في أي وقت.",
           "button": "اشتراك", "placeholder": "بريد العمل", "label": "البريد الإلكتروني", "sending": "جارٍ الإرسال…"},
}

FORM = """<section class="nl-box" aria-labelledby="nl-title"><h2 id="nl-title">%(title)s</h2><p>%(text)s</p>
<form class="nl-form" novalidate><label class="sr-only" for="nl-email">%(label)s</label>
<input id="nl-email" type="email" name="email" required autocomplete="email" placeholder="%(placeholder)s" dir="ltr">
<span class="nl-hp" aria-hidden="true"><input type="text" name="website" tabindex="-1" autocomplete="off"></span>
<button type="submit" class="button">%(button)s</button><div class="ts-box" data-ts></div></form><p class="nl-msg" role="status" hidden></p>
<p class="nl-legal"><a href="%(privacy)s">%(privacy_label)s</a></p></section>
<style>.nl-box{margin-top:48px;padding:26px 24px;border:1px solid var(--line,#e2ddd1);border-radius:16px;background:var(--paper,#faf8f3)}
.nl-box h2{margin:0 0 6px;font-size:22px}.nl-box p{margin:0 0 14px}.nl-form{display:flex;gap:10px;flex-wrap:wrap}.nl-form .ts-box{flex-basis:100%%}.nl-form .ts-box:empty{display:none}
.nl-form input[type=email]{flex:1 1 240px;min-width:0;max-width:100%%;box-sizing:border-box;font:inherit;padding:11px 14px;border:1px solid var(--line,#d8d2c4);border-radius:999px;background:#fff}
.nl-hp{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%%);white-space:nowrap}.nl-box{position:relative}.nl-msg{margin:12px 0 0 !important;font-weight:600}.nl-legal{margin:10px 0 0 !important;font-size:13.5px}.nl-legal a{color:inherit}</style>
<script>(function(){var f=document.querySelector(".nl-form");if(!f)return;var m=f.parentNode.querySelector(".nl-msg"),b=f.querySelector("button");
var ts=function(){return window.TechntingCMSTurnstile||{ready:function(){return true},mount:function(){},reset:function(){}}};
f.addEventListener("submit",function(e){e.preventDefault();if(!ts().ready(f)){ts().mount(f);m.textContent=%(check)s;m.hidden=false;return}var d=new URLSearchParams(new FormData(f));d.append("lang",%(lang)s);d.append("page",location.pathname);
b.disabled=true;var old=b.textContent;b.textContent=%(sending)s;
fetch(%(endpoint)s,{method:"POST",body:d,credentials:"omit"}).then(function(r){return r.json()}).then(function(r){m.textContent=r.message;m.hidden=false;if(r.ok)f.hidden=true})
.catch(function(){m.textContent=%(fail)s;m.hidden=false}).then(function(){ts().reset(f);b.disabled=false;b.textContent=old})})})();</script>"""

FAIL = {"en": "We could not sign you up right now. Please try again later.", "ar": "تعذّر الاشتراك الآن. يرجى المحاولة لاحقاً."}
CHECK = {"en": "Please complete the security check, then press Subscribe again.", "ar": "يرجى إكمال التحقق الأمني ثم الضغط على «اشتراك» مرة أخرى."}
PRIVACY = {"en": "How we use your email", "ar": "كيف نستخدم بريدكم"}


def register(api):
    def box(parts, page=None, lang=None, preview=False, **_):
        code = (lang or {}).get("code", "en")
        d = DEFAULTS.get(code, DEFAULTS["en"])
        title = str(api.setting(f"title_{code}", "") or d["title"])
        text = str(api.setting(f"text_{code}", "") or d["text"])
        esc = Markup.escape

        def js(v):
            return Markup(json.dumps(v, ensure_ascii=False).replace("</", "<\\/"))
        parts.append(Markup(FORM % {
            "title": esc(title), "text": esc(text), "label": esc(d["label"]), "placeholder": esc(d["placeholder"]),
            "button": esc(d["button"]), "privacy": esc((lang or {}).get("home", "/") + "privacy/"),
            "privacy_label": esc(PRIVACY.get(code, PRIVACY["en"])), "lang": js(code),
            "sending": js(d["sending"]), "fail": js(FAIL.get(code, FAIL["en"])), "check": js(CHECK.get(code, CHECK["en"])),
            "endpoint": js(settings.TECHNTING_CMS_ADMIN_URL + "/api/subscribe")}))
        return parts
    api.add_filter("post_end_html", box)
