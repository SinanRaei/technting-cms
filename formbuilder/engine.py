"""Form logic shared by the public API, the dashboard preview, emails and tests.

Spec(form) loads a form once (steps, fields, options) and answers the questions the rest of the app asks: which steps
and fields are visible for these answers, are the answers valid, what do the calculations give, which tags apply, and
what do the results say. Results are rendered on the server into plain blocks, stored on the submission, and turned
into HTML for the page (to_html) or the email (to_email_html) from the same blocks, so both always match.
"""
import re

from django.utils.html import escape

from . import expr
from .models import Field

EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
PHONE_RE = re.compile(r"[+()0-9 .-]{4,40}")
PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}", re.S)
LANGS = ("en", "ar")
TEXT_LIMIT = {Field.TEXT: 300, Field.EMAIL: 254, Field.PHONE: 40, Field.TEXTAREA: 4000, Field.HIDDEN: 300}


def tx(value, lang):
    """Text in the language, falling back to English."""
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or ""
    return value or ""


class Spec:
    def __init__(self, form, steps=None):
        self.form = form
        qs = form.steps.prefetch_related("fields__options")
        self.steps = [s for s in qs if not steps or s.key in steps]
        self.all_steps = list(qs) if steps else self.steps
        self.fields = [f for s in self.steps for f in s.fields.all()]
        self.by_key = {f.key: f for f in self.fields}            # what this person answers (a link may limit the steps)
        self.index = {f.key: {"type": f.type, "options": {o.key: {"values": o.values, "is_unknown": o.is_unknown}
                                                           for o in f.options.all()}} for s in self.all_steps for f in s.fields.all()}
        self.labels = (form.results or {}).get("labels", {})

    def env(self, answers, calcs=None, lang="en", extra=None):
        return expr.Env(fields=self.index, answers=answers, calcs=calcs if calcs is not None else {}, labels=self.labels,
                        lang=lang, settings=self.form.settings or {}, extra=extra or {})

    # ---------------------------------------------------------------- visibility
    def visible(self, answers):
        """{step key: [visible fields]} for these answers, steps in order."""
        env = self.env(answers)
        out = {}
        for s in self.steps:
            if expr.truthy(s.visible_if, env):
                out[s.key] = [f for f in s.fields.all() if expr.truthy(f.visible_if, env)]
        return out

    def visible_options(self, field, answers):
        env = self.env(answers)
        return [o for o in field.options.all() if expr.truthy(o.visible_if, env)]

    # ---------------------------------------------------------------- answers
    def clean(self, raw, final=False):
        """Checked answers and errors {field key: code}. Unknown keys and wrong types are dropped. final=True also drops
        answers to hidden questions and requires every visible required one (repeated until nothing changes, because a
        dropped answer can hide another question)."""
        answers, errors = {}, {}
        raw = raw if isinstance(raw, dict) else {}
        for key, value in raw.items():
            f = self.by_key.get(str(key))
            if f is None or f.type == Field.INFO:
                continue
            ok, v = self._clean_value(f, value)
            if ok and v not in (None, "", []):
                answers[f.key] = v
            elif not ok:
                errors[f.key] = "invalid"
        if not final:
            return answers, errors
        for _ in range(5):
            vis = self.visible(answers)
            shown = {f.key: f for fields in vis.values() for f in fields}
            before = dict(answers)
            for key in list(answers):
                f = self.by_key.get(key)
                if key not in shown:
                    answers.pop(key)
                elif f is not None and f.has_options:
                    allowed = {o.key for o in self.visible_options(f, answers)}
                    v = answers[key]
                    if (isinstance(v, list) and not set(v) <= allowed) or (not isinstance(v, list) and v not in allowed):
                        answers.pop(key)
                        errors[key] = "invalid"
            if answers == before:
                break
        for f in shown.values():
            if f.required and f.type not in (Field.INFO, Field.HIDDEN) and answers.get(f.key) in (None, "", [], False):
                errors.setdefault(f.key, "required")
        return answers, errors

    def _clean_value(self, f, value):
        t = f.type
        extra = f.options_extra or {}
        if t in (Field.TEXT, Field.EMAIL, Field.PHONE, Field.TEXTAREA, Field.HIDDEN):
            if not isinstance(value, str):
                return False, None
            v = value.strip()
            limit = int(extra.get("max_length") or TEXT_LIMIT.get(t, 300))
            if len(v) > limit or any(ord(c) < 32 and c not in "\n\t" for c in v):
                return False, None
            if t != Field.TEXTAREA and "\n" in v:
                return False, None
            if v and t == Field.EMAIL and not EMAIL_RE.fullmatch(v):
                return False, None
            if v and t == Field.PHONE and (not PHONE_RE.fullmatch(v) or sum(c.isdigit() for c in v) < 6):
                return False, None
            return True, v
        if t in (Field.SELECT, Field.RADIO):
            keys = {o.key for o in f.options.all()}
            return (True, value) if isinstance(value, str) and (value in keys or value == "") else (False, None)
        if t == Field.CHECKBOX:
            keys = {o.key for o in f.options.all()}
            if not isinstance(value, list) or not all(isinstance(v, str) and v in keys for v in value):
                return False, None
            return True, sorted(set(value), key=[o.key for o in f.options.all()].index)
        if t == Field.CONSENT:
            return (True, True) if value is True else (True, None) if value in (False, None, "") else (False, None)
        if t == Field.SCALE:
            try:
                n = float(value)
            except (TypeError, ValueError):
                return (True, None) if value in (None, "") else (False, None)
            lo, hi = float(extra.get("min", 0)), float(extra.get("max", 10))
            if not lo <= n <= hi:
                return False, None
            return True, int(n) if n.is_integer() else n
        return False, None

    # ---------------------------------------------------------------- calculations, tags, results
    def compute(self, answers, lang="en"):
        """Every calculation in order (later ones can use earlier ones). Errors are kept as {name: message}."""
        calcs, errors = {}, {}
        env = self.env(answers, calcs, lang)
        for c in self.form.calcs or []:
            name = str(c.get("name") or "")
            if not name:
                continue
            try:
                calcs[name] = expr.evaluate(c.get("expr", ""), env)
            except (expr.ExprError, TypeError, ValueError, IndexError) as exc:
                calcs[name], errors[name] = 0, str(exc)
        return calcs, errors

    def public_calcs(self, calcs):
        internal = {c.get("name") for c in self.form.calcs or [] if c.get("internal")}
        return {k: v for k, v in calcs.items() if k not in internal}

    def tags(self, answers, calcs):
        env = self.env(answers, calcs)
        return [str(t["name"]) for t in self.form.opt("tags", []) if t.get("name") and expr.truthy(t.get("if"), env, default=False)]

    def results(self, answers, calcs, lang, emailed=False):
        """Rendered result blocks for the respondent (never internal calculations)."""
        env = self.env(answers, self.public_calcs(calcs), lang, extra={"emailed": emailed})
        out = []
        for b in (self.form.results or {}).get("blocks", []):
            out.extend(self._block(b, env, lang))
        return out

    def _block(self, b, env, lang):
        if not expr.truthy(b.get("if"), env):
            return []
        t = b.get("type")
        if t == "heading":
            return [{"t": "h", "level": int(b.get("level") or 2), "html": fill(tx(b.get("text"), lang), env)}]
        if t == "text":
            return [{"t": "p", "style": b.get("style") or "p", "html": fill(tx(b.get("text"), lang), env)}]
        if t == "lookup":
            try:
                key = str(expr.evaluate(b.get("key") or "''", env))
            except expr.ExprError:
                key = ""
            text = (b.get("texts") or {}).get(key)
            if not text:
                return []
            title = fill(tx(b.get("title"), lang), env) if b.get("title") else ""
            return [{"t": "p", "style": b.get("style") or "p", "title": title, "html": fill(tx(text, lang), env)}]
        if t == "match":
            for case in b.get("cases") or []:
                if expr.truthy(case.get("if"), env, default=True):
                    return [{"t": "rung", "title": fill(tx(case.get("title"), lang), env), "html": fill(tx(case.get("text"), lang), env)}]
            return []
        if t == "scores":
            items = []
            for it in b.get("items") or []:
                try:
                    score, band = expr.evaluate(it.get("score") or "0", env), expr.evaluate(it.get("band") or "''", env)
                except expr.ExprError:
                    continue
                items.append({"label": fill(tx(it.get("label"), lang), env), "score": expr.num(score), "band": str(band),
                              "band_label": escape(env.call("label", [band]))})
            return [{"t": "scores", "items": items}]
        if t == "verify":
            keys = b.get("fields") or [f.key for f in self.fields if f.has_options and tx(f.why, "en")]
            rule = b.get("include") or "unknown(this) or score(this) == 0"
            items = []
            for k in keys:
                f = self.by_key.get(k)
                if f is None:
                    continue
                env.extra["this"] = k
                if expr.truthy(rule, env, default=False):
                    items.append({"key": k, "q": fill(tx(f.label, lang), env), "why": fill(tx(f.why, lang), env)})
            env.extra.pop("this", None)
            if items:
                return [{"t": "verify", "intro": fill(tx(b.get("intro"), lang), env), "items": items}]
            return [{"t": "p", "style": "p", "html": fill(tx(b.get("empty"), lang), env)}] if tx(b.get("empty"), lang) else []
        if t == "button":
            url = str(fill(tx(b.get("url"), lang), env, markdown=False)).strip()
            if not url.startswith(("https://", "http://", "/", "mailto:")):
                url = ""
            return [{"t": "button", "label": fill(tx(b.get("label"), lang), env), "url": url,
                     "note": fill(tx(b.get("note"), lang), env) if b.get("note") else ""}]
        return []

    # ---------------------------------------------------------------- what the browser gets
    def public(self, lang, link=None):
        """The form as the respondent's browser needs it: no option values, no "why it matters", no calculations,
        no result rules. Visibility rules go as JSON trees (expr.to_client)."""
        env = self.env({}, lang=lang)
        f = self.form

        def cond(src):
            try:
                return expr.to_client(src)
            except expr.ExprError:
                return None

        steps = []
        for s in self.steps:
            fields = []
            for fl in s.fields.all():
                extra = fl.options_extra or {}
                item = {"key": fl.key, "type": fl.type, "label": fill(tx(fl.label, lang), env), "help": fill(tx(fl.help, lang), env),
                        "required": fl.required, "if": cond(fl.visible_if),
                        "texts": [{"if": cond(t_.get("if")), "html": fill(tx(t_.get("text"), lang), env)} for t_ in fl.texts or []]}
                if fl.has_options:
                    item["options"] = [{"key": o.key, "label": fill(tx(o.label, lang), env, markdown=False), "unknown": o.is_unknown,
                                        "if": cond(o.visible_if)} for o in fl.options.all()]
                for k in ("min", "max", "step"):
                    if k in extra:
                        item[k] = extra[k]
                for k in ("min_label", "max_label", "placeholder"):
                    if extra.get(k):
                        item[k] = tx(extra[k], lang)
                if fl.type in (Field.TEXT, Field.TEXTAREA, Field.HIDDEN):
                    item["max_length"] = int(extra.get("max_length") or TEXT_LIMIT.get(fl.type, 300))
                if extra.get("autocomplete"):
                    item["autocomplete"] = extra["autocomplete"]
                fields.append(item)
            steps.append({"key": s.key, "title": fill(tx(s.title, lang), env), "intro": fill(tx(s.intro, lang), env),
                          "if": cond(s.visible_if), "fields": fields})
        return {"slug": f.slug, "version": f.version, "lang": lang, "dir": "rtl" if lang == "ar" else "ltr",
                "title": escape(f.name(lang)), "intro": fill(tx(f.intro, lang), env), "steps": steps,
                "results": f.opt("results", "show"), "thank_you": fill(tx(f.opt("thank_you", {}), lang), env),
                "link": bool(link)}


