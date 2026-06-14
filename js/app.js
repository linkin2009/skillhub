(function () {
  "use strict";
  var DATA = "data/";
  var state = {
    lang: localStorage.getItem("lang") || "zh",
    theme: localStorage.getItem("theme") || "light",
    skills: [], byId: {}, meta: { categories: {} },
    collections: [], treasure: [], daily: {},
    query: "", category: "all", sort: "recommend",
    verified: false, official: false, showDupes: false,
  };

  var t = function (k) { var u = window.UI[k]; return (u && u[state.lang]) || k; };
  var catLabel = function (k) { var c = window.CAT_LABELS[k]; return (c && c[state.lang]) || k; };
  function fmt(n) {
    n = n || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return "" + n;
  }
  function esc(s) {
    return ("" + (s == null ? "" : s)).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function descOf(s) { return (state.lang === "zh" && s.desc_zh) ? s.desc_zh : (s.description || ""); }

  // ---------- data ----------
  async function loadData() {
    var f = function (p) { return fetch(DATA + p).then(function (r) { return r.json(); }).catch(function () { return null; }); };
    var r = await Promise.all([f("skills.json"), f("meta.json"), f("collections.json"), f("treasure.json"), f("daily.json")]);
    state.skills = r[0] || [];
    state.meta = r[1] || { categories: {}, total_skills: state.skills.length, total_stars: 0 };
    state.collections = r[2] || [];
    state.treasure = r[3] || [];
    state.daily = r[4] || {};
    state.byId = {};
    state.skills.forEach(function (s) { state.byId[s.id] = s; });
  }

  function normName(s) { return ((s && s.name) || "").toLowerCase().replace(/[^a-z0-9]+/g, ""); }
  function dedupe(list) {
    var groups = {}, order = [];
    list.forEach(function (s) {
      var k = normName(s) || s.id;
      if (!groups[k]) { groups[k] = { primary: s, count: 0 }; order.push(k); }
      else { groups[k].count++; if (s.stars > groups[k].primary.stars) groups[k].primary = s; }
    });
    return order.map(function (k) {
      var o = {}, p; for (p in groups[k].primary) o[p] = groups[k].primary[p];
      o._sim = groups[k].count; return o;
    });
  }

  function getFiltered() {
    var list = state.skills.slice();
    if (state.category !== "all") list = list.filter(function (s) { return s.category === state.category; });
    if (state.verified) list = list.filter(function (s) { return s.verified; });
    if (state.official) list = list.filter(function (s) { return s.official; });
    var q = state.query.trim().toLowerCase();
    if (q) list = list.filter(function (s) {
      return (s.name + " " + s.description + " " + s.author + " " + (s.topics || []).join(" ")).toLowerCase().indexOf(q) >= 0;
    });
    var by = {
      recommend: function (a, b) { return (b.official - a.official) || (b.verified - a.verified) || (b.stars - a.stars); },
      stars: function (a, b) { return b.stars - a.stars; },
      trend: function (a, b) { return (b.trend - a.trend) || (b.stars - a.stars); },
      forks: function (a, b) { return b.forks - a.forks; },
      new: function (a, b) { return (b.created_at || "").localeCompare(a.created_at || ""); },
    };
    list.sort(by[state.sort] || by.recommend);
    return list;
  }

  // ---------- components ----------
  function card(s) {
    if (!s) return "";
    var badges = "";
    if (s.official) badges += '<span class="badge b-official">' + t("official") + "</span>";
    if (s.verified) badges += '<span class="badge b-verified">✓</span>';
    if (s.tier === "A" || s.tier === "B") badges += '<span class="tier tier-' + s.tier + '">' + s.tier + "</span>";
    if (s.stale) badges += '<span class="badge warn" title="' + t("stale") + '">⚠</span>';
    var av = s.avatar
      ? '<img class="ava" src="' + esc(s.avatar) + '" loading="lazy" alt="">'
      : '<div class="ava ava-ph">' + esc((s.author || "?").charAt(0).toUpperCase()) + "</div>";
    var trend = s.trend > 0 ? '<span class="m m-trend">↗ ' + s.trend + "/" + (state.lang === "zh" ? "天" : "d") + "</span>" : "";
    return '<div class="card" data-skill="' + esc(s.id) + '">' +
      '<div class="card-head">' + av +
        '<div class="card-id"><div class="card-name">' + esc(s.name) + " " + badges + "</div>" +
        '<div class="card-author">' + t("author") + " " + esc(s.author) + "</div></div></div>" +
      '<div class="card-desc">' + (esc(descOf(s)) || "—") + "</div>" +
      '<div class="card-foot">' +
        '<span class="m m-star">★ ' + fmt(s.stars) + "</span>" +
        '<span class="m m-fork">⎇ ' + fmt(s.forks) + "</span>" + trend +
        (s._sim > 0 ? '<span class="sim">+' + s._sim + (state.lang === "zh" ? " 个同类" : " similar") + "</span>" : "") +
        '<span class="cat-chip">' + catLabel(s.category) + "</span>" +
      "</div>" +
      '<div class="card-actions">' +
        '<button class="btn btn-install" data-install="' + esc(s.repo) + '">' + t("install") + "</button>" +
        '<a class="btn btn-ghost" href="' + esc(s.url) + '" target="_blank" rel="noopener">' + t("view_repo") + "</a>" +
      "</div></div>";
  }

  function miniRow(s) {
    return '<a class="mrow" href="' + esc(s.url) + '" target="_blank" rel="noopener">' +
      '<span class="mname">' + esc(s.name) + "</span>" +
      '<span class="mstar">★ ' + fmt(s.stars) + (s.trend > 0 ? " · ↗" + s.trend : "") + "</span></a>";
  }

  function emptyHtml() { return '<div class="empty">' + t("empty") + "</div>"; }

  function ids(arr) { return (arr || []).map(function (i) { return state.byId[i]; }).filter(Boolean); }

  // ---------- views ----------
  function homeView() {
    var m = state.meta;
    var hot = ids(state.daily.hot).slice(0, 6);
    var rising = ids(state.daily.rising).slice(0, 8);
    var news = ids(state.daily.new).slice(0, 8);
    return '<div class="hero"><h1>' + t("home_title") + "</h1>" +
      '<p class="stats">' + t("home_stats").replace("{n}", fmt(m.total_skills)).replace("{s}", fmt(m.total_stars)) + "</p>" +
      '<div class="searchbar big"><span class="si">⌕</span><input id="qhome" placeholder="' + t("search_ph") + '"></div></div>' +
      '<div class="panels"><section class="panel"><h2>' + t("today_changes") + "</h2>" +
        '<div class="mini-h">' + t("new_skills") + (state.daily.added_count ? ' <em>+' + state.daily.added_count + "</em>" : "") + "</div>" +
        (news.length ? news.map(miniRow).join("") : '<div class="muted small">' + t("await_snap") + "</div>") +
        '<div class="mini-h">' + t("rising") + "</div>" +
        (rising.length ? rising.map(miniRow).join("") : '<div class="muted small">' + t("await_snap") + "</div>") +
      "</section>" +
      '<section class="panel"><h2>' + t("hot") + '</h2><div class="hotgrid">' + hot.map(card).join("") + "</div></section></div>";
  }

  function catalogView() {
    var full = getFiltered();
    var list = state.showDupes ? full : dedupe(full);
    var head = state.category !== "all" ? '<h1 class="cat-title">' + catLabel(state.category) + "</h1>" : "";
    var chip = function (k, l) { return '<button class="chip ' + (state.sort === k ? "on" : "") + '" data-sort="' + k + '">' + l + "</button>"; };
    var fchip = function (k, l, on) { return '<button class="fchip ' + (on ? "on" : "") + '" data-filter="' + k + '">' + l + "</button>"; };
    var toolbar = '<div class="toolbar">' +
      '<div class="searchbar"><span class="si">⌕</span><input id="q" placeholder="' + t("search_ph") + '" value="' + esc(state.query) + '"></div>' +
      '<div class="chiprow"><div class="sorts">' +
        chip("recommend", t("sort_recommend")) + chip("stars", t("sort_stars")) + chip("trend", t("sort_trend")) +
        chip("forks", t("sort_forks")) + chip("new", t("sort_new")) +
      '</div><div class="filters">' +
        fchip("verified", t("filter_verified"), state.verified) + fchip("official", t("filter_official"), state.official) +
        fchip("showDupes", t("show_dupes"), state.showDupes) +
      "</div></div>" +
      '<div class="rescount">' + t("results_count").replace("{n}", list.length) + "</div></div>";
    var shown = list.slice(0, 300);
    var grid = '<div class="grid">' + (shown.length ? shown.map(card).join("") : emptyHtml()) + "</div>";
    var more = list.length > 300 ? '<div class="muted small center">' + t("showing_first") + "</div>" : "";
    return head + toolbar + grid + more;
  }

  function collectionsView() {
    var cards = state.collections.map(function (c) {
      var members = ids(c.skills);
      var avs = members.slice(0, 5).map(function (s) { return s.avatar ? '<img class="sava" src="' + esc(s.avatar) + '">' : ""; }).join("");
      var name = state.lang === "zh" ? c.name_zh : (c.name_en || c.name_zh);
      return '<a class="ccard" href="#/collections/' + esc(c.id) + '">' +
        '<div class="cicon">' + (c.icon || "📦") + "</div>" +
        '<div class="cmeta"><div class="ctitle">' + esc(name) +
        ' <span class="ccount">' + c.count + " " + (state.lang === "zh" ? "个技能" : "skills") + "</span></div>" +
        '<div class="cdesc">' + esc(c.desc_zh) + "</div>" +
        '<div class="avastack">' + avs + "</div></div></a>";
    }).join("");
    return "<h1>" + t("nav_collections").replace(/^.. /, "") + '</h1><p class="sub">' + t("collections_sub") + "</p>" +
      '<div class="cgrid">' + (cards || emptyHtml()) + "</div>";
  }

  function collectionDetail(id) {
    var c = state.collections.filter(function (x) { return x.id === id; })[0];
    if (!c) return emptyHtml();
    var members = ids(c.skills);
    var name = state.lang === "zh" ? c.name_zh : (c.name_en || c.name_zh);
    return '<a class="back" href="#/collections">← ' + t("nav_collections").replace(/^.. /, "") + "</a>" +
      "<h1>" + (c.icon || "") + " " + esc(name) + '</h1><p class="sub">' + esc(c.desc_zh) + "</p>" +
      '<div class="grid">' + (members.length ? members.map(card).join("") : emptyHtml()) + "</div>";
  }

  function treasureView() {
    var members = ids(state.treasure);
    return "<h1>" + t("nav_treasure").replace(/^.. /, "") + '</h1><p class="sub">' + t("treasure_sub") + "</p>" +
      '<div class="grid">' + (members.length ? members.map(card).join("") : emptyHtml()) + "</div>";
  }

  function dailyView() {
    var d = state.daily;
    var section = function (label, list) {
      var m = ids(list);
      return "<h2 style='margin:22px 2px 12px;font-size:16px'>" + label + "</h2>" +
        '<div class="grid">' + (m.length ? m.map(card).join("") : '<div class="muted small">' + t("await_snap") + "</div>") + "</div>";
    };
    return "<h1>" + t("nav_daily").replace(/^.. /, "") + '</h1><p class="sub">' + t("daily_sub") +
      (d.date ? "  · " + d.date : "") + "</p>" +
      section(t("hot"), d.hot) + section(t("rising"), d.rising) + section(t("new_skills"), d.new);
  }

  // ---------- shell ----------
  function sidebar() {
    var total = state.meta.total_skills || state.skills.length;
    var cats = [["all", total]].concat(
      Object.keys(state.meta.categories || {}).map(function (k) { return [k, state.meta.categories[k]]; })
        .sort(function (a, b) { return b[1] - a[1]; })
    );
    var h = location.hash || "#/";
    var nav = function (route, key) {
      return '<a class="nav ' + (h.indexOf(route) === 0 ? "on" : "") + '" href="' + route + '">' + t(key) + "</a>";
    };
    var inCatalog = (h === "#/" || h === "" || h.indexOf("#/catalog") === 0);
    var catItems = cats.map(function (p) {
      var on = inCatalog && state.category === p[0];
      return '<button class="catitem ' + (on ? "on" : "") + '" data-cat="' + p[0] + '">' +
        "<span>" + catLabel(p[0]) + "</span><span class='cnum'>" + fmt(p[1]) + "</span></button>";
    }).join("");
    return '<a class="brand" href="#/"><div class="logo">📦</div><div>' +
      '<div class="bname">' + esc(window.BRAND.name) + "</div>" +
      '<div class="bsub">' + esc(window.BRAND.sub[state.lang]) + "</div></div></a>" +
      '<nav class="navs">' + nav("#/daily", "nav_daily") + nav("#/collections", "nav_collections") + nav("#/treasure", "nav_treasure") + "</nav>" +
      '<div class="cat-h">' + t("cat_title") + '</div><div class="catlist">' + catItems + "</div>";
  }

  function topbar() {
    var upd = state.meta.updated_at ? (state.meta.updated_at + "").slice(0, 10) : "";
    return (upd ? '<span class="muted small" style="margin-right:auto;padding-left:6px">' + t("updated") + " " + upd + "</span>" : "") +
      '<button class="tbtn" id="themeBtn">' + (state.theme === "dark" ? "☀️" : "🌙") + "</button>" +
      '<button class="tbtn" id="langBtn">🌐 ' + (state.lang === "zh" ? "ZH" : "EN") + "</button>";
  }

  function route() {
    var h = location.hash || "#/";
    if (h.indexOf("#/collections/") === 0) return collectionDetail(decodeURIComponent(h.slice("#/collections/".length)));
    if (h.indexOf("#/collections") === 0) return collectionsView();
    if (h.indexOf("#/treasure") === 0) return treasureView();
    if (h.indexOf("#/daily") === 0) return dailyView();
    if (h.indexOf("#/catalog") === 0) return catalogView();
    return homeView();
  }

  function render() {
    document.documentElement.setAttribute("data-theme", state.theme);
    document.documentElement.setAttribute("lang", state.lang === "zh" ? "zh" : "en");
    document.getElementById("sidebar").innerHTML = sidebar();
    document.getElementById("topbar").innerHTML = topbar();
    document.getElementById("content").innerHTML = route();
    wire();
  }

  // ---------- interactions ----------
  var toastTimer;
  function toast(msg) {
    var el = document.getElementById("toast");
    el.textContent = msg; el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("show"); }, 1600);
  }

  var debounceTimer;
  function wire() {
    var q = document.getElementById("q");
    if (q) {
      q.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        var v = q.value;
        debounceTimer = setTimeout(function () {
          state.query = v;
          var grid = document.querySelector(".grid");
          var rc = document.querySelector(".rescount");
          var full = getFiltered();
          var list = state.showDupes ? full : dedupe(full);
          if (rc) rc.textContent = t("results_count").replace("{n}", list.length);
          if (grid) grid.innerHTML = list.slice(0, 300).map(card).join("") || emptyHtml();
        }, 140);
      });
    }
    var qh = document.getElementById("qhome");
    if (qh) {
      var go = function () { state.query = qh.value; state.category = "all"; location.hash = "#/catalog"; };
      qh.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });
    }
    var themeBtn = document.getElementById("themeBtn");
    if (themeBtn) themeBtn.onclick = function () {
      state.theme = state.theme === "dark" ? "light" : "dark";
      localStorage.setItem("theme", state.theme); render();
    };
    var langBtn = document.getElementById("langBtn");
    if (langBtn) langBtn.onclick = function () {
      state.lang = state.lang === "zh" ? "en" : "zh";
      localStorage.setItem("lang", state.lang); render();
    };
  }

  function skillModal(s) {
    var topics = (s.topics || []).map(function (x) { return '<span class="tchip">' + esc(x) + "</span>"; }).join("");
    var badges = "";
    if (s.official) badges += '<span class="badge b-official">' + t("official") + "</span>";
    if (s.verified) badges += '<span class="badge b-verified">✓</span>';
    if (s.tier === "A" || s.tier === "B") badges += '<span class="tier tier-' + s.tier + '">' + s.tier + "</span>";
    var av = s.avatar ? '<img class="ava" style="width:48px;height:48px" src="' + esc(s.avatar) + '" alt="">' : "";
    return '<div class="modal" role="dialog" aria-modal="true">' +
      '<button class="modal-x" data-close="1" aria-label="close">✕</button>' +
      '<div class="card-head">' + av +
        '<div><div class="card-name" style="font-size:18px">' + esc(s.name) + " " + badges + "</div>" +
        '<div class="card-author">' + t("author") + " " + esc(s.author) + "</div></div></div>" +
      '<p style="color:var(--muted);margin:14px 0;line-height:1.6">' + (esc(descOf(s)) || "—") + "</p>" +
      (topics ? '<div class="tchips">' + topics + "</div>" : "") +
      '<div class="modal-meta"><span class="m-star">★ ' + fmt(s.stars) + "</span><span>⎇ " + fmt(s.forks) + "</span>" +
        (s.trend > 0 ? '<span class="m-trend">↗ ' + s.trend + "/" + (state.lang === "zh" ? "天" : "d") + "</span>" : "") +
        '<span class="cat-chip">' + catLabel(s.category) + "</span>" +
        (s.language ? '<span class="cat-chip">' + esc(s.language) + "</span>" : "") +
        (s.license ? '<span class="cat-chip">' + esc(s.license) + "</span>" : "") + "</div>" +
      (s.pushed_at ? '<div class="muted small" style="margin-top:10px">' + t("updated") + " " + esc(("" + s.pushed_at).slice(0, 10)) + (s.stale ? " · ⚠ " + t("stale") : "") + "</div>" : "") +
      '<div class="card-actions" style="margin-top:18px">' +
        '<button class="btn btn-install" data-install="' + esc(s.repo) + '">' + t("install") + "</button>" +
        '<a class="btn btn-ghost" href="' + esc(s.url) + '" target="_blank" rel="noopener">' + t("view_repo") + "</a></div></div>";
  }
  function openSkill(id) {
    var s = state.byId[id];
    if (!s) return;
    var m = document.getElementById("modal");
    if (!m) { m = document.createElement("div"); m.id = "modal"; m.className = "modal-overlay"; document.body.appendChild(m); }
    m.innerHTML = skillModal(s);
    m.classList.add("show");
  }
  function closeModal() { var m = document.getElementById("modal"); if (m) m.classList.remove("show"); }

  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    if (e.target.closest("[data-close]") || e.target.id === "modal") { closeModal(); return; }
    var el = e.target.closest("[data-sort],[data-filter],[data-cat],[data-install]");
    if (!el) {
      var c = e.target.closest(".card[data-skill]");
      if (c && !e.target.closest("a,button")) openSkill(c.getAttribute("data-skill"));
      return;
    }
    if (el.hasAttribute("data-sort")) { state.sort = el.getAttribute("data-sort"); render(); }
    else if (el.hasAttribute("data-filter")) {
      var f = el.getAttribute("data-filter"); state[f] = !state[f]; render();
    } else if (el.hasAttribute("data-cat")) {
      state.category = el.getAttribute("data-cat"); state.query = "";
      document.getElementById("sidebar").classList.remove("open");
      if ((location.hash || "#/").indexOf("#/catalog") !== 0) location.hash = "#/catalog"; else render();
    } else if (el.hasAttribute("data-install")) {
      var cmd = "/plugin marketplace add " + el.getAttribute("data-install");
      if (navigator.clipboard) navigator.clipboard.writeText(cmd);
      toast(t("copied"));
    }
  });

  window.addEventListener("hashchange", function () {
    document.getElementById("content").scrollIntoView ? window.scrollTo(0, 0) : null;
    render();
  });

  var menu = document.getElementById("menu");
  if (menu) menu.onclick = function () { document.getElementById("sidebar").classList.toggle("open"); };

  // ---------- boot ----------
  (async function () {
    try { await loadData(); } catch (e) { console.error(e); }
    render();
  })();
})();
