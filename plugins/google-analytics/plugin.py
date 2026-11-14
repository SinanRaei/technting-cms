"""Google Analytics 4, loaded only after consent.

No Google script, cookie or request exists until the visitor clicks Accept in the banner. The choice is
kept in localStorage ("tcms-consent": granted / denied); any element with [data-consent-open] reopens
the banner (for example a "Cookie settings" link in the privacy notice). Previews never load analytics.
"""
import json
import re

from markupsafe import Markup

ID = re.compile(r"^G-[A-Z0-9]{4,16}$")
TEXT = {
    "en": {"msg": "We use Google Analytics to understand which pages help visitors. It loads only if you accept.",
           "accept": "Accept", "decline": "No thanks", "more": "Privacy notice"},
    "ar": {"msg": "نستخدم Google Analytics لنعرف الصفحات المفيدة للزوار، ولا يُحمَّل إلا إذا وافقتم.",
           "accept": "موافق", "decline": "لا، شكراً", "more": "إشعار الخصوصية"},
}

SCRIPT = """<div class="consent" id="consent" role="dialog" aria-live="polite" aria-label="%(accept)s" hidden>
<p>%(msg)s <a href="%(privacy)s">%(more)s</a></p><div class="consent-actions"><button type="button" class="button button-small button-ghost" data-consent="denied">%(decline)s</button><button type="button" class="button button-small" data-consent="granted">%(accept)s</button></div></div>
<style>.consent{position:fixed;inset-inline:16px;bottom:16px;z-index:60;max-width:560px;margin-inline:auto;display:flex;flex-wrap:wrap;gap:12px 18px;align-items:center;justify-content:space-between;padding:16px 18px;background:#fff;border:1px solid #E2DDD1;border-radius:14px;box-shadow:0 18px 50px -20px rgba(11,19,32,.35);font-size:14.5px;line-height:1.5}.consent[hidden]{display:none}.consent p{margin:0;flex:1 1 260px}.consent-actions{display:flex;gap:8px}</style>
<script>(function(){var ID=%(id)s,K="tcms-consent",box=document.getElementById("consent");
function get(){try{return localStorage.getItem(K)}catch(e){return null}}
function set(v){try{localStorage.setItem(K,v)}catch(e){}}
function load(){if(window.gtag)return;window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments)};
gtag("consent","default",{analytics_storage:"granted",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied"});
gtag("js",new Date());gtag("config",ID,{anonymize_ip:true});var s=document.createElement("script");s.async=true;s.src="https://www.googletagmanager.com/gtag/js?id="+ID;document.head.appendChild(s)}
var v=get();if(v==="granted")load();else if(v!=="denied")box.hidden=false;
box.addEventListener("click",function(e){var b=e.target.closest("[data-consent]");if(!b)return;var c=b.getAttribute("data-consent");set(c);box.hidden=true;if(c==="granted")load();else if(window.gtag){location.reload()}});
document.addEventListener("click",function(e){if(e.target.closest("[data-consent-open]")){e.preventDefault();box.hidden=false}});})();</script>"""


def register(api):
    def body_end(parts, page=None, lang=None, preview=False, **_):
        mid = str(api.setting("measurement_id", "")).strip().upper()
        if preview or not ID.match(mid) or not lang:
            return parts
        code = lang.get("code", "en")
        t = TEXT.get(code, TEXT["en"])
        privacy = (lang.get("home") or "/") + "privacy/"
        parts.append(Markup(SCRIPT % {**{k: Markup.escape(v) for k, v in t.items()}, "id": json.dumps(mid),
                                      "privacy": Markup.escape(privacy)}))
        return parts
    api.add_filter("body_end_html", body_end)