# ---------------------------------------------------------------- text
def fill(text, env, markdown=True):
    """Text with {{ expression }} placeholders and light markdown (**bold**, *italic*, [link](https://…), line breaks),
    escaped for HTML. Values from answers are always escaped and never read as markdown."""
    text = text or ""
    values = []

    def hold(m):
        try:
            v = expr.evaluate(m.group(1).strip(), env)
        except (expr.ExprError, TypeError, ValueError):
            v = ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        values.append(escape("" if v is None else str(v)))
        return f"\x00{len(values) - 1}\x00"

    out = escape(PLACEHOLDER.sub(hold, text))
    if markdown:
        out = re.sub(r"\[([^\]\n]+)\]\(((?:https://|/)[^)\s\"'<>]+)\)", r'<a href="\2">\1</a>', out)
        out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
        out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
        out = _lists(out.split("\n"))
    return re.sub("\x00(\\d+)\x00", lambda m: values[int(m.group(1))], out)


def _lists(lines):
    """Lines starting with "- " become a list; other lines are joined with line breaks."""
    out, items, text = [], [], []
    for ln in lines:
        if ln.startswith("- "):
            if text:
                out.append("<br>".join(text))
                text = []
            items.append(f"<li>{ln[2:].strip()}</li>")
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if ln.strip() or text:
            text.append(ln)
    if text:
        out.append("<br>".join(text))
    if items:
        out.append("<ul>" + "".join(items) + "</ul>")
    return "".join(out)


