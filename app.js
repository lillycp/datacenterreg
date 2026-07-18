(function () {
  "use strict";

  var regulations = [];
  var opposition = [];

  function $(id) { return document.getElementById(id); }

  function escapeHtml(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function formatDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return escapeHtml(iso);
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  }

  // ---------- Tabs ----------
  function initTabs() {
    var buttons = document.querySelectorAll(".tab-btn");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        document.querySelectorAll(".panel").forEach(function (p) { p.classList.remove("active"); });

        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        $(btn.getAttribute("aria-controls")).classList.add("active");
      });
    });
  }

  // ---------- Regulations tab ----------
  function populateStateFilter() {
    var select = $("stateFilter");
    var states = Array.from(new Set(regulations.map(function (r) { return r.state; }))).sort();
    states.forEach(function (s) {
      var opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      select.appendChild(opt);
    });
  }

  function levelBadge(level) {
    var cls = level === "federal" ? "badge-federal" : level === "state" ? "badge-state" : "badge-local";
    var label = level === "federal" ? "Federal" : level === "state" ? "State" : "Local";
    return '<span class="badge ' + cls + '">' + label + "</span>";
  }

  function renderRegulations() {
    var stateVal = $("stateFilter").value;
    var sortVal = $("sortOrder").value;

    var rows = regulations.slice();
    if (stateVal !== "all") {
      rows = rows.filter(function (r) { return r.state === stateVal; });
    }

    if (sortVal === "recent") {
      rows.sort(function (a, b) { return new Date(b.date || 0) - new Date(a.date || 0); });
    } else {
      rows.sort(function (a, b) { return a.state.localeCompare(b.state) || (new Date(b.date || 0) - new Date(a.date || 0)); });
    }

    var tbody = $("regTableBody");
    tbody.innerHTML = "";

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-row">No regulations match this filter.</td></tr>';
    } else {
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        var titleCell = r.sourceUrl
          ? '<a href="' + escapeHtml(r.sourceUrl) + '" target="_blank" rel="noopener">' + escapeHtml(r.title) + "</a>"
          : escapeHtml(r.title);
        tr.innerHTML =
          "<td>" + levelBadge(r.level) + " " + escapeHtml(r.state) + "</td>" +
          "<td>" + titleCell + "</td>" +
          "<td>" + escapeHtml(r.body) + "</td>" +
          '<td><span class="status-pill">' + escapeHtml(r.status || "—") + "</span></td>" +
          "<td>" + formatDate(r.date) + "</td>";
        tbody.appendChild(tr);
      });
    }

    $("regCount").textContent = rows.length + (rows.length === 1 ? " result" : " results");
  }

  // ---------- Opposition tab ----------
  function renderOpposition() {
    var list = $("oppList");
    list.innerHTML = "";

    var items = opposition.slice().sort(function (a, b) {
      return new Date(b.publishedDate || 0) - new Date(a.publishedDate || 0);
    });

    if (items.length === 0) {
      list.innerHTML = '<li class="empty-row">No opposition headlines found yet.</li>';
    } else {
      items.forEach(function (item) {
        var li = document.createElement("li");
        li.innerHTML =
          '<a class="headline-title" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' +
            escapeHtml(item.title) +
          "</a>" +
          '<div class="headline-meta">' +
            "<span>" + escapeHtml(item.source || "Unknown source") + "</span>" +
            "<span>" + formatDate(item.publishedDate) + "</span>" +
            (item.state ? "<span>" + escapeHtml(item.state) + "</span>" : "") +
          "</div>" +
          (item.snippet ? '<div class="headline-snippet">' + escapeHtml(item.snippet) + "</div>" : "");
        list.appendChild(li);
      });
    }

    $("oppCount").textContent = items.length + (items.length === 1 ? " headline" : " headlines");
  }

  // ---------- Data loading ----------
  function loadJson(path) {
    return fetch(path, { cache: "no-store" }).then(function (res) {
      if (!res.ok) throw new Error("Failed to load " + path);
      return res.json();
    });
  }

  function loadMeta() {
    loadJson("data/meta.json").then(function (meta) {
      $("lastUpdated").textContent = "Last updated: " + formatDate(meta.lastUpdated);
    }).catch(function () {
      $("lastUpdated").textContent = "";
    });
  }

  function init() {
    initTabs();
    loadMeta();

    loadJson("data/regulations.json")
      .then(function (data) {
        regulations = data;
        populateStateFilter();
        renderRegulations();
        $("stateFilter").addEventListener("change", renderRegulations);
        $("sortOrder").addEventListener("change", renderRegulations);
      })
      .catch(function () {
        $("regTableBody").innerHTML = '<tr><td colspan="5" class="empty-row">Could not load regulation data.</td></tr>';
      });

    loadJson("data/opposition.json")
      .then(function (data) {
        opposition = data;
        renderOpposition();
      })
      .catch(function () {
        $("oppList").innerHTML = '<li class="empty-row">Could not load headline data.</li>';
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
