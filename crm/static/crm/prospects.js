/* Prospect list: select rows, move to leads, and show the "already in the CRM" popup before anything is created. */
(function () {
  var modal = document.getElementById("dupes-modal");

  function close() { modal.classList.remove("on"); modal.querySelector("[data-body]").innerHTML = ""; }

  function showDupes(html) {
    var body = modal.querySelector("[data-body]");
    body.innerHTML = html;
    body.querySelectorAll("[data-close-modal]").forEach(function (b) {
      b.addEventListener("click", function (e) { e.preventDefault(); close(); });
    });
    modal.classList.add("on");
    var first = body.querySelector("input[type=radio]:checked") || body.querySelector("button");
    if (first) first.focus();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-confirm]");
    if (btn && !confirm(btn.getAttribute("data-confirm"))) e.preventDefault();
  });

  document.querySelectorAll("button[data-move]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var form = btn.form, data = new FormData(form);
      if (btn.name) data.set(btn.name, btn.value);
      btn.disabled = true;
      fetch(btn.getAttribute("formaction"), {method: "POST", body: data, credentials: "same-origin",
                                             headers: {"X-Requested-With": "fetch"}})
        .then(function (r) { return r.json(); })
        .then(function (res) {
          btn.disabled = false;
          if (res.dupes) showDupes(res.html);
          else if (res.redirect) window.location = res.redirect;
        })
        .catch(function () { btn.disabled = false; form.action = btn.getAttribute("formaction"); form.submit(); });
    });
  });

  document.querySelectorAll("select[data-autosubmit]").forEach(function (sel) {
    sel.addEventListener("change", function () { sel.form.submit(); });
  });

  if (modal) {
    modal.addEventListener("click", function (e) { if (e.target === modal) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && modal.classList.contains("on")) close(); });
  }

  // ticked rows -> bulk bar
  var bulk = document.getElementById("bulk");
  if (!bulk) return;
  var bar = bulk.querySelector(".bulkbar"), all = bulk.querySelector("[data-all]"), label = bulk.querySelector("[data-selected]");
  function boxes() { return bulk.querySelectorAll("tbody input[name=ids]"); }
  function refresh() {
    var n = bulk.querySelectorAll("tbody input[name=ids]:checked").length;
    bar.hidden = n === 0;
    label.textContent = (document.documentElement.lang === "ar" ? "المحدد: " : "Selected: ") + n;
  }
  if (all) all.addEventListener("change", function () { boxes().forEach(function (b) { b.checked = all.checked; }); refresh(); });
  bulk.addEventListener("change", function (e) { if (e.target.name === "ids") refresh(); });
})();
