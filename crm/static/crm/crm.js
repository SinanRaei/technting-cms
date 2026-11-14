/* Technting CRM: pipeline drag and drop (mouse), a stage menu on touch screens, deal composer tabs and the lost dialog. */
(function () {
  var board = document.getElementById("board");
  if (board) {
    var dragged = null, modal = document.getElementById("lost-modal");
    function counts() {
      document.querySelectorAll(".col").forEach(function (c) { c.querySelector(".c").textContent = c.querySelectorAll(".dcard").length; });
    }
    function post(id, stage, extra) {
      var body = Object.assign({stage: stage}, extra || {});
      var col = document.querySelector('.col[data-stage="' + stage + '"]');
      if (col) body.order = Array.prototype.map.call(col.querySelectorAll(".dcard"), function (c) { return c.dataset.id; });
      return fetch(CRM.moveUrl.replace("/0/", "/" + id + "/"), {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": CRM.csrf}, body: JSON.stringify(body)})
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    }
    function askLost() {
      return new Promise(function (resolve) {
        modal.classList.add("on");
        document.getElementById("lost-reason").focus();
        modal.querySelector("[data-ok]").onclick = function () {
          modal.classList.remove("on");
          resolve({lost_reason: document.getElementById("lost-reason").value, lost_note: document.getElementById("lost-note").value});
        };
        modal.querySelector("[data-cancel]").onclick = function () { modal.classList.remove("on"); resolve(null); };
      });
    }
    function move(card, stage, beforeEl) {
      var target = document.querySelector('.col[data-stage="' + stage + '"]');
      var run = function (extra) {
        if (target) { target.insertBefore(card, beforeEl || null); var hint = target.querySelector(".drop-hint"); if (hint) hint.remove(); }
        post(card.dataset.id, stage, extra).then(function () {
          if (!target) card.remove();
          counts();
        }).catch(function () { location.reload(); });
      };
      if (stage === "lost") {
        askLost().then(function (extra) { if (extra) { run(extra); } else { var s = card.querySelector("[data-move]"); if (s) s.value = card.closest(".col").dataset.stage; } });
      } else { run(); }
    }
    board.addEventListener("dragstart", function (e) {
      var c = e.target.closest(".dcard"); if (!c) return;
      dragged = c; c.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", c.dataset.id);
    });
    document.addEventListener("dragend", function () {
      if (dragged) dragged.classList.remove("dragging");
      dragged = null;
      document.querySelectorAll(".over").forEach(function (x) { x.classList.remove("over"); });
    });
    document.querySelectorAll(".col, .zone").forEach(function (zone) {
      zone.addEventListener("dragover", function (e) { if (!dragged) return; e.preventDefault(); zone.classList.add("over"); });
      zone.addEventListener("dragleave", function (e) { if (!zone.contains(e.relatedTarget)) zone.classList.remove("over"); });
      zone.addEventListener("drop", function (e) {
        e.preventDefault(); zone.classList.remove("over");
        if (!dragged) return;
        var card = dragged, before = null;
        if (zone.classList.contains("col")) {
          var cards = Array.prototype.filter.call(zone.querySelectorAll(".dcard"), function (c) { return c !== card; });
          before = cards.find(function (c) { var r = c.getBoundingClientRect(); return e.clientY < r.top + r.height / 2; }) || null;
          if (zone.dataset.stage === card.closest(".col").dataset.stage) {  // reorder inside a column
            zone.insertBefore(card, before); post(card.dataset.id, zone.dataset.stage); return;
          }
        }
        move(card, zone.dataset.stage, before);
      });
    });
    board.addEventListener("click", function (e) { if (e.target.closest("select")) e.preventDefault(); });
    board.addEventListener("change", function (e) {
      var s = e.target.closest("[data-move]"); if (!s) return;
      move(s.closest(".dcard"), s.value, null);
    });
  }

  // deal and contact composer: switch between note, call, email, meeting and task
  document.querySelectorAll(".composer").forEach(function (comp) {
    var kind = comp.querySelector("input[name=kind]");
    comp.querySelectorAll(".ctabs button").forEach(function (b) {
      b.addEventListener("click", function () {
        comp.querySelectorAll(".ctabs button").forEach(function (x) { x.classList.toggle("on", x === b); });
        kind.value = b.dataset.kind;
        comp.querySelectorAll("[data-only]").forEach(function (el) { el.hidden = el.dataset.only.split(" ").indexOf(b.dataset.kind) < 0; });
        var body = comp.querySelector("textarea");
        body.placeholder = b.dataset.placeholder || "";
        body.focus();
      });
    });
  });

  // lost dialog on the deal page
  var lostBtn = document.querySelector("[data-lost-open]");
  if (lostBtn) lostBtn.addEventListener("click", function () { document.getElementById("deal-lost").classList.add("on"); });
  document.querySelectorAll("[data-close-modal]").forEach(function (b) {
    b.addEventListener("click", function () { b.closest(".modal").classList.remove("on"); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") document.querySelectorAll(".modal.on").forEach(function (m) { m.classList.remove("on"); });
  });
})();
