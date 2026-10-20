"""The review site (SPEC 6.2): one self-contained page rendered from the
parsed :class:`~archdoc.project.Project`.

``build(project, out_dir=None)`` writes ``<out>/site/``:

- ``index.html``: the page, with ``assets/site.css`` and ``assets/site.js``
  inlined and the theme built from the profile's ``house`` tokens;
- ``media/<anchor>.<ext>``: each figure and view, downscaled to 1600 px wide
  for the page, and ``media/full/<anchor>.<ext>``, the original, for the
  lightbox;
- ``PUBLISH.md``: the Artifact publish call and the comment read-back steps.

Every heading, paragraph, list item, table row and figure carries the
anchor the core assigned (``s7``, ``s7-3-p2``, ``s7-3-t1-r4``, ``fig-4``,
``view-2``, ``dc``, ``app-open-items``), so a review comment names exactly
where it applies and ``archdoc comments import`` can place it again.

The page is written without a document skeleton, because the Artifact
publish wraps it in one. Every character outside ASCII is written as an
HTML character reference, so the page reads the same when it is opened as
a local file with no charset declared.
"""
from __future__ import annotations

import colorsys
import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

from . import content as C
from .content import ANCHOR_DC, ANCHOR_OPEN_ITEMS, inline_runs, plain
from .project import person_line
from .formatting import date_format, format_date, view_caption
from .registers import display, tbc_markers


def _date(project, value) -> str:
    return format_date(value, date_format(project))


def _dep_name(project, d: dict) -> str:
    """"the X design" (or "the X SAD" when the title already ends in a
    document noun), from the core's dependency reference."""
    if d.get("ref"):
        try:
            return project.dependency_reference(str(d["ref"]))
        except LookupError:
            pass
    return f"the {display(d.get('title'))} design"

ASSETS = Path(__file__).resolve().parent / "assets"
PAGE_W = 1600
TALL_ROWS = 14
WIDE_COLS = 5
ANCHOR_COMMENTS = "app-comments"
REVIEW_COLLECTION = "review"
STATUSES = (("", "Not reviewed"), ("in-review", "In review"), ("changes", "Changes needed"),
            ("agreed", "Agreed"))
RASTER = (".png", ".jpg", ".jpeg", ".gif", ".webp")
KIND_LABEL = {"solution": "Solution design", "capability": "Capability design"}

esc = html.escape


class SiteBuildError(RuntimeError):
    """Raised when the site cannot be built (a figure file cannot be read)."""


# ------------------------------------------------------------- anchor index

@dataclass(frozen=True)
class Place:
    """Where an anchor sits: ``label`` is the section label the page and
    comments use ("7.3 Component Design", "Document control"); ``order``
    sorts anchors in document order."""

    anchor: str
    label: str
    number: str | None
    title: str
    order: int


def block_anchors(b: C.Block) -> list[str]:
    """Every anchor a block carries: its own, then header, items and rows."""
    out = [b.anchor] if b.anchor else []
    if getattr(b, "header_anchor", None):
        out.append(b.header_anchor)
    out += list(getattr(b, "item_anchors", []) or [])
    out += list(getattr(b, "row_anchors", []) or [])
    return out


def anchor_index(project) -> dict[str, Place]:
    """Every anchor the site renders, in document order, to its place."""
    out: dict[str, Place] = {}

    def put(anchor: str, label: str, number: str | None, title: str) -> None:
        if anchor and anchor not in out:
            out[anchor] = Place(anchor, label, number, title, len(out))

    dc = "Document control"
    put(ANCHOR_DC, dc, None, dc)
    for i, (_, _, rows) in enumerate(_dc_tables(project), start=1):
        tid = f"{ANCHOR_DC}-t{i}"
        for a in [tid, f"{tid}-h"] + [f"{tid}-r{r}" for r in range(1, len(rows) + 1)]:
            put(a, dc, None, dc)
    for ch in project.chapters:
        clabel = f"{ch.number} {ch.title}"
        put(ch.anchor, clabel, str(ch.number), ch.title)
        for b in ch.lead:
            for a in block_anchors(b):
                put(a, clabel, str(ch.number), ch.title)
        for s in ch.sections:
            slabel = f"{s.number} {s.title}"
            put(s.anchor, slabel, s.number, s.title)
            for b in s.blocks:
                for a in block_anchors(b):
                    put(a, slabel, s.number, s.title)
    put(ANCHOR_OPEN_ITEMS, "Open items", None, "Open items")
    return out


def place_of(index: dict[str, Place], anchor: str) -> Place | None:
    """The place of an anchor, or of the nearest anchor it sits under when
    the anchor itself is not in this version (``s7-3-t1-r9`` falls back to
    ``s7-3-t1``, then ``s7-3``)."""
    a = anchor
    while a:
        if a in index:
            return index[a]
        if "-" not in a:
            break
        a = a.rsplit("-", 1)[0]
    return None


# ------------------------------------------------------------------- theme