# ---------------------------------------------------------------- results to HTML
def to_html(blocks):
    """Result blocks as HTML for the results page (classes styled by the theme's forms.css)."""
    parts = []
    for b in blocks:
        t = b.get("t")
        if t == "h":
            lvl = min(max(int(b.get("level") or 2), 1), 4)
            parts.append(f'<h{lvl} class="fr-h fr-h{lvl}">{b["html"]}</h{lvl}>')
        elif t == "p":
            title = f'<h3 class="fr-h fr-h3">{b["title"]}</h3>' if b.get("title") else ""
            parts.append(f'<div class="fr-block fr-{escape(b.get("style") or "p")}">{title}<p>{b["html"]}</p></div>')
        elif t == "scores":
            rows = "".join(
                f'<li class="fr-score band-{escape(i["band"])}"><span class="fr-score-name">{i["label"]}</span>'
                f'<span class="fr-score-bar" aria-hidden="true"><span style="width:{max(0, min(100, int(i["score"])))}%"></span></span>'
                f'<span class="fr-score-num"><b>{int(i["score"])}</b>/100</span><span class="fr-score-band">{i["band_label"]}</span></li>'
                for i in b["items"])
            parts.append(f'<ul class="fr-scores">{rows}</ul>')
        elif t == "verify":
            items = "".join(f'<li><span class="fr-q">{i["q"]}</span><span class="fr-why">{i["why"]}</span></li>' for i in b["items"])
            parts.append(f'<div class="fr-block fr-verify"><p>{b["intro"]}</p><ol>{items}</ol></div>')
        elif t == "rung":
            parts.append(f'<div class="fr-block fr-rung"><h3 class="fr-h fr-h3">{b["title"]}</h3><p>{b["html"]}</p></div>')
        elif t == "button":
            btn = (f'<a class="button button-primary fr-book" href="{escape(b["url"])}" rel="noopener">{b["label"]}</a>'
                   if b.get("url") else "")
            note = f'<p class="fr-note">{b["note"]}</p>' if b.get("note") else ""
            parts.append(f'<div class="fr-block fr-cta">{btn}{note}</div>')
    return "\n".join(parts)


