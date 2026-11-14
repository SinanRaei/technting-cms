(function () {
  "use strict";

  document.documentElement.classList.add("js");
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var header = document.querySelector(".site-header");
  var menuButton = document.querySelector(".menu-toggle");
  var nav = document.getElementById("primary-nav");

  function setMenu(open) {
    if (!menuButton || !nav) return;
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.querySelector(".sr-only").textContent = menuButton.getAttribute(open ? "data-close-label" : "data-open-label");
    nav.classList.toggle("is-open", open);
    if (header) header.classList.toggle("menu-open", open);
  }

  if (menuButton && nav) {
    menuButton.addEventListener("click", function () {
      setMenu(menuButton.getAttribute("aria-expanded") !== "true");
    });
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) setMenu(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        setMenu(false);
        menuButton.focus();
      }
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 1024) setMenu(false);
    }, { passive: true });
  }

  // a hairline under the header once the page has scrolled
  if (header) {
    var onScroll = function () { header.classList.toggle("has-scrolled", window.scrollY > 8); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Cloudflare Turnstile ("are you human") on the website forms, when Technting Shield has it on (<html data-turnstile>).
  // The script loads only when someone starts a form; each [data-ts] box gets its own widget, reset after each send.
  var tsKey = document.documentElement.getAttribute("data-turnstile");
  var tsQueue = [];
  var tsState = "";  // "", "loading", "ready", "failed"
  window.__technting_cmsTs = function () {
    tsState = "ready";
    tsQueue.splice(0).forEach(function (fn) { fn(); });
  };
  function tsLoad(fn) {
    if (tsState === "ready") return fn();
    tsQueue.push(fn);
    if (tsState) return;
    tsState = "loading";
    var s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=__technting_cmsTs";
    s.async = true;
    s.onerror = function () { tsState = "failed"; };
    document.head.appendChild(s);
  }
  var turnstile = window.TechntingCMSTurnstile = {
    on: Boolean(tsKey),
    failed: function () { return tsState === "failed"; },  // script blocked or unreachable
    mount: function (form) {
      var box = tsKey && form && form.querySelector("[data-ts]");
      if (!box || box.getAttribute("data-ts-id")) return;
      box.setAttribute("data-ts-id", "pending");
      tsLoad(function () {
        box.setAttribute("data-ts-id", window.turnstile.render(box, {
          sitekey: tsKey, theme: "light", size: "flexible", language: document.documentElement.lang || "auto"
        }));
      });
    },
    ready: function (form) {
      if (!tsKey) return true;
      var input = form.querySelector('[name="cf-turnstile-response"]');
      return Boolean(input && input.value);
    },
    reset: function (form) {
      var box = form && form.querySelector("[data-ts]");
      var id = box && box.getAttribute("data-ts-id");
      if (id && id !== "pending" && window.turnstile) window.turnstile.reset(id);
    }
  };
  if (tsKey) {
    document.addEventListener("focusin", function (event) {
      var form = event.target.closest && event.target.closest("form");
      if (form && form.querySelector("[data-ts]")) turnstile.mount(form);
    });
  }

  var contactDialog = document.getElementById("contact-dialog");
  var contactForm = document.getElementById("contact-form");
  var contactAvailability = document.getElementById("contact-availability");
  var contactStatus = document.getElementById("contact-status");
  var contactSuccess = document.getElementById("contact-success");
  var contactSubmit = document.getElementById("contact-submit");
  var contactReady = false;

  function msg(name) {
    var d = contactDialog && contactDialog.dataset;
    return (d && d["msg" + name.charAt(0).toUpperCase() + name.slice(1)]) || "";
  }

  if (contactDialog && contactForm && typeof contactDialog.showModal === "function" && window.fetch) {
    function setAvailability(ready) {
      contactReady = ready;
      contactSubmit.disabled = !ready;
      contactAvailability.classList.toggle("is-ready", ready);
      if (ready) { contactAvailability.textContent = msg("ready"); }
      else { contactAvailability.innerHTML = msg("paused"); }
    }

    function checkAvailability() {
      contactReady = false;
      contactSubmit.disabled = true;
      contactAvailability.textContent = msg("checking");
      fetch("/api/contact/status", { cache: "no-store", credentials: "same-origin" })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (result) { setAvailability(Boolean(result && result.available)); })
        .catch(function () { setAvailability(false); });
    }

    Array.prototype.forEach.call(document.querySelectorAll("[data-contact-open]"), function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        if (contactDialog.open) return;
        contactForm.hidden = false;
        contactSuccess.hidden = true;
        contactStatus.hidden = true;
        contactDialog.showModal();
        turnstile.mount(contactForm);
        checkAvailability();
      });
    });

    Array.prototype.forEach.call(contactDialog.querySelectorAll("[data-contact-close]"), function (button) {
      button.addEventListener("click", function () { contactDialog.close(); });
    });
    contactDialog.addEventListener("click", function (event) {
      if (event.target === contactDialog) contactDialog.close();
    });

    contactForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!contactReady || !contactForm.reportValidity()) return;
      if (!turnstile.ready(contactForm)) {
        turnstile.mount(contactForm);
        contactStatus.textContent = turnstile.failed() ? msg("error") : msg("check");
        contactStatus.hidden = false;
        return;
      }
      contactSubmit.disabled = true;
      contactSubmit.textContent = msg("sending");
      contactStatus.hidden = true;
      var payload = Object.fromEntries(new FormData(contactForm).entries());
      payload.source = "dialog";
      payload.page = window.location.pathname;
      payload.lang = document.documentElement.lang === "ar" ? "ar" : "en";
      fetch("/api/contact", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (response) {
        return response.json().then(function (result) { return { ok: response.ok, result: result }; });
      }).then(function (outcome) {
        if (!outcome.ok || !outcome.result.ok) throw new Error(outcome.result.message || msg("error"));
        contactForm.reset();
        contactForm.hidden = true;
        contactSuccess.hidden = false;
        contactSuccess.querySelector("h3").focus();
      }).catch(function (error) {
        contactStatus.textContent = error.message || msg("error");
        contactStatus.hidden = false;
        contactStatus.focus();
        checkAvailability();
      }).finally(function () {
        turnstile.reset(contactForm);
        contactSubmit.textContent = msg("send");
        contactSubmit.disabled = !contactReady;
      });
    });
  }

  // Inline enquiry forms (service pages, contact page, end of articles): same endpoint and checks as the dialog.
  Array.prototype.forEach.call(document.querySelectorAll("[data-enquiry]"), function (box) {
    var form = box.querySelector("[data-enquiry-form]");
    var status = form && form.querySelector(".contact-status");
    var done = box.querySelector(".enquiry-success");
    var button = form && form.querySelector("[type=submit]");
    if (!form || !status || !done || !button || !window.fetch) return;
    var label = button.innerHTML;
    var busy = false;

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (busy || !form.reportValidity()) return;
      if (!turnstile.ready(form)) {
        turnstile.mount(form);
        status.textContent = turnstile.failed() ? box.dataset.msgError : box.dataset.msgCheck;
        status.hidden = false;
        return;
      }
      busy = true;
      button.disabled = true;
      button.textContent = box.dataset.msgSending;
      status.hidden = true;
      var payload = Object.fromEntries(new FormData(form).entries());
      payload.page = window.location.pathname;
      payload.lang = document.documentElement.lang === "ar" ? "ar" : "en";
      fetch("/api/contact", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (result) { return { ok: response.ok, result: result }; });
      }).then(function (outcome) {
        if (!outcome.ok || !outcome.result.ok) throw new Error(outcome.result.message || box.dataset.msgError);
        form.reset();
        form.hidden = true;
        done.hidden = false;
        done.querySelector("h3").focus();
      }).catch(function (error) {
        // a network failure gives a browser message in English; show ours instead
        status.textContent = (error && error.message && !(error instanceof TypeError)) ? error.message : box.dataset.msgError;
        status.hidden = false;
        status.focus();
      }).finally(function () {
        turnstile.reset(form);
        busy = false;
        button.disabled = false;
        button.innerHTML = label;
      });
    });

    var again = done.querySelector("[data-enquiry-again]");
    if (again) again.addEventListener("click", function () {
      done.hidden = true;
      form.hidden = false;
      form.querySelector("input[name=name]").focus();
    });

    // "Ask about this service" buttons jump to the form with that service chosen
    Array.prototype.forEach.call(document.querySelectorAll("[data-enquire]"), function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        var select = form.querySelector("select[name=service]");
        var code = link.getAttribute("data-enquire");
        if (select && code && select.querySelector('option[value="' + code + '"]')) select.value = code;
        done.hidden = true;
        form.hidden = false;
        box.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "start" });
        form.querySelector("input[name=name]").focus({ preventScroll: true });
        if (window.history && history.replaceState) history.replaceState(null, "", "#enquire");
      });
    });
  });

  // Motion (see "motion system" in theme.css). Reveals: items entering together are staggered through --rd;
  // .is-done afterwards hands each element its own hover transitions back. [data-inview] gets .is-in.
  var revealItems = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  var inviewItems = Array.prototype.slice.call(document.querySelectorAll("[data-inview]"));
  function settle(item) { item.classList.add("is-visible", "is-done"); }
  if ("IntersectionObserver" in window && !reducedMotion.matches) {
    var revealObserver = new IntersectionObserver(function (entries, observer) {
      var batch = 0;
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var item = entry.target;
        observer.unobserve(item);
        if (!item.classList.contains("reveal")) { item.classList.add("is-in"); return; }
        var delay = Math.min(batch, 6) * 80;
        batch += 1;
        item.style.setProperty("--rd", delay + "ms");
        item.classList.add("is-visible");
        setTimeout(function () { item.classList.add("is-done"); item.style.removeProperty("--rd"); }, delay + 1700);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -24px 0px" });
    revealItems.concat(inviewItems).forEach(function (item) { revealObserver.observe(item); });
  } else {
    revealItems.forEach(settle);
    inviewItems.forEach(function (item) { item.classList.add("is-in"); });
  }

  // Card spotlight: a soft Electric light follows the pointer (--mx/--my), only with a mouse and full motion.
  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  if (finePointer.matches && !reducedMotion.matches) {
    var spotCards = ".card-link, .feature, .post-card, .plan, .post-svc";
    document.addEventListener("pointermove", function (event) {
      if (event.pointerType !== "mouse" || !event.target.closest) return;
      var card = event.target.closest(spotCards);
      if (!card) return;
      var r = card.getBoundingClientRect();
      card.style.setProperty("--mx", Math.round(event.clientX - r.left) + "px");
      card.style.setProperty("--my", Math.round(event.clientY - r.top) + "px");
    }, { passive: true });
  }

  // Scroll progress line: CSS scroll timeline where supported, otherwise this light fallback.
  var progress = document.querySelector(".scroll-progress");
  if (progress && !reducedMotion.matches && !(window.CSS && CSS.supports && CSS.supports("animation-timeline: scroll()"))) {
    var ticking = false;
    var setProgress = function () {
      ticking = false;
      var max = document.documentElement.scrollHeight - window.innerHeight;
      progress.style.setProperty("--p", max > 0 ? Math.min(1, window.scrollY / max).toFixed(4) : "0");
    };
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(setProgress); }
    }, { passive: true });
    setProgress();
  }
})();
