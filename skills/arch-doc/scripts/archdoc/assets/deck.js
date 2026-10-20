/* arch-doc TL;DR deck: navigation, the slide overview, notes, print and the
 * layout check.
 *
 *   Arrow keys, Page Up/Down, Space, Home/End, swipe, the previous and next
 *   buttons, or a click on the left or right third of the slide: move
 *   between slides
 *   G, or the counter: every slide as a thumbnail; click one to open it
 *   P: print (one slide per PDF page)      N: show or hide speaker notes
 *   #<slide-id>: open that slide           ?slide=<id>&shot=1: that slide alone,
 *                                          unscaled, for a 1920x1080 screenshot
 *   ?check=1: run window.__deckOverflow() (layout faults, and story or detail
 *             slides under 80% full) at load, synchronously, and write the
 *             result as JSON into the pre element #deck-check (for headless tests)
 *   ?check=ui: drive the navigation (next, a click zone, the overview, a
 *             thumbnail) and write what each step showed into #deck-check
 *
 * None of the navigation chrome shows in print, ?shot=1 or ?check=1.
 */
(function () {
  "use strict";
  var W = 1920, H = 1080;
  var stage = document.querySelector(".stage");
  var slides = Array.prototype.slice.call(document.querySelectorAll(".stage > .slide"));
  var params = new URLSearchParams(location.search);
  var checkUi = params.get("check") === "ui";
  var shot = params.get("shot") === "1" || params.get("check") === "1";
  var panel = document.querySelector(".notes-panel");
  var counter = document.querySelector(".counter");
  var counterText = document.querySelector(".counter-text");
  var prevBtn = document.querySelector(".nav-btn.prev");
  var nextBtn = document.querySelector(".nav-btn.next");
  var bar = document.querySelector(".progress-bar");
  var overview = document.querySelector(".overview");
  var grid = document.querySelector(".overview-grid");
  var hint = document.querySelector(".hint");
  var root = document.documentElement;
  var idx = 0;

  function indexOf(id) {
    for (var i = 0; i < slides.length; i++) if (slides[i].id === id) return i;
    return -1;
  }

  /* The slide is scaled to fit the viewport's width and its height, and
     centred (letterboxed). Its box goes into CSS variables, which place the
     buttons, the counter and the progress bar on the slide. When a tall
     viewport leaves room under the slide, the controls move there. */
  function fit() {
    if (shot) { stage.style.transform = "none"; return; }
    var vw = root.clientWidth || window.innerWidth, vh = root.clientHeight || window.innerHeight;
    var s = Math.min(vw / W, vh / H);
    var x = (vw - W * s) / 2, y = (vh - H * s) / 2;
    stage.style.transform = "translate(" + x + "px," + y + "px) scale(" + s + ")";
    var st = root.style;
    st.setProperty("--slide-x", x + "px");
    st.setProperty("--slide-y", y + "px");
    st.setProperty("--slide-w", W * s + "px");
    st.setProperty("--slide-h", H * s + "px");
    st.setProperty("--below", (vh - y - H * s) + "px");
    document.body.classList.toggle("ui-below", vh - y - H * s >= 76);
    if (overview && !overview.hidden) scaleThumbs();
  }

  function show(i, write) {
    if (!slides.length) return;
    var was = idx;
    idx = Math.max(0, Math.min(slides.length - 1, i));
    slides.forEach(function (s, k) {
      s.classList.toggle("active", k === idx);
      if (k === idx) s.removeAttribute("aria-hidden"); else s.setAttribute("aria-hidden", "true");
    });
    var s = slides[idx];
    if (write && location.hash !== "#" + s.id) history.replaceState(null, "", "#" + s.id);
    var aside = s.querySelector("aside.notes");
    if (panel) panel.innerHTML = aside ? aside.innerHTML : "";
    if (counterText) counterText.textContent = (idx + 1) + " / " + slides.length;
    if (counter) counter.setAttribute("aria-label", "Slide " + (idx + 1) + " of " + slides.length + ": show all slides");
    if (prevBtn) prevBtn.disabled = idx === 0;
    if (nextBtn) nextBtn.disabled = idx === slides.length - 1;
    if (bar) bar.style.width = ((idx + 1) / slides.length * 100) + "%";
    document.body.classList.toggle("on-accent", s.classList.contains("bg-s"));
    document.title = (s.getAttribute("data-title") || "") + " · " + document.body.getAttribute("data-deck");
    if (was !== idx) dismissHint();
  }

  function step(d) { show(idx + d, true); }

  function fromHash() {
    var id = decodeURIComponent(location.hash.replace(/^#/, ""));
    var i = id ? indexOf(id) : -1;
    if (i >= 0) show(i, false);
  }

  /* ---- focus: the keys only reach a frame that has focus --------------- */
  function takeFocus() {
    if (shot) return;
    try { window.focus(); } catch (e) { /* a parent may refuse */ }
    var a = document.activeElement;
    if (!a || a === document.body || a === root) document.body.focus({ preventScroll: true });
  }

  /* ---- overview: every slide as a live, scaled thumbnail ---------------- */
  var thumbs = [];

  /* A slide's copy for its thumbnail. Ids inside it (an SVG's arrowhead
     markers, say) are renamed and the references to them rewritten, so the
     copy draws its own markers and the document keeps unique ids. */
  function copySlide(s, n) {
    var c = s.cloneNode(true);
    c.classList.remove("active");
    c.removeAttribute("aria-hidden");
    var notes = c.querySelector("aside.notes");
    if (notes) notes.parentNode.removeChild(notes);
    var map = {};
    var named = [c].concat(Array.prototype.slice.call(c.querySelectorAll("[id]")));
    named.forEach(function (el) {
      if (!el.id) return;
      map[el.id] = "ov" + n + "-" + el.id;
      el.id = map[el.id];
    });
    var all = c.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var attrs = all[i].attributes;
      for (var j = 0; j < attrs.length; j++) {
        var a = attrs[j], v = a.value, nv = v;
        if (v.indexOf("url(") >= 0) {
          nv = v.replace(/url\(\s*(['"]?)#([^'")\s]+)\1\s*\)/g, function (m, q, id) {
            return map[id] ? "url(#" + map[id] + ")" : m;
          });
        }
        if ((a.name === "href" || a.name === "xlink:href") && v.charAt(0) === "#" && map[v.slice(1)]) {
          nv = "#" + map[v.slice(1)];
        }
        if (nv !== v) a.value = nv;
      }
    }
    c.setAttribute("aria-hidden", "true");
    c.setAttribute("inert", "");
    return c;
  }

  function buildThumbs() {
    if (thumbs.length || !grid) return;
    slides.forEach(function (s, k) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "thumb";
      b.setAttribute("data-index", String(k));
      var title = s.getAttribute("data-title") || s.id;
      b.setAttribute("aria-label", "Slide " + (k + 1) + ": " + title);
      var frame = document.createElement("span");
      frame.className = "thumb-frame";
      frame.appendChild(copySlide(s, k));
      var cap = document.createElement("span");
      cap.className = "thumb-cap";
      var num = document.createElement("b");
      num.textContent = String(k + 1);
      cap.appendChild(num);
      cap.appendChild(document.createTextNode(title));
      b.appendChild(frame);
      b.appendChild(cap);
      b.addEventListener("click", function () { closeOverview(); show(k, true); });
      grid.appendChild(b);
      thumbs.push(b);
    });
  }

  function scaleThumbs() {
    if (!thumbs.length) return;
    var w = thumbs[0].querySelector(".thumb-frame").clientWidth;
    if (w) overview.style.setProperty("--thumb-k", String(w / W));
  }

  function openOverview() {
    if (!overview || shot) return;
    buildThumbs();
    overview.hidden = false;
    document.body.classList.add("overview-open");
    scaleThumbs();
    thumbs.forEach(function (t, k) { t.classList.toggle("current", k === idx); });
    var cur = thumbs[idx];
    if (cur) {
      cur.focus({ preventScroll: true });
      cur.scrollIntoView({ block: "center" });
    }
    dismissHint();
  }

  function closeOverview() {
    if (!overview || overview.hidden) return;
    overview.hidden = true;
    document.body.classList.remove("overview-open");
    document.body.focus({ preventScroll: true });
  }

  function overviewOpen() { return overview && !overview.hidden; }

  /* Arrow keys move between thumbnails, a row at a time up and down. */
  function moveThumb(k, d) {
    var at = thumbs.indexOf(document.activeElement);
    if (at < 0) at = idx;
    var cols = 1;
    if (thumbs.length > 1) {
      var top = thumbs[0].offsetTop;
      while (cols < thumbs.length && thumbs[cols].offsetTop === top) cols++;
    }
    var to = k === "row" ? at + d * cols : at + d;
    to = Math.max(0, Math.min(thumbs.length - 1, to));
    thumbs[to].focus();
    thumbs[to].scrollIntoView({ block: "nearest" });
  }

  /* ---- the hint on the cover ------------------------------------------- */
  var hintTimer = null;
  function showHint() {
    if (!hint || shot || idx !== 0) return;
    hint.hidden = false;
    requestAnimationFrame(function () { hint.classList.add("on"); });
    hintTimer = setTimeout(dismissHint, 4500);
  }
  function dismissHint() {
    if (!hint || hint.hidden) return;
    clearTimeout(hintTimer);
    hint.classList.remove("on");
    setTimeout(function () { hint.hidden = true; }, 600);
  }

  /* ---- keys ------------------------------------------------------------- */
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var k = e.key;
    if (overviewOpen()) {
      if (k === "Escape" || k === "g" || k === "G") { closeOverview(); e.preventDefault(); }
      else if (k === "ArrowRight") { moveThumb("one", 1); e.preventDefault(); }
      else if (k === "ArrowLeft") { moveThumb("one", -1); e.preventDefault(); }
      else if (k === "ArrowDown") { moveThumb("row", 1); e.preventDefault(); }
      else if (k === "ArrowUp") { moveThumb("row", -1); e.preventDefault(); }
      return;
    }
    var onButton = e.target && e.target.closest && e.target.closest("button");
    if (k === "ArrowRight" || k === "ArrowDown" || k === "PageDown" || (k === " " && !onButton)) { step(1); e.preventDefault(); }
    else if (k === "ArrowLeft" || k === "ArrowUp" || k === "PageUp") { step(-1); e.preventDefault(); }
    else if (k === "Home") { show(0, true); e.preventDefault(); }
    else if (k === "End") { show(slides.length - 1, true); e.preventDefault(); }
    else if (k === "g" || k === "G") { openOverview(); e.preventDefault(); }
    else if (k === "p" || k === "P") { window.print(); }
    else if (k === "n" || k === "N") { document.body.classList.toggle("show-notes"); }
    else if (k === "Escape") { document.body.classList.remove("show-notes"); }
  });

  /* ---- swipe ------------------------------------------------------------ */
  var x0 = null, y0 = null, swiped = false;
  document.addEventListener("touchstart", function (e) {
    swiped = false;
    if (overviewOpen()) { x0 = null; return; }
    if (e.touches.length === 1) { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }
  }, { passive: true });
  document.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var t = e.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) { step(dx < 0 ? 1 : -1); swiped = true; }
    x0 = y0 = null;
  }, { passive: true });

  /* ---- click zones: the left and right thirds of the slide -------------- */
  /* A click on text waits a moment, so a double click can still select a
     word; a drag that selects text, a link, a button, and anything outside
     the slide's own content do not move the deck. */
  var TEXT = "p, h1, h2, h3, td, th, li, b, em, code, span, text, tspan, .callout";
  var pending = null;

  function zone(x) {
    var r = stage.getBoundingClientRect();
    if (!r.width) return 0;
    if (x < r.left + r.width / 3) return -1;
    if (x > r.right - r.width / 3) return 1;
    return 0;
  }

  function navigable(e) {
    if (shot || swiped || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
    if (overviewOpen()) return false;
    var t = e.target;
    if (!t || !t.closest) return false;
    if (t.closest("a, button, input, select, textarea, summary, label, .deck-ui, .notes-panel")) return false;
    var sel = window.getSelection && window.getSelection();
    return !(sel && !sel.isCollapsed && String(sel).length);
  }

  document.addEventListener("click", function (e) {
    if (!navigable(e)) return;
    var d = zone(e.clientX);
    if (pending) { clearTimeout(pending); pending = null; }
    if (!d || e.detail > 1) return;
    var go = function () {
      pending = null;
      var sel = window.getSelection && window.getSelection();
      if (sel && !sel.isCollapsed && String(sel).length) return;
      step(d);
    };
    var t = e.target;
    if (t.closest && t.closest(".slide") && t.closest(TEXT)) pending = setTimeout(go, 280);
    else go();
  });

  /* ---- pointer: wake the buttons, show which way a click goes ----------- */
  var wakeTimer = null, focused = false;
  document.addEventListener("pointermove", function (e) {
    if (shot) return;
    if (!focused) { focused = true; takeFocus(); }
    if (e.pointerType === "touch") return;
    document.body.classList.add("ui-awake");
    clearTimeout(wakeTimer);
    wakeTimer = setTimeout(function () { document.body.classList.remove("ui-awake"); }, 2400);
    var d = overviewOpen() || (e.target.closest && e.target.closest("a, button, .deck-ui")) ? 0 : zone(e.clientX);
    if (d < 0 && idx === 0) d = 0;
    if (d > 0 && idx === slides.length - 1) d = 0;
    document.body.classList.toggle("zone-prev", d < 0);
    document.body.classList.toggle("zone-next", d > 0);
  });
  document.addEventListener("pointerdown", function () { takeFocus(); }, true);
  document.addEventListener("mouseleave", function () {
    document.body.classList.remove("ui-awake", "zone-prev", "zone-next");
  });

  if (prevBtn) prevBtn.addEventListener("click", function () { step(-1); });
  if (nextBtn) nextBtn.addEventListener("click", function () { step(1); });
  if (counter) counter.addEventListener("click", function () { openOverview(); });
  var closeBtn = document.querySelector(".overview-close");
  if (closeBtn) closeBtn.addEventListener("click", function () { closeOverview(); });
  if (overview) overview.addEventListener("click", function (e) {
    if (e.target === overview || e.target === grid) closeOverview();
  });

  window.addEventListener("resize", fit);
  window.addEventListener("hashchange", fromHash);

  /* What the navigation chrome is doing, for headless tests: whether each
     piece is laid out, the counter's text and the overview's state. */
  window.__deckUI = function () {
    function shown(el) {
      if (!el || el.hidden) return false;
      var cs = getComputedStyle(el);
      return cs.display !== "none" && cs.visibility !== "hidden" && el.getClientRects().length > 0;
    }
    var ids = Array.prototype.map.call(document.querySelectorAll("[id]"), function (el) { return el.id; });
    var dup = ids.filter(function (id, i) { return ids.indexOf(id) !== i; });
    return {
      shown: { prev: shown(prevBtn), next: shown(nextBtn), counter: shown(counter),
               progress: shown(bar && bar.parentNode), overview: shown(overview), hint: shown(hint) && hint.classList.contains("on") },
      counter: counterText ? counterText.textContent : null,
      progress: bar ? bar.style.width : null,
      active: slides[idx] ? slides[idx].id : null,
      thumbs: grid ? grid.querySelectorAll(".thumb").length : 0,
      thumbSlides: grid ? grid.querySelectorAll(".thumb .slide").length : 0,
      duplicateIds: dup.slice(0, 10)
    };
  };


  /* ---- fitting --------------------------------------------------------
     The builder renders every row it may show (up to 14 a table); here,
     with fonts loaded, each body is filled exactly by adding, not only
     removing. Every table starts as a header, every side table as a
     one-line summary. The main register (data-weight 2) then takes rows
     one at a time while the next fits; each side table is opened when it
     can show three rows (or all it has) and stays a summary otherwise; the
     room left goes a row at a time round the open tables. Story cards
     (.trim-item) go from the end only if the body overflows without them.
     Each table keeps one footnote: "9 more rows · 1 more column in 4.3". */
  var MIN_SIDE_ROWS = 3;
  function rowsAll(g) { return Array.prototype.slice.call(g.querySelectorAll("tr.r")); }
  function rowsShown(g) { return rowsAll(g).filter(function (r) { return !r.hidden; }); }
  function plural(n, w) { return n + " " + w + (n === 1 ? "" : "s"); }
  function note(g) {
    var total = +g.getAttribute("data-total"), shown = rowsShown(g).length, where = g.getAttribute("data-where");
    var cols = +g.getAttribute("data-cols") || 0, split = g.getAttribute("data-split") || "";
    var more = g.querySelector("p.more"), table = g.querySelector("table");
    if (!more) return;
    more.title = "";
    if (g.hasAttribute("data-collapsed")) {
      table.hidden = true; more.hidden = false;
      more.textContent = plural(total, "row") + " in " + where + (split ? ": " + split : "");
      more.title = more.textContent;
      return;
    }
    table.hidden = false;
    var parts = [];
    if (total > shown) parts.push(plural(total - shown, "more row"));
    if (cols) parts.push(plural(cols, "more column"));
    more.hidden = !parts.length;
    more.textContent = parts.length ? parts.join(" · ") + " in " + where : "";
  }
  function over(el) { return el.scrollHeight > el.clientHeight + 1; }
  function room(c) { return (1 - fillOfBody(c)) * c.clientHeight; }
  /* Remember the smallest addition that did not fit, as the room it would
     have needed: a body with less room than that left is full. */
  function missed(c, free0) {
    var need = free0 + (c.scrollHeight - c.clientHeight), body = c.closest(".body") || c;
    [body, c].forEach(function (el) {       // the body's record, and the lane's
      var m = +el.getAttribute("data-next-row") || Infinity;
      if (need > 0 && need < m) el.setAttribute("data-next-row", Math.round(need));
    });
  }
  function addRow(g, c, free0) {
    if (g.hasAttribute("data-collapsed")) return false;      // a summary line takes no rows
    var next = rowsAll(g).filter(function (r) { return r.hidden; })[0];
    if (!next) return false;
    if (free0 === undefined) free0 = room(c);
    next.hidden = false; note(g);
    if (over(c)) {
      missed(c, free0);
      next.hidden = true; note(g); return false;
    }
    return true;
  }
  /* Open a summarised table with up to ``want`` rows (at least one); put it
     back to its summary line when ``least`` rows do not fit. */
  function tryOpen(g, c, want, least) {
    if (g.hasAttribute("data-fixed")) return false;     // a thin table: always its summary
    var free0 = room(c);
    g.removeAttribute("data-collapsed"); note(g);
    var got = 0;
    while (got < want && addRow(g, c, got === 0 ? free0 : undefined)) got++;
    if (got < least) {
      rowsAll(g).forEach(function (r) { r.hidden = true; });
      g.setAttribute("data-collapsed", ""); note(g);
      return false;
    }
    return true;
  }
  function fitBox(c) {
    var groups = Array.prototype.slice.call(c.querySelectorAll(".group[data-total]"));
    var main = groups.filter(function (g) { return g.getAttribute("data-weight") === "2"; })[0] || groups[0];
    var sides = groups.filter(function (g) { return g !== main; });
    c.removeAttribute("data-next-row");   // a fresh fit, a fresh record (the body's is reset in fitLayout)
    c.querySelectorAll("table.reg").forEach(function (t) { t.style.fontSize = ""; });
    groups.forEach(function (g) {
      rowsAll(g).forEach(function (r) { r.hidden = true; });
      if (g === main && !g.hasAttribute("data-fixed")) g.removeAttribute("data-collapsed");
      else g.setAttribute("data-collapsed", "");
      note(g);
    });
    c.querySelectorAll(".card .text[data-lines]").forEach(function (t) {
      var n = +t.getAttribute("data-min") || 3;
      t.setAttribute("data-lines", n); t.style.webkitLineClamp = n;
    });
    /* Optional registers (a story column's excerpts after the first) are
       dropped from the end while even their summaries do not fit. */
    var optional = groups.filter(function (g) { return g.classList.contains("optional"); });
    optional.forEach(function (g) { g.hidden = false; });
    for (var o = optional.length - 1; o >= 0 && over(c); o--) optional[o].hidden = true;
    groups = groups.filter(function (g) { return !g.hidden; });
    sides = sides.filter(function (g) { return !g.hidden; });
    var items = Array.prototype.slice.call(c.querySelectorAll(".trim-item"));
    items.forEach(function (e) { e.hidden = false; });
    for (var k = items.length - 1; k >= 0 && over(c); k--) items[k].hidden = true;
    /* Cards trimmed: offer the dropped optional registers the room again,
       in order, each kept if its summary fits. */
    optional.forEach(function (g) {
      if (!g.hidden) return;
      g.hidden = false;
      if (over(c)) g.hidden = true;
    });
    groups = Array.prototype.slice.call(c.querySelectorAll(".group[data-total]")).filter(function (g) {
      return !g.hidden;
    });
    main = groups.filter(function (g) { return g.getAttribute("data-weight") === "2"; })[0] || groups[0];
    sides = groups.filter(function (g) { return g !== main; });
    if (main && !main.hasAttribute("data-fixed")) { main.removeAttribute("data-collapsed"); note(main); }
    if (main && over(c)) { main.setAttribute("data-collapsed", ""); note(main); }
    // In a story column the cards' text grows before tables take the room left.
    if (c.classList.contains("fitcol")) grow(c);
    if (main) { var guard = 100; while (guard-- > 0 && addRow(main, c)) {} }
    // A table shows at least one row or stays a one-line summary.
    if (main && !rowsShown(main).length) { main.setAttribute("data-collapsed", ""); note(main); }
    /* Then each summarised section, in order, opens with up to three rows
       and stays open when at least one fits; then the open tables take rows
       a row at a time, main first, until the next row would not fit. */
    // From here additions are tried in their final order: the record of the
    // cheapest that did not fit starts afresh (the main register's next row
    // is tried again in the round that follows).
    c.removeAttribute("data-next-row");
    var bodyEl = c.closest(".body");
    if (bodyEl && bodyEl !== c && !bodyEl.querySelector(".fitcol")) bodyEl.removeAttribute("data-next-row");
    sides.forEach(function (g) {
      tryOpen(g, c, Math.min(MIN_SIDE_ROWS, rowsAll(g).length), 1);
    });
    var open = groups.filter(function (g) { return !g.hasAttribute("data-collapsed"); });
    var progress = true;
    while (progress) {
      progress = false;
      open.forEach(function (g) { if (addRow(g, c)) progress = true; });
    }
    groups.forEach(function (g) {
      if (g.hasAttribute("data-collapsed")) return;
      var t = g.querySelector("table"), cols = t ? t.querySelectorAll("tr")[0].children.length : 0;
      if (rowsShown(g).length === 1 && cols < 3) {
        // What showing it properly (two rows) would overflow by, then the
        // room its summary leaves: together, the cost of that addition.
        var second = rowsAll(g)[1], overBy = 0;
        if (second) { second.hidden = false; overBy = Math.max(0, c.scrollHeight - c.clientHeight); second.hidden = true; }
        rowsAll(g).forEach(function (r) { r.hidden = true; });
        g.setAttribute("data-collapsed", ""); note(g);
        if (second) {
          // the state the earlier records measured is gone: this cost replaces them
          var need = Math.round(room(c) + overBy), bodyEl2 = c.closest(".body") || c;
          [bodyEl2, c].forEach(function (el) { el.setAttribute("data-next-row", need); });
        }
      }
    });
    grow(c);
    /* Last, what was held back is offered again in its smallest form: a
       dropped register as its summary line, a trimmed card at two lines.
       Each stays only if it fits. */
    c.querySelectorAll(".group.optional[hidden]").forEach(function (g) {
      var free0 = room(c);
      g.hidden = false; g.setAttribute("data-collapsed", ""); note(g);
      if (over(c)) { missed(c, free0); g.hidden = true; }
    });
    c.querySelectorAll(".trim-item[hidden]").forEach(function (e) {
      var t = e.querySelector(".text[data-lines]"), free0 = room(c);
      e.hidden = false;
      if (t) { t.setAttribute("data-lines", 2); t.style.webkitLineClamp = 2; }
      if (over(c)) { missed(c, free0); e.hidden = true; }
    });
    growType(c);
  }
  /* A body that shows everything its tables hold and still has room sets
     their type larger, a pixel at a time up to 30px, while it fits. */
  function growType(c) {
    if (!c.classList.contains("rows")) return;
    if (c.querySelector("tr.r[hidden], .group[data-collapsed]")) return;
    var tables = c.querySelectorAll("table.reg");
    if (!tables.length) return;
    var size = 24;
    while (size < 30) {
      Array.prototype.forEach.call(tables, function (t) { t.style.fontSize = (size + 1) + "px"; });
      if (over(c)) { Array.prototype.forEach.call(tables, function (t) { t.style.fontSize = size + "px"; }); break; }
      size++;
    }
  }
  /* Story cards show as many lines of their text as the column has room
     for: each card's line limit rises a line at a time while it fits. */
  function grow(c) {
    var cards = Array.prototype.filter.call(c.querySelectorAll(".card .text[data-lines]"), function (t) {
      return !t.closest("[hidden]");
    });
    var progress = true;
    while (progress) {
      progress = false;
      cards.forEach(function (t) {
        var n = +t.getAttribute("data-lines"), max = +t.getAttribute("data-max") || 12;
        if (n >= max || t.scrollHeight <= t.clientHeight + 1) return;   // already shows all its text
        t.setAttribute("data-lines", n + 1); t.style.webkitLineClamp = n + 1;
        if (over(c)) { t.setAttribute("data-lines", n); t.style.webkitLineClamp = n; }
        else progress = true;
      });
    }
  }
  /* Whether an element holds content back: hidden rows, a collapsed or
     dropped register, or trimmed cards. A fixed summary (a thin table)
     shows all it ever will, so nothing inside it counts. */
  function heldBack(el) {
    return Array.prototype.some.call(el.querySelectorAll(
      "tr.r[hidden], .group[data-collapsed], .group[hidden], .trim-item[hidden]"), function (e) {
      return !e.closest("[data-fixed]");
    });
  }
  function fitLayout() {
    slides.forEach(function (s) {
      s.querySelectorAll(".body.fill").forEach(function (b) {
        b.removeAttribute("data-next-row");
        var cols = b.querySelectorAll(".fitcol");
        if (cols.length) { Array.prototype.forEach.call(cols, fitBox); return; }
        var row = b.querySelector(".cols.gridrow");
        if (row) row.classList.remove("stacked");
        fitBox(b);
        /* Side tables too narrow to open: stacked full width their rows are
           shorter. Keep whichever layout shows more rows. */
        if (row && b.querySelector(".group[data-collapsed]") && fillOfBody(b) < DETAIL_FILL) {
          var before = b.querySelectorAll("tr.r:not([hidden])").length;
          row.classList.add("stacked");
          fitBox(b);
          if (b.querySelectorAll("tr.r:not([hidden])").length <= before) {
            row.classList.remove("stacked");
            fitBox(b);
          }
        }
      });
      if (heldBack(s)) s.setAttribute("data-trimmed", ""); else s.removeAttribute("data-trimmed");
    });
  }
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer); resizeTimer = setTimeout(fitLayout, 200);
  });

  /* How far down its body a story or detail slide's content reaches, as a
     fraction of the body's height. */
  function fillOf(s) { var body = s.querySelector(".body"); return body ? fillOfBody(body) : 1; }
  function fillOfBody(body) {
    var br = body.getBoundingClientRect();
    var bottom = br.top;
    Array.prototype.forEach.call(body.querySelectorAll("*"), function (el) {
      if (el.closest("[hidden]")) return;
      var r = el.getBoundingClientRect();
      if (r.height && r.width) bottom = Math.max(bottom, r.bottom);
    });
    return (bottom - br.top) / (br.height || 1);
  }
  /* Blank area: the share of the 1664 x 824 content box (128px margins) in
     which a sample point hits only the slide or a layout container, i.e. no
     text, table, card, picture or other content. Sampled every 16px with
     the slide shown at scale 1. */
  var STRUCTURE = ["slide", "body", "cols", "col", "gcol", "fitcol", "grid", "cardgrid", "story-cols", "group",
                   "group-head", "points", "facts", "hblock", "runstats", "toc", "picture"];
  function structural(el, slide) {
    if (!el || el === slide || el === document.body || el === document.documentElement) return true;
    if (el.closest && !slide.contains(el)) return true;
    if (el.tagName && el.tagName.toLowerCase() === "svg") return true;     // the picture's empty canvas
    var cls = (el.getAttribute && el.getAttribute("class")) || "";
    return cls.split(/\s+/).some(function (c) { return STRUCTURE.indexOf(c) >= 0; });
  }
  function blankOf(s) {
    var was = idx, k = slides.indexOf(s);
    show(k, false);
    var sr = s.getBoundingClientRect(), scale = sr.width / W || 1;
    var x0 = 128, y0 = 128, w = W - 256, h = H - 256, step = 16, blank = 0, n = 0;
    for (var y = y0 + step / 2; y < y0 + h; y += step) {
      for (var x = x0 + step / 2; x < x0 + w; x += step) {
        var el = document.elementFromPoint(sr.left + x * scale, sr.top + y * scale);
        n++;
        if (structural(el, s)) blank++;
      }
    }
    show(was, false);
    return blank / (n || 1);
  }
  /* Reach: across the body's width (every 48px), how far above the body's
     foot the lowest content ends. Returns the share of the width that ends
     more than REACH_GAP px short. */
  var REACH_GAP = 120, REACH_SHARE = 0.5;
  function reachOf(s) {
    var body = s.querySelector(".body");
    if (!body) return 0;
    var was = idx;
    show(slides.indexOf(s), false);
    var sr = s.getBoundingClientRect(), k = sr.width / W || 1, br = body.getBoundingClientRect();
    /* A lane counts only while it holds something back: hidden rows, a
       collapsed or dropped register, or trimmed cards. Its share is how much
       of its own width ends more than REACH_GAP px above the body's foot. */
    var lanes = Array.prototype.filter.call(s.querySelectorAll(".body .fitcol, .body .gcol"), function (l) {
      return heldBack(l);
    });
    var worst = 0, widest = 0, laneLog = [];
    reachOf.lanes = laneLog;
    lanes.forEach(function (l) {
      // what the lane holds back would not fit in less than this
      var cost = +l.getAttribute("data-next-row") || +body.getAttribute("data-next-row") || 0;
      var lr = l.getBoundingClientRect(), short = 0, n = 0;
      for (var x = lr.left + 16 * k; x < lr.right - 8 * k; x += 24 * k) {
        var y = br.bottom - 2 * k;
        while (y > br.top) {
          if (!structural(document.elementFromPoint(x, y), s)) break;
          y -= 8 * k;
        }
        var gap = (br.bottom - y) / k;
        n++;
        if (gap > REACH_GAP && gap > cost + 16) { short++; widest = Math.max(widest, gap); }
      }
      worst = Math.max(worst, short / (n || 1));
      laneLog.push({ cost: cost, short: Math.round(short / (n || 1) * 100) / 100, widest: Math.round(widest) });
    });
    show(was, false);
    reachOf.gap = widest;
    return worst;
  }
  window.__deckReach = function () {
    return slides.filter(function (s) { return s.hasAttribute("data-fill"); }).map(function (s) {
      return { slide: s.id, short: Math.round(reachOf(s) * 100) / 100, lanes: reachOf.lanes };
    });
  };
  window.__deckBlank = function () {
    return slides.filter(function (s) { return s.getAttribute("data-kind") !== "cover"; }).map(function (s) {
      return { slide: s.id, kind: s.getAttribute("data-kind"), blank: Math.round(blankOf(s) * 100) / 100,
               complete: s.hasAttribute("data-complete") && !s.hasAttribute("data-trimmed") };
    });
  };
  window.__deckFill = function () {
    return slides.filter(function (s) { return s.hasAttribute("data-fill"); }).map(function (s) {
      return { slide: s.id, fill: Math.round(fillOf(s) * 100) / 100, rows: Math.round(rowArea(s) * 100) / 100,
               complete: s.hasAttribute("data-complete"),
               trimmed: s.hasAttribute("data-trimmed") };
    });
  };

  /* ---- layout check ---------------------------------------------------- */
  function describe(el) {
    var cls = el.getAttribute("class") || "";
    var text = (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60);
    return el.tagName.toLowerCase() + (cls ? "." + cls.split(/\s+/).join(".") : "") + (text ? " \"" + text + "\"" : "");
  }

  function boxesOverlap(a, b, tol) {
    return a.x + tol < b.x + b.width && b.x + tol < a.x + a.width &&
           a.y + tol < b.y + b.height && b.y + tol < a.y + a.height;
  }

  /* Every element that leaves its slide, every .fit container whose content
     is larger than the box, every SVG label that leaves the box it was
     placed in (data-in), and every pair of SVG labels that overlap. */
  var MIN_FILL = 0.8, DETAIL_FILL = 0.85, ROW_AREA = 0.45;
  function rowArea(s) {
    var body = s.querySelector(".body");
    if (!body) return 1;
    var a = 0, br = body.getBoundingClientRect();
    body.querySelectorAll("tr.r, .card").forEach(function (r) {
      if (r.closest("[hidden]") || r.hidden) return;
      var rr = r.getBoundingClientRect();
      a += rr.width * rr.height;
    });
    return a / ((br.width * br.height) || 1);
  }
  window.__deckOverflow = function () {
    var out = [], seenPictures = {};
    slides.forEach(function (s) {
      var sr = s.getBoundingClientRect();
      var k = sr.width / W || 1, tol = 1.5 * k;
      var all = s.querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        var el = all[i];
        if (el.closest("aside")) continue;
        var tag = el.tagName.toLowerCase();
        var inSvg = el.closest("svg") && tag !== "svg";
        if (inSvg && tag !== "text") continue;
        var r = el.getBoundingClientRect();
        if (!r.width && !r.height) continue;
        if (r.left < sr.left - tol || r.top < sr.top - tol || r.right > sr.right + tol || r.bottom > sr.bottom + tol) {
          out.push({ slide: s.id, problem: "outside the slide", element: describe(el) });
        }
        if (el.classList && el.classList.contains("fit")) {
          var dw = el.scrollWidth - el.clientWidth, dh = el.scrollHeight - el.clientHeight;
          if (dw > 1 || dh > 1) {
            out.push({ slide: s.id, problem: "content larger than its box by " + dw + "x" + dh + "px", element: describe(el) });
          }
        }
      }
      var head = s.querySelector(".hblock");
      if (head) {
        var hb = head.getBoundingClientRect().bottom;
        s.querySelectorAll(".body, .picture").forEach(function (b) {
          if (hb > b.getBoundingClientRect().top + tol) {
            out.push({ slide: s.id, problem: "heading runs into the body", element: describe(head) });
          }
        });
      }
      var footer = s.querySelector(".footer");
      if (footer) {
        var fr = footer.getBoundingClientRect();
        s.querySelectorAll(".body, .picture").forEach(function (b) {
          if (b.getBoundingClientRect().bottom > fr.top + tol) {
            out.push({ slide: s.id, problem: "runs into the footer", element: describe(b) });
          }
        });
      }
      /* A table is never a header alone: an open table shows a row. */
      s.querySelectorAll(".group[data-total]").forEach(function (g) {
        if (g.hidden || g.closest("[hidden]") || g.hasAttribute("data-collapsed")) return;
        var t = g.querySelector("table");
        if (t && !t.hidden && !rowsShown(g).length) {
          out.push({ slide: s.id, problem: "header-only table", element: describe(g.querySelector(".group-label")) });
        }
        var hdr = t ? t.querySelectorAll("tr")[0] : null, ncol = hdr ? hdr.children.length : 0;
        if (t && !t.hidden && (ncol < 2 || (rowsShown(g).length === 1 && ncol < 3))) {
          out.push({ slide: s.id, problem: "thin table (" + ncol + " columns, " + rowsShown(g).length + " rows)",
                     element: describe(g.querySelector(".group-label")) });
        }
      });
      /* A generated picture appears on one slide only. */
      var svgp = s.querySelector(".picture svg");
      if (svgp) {
        var sig = svgp.textContent.replace(/\s+/g, " ") + "|" + svgp.querySelectorAll("*").length;
        if (seenPictures[sig]) out.push({ slide: s.id, problem: "same picture as " + seenPictures[sig],
                                          element: describe(svgp) });
        else seenPictures[sig] = s.id;
      }
      /* A callout sits inside its picture, clear of the edge. */
      s.querySelectorAll(".picture .callout").forEach(function (c) {
        var pr = c.closest(".picture").getBoundingClientRect(), cr = c.getBoundingClientRect();
        var m = 8 * k;
        if (cr.left < pr.left + m || cr.right > pr.right - m || cr.top < pr.top + m || cr.bottom > pr.bottom - m) {
          out.push({ slide: s.id, problem: "callout not inside its picture", element: describe(c) });
        }
      });
      /* A story or detail slide fills its body (MIN_FILL), unless the
         chapter has nothing more to show (data-complete, nothing trimmed). */
      if (s.hasAttribute("data-fill") && !(s.hasAttribute("data-complete") && !s.hasAttribute("data-trimmed"))) {
        /* Content is hidden, so the body must reach its foot across its
           columns: no column holding content back may end 120px short across more than half its width. */
        var sh = reachOf(s), nextAdd = +s.querySelector(".body").getAttribute("data-next-row") || 0;
        if (sh > REACH_SHARE) out.push({ slide: s.id, problem: "stops short: a column holding content back ends " +
                                  "more than " + REACH_GAP + "px above the body's foot across " + Math.round(sh * 100) +
                                  "% of its width (widest gap " + Math.round(reachOf.gap) + "px)",
                                  element: describe(s.querySelector(".body")) });
        var f = fillOf(s), detail = s.getAttribute("data-kind") === "detail";
        var rowsBody = !!s.querySelector(".body.fill.rows");     // a detail body, or a stacked story
        var need = (detail || rowsBody) ? DETAIL_FILL : MIN_FILL;
        var bb = s.querySelector(".body").getBoundingClientRect();
        var left = (1 - f) * bb.height / k;           // px of body left, in slide pixels
        var nextRow = +s.querySelector(".body").getAttribute("data-next-row") || 0;
        if (f < need && left > Math.max(nextRow, 1) + 4) out.push({ slide: s.id, problem: "underfilled: content reaches " + Math.round(f * 100) +
                                 "% of the body", element: describe(s.querySelector(".body")) });
        /* A detail slide that hides rows must spend its room on rows, not
           on labels, headers and footnotes. */
        var ra = rowArea(s);
        if (detail && ra < ROW_AREA) out.push({ slide: s.id, problem: "rows fill only " + Math.round(ra * 100) +
                                               "% of the body while rows are hidden",
                                               element: describe(s.querySelector(".body")) });
      }
      s.querySelectorAll("svg").forEach(function (svg) {
        /* Work in client pixels, so rotated labels and the picture's scale
           are accounted for. A line's font box is taller than its line
           (ascent plus descent), so each line is trimmed by 12% of the font
           size top and bottom before comparing: what is left is the ink. */
        var m = svg.getScreenCTM();
        if (!m) return;
        var unit = Math.abs(m.a) || 1;
        var lines = [];
        var texts = Array.prototype.slice.call(svg.querySelectorAll("text"));
        texts.forEach(function (t, j) {
          var size = parseFloat(t.getAttribute("font-size") || "24") * unit;
          var trim = 0.12 * size;
          var spans = t.querySelectorAll("tspan");
          (spans.length ? Array.prototype.slice.call(spans) : [t]).forEach(function (sp) {
            var r = sp.getBoundingClientRect();
            if (!r.width) return;
            lines.push({ text: j, el: t, x: r.left, y: r.top + trim, width: r.width, height: Math.max(0, r.height - 2 * trim) });
          });
          var d = (t.getAttribute("data-in") || "").split(" ").map(Number);
          if (d.length === 4) {
            var r = t.getBoundingClientRect();
            var x0 = m.a * d[0] + m.e, y0 = m.d * d[1] + m.f, x1 = m.a * (d[0] + d[2]) + m.e, y1 = m.d * (d[1] + d[3]) + m.f;
            if (r.left < x0 - 1 || r.right > x1 + 1 || r.top + trim < y0 - 1 || r.bottom - trim > y1 + 1) {
              out.push({ slide: s.id, problem: "label leaves its box", element: describe(t) });
            }
          }
        });
        for (var a = 0; a < lines.length; a++) {
          for (var b = a + 1; b < lines.length; b++) {
            if (lines[a].text !== lines[b].text && boxesOverlap(lines[a], lines[b], 1)) {
              out.push({ slide: s.id, problem: "labels overlap",
                         element: describe(lines[a].el) + " / " + describe(lines[b].el) });
            }
          }
        }
      });
    });
    return out;
  };

  /* Callout tags that sit on a picture's labels (a deck.yaml placement to
     adjust, reported separately from layout faults). */
  window.__deckCallouts = function () {
    var out = [];
    slides.forEach(function (s) {
      s.querySelectorAll(".callout").forEach(function (c) {
        var cr = c.getBoundingClientRect();
        /* Against every shape the picture draws (boxes, cells, cards, bars,
           lanes, markers) and every label, not just the panel. */
        s.querySelectorAll(".picture svg text, .picture svg rect, .picture svg circle").forEach(function (t) {
          var tr = t.getBoundingClientRect();
          if (!tr.width || !tr.height) return;
          if (boxesOverlap({ x: cr.left, y: cr.top, width: cr.width, height: cr.height },
                           { x: tr.left, y: tr.top, width: tr.width, height: tr.height }, 1)) {
            out.push({ slide: s.id, callout: c.textContent,
                       covers: t.tagName.toLowerCase() === "text" ? (t.textContent || "").trim() : t.tagName.toLowerCase() });
          }
        });
      });
    });
    return out;
  };

  /* ---- start ----------------------------------------------------------- */
  if (shot) document.body.classList.add("shot");
  if (!shot && window.matchMedia && window.matchMedia("(hover: none)").matches && hint) {
    hint.textContent = "Swipe or tap the sides · tap the counter for all slides";
  }
  fit();
  fitLayout();
  var want = params.get("slide");
  if (want && indexOf(want) >= 0) show(indexOf(want), false);
  else if (location.hash) { show(0, false); fromHash(); }
  else show(0, false);
  if (!shot) { showHint(); takeFocus(); }

  function report(data) {
    var pre = document.getElementById("deck-check") || document.createElement("pre");
    pre.id = "deck-check";
    pre.textContent = JSON.stringify(data);
    document.body.appendChild(pre);
  }
  var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
  /* When web fonts arrive, refit (viewing only). The check modes below never
     wait for them: font loading is real network and decode I/O, which
     headless Chrome's --virtual-time-budget does not wait for, so a check
     that awaited it could be dumped before it wrote its result. A check
     measures the fonts present at load, synchronously. */
  if (!params.get("check")) ready.then(fitLayout, function () {});

  if (params.get("check") === "1") {
    var done = function () {
      fitLayout();
      report({ slides: slides.map(function (s) { return s.id; }), overflow: window.__deckOverflow(),
               callouts: window.__deckCallouts(), fill: window.__deckFill(), blank: window.__deckBlank(),
               reach: window.__deckReach(),
               ui: window.__deckUI() });
    };
    /* &fonts=1 (manual verification only, never in tests): wait for web
       fonts and refit first, to measure what a reader with fonts sees. */
    if (params.get("fonts") === "1") ready.then(function () { fitLayout(); done(); }, done);
    else done();
  }

  /* ?check=ui: each step through the controls a reader would use, and what
     the chrome showed after it. Events are dispatched as a browser would. */
  if (checkUi) {
    var drive = function () {
      var steps = [];
      var at = function (name) { var u = window.__deckUI(); u.step = name; steps.push(u); };
      var clickAt = function (x, y) {
        var el = document.elementFromPoint(x, y) || document.body;
        el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, clientX: x, clientY: y,
                                                   button: 0, detail: 1 }));
      };
      var key = function (k) {
        document.body.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
      };
      var r = function () { return stage.getBoundingClientRect(); };
      at("load");
      if (shot) { report({ slides: slides.map(function (s) { return s.id; }), steps: steps }); return; }
      nextBtn.click(); at("next button");
      prevBtn.click(); at("previous button");
      clickAt(r().right - r().width / 6, r().top + r().height / 2);
      setTimeout(function () {
        at("right third");
        clickAt(r().left + r().width / 6, r().top + r().height / 2);
        setTimeout(function () {
          at("left third");
          key("g"); at("G");
          key("Escape"); at("Escape");
          counter.click(); at("counter");
          var mid = Math.floor(slides.length / 2);
          var th = grid.querySelectorAll(".thumb")[mid];
          th.click(); at("thumbnail " + (mid + 1));
          report({ slides: slides.map(function (s) { return s.id; }), steps: steps });
        }, 400);
      }, 400);
    };
    /* The cover's hint turns on in an animation-frame callback registered
       at start-up; this one is registered after it, and callbacks in a frame
       run in the order they were registered, so the drive always sees the
       hint on. No timer races a frame, and nothing waits for real I/O. */
    requestAnimationFrame(drive);
  }
})();