INK, TEAL, SLATE, PAPER, MIST = "#0B1320", "#007F76", "#647488", "#F7F5F0", "#E5EBF0"


def to_email_html(blocks, lang, before="", after=""):
    """The same blocks as an email: inline styles only (mail apps drop style sheets), dir=rtl for Arabic."""
    rtl = lang == "ar"
    align = "right" if rtl else "left"
    font = "'IBM Plex Sans Arabic',Tahoma,Arial,sans-serif" if rtl else "Manrope,Arial,sans-serif"
    p = f"margin:0 0 14px;line-height:1.6;color:{INK};font-size:15px"
    parts = []
    for b in blocks:
        t = b.get("t")
        if t == "h":
            size = {1: 24, 2: 19, 3: 16}.get(int(b.get("level") or 2), 16)
            parts.append(f'<h{min(int(b.get("level") or 2), 3)} style="margin:22px 0 10px;font-size:{size}px;color:{INK}">{b["html"]}</h{min(int(b.get("level") or 2), 3)}>')
        elif t == "p":
            style = b.get("style")
            extra = (f";color:{SLATE};font-size:13px" if style in ("note", "small") else
                     ";font-size:17px;font-weight:600" if style == "lead" else
                     f";background:{PAPER};padding:12px 14px;border-{'right' if rtl else 'left'}:3px solid {TEAL}" if style == "callout" else "")
            title = f'<h3 style="margin:18px 0 6px;font-size:16px;color:{INK}">{b["title"]}</h3>' if b.get("title") else ""
            parts.append(f'{title}<p style="{p}{extra}">{b["html"]}</p>')
        elif t == "scores":
            rows = "".join(
                f'<tr><td style="padding:6px 0;color:{INK};font-weight:700">{i["label"]}</td>'
                f'<td style="padding:6px 10px;color:{INK}" dir="ltr">{int(i["score"])}/100</td>'
                f'<td style="padding:6px 0;color:{TEAL};font-weight:700">{i["band_label"]}</td></tr>' for i in b["items"])
            parts.append(f'<table role="presentation" style="border-collapse:collapse;margin:4px 0 14px">{rows}</table>')
        elif t == "verify":
            items = "".join(f'<li style="margin:0 0 10px"><b>{i["q"]}</b><br><span style="color:{SLATE}">{i["why"]}</span></li>' for i in b["items"])
            parts.append(f'<p style="{p}">{b["intro"]}</p><ol style="margin:0 0 14px;padding-{align}:20px;color:{INK};font-size:14px;line-height:1.5">{items}</ol>')
        elif t == "rung":
            parts.append(f'<div style="background:{MIST};border-radius:10px;padding:14px 16px;margin:0 0 14px">'
                         f'<p style="margin:0 0 6px;font-weight:800;color:{INK};font-size:16px">{b["title"]}</p>'
                         f'<p style="margin:0;line-height:1.6;color:{INK};font-size:14px">{b["html"]}</p></div>')
        elif t == "button":
            if b.get("url"):
                parts.append(f'<p style="margin:18px 0 8px"><a href="{escape(b["url"])}" style="display:inline-block;background:{INK};'
                             f'color:#fff;padding:12px 18px;border-radius:999px;text-decoration:none;font-weight:700">{b["label"]}</a></p>')
            if b.get("note"):
                parts.append(f'<p style="{p};color:{SLATE};font-size:13px">{b["note"]}</p>')
    body = "".join(parts)
    return (f'<!doctype html><html lang="{lang}" dir="{"rtl" if rtl else "ltr"}"><head><meta charset="utf-8"></head>'
            f'<body style="margin:0;background:#ffffff"><div dir="{"rtl" if rtl else "ltr"}" style="font-family:{font};text-align:{align};'
            f'max-width:640px;margin:0 auto;padding:24px 18px">{before}{body}{after}</div></body></html>')


def to_text(blocks):
    """Plain-text version of the results (email fallback, CSV)."""
    def plain(html):
        return re.sub(r"<[^>]+>", "", (html or "").replace("<br>", "\n")).replace("&amp;", "&").replace("&#x27;", "'") \
            .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
    lines = []
    for b in blocks:
        t = b.get("t")
        if t == "h":
            lines += ["", plain(b["html"]).upper() if b.get("level") == 1 else plain(b["html"])]
        elif t == "p":
            if b.get("title"):
                lines.append(plain(b["title"]))
            lines.append(plain(b["html"]))
        elif t == "scores":
            lines += [f'{plain(i["label"])}: {int(i["score"])}/100, {plain(i["band_label"])}' for i in b["items"]]
        elif t == "verify":
            lines.append(plain(b["intro"]))
            lines += [f'- {plain(i["q"])}\n  {plain(i["why"])}' for i in b["items"]]
        elif t == "rung":
            lines += [plain(b["title"]), plain(b["html"])]
        elif t == "button":
            lines.append(f'{plain(b["label"])}: {b.get("url") or ""}'.strip(": "))
            if b.get("note"):
                lines.append(plain(b["note"]))
    return "\n".join(lines).strip()
