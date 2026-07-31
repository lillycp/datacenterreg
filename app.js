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
  function populateOppFilters() {
    var stateSelect = $("oppStateFilter");
    var states = Array.from(new Set(opposition.map(function (o) { return o.state; }).filter(Boolean))).sort();
    states.forEach(function (s) {
      var opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      stateSelect.appendChild(opt);
    });

    var typeSelect = $("oppTypeFilter");
    var types = Array.from(new Set(opposition.map(function (o) { return o.legislationType; }).filter(Boolean))).sort();
    types.forEach(function (t) {
      var opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      typeSelect.appendChild(opt);
    });
  }

  function yesNoBadge(value) {
    var isYes = value === "Yes";
    var cls = isYes ? "badge-sustain-yes" : "badge-sustain-no";
    return '<span class="badge ' + cls + '">' + (isYes ? "Yes" : "No") + "</span>";
  }

  function renderOpposition() {
    var stateVal = $("oppStateFilter").value;
    var typeVal = $("oppTypeFilter").value;
    var sustainVal = $("oppSustainabilityFilter").value;
    var nimbyVal = $("oppNimbyFilter").value;
    var sortVal = $("oppSortOrder").value;

    var rows = opposition.slice();
    if (stateVal !== "all") {
      rows = rows.filter(function (o) { return o.state === stateVal; });
    }
    if (typeVal !== "all") {
      rows = rows.filter(function (o) { return o.legislationType === typeVal; });
    }
    if (sustainVal !== "all") {
      rows = rows.filter(function (o) { return o.sustainability === sustainVal; });
    }
    if (nimbyVal !== "all") {
      rows = rows.filter(function (o) { return o.nimbyConcerns === nimbyVal; });
    }

    if (sortVal === "recent") {
      rows.sort(function (a, b) { return new Date(b.publishedDate || 0) - new Date(a.publishedDate || 0); });
    } else {
      rows.sort(function (a, b) {
        return (a.state || "").localeCompare(b.state || "") ||
          (new Date(b.publishedDate || 0) - new Date(a.publishedDate || 0));
      });
    }

    var tbody = $("oppTableBody");
    tbody.innerHTML = "";

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-row">No opposition headlines match this filter.</td></tr>';
    } else {
      rows.forEach(function (o) {
        var tr = document.createElement("tr");
        var headlineCell = '<a href="' + escapeHtml(o.url) + '" target="_blank" rel="noopener">' +
          escapeHtml(o.title) + "</a>" +
          (o.snippet ? '<div class="headline-snippet">' + escapeHtml(o.snippet) + "</div>" : "");
        tr.innerHTML =
          "<td>" + escapeHtml(o.state || "—") + "</td>" +
          "<td>" + escapeHtml(o.jurisdiction || "—") + "</td>" +
          "<td>" + escapeHtml(o.legislationType || "—") + "</td>" +
          "<td>" + headlineCell + "</td>" +
          "<td>" + formatDate(o.publishedDate) + "</td>" +
          "<td>" + escapeHtml(o.reasons || "—") + "</td>" +
          "<td>" + yesNoBadge(o.sustainability) + "</td>" +
          "<td>" + yesNoBadge(o.nimbyConcerns) + "</td>";
        tbody.appendChild(tr);
      });
    }

    $("oppCount").textContent = rows.length + (rows.length === 1 ? " headline" : " headlines");
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
        populateOppFilters();
        renderOpposition();
        $("oppStateFilter").addEventListener("change", renderOpposition);
        $("oppTypeFilter").addEventListener("change", renderOpposition);
        $("oppSustainabilityFilter").addEventListener("change", renderOpposition);
        $("oppNimbyFilter").addEventListener("change", renderOpposition);
        $("oppSortOrder").addEventListener("change", renderOpposition);
      })
      .catch(function () {
        $("oppTableBody").innerHTML = '<tr><td colspan="8" class="empty-row">Could not load headline data.</td></tr>';
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
