/* Technting CMS editor: schema-driven fields, block editor, media picker. No dependencies. */
(function () {
  "use strict";
  var CFG = window.TECHNTING_CMS || {};
  var G = (window.TechntingCMS = {dirty: false});
  var UI = CFG.ui || (function () { var n = document.getElementById("cms-ui"); try { return n ? JSON.parse(n.textContent) : {}; } catch (x) { return {}; } })();
  function T(x) { return (UI.t || {})[x] || x; }
  function L(x) { return (UI.labels || {})[x] || x; }
  G.T = T; G.L = L;

  // ------------------------------------------------------------ dom helpers
  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "on") Object.keys(v).forEach(function (ev) { n.addEventListener(ev, v[ev]); });
      else if (k === "text") n.textContent = v;
      else if (k === "html") n.innerHTML = v;
      else n.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) { if (c !== null && c !== undefined) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  G.el = el;
  function touch() { G.dirty = true; }
  function uid() { return Math.random().toString(16).slice(2, 10); }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  // ------------------------------------------------------------ remote data
  var entryCache = {};
  function entryOptions(coll) {
    if (!entryCache[coll]) {
      entryCache[coll] = fetch(CFG.entriesApi.replace("COLL", coll), {credentials: "same-origin"})
        .then(function (r) { return r.json(); }).then(function (d) { return d.items || []; });
    }
    return entryCache[coll];
  }

  // ------------------------------------------------------------ fields
  var renderers = {};

  function emptyValue(f) {
    if (f.default !== undefined) return clone(f.default);
    switch (f.type) {
      case "link": return {label: "", url: ""};
      case "repeater": case "entries": return [];
      case "bool": return false;
      case "image": case "number": return null;
      default: return "";
    }
  }

  function fieldGroup(container, fields, data, opts) {
    opts = opts || {};
    var getters = {};
    data = data || {};
    fields.forEach(function (f) {
      var value = data[f.name] !== undefined ? data[f.name] : emptyValue(f);
      var r = renderers[f.type] || renderers.text;
      var wrap = el("div", {class: "f", style: "margin-bottom:12px"});
      if (f.type !== "bool") wrap.appendChild(el("span", {class: "flabel"}, [((document.documentElement.lang === "ar" && f.label_ar) || L(f.label)) + (f.required ? " *" : "")]));
      var api = r(wrap, f, value, f.dir ? Object.assign({}, opts, {dir: f.dir}) : opts);
      if (f.help) wrap.appendChild(el("div", {class: "help"}, [(document.documentElement.lang === "ar" && f.help_ar) || L(f.help)]));
      container.appendChild(wrap);
      getters[f.name] = api;
    });
    return {
      value: function () {
        var out = {};
        Object.keys(getters).forEach(function (k) { out[k] = getters[k].value(); });
        return out;
      }
    };
  }
  G.fieldGroup = fieldGroup;

  renderers.text = function (wrap, f, value, opts) {
    var i = el("input", {type: "text", value: value || "", dir: opts.dir, on: {input: touch}});
    wrap.appendChild(i);
    return {value: function () { return i.value; }, input: i};
  };
  renderers.secret = function (wrap, f, value) {
    // saved keys never come back to the browser: leave the field empty to keep the saved one
    var saved = value === "__saved__";
    var i = f.multiline ? el("textarea", {dir: "ltr", rows: 3, spellcheck: "false", autocomplete: "off", on: {input: touch}})
                        : el("input", {type: "password", value: "", dir: "ltr", autocomplete: "new-password", on: {input: touch}});
    if (saved) i.placeholder = T("Saved. Type a new one to replace it.");
    wrap.appendChild(i);
    if (f.multiline) {  // a key file: paste it or choose it
      var file = el("input", {type: "file", accept: ".json,application/json", style: "margin-top:6px"});
      file.addEventListener("change", function () { if (file.files[0]) file.files[0].text().then(function (t) { i.value = t; touch(); }); });
      wrap.appendChild(file);
    }
    var rm = el("input", {type: "checkbox", on: {change: touch}});
    if (saved) wrap.appendChild(el("label", {class: "help", style: "display:flex;gap:6px;align-items:center"}, [rm, T("Remove the saved key")]));
    return {value: function () { return rm.checked ? "__remove__" : i.value.trim(); }};
  };
  renderers.url = function (wrap, f, value) {
    var i = el("input", {type: "text", value: value || "", dir: "ltr", placeholder: "https:// or /path/", on: {input: touch}});
    wrap.appendChild(i);
    return {value: function () { return i.value.trim(); }};
  };
  renderers.date = function (wrap, f, value) {
    var i = el("input", {type: "date", value: value || "", dir: "ltr", on: {input: touch}});
    if (!value && f.default_today) { i.value = new Date().toISOString().slice(0, 10); }
    wrap.appendChild(i);
    return {value: function () { return i.value; }};
  };
  renderers.number = function (wrap, f, value) {
    var i = el("input", {type: "number", step: "any", value: value === null || value === undefined ? "" : value, dir: "ltr", on: {input: touch}});
    wrap.appendChild(i);
    return {value: function () { return i.value === "" ? null : Number(i.value); }};
  };
  renderers.textarea = function (wrap, f, value, opts) {
    var t = el("textarea", {dir: opts.dir, rows: 3, on: {input: touch}});
    t.value = value || "";
    wrap.appendChild(t);
    return {value: function () { return t.value; }, input: t};
  };
  renderers.code = function (wrap, f, value) {
    var t = el("textarea", {class: "code", dir: "ltr", spellcheck: "false", on: {input: touch}});
    t.value = value || "";
    if (!CFG.isAdmin) { t.disabled = true; wrap.appendChild(el("div", {class: "help"}, [T("Only administrators can edit custom HTML.")])); }
    wrap.appendChild(t);
    return {value: function () { return t.value; }};
  };
  renderers.bool = function (wrap, f, value) {
    var c = el("input", {type: "checkbox", on: {change: touch}});
    c.checked = !!value;
    wrap.appendChild(el("label", {style: "display:flex;gap:6px;align-items:center;font-weight:700"}, [c, (document.documentElement.lang === "ar" && f.label_ar) || L(f.label)]));
    return {value: function () { return c.checked; }};
  };
  renderers.select = function (wrap, f, value) {
    var s = el("select", {on: {change: touch}}, (f.options || []).map(function (o) {
      return el("option", {value: o, selected: o === value}, [o === "" ? T("(none)") : o]);
    }));
    wrap.appendChild(s);
    return {value: function () { return s.value; }};
  };
  renderers.link = function (wrap, f, value, opts) {
    value = value || {};
    var l = el("input", {type: "text", value: value.label || "", placeholder: T("Text"), dir: opts.dir, on: {input: touch}});
    var u = el("input", {type: "text", value: value.url || "", placeholder: "/page/ or https://", dir: "ltr", on: {input: touch}});
    wrap.appendChild(el("div", {class: "link2"}, [l, u]));
    return {value: function () { return {label: l.value, url: u.value.trim()}; }};
  };
  renderers.richtext = function (wrap, f, value, opts) {
    var area = el("div", {class: "rtc", contenteditable: "true", dir: opts.dir, on: {input: touch}});
    area.innerHTML = value || "";
    function cmd(c, arg) { return function (e) { e.preventDefault(); area.focus(); document.execCommand(c, false, arg); touch(); }; }
    var bar = el("div", {class: "rtb"}, [
      el("button", {type: "button", title: T("Bold"), on: {click: cmd("bold")}}, ["B"]),
      el("button", {type: "button", title: T("Italic"), on: {click: cmd("italic")}, style: "font-style:italic"}, ["I"]),
      el("button", {type: "button", title: T("Heading"), on: {click: cmd("formatBlock", "h2")}}, ["H2"]),
      el("button", {type: "button", title: T("Subheading"), on: {click: cmd("formatBlock", "h3")}}, ["H3"]),
      el("button", {type: "button", title: T("Paragraph"), on: {click: cmd("formatBlock", "p")}}, ["¶"]),
      el("button", {type: "button", title: T("Bulleted list"), on: {click: cmd("insertUnorderedList")}}, ["•"]),
      el("button", {type: "button", title: T("Numbered list"), on: {click: cmd("insertOrderedList")}}, ["1."]),
      el("button", {type: "button", title: T("Link"), on: {click: function (e) {
        e.preventDefault(); var url = prompt(T("Link address (https://, /page/ or mailto:)")); if (url) { area.focus(); document.execCommand("createLink", false, url); touch(); }
      }}}, ["🔗"]),
      el("button", {type: "button", title: T("Image"), on: {click: function (e) {
        e.preventDefault();
        var range = window.getSelection().rangeCount ? window.getSelection().getRangeAt(0) : null;
        mediaPicker("image").then(function (m) {
          if (!m) return;
          area.focus();
          if (range) { var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }
          var alt = ((m.alt || {})[document.documentElement.lang] || m.title || "").replace(/[<>"&]/g, "");
          var src = m.variants_960 || m.url;
          document.execCommand("insertHTML", false, '<img src="' + src + '" alt="' + alt + '" loading="lazy">');
          touch();
        });
      }}}, ["🖼"]),
      el("button", {type: "button", title: T("Remove formatting"), on: {click: cmd("removeFormat")}}, ["⌫"])
    ]);
    wrap.appendChild(el("div", {class: "rt"}, [bar, area]));
    return {value: function () { return area.innerHTML; }};
  };
  function mediaRenderer(kind) {
    return function (wrap, f, value) {
      var current = value ? {id: value} : null;
      var host = el("div");
      wrap.appendChild(host);
      var api = imageField(host, current, function (m) { current = m; touch(); }, kind);
      if (value) fetch(CFG.mediaApi + "?kind=" + kind, {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (d) {
        var m = (d.items || []).filter(function (x) { return String(x.id) === String(value); })[0];
        if (m) api.set(m);
      });
      return {value: function () { return current ? current.id : null; }};
    };
  }
  renderers.image = mediaRenderer("image");
  renderers.video = mediaRenderer("video");
  renderers.entry = function (wrap, f, value) {
    var s = el("select", {on: {change: touch}}, [el("option", {value: ""}, [T("Select…")])]);
    wrap.appendChild(s);
    entryOptions(f.collection).then(function (items) {
      items.forEach(function (it) { s.appendChild(el("option", {value: it.key, selected: it.key === value}, [it.label])); });
      if (value && !items.some(function (it) { return it.key === value; })) s.appendChild(el("option", {value: value, selected: true}, [value + " (" + T("missing") + ")"]));
    });
    return {value: function () { return s.value || (s.options.length <= 1 ? value || "" : ""); }};
  };
  renderers.entries = function (wrap, f, value) {
    var box = el("div", {class: "checks"}, [el("span", {class: "muted small"}, [T("Loading…")])]);
    var selected = (value || []).slice();
    wrap.appendChild(box);
    entryOptions(f.collection).then(function (items) {
      box.innerHTML = "";
      items.forEach(function (it) {
        var c = el("input", {type: "checkbox", on: {change: function () {
          selected = selected.filter(function (k) { return k !== it.key; });
          if (c.checked) selected.push(it.key);
          touch();
        }}});
        c.checked = selected.indexOf(it.key) >= 0;
        box.appendChild(el("label", {}, [c, it.label]));
      });
    });
    return {value: function () { return selected.slice(); }};
  };
  renderers.repeater = function (wrap, f, value, opts) {
    var rows = [];
    var list = el("div", {class: "rows"});
    var rep = el("div", {class: "rep"}, [list]);
    var add = el("button", {type: "button", class: "btn sm", on: {click: function () { addRow(emptyRow()); touch(); }}}, [T("+ Add") + " " + T(f.item_label || "item")]);
    rep.appendChild(el("div", {class: "rf"}, [add]));
    wrap.appendChild(rep);
    function emptyRow() { var o = {}; (f.fields || []).forEach(function (sf) { o[sf.name] = emptyValue(sf); }); return o; }
    function summary(data) {
      var first = (f.fields || []).filter(function (sf) { return ["text", "textarea"].indexOf(sf.type) >= 0; })[0];
      var link = (f.fields || []).filter(function (sf) { return sf.type === "link"; })[0];
      if (first && data[first.name]) return data[first.name];
      if (link && data[link.name] && data[link.name].label) return data[link.name].label;
      var ent = (f.fields || []).filter(function (sf) { return sf.type === "entry"; })[0];
      return ent ? data[ent.name] || "" : "";
    }
    function addRow(data, at) {
      var body = el("div", {class: "rb"});
      var label = el("span", {class: "sp"}, [summary(data) || ""]);
      var row = el("div", {class: "row"});
      var group;
      var head = el("div", {class: "rh"}, [
        el("span", {}, ["#"]), label,
        el("button", {type: "button", class: "btn sm ghost", title: T("Move up"), on: {click: function () { move(row, -1); }}}, ["↑"]),
        el("button", {type: "button", class: "btn sm ghost", title: T("Move down"), on: {click: function () { move(row, 1); }}}, ["↓"]),
        el("button", {type: "button", class: "btn sm ghost danger", title: T("Remove"), on: {click: function () {
          if (!confirm(T("Remove this item?"))) return;
          rows = rows.filter(function (r) { return r.row !== row; }); row.remove(); touch();
        }}}, ["✕"])
      ]);
      row.appendChild(head); row.appendChild(body);
      group = fieldGroup(body, f.fields || [], data, opts);
      body.addEventListener("input", function () { label.textContent = summary(group.value()); });
      var entry = {row: row, group: group};
      if (at === undefined) { rows.push(entry); list.appendChild(row); }
      return entry;
    }
    function move(row, delta) {
      var i = rows.findIndex(function (r) { return r.row === row; });
      var j = i + delta;
      if (j < 0 || j >= rows.length) return;
      var tmp = rows[i]; rows[i] = rows[j]; rows[j] = tmp;
      rows.forEach(function (r) { list.appendChild(r.row); });
      touch();
    }
    (value || []).forEach(function (d) { addRow(d); });
    return {value: function () { return rows.map(function (r) { return r.group.value(); }); }};
  };

  // ------------------------------------------------------------ media picker
  function mediaPicker(kind) {
    kind = kind || "image";
    return new Promise(function (resolve) {
      var chosen = null;
      var grid = el("div", {class: "media-grid"});
      var search = el("input", {type: "search", placeholder: T("Search media"), style: "max-width:280px"});
      var file = el("input", {type: "file", accept: kind === "video" ? "video/mp4,video/webm" : "image/*", multiple: true, style: "display:none"});
      var drop = el("div", {class: "drop"}, [T("Drop images here or "), el("a", {href: "#", on: {click: function (e) { e.preventDefault(); file.click(); }}}, [T("choose files")])]);
      var useBtn = el("button", {type: "button", class: "btn primary", disabled: true}, [T(kind === "video" ? "Use video" : "Use image")]);
      var modal = el("div", {class: "modal"}, [el("div", {class: "box"}, [
        el("div", {class: "hd"}, [T("Media library"), el("span", {style: "flex:1"}), search]),
        el("div", {class: "bd"}, [drop, el("div", {style: "height:12px"}), grid]),
        el("div", {class: "ft"}, [el("button", {type: "button", class: "btn", on: {click: function () { close(null); }}}, [T("Cancel")]), useBtn])
      ])]);
      function close(v) { modal.remove(); resolve(v); }
      useBtn.addEventListener("click", function () { close(chosen); });
      modal.addEventListener("click", function (e) { if (e.target === modal) close(null); });
      function load(q) {
        fetch(CFG.mediaApi + "?kind=" + kind + "&q=" + encodeURIComponent(q || ""), {credentials: "same-origin"})
          .then(function (r) { return r.json(); }).then(function (d) { show(d.items || []); });
      }
      function show(items) {
        grid.innerHTML = "";
        items.forEach(function (m) {
          var b = el("button", {type: "button", class: "mi", on: {click: function () {
            Array.prototype.forEach.call(grid.children, function (c) { c.classList.remove("sel"); });
            b.classList.add("sel"); chosen = m; useBtn.disabled = false;
          }, dblclick: function () { close(m); }}}, [
            el("div", {class: "th", style: m.thumb ? "background-image:url('" + m.thumb + "')" : ""}, [m.thumb ? "" : (m.kind === "video" ? "▶ VIDEO" : "FILE")]),
            el("div", {class: "cap"}, [m.title || m.url])
          ]);
          grid.appendChild(b);
        });
      }
      function upload(files) {
        var fd = new FormData();
        Array.prototype.forEach.call(files, function (f) { fd.append("files", f); });
        drop.textContent = T("Uploading…");
        fetch(CFG.uploadUrl, {method: "POST", body: fd, credentials: "same-origin", headers: {"X-CSRFToken": CFG.csrf}})
          .then(function (r) { return r.json(); }).then(function (d) {
            drop.textContent = (d.errors && d.errors.length) ? d.errors.join(" ") : T("Uploaded.");
            load("");
          });
      }
      file.addEventListener("change", function () { upload(file.files); });
      drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("over"); });
      drop.addEventListener("dragleave", function () { drop.classList.remove("over"); });
      drop.addEventListener("drop", function (e) { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files); });
      var t;
      search.addEventListener("input", function () { clearTimeout(t); t = setTimeout(function () { load(search.value); }, 250); });
      document.body.appendChild(modal);
      modal.appendChild(file);
      load("");
    });
  }
  G.mediaPicker = mediaPicker;

  function imageField(host, media, onChange, kind) {
    kind = kind || "image";
    var prev = el("div", {class: "prev"});
    var name = el("div", {class: "small muted", style: "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis"});
    var pick = el("button", {type: "button", class: "btn sm"}, [T("Choose")]);
    var clear = el("button", {type: "button", class: "btn sm ghost danger"}, [T("Remove")]);
    host.appendChild(el("div", {class: "imgfield"}, [prev, name, pick, clear]));
    function set(m) {
      prev.style.backgroundImage = m && m.thumb ? "url('" + m.thumb + "')" : "";
      prev.textContent = m && !m.thumb && kind === "video" ? "▶" : "";
      name.textContent = m ? (m.title || ("#" + m.id)) : T(kind === "video" ? "No video" : "No image");
      clear.style.display = m ? "" : "none";
    }
    pick.addEventListener("click", function () { mediaPicker(kind).then(function (m) { if (m) { set(m); onChange(m); } }); });
    clear.addEventListener("click", function () { set(null); onChange(null); });
    set(media);
    return {set: set};
  }
  G.imageField = imageField;

  // ------------------------------------------------------------ block editor
  var DEVICES = ["phone", "tablet", "desktop"];
  var DEVICE_LABEL = {phone: "Phone", tablet: "Tablet", desktop: "Desktop"};
  // Brand UI icon rules: 2 px stroke on a 24 px grid, square caps, mitred joins, one square pixel
  var SVG_EYE = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" stroke-linejoin="miter" aria-hidden="true" focusable="false">';
  var EYE = SVG_EYE + '<path d="M2 12c3-5.3 6.3-7 10-7s7 1.7 10 7c-3 5.3-6.3 7-10 7S5 17.3 2 12Z"/><rect x="10.5" y="10.5" width="3" height="3" fill="currentColor" stroke="none"/></svg>';
  var EYE_OFF = SVG_EYE + '<path d="M9 5.4A9.6 9.6 0 0 1 12 5c3.7 0 7 1.7 10 7a19 19 0 0 1-2.6 3.6M6.2 6.9C4.6 8.1 3.3 9.7 2 12c3 5.3 6.3 7 10 7a9.4 9.4 0 0 0 4.6-1.2M4 4l16 16"/></svg>';

  function blockEditor(host, theme, blocks, opts) {
    var items = [];
    var list = el("div", {class: "blocks"});
    host.appendChild(list);
    host.appendChild(el("div", {class: "adder", style: "margin-top:12px"}, [
      el("button", {type: "button", class: "btn", on: {click: function () { palette(items.length); }}}, [T("+ Add block")])
    ]));

    function summaryOf(spec, data) {
      var keys = ["title", "eyebrow", "heading", "body", "code"];
      for (var i = 0; i < keys.length; i++) {
        var v = data[keys[i]];
        if (v) return String(v).replace(/<[^>]+>/g, " ").slice(0, 120);
      }
      return "";
    }

    function make(block, open) {
      var spec = theme.blocks[block.type];
      if (!spec) return null;
      var body = el("div", {class: "bb"});
      var sm = el("span", {class: "bsum"}, [summaryOf(spec, block.data || {})]);
      var card = el("div", {class: "blk" + (open ? "" : " closed")});
      // display settings: hidden from the public site, and the screen sizes it shows on
      var vis = {hidden: block.hidden === true, devices: (block.devices && block.devices.length ? block.devices : DEVICES).slice()};
      var badge = el("span", {class: "bvis"});
      var eye = el("button", {type: "button", class: "btn sm ghost eye", on: {click: function (e) {
        e.stopPropagation(); vis.hidden = !vis.hidden; paintVis(); touch();
      }}});
      function paintVis() {
        card.classList.toggle("is-hidden", vis.hidden);
        eye.innerHTML = vis.hidden ? EYE_OFF : EYE;
        eye.title = vis.hidden ? T("Hidden from the site. Click to show it") : T("Shown on the site. Click to hide it");
        eye.setAttribute("aria-pressed", vis.hidden ? "true" : "false");
        var parts = [];
        if (vis.hidden) parts.push(T("Hidden"));
        if (vis.devices.length < DEVICES.length) parts.push(vis.devices.map(function (d) { return T(DEVICE_LABEL[d]); }).join(" · ") + " " + T("only"));
        badge.textContent = parts.join(" · ");
        badge.style.display = parts.length ? "" : "none";
        chips.forEach(function (c) { c.input.checked = vis.devices.indexOf(c.device) >= 0; });
      }
      var chips = DEVICES.map(function (d) {
        var input = el("input", {type: "checkbox", on: {change: function () {
          var on = vis.devices.filter(function (x) { return x !== d; });
          if (input.checked) on.push(d);
          on = DEVICES.filter(function (x) { return on.indexOf(x) >= 0; });
          if (!on.length) { input.checked = true; alert(T("A section must show on at least one screen size. To remove it from the site, use Hide.")); return; }
          vis.devices = on; paintVis(); touch();
        }}});
        return {device: d, input: input, label: el("label", {class: "vchip"}, [input, " " + T(DEVICE_LABEL[d])])};
      });
      var head = el("div", {class: "bh"}, [
        el("span", {class: "handle", title: T("Drag to reorder"), draggable: "true"}, ["⠿"]),
        el("span", {class: "ic"}, [L(spec.label).charAt(0)]),
        el("span", {class: "nm"}, [L(spec.label)]), badge, sm,
        eye,
        el("button", {type: "button", class: "btn sm ghost", title: T("Move up"), on: {click: function (e) { e.stopPropagation(); move(card, -1); }}}, ["↑"]),
        el("button", {type: "button", class: "btn sm ghost", title: T("Move down"), on: {click: function (e) { e.stopPropagation(); move(card, 1); }}}, ["↓"]),
        el("button", {type: "button", class: "btn sm ghost", title: T("Duplicate"), on: {click: function (e) {
          e.stopPropagation(); var i = index(card); insert(Object.assign({id: uid(), type: block.type, data: entry.group.value()}, entry.vis()), i + 1, true); touch();
        }}}, ["⧉"]),
        el("button", {type: "button", class: "btn sm ghost", title: T("Add block below"), on: {click: function (e) { e.stopPropagation(); palette(index(card) + 1); }}}, ["+"]),
        el("button", {type: "button", class: "btn sm ghost danger", title: T("Delete block"), on: {click: function (e) {
          e.stopPropagation(); if (!confirm(T("Delete this block?"))) return;
          items.splice(index(card), 1); card.remove(); touch();
        }}}, ["✕"])
      ]);
      head.addEventListener("click", function () { card.classList.toggle("closed"); });
      card.appendChild(head); card.appendChild(body);
      body.appendChild(el("div", {class: "vrow"}, [el("span", {class: "vlabel"}, [T("Show on:")])].concat(chips.map(function (c) { return c.label; }))));
      paintVis();
      if (spec.source && (UI.collections || {})[spec.source]) {
        var c = UI.collections[spec.source];
        body.appendChild(el("div", {class: "msg info", style: "margin-bottom:12px"}, [
          T("This block shows records from") + " «" + L(c.label) + "». " + T("To change names, photos or texts, edit them there:") + " ",
          el("a", {href: c.url, target: "_blank", rel: "noopener"}, [L(c.label) + " ↗"])]));
      }
      var entry = {id: block.id || uid(), type: block.type, card: card, group: fieldGroup(body, spec.fields || [], block.data || {}, opts),
                   vis: function () {
                     var v = {};
                     if (vis.hidden) v.hidden = true;
                     if (vis.devices.length < DEVICES.length) v.devices = vis.devices.slice();
                     return v;
                   }};
      body.addEventListener("input", function () { sm.textContent = summaryOf(spec, entry.group.value()); });
      // drag and drop reordering
      var handle = head.querySelector(".handle");
      handle.addEventListener("dragstart", function (e) { e.dataTransfer.effectAllowed = "move"; G._drag = card; card.classList.add("drag"); });
      handle.addEventListener("dragend", function () { card.classList.remove("drag"); G._drag = null; });
      card.addEventListener("dragover", function (e) { if (G._drag && G._drag !== card) e.preventDefault(); });
      card.addEventListener("drop", function (e) {
        e.preventDefault(); if (!G._drag || G._drag === card) return;
        var from = index(G._drag), to = index(card);
        var moved = items.splice(from, 1)[0]; items.splice(to, 0, moved); redraw(); touch();
      });
      return entry;
    }
    function index(card) { return items.findIndex(function (it) { return it.card === card; }); }
    function redraw() { items.forEach(function (it) { list.appendChild(it.card); }); }
    function move(card, delta) {
      var i = index(card), j = i + delta;
      if (j < 0 || j >= items.length) return;
      var tmp = items[i]; items[i] = items[j]; items[j] = tmp; redraw(); touch();
    }
    function insert(block, at, open) {
      var e = make(block, open);
      if (!e) return;
      items.splice(at, 0, e); redraw();
      if (open) e.card.scrollIntoView({behavior: "smooth", block: "center"});
    }
    function palette(at) {
      var groups = {};
      Object.keys(theme.blocks).forEach(function (k) { var b = theme.blocks[k]; (groups[b.group || "Content"] = groups[b.group || "Content"] || []).push([k, b]); });
      var box = el("div", {class: "box"}, [el("h3", {}, [T("Add a block")])]);
      var overlay = el("div", {class: "palette", on: {click: function (e) { if (e.target === overlay) overlay.remove(); }}}, [box]);
      Object.keys(groups).forEach(function (g) {
        box.appendChild(el("div", {class: "grp"}, [L(g)]));
        box.appendChild(el("div", {class: "opts"}, groups[g].map(function (kb) {
          return el("button", {type: "button", class: "opt", on: {click: function () {
            overlay.remove(); insert({id: uid(), type: kb[0], data: {}}, at, true); touch();
          }}}, [el("span", {class: "ic", style: "width:24px;height:24px;border-radius:6px;background:#ECEAFF;color:#4B3BE6;display:grid;place-items:center;font-weight:800;font-size:12px"}, [L(kb[1].label).charAt(0)]), L(kb[1].label)]);
        })));
      });
      document.body.appendChild(overlay);
    }
    (blocks || []).forEach(function (b) { var e = make(b, false); if (e) items.push(e); });
    redraw();
    return {value: function () { return items.map(function (it) { return Object.assign({id: it.id, type: it.type, data: it.group.value()}, it.vis()); }); }};
  }
  G.blockEditor = blockEditor;

  // ------------------------------------------------------------ small helpers
  G.counters = function (root) {
    Array.prototype.forEach.call(root.querySelectorAll("[data-count]"), function (inp) {
      var max = Number(inp.getAttribute("data-count"));
      var hint = el("div", {class: "help"});
      inp.parentNode.appendChild(hint);
      function upd() { var n = inp.value.length; hint.textContent = n + " / ~" + max + " " + T("characters") + (n > max ? " " + T("(search engines may cut it)") : ""); hint.style.color = n > max ? "#b7791f" : ""; }
      inp.addEventListener("input", upd); upd();
    });
  };
  // Autosave (like WordPress): while there are unsaved changes, keep a copy in this browser every 10 seconds.
  // A copy newer than the last save is offered back when the editor opens; restoring reloads the editor with it.
  function asKey(k) { return "technting-cms-autosave:" + k; }
  G.autosave = function (key, collect) {
    function keep() { if (!G.dirty) return; try { localStorage.setItem(asKey(key), JSON.stringify({t: Date.now(), d: collect()})); } catch (e) {} }
    setInterval(keep, 10000);
    window.addEventListener("beforeunload", keep);
  };
  G.takeRestore = function (key) {
    try { var v = sessionStorage.getItem("technting-cms-restore:" + key); sessionStorage.removeItem("technting-cms-restore:" + key); return v ? JSON.parse(v) : null; } catch (e) { return null; }
  };
  G.offerAutosave = function (key, savedAt, host) {
    var v = null;
    try { v = JSON.parse(localStorage.getItem(asKey(key)) || "null"); } catch (e) { v = null; }
    if (!v) return;
    if (v.t <= savedAt) { try { localStorage.removeItem(asKey(key)); } catch (e) {} return; }
    var when = new Date(v.t);
    var box = el("div", {class: "msg info autosave-note", role: "status"}, [
      el("span", {}, [(function () {
        var ar = document.documentElement.lang === "ar", tail = T("were found in this browser.");
        var stamp = when.toLocaleString(ar ? "ar-u-nu-latn" : undefined, {dateStyle: "medium", timeStyle: "short"});
        return T("Unsaved changes from") + " " + stamp + (tail === "." ? ". " : " " + tail + " ");
      })()]),
      el("button", {type: "button", class: "btn sm primary", on: {click: function () {
        try { sessionStorage.setItem("technting-cms-restore:" + key, JSON.stringify(v.d)); } catch (e) {}
        G.dirty = false; location.reload();
      }}}, [T("Restore them")]),
      el("button", {type: "button", class: "btn sm", on: {click: function () {
        try { localStorage.removeItem(asKey(key)); } catch (e) {}
        box.remove();
      }}}, [T("Discard")])]);
    host.insertBefore(box, host.firstChild);
  };
  // Edit lock (like WordPress): tell others this item is open here, and warn when someone else has it open.
  G.editLock = function (form, kind, id, lang, other) {
    var bar = null, mine = !other;
    function post(action) {
      return fetch("/api/edit-lock/", {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": (window.TECHNTING_CMS || {}).csrf || ""},
        body: JSON.stringify({kind: kind, id: id, lang: lang, action: action})}).then(function (r) { return r.json(); }).catch(function () { return {}; });
    }
    function show(name) {
      if (bar) bar.remove();
      bar = el("div", {class: "msg info lock-note", role: "alert"}, [
        el("span", {}, [name + " " + T("has this open right now. If you both save, the later save replaces the earlier one.") + " "]),
        el("button", {type: "button", class: "btn sm", on: {click: function () {
          post("take").then(function () { if (bar) { bar.remove(); bar = null; } mine = true; });
        }}}, [T("Edit anyway")])]);
      form.insertBefore(bar, form.firstChild);
    }
    if (other) { show(other); } else { post("beat"); }
    setInterval(function () {
      if (!mine) return;
      post("beat").then(function (r) { if (r.locked_by) { mine = false; show(r.locked_by); } });
    }, 30000);
  };
  G.guardUnsaved = function (form) {
    form.addEventListener("input", touch);
    window.addEventListener("beforeunload", function (e) { if (G.dirty) { e.preventDefault(); e.returnValue = ""; } });
  };
})();
