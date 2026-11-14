"""Announcement bar at the top of every page (in the spirit of Hello Bar / WP Notification Bars).

The site is static, so the start and end dates are checked in the visitor's browser: the bar is built into every page
hidden, and a few lines of script show it inside the date window. Closing it is remembered in localStorage per message,
so a new message shows again.
"""
import hashlib

from markupsafe import Markup

STYLES = {"teal": ("#01a99a", "#06221f", "#06221f"), "dark": ("#0b1320", "#ffffff", "#7fe3d8"),
          "sand": ("#f3eee4", "#0b1320", "#017f74")}
CLOSE = {"en": "Close announcement", "ar": "إغلاق الإعلان"}


def register(api):
    def bar(parts, page=None, lang=None, preview=False, **_):
        code = (lang or {}).get("code", "en")
        text = str(api.setting(f"text_{code}", "") or api.setting("text_en", "")).strip()
        if not text:
            return parts
        label = str(api.setting(f"link_label_{code}", "") or "").strip()
        url = str((api.setting("link_url_ar", "") if code == "ar" else "") or api.setting("link_url", "") or "").strip()
        if url and not url.startswith(("/", "https://", "http://", "#", "mailto:")):
            url = ""
        bg, fg, link = STYLES.get(str(api.setting("style", "teal")), STYLES["teal"])
        key = hashlib.sha256(f"{text}|{label}|{url}".encode()).hexdigest()[:10]
        arrow = "←" if code == "ar" else "→"
        link_html = Markup(' <a href="%s">%s %s</a>') % (url, label, arrow) if url and label else ""
        html = Markup(
            '<div class="announce" id="announce" role="region" aria-label="%s" hidden data-start="%s" data-end="%s" data-key="%s">'
            '<p>%s%s</p><button type="button" aria-label="%s">×</button></div>'
            '<style>.announce{background:%s;color:%s;font-size:15px;line-height:1.45;position:relative;z-index:61}'
            '.announce[hidden]{display:none}.announce p{margin:0;padding:10px 52px;text-align:center}'
            '.announce a{color:%s;font-weight:700;text-decoration:underline;text-underline-offset:3px;white-space:nowrap}'
            '.announce button{position:absolute;inset-inline-end:10px;top:50%%;transform:translateY(-50%%);background:none;border:0;'
            'color:inherit;font-size:22px;line-height:1;padding:6px 10px;cursor:pointer;opacity:.75}.announce button:hover{opacity:1}'
            '@media(max-width:640px){.announce p{padding:9px 44px 9px 16px;text-align:start;font-size:14px}'
            '[dir=rtl] .announce p{padding:9px 16px 9px 44px}}</style>'
            '<script>(function(){var b=document.getElementById("announce");if(!b)return;var d=new Date(),t=d.getFullYear()+"-"+'
            '("0"+(d.getMonth()+1)).slice(-2)+"-"+("0"+d.getDate()).slice(-2),s=b.dataset.start,e=b.dataset.end,k="tcms-announce-"+b.dataset.key;'
            'if((s&&t<s)||(e&&t>e))return;try{if(localStorage.getItem(k))return}catch(x){}b.hidden=false;'
            'b.querySelector("button").addEventListener("click",function(){b.hidden=true;try{localStorage.setItem(k,"1")}catch(x){}})})();</script>'
        ) % (CLOSE.get(code, CLOSE["en"]), str(api.setting("starts", "") or ""), str(api.setting("ends", "") or ""), key,
             text, link_html, CLOSE.get(code, CLOSE["en"]), Markup(bg), Markup(fg), Markup(link))
        parts.append(html)
        return parts
    api.add_filter("body_start_html", bar)
