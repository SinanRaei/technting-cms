/* Technting Forms runner: shows a multi-step form built in Technting CMS (Forms) and sends it to the dashboard host.
   <div data-form-runner data-api="https://cms.example.com/api/forms/" data-slug="..." data-lang="en"
        data-link="(personal link token)" data-preview="1"></div>
   The form arrives without scores or result rules; results are worked out on the server and shown only after the
   answers are recorded. Drafts are saved on the server when the person moves to the next step; this browser keeps
   only the draft's token (localStorage), so the person can come back to it. */
(function () {
  "use strict";
  var UI = {
    en: { start: "Start", resume: "Continue where you left off", restart: "Start again", next: "Next", back: "Back",
      submit: "Send and see my results", sending: "Sending…", step: "Step {i} of {n}", required: "Please answer this question.",
      invalid: "Please check this answer.", choose: "Choose…", error: "Something went wrong. Please try again in a moment.",
      check: "Please complete the security check first.", progress: "Progress", saved: "Saved", req: "required",
      loading: "Loading the form…", closed: "This form is not open at the moment.", email: "Please enter a valid email address.",
      phone: "Please enter a valid phone number.", resumed: "Your earlier answers are back.", gone: "This link has expired or was withdrawn." },
    ar: { start: "ابدأوا", resume: "أكملوا من حيث توقفتم", restart: "ابدأوا من جديد", next: "التالي", back: "السابق",
      submit: "أرسلوا واعرضوا النتائج", sending: "جارٍ الإرسال…", step: "الخطوة {i} من {n}", required: "يرجى الإجابة عن هذا السؤال.",
      invalid: "يرجى مراجعة هذه الإجابة.", choose: "اختاروا…", error: "حدث خطأ. يرجى المحاولة بعد قليل.",
      check: "يرجى إكمال التحقق الأمني أولاً.", progress: "التقدم", saved: "تم الحفظ", req: "إلزامي",
      loading: "جارٍ تحميل النموذج…", closed: "هذا النموذج غير متاح حالياً.", email: "يرجى إدخال بريد إلكتروني صحيح.",
      phone: "يرجى إدخال رقم هاتف صحيح.", resumed: "عادت إجاباتكم السابقة.", gone: "انتهت صلاحية هذا الرابط أو أُلغي." }
  };
  var EMAIL = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;

  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] === false || attrs[k] == null) return;
      if (k === "text") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    if (html != null) e.innerHTML = html;
    return e;
  }
  function store(key, value) {
    try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }
  function stored(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function Runner(root) {
    this.root = root;
    this.api = (root.getAttribute("data-api") || "/api/forms/").replace(/\/?$/, "/");
    this.slug = root.getAttribute("data-slug");
    this.lang = root.getAttribute("data-lang") || document.documentElement.lang || "en";
    this.link = root.getAttribute("data-link") || "";
    this.preview = root.getAttribute("data-preview") === "1";
    this.t = UI[this.lang] || UI.en;
    this.answers = {};
    this.token = "";
    this.key = "technting-cms-form:" + this.slug;
    this.index = 0;
    this.load();
  }

  Runner.prototype.url = function (what) {
    return this.api + encodeURIComponent(this.slug) + "/" + what;
  };
  Runner.prototype.post = function (what, body) {
    body.lang = this.lang;
    if (this.link) body.link = this.link;
    if (this.preview) body.preview = true;
    return fetch(this.url(what), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      credentials: this.api.charAt(0) === "/" ? "same-origin" : "omit", cache: "no-store" })
      .then(function (r) { return r.json().then(function (d) { d.status = r.status; return d; }); });
  };
  Runner.prototype.event = function (kind, step) {
    if (this.preview) return;
    try {
      fetch(this.url("event"), { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true, credentials: "omit",
        body: JSON.stringify({ kind: kind, step: step || 0, lang: this.lang }) }).catch(function () {});
    } catch (e) { /* old browsers */ }
  };

  Runner.prototype.load = function () {
    var self = this;
    this.root.setAttribute("aria-busy", "true");
    this.root.appendChild(el("p", { "class": "fr-loading", text: this.t.loading }));
    var q = "?lang=" + encodeURIComponent(this.lang) + (this.link ? "&link=" + encodeURIComponent(this.link) : "");
    fetch(this.url("") + q, { credentials: this.api.charAt(0) === "/" ? "same-origin" : "omit", cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        self.root.removeAttribute("aria-busy");
        if (!d.ok) return self.message(d.message || self.t.closed);
        self.form = d.form;
        self.fields = {};
        self.form.steps.forEach(function (s) { s.fields.forEach(function (f) { self.fields[f.key] = f; }); });
        self.root.setAttribute("dir", d.form.dir);
        self.event("view");
        self.token = self.link ? "" : (stored(self.key) || "");
        if (self.link || self.token) {
          self.post("resume", { token: self.token }).then(function (r) {
            if (r.ok) { self.answers = r.answers || {}; self.resumeStep = r.step; self.intro(true); }
            else { if (!self.link) store(self.key, null); self.token = ""; self.intro(false, r.complete && r.message); }
          }).catch(function () { self.intro(false); });
        } else self.intro(false);
      })
      .catch(function () { self.root.removeAttribute("aria-busy"); self.message(self.t.error); });
  };

  Runner.prototype.message = function (text) {
    this.root.innerHTML = "";
    this.root.appendChild(el("p", { "class": "fr-message", role: "status", text: text }));
  };

  Runner.prototype.intro = function (canResume, doneMessage) {
    var self = this, t = this.t;
    this.root.innerHTML = "";
    var box = el("div", { "class": "fr-intro fr-enter" });
    if (this.form.intro) box.appendChild(el("div", { "class": "fr-intro-text" }, this.form.intro));
    if (doneMessage) box.appendChild(el("p", { "class": "fr-message", role: "status", text: doneMessage }));
    var actions = el("div", { "class": "fr-actions" });
    if (canResume) {
      var go = el("button", { type: "button", "class": "button button-primary" }, t.resume + ' <span aria-hidden="true">' + (this.form.dir === "rtl" ? "←" : "→") + "</span>");
      go.addEventListener("click", function () {
        var i = self.visibleSteps().map(function (s) { return s.key; }).indexOf(self.resumeStep);
        self.show(Math.max(0, i), true);
      });
      actions.appendChild(go);
      if (!this.link) {
        var again = el("button", { type: "button", "class": "button button-ghost", text: t.restart });
        again.addEventListener("click", function () { store(self.key, null); self.token = ""; self.answers = {}; self.event("start"); self.show(0, true); });
        actions.appendChild(again);
      }
    } else if (!doneMessage || !this.link) {
      var start = el("button", { type: "button", "class": "button button-primary" }, t.start + ' <span aria-hidden="true">' + (this.form.dir === "rtl" ? "←" : "→") + "</span>");
      start.addEventListener("click", function () { self.event("start"); self.show(0, true); });
      actions.appendChild(start);
    }
    box.appendChild(actions);
    this.root.appendChild(box);
  };

  // ---------------------------------------------------------------- rules (same meaning as formbuilder/expr.py)
  Runner.prototype.ev = function (n) {
    var self = this;
    if (!n) return true;
    switch (n.k) {
      case "c": return n.v;
      case "l": return n.v.map(function (x) { return self.ev(x); });
      case "and": for (var i = 0, v = true; i < n.v.length; i++) { v = self.ev(n.v[i]); if (!v) return v; } return v;
      case "or": for (var j = 0, w = false; j < n.v.length; j++) { w = self.ev(n.v[j]); if (w) return w; } return w;
      case "not": return !self.ev(n.v);
      case "if": return self.ev(n.t) ? self.ev(n.a) : self.ev(n.b);
      case "answer": return self.answers[n.v] == null ? "" : self.answers[n.v];
      case "answered": var a = self.answers[n.v]; return !(a == null || a === "" || a === false || (Array.isArray(a) && !a.length));
      case "unknown":
        var f = self.fields[n.v], val = self.answers[n.v];
        if (!f || !f.options) return false;
        var keys = Array.isArray(val) ? val : [val];
        return f.options.some(function (o) { return o.unknown && keys.indexOf(o.key) >= 0; });
      case "cmp":
        var l = self.ev(n.l), r = self.ev(n.r);
        switch (n.op) {
          case "==": return l === r || (Array.isArray(l) && l.indexOf(r) >= 0);
          case "!=": return !(l === r || (Array.isArray(l) && l.indexOf(r) >= 0));
          case "in": return Array.isArray(l) ? l.some(function (x) { return (r || []).indexOf(x) >= 0; }) : (Array.isArray(r) || typeof r === "string") && r.indexOf(l) >= 0;
          case "not in": return !(Array.isArray(l) ? l.some(function (x) { return (r || []).indexOf(x) >= 0; }) : (Array.isArray(r) || typeof r === "string") && r.indexOf(l) >= 0);
          case "<": return Number(l) < Number(r);
          case "<=": return Number(l) <= Number(r);
          case ">": return Number(l) > Number(r);
          case ">=": return Number(l) >= Number(r);
        }
        return false;
    }
    return true;
  };
  Runner.prototype.visibleSteps = function () {
    var self = this;
    return this.form.steps.filter(function (s) { return self.ev(s["if"]); });
  };

  // ---------------------------------------------------------------- a step
  Runner.prototype.show = function (i, moveFocus) {
    var self = this, t = this.t, steps = this.visibleSteps();
    this.index = Math.max(0, Math.min(i, steps.length - 1));
    var step = steps[this.index], last = this.index === steps.length - 1;
    this.root.innerHTML = "";
    var pct = Math.round(100 * (this.index + 1) / steps.length);
    var head = el("div", { "class": "fr-progress-wrap" });
    head.appendChild(el("p", { "class": "fr-progress-text", "aria-hidden": "true", text: t.step.replace("{i}", this.index + 1).replace("{n}", steps.length) + (step.title ? " · " + step.title.replace(/<[^>]+>/g, "") : "") }));
    var bar = el("div", { "class": "fr-progress", role: "progressbar", "aria-label": t.progress, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct), "aria-valuetext": t.step.replace("{i}", this.index + 1).replace("{n}", steps.length) });
    bar.appendChild(el("span", { style: "width:" + pct + "%" }));
    head.appendChild(bar);
    this.root.appendChild(head);

    var form = el("form", { "class": "fr-step fr-enter", novalidate: true, "aria-labelledby": "fr-title-" + step.key });
    var h = el("h2", { "class": "fr-step-title", id: "fr-title-" + step.key, tabindex: "-1" }, step.title || "");
    form.appendChild(h);
    if (step.intro) form.appendChild(el("p", { "class": "fr-step-intro" }, step.intro));
    step.fields.forEach(function (f) { form.appendChild(self.field(f)); });
    if (last && !this.link && !this.preview) {
      form.appendChild(el("div", { "class": "fr-trap", "aria-hidden": "true" }, '<label>Leave this field empty<input name="website" type="text" tabindex="-1" autocomplete="off"></label>'));
      form.appendChild(el("div", { "class": "ts-box", "data-ts": true }));
    }
    var status = el("p", { "class": "fr-status", role: "alert", tabindex: "-1", hidden: true });
    form.appendChild(status);
    var nav = el("div", { "class": "fr-actions" });
    if (this.index > 0) {
      var back = el("button", { type: "button", "class": "button button-ghost" }, '<span aria-hidden="true">' + (this.form.dir === "rtl" ? "→" : "←") + "</span> " + t.back);
      back.addEventListener("click", function () { self.collect(form); self.show(self.index - 1, true); });
      nav.appendChild(back);
    }
    var next = el("button", { type: "submit", "class": "button button-primary" }, (last ? t.submit : t.next) + ' <span aria-hidden="true">' + (this.form.dir === "rtl" ? "←" : "→") + "</span>");
    nav.appendChild(next);
    form.appendChild(nav);
    form.addEventListener("change", function () { self.collect(form); self.refresh(form); });
    form.addEventListener("input", function (e) { if (e.target.type !== "radio" && e.target.type !== "checkbox") self.collect(form); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      self.collect(form);
      if (!self.validate(form)) return;
      if (last) return self.send(form, next, status);
      self.save(steps[self.index + 1] && steps[self.index + 1].key);
      self.show(self.index + 1, true);
    });
    this.root.appendChild(form);
    this.refresh(form);
    if (last && window.TechntingCMSTurnstile && !this.link && !this.preview) window.TechntingCMSTurnstile.mount(form);
    this.event("step", this.index + 1);
    if (moveFocus) {
      var top = this.root.getBoundingClientRect().top + window.pageYOffset - 96;
      if (window.pageYOffset > top) window.scrollTo({ top: top, behavior: reduce ? "auto" : "smooth" });
      h.focus({ preventScroll: true });
    }
  };

  Runner.prototype.field = function (f) {
    var self = this, t = this.t, id = "fr-" + f.key, wrap = el("div", { "class": "fr-field fr-" + f.type, "data-key": f.key });
    var req = f.required && f.type !== "info" ? ' <span class="fr-req" aria-hidden="true">*</span>' : "";
    var helpId = f.help ? id + "-help" : null, errId = id + "-err", textsId = id + "-texts";
    var described = [helpId, textsId, errId].filter(Boolean).join(" ");
    var value = this.answers[f.key];
    if (f.type === "hidden") { wrap.hidden = true; return wrap; }
    if (f.type === "info") { wrap.appendChild(el("div", { "class": "fr-info" }, f.label)); return wrap; }
    if (f.type === "radio" || f.type === "checkbox" || f.type === "scale") {
      var fs = el("fieldset", { "aria-describedby": described, "aria-required": f.required ? "true" : false });
      fs.appendChild(el("legend", { "class": "fr-label" }, f.label + req));
      if (f.help) fs.appendChild(el("p", { "class": "fr-help", id: helpId }, f.help));
      fs.appendChild(el("div", { "class": "fr-texts", id: textsId }));
      var list = el("div", { "class": "fr-options" + (f.type === "scale" ? " fr-scale" : "") });
      var opts = f.type === "scale" ? this.scaleOptions(f) : f.options;
      opts.forEach(function (o, n) {
        var oid = id + "-" + n, type = f.type === "checkbox" ? "checkbox" : "radio";
        var checked = Array.isArray(value) ? value.indexOf(o.key) >= 0 : String(value) === String(o.key);
        var lab = el("label", { "class": "fr-opt" + (o.unknown ? " fr-opt-unknown" : ""), "for": oid, "data-opt": o.key });
        lab.appendChild(el("input", { type: type, id: oid, name: f.key, value: o.key, checked: checked }));
        lab.appendChild(el("span", { "class": "fr-opt-text" }, o.label));
        list.appendChild(lab);
      });
      fs.appendChild(list);
      if (f.type === "scale" && (f.min_label || f.max_label)) fs.appendChild(el("p", { "class": "fr-scale-ends" }, "<span>" + (f.min_label || "") + "</span><span>" + (f.max_label || "") + "</span>"));
      fs.appendChild(el("p", { "class": "fr-err", id: errId, hidden: true }));
      wrap.appendChild(fs);
      return wrap;
    }
    if (f.type === "consent") {
      var lab2 = el("label", { "class": "fr-consent", "for": id });
      lab2.appendChild(el("input", { type: "checkbox", id: id, name: f.key, checked: value === true, "aria-describedby": described, "aria-required": f.required ? "true" : false }));
      lab2.appendChild(el("span", {}, f.label + req));
      wrap.appendChild(lab2);
      if (f.help) wrap.appendChild(el("p", { "class": "fr-help", id: helpId }, f.help));
      wrap.appendChild(el("div", { "class": "fr-texts", id: textsId }));
      wrap.appendChild(el("p", { "class": "fr-err", id: errId, hidden: true }));
      return wrap;
    }
    wrap.appendChild(el("label", { "class": "fr-label", "for": id }, f.label + req));
    if (f.help) wrap.appendChild(el("p", { "class": "fr-help", id: helpId }, f.help));
    var input;
    if (f.type === "select") {
      input = el("select", { id: id, name: f.key, "aria-describedby": described, "aria-required": f.required ? "true" : false });
      input.appendChild(el("option", { value: "", text: t.choose }));
      f.options.forEach(function (o) {
        var op = el("option", { value: o.key, selected: value === o.key });
        op.textContent = o.label.replace(/<[^>]+>/g, "");
        input.appendChild(op);
      });
    } else if (f.type === "textarea") {
      input = el("textarea", { id: id, name: f.key, rows: "5", maxlength: f.max_length || 4000, "aria-describedby": described, "aria-required": f.required ? "true" : false });
      input.value = value || "";
    } else {
      var kind = { email: "email", phone: "tel" }[f.type] || "text";
      var auto = f.autocomplete || { email: "email", phone: "tel" }[f.type] || false;
      input = el("input", { id: id, name: f.key, type: kind, autocomplete: auto, maxlength: f.max_length || (f.type === "email" ? 254 : f.type === "phone" ? 40 : 300),
        dir: (f.type === "email" || f.type === "phone") ? "ltr" : "auto", inputmode: f.type === "phone" ? "tel" : false,
        placeholder: f.placeholder || false, "aria-describedby": described, "aria-required": f.required ? "true" : false });
      input.value = value || "";
    }
    wrap.appendChild(input);
    wrap.appendChild(el("div", { "class": "fr-texts", id: textsId }));
    wrap.appendChild(el("p", { "class": "fr-err", id: errId, hidden: true }));
    return wrap;
  };

  Runner.prototype.scaleOptions = function (f) {
    var out = [], lo = Number(f.min || 0), hi = Number(f.max || 10), st = Number(f.step || 1);
    for (var v = lo; v <= hi; v += st) out.push({ key: String(v), label: String(v) });
    return out;
  };

  Runner.prototype.collect = function (form) {
    var self = this;
    form.querySelectorAll(".fr-field").forEach(function (w) {
      var key = w.getAttribute("data-key"), f = self.fields[key];
      if (!f || f.type === "info" || f.type === "hidden") return;
      if (f.type === "radio" || f.type === "scale") {
        var c = w.querySelector("input:checked");
        if (c) self.answers[key] = f.type === "scale" ? Number(c.value) : c.value; else delete self.answers[key];
      } else if (f.type === "checkbox") {
        self.answers[key] = Array.prototype.map.call(w.querySelectorAll("input:checked"), function (i) { return i.value; });
      } else if (f.type === "consent") {
        self.answers[key] = w.querySelector("input").checked;
      } else {
        var v = w.querySelector("input, select, textarea").value.trim();
        if (v) self.answers[key] = v; else delete self.answers[key];
      }
    });
  };

  Runner.prototype.refresh = function (form) {
    var self = this;
    form.querySelectorAll(".fr-field").forEach(function (w) {
      var f = self.fields[w.getAttribute("data-key")];
      if (!f || f.type === "hidden") return;
      var shown = self.ev(f["if"]);
      w.hidden = !shown;
      (f.options || []).forEach(function (o, n) {
        var lab = w.querySelector('[data-opt="' + (window.CSS && CSS.escape ? CSS.escape(o.key) : o.key) + '"]');
        if (!lab) {
          var op = w.querySelector('option[value="' + o.key + '"]');
          if (op) { op.hidden = op.disabled = !self.ev(o["if"]); if (op.disabled && op.selected) { op.selected = false; delete self.answers[f.key]; } }
          return;
        }
        var ok = self.ev(o["if"]);
        lab.hidden = !ok;
        var inp = lab.querySelector("input");
        inp.disabled = !ok;
        if (!ok && inp.checked) { inp.checked = false; self.collect(form); }
      });
      var box = w.querySelector(".fr-texts");
      if (box) {
        var html = (f.texts || []).filter(function (x) { return self.ev(x["if"]); }).map(function (x) { return '<p class="fr-text">' + x.html + "</p>"; }).join("");
        if (box.innerHTML !== html) box.innerHTML = html;
      }
    });
  };

  Runner.prototype.validate = function (form) {
    var self = this, first = null, t = this.t;
    form.querySelectorAll(".fr-field").forEach(function (w) {
      var f = self.fields[w.getAttribute("data-key")], err = w.querySelector(".fr-err");
      if (!f || !err) return;
      var v = self.answers[f.key], msg = "";
      if (!w.hidden) {
        var empty = v == null || v === "" || v === false || (Array.isArray(v) && !v.length);
        if (f.required && empty) msg = t.required;
        else if (!empty && f.type === "email" && !EMAIL.test(v)) msg = t.email;
        else if (!empty && f.type === "phone" && (!/^[+()0-9 .-]{4,40}$/.test(v) || v.replace(/\D/g, "").length < 6)) msg = t.phone;
      }
      self.mark(w, msg);
      if (msg && !first) first = w;
    });
    if (first) {
      var target = first.querySelector("input:not([disabled]), select, textarea");
      if (target) target.focus();
    }
    return !first;
  };

  Runner.prototype.mark = function (w, msg) {
    var err = w.querySelector(".fr-err");
    err.textContent = msg || "";
    err.hidden = !msg;
    w.classList.toggle("fr-has-error", Boolean(msg));
    w.querySelectorAll("input, select, textarea, fieldset").forEach(function (i) { if (msg) i.setAttribute("aria-invalid", "true"); else i.removeAttribute("aria-invalid"); });
  };

  Runner.prototype.save = function (stepKey) {
    var self = this;
    if (this.preview) return;
    this.post("save", { token: this.token, answers: this.answers, step: stepKey || "" }).then(function (r) {
      if (r.ok && r.token && !self.link) { self.token = r.token; store(self.key, r.token); }
    }).catch(function () { /* the next save will try again */ });
  };

  Runner.prototype.send = function (form, button, status) {
    var self = this, t = this.t;
    var turn = form.querySelector('[name="cf-turnstile-response"]');
    if (window.TechntingCMSTurnstile && !this.link && !this.preview && !window.TechntingCMSTurnstile.ready(form)) {
      window.TechntingCMSTurnstile.mount(form);
      status.textContent = window.TechntingCMSTurnstile.failed() ? t.error : t.check;
      status.hidden = false; status.focus();
      return;
    }
    var trap = form.querySelector('[name="website"]');
    button.disabled = true;
    var label = button.innerHTML;
    button.textContent = t.sending;
    status.hidden = true;
    this.post("submit", { token: this.token, answers: this.answers, page: location.pathname,
      website: trap ? trap.value : "", "cf-turnstile-response": turn ? turn.value : "" })
      .then(function (r) {
        if (r.ok) { if (!self.link) store(self.key, null); return self.done(r); }
        button.disabled = false; button.innerHTML = label;
        if (window.TechntingCMSTurnstile) window.TechntingCMSTurnstile.reset(form);
        if (r.errors) {
          var keys = Object.keys(r.errors), steps = self.visibleSteps();
          for (var i = 0; i < steps.length; i++) {
            if (steps[i].fields.some(function (f) { return keys.indexOf(f.key) >= 0; })) {
              if (i !== self.index) self.show(i, true);
              var f2 = self.root.querySelector("form");
              keys.forEach(function (k) { var w = f2.querySelector('[data-key="' + k + '"]'); if (w) self.mark(w, r.errors[k] === "required" ? t.required : t.invalid); });
              break;
            }
          }
        }
        var st = self.root.querySelector(".fr-status");
        st.textContent = r.message || t.error; st.hidden = false; st.focus();
      })
      .catch(function () { button.disabled = false; button.innerHTML = label; status.textContent = t.error; status.hidden = false; status.focus(); });
  };

  Runner.prototype.done = function (r) {
    this.root.innerHTML = "";
    var box = el("div", { "class": "fr-results fr-enter", tabindex: "-1", "aria-live": "polite" });
    box.innerHTML = r.html || '<p class="fr-thanks">' + (r.thank_you || "") + "</p>";
    this.root.appendChild(box);
    var top = this.root.getBoundingClientRect().top + window.pageYOffset - 96;
    window.scrollTo({ top: top, behavior: reduce ? "auto" : "smooth" });
    var h = box.querySelector("h1, h2") || box;
    if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
    h.focus({ preventScroll: true });
    var bars = box.querySelectorAll(".fr-score-bar span");
    if (!reduce) bars.forEach(function (b) { var w = b.style.width; b.style.width = "0"; requestAnimationFrame(function () { setTimeout(function () { b.style.width = w; }, 60); }); });
  };

  function boot() {
    document.querySelectorAll("[data-form-runner]").forEach(function (root) {
      if (!root.__runner) root.__runner = new Runner(root);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