def _rgb(hexv: str) -> tuple[float, float, float]:
    h = hexv.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: Iterable[float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def _mix(a: str, b: str, t: float) -> str:
    """``a`` moved ``t`` of the way toward ``b``."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(x + (y - x) * t for x, y in zip(ra, rb))


def _tone(hexv: str, lightness: float, sat_cap: float | None = None, sat_min: float = 0.0) -> str:
    """The colour's hue at a new lightness, saturation capped."""
    h, _, s = colorsys.rgb_to_hls(*_rgb(hexv))
    if sat_cap is not None:
        s = min(s, sat_cap)
    s = max(s, sat_min) if s > 0.02 else s
    return _hex(colorsys.hls_to_rgb(h, lightness, s))


def _lightness(hexv: str) -> float:
    return colorsys.rgb_to_hls(*_rgb(hexv))[1]


def theme_tokens(palette: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Light and dark colour tokens from the profile's house palette. Light
    uses the palette as given; dark keeps each colour's hue and moves its
    lightness, so the house accent stays recognisable on a dark ground."""
    p = palette
    paper, ink, accent = p["paper"], p["ink"], p["accent"]
    light = {
        "bg": paper,
        "surface": p["panel"],
        "raised": paper,
        "ink": ink,
        "muted": p["muted"],
        "faint": _mix(p["muted"], paper, 0.3),
        "line": p["rule"],
        "line-soft": _mix(p["rule"], paper, 0.5),
        "accent": accent,
        "accent-ink": _tone(accent, min(_lightness(accent), 0.36)),
        "accent-wash": p["accent_soft"],
        "on-accent": paper if _lightness(accent) < 0.6 else ink,
        "done": p["done"],
        "partial": p["partial"],
        "not-started": p["not_started"],
        "tbc": p["tbc"],
        "tbc-bg": _mix(p["tbc"], paper, 0.88),
        "tbc-ink": _tone(p["tbc"], min(_lightness(p["tbc"]), 0.3)),
        "tbc-line": _mix(p["tbc"], paper, 0.55),
        "plate": "#ffffff",
        "shadow": "rgba(15, 23, 42, .14)",
    }
    bg = _tone(ink, 0.085, 0.22)
    dark = {
        "bg": bg,
        "surface": _tone(ink, 0.12, 0.2),
        "raised": _tone(ink, 0.15, 0.2),
        "ink": _tone(ink, 0.92, 0.12),
        "muted": _tone(p["muted"], 0.72, 0.15),
        "faint": _tone(p["muted"], 0.55, 0.12),
        "line": _tone(p["rule"], 0.26, 0.15),
        "line-soft": _tone(p["rule"], 0.19, 0.15),
        "accent": _tone(accent, 0.68, 0.55, 0.3),
        "accent-ink": _tone(accent, 0.8, 0.5, 0.25),
        "accent-wash": _tone(accent, 0.2, 0.35),
        "on-accent": bg,
        "done": _tone(p["done"], 0.62, 0.5),
        "partial": _tone(p["partial"], 0.64, 0.7),
        "not-started": _tone(p["not_started"], 0.66, 0.12),
        "tbc": _tone(p["tbc"], 0.68, 0.65),
        "tbc-bg": _mix(_tone(p["tbc"], 0.45, 0.6), bg, 0.72),
        "tbc-ink": _tone(p["tbc"], 0.84, 0.6),
        "tbc-line": _tone(p["tbc"], 0.42, 0.5),
        "plate": _mix(paper, p["panel"], 0.6),
        "shadow": "rgba(0, 0, 0, .55)",
    }
    return light, dark


def _stack(name: str, role: str) -> str:
    q = f'"{name}"'
    if role == "mono":
        return f'{q}, ui-monospace, "SF Mono", Menlo, Consolas, monospace'
    if "serif" in name.lower() and "sans" not in name.lower():
        return f'{q}, Georgia, Cambria, "Times New Roman", serif'
    return f'{q}, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif'


def font_links(fonts: dict[str, str]) -> list[str]:
    """One Google Fonts stylesheet per family, so a family Google does not
    serve fails alone and its fallback stack takes over."""
    seen, out = set(), []
    for role in ("heading", "body", "mono"):
        name = fonts.get(role)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append("https://fonts.googleapis.com/css2?family=" + quote_plus(name) + ":wght@400;700&display=swap")
    return out


def theme_css(profile) -> str:
    light, dark = theme_tokens(profile.palette)
    fonts = profile.fonts
    def block(tokens):
        return " ".join(f"--{k}: {v};" for k, v in tokens.items())
    fl = (f'--font-head: {_stack(fonts["heading"], "heading")}; '
          f'--font-body: {_stack(fonts["body"], "body")}; '
          f'--font-mono: {_stack(fonts.get("mono") or "IBM Plex Mono", "mono")};')
    return (":root { " + block(light) + " " + fl + " }\n"
            "@media (prefers-color-scheme: dark) { :root:not([data-theme=\"light\"]) { "
            + block(dark) + " color-scheme: dark; } }\n"
            ":root[data-theme=\"dark\"] { " + block(dark) + " color-scheme: dark; }\n")


# ------------------------------------------------------------------ inline

def _mark_tbc(text: str, owner_of_bare: str | None = None) -> str:
    """Escape text, wrapping each TBC in a mark titled with its owner. A
    bare "TBC" takes ``owner_of_bare`` (a register row's accountable owner,
    which the row names once)."""
    out, pos = [], 0
    for start, end, tbc in tbc_markers(text):   # the core's one rule: "Every TBC has..." is not a marker
        out.append(esc(text[pos:start], quote=False))
        owner = tbc.owner or owner_of_bare
        t = esc(text[start:end], quote=False)
        title = f' title="Owner: {esc(owner)}"' if owner else ' title="No owner named"'
        out.append(f'<mark class="tbc"{title}>{t}</mark>')
        pos = end
    out.append(esc(text[pos:], quote=False))
    return "".join(out)


def inline_html(text: str, owner_of_bare: str | None = None) -> str:
    """Resolved block text (inline Markdown kept) as HTML."""
    out = []
    for t, styles, href in inline_runs(text or ""):
        h = f"<code>{esc(t, quote=False)}</code>" if "code" in styles else _mark_tbc(t, owner_of_bare)
        if "bold" in styles:
            h = f"<strong>{h}</strong>"
        if "em" in styles:
            h = f"<em>{h}</em>"
        if href:
            if href.startswith(("http://", "https://")):
                h = f'<a href="{esc(href)}" target="_blank" rel="noopener">{h}</a>'
            elif re.match(r"^#[A-Za-z0-9._~-]+$", href):
                h = f'<a href="{esc(href)}">{h}</a>'
        out.append(h)
    return "".join(out)


def _where_text(where) -> str:
    """A register filter in words: ``state is current or both``."""
    return "; ".join(f"{c.field.replace('_', ' ')} {'is' if c.op == '=' else 'is not'} {' or '.join(c.values)}"
                     for c in where.conditions)


# --------------------------------------------------------- document control

def _who(v) -> str:
    return person_line(v) if isinstance(v, dict) else display(v)


def _dc_tables(project) -> list[tuple[str, list[str], list[list[str]]]]:
    """The document-control tables: (caption, header, rows)."""
    cfg = project.config
    org = project.profile.get("org.name")
    rows = [["Title", project.title], ["Short name", project.short],
            ["Kind", KIND_LABEL.get(project.kind, project.kind)],
            ["Layer", "Logical" if project.layer == "logical" else "Logical and physical"],
            ["Version", project.version]]
    if cfg.get("date"):
        rows.append(["Date", _date(project, cfg["date"])])
    if org and str(org).strip().lower() not in ("none", "null"):
        rows.append(["Organisation", display(org)])
    if cfg.get("author"):
        rows.append(["Author", _who(cfg["author"])])
    if cfg.get("owner"):
        rows.append(["Owner", _who(cfg["owner"])])
    tables = [("Document", ["Field", "Value"], rows)]
    deps = [d for d in cfg.get("depends_on") or [] if isinstance(d, dict)]
    if deps:
        tables.append(("Designs this document depends on", ["Design", "Kind", "Version", "Reference"],
                       [[display(d.get("title")), KIND_LABEL.get(d.get("kind"), display(d.get("kind"))),
                         display(d.get("version")), display(d.get("ref"))] for d in deps]))
    hist = [h for h in cfg.get("history") or [] if isinstance(h, dict)]
    if hist:
        tables.append(("Version history", ["Date", "Version", "Author", "Change"],
                       [[_date(project, h.get("date")), display(h.get("version")), _who(h.get("author")),
                         display(h.get("change"))] for h in hist]))
    return tables


# ---------------------------------------------------------------- renderer

class Renderer:
    def __init__(self, project, site: Path):
        self.p = project
        self.site = site
        self.media = site / "media"
        self.full = self.media / "full"
        self.out: list[str] = []
        self.label = ""          # current section label for anchor tags
        self.number = ""         # current section number
        self.images: list[str] = []
        self.mermaid = 0
        self.index = anchor_index(project)

    # -- small pieces
    def ref(self, aid: str, short: str) -> str:
        return (f'<button class="ref" type="button" data-ref="{aid}" aria-label="Comment on {aid}" title="{aid}">'
                f'<span class="ref-sec">{esc(self.number)}</span><span class="ref-id">{esc(short)}</span></button>')

    def tools(self, sid: str, label: str) -> str:
        opts = "".join(f'<option value="{v}">{t}</option>' for v, t in STATUSES)
        return (f'<div class="h-tools">'
                f'<select class="rs" id="rs-{sid}" data-sec="{sid}" aria-label="Review status for {esc(label)}">'
                f'{opts}</select>'
                f'<button class="h-act" type="button" data-ref="{sid}" title="Comment on {esc(label)}">'
                f'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3h11v7.5H7L4 13v-2.5H2.5z"/></svg>'
                f'<span>Comment</span></button></div>')

    def heading(self, level: int, aid: str, num: str, title: str, label: str) -> str:
        n = f'<span class="num">{esc(num)}</span>' if num else ""
        return (f'<header class="h-row h-{level}" data-anchor="{aid}" data-label="{esc(label)}">'
                f'<h{level} id="{aid}" data-comment-target>{n}{esc(title)}</h{level}>'
                f'{self.tools(aid, label)}</header>')

    # -- blocks
    def block(self, b: C.Block) -> str:
        if isinstance(b, C.View) or isinstance(b, C.Figure):
            return self.figure(b)
        if isinstance(b, C.Table):  # plain, register and catalogue tables
            return self.table(b)
        if isinstance(b, C.Bullets):
            return self.bullets(b)
        if isinstance(b, C.Para):
            return (f'<p id="{b.anchor}" class="blk" data-anchor="{b.anchor}" data-comment-target>'
                    f'{self.ref(b.anchor, b.anchor.rsplit("-", 1)[1])}{inline_html(b.text)}</p>')
        raise SiteBuildError(f"{b.source}: no site rendering for block kind '{b.kind}'")

    def bullets(self, b: C.Bullets) -> str:
        tag = "ol" if b.ordered else "ul"
        counters: dict[int, int] = {}
        rows = []
        for i, (text, aid, level) in enumerate(zip(b.items, b.item_anchors, b.levels), start=1):
            for k in [k for k in counters if k > level]:
                del counters[k]
            counters[level] = counters.get(level, 0) + 1
            n = f' data-n="{counters[level]}."' if b.ordered else ""
            rows.append(f'<li id="{aid}" class="blk lv{min(level, 4)}" data-anchor="{aid}"{n} data-comment-target>'
                        f'{self.ref(aid, "i" + str(i))}{inline_html(text)}</li>')
        return f'<{tag} id="{b.anchor}" class="doc-list">{"".join(rows)}</{tag}>'

    def _row(self, cells: list[str], aid: str, short: str, tag: str, chip: str | None = None,
             status_col: int | None = None, rid: str | None = None, id_col: int | None = None,
             owner: str | None = None) -> str:
        out = []
        for ci, c in enumerate(cells):
            body = inline_html(c, owner)
            if chip and ci == status_col and c:
                body = f'<span class="chip" data-chip="{chip}">{body}</span>'
            cls = ' class="rid"' if ci == id_col else ""
            out.append(f"<{tag}{cls}>{body}</{tag}>")
        extra = f' data-record="{esc(rid)}"' if rid else ""
        return (f'<tr id="{aid}" data-anchor="{aid}"{extra} data-comment-target>'
                f'<{tag} class="rref">{self.ref(aid, short)}</{tag}>{"".join(out)}</tr>')

    def table_html(self, tid: str, header: list[str], rows: list[list[str]], header_anchor: str,
                   row_anchors: list[str], caption: str, chips: list[str] | None = None,
                   status_col: int | None = None, records: list | None = None, id_col: int | None = None) -> str:
        ncols = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
        head = self._row(header + [""] * (ncols - len(header)), header_anchor, "h", "th", id_col=id_col)
        body = []
        for i, (r, aid) in enumerate(zip(rows, row_anchors)):
            body.append(self._row(r + [""] * (ncols - len(r)), aid, f"r{i + 1}", "td",
                                  chips[i] if chips else None, status_col,
                                  records[i].id if records else None, id_col,
                                  records[i].accountable if records else None))
        if not rows:
            body.append(f'<tr class="none"><td class="rref"></td><td colspan="{max(ncols, 1)}">No records.</td></tr>')
        cls = "tbl" + (" tall" if len(rows) > TALL_ROWS else "") + (" wide" if ncols > WIDE_COLS else "")
        n = len(rows)
        return (f'<div class="{cls}" id="{tid}" data-anchor="{tid}">'
                f'<div class="tbl-cap"><span class="tbl-id">{esc(caption)}</span>'
                f'<span class="tbl-meta">{esc(self.number + " · " if self.number else "")}{tid} · '
                f'{n} row{"s" if n != 1 else ""}</span></div>'
                f'<div class="tbl-scroll" tabindex="0" role="region" aria-label="Table {tid}">'
                f'<table style="--cols: {max(ncols, 1)}"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div></div>')

    def table(self, b: C.Table) -> str:
        chips, status_col, records, caption, id_col = None, None, None, "", None
        if isinstance(b, C.RegisterTable):
            reg = self.p.registers.get(b.type)
            label = reg.type.label if reg else b.type
            caption = f"{label} register" + (f" · {_where_text(b.where)}" if b.where else "")
            chips, records = b.chips, b.records
            if "status" in b.columns:
                status_col = b.columns.index("status")
            if "id" in b.columns:
                id_col = b.columns.index("id")
        elif isinstance(b, C.Catalogue):
            caption = "EA model catalogue"
        rows = b.body
        if isinstance(b, C.RegisterTable) and len(b.compact_rows) == len(b.records):
            rows = b.compact_rows   # each owner named once per row; a bare TBC's owner is the record's
        return self.table_html(b.anchor, b.header, rows, b.header_anchor, b.row_anchors, caption,
                               chips, status_col, records, id_col)

    def figure(self, f: C.Figure) -> str:
        fid = f.anchor
        is_view = isinstance(f, C.View)
        label = f.label
        # a view's caption is the Word document's: title, (EA metamodel viewpoint), view note
        title = view_caption(self.p, f) if is_view else f.caption
        meta = ""
        if is_view:
            vp = self.p.model.viewpoints.get(f.viewpoint) if f.viewpoint else None
            meta = f'<span class="fig-vp">{esc(vp.title if vp else f.viewpoint_ref)}</span>'
        zoom = (f'<button type="button" class="fig-btn" data-zoom="{fid}">Enlarge</button>')
        if f.path is not None:
            body = self.image(f, fid, label)
        elif f.source_file is not None and f.source_file.suffix == ".mmd":
            self.mermaid += 1
            src = f.source_file.read_text()
            body = (f'<button type="button" class="fig-img fig-mmd" data-zoom="{fid}" aria-label="Enlarge {label}">'
                    f'<pre class="mermaid">{esc(src, quote=False)}</pre></button>')
        else:
            zoom = ""
            why = (f"{self.p.rel(f.source_file)} has no rendered PNG or SVG; run archdoc diagrams --render"
                   if f.source_file is not None else f"diagrams/{f.name}.png (or .svg, .mmd) does not exist")
            body = f'<div class="fig-missing"><b>Not rendered.</b> {esc(why)}.</div>'
        return (f'<figure id="{fid}" class="fig" data-anchor="{fid}" data-comment-target data-label="{label}">'
                f'<div class="fig-bar"><span class="fig-id">{esc(self.number)} · {fid}</span>{meta}'
                f'<span class="fig-tools">{zoom}'
                f'<button type="button" class="fig-btn" data-ref="{fid}">Comment</button></span></div>'
                f'{body}<figcaption><b class="fig-label">{label}.</b> {inline_html(title)}</figcaption></figure>')

    def image(self, f: C.Figure, fid: str, label: str) -> str:
        src = Path(f.path)
        ext = src.suffix.lower()
        name = f"{fid}{ext}"
        self.full.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, self.full / name)
        dims = ""
        if ext == ".svg":
            shutil.copyfile(src, self.media / name)
        elif ext in RASTER:
            from PIL import Image
            try:
                im = Image.open(src)
                im.load()
            except OSError as e:
                raise SiteBuildError(f"{self.p.rel(src)}: cannot read image ({e})") from e
            w, h = im.size
            if w > PAGE_W:
                im = im.resize((PAGE_W, round(h * PAGE_W / w)), Image.LANCZOS)
            im.save(self.media / name, optimize=True)
            dims = f' width="{im.width}" height="{im.height}"'
        else:
            raise SiteBuildError(f"{self.p.rel(src)}: {ext} is not an image the site can show")
        self.images.append(name)
        return (f'<button type="button" class="fig-img" data-zoom="{fid}" aria-label="Enlarge {label}">'
                f'<img src="media/{name}" data-full="media/full/{name}"{dims} alt="{esc(label)}" '
                f'loading="lazy" decoding="async"></button>')

    # -- document
    def document_control(self) -> str:
        self.number, self.label = "", "Document control"
        out = ['<section class="chapter front" data-section="dc">',
               self.heading(1, ANCHOR_DC, "", "Document control", "Document control")]
        for i, (cap, header, rows) in enumerate(_dc_tables(self.p), start=1):
            tid = f"{ANCHOR_DC}-t{i}"
            out.append(self.table_html(tid, header, rows, f"{tid}-h",
                                       [f"{tid}-r{r}" for r in range(1, len(rows) + 1)], cap))
        out.append("</section>")
        return "".join(out)

    def chapters(self) -> str:
        out = []
        for ch in self.p.chapters:
            self.number = str(ch.number)
            clabel = f"{ch.number} {ch.title}"
            out.append(f'<section class="chapter" data-section="{ch.anchor}">')
            out.append(self.heading(1, ch.anchor, str(ch.number), ch.title, clabel))
            out += [self.block(b) for b in ch.lead]
            for s in ch.sections:
                self.number = s.number
                slabel = f"{s.number} {s.title}"
                out.append(self.heading(2, s.anchor, s.number, s.title, slabel))
                if s.blocks:
                    out += [self.block(b) for b in s.blocks]
                else:
                    out.append('<p class="empty">No content in this version.</p>')
            out.append("</section>")
        return "".join(out)

    def toc(self) -> str:
        out = ['<ol class="toc">',
               f'<li class="toc-ch"><a href="#{ANCHOR_DC}" data-nav="{ANCHOR_DC}"><span class="tn"></span>'
               f'<span class="tt">Document control</span><i class="dot" data-dot="{ANCHOR_DC}"></i></a></li>']
        for ch in self.p.chapters:
            out.append(f'<li class="toc-ch"><a href="#{ch.anchor}" data-nav="{ch.anchor}">'
                       f'<span class="tn">{ch.number}</span><span class="tt">{esc(ch.title)}</span>'
                       f'<i class="dot" data-dot="{ch.anchor}"></i></a>')
            if ch.sections:
                out.append('<ol class="toc-sub">')
                for s in ch.sections:
                    empty = "" if s.blocks else " empty"
                    out.append(f'<li><a class="{empty.strip()}" href="#{s.anchor}" data-nav="{s.anchor}">'
                               f'<span class="tn">{s.number}</span><span class="tt">{esc(s.title)}</span>'
                               f'<i class="dot" data-dot="{s.anchor}"></i></a></li>')
                out.append("</ol>")
            out.append("</li>")
        out.append("</ol>")
        return "".join(out)

    def open_items(self) -> tuple[str, int]:
        """The open-items panel, from :meth:`Project.open_items` as given:
        each item's text, owner, section and anchor, by section and by
        owner."""
        items = self.p.open_items()
        rows = []
        for it in items:
            label = f"<b>{esc(it.id)}</b> " if it.origin == "register" else ""
            owner = (f'<span class="oi-owner">{esc(it.owner)}</span>' if it.owner
                     else '<span class="oi-owner none">No owner</span>')
            inh = ' <span class="oi-inh" title="Taken from the record owner">record owner</span>' if it.inherited else ""
            link = (f'<a class="oi-link" href="#{it.anchor}"><code>{it.anchor}</code></a>' if it.anchor
                    else '<span class="oi-link uncited">not cited</span>')
            src = f'<span class="oi-src">{esc(str(it.source))}</span>' if it.source else ""
            rows.append((it, f'<li class="oi-item" data-anchor-ref="{it.anchor or ""}" data-owner="{esc(it.owner or "")}">'
                             f'{link}<div class="oi-body"><div class="oi-what">{label}{_mark_tbc(it.text)}</div>'
                             f'<div class="oi-meta">{owner}{inh}{src}</div></div></li>'))

        def by_section() -> str:
            groups: dict[str | None, list] = {}
            for it, row in rows:                       # already in document order, uncited last
                groups.setdefault(it.section, []).append((it, row))
            out = []
            for sec, members in groups.items():
                anc = members[0][0].section_anchor
                if sec:
                    out.append(f'<h3 class="oi-sec"><a href="#{anc}">{esc(sec)}</a></h3>')
                else:
                    out.append('<h3 class="oi-sec">Not shown in the document</h3><p class="oi-note">Register '
                               'records with a TBC that no REGISTER table in the document shows. Cite them, or '
                               'settle the value.</p>')
                out.append(f'<ol class="oi-list">{"".join(r for _, r in members)}</ol>')
            return "".join(out)

        def by_owner() -> str:
            groups: dict[str, list[str]] = {}
            for it, row in rows:
                groups.setdefault(it.owner or "", []).append(row)
            out = []
            for key in sorted(groups, key=lambda k: (k == "", k.lower())):
                out.append(f'<h3 class="oi-sec{" bad" if not key else ""}">{esc(key or "No owner")} '
                           f'<span class="oi-count">{len(groups[key])}</span></h3>'
                           f'<ol class="oi-list">{"".join(groups[key])}</ol>')
            return "".join(out)

        n = len(items)
        owners = {it.owner for it in items if it.owner}
        unowned = sum(1 for it in items if not it.owner)
        uncited = sum(1 for it in items if not it.anchor)
        if items:
            summary = (f'{n} open item{"s" if n != 1 else ""} with {len(owners)} owner{"s" if len(owners) != 1 else ""}'
                       + (f'; <b class="bad">{unowned} with no owner</b>' if unowned else "")
                       + (f"; {uncited} in records the document does not show" if uncited else "")
                       + ". Each link goes to the paragraph, list item or table row that holds it.")
            body = (f'<div class="oi-group" role="group" aria-label="Group open items">'
                    f'<button type="button" class="seg on" data-group="section">By section</button>'
                    f'<button type="button" class="seg" data-group="owner">By owner</button></div>'
                    f'<div class="oi-view" data-view="section">{by_section()}</div>'
                    f'<div class="oi-view" data-view="owner" hidden>{by_owner()}</div>')
        else:
            summary, body = "No value in this version is marked TBC.", ""
        return (f'<div class="oi-head"><h1 id="{ANCHOR_OPEN_ITEMS}-title">Open items</h1>'
                f'<p class="oi-sum">{summary}</p></div>{body}', n)

    def page(self) -> str:
        p = self.p
        dc = self.document_control()
        body = self.chapters()
        oi, n_tbc = self.open_items()
        css = (ASSETS / "site.css").read_text()
        js = (ASSETS / "site.js").read_text()
        kind = KIND_LABEL.get(p.kind, p.kind)
        org = p.profile.get("org.name")
        org = display(org) if org and str(org).strip().lower() not in ("none", "null") else ""
        date = _date(p, p.config.get("date")) if p.config.get("date") else ""
        deps = [d for d in p.config.get("depends_on") or [] if isinstance(d, dict)]
        dep_line = ""
        if deps:
            names = "; ".join(esc(_dep_name(p, d))
                              + (f" v{esc(display(d.get('version')))}" if d.get("version") else "") for d in deps)
            dep_line = f'<p class="tb-deps">Depends on {names}.</p>'
        n_sec = sum(len(c.sections) for c in p.chapters)
        n_fig = len(p.figures) + len(p.views)
        meta = {"title": p.title, "short": p.short, "version": p.version, "kind": p.kind,
                "key": re.sub(r"[^A-Za-z0-9_-]+", "-", f"{p.short}-{p.version}"),
                "review_collection": REVIEW_COLLECTION, "open_items": ANCHOR_OPEN_ITEMS,
                "comments_panel": ANCHOR_COMMENTS}
        meta_json = json.dumps(meta, ensure_ascii=True).replace("</", "<\\/")
        fonts = "".join(f'<link rel="stylesheet" href="{esc(u)}">' for u in font_links(p.profile.fonts))
        kicker = " · ".join(x for x in (org, kind, f"v{p.version}", date) if x)
        html_body = f"""<div class="app">
<header class="topbar">
  <button class="nav-toggle" id="nav-toggle" type="button" aria-controls="sidenav" aria-expanded="false">Contents</button>
  <a class="doc-id" href="#top"><span class="doc-short">{esc(p.short)}</span><span class="doc-name">{esc(p.title)}</span><span class="doc-ver">v{esc(p.version)}</span></a>
  <div class="top-tools">
    <span class="progress" id="progress"></span>
    <a class="oi-btn" href="#{ANCHOR_OPEN_ITEMS}" id="oi-btn">Open items <b>{n_tbc}</b></a>
    <a class="cm-btn" href="#{ANCHOR_COMMENTS}" id="cm-btn" hidden><span class="lg">My comments</span><span class="sm">Comments</span> <b id="cm-count">0</b></a>
  </div>
</header>
<nav class="sidenav" id="sidenav" aria-label="Document contents">
  <a class="toc-oi" href="#{ANCHOR_OPEN_ITEMS}">Open items <span>{n_tbc}</span></a>
  {self.toc()}
</nav>
<main class="doc" id="doc">
  <div class="titleblock" id="top">
    <p class="tb-kicker">{esc(kicker)}</p>
    <h1 class="tb-title">{esc(p.title)}</h1>
    {dep_line}
    <p class="tb-help">Select any text to comment on it, or use the reference tag beside a paragraph, list item or table row. Headings and figures have their own Comment button, and each heading has a review status. Every comment names the anchor it applies to, such as <code>{esc(self.sample_anchor())}</code>. {len(p.chapters)} chapters, {n_sec} sections, {n_fig} figures and views.</p>
    <p class="tb-mode" id="tb-mode"></p>
  </div>
  {dc}
  {body}
</main>
<main class="doc oi" id="{ANCHOR_OPEN_ITEMS}" hidden>
  {oi}
</main>
<main class="doc cm" id="{ANCHOR_COMMENTS}" hidden>
  <div class="oi-head"><h1>My comments</h1>
  <p class="oi-sum" id="cm-sum"></p>
  <div class="cm-actions"><button type="button" class="btn primary" id="cm-export">Export comments</button><button type="button" class="btn" id="cm-copyjson">Copy as JSON</button></div>
  <p class="cmp-msg" id="cm-msg" role="status"></p>
  <textarea class="cm-json" id="cm-json" rows="8" readonly hidden aria-label="Exported comments as JSON"></textarea>
  </div>
  <div id="cm-list"></div>
</main>
</div>
<div class="sel-pop" id="sel-pop" hidden><button type="button" id="sel-comment">Comment</button><button type="button" id="sel-copy">Copy reference</button></div>
<aside class="composer" id="composer" hidden aria-labelledby="cmp-title">
  <div class="cmp-head"><span id="cmp-title">Comment</span><code id="cmp-ref"></code>
    <button type="button" class="cmp-x" id="cmp-close" aria-label="Close">&times;</button></div>
  <p class="cmp-where" id="cmp-where"></p>
  <blockquote class="cmp-quote" id="cmp-quote" hidden></blockquote>
  <label class="sr" for="cmp-text">Your note</label>
  <textarea id="cmp-text" rows="5" maxlength="3200" placeholder="What should change here?"></textarea>
  <div class="cmp-name" id="cmp-name-row" hidden><label for="cmp-name">Your name</label><input id="cmp-name" type="text" maxlength="80" autocomplete="name"></div>
  <p class="cmp-msg" id="cmp-msg" role="status"></p>
  <div class="cmp-actions">
    <button type="button" class="btn primary" id="cmp-claude" hidden>Send to Claude</button>
    <button type="button" class="btn" id="cmp-post" hidden>Post comment</button>
    <button type="button" class="btn primary" id="cmp-save" hidden>Save comment</button>
    <button type="button" class="btn ghost" id="cmp-native" hidden>Open in comment panel</button>
    <button type="button" class="btn ghost" id="cmp-copy">Copy reference</button>
  </div>
</aside>
<div class="lightbox" id="lightbox" hidden role="dialog" aria-modal="true" aria-labelledby="lb-title">
  <div class="lb-bar"><span id="lb-title"></span>
    <div class="lb-tools">
      <button type="button" data-lb="out" aria-label="Zoom out">&minus;</button>
      <span id="lb-zoom">100%</span>
      <button type="button" data-lb="in" aria-label="Zoom in">+</button>
      <button type="button" data-lb="width">Fit width</button>
      <button type="button" data-lb="fit">Fit</button>
      <button type="button" data-lb="actual">1:1</button>
      <button type="button" data-lb="comment">Comment</button>
      <button type="button" data-lb="close" aria-label="Close">Close</button>
    </div></div>
  <div class="lb-stage" id="lb-stage"><img id="lb-img" alt="" draggable="false"></div>
</div>"""
        html_body = _ascii(html_body)
        title = _ascii(esc(p.title))
        return (f"<title>{title}</title>\n"
                '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
                f"{fonts}\n<style>\n{theme_css(p.profile)}{css}</style>\n{html_body}\n"
                f'<script type="application/json" id="doc-meta">{meta_json}</script>\n'
                f"<script>\n{js}</script>\n")

    def sample_anchor(self) -> str:
        for b in self.p.blocks():
            if isinstance(b, C.Para) and b.anchor and b.anchor.count("-") == 2:
                return b.anchor
        return "s1-1-p1"


def _ascii(s: str) -> str:
    """Non-ASCII characters as HTML character references."""
    return s.encode("ascii", "xmlcharrefreplace").decode("ascii")


# ----------------------------------------------------------------- publish

def publish_md(project, site: Path, files: list[str]) -> str:
    size = sum((site / f).stat().st_size for f in files) + (site / "index.html").stat().st_size
    desc = (f"Review copy of the {project.title} v{project.version}, with anchored comments, open items "
            f"and per-section review status.")
    files_json = json.dumps(files)
    return f"""# Publishing the {project.title} review site

Built by `archdoc build site` from the project at `{project.root}`. Rebuild it after every change to the
content or registers; never edit `index.html` by hand.

## Artifact publish call

- **file_path**: `{site / "index.html"}`
- **root**: `{site}`
- **files** (supporting files, a plain list; each publishes at its own path relative to `root`;
  {len(files)} files, {size / 1e6:.1f} MB with the page):

```json
{files_json}
```

  Use supporting files (`files`), not the asset store. The page references every image by relative path:
  `media/<anchor>.png` on the page and `media/full/<anchor>.png` in the lightbox.
- **capabilities**: `{{"comments": {{}}, "db": {{}}, "downloads": true}}`
  - `comments` (the full form, not `composer_only`): the page posts threads itself, so every comment
    starts with its anchor. Editors also get **Send to Claude**. Viewers are asked for consent on their
    first post. **Open in comment panel** opens the shell's own composer on the selected text.
  - `db` (default rules): shared review status per chapter and section, in collection
    `{REVIEW_COLLECTION}`.
  - `downloads`: lets a viewer whose view keeps comments in the browser save them with **Export comments**
    (the viewer confirms each save); without it the page hides that button.
  - `comments` and `db` make the artifact organisation-internal: it cannot be shared publicly.
- **icon**: `document`
- **description**: `{desc}`
- The title comes from the page: `{project.title}`.

To republish after a rebuild, run `archdoc build site` and publish the same `file_path` with the same
`root` and `files`, passing the artifact's `url` from another session. Omit `icon` and `capabilities` on
a redeploy so the artifact keeps them. Comments and review status survive a republish, but anchors are
positional: inserting a paragraph moves the paragraph numbers after it in that section.

## Reading comments back

### From the published page

`ArtifactComments` `action: "read"` with the artifact URL. A comment posted from the page's composer
starts with the anchor in square brackets, then the figure label (figures only) and the section, then
the quoted selection when there was one, then the note:

```
[s7-3-p2] 7.3 Component Design
"One container image runs as three processes"

Name the three process types explicitly.
```

Threads opened through **Open in comment panel**, or the shell's own comment mode, carry no bracketed
prefix: place them by their quoted excerpt and position. Every block carries `data-comment-target`, so
a comment-mode click inside a paragraph, list item, table row or figure anchors to that element.

To keep the comments with the project, write the threads to a JSON file as a list of objects with
`text` (the body, starting with `[anchor]`), and `author` and `at` when known, then run
`archdoc comments import <file>`. It reads the anchor from the bracketed prefix.

### From a local copy

Opened as a file, the page keeps comments and review status in that browser. The reviewer presses
**Export comments** under **My comments** and sends the JSON file back. Then:

```
archdoc -C {project.root} comments import <exported file>
```

This merges the file into `out/comments.json` (repeat imports add only new comments) and prints the
comments grouped by anchor, with the section number and title.

## Review status (db)

`ArtifactData` `action: "list"`, `collection: "{REVIEW_COLLECTION}"`. One document per section anchor
that has a status:

```json
{{"status": "changes", "section": "7.3 Component Design", "at": "2026-10-20T09:00:00.000Z"}}
```

`status` is `in-review`, `changes` or `agreed`. A section with no document has not been reviewed.

## Anchors

| Anchor | Means |
|---|---|
| `s7` | chapter 7 heading |
| `s7-p2` | lead-in paragraph 2 of chapter 7, before 7.1 |
| `s7-3` | section 7.3 heading |
| `s7-3-p2` | paragraph 2 of section 7.3 |
| `s7-3-l1-i4` | item 4 of list 1 in 7.3 |
| `s7-3-t1`, `s7-3-t1-h`, `s7-3-t1-r4` | table 1 in 7.3, its header row, its data row 4 |
| `fig-4`, `view-2` | Figure 4, View 2 |
| `dc`, `dc-t1-r3` | document control and its tables |
| `{ANCHOR_OPEN_ITEMS}` | the open-items panel |

To find an anchor in the page, search `index.html` for `id="s7-3-t1-r4"`.
"""


# ------------------------------------------------------------------- build

def build(project, out_dir=None) -> list[Path]:
    """Write ``<out>/site/index.html``, its media and ``PUBLISH.md``."""
    out = Path(out_dir) if out_dir is not None else project.root / "out"
    site = out / "site"
    site.mkdir(parents=True, exist_ok=True)
    media = site / "media"
    if media.exists():
        shutil.rmtree(media)
    media.mkdir()
    r = Renderer(project, site)
    page = r.page()
    index = site / "index.html"
    index.write_text(page, encoding="ascii")
    files = [f"media/{n}" for n in r.images] + [f"media/full/{n}" for n in r.images]
    pub = site / "PUBLISH.md"
    pub.write_text(publish_md(project, site, files))
    return [index, pub]


__all__ = ["build", "anchor_index", "place_of", "Place", "theme_tokens", "theme_css", "inline_html",
           "SiteBuildError", "REVIEW_COLLECTION", "ANCHOR_COMMENTS"]
