/* arch-doc review site runtime.
   Two comment paths:
   - published as an Artifact with the comments and db capabilities: the page posts anchored threads
     (each body starts with "[anchor] <section>") and keeps review status in db collection "review";
   - opened as a local file (or wherever window.claude.use resolves null): comments and status stay
     in this browser's localStorage, and "Export comments" hands them to the author as JSON for
     `archdoc comments import`.
   Kept ASCII-only so the page reads the same with no charset declared. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const META = JSON.parse($("#doc-meta").textContent);
  const docEl = $("#doc");
  const oiEl = document.getElementById(META.open_items);
  const cmEl = document.getElementById(META.comments_panel);
  const FRAMED = !!(window.claude && typeof window.claude.use === "function");
  const ELLIPSIS = "\u2026", LQ = "\u201c", RQ = "\u201d", DOT = " \u00b7 ";

  /* ------------------------------------------------ browser storage (per document and version) */
  const KEY = "archdoc:" + META.key + ":";
  const store = {
    get(k, d) {
      try { const v = window.localStorage.getItem(KEY + k); return v == null ? d : JSON.parse(v); }
      catch (e) { return d; }
    },
    set(k, v) {
      try { window.localStorage.setItem(KEY + k, JSON.stringify(v)); return true; }
      catch (e) { return false; }
    },
  };

  /* ------------------------------------------------ anchor -> section label, document order */
  const sectionOf = new Map();
  const orderOf = new Map();
  let curLabel = "";
  $$("[data-anchor]", docEl).forEach((el, i) => {
    if (el.classList.contains("h-row")) curLabel = el.dataset.label || "";
    sectionOf.set(el.dataset.anchor, curLabel);
    orderOf.set(el.dataset.anchor, i);
  });
  const anchorEl = (id) => docEl.querySelector('[data-anchor="' + CSS.escape(id) + '"]');
  const commentTarget = (id) => {
    const a = anchorEl(id);
    if (!a) return null;
    if (a.classList.contains("h-row")) return a.querySelector("h1,h2") || a;
    return a;
  };
  const headingFor = (id) => {
    let a = id;
    while (a) {
      const el = anchorEl(a);
      if (el && el.classList.contains("h-row")) return a;
      if (a.indexOf("-") < 0) break;
      a = a.slice(0, a.lastIndexOf("-"));
    }
    return null;
  };

  /* ------------------------------------------------ capabilities */
  const use = (name) => (FRAMED ? Promise.resolve(window.claude.use(name)).catch(() => null) : Promise.resolve(null));
  let comments = null, commentsKnown = false, pageWrites = true;
  use("comments").then((c) => { comments = c; commentsKnown = true; applyMode(); });
  use("db").then((d) => startReview(d));
  // Hosted, a page may only hand the viewer a file through the downloads capability. Until it
  // answers (and when it answers null) the Export button stays hidden rather than doing nothing.
  let downloads = null, downloadsKnown = !FRAMED;
  use("downloads").then((d) => { downloads = d; downloadsKnown = true; applyMode(); });
  const canExport = () => !FRAMED || (downloadsKnown && !!downloads);

  const modeEl = $("#tb-mode");
  function applyMode() {
    const local = !comments;
    // Published, comments live in the shared store: the browser-only panel and its export do not apply.
    $("#cm-btn").hidden = !local;
    $("#cm-export").hidden = !local || !canExport();
    $("#cm-copyjson").hidden = !local;
    $("#cm-json").hidden = true;
    if (!local && !cmEl.hidden) { history.replaceState(null, "", "#top"); route(); }
    modeEl.textContent = local
      ? "This copy keeps your comments and review status in this browser. Open My comments to export them for the author."
      : "Comments post to this page's comment threads, where everyone with access sees them.";
    if (cmp.open) refreshComposerActions();
  }

  /* ------------------------------------------------ local comments */
  let local = store.get("comments", []);
  if (!Array.isArray(local)) local = [];
  const newId = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID()
    : Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10));

  function paintNoted() {
    $$(".noted").forEach((e) => e.classList.remove("noted"));
    local.forEach((c) => { const el = anchorEl(c.anchor); if (el) el.classList.add("noted"); });
    $("#cm-count").textContent = String(local.length);
  }

  /* ------------------------------------------------ composer */
  const cmp = {
    open: false, id: null, el: null, range: null, quote: "",
    box: $("#composer"), ref: $("#cmp-ref"), where: $("#cmp-where"), q: $("#cmp-quote"),
    text: $("#cmp-text"), msg: $("#cmp-msg"), nameRow: $("#cmp-name-row"), name: $("#cmp-name"),
    claude: $("#cmp-claude"), post: $("#cmp-post"), save: $("#cmp-save"), native: $("#cmp-native"), copy: $("#cmp-copy"),
  };
  cmp.name.value = store.get("author", "") || "";

  function setMsg(text, kind) {
    cmp.msg.textContent = text || "";
    cmp.msg.className = "cmp-msg" + (kind ? " " + kind : "");
  }
  function clearHit() { $$(".hit").forEach((e) => e.classList.remove("hit")); }
  function clip(s, n) { return s.length > n ? s.slice(0, n - 1).trimEnd() + ELLIPSIS : s; }
  const figLabel = (el) => (el && el.matches("figure") ? el.dataset.label : "");

  function openComposer(id, range, quote) {
    const el = commentTarget(id);
    if (!el) return;
    clearHit();
    (anchorEl(id) || el).classList.add("hit");
    cmp.open = true; cmp.id = id; cmp.el = el; cmp.range = range || null; cmp.quote = (quote || "").trim();
    cmp.ref.textContent = id;
    cmp.where.textContent = [figLabel(el), sectionOf.get(id) || ""].filter(Boolean).join(DOT);
    cmp.q.hidden = !cmp.quote;
    cmp.q.textContent = cmp.quote ? LQ + clip(cmp.quote, 700) + RQ : "";
    setMsg("");
    cmp.box.hidden = false;
    refreshComposerActions();
    cmp.text.focus({ preventScroll: true });
  }
  function closeComposer() { cmp.open = false; cmp.box.hidden = true; cmp.range = null; clearHit(); }

  async function refreshComposerActions() {
    const isLocal = !comments;
    cmp.save.hidden = !isLocal;
    cmp.nameRow.hidden = !isLocal;
    cmp.post.hidden = isLocal || !pageWrites;
    cmp.native.hidden = isLocal;
    cmp.claude.hidden = true;
    if (isLocal) {
      if (FRAMED && !commentsKnown) setMsg("Connecting to comments" + ELLIPSIS);
      else if (!cmp.msg.textContent) setMsg("Saved in this browser. Export them from My comments.");
      return;
    }
    if (!pageWrites) return;
    try {
      const s = await comments.canSendToClaude();
      cmp.claude.hidden = s !== "available";
      cmp.post.classList.toggle("primary", s !== "available");
    } catch (e) { cmp.claude.hidden = true; cmp.post.classList.add("primary"); }
  }

  function citation() {
    const fig = figLabel(cmp.el);
    const label = (fig ? fig + DOT : "") + (sectionOf.get(cmp.id) || "");
    let s = ("[" + cmp.id + "] " + label).trim();
    if (cmp.quote) s += "\n" + LQ + clip(cmp.quote, 700) + RQ;
    return s;
  }
  function commentText() {
    const note = cmp.text.value.trim();
    let text = citation() + (note ? "\n\n" + note : "");
    const enc = new TextEncoder();
    while (enc.encode(text).length > 4000 && cmp.quote.length > 40) {
      cmp.quote = cmp.quote.slice(0, Math.floor(cmp.quote.length * 0.7));
      text = citation() + (note ? "\n\n" + note : "");
    }
    return { note, text };
  }

  const ERR = {
    consent_required: "Not posted. Allow this page to comment for you when asked, then try again. Your note is kept.",
    forbidden: "Commenting from the page is off for you here. Use Open in comment panel instead.",
    invalid: "The comment was rejected. Check it is not empty and under 4 KB.",
    rate_limited: "Too many comments in a short time. Wait a moment, then post again.",
    unavailable: "Comments are unavailable right now. Try once more in a moment.",
    upstream_error: "The comment may not have posted. Check the comment panel before trying again.",
    claude_unavailable: "Could not send to Claude from here, so nothing was posted. Post it as a plain comment instead.",
  };

  async function submit(toClaude) {
    if (!comments || !cmp.el) return;
    const { note, text } = commentText();
    if (!note) { setMsg("Write a note first.", "err"); cmp.text.focus(); return; }
    cmp.post.disabled = cmp.claude.disabled = true;
    setMsg(toClaude ? "Sending to Claude" + ELLIPSIS : "Posting" + ELLIPSIS);
    try {
      const anchor = await comments.anchorFor(cmp.el);
      if (toClaude) await comments.sendToClaude({ anchor, text });
      else await comments.create({ anchor, text });
      cmp.text.value = "";
      setMsg((toClaude ? "Sent to Claude on " : "Posted on ") + cmp.id + ".", "ok");
      setTimeout(() => { if (cmp.msg.classList.contains("ok")) closeComposer(); }, 1400);
    } catch (e) {
      const code = (e && e.code) || "upstream_error";
      if (["forbidden", "not_granted", "capability_disabled", "capability_removed"].includes(code)) {
        pageWrites = false;
        refreshComposerActions();
      }
      setMsg(ERR[code] || ERR.upstream_error, "err");
    } finally {
      cmp.post.disabled = cmp.claude.disabled = false;
    }
  }

  function saveLocal() {
    if (!cmp.el) return;
    const note = cmp.text.value.trim();
    if (!note) { setMsg("Write a note first.", "err"); cmp.text.focus(); return; }
    const author = cmp.name.value.trim();
    store.set("author", author);
    const entry = {
      id: newId(), anchor: cmp.id, section: sectionOf.get(cmp.id) || "", label: figLabel(cmp.el) || "",
      quote: cmp.quote ? clip(cmp.quote, 700) : "", text: note, author: author, at: new Date().toISOString(),
    };
    local.push(entry);
    if (!store.set("comments", local)) {
      local.pop();
      setMsg("This browser blocks saving here, so the comment was not kept. Copy reference and send it instead.", "err");
      return;
    }
    cmp.text.value = "";
    paintNoted();
    renderComments();
    setMsg("Saved on " + cmp.id + ". " + local.length + " comment" + (local.length === 1 ? "" : "s") + " in this browser.", "ok");
    setTimeout(() => { if (cmp.msg.classList.contains("ok")) closeComposer(); }, 1400);
  }

  cmp.post.addEventListener("click", () => submit(false));
  cmp.claude.addEventListener("click", () => submit(true));
  cmp.save.addEventListener("click", saveLocal);
  cmp.native.addEventListener("click", async () => {
    if (!comments) return;
    const target = cmp.range && cmp.range.startContainer.isConnected ? { range: cmp.range } : { element: cmp.el };
    try {
      const r = await comments.openComposer(target);
      if (r && r.opened) closeComposer();
      else setMsg("The comment panel is busy with another draft. Finish or discard it first.");
    } catch (e) {
      setMsg(e && e.code === "rate_limited" ? ERR.rate_limited : "The comment panel is not available in this view.", "err");
      if (e && e.code === "unavailable") cmp.native.hidden = true;
    }
  });
  cmp.copy.addEventListener("click", () => copyText(commentText().text, cmp.text, (m, k) => setMsg(m, k)));
  $("#cmp-close").addEventListener("click", closeComposer);
  cmp.box.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeComposer();
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      if (!comments) saveLocal(); else submit(!cmp.claude.hidden);
    }
  });

  function copyText(t, area, say) {
    const fallback = () => {
      if (area === cmp.text) {
        if (!cmp.open) return;
        cmp.text.value = t + (cmp.text.value ? "\n\n" + cmp.text.value : "");
      } else { area.hidden = false; area.value = t; }
      area.focus(); area.select();
      say("Copying is blocked here. The text is selected; copy it from there.");
    };
    try { navigator.clipboard.writeText(t).then(() => say("Copied.", "ok"), fallback); }
    catch (e) { fallback(); }
  }

  /* entry points: anchor tags, heading and figure buttons */
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-ref]");
    if (b && (b.classList.contains("ref") || b.classList.contains("h-act") || b.classList.contains("fig-btn"))) {
      e.preventDefault();
      openComposer(b.dataset.ref, null, "");
    }
  });

  /* ------------------------------------------------ selection -> Comment */
  const pop = $("#sel-pop");
  let selState = null;
  function onSelect() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { pop.hidden = true; return; }
    const range = sel.getRangeAt(0);
    const text = sel.toString().trim();
    if (!text) { pop.hidden = true; return; }
    let node = range.startContainer;
    if (node.nodeType !== 1) node = node.parentElement;
    if (!node || !docEl.contains(node) || docEl.hidden) { pop.hidden = true; return; }
    const blk = node.closest("[data-anchor]");
    if (!blk) { pop.hidden = true; return; }
    selState = { id: blk.dataset.anchor, range: range.cloneRange(), text };
    const r = range.getBoundingClientRect();
    pop.hidden = false;
    const pw = pop.offsetWidth;
    const left = Math.min(Math.max(8, r.left + window.scrollX + r.width / 2 - pw / 2), document.documentElement.clientWidth - pw - 8);
    const top = r.top + window.scrollY - pop.offsetHeight - 8;
    pop.style.left = left + "px";
    pop.style.top = (top < window.scrollY + 60 ? r.bottom + window.scrollY + 8 : top) + "px";
  }
  document.addEventListener("mouseup", (e) => { if (!pop.contains(e.target) && !cmp.box.contains(e.target)) setTimeout(onSelect, 0); });
  document.addEventListener("keyup", (e) => { if (e.shiftKey && !cmp.box.contains(e.target)) onSelect(); });
  document.addEventListener("touchend", () => setTimeout(onSelect, 250));
  document.addEventListener("selectionchange", () => {
    const s = window.getSelection();
    if (s && s.isCollapsed && !pop.matches(":hover")) pop.hidden = true;
  });
  pop.addEventListener("mousedown", (e) => e.preventDefault());
  $("#sel-comment").addEventListener("click", () => {
    if (!selState) return;
    pop.hidden = true;
    openComposer(selState.id, selState.range, selState.text);
  });
  $("#sel-copy").addEventListener("click", () => {
    if (!selState) return;
    pop.hidden = true;
    openComposer(selState.id, selState.range, selState.text);
    copyText(commentText().text, cmp.text, (m, k) => setMsg(m, k));
  });

  /* ------------------------------------------------ lightbox with pan and zoom */
  const lb = { box: $("#lightbox"), stage: $("#lb-stage"), img: $("#lb-img"), title: $("#lb-title"), zoom: $("#lb-zoom"),
    s: 1, x: 0, y: 0, id: null, pointers: new Map(), pinch: null, opener: null, blob: null };

  function lbApply() {
    lb.img.style.transform = "translate(" + lb.x + "px, " + lb.y + "px) scale(" + lb.s + ")";
    lb.zoom.textContent = Math.round(lb.s * 100) + "%";
  }
  function lbSize() { return { sw: lb.stage.clientWidth, sh: lb.stage.clientHeight, iw: lb.img.naturalWidth || 1, ih: lb.img.naturalHeight || 1 }; }
  function lbFit(mode) {
    const { sw, sh, iw, ih } = lbSize();
    const pad = 24;
    if (mode === "actual") lb.s = 1;
    else if (mode === "width") lb.s = (sw - pad * 2) / iw;
    else lb.s = Math.min((sw - pad * 2) / iw, (sh - pad * 2) / ih);
    lb.x = (sw - iw * lb.s) / 2;
    lb.y = mode === "fit" ? (sh - ih * lb.s) / 2 : pad;
    lbApply();
  }
  function lbZoomAt(f, cx, cy) {
    const ns = Math.min(8, Math.max(0.05, lb.s * f));
    lb.x = cx - (cx - lb.x) * (ns / lb.s);
    lb.y = cy - (cy - lb.y) * (ns / lb.s);
    lb.s = ns;
    lbApply();
  }
  function svgSource(fig) {
    const svg = fig.querySelector(".fig-mmd svg");
    if (!svg) return null;
    const c = svg.cloneNode(true);
    const vb = svg.viewBox && svg.viewBox.baseVal;
    const w = vb && vb.width ? vb.width : svg.getBoundingClientRect().width;
    const h = vb && vb.height ? vb.height : svg.getBoundingClientRect().height;
    c.setAttribute("width", String(Math.round(w * 2)));
    c.setAttribute("height", String(Math.round(h * 2)));
    c.removeAttribute("style");
    c.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const blob = new Blob([new XMLSerializer().serializeToString(c)], { type: "image/svg+xml" });
    return URL.createObjectURL(blob);
  }
  function openLightbox(id) {
    const fig = document.getElementById(id);
    if (!fig) return;
    const im = fig.querySelector("img");
    let src = im ? (im.dataset.full || im.src) : svgSource(fig);
    if (!src) return;
    if (!im) lb.blob = src;
    lb.id = id; lb.opener = document.activeElement;
    lb.title.textContent = (fig.dataset.label || id) + DOT + id;
    lb.box.hidden = false;
    document.documentElement.style.overflow = "hidden";
    const start = () => {
      const { sw, sh, iw, ih } = lbSize();
      lbFit(ih * ((sw - 48) / iw) > sh * 1.25 ? "width" : "fit");
    };
    lb.img.onload = start;
    lb.img.onerror = () => { if (im && lb.img.src !== im.currentSrc) lb.img.src = im.currentSrc || im.src; };
    lb.img.alt = im ? im.alt : fig.dataset.label || id;
    lb.img.src = src;
    if (lb.img.complete && lb.img.naturalWidth) start();
    $('[data-lb="close"]').focus();
  }
  function closeLightbox() {
    lb.box.hidden = true; lb.img.removeAttribute("src");
    if (lb.blob) { URL.revokeObjectURL(lb.blob); lb.blob = null; }
    document.documentElement.style.overflow = "";
    if (lb.opener && lb.opener.focus) lb.opener.focus();
  }
  document.addEventListener("click", (e) => {
    const z = e.target.closest("[data-zoom]");
    if (z) { e.preventDefault(); openLightbox(z.dataset.zoom); }
  });
  $$("[data-lb]").forEach((b) => b.addEventListener("click", () => {
    const a = b.dataset.lb, { sw, sh } = lbSize();
    if (a === "close") closeLightbox();
    else if (a === "in") lbZoomAt(1.25, sw / 2, sh / 2);
    else if (a === "out") lbZoomAt(0.8, sw / 2, sh / 2);
    else if (a === "comment") { const id = lb.id; closeLightbox(); openComposer(id, null, ""); }
    else lbFit(a);
  }));
  lb.stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = lb.stage.getBoundingClientRect();
    if (e.ctrlKey || e.metaKey || e.altKey) {
      lbZoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002)), e.clientX - r.left, e.clientY - r.top);
    } else { lb.x -= e.deltaX; lb.y -= e.deltaY; lbApply(); }
  }, { passive: false });
  lb.stage.addEventListener("dblclick", (e) => {
    const r = lb.stage.getBoundingClientRect();
    lbZoomAt(e.shiftKey ? 0.5 : 2, e.clientX - r.left, e.clientY - r.top);
  });
  lb.stage.addEventListener("pointerdown", (e) => {
    lb.stage.setPointerCapture(e.pointerId);
    lb.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    lb.stage.classList.add("drag");
    if (lb.pointers.size === 2) {
      const [a, b] = [...lb.pointers.values()];
      lb.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), s: lb.s };
    }
  });
  lb.stage.addEventListener("pointermove", (e) => {
    const p = lb.pointers.get(e.pointerId);
    if (!p) return;
    const nx = e.clientX, ny = e.clientY;
    if (lb.pointers.size === 1) { lb.x += nx - p.x; lb.y += ny - p.y; lbApply(); }
    else if (lb.pointers.size === 2 && lb.pinch) {
      lb.pointers.set(e.pointerId, { x: nx, y: ny });
      const [a, b] = [...lb.pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      const r = lb.stage.getBoundingClientRect();
      lbZoomAt((lb.pinch.s * d / lb.pinch.d) / lb.s, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
      return;
    }
    lb.pointers.set(e.pointerId, { x: nx, y: ny });
  });
  const endPtr = (e) => {
    lb.pointers.delete(e.pointerId);
    if (lb.pointers.size < 2) lb.pinch = null;
    if (!lb.pointers.size) lb.stage.classList.remove("drag");
  };
  lb.stage.addEventListener("pointerup", endPtr);
  lb.stage.addEventListener("pointercancel", endPtr);
  document.addEventListener("keydown", (e) => {
    if (lb.box.hidden) return;
    const { sw, sh } = lbSize();
    const k = e.key;
    if (k === "Escape") closeLightbox();
    else if (k === "+" || k === "=") lbZoomAt(1.25, sw / 2, sh / 2);
    else if (k === "-") lbZoomAt(0.8, sw / 2, sh / 2);
    else if (k === "0") lbFit("fit");
    else if (k === "ArrowUp") { lb.y += 80; lbApply(); }
    else if (k === "ArrowDown") { lb.y -= 80; lbApply(); }
    else if (k === "ArrowLeft") { lb.x += 80; lbApply(); }
    else if (k === "ArrowRight") { lb.x -= 80; lbApply(); }
    else return;
    e.preventDefault();
  });
  window.addEventListener("resize", () => { if (!lb.box.hidden) lbFit("fit"); });

  /* ------------------------------------------------ Mermaid figures without a rendered file */
  const pending = () => $$("pre.mermaid").filter((p) => !p.querySelector("svg"));
  function loadMermaid() {
    if (!pending().length || window.mermaid) return;
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js";
    s.onload = () => {
      try {
        window.mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
        window.mermaid.run({ nodes: pending() });
      } catch (e) { /* the source stays visible as text */ }
    };
    document.head.appendChild(s);
  }
  if ($("pre.mermaid")) {
    // A viewer renders Mermaid blocks itself; a local file needs the library.
    if (FRAMED) setTimeout(loadMermaid, 2500); else loadMermaid();
  }

  /* ------------------------------------------------ navigation, routing, scrollspy */
  const nav = $("#sidenav"), toggle = $("#nav-toggle");
  toggle.addEventListener("click", () => {
    const open = !nav.classList.contains("open");
    nav.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  });
  nav.addEventListener("click", (e) => {
    if (e.target.closest("a") && window.matchMedia("(max-width: 960px)").matches) {
      nav.classList.remove("open"); toggle.setAttribute("aria-expanded", "false");
    }
  });

  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    const panel = h === META.open_items ? oiEl : h === META.comments_panel && !comments ? cmEl : null;
    oiEl.hidden = panel !== oiEl;
    cmEl.hidden = panel !== cmEl;
    docEl.hidden = !!panel;
    if (panel) {
      if (cmp.open) closeComposer();
      if (panel === cmEl) renderComments();
      window.scrollTo(0, 0);
      return;
    }
    if (!h) return;
    const el = document.getElementById(h);
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollIntoView({ block: el.matches("figure,.tbl,.titleblock") ? "start" : "center" });
      clearHit();
      const a = el.closest("[data-anchor]") || el;
      a.classList.add("hit");
      setTimeout(() => { if (!cmp.open) clearHit(); }, 2600);
      spy();
    });
  }
  window.addEventListener("hashchange", route);

  const navLinks = new Map($$("[data-nav]", nav).map((a) => [a.dataset.nav, a]));
  const heads = $$(".h-row h1[id], .h-row h2[id]", docEl);
  let active = null, ticking = false;
  function spy() {
    ticking = false;
    if (docEl.hidden) return;
    let cur = null;
    for (const h of heads) { if (h.getBoundingClientRect().top < 120) cur = h; else break; }
    const a = cur ? navLinks.get(cur.id) : null;
    if (a === active) return;
    if (active) active.classList.remove("on");
    active = a;
    if (!a) return;
    a.classList.add("on");
    const r = a.getBoundingClientRect(), nr = nav.getBoundingClientRect();
    if (r.top < nr.top + 40 || r.bottom > nr.bottom - 40) nav.scrollTop += r.top - nr.top - nr.height / 3;
  }
  window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(spy); } }, { passive: true });

  /* open items: group by section or by owner */
  $$(".seg[data-group]", oiEl).forEach((b) => b.addEventListener("click", () => {
    $$(".seg[data-group]", oiEl).forEach((x) => x.classList.toggle("on", x === b));
    $$(".oi-view", oiEl).forEach((v) => { v.hidden = v.dataset.view !== b.dataset.group; });
  }));

  /* ------------------------------------------------ review status: db when granted, else this browser */
  const LABEL = { "": "Not reviewed", "in-review": "In review", changes: "Changes needed", agreed: "Agreed" };
  const selects = $$("select.rs");
  let status = {}, backend = null, dbRef = null;
  let localReview = store.get("review", {});
  if (!localReview || typeof localReview !== "object" || Array.isArray(localReview)) localReview = {};
  selects.forEach((s) => { s.disabled = true; });

  function paintReview() {
    selects.forEach((s) => {
      const v = status[s.dataset.sec] || "";
      if (document.activeElement !== s) s.value = v;
      s.dataset.s = v;
    });
    $$("[data-dot]").forEach((d) => { const v = status[d.dataset.dot] || ""; d.dataset.s = v; d.title = LABEL[v]; });
    const vals = Object.values(status);
    const n = (k) => vals.filter((v) => v === k).length;
    $("#progress").textContent = n("agreed") + " of " + selects.length + " agreed" + DOT + n("changes") + " need changes"
      + DOT + n("in-review") + " in review" + (backend === "local" ? " (this browser)" : "");
  }
  function useLocalReview() {
    backend = "local";
    status = {};
    Object.keys(localReview).forEach((k) => { const v = localReview[k]; if (v && v.status) status[k] = v.status; });
    selects.forEach((s) => { s.disabled = false; s.title = "Review status, kept in this browser"; });
    paintReview();
  }
  function startReview(db) {
    if (!db) { useLocalReview(); return; }
    dbRef = db;
    try {
      db.collection(META.review_collection).onSnapshot((snap) => {
        backend = "db";
        status = {};
        snap.docs.forEach((d) => { const v = d.data(); if (v && v.status) status[d.id] = v.status; });
        selects.forEach((s) => { s.disabled = false; s.title = "Review status, shared with everyone on this page"; });
        paintReview();
      }, () => useLocalReview());
    } catch (e) { useLocalReview(); }
  }
  selects.forEach((s) => s.addEventListener("change", async () => {
    const sec = s.dataset.sec, v = s.value, prev = status[sec] || "";
    if (v) status[sec] = v; else delete status[sec];
    paintReview();
    const body = { status: v, section: sectionOf.get(sec) || sec, at: new Date().toISOString() };
    if (backend === "db") {
      try {
        const ref = dbRef.doc(META.review_collection + "/" + sec);
        if (v) await ref.set(body); else await ref.delete();
      } catch (e) {
        if (prev) status[sec] = prev; else delete status[sec];
        paintReview();
        s.title = "Status not saved: you may not have edit access to this page.";
      }
      return;
    }
    if (v) localReview[sec] = body; else delete localReview[sec];
    if (!store.set("review", localReview)) s.title = "This browser blocks saving here; the status lasts until you close the page.";
  }));

  /* ------------------------------------------------ My comments panel and export */
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let armed = null;
  function exportData() {
    return {
      format: "arch-doc-comments", version: 1,
      document: { title: META.title, short: META.short, version: META.version },
      exported: new Date().toISOString(), comments: local, review: localReview,
    };
  }
  function renderComments() {
    const reviewed = Object.keys(localReview).length;
    $("#cm-sum").textContent = local.length
      ? local.length + " comment" + (local.length === 1 ? "" : "s") + " and " + reviewed + " review status"
        + (reviewed === 1 ? "" : "es") + " kept in this browser. Export them and send the file to the author."
      : (reviewed ? reviewed + " review status" + (reviewed === 1 ? "" : "es") + " kept in this browser, and no comments yet. "
        : "No comments yet. ") + "Select text, or use a reference tag or Comment button, to add one.";
    const groups = new Map();
    local.slice().sort((a, b) => (orderOf.get(a.anchor) ?? 1e9) - (orderOf.get(b.anchor) ?? 1e9) || (a.at < b.at ? -1 : 1))
      .forEach((c) => { const k = headingFor(c.anchor) || ""; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(c); });
    const out = [];
    groups.forEach((list, head) => {
      const title = head ? sectionOf.get(head) || head : "Anchors not in this version";
      out.push('<h3 class="oi-sec">' + (head ? '<a href="#' + esc(head) + '">' + esc(title) + "</a>" : esc(title)) + "</h3>");
      list.forEach((c) => {
        out.push('<div class="cm-item"><a class="oi-link" href="#' + esc(c.anchor) + '"><code>' + esc(c.anchor) + "</code></a><div class=\"oi-body\">"
          + (c.quote ? '<p class="cm-quote">' + esc(c.quote) + "</p>" : "")
          + '<p class="cm-text">' + esc(c.text) + "</p>"
          + '<div class="cm-meta">' + (c.label ? "<span>" + esc(c.label) + "</span>" : "")
          + (c.author ? "<span>" + esc(c.author) + "</span>" : "")
          + "<span>" + esc(new Date(c.at).toLocaleString()) + "</span>"
          + '<button type="button" class="cm-del" data-del="' + esc(c.id) + '">Delete</button></div></div></div>');
      });
    });
    $("#cm-list").innerHTML = out.join("");
  }
  $("#cm-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]");
    if (!b) return;
    if (armed !== b.dataset.del) {
      armed = b.dataset.del;
      $$(".cm-del.armed").forEach((x) => { x.classList.remove("armed"); x.textContent = "Delete"; });
      b.classList.add("armed"); b.textContent = "Delete this comment";
      return;
    }
    local = local.filter((c) => c.id !== armed);
    armed = null;
    store.set("comments", local);
    paintNoted();
    renderComments();
  });
  const say = (m, kind) => { const el = $("#cm-msg"); el.textContent = m; el.className = "cmp-msg" + (kind ? " " + kind : ""); };
  const SAVE_ERR = {
    declined: "Not saved. Export again when you want the file.",
    rate_limited: "A save prompt is already open. Answer it, then try again.",
    too_large: "The file is too large to save here. Use Copy as JSON instead.",
  };
  $("#cm-export").addEventListener("click", async () => {
    if (comments || !canExport()) return;
    const text = JSON.stringify(exportData(), null, 2);
    const filename = META.short + "-v" + META.version + "-comments.json";
    const area = $("#cm-json");
    const n = local.length + " comment" + (local.length === 1 ? "" : "s");
    if (FRAMED) {
      say("Confirm the save to download " + n + ELLIPSIS);
      try {
        await downloads.save({ filename, data: text });
        say("Saved " + n + " as " + filename + ". Send the file to the author.", "ok");
      } catch (e) {
        const code = (e && e.code) || "unavailable";
        if (SAVE_ERR[code]) { say(SAVE_ERR[code], code === "declined" ? "" : "err"); return; }
        $("#cm-export").hidden = true;   // saving is not possible in this view; do not leave a dead button
        say("Saving files is not available here. Use Copy as JSON and send it to the author.", "err");
      }
      return;
    }
    try {
      const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      say("Exported " + n + ". Send the file to the author.", "ok");
    } catch (e) {
      area.hidden = false; area.value = text; area.select();
      say("The download did not start. Copy the selected JSON into a file instead.");
    }
  });
  $("#cm-copyjson").addEventListener("click", () => {
    copyText(JSON.stringify(exportData(), null, 2), $("#cm-json"), (m) => say(m === "Copied." ? "Copied the comments as JSON." : m));
  });

  /* ------------------------------------------------ start */
  applyMode();
  paintNoted();
  route();
  spy();
})();
