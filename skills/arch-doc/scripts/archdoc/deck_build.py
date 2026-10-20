"""The TL;DR deck (SPEC 6.3): ``archdoc build deck``.

:func:`build` writes one self-contained ``out/deck/index.html`` (the CSS and
JavaScript inlined; fonts from Google Fonts with system fallbacks) and the
figures it shows under ``out/deck/media/``. :func:`plan` produces the slides
without writing anything, which is what the tests read.

Order: a cover; a divider before each of the four runs (run membership comes
from the metamodel's ``deck.run``); then per chapter

- ``chNN-a`` **story**: the eyebrow "Chapter n", the title, the claim and
  three to six points or cards;
- ``chNN-b`` **detail**: the chapter's registers (those its sections cite
  through ``REGISTER`` blocks and metamodel ``artefacts``) and its own
  tables, as dense tables or card grids, status chips in words, split across
  two columns when narrow, with "n more in section x.y" where rows do not
  fit;
- ``chNN-c`` **picture**: the chapter's figure or view when its aspect ratio
  is between 1.2 and 2.4, otherwise the generated picture
  (:mod:`archdoc.pictures`), with up to three callout tags.

A chapter whose metamodel entry says ``deck.min_slides: 2``, or whose detail
is below :data:`DETAIL_MIN_ROWS` rows, gets story and picture only.

``deck.yaml`` (optional, in the project root)::

    cover: {line: <what the document decides or asks>}
    runs: {1: <one-sentence description>, ...}
    chapters:                       # or the chapter keys at the top level
      <chapter key>:
        claim: <one sentence>
        points: [<text>, ...]       # 3 to 6, or
        cards: [{title: .., text: ..}, ...]   # 3 to 6
        callouts: [{text: .., x: 0.4, y: 0.2}, ...]   # up to 3; x, y as fractions of the picture
        notes: <2-5 sentences>      # or {story: .., detail: .., picture: ..}

Every text may use the content placeholders; they are resolved with
:meth:`Project.resolve_text`. :func:`load_deck_yaml` validates the file:
structural errors stop the build (:class:`DeckError`), unknown chapter keys
are reported as warnings.

Text is measured before it is placed (:func:`archdoc.pictures.wrap`, about
0.55 x the font size per character) and nothing is set below 24px. The page
exposes ``window.__deckOverflow()``, which lists every element that leaves
its slide or box, so a headless browser can prove the layout.

:func:`chrome_html` adds the navigation deck.js drives (previous and next
buttons, a progress bar, a counter that opens an overview of every slide,
and a hint on the cover); deck.css hides all of it in print and shot mode.
"""
from __future__ import annotations

import html
import math
import re
import shutil
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import content as C
from . import pictures as P
from .pictures import Theme, ellipsize, human, status_words, text_width, wrap
from .project import Chapter, Project, ProjectError, person_line
from .registers import Record, Source, Tbc, display

ASSETS = Path(__file__).resolve().parent / "assets"
DECK_FILE = "deck.yaml"

SLIDE_W, SLIDE_H = 1920, 1080
MX = 128                     # side margin
TOP = 128                    # top margin
BOTTOM = 920                 # content stops here; the footer sits below
CW = SLIDE_W - 2 * MX        # 1664
ASPECT = (0.9, 2.6)          # figure aspect ratios a picture slide can use (letterboxed)
DETAIL_MIN_ROWS = 3          # fewer detail rows than this: a two-slide chapter
DETAIL_MAX_ROWS = 14         # "above about 14 rows ... n more in section x.y"
MAX_CELL_LINES = 3
CHAPTER_FIELDS = ("claim", "points", "cards", "callouts", "notes")
NOTE_SLIDES = ("story", "detail", "picture")
RUN_IDS = {1: "run-1", 2: "run-2", 3: "run-3", 4: "run-4"}


class DeckError(ProjectError):
    """deck.yaml cannot be used: the message lists every problem."""


@dataclass
class DeckIssue:
    severity: str            # error | warn
    message: str
    source: Source | None = None

    def __str__(self) -> str:
        where = f"{self.source}: " if self.source else ""
        return f"{where}[deck] {self.severity}: {self.message}"


@dataclass
class Slide:
    """One slide. ``kind`` is cover, divider, story, detail or picture."""

    id: str
    kind: str
    title: str
    html: str
    notes: str = ""
    chapter: int | None = None
    footer: str | None = None
    bg: str = "a"
    picture: P.Picture | None = None
    figure: C.Figure | None = None
    counts: list[str] = field(default_factory=list)   # detail slides: what the registers hold
    fill: bool = False        # a story or detail slide: deck.js trims it to fill, the check wants it full
    complete: bool = True     # everything the chapter has is on the slide (then a short slide is fine)


@dataclass
class Deck:
    slides: list[Slide]
    issues: list[DeckIssue]
    media: dict[str, Path] = field(default_factory=dict)   # published name -> source file

    @property
    def ids(self) -> list[str]:
        return [s.id for s in self.slides]


# ---------------------------------------------------------------- helpers

def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def inline_html(text: str) -> str:
    """Resolved block text (inline Markdown kept) as HTML."""
    out = []
    for t, styles, href in C.inline_runs(text):
        s = esc(t)
        if "code" in styles:
            s = f"<code>{s}</code>"
        if "bold" in styles:
            s = f"<b>{s}</b>"
        if "em" in styles:
            s = f"<em>{s}</em>"
        out.append(s)
    return "".join(out)


_ABBREV = re.compile(r"\b(e\.g|i\.e|etc|vs|approx|incl|cf|no|fig|sec)\.$", re.IGNORECASE)


def first_sentence(text: str) -> str:
    """The first sentence of plain text (abbreviations such as "e.g." and
    numbers such as "7.3" do not end one)."""
    t = " ".join(C.plain(text).split())
    for m in re.finditer(r"[.!?](?=\s+[A-Z0-9\"'“(])", t):
        head = t[:m.end()]
        if _ABBREV.search(head):
            continue
        return head
    return t


def sentences(text: str) -> list[str]:
    out, rest = [], " ".join(C.plain(text).split())
    while rest:
        s = first_sentence(rest)
        out.append(s)
        rest = rest[len(s):].strip()
    return out


def fit_text(text: str, width: float, height: float, sizes=(28, 24), lh: float = 1.4,
             bold: bool = False) -> tuple[int, str, int]:
    """The largest size in ``sizes`` at which ``text`` fits the box, as
    ``(size, text, lines)``; at the smallest size the text is cut with an
    ellipsis to the lines that fit."""
    for size in sizes:
        lines = wrap(text, width, size, bold)
        if len(lines) * size * lh <= height:
            return size, text, len(lines)
    size = sizes[-1]
    n = max(1, int(height // (size * lh)))
    lines = wrap(text, width, size, bold, max_lines=n)
    return size, " ".join(lines), len(lines)


def image_size(path: Path) -> tuple[float, float] | None:
    """Width and height of a PNG or SVG, read from the file itself."""
    try:
        if path.suffix.lower() == ".png":
            with path.open("rb") as f:
                head = f.read(24)
            if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
                w, h = struct.unpack(">II", head[16:24])
                return float(w), float(h)
            return None
        if path.suffix.lower() == ".svg":
            text = path.read_text(errors="replace")[:4000]
            m = re.search(r"<svg\b[^>]*>", text, re.DOTALL)
            if not m:
                return None
            tag = m.group(0)
            vb = re.search(r'viewBox\s*=\s*["\']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', tag)
            if vb:
                return float(vb.group(1)), float(vb.group(2))
            wm = re.search(r'\bwidth\s*=\s*["\']([\d.]+)(px)?["\']', tag)
            hm = re.search(r'\bheight\s*=\s*["\']([\d.]+)(px)?["\']', tag)
            if wm and hm:
                return float(wm.group(1)), float(hm.group(1))
    except OSError:
        return None
    return None


def chip_html(text: str, chip: str) -> str:
    return f'<span class="chip {esc(chip)}">{esc(text)}</span>'


def _plural(label: str, n: int) -> str:
    return P.count_phrase(label, n)


# ---------------------------------------------------------------- deck.yaml

def load_deck_yaml(project: Project) -> tuple[dict, list[DeckIssue]]:
    """Read and validate ``deck.yaml``. Returns the normalised mapping
    (``cover``, ``runs``, ``chapters``; texts resolved) and the issues
    found. A missing file is an empty mapping."""
    path = project.root / DECK_FILE
    norm: dict = {"cover": {}, "runs": {}, "chapters": {}}
    issues: list[DeckIssue] = []
    if not path.exists():
        return norm, issues
    src = Source(DECK_FILE)
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        line = getattr(getattr(e, "problem_mark", None), "line", None)
        return norm, [DeckIssue("error", f"YAML error: {e}", Source(DECK_FILE, line + 1 if line is not None else None))]
    if data is None:
        return norm, issues
    if not isinstance(data, dict):
        return norm, [DeckIssue("error", "deck.yaml must be a mapping", src)]

    def err(msg):
        issues.append(DeckIssue("error", msg, src))

    def resolve(text, where) -> str:
        if not isinstance(text, (str, int, float)) or isinstance(text, bool):
            err(f"{where} must be text")
            return ""
        out, unresolved = project.resolve_text(str(text), src)
        for u in unresolved:
            err(f"{where}: {u.token}: {u.reason}")
        return " ".join(out.split())

    chapters = data.get("chapters")
    top_level = {k: v for k, v in data.items() if k not in ("chapters", "cover", "runs")}
    if chapters is None:
        chapters = top_level
    else:
        if not isinstance(chapters, dict):
            err("chapters must map chapter keys to their slides")
            chapters = {}
        for k in top_level:
            err(f"unknown top-level key '{k}' (expected cover, runs and chapters)")

    cover = data.get("cover") or {}
    if isinstance(cover, str):
        cover = {"line": cover}
    if not isinstance(cover, dict):
        err("cover must be a mapping with a line")
    else:
        for k, v in cover.items():
            if k != "line":
                err(f"cover: unknown key '{k}' (expected line)")
            else:
                norm["cover"]["line"] = resolve(v, "cover.line")

    runs = data.get("runs") or {}
    if not isinstance(runs, dict):
        err("runs must map run numbers (1-4) to a one-sentence description")
    else:
        titles = {v.lower(): k for k, v in project.model.runs.items()}
        for k, v in runs.items():
            n = k if isinstance(k, int) else (int(k) if str(k).isdigit() else titles.get(str(k).lower()))
            if n not in (1, 2, 3, 4):
                err(f"runs: '{k}' is not a run number (1-4) or run title")
                continue
            norm["runs"][n] = resolve(v, f"runs.{k}")

    for key, entry in (chapters or {}).items():
        where = f"chapters.{key}"
        ch = project.chapter(str(key))
        if ch is None:
            why = ("is excluded by the profile or document kind" if project.metamodel.chapter(str(key))
                   else "is not a chapter of the metamodel")
            issues.append(DeckIssue("warn", f"chapter key '{key}' {why}; its slides are ignored", src))
            continue
        if entry is None:
            continue
        if not isinstance(entry, dict):
            err(f"{where} must be a mapping of {', '.join(CHAPTER_FIELDS)}")
            continue
        out: dict = {}
        for f in entry:
            if f not in CHAPTER_FIELDS:
                err(f"{where}: unknown key '{f}' (expected {', '.join(CHAPTER_FIELDS)})")
        if "claim" in entry:
            out["claim"] = resolve(entry["claim"], f"{where}.claim")
        if "points" in entry and "cards" in entry:
            err(f"{where}: give points or cards, not both")
        if "points" in entry:
            pts = entry["points"]
            if not isinstance(pts, list) or not 3 <= len(pts) <= 6:
                err(f"{where}.points must be a list of 3 to 6 points")
            else:
                out["points"] = [resolve(x, f"{where}.points[{i}]") for i, x in enumerate(pts)]
        if "cards" in entry:
            cards = entry["cards"]
            if not isinstance(cards, list) or not 3 <= len(cards) <= 6:
                err(f"{where}.cards must be a list of 3 to 6 cards")
            else:
                out["cards"] = []
                for i, c in enumerate(cards):
                    if not isinstance(c, dict) or not c.get("title") or not c.get("text"):
                        err(f"{where}.cards[{i}] needs a title and a text")
                        continue
                    for k in c:
                        if k not in ("title", "text"):
                            err(f"{where}.cards[{i}]: unknown key '{k}' (expected title, text)")
                    out["cards"].append({"title": resolve(c["title"], f"{where}.cards[{i}].title"),
                                         "text": resolve(c["text"], f"{where}.cards[{i}].text")})
        if "callouts" in entry:
            cs = entry["callouts"]
            if not isinstance(cs, list) or len(cs) > 3:
                err(f"{where}.callouts must be a list of up to 3 callouts")
            else:
                out["callouts"] = []
                for i, c in enumerate(cs):
                    if not isinstance(c, dict) or not c.get("text"):
                        err(f"{where}.callouts[{i}] needs a text, x and y")
                        continue
                    for k in c:
                        if k not in ("text", "x", "y"):
                            err(f"{where}.callouts[{i}]: unknown key '{k}' (expected text, x, y)")
                    ok = True
                    for axis in ("x", "y"):
                        v = c.get(axis)
                        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
                            err(f"{where}.callouts[{i}].{axis} must be a fraction from 0 to 1")
                            ok = False
                    if ok:
                        out["callouts"].append({"text": resolve(c["text"], f"{where}.callouts[{i}].text"),
                                                "x": float(c["x"]), "y": float(c["y"])})
        if "notes" in entry:
            n = entry["notes"]
            if isinstance(n, dict):
                out["notes"] = {}
                for k, v in n.items():
                    if k not in NOTE_SLIDES:
                        err(f"{where}.notes: unknown slide '{k}' (expected {', '.join(NOTE_SLIDES)})")
                    else:
                        out["notes"][k] = resolve(v, f"{where}.notes.{k}")
            else:
                out["notes"] = {"story": resolve(n, f"{where}.notes")}
        norm["chapters"][ch.key] = out
    return norm, issues


# ----------------------------------------------------------- chapter facts

@dataclass
class Group:
    """One table on a detail slide: a section's register (or its own
    table) with the rows it holds."""

    label: str               # "19.1 Architecture Risks"
    number: str              # the section number, for "n more in section x.y"
    columns: list[str]       # field names (register) or header texts (table)
    headers: list[str]
    rows: list[list[tuple[str, str | None]]]   # (text, chip or None) per cell
    status: list[tuple[str, str]] = field(default_factory=list)   # (words, chip) per row, registers only
    records: list[Record] = field(default_factory=list)
    type_label: str = ""
    where_text: str = ""     # where the rest are, when not a section ("the risk register")
    all_columns: int = 0     # columns the source has; more than shown means "n more columns"

    @property
    def count(self) -> int:
        return len(self.rows)


def _row(rec: Record, cols: list[str]) -> list[tuple[str, str | None]]:
    """A record's cells as the reader sees them (core ``cells``: resolved,
    labelled, the TBC owner named once per row); a TBC cell is a chip."""
    texts = rec.cells(cols)
    return [(t, "tbc" if isinstance(rec.get(c), Tbc) else None) for t, c in zip(texts, cols)]


def _cell(rec: Record, col: str) -> tuple[str, str | None]:
    v = rec.get(col)
    if isinstance(v, Tbc):
        owner = v.owner or rec.accountable
        return (f"TBC: {owner}" if owner else "TBC"), "tbc"
    return rec.display(col), None


def chapter_groups(project: Project, ch: Chapter) -> list[Group]:
    """The registers and tables a chapter's detail slide shows, section by
    section. A record shown once is not repeated by a later section's
    narrower filter."""
    groups: list[Group] = []
    shown: dict[str, set[str]] = {}

    def add_register(label, number, rtype, where, columns, shown_by_section=True):
        reg = project.registers.get(rtype)
        if reg is None:
            return
        if not shown_by_section:
            # The metamodel says the section covers this register, but the
            # section does not show it: the group is named for the register.
            plural = P._plural(reg.type.label, 2)
            # The part that tells two such groups apart comes first, so it
            # survives a cut: "Availability · non-functional requirements".
            which = " ".join(human(v) for c_ in (where.conditions if where else ()) for v in c_.values)
            label = (f"{which} · {plural}" if which else plural[:1].upper() + plural[1:])
        recs = [r for r in reg.filter(where) if r.id not in shown.setdefault(rtype, set())]
        if not recs:
            return
        cols = [c for c in (columns or reg.type.columns) if c != "status"]
        known = {"id", "title"} | set(reg.type.fields)
        cols = [c for c in cols if c in known]
        # A column no record fills says nothing on a slide.
        cols = [c for c in cols if c in ("id", "title") or any(r.get(c) not in (None, "", []) for r in recs)]
        for r in recs:
            shown[rtype].add(r.id)
        groups.append(Group(label, number, cols, [reg.type.header(c) for c in cols],
                            [_row(r, cols) for r in recs],
                            [(status_words(r), r.chip) for r in recs], recs, reg.type.label,
                            "" if shown_by_section else f"the {P._plural(reg.type.label, 2)} register",
                            len(cols)))

    def add_blocks(label, number, blocks, artefacts):
        regs_done = set()
        for b in blocks:
            if isinstance(b, C.RegisterTable):
                add_register(label, number, b.type, b.where, b.columns)
                regs_done.add((b.type, str(b.where)))
            elif isinstance(b, C.Table) and not isinstance(b, C.Catalogue) and b.body and len(b.header) >= 2:
                # (a table of one column is a list, not a table: its prose is on the story slide)
                groups.append(Group(label, number, list(b.header), list(b.header),
                                    [[(C.plain(c), None) for c in row] for row in b.body],
                                    all_columns=len(b.header)))
        for a in artefacts:
            if (a.type, str(a.where)) not in regs_done and not any(t == a.type for t, _ in regs_done):
                add_register(label, number, a.type, a.where, None, shown_by_section=False)

    add_blocks(f"{ch.number} {ch.title}", str(ch.number), ch.lead, [])
    for s in ch.sections:
        add_blocks(f"{s.number} {s.title}", s.number, s.blocks, s.artefacts)
    # Sections that show the same register with the same columns (risks by
    # category, say) read as one table on a slide.
    merged: list[Group] = []
    parts: list[list[Group]] = []
    for g in groups:
        prev = merged[-1] if merged else None
        if prev is not None and g.records and prev.records and prev.type_label == g.type_label \
                and prev.columns == g.columns and prev.where_text == g.where_text:
            prev.rows += g.rows
            prev.status += g.status
            prev.records += g.records
            parts[-1].append(g)
            continue
        merged.append(Group(g.label, g.number, g.columns, g.headers, list(g.rows), list(g.status),
                            list(g.records), g.type_label, g.where_text, g.all_columns))
        parts.append([g])
    for m, ps in zip(merged, parts):
        if len(ps) == 2:
            m.label = f"{ps[0].label} · {ps[1].label}"
            m.number = f"{ps[0].number} and {ps[1].number}"
        elif len(ps) > 2:
            m.label = f"{P._plural(m.type_label, 2).capitalize()} · sections {ps[0].number} to {ps[-1].number}"
            m.number = f"{ps[0].number} to {ps[-1].number}"
    # Groups that share a label (two registers or tables in one section)
    # each say what they hold: the register's name, or a table's first
    # headings; an ordinal only if that still repeats.
    labels: dict[str, list[Group]] = {}
    for m in merged:
        labels.setdefault(m.label, []).append(m)
    for label, twins in labels.items():
        if len(twins) < 2:
            continue
        for o in twins:
            what = P._plural(o.type_label, 2).capitalize() if o.type_label else \
                " and ".join(h for h in o.headers[:2] if h)
            o.label = f"{label} · {what}"
        seen_l: dict[str, int] = {}
        for o in twins:
            seen_l[o.label] = seen_l.get(o.label, 0) + 1
            if seen_l[o.label] > 1:
                o.label = f"{o.label} ({seen_l[o.label]})"
    return merged


def chapter_anchors(ch: Chapter) -> set[str]:
    out = {ch.anchor}
    for s in ch.sections:
        out.add(s.anchor)
    for b in ch.blocks():
        for a in [b.anchor, getattr(b, "header_anchor", None)] + list(getattr(b, "item_anchors", [])) \
                + list(getattr(b, "row_anchors", [])):
            if a:
                out.add(a)
    return out


def chapter_open_items(project: Project, ch: Chapter, groups: list[Group]) -> list:
    """The core's open items that belong to a chapter: those shown in one
    of its sections, and those on records the chapter's tables cite."""
    ids = {r.id for g in groups for r in g.records}
    anchors = {ch.anchor} | {s.anchor for s in ch.sections}
    return [i for i in project.open_items()
            if (i.section_anchor in anchors) or (i.record is not None and i.record in ids)]


def key_open_item(project: Project, ch: Chapter, groups: list[Group]):
    """The chapter's open item that matters most: on the most severe record
    (rating, severity, criticality, impact), then the least advanced."""
    items = chapter_open_items(project, ch, groups)
    if not items:
        return None
    rank = {"extreme": 0, "critical": 0, "high": 1, "medium": 2, "low": 3}

    def weight(it) -> tuple:
        rec = project.record(it.record) if it.record else None
        if rec is None:
            return (5, 9)
        sev = min(rank.get(display(rec.get(f)).lower(), 4) for f in ("rating", "severity", "criticality", "impact"))
        order = ("not-started", "tbc", "partial", "done")
        return (sev, order.index(rec.chip) if rec.chip in order else 4)
    return sorted(items, key=weight)[0]


def open_item_note(item) -> str | None:
    """The open item for speaker notes, as the core gives it."""
    if item is None:
        return None
    owner = f" Owner: {item.owner}." if item.owner else " No owner."
    where = f" Section {item.section}." if item.section else ""
    return _sentence(f"Open item: {item.text}") + owner + where


# ------------------------------------------------------------------ frame

SERIF = 0.53      # the heading face's width per character at 56px and up, semibold


def heading_lines(text: str, width: float, size: float) -> int:
    """Lines a serif heading takes: the heading face runs narrower than the
    body face, so it has its own factor."""
    per = max(1, int(width // (size * SERIF)))
    return len(wrap(text, per * size * P.CHAR, size))


def header_html(eyebrow: str, title: str, claim: str | None = None) -> tuple[str, float]:
    """The heading block at the top margin, laid out in flow (eyebrow,
    title, claim); returns its HTML and where the body may start."""
    y = TOP + 29 + 12 + heading_lines(title, CW, 56) * 62
    parts = [f'<p class="eyebrow">{esc(eyebrow)}</p>', f'<h2 class="title">{esc(title)}</h2>']
    if claim:
        y += 16 + len(wrap(C.plain(claim), CW, 36)) * 45
        parts.append(f'<p class="claim">{inline_html(claim)}</p>')
    return f'<div class="hblock" style="top:{TOP}px">{"".join(parts)}</div>', y


def footer_html(project: Project, n: int) -> str:
    return f'<p class="footer">{esc(project.short)} v{esc(project.version)} · {n}</p>'


# ------------------------------------------------------------------ story

def derived_claim(ch: Chapter) -> str | None:
    """The chapter's claim when deck.yaml gives none: the lead-in's first
    sentence, else the first paragraph's."""
    for b in ch.lead:
        if isinstance(b, C.Para) and b.text.strip():
            return first_sentence(b.text)
    for s in ch.sections:
        for b in s.blocks:
            if isinstance(b, C.Para) and b.text.strip():
                return first_sentence(b.text)
    return None


def section_cards(ch: Chapter, claim: str | None) -> list[dict]:
    """One card per section with prose: its number and title, and its first
    two or three sentences (a list's first items). The sentence that is
    already the claim is not repeated."""
    out: list[dict] = []
    for s in ch.sections:
        text = None
        for b in s.blocks:
            if isinstance(b, C.Para) and b.text.strip():
                sents = [x for x in sentences(b.text) if x != claim]
                text = " ".join(sents[:3]) if sents else None
            elif isinstance(b, C.Bullets) and b.items:
                text = "; ".join(C.plain(i).rstrip(".") for i in b.items[:3]) + "."
            if text:
                break
        if text:
            out.append({"label": f"{s.number} {s.title}", "text": text})
    return out


def derived_story(project: Project, ch: Chapter, groups: list[Group]) -> tuple[str | None, list[dict]]:
    """The claim and section cards a story slide derives from the content."""
    claim = derived_claim(ch)
    return claim, section_cards(ch, claim)


def register_facts(project: Project, groups: list[Group]) -> list[dict]:
    """One fact per register the chapter cites: how many records, their
    status in words, and how many carry a TBC."""
    # The whole register, not just the rows a section shows: "11
    # non-functional requirements" on the chapter that covers them all.
    by_type: dict[str, list[Record]] = {}
    for g in groups:
        if g.records and g.type_label not in by_type:
            by_type[g.type_label] = list(project.registers[g.records[0].type.key])
    out = []
    for label, recs in by_type.items():
        counts: dict[str, int] = {}
        for r in recs:
            w = status_words(r)
            w = "TBC" if w.startswith("TBC") else w.lower()
            counts[w] = counts.get(w, 0) + 1
        parts = [f"{n} {w}" for w, n in sorted(counts.items(), key=lambda kv: -kv[1])]
        tbc = sum(1 for r in recs if r.tbcs())
        if tbc and "TBC" not in counts:
            parts.append(f"{tbc} with a TBC")
        out.append({"n": len(recs), "label": P._plural(label, len(recs)), "split": " · ".join(parts)})
    return out


def facts_html(facts: list[dict], width: float) -> str:
    tiles = []
    for f in facts[:4]:
        split = ellipsize(f["split"], width / min(4, len(facts)) - 40, 24)
        tiles.append(f'<div class="fact"><p class="num">{f["n"]}<span>{esc(f["label"])}</span></p>'
                     f'<p class="split">{esc(split)}</p></div>')
    return '<div class="facts">' + "".join(tiles) + "</div>"


def open_item_box(project: Project, ch: Chapter, groups: list[Group]) -> str | None:
    """The chapter's most important open item as an amber box: the core's
    text, its owner and the section it is in, as given."""
    item = key_open_item(project, ch, groups)
    if item is None:
        return None
    meta = " · ".join(x for x in (f"Owner: {item.owner}" if item.owner else "No owner",
                                  item.section) if x)
    return (f'<div class="openbox"><p class="label">Open item</p>'
            f'<p class="what">{esc(item.text)}</p><p class="who">{esc(meta)}</p></div>')


def card_html(c: dict, width: float, trim: bool = False, max_lines: int = 4) -> str:
    """A card: its label (or bold head) and its whole text. The text is
    clamped to ``max_lines`` lines; deck.js raises the clamp line by line
    while the column has room, up to the whole text."""
    inner = width - 42
    if c.get("label"):
        head = f'<p class="label">{esc(ellipsize(c["label"], inner, 24, caps=True))}</p>'
    else:
        head = f'<p class="head">{esc(" ".join(wrap(c.get("title") or "", inner, 28, True, max_lines=2)))}</p>'
    total = len(wrap(C.plain(c["text"]), inner, 24))
    cls = "card trim-item" if trim else "card"
    return (f'<div class="{cls}">{head}<p class="text" data-lines="{min(max_lines, total)}" '
            f'data-min="{min(max_lines, total)}" data-max="{total + 1}" '
            f'style="font-size:24px;line-height:1.35;-webkit-line-clamp:{min(max_lines, total)}">'
            f'{inline_html(c["text"])}</p></div>')


def excerpt_group(g: Group, note: bool = True) -> Group:
    """A register cut to id, title and status, for the side of a slide.
    With ``note``, the table says how many columns it leaves out."""
    # A register keeps its id and title (its status is a column of its own);
    # a plain table keeps up to three columns, so one row of it still says
    # something.
    keep = [i for i, c in enumerate(g.columns) if c in ("id", "title")] or list(range(min(3, len(g.columns))))
    return Group(g.label, g.number, [g.columns[i] for i in keep], [g.headers[i] for i in keep],
                 [[row[i] for i in keep] for row in g.rows], list(g.status), list(g.records), g.type_label,
                 g.where_text, (g.all_columns or len(g.columns)) if note else len(keep))


def story_slide(project: Project, ch: Chapter, entry: dict, groups: list[Group]) -> tuple[Slide, str]:
    """Claim; a strip of register facts; the headline points or cards with
    the sections' story under them; the open item and an excerpt of the main
    register beside them. deck.js trims cards and rows to fill the body."""
    claim, cards = derived_story(project, ch, groups)
    claim = entry.get("claim") or claim
    empty = not any(True for _ in ch.blocks())
    if not claim:
        claim = ch.question or None
    head, y = header_html(f"Chapter {ch.number}", ch.title, claim)
    top = y + 32
    height = BOTTOM - top
    facts = register_facts(project, groups)
    openbox = open_item_box(project, ch, groups)
    main = max(groups, key=lambda g: g.count) if groups else None
    side = bool(openbox or main)
    gap = 32
    rw = 620 if side else 0
    lw = CW - rw - (gap if side else 0)
    left: list[str] = []
    complete = True
    if entry.get("points"):
        pts = "".join(f'<p class="point" style="font-size:28px;line-height:1.35">{inline_html(p)}</p>'
                      for p in entry["points"])
        left.append(f'<div class="points tight">{pts}</div>')
    elif entry.get("cards"):
        cw2 = (lw - 16) / 2
        left.append('<div class="cardgrid">' + "".join(card_html(c, cw2) for c in entry["cards"]) + "</div>")
    if empty:
        cards = [{"label": f"{s.number} {s.title}", "text": "Not written yet."} for s in ch.sections]
    if cards:
        cw2 = (lw - 16) / 2
        lines = 3 if (entry.get("points") or entry.get("cards")) else 4
        left.append('<div class="cardgrid">' + "".join(card_html(c, cw2, trim=True, max_lines=lines)
                                                         for c in cards) + "</div>")
    lead_items = list(left)           # the points and cards, before any register excerpt
    right: list[str] = []
    if openbox:
        right.append(openbox)
    if main is not None:
        # The largest register beside the story, as id, title and status;
        # the chapter's other registers under the cards, where the left
        # column has room. deck.js opens and fills them to their column.
        ex = excerpt_group(main, note=False)
        n = min(ex.count, DETAIL_MAX_ROWS)
        right.append(table_html(plan_group(ex, rw), 0, n, rw, ex.count - n, ex.label, weight=2))
        complete = n == ex.count
        for g0 in [g for g in groups if g is not main]:
            ex = excerpt_group(g0, note=False)
            n = min(ex.count, DETAIL_MAX_ROWS)
            left.append(table_html(plan_group(ex, lw), 0, n, lw, ex.count - n, ex.label, optional=True))
            complete = complete and n == ex.count
    parts = []
    if facts:
        parts.append(facts_html(facts, CW))
    # How tall the left column's own content is: points and cards.
    est = 0.0
    for p_ in entry.get("points") or []:
        est += len(wrap(C.plain(p_), lw - 30, 28)) * 38 + 12
    n_cards = len(entry.get("cards") or []) + len(cards)
    est += -(-n_cards // 2) * (30 + 4 * 33 + 40)
    # A nearly empty left column (a few short points, no cards) stacks the
    # registers under the points instead.
    stacked = main is not None and est < 0.4 * (height - 100)
    if stacked:
        # Little to say beside the registers: the points and the open item
        # on top, then every register at full width with its decision
        # columns, filled row by row.
        lead = "".join(lead_items)
        top_row = (f'<div class="cols story-top"><div class="col" style="flex:1;min-width:0">{lead}</div>'
                   + (f'<div class="col" style="width:{rw:.0f}px">{openbox}</div>' if openbox else "")
                   + "</div>")
        parts.append(top_row)
        complete = True
        for g0 in [main] + [g for g in groups if g is not main and g.records]:
            g = decision_group(g0, 5 if g0 is main else 4)
            n = min(g.count, DETAIL_MAX_ROWS)
            parts.append(table_html(plan_group(g, CW), 0, n, CW, g.count - n, g.label,
                                    weight=2 if g0 is main else 1, optional=g0 is not main))
            complete = complete and n == g.count
        body = (f'<div class="body fit fill rows" style="top:{top:.0f}px;height:{height:.0f}px">'
                f'{"".join(parts)}</div>')
    else:
        cols = f'<div class="col fitcol" style="width:{lw:.0f}px">{"".join(left)}</div>'
        if side:
            cols += f'<div class="col fitcol" style="width:{rw:.0f}px">{"".join(right)}</div>'
        parts.append(f'<div class="cols story-cols">{cols}</div>')
        body = f'<div class="body fit fill" style="top:{top:.0f}px;height:{height:.0f}px">{"".join(parts)}</div>'
    sid = f"ch{ch.number:02d}-a"
    html_ = "\n".join([head, body, footer_html(project, ch.number)])
    s = Slide(sid, "story", ch.title, html_, chapter=ch.number, footer=f"{project.short} v{project.version} · {ch.number}")
    s.fill, s.complete = True, complete
    return s, claim or ""


# ----------------------------------------------------------------- detail

@dataclass
class Plan:
    """A group laid out at a width: the columns kept, their widths, and
    how tall each row is."""

    group: Group
    keep: list[int]          # indexes into group.columns
    widths: list[float]      # px per kept column, then the status column
    row_h: list[float]
    head_h: float
    status_w: float

    def height(self, rows: int, more: bool) -> float:
        h = 30 + 8 + self.head_h + sum(self.row_h[:rows])
        return h + (8 + 30 if more else 0)


PAD_X, PAD_Y, LH = 24, 12, 24 * 1.3
CHIP_EXTRA = 6          # a chip's padding and border add to its line
WORD_FACTOR = 0.68      # the longest word's width per character, in font sizes


def _longest_word(text: str) -> int:
    return max((len(w) for w in text.split()), default=0)


def plan_group(g: Group, width: float) -> Plan:
    """Choose columns and widths for a group at ``width`` px."""
    n = len(g.columns)
    texts = [[row[i][0] for row in g.rows] for i in range(n)]
    status_w = 0.0
    if g.status:
        status_w = max(text_width(w, 24, True) for w, _ in g.status) + 24 + PAD_X + 4
        status_w = max(status_w, text_width("Status", 24, True) + PAD_X)

    def nat(i):
        cells = texts[i]
        bold = g.columns[i] == "id"
        w = max([text_width(c, 24, bold) + (24 if g.rows[k][i][1] else 0) for k, c in enumerate(cells)] or [0])
        word = max([_longest_word(c) for c in cells] + [_longest_word(g.headers[i])])
        return max(w, text_width(g.headers[i], 24, True), word * 24 * WORD_FACTOR) + PAD_X + 2

    def mn(i):
        cells = texts[i]
        word = max([_longest_word(c) for c in cells] + [_longest_word(g.headers[i])])
        is_id = g.columns[i] == "id"
        if is_id:
            return nat(i)
        widths = sorted(text_width(c, 24) for c in cells) or [0]
        p80 = widths[min(len(widths) - 1, int(len(widths) * 0.8))]
        # A word cannot wrap, and wide letters (m, w) run past the average
        # character width, so the longest word is measured generously.
        return max(word * 24 * WORD_FACTOR, p80 / MAX_CELL_LINES, 96) + PAD_X + 2

    keep = list(range(n))
    protected = {i for i, c in enumerate(g.columns) if c in ("id", "title")}
    while True:
        avail = width - status_w
        mins = [min(mn(i), nat(i)) for i in keep]
        if sum(mins) <= avail or len(keep) <= max(1, len(protected)):
            break
        drop = next((i for i in reversed(keep) if i not in protected), None)
        if drop is None:
            break
        keep.remove(drop)
    avail = width - status_w
    nats = [nat(i) for i in keep]
    mins = [min(mn(i), nat(i)) for i in keep]
    if sum(nats) <= avail:
        extra = avail - sum(nats)
        widths = [w + extra * w / sum(nats) for w in nats]
    else:
        spare = max(0.0, avail - sum(mins))
        flex = [max(0.0, a - b) for a, b in zip(nats, mins)]
        tot = sum(flex) or 1
        widths = [m + spare * f / tot for m, f in zip(mins, flex)]
    if sum(widths) > avail:
        # Still too wide for the space: every column but the id gives up its
        # share (an id never breaks).
        fixed = sum(w for i, w in zip(keep, widths) if g.columns[i] == "id")
        k = max(0.1, (avail - fixed) / max(1.0, sum(widths) - fixed))
        widths = [w if g.columns[i] == "id" else w * k for i, w in zip(keep, widths)]
    widths = [math.floor(w) for w in widths]
    status_w = math.floor(status_w)
    head_h = max(len(wrap(g.headers[i], w - PAD_X, 24, True)) for i, w in zip(keep, widths)) * LH + PAD_Y + 1
    row_h = []
    for k, row in enumerate(g.rows):
        h = LH
        for i, w in zip(keep, widths):
            text, chip = row[i]
            inner = w - PAD_X - (24 if chip else 0)
            lines = min(MAX_CELL_LINES, len(wrap(text, inner, 24)))
            h = max(h, lines * LH + (CHIP_EXTRA if chip else 0))
        if g.status:
            h = max(h, LH + CHIP_EXTRA)
        row_h.append(h + PAD_Y + 1)
    return Plan(g, keep, widths, row_h, head_h, status_w)


def table_html(pl: Plan, start: int, rows: int, width: float, more: int, label: str,
               total: int | None = None, weight: int = 1, optional: bool = False) -> str:
    """A register or table as a group: label, table, and a "n more in
    section x.y" line. The group carries its total and where the rest are,
    so deck.js can trim rows and keep the line true."""
    g = pl.group
    total = g.count - start if total is None else total
    cols = "".join(f'<col style="width:{w:.0f}px">' for w in pl.widths)
    if g.status:
        cols += f'<col style="width:{pl.status_w:.0f}px">'
    head = "".join(f"<th>{esc(g.headers[i])}</th>" for i in pl.keep) + ("<th>Status</th>" if g.status else "")
    body = []
    for k in range(start, start + rows):
        row = g.rows[k]
        cells = []
        for i, w in zip(pl.keep, pl.widths):
            text, chip = row[i]
            inner = w - PAD_X - (24 if chip else 0)
            # A chip (a TBC and its owner) wraps in its cell and is never cut.
            shown = text if chip else " ".join(wrap(text, inner, 24, max_lines=MAX_CELL_LINES))
            cls = ' class="idc"' if g.columns[i] == "id" else ""
            cells.append(f"<td{cls}>{chip_html(shown, chip) if chip else esc(shown)}</td>")
        if g.status:
            words, chip = g.status[k]
            cells.append(f"<td>{chip_html(words, chip)}</td>")
        body.append('<tr class="r">' + "".join(cells) + "</tr>")
    hidden_cols = max(0, (g.all_columns or len(g.columns)) - len(pl.keep))
    total_w = sum(pl.widths) + pl.status_w
    where = _where(g)
    w_attr = f' data-weight="{weight}"' if weight != 1 else ""
    split = ""
    if g.status:
        counts: dict[str, int] = {}
        for words, _ in g.status[start:]:
            k = "TBC" if words.startswith("TBC") else words.lower()
            counts[k] = counts.get(k, 0) + 1
        split = ", ".join(f"{n} {w}" for w, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    # One footnote: rows and columns not shown, and where they are. deck.js
    # rewrites it as it trims; a collapsed group shows only the footnote.
    cols_shown = len(pl.keep) + (1 if g.status else 0)
    # Under two columns, or one row with under three, a table says less than
    # its summary line: it stays a summary.
    thin = cols_shown < 2 or (g.count - start <= 1 and cols_shown < 3)
    cls = ("group optional" if optional else "group") + (" summary-only" if thin else "")
    fixed = ' data-collapsed="" data-fixed=""' if thin else ""
    return (f'<div class="{cls}" data-total="{total}" data-where="{esc(where)}" data-cols="{hidden_cols}"{fixed}'
            f' data-split="{esc(split)}"{w_attr}>'
            f'<div class="group-head"><p class="group-label">{esc(ellipsize(label, width, 24, caps=True))}</p>'
            f'<p class="more">{esc(footnote(more, hidden_cols, where))}</p></div>'
            f'<table class="reg" style="width:{total_w:.0f}px"><colgroup>{cols}</colgroup>'
            f"<tr>{head}</tr>{''.join(body)}</table></div>")


def footnote(rows: int, cols: int, where: str) -> str:
    """'9 more rows · 1 more column in section 4.3' (empty when nothing is hidden)."""
    parts = []
    if rows:
        parts.append(P.count_phrase("more row", rows))
    if cols:
        parts.append(P.count_phrase("more column", cols))
    return " · ".join(parts) + f" in {where}" if parts else ""


def detail_cards_html(g: Group, top: float, height: float) -> str:
    """A register of up to six records as a card grid: id, title, the
    other columns as labelled lines, and the status chip."""
    n = len(g.rows)
    cols = n if n <= 3 else (2 if n == 4 else 3)
    rows = -(-n // cols)
    gap = 24
    cw = (CW - gap * (cols - 1)) / cols
    chh = (height - 38 - gap * (rows - 1)) / rows
    inner = cw - 56
    items = []
    for k, rec in enumerate(g.records):
        id_i = g.columns.index("id") if "id" in g.columns else None
        title_i = g.columns.index("title") if "title" in g.columns else None
        parts = []
        used = 48 + 2
        if id_i is not None:
            parts.append(f'<p class="label">{esc(g.rows[k][id_i][0])}</p>')
            used += 30 + 12
        tl = wrap(rec.title, inner, 28, True, max_lines=2)
        parts.append(f'<p class="head">{esc(" ".join(tl))}</p>')
        used += len(tl) * 28 * 1.3 + 12
        chip_h = 32 + 12
        for i, col in enumerate(g.columns):
            if i in (id_i, title_i):
                continue
            text, chip = g.rows[k][i]
            if not text:
                continue
            label = g.headers[i]
            avail = chh - used - chip_h
            if avail < LH:
                break
            lines = wrap(f"{label}: {text}", inner, 24, max_lines=max(1, int(avail // LH)))
            shown = " ".join(lines)
            body = shown[len(label) + 2:] if shown.startswith(f"{label}: ") else shown
            val = chip_html(body, chip) if chip else esc(body)
            parts.append(f'<p class="field"><b>{esc(label)}:</b> {val}</p>')
            used += len(lines) * LH + 12
        words, chip = g.status[k] if g.status else ("", "")
        if words:
            parts.append(f"<p>{chip_html(words, chip)}</p>")
        items.append(f'<div class="card fit" style="height:{chh:.0f}px">{"".join(parts)}</div>')
    grid = (f'<div class="grid" style="grid-template-columns:repeat({cols},1fr);grid-auto-rows:{chh:.0f}px;'
            f'height:auto">' + "".join(items) + "</div>")
    label = f'<p class="group-label">{esc(ellipsize(g.label, CW, 24, caps=True))}</p>'
    return (f'<div class="body fit" style="top:{top:.0f}px;height:{height:.0f}px">'
            f'<div class="group" style="gap:8px">{label}{grid}</div></div>')


def _card_worthy(g: Group) -> bool:
    if not g.records or len(g.rows) > 6:
        return False
    text_cols = [i for i, c in enumerate(g.columns) if c not in ("id", "title")]
    longest = max((len(g.rows[k][i][0]) for k in range(len(g.rows)) for i in text_cols), default=0)
    return longest > 48


def _where(g: Group) -> str:
    if g.where_text:
        return g.where_text
    return f"sections {g.number}" if (" and " in g.number or " to " in g.number) else f"section {g.number}"


# Columns a reviewer decides on, first; long free text gives way to them.
DECISION_COLUMNS = ("owner", "target", "rating", "likelihood", "impact", "priority", "severity", "due",
                    "required_by", "date", "timing", "forum", "stage", "area", "category", "type", "pattern",
                    "source", "criticality", "change", "classification", "required", "involvement", "process",
                    "order", "start", "finish", "after", "rollback_point", "tested", "threshold")


def decision_group(g: Group, max_extra: int = 4) -> Group:
    """A register cut to id, title and the columns a reviewer decides on:
    short fields first (owner, target, rating, dates, enums), long free text
    only when too few short ones are left."""
    if not g.records:
        return g
    keep = [i for i, c in enumerate(g.columns) if c in ("id", "title")]
    others = [i for i, c in enumerate(g.columns) if c not in ("id", "title")]

    def avg(i):
        return sum(len(r[i][0]) for r in g.rows) / max(1, len(g.rows))
    short = sorted([i for i in others if avg(i) <= 32],
                   key=lambda i: (g.columns[i] not in DECISION_COLUMNS, others.index(i)))
    long_ = [i for i in others if avg(i) > 32]
    chosen = short[:max_extra]
    if len(chosen) < 2:
        chosen += long_[:2 - len(chosen)]
    cols = sorted(keep + chosen)
    return Group(g.label, g.number, [g.columns[i] for i in cols], [g.headers[i] for i in cols],
                 [[row[i] for i in cols] for row in g.rows], list(g.status), list(g.records), g.type_label,
                 g.where_text, g.all_columns or len(g.columns))


def detail_slide(project: Project, ch: Chapter, groups: list[Group]) -> Slide:
    """The chapter's registers, filling the body: the largest register full
    width with its decision columns, the others side by side as compact
    tables. Up to 14 rows a table are rendered; deck.js trims rows that do
    not fit and keeps every "n more in section x.y" line true."""
    seen: dict[str, int] = {}
    for g in groups:
        if g.type_label:
            seen[g.type_label] = seen.get(g.type_label, 0) + g.count
    counts = [_plural(label, n) for label, n in seen.items()]
    head, y = header_html(f"Chapter {ch.number} · Detail", ch.title)
    top = y + 32
    height = BOTTOM - top
    complete = all(g.count <= DETAIL_MAX_ROWS for g in groups)
    half = (CW - 32) / 2
    if len(groups) == 1 and groups[0].records and groups[0].count <= 6:
        # A short register: one card per record, with every field it has.
        body = detail_cards_html(groups[0], top, height)
    elif len(groups) == 1:
        g = decision_group(groups[0], 5)
        pl_half = plan_group(g, half)
        # Only a genuinely narrow register (a few short columns, one-line
        # rows) runs on into a second column; a wide one never splits.
        narrow = (len(g.columns) <= 3 and len(pl_half.keep) == len(g.columns)
                  and all(h <= LH + CHIP_EXTRA + PAD_Y + 1 for h in pl_half.row_h))
        if narrow and g.count > 7:
            left = min(-(-g.count // 2), DETAIL_MAX_ROWS)
            right = min(g.count - left, DETAIL_MAX_ROWS)
            lhtml = table_html(pl_half, 0, left, half, 0, g.label, total=left, weight=2)
            rhtml = table_html(pl_half, left, right, half, g.count - left - right, g.label + " (continued)")
            inner = (f'<div class="cols gridrow"><div class="gcol" style="width:{half:.0f}px">{lhtml}</div>'
                     f'<div class="gcol" style="width:{half:.0f}px">{rhtml}</div></div>')
        else:
            pl = plan_group(g, CW)
            n = min(g.count, DETAIL_MAX_ROWS)
            inner = table_html(pl, 0, n, CW, g.count - n, g.label, weight=2)
        body = f'<div class="body fit fill rows" style="top:{top:.0f}px;height:{height:.0f}px">{inner}</div>'
    else:
        # Every register full width, where its rows are shortest: the largest
        # first (it takes rows first), then the others in document order.
        # deck.js opens and fills them until the next row would not fit.
        main = max(groups, key=lambda g: g.count)
        parts = []
        for g0 in [main] + [g for g in groups if g is not main]:
            g = decision_group(g0, 5 if g0 is main else 4)
            n = min(g.count, DETAIL_MAX_ROWS)
            parts.append(table_html(plan_group(g, CW), 0, n, CW, g.count - n, g.label,
                                    weight=2 if g0 is main else 1))
        body = f'<div class="body fit fill rows" style="top:{top:.0f}px;height:{height:.0f}px">{"".join(parts)}</div>'
    sid = f"ch{ch.number:02d}-b"
    html_ = "\n".join([head, body, footer_html(project, ch.number)])
    s = Slide(sid, "detail", ch.title, html_, chapter=ch.number, footer=f"{project.short} v{project.version} · {ch.number}")
    s.counts = counts
    s.fill, s.complete = True, complete
    return s


def detail_rows(groups: list[Group]) -> int:
    return sum(g.count for g in groups)


# ---------------------------------------------------------------- picture

def chapter_figure(ch: Chapter) -> tuple[C.Figure, tuple[float, float]] | None:
    """The chapter's first figure or view with a rendered file whose aspect
    ratio is between 1.2 and 2.4."""
    for f in ch.figures:
        if f.path is None or not Path(f.path).exists():
            continue
        size = image_size(Path(f.path))
        if size and size[1] and ASPECT[0] <= size[0] / size[1] <= ASPECT[1]:
            return f, size
    return None


def place_callout(text: str, x: float, y: float, area_w: float, area_h: float,
                  taken: list[P.Box]) -> P.Box | None:
    """Where a callout tag goes: at the requested point (its fractions of
    the picture), or the nearest place to it, searching outward, where it
    covers no label of the picture and no other callout; a narrower,
    wrapped tag is tried when the full one finds no room. When the picture
    has no free room at all, the place that covers the least."""
    natural = min(text_width(text, 24, True) + 32, 520)
    best: tuple[float, P.Box] | None = None
    for w in sorted({natural, min(natural, 380), min(natural, 280)}, reverse=True):
        lines = len(wrap(text, w - 32, 24, True))
        h = lines * 24 * 1.3 + 17

        def clamp(px, py):
            # inside the picture, 16px clear of its edge
            return min(max(px, 16), area_w - w - 16), min(max(py, 16), area_h - h - 16)
        x0, y0 = clamp(x, y)
        step = 16
        for radius in range(0, 720, step):
            n = max(1, int(2 * math.pi * radius / step))
            for i in range(n):
                a = 2 * math.pi * i / n
                px, py = clamp(x0 + radius * math.cos(a), y0 + radius * math.sin(a))
                box = P.Box(px, py, w, h)
                cover = sum(max(0.0, min(box.x + box.w, o.x + o.w) - max(box.x, o.x) + 12) *
                            max(0.0, min(box.y + box.h, o.y + o.h) - max(box.y, o.y) + 12)
                            for o in taken if P._hit(box, o, 6))
                if cover == 0:
                    return box
    # No free space anywhere on the picture: the callout is dropped rather
    # than laid over what the picture shows.
    return None


TRIMS: dict[str, tuple[int, int, int, int]] = {}    # media name -> crop box, applied when copied
DROPPED: list[tuple[int, str]] = []     # callouts with no free space on their picture, reported by plan()


def trimmed_box(path: Path, pad: int = 16) -> tuple[int, int, int, int] | None:
    """The crop box of a PNG without its uniform border (the colour of its
    corner), padded, or None when it has no such border or Pillow is absent."""
    if path.suffix.lower() != ".png":
        return None
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
        diff = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > 12 else 0)
        bbox = diff.getbbox()
        if not bbox:
            return None
        x0, y0, x1, y1 = bbox
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(rgb.width, x1 + pad), min(rgb.height, y1 + pad)
        if (x1 - x0) * (y1 - y0) > 0.97 * rgb.width * rgb.height:
            return None
        return x0, y0, x1, y1


def picture_slide(project: Project, ch: Chapter, entry: dict, theme: Theme, media: dict[str, Path],
                  used: set[str] | None = None) -> Slide:
    """The chapter's figure, or a generated picture no other chapter shows
    (``used`` collects the fingerprints of those already drawn)."""
    used = used if used is not None else set()
    head, y = header_html(f"Chapter {ch.number}", ch.title)
    top = y + 20
    height = BOTTOM - top
    found = chapter_figure(ch)
    pic = None
    fig = None
    if found:
        fig, (iw, ih) = found
        name = f"{fig.kind}-{fig.number}{Path(fig.path).suffix.lower()}"
        media[name] = Path(fig.path)
        box = trimmed_box(Path(fig.path))
        if box is not None:
            # Drawn without the image's own blank margins, so the diagram
            # itself is as large as the area allows.
            TRIMS[name] = box
            iw, ih = box[2] - box[0], box[3] - box[1]
        alt = f"{fig.label}. {C.plain(fig.caption)}"
        inner = f'<img src="media/{esc(name)}" alt="{esc(alt)}">'
        nat_w, nat_h = iw, ih
    else:
        regs = [g.records[0].type.key for g in chapter_groups(project, ch) if g.records]
        pic = P.generate(project, ch, theme, exclude=used, registers=list(dict.fromkeys(regs)))
        used.add(pic.fingerprint)
        inner = pic.svg
        nat_w, nat_h = P.W, P.H
    callouts = entry.get("callouts") or []

    def lay(area_h: float):
        """The picture at the largest size the area allows (letterboxed),
        and each callout placed in true free space on it, or None."""
        scale = min(CW / nat_w, area_h / nat_h)
        bw, bh = nat_w * scale, nat_h * scale
        taken: list[P.Box] = []
        if pic is not None:
            # Every label and every box the picture draws (cards, cells,
            # bars, lanes): a callout covers none of them.
            k = bw / P.W
            taken = [P.Box(b.x * k, b.y * k, b.w * k, b.h * k) for b in list(pic.texts) + list(pic.rects)]
        placed = []
        for c in callouts:
            box = place_callout(c["text"], c["x"] * bw, c["y"] * bh, bw, bh, taken)
            if box is not None:
                taken.append(box)
            placed.append(box)
        return bw, bh, placed

    bw, bh, placed = lay(height)
    strip: list[str] = []
    if any(b is None for b in placed):
        # No free space on the picture for some callouts: they sit in a
        # strip under it, the picture shortened to make room.
        strip_h = 24 * 1.3 + 17 + 20
        bw, bh, placed = lay(height - strip_h)
        strip = [c["text"] for c, b in zip(callouts, placed) if b is None]
    left, ptop = MX + (CW - bw) / 2, top + (height - (bh + (24 * 1.3 + 37 if strip else 0))) / 2
    calls = [f'<p class="callout" style="left:{b.x:.0f}px;top:{b.y:.0f}px;width:{b.w:.0f}px">{esc(c["text"])}</p>'
             for c, b in zip(callouts, placed) if b is not None]
    body = (f'<div class="picture" style="left:{left:.0f}px;top:{ptop:.0f}px;width:{bw:.0f}px;height:{bh:.0f}px">'
            f'{inner}{"".join(calls)}</div>')
    if strip:
        tags = "".join(f'<p class="callout strip">{esc(t)}</p>' for t in strip)
        body += (f'<div class="callout-strip fit" style="left:{MX}px;top:{ptop + bh + 20:.0f}px;width:{CW}px">'
                 f'{tags}</div>')
    sid = f"ch{ch.number:02d}-c"
    s = Slide(sid, "picture", ch.title, "\n".join([head, body, footer_html(project, ch.number)]),
              chapter=ch.number, footer=f"{project.short} v{project.version} · {ch.number}", picture=pic, figure=fig)
    return s


# ------------------------------------------------------- cover, dividers

def format_date(project: Project, value: Any) -> str:
    """A date as the house writes it (``house.date_format``), through the
    core's helper, so the deck, the site and the document agree."""
    from .formatting import date_format, format_date as _format
    return _format(value, date_format(project))


def cover_slide(project: Project, line: str | None) -> Slide:
    cfg = project.config
    kind = "Capability design" if project.kind == "capability" else "Solution design"
    org = project.profile.text("org.name") if project.profile.is_set("org.name") else None
    eyebrow = f"{org} · {kind}" if org else kind
    y = 200
    out = [f'<p class="eyebrow" style="top:{y}px">{esc(eyebrow)}</p>']
    y += 29 + 24
    t_lines = heading_lines(project.title, CW, 88)
    out.append(f'<h1 class="cover-title" style="top:{y}px">{esc(project.title)}</h1>')
    y += t_lines * 95 + 32
    if line:
        line = ellipsize(C.plain(line), CW * 3, 36)
        out.append(f'<p class="cover-line" style="top:{y}px">{inline_html(line)}</p>')
        y += len(wrap(line, CW, 36)) * 45 + 32
    meta = [f"Version {project.version}" + (f" · {format_date(project, cfg['date'])}" if cfg.get("date") else "")]
    if cfg.get("author"):
        meta.append(f"Author: {person_line(cfg['author'])}")
    if cfg.get("owner"):
        meta.append(f"Owner: {person_line(cfg['owner'])}")
    deps = [d for d in cfg.get("depends_on") or [] if isinstance(d, dict) and d.get("title")]
    if deps:
        meta.append("Depends on " + ", ".join(
            f"{d['title']}" + (f" v{d['version']}" if d.get("version") else "") for d in deps))
    meta_html = "".join(f"<p>{esc(m)}</p>" for m in meta)
    out.append(f'<div class="cover-meta" style="top:{max(y, 620)}px">{meta_html}</div>')
    notes = (f"{project.title}, {kind.lower()}, version {project.version}. "
             + (f"{C.plain(line)} " if line else "")
             + (f"It depends on {', '.join(d['title'] for d in deps)}." if deps else "It depends on no other design."))
    return Slide("cover", "cover", project.title, "\n".join(out), notes=notes, bg="s")


def divider_slide(project: Project, run: int, title: str, chapters: list[Chapter], desc: str | None,
                  groups: dict[int, list[Group]] | None = None) -> Slide:
    """A run's divider: its title and description, its chapters with what
    each holds, and the run's key numbers from the registers (open TBCs,
    risks by rating, the status of every record its chapters cite)."""
    groups = groups or {}
    out = [f'<p class="eyebrow" style="top:{TOP + 40}px">Part {run}</p>']
    y = TOP + 40 + 29 + 24
    out.append(f'<h2 class="divider-title" style="top:{y}px">{esc(title)}</h2>')
    y += heading_lines(title, CW, 88) * 95 + 16
    if desc:
        out.append(f'<p class="claim" style="top:{y}px">{inline_html(desc)}</p>')
        y += len(wrap(C.plain(desc), CW, 36)) * 45 + 16
    y += 32
    lw, gap = 860, 48
    rw = CW - lw - gap
    rows = []
    # Each chapter with what it holds when the list has the room; titles only otherwise.
    with_sub = len(chapters) * (2 * 32 + 14) <= BOTTOM - y
    for c in chapters:
        facts = register_facts(project, groups.get(c.number, [])) if with_sub else []
        sub = " · ".join(f"{f['n']} {f['label']}" for f in facts[:3])
        sub_html = f'<span class="toc-sub">{esc(ellipsize(sub, lw - 60, 24))}</span>' if sub else ""
        rows.append(f"<p><b>{c.number}</b>{esc(c.title)}{sub_html}</p>")
    left = f'<div class="toc toc-run" style="width:{lw}px">{"".join(rows)}</div>'
    # The run's numbers.
    recs: list[Record] = []
    items = []
    for c in chapters:
        gs = groups.get(c.number, [])
        for g in gs:
            for r in g.records:
                if r not in recs:
                    recs.append(r)
        items += [i for i in chapter_open_items(project, c, gs) if i not in items]
    tiles = []
    if items:
        owners = {i.owner for i in items if i.owner}
        unowned = sum(1 for i in items if not i.owner)
        split = (f"owned by {len(owners)} " + ("person" if len(owners) == 1 else "people")
                 + (f" · {unowned} with no owner" if unowned else ""))
        tiles.append(f'<div class="fact"><p class="num">{len(items)}<span>open '
                     f'{"item" if len(items) == 1 else "items"}</span></p><p class="split">{esc(split)}</p></div>')
    risks = [r for r in recs if r.type.key == "risk"]
    if risks:
        by: dict[str, int] = {}
        for r in risks:
            k = human(r.get("rating")) or "Unrated"
            by[k] = by.get(k, 0) + 1
        order = ["Extreme", "High", "Medium", "Low"]
        split = " · ".join(f"{by[k]} {k.lower()}" for k in sorted(by, key=lambda k: order.index(k) if k in order else 9))
        tiles.append(f'<div class="fact"><p class="num">{len(risks)}<span>{P._plural("risk", len(risks))}</span></p>'
                     f'<p class="split">{esc(split)}</p></div>')
    if recs:
        counts = {c_: sum(1 for r in recs if r.chip == c_) for c_ in P.CHIP_ORDER}
        segs = "".join(
            f'<div style="flex:{n};background:var(--{c_}-soft);color:var(--{c_})">{n if n * 1.0 / len(recs) > 0.06 else ""}</div>'
            for c_, n in counts.items() if n)
        words = " · ".join(f"{n} {P.CHIP_WORDS[c_].lower()}" for c_, n in counts.items() if n)
        regs = len({r.type.key for r in recs})
        tiles.append(f'<div class="fact"><p class="num">{len(recs)}<span>records in {P.count_phrase("register", regs)}</span></p>'
                     f'<div class="statbar">{segs}</div><p class="split">{esc(words)}</p></div>')
    right = f'<div class="runstats" style="width:{rw}px">{"".join(tiles)}</div>' if tiles else ""
    out.append(f'<div class="body fit" style="top:{y}px;height:{BOTTOM - y}px;display:flex;gap:{gap}px">'
               f'{left}{right}</div>')
    n0, n1 = chapters[0].number, chapters[-1].number
    span = f"chapter {n0}" if n0 == n1 else f"chapters {n0} to {n1}"
    notes = f"Part {run}, {title}, covers {span}." + (f" {desc}" if desc else "")
    if items:
        notes += f" It carries {P.count_phrase('open item', len(items))}."
    return Slide(RUN_IDS[run], "divider", title, "\n".join(out), notes=notes, bg="b")


# ------------------------------------------------------------------- plan

def plan(project: Project) -> Deck:
    """Every slide of the deck, in order, without writing anything. Raises
    :class:`DeckError` when deck.yaml has errors."""
    data, issues = load_deck_yaml(project)
    DROPPED.clear()
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise DeckError("deck.yaml: " + "; ".join(i.message for i in errors))
    theme = Theme.from_profile(project.profile)
    P.use_plurals(project)
    media: dict[str, Path] = {}
    slides: list[Slide] = []
    stories: dict[int, str] = {}

    runs: dict[int, list[Chapter]] = {}
    for ch in project.chapters:
        runs.setdefault(int(ch.deck.get("run") or 4), []).append(ch)

    chapter_slides: dict[int, list[Slide]] = {}
    all_groups: dict[int, list[Group]] = {}
    used_pictures: set[str] = set()
    for ch in project.chapters:
        entry = data["chapters"].get(ch.key, {})
        notes_in = entry.get("notes") or {}
        groups = chapter_groups(project, ch)
        all_groups[ch.number] = groups
        bg = "a" if int(ch.deck.get("run") or 4) % 2 == 1 else "b"
        story, claim = story_slide(project, ch, entry, groups)
        stories[ch.number] = claim
        item = open_item_note(key_open_item(project, ch, groups))
        covers = [s_.title for s_ in ch.sections if s_.filled][:4]
        story.notes = notes_in.get("story") or " ".join(x for x in [
            _sentence(claim),
            (f"Chapter {ch.number} covers " + _join([c.lower() if i else c for i, c in enumerate(covers)]) + ".")
            if covers else f"Chapter {ch.number} has no content yet.",
            item] if x)
        thin = ch.deck.get("min_slides") == 2 or detail_rows(groups) < DETAIL_MIN_ROWS
        out = [story]
        if not thin:
            d = detail_slide(project, ch, groups)
            counts = d.counts
            d.notes = notes_in.get("detail") or " ".join(x for x in [
                (f"The detail behind chapter {ch.number}: " + _join(counts) + ".") if counts else
                f"The tables behind chapter {ch.number}.",
                "Rows that do not fit are counted on the slide, with the section that holds them.",
                item] if x)
            out.append(d)
        pic = picture_slide(project, ch, entry, theme, media, used_pictures)
        if pic.figure is not None:
            what = f"{pic.figure.label}, {C.plain(pic.figure.caption)}"
        else:
            what = pic.picture.description if pic.picture else ""
        if pic.figure is not None:
            origin = f"It is {pic.figure.label} of the document, shown as drawn."
        elif pic.picture is not None:
            origin = ("It is drawn from the design's dependencies." if pic.picture.source == "depends_on" else
                      "It is drawn from the registers." if pic.picture.source == "registers" else
                      f"It is drawn from the {pic.picture.source.replace('-', ' ')} register.")
        else:
            origin = None
        pic.notes = notes_in.get("picture") or " ".join(x for x in [
            _sentence(f"The picture shows {what}") if what else None, origin,
            " ".join(_sentence(c["text"]) for c in entry.get("callouts") or []) or None] if x)
        out.append(pic)
        for s in out:
            s.bg = bg
        chapter_slides[ch.number] = out

    summary = project.chapter("summary")
    line = data["cover"].get("line") or (stories.get(summary.number) if summary else None) or None
    slides.append(cover_slide(project, line))
    for run in sorted(runs):
        title = project.model.runs.get(run, f"Part {run}")
        slides.append(divider_slide(project, run, title, runs[run], data["runs"].get(run), all_groups))
        for ch in runs[run]:
            slides.extend(chapter_slides[ch.number])
    for n, text in DROPPED:
        issues.append(DeckIssue("warn", f"chapter {n}: callout '{text}' dropped; the picture has no free space for it",
                                Source(DECK_FILE)))
    return Deck(slides, issues, media)


def _sentence(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    return s if s.endswith((".", "!", "?")) else s + "."


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# ------------------------------------------------------------------ write

def _google_fonts(theme: Theme, mono: str | None) -> str:
    fams = []
    for f, w in ((theme.heading_font, "wght@400;600;700"), (theme.body_font, "wght@400;500;600;700"),
                 (mono, "wght@400;500")):
        if f and f not in [x[0] for x in fams]:
            fams.append((f, w))
    q = "&".join(f"family={f.replace(' ', '+')}:{w}" for f, w in fams)
    return f"https://fonts.googleapis.com/css2?{q}&display=swap"


def tokens_css(theme: Theme, mono: str | None) -> str:
    t = theme
    pairs = {
        "ink": t.ink, "muted": t.muted, "paper": t.paper, "panel": t.panel, "rule": t.rule,
        "accent": t.accent, "accent-soft": t.accent_soft, "done": t.done, "partial": t.partial,
        "not-started": t.not_started, "tbc": t.tbc,
        "done-soft": t.soft(t.done), "partial-soft": t.soft(t.partial),
        "not-started-soft": t.soft(t.not_started), "tbc-soft": t.soft(t.tbc),
        "frame": P.mix(t.ink, t.paper, 0.15),
    }
    body = "".join(f"--{k}:{v};" for k, v in pairs.items())
    mono_stack = f"'{mono}', ui-monospace, Menlo, monospace" if mono else "ui-monospace, Menlo, monospace"
    return (f":root{{{body}--heading:{t.heading_stack};--body:{t.body_stack};--mono:{mono_stack};"
            f"color-scheme:light;}}")


CHEVRON_PREV = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 5.5 8 12l6.5 6.5"/></svg>'
CHEVRON_NEXT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 5.5 16 12l-6.5 6.5"/></svg>'
GRID_ICON = ('<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="1" width="6" height="6" rx="1"/>'
             '<rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/>'
             '<rect x="9" y="9" width="6" height="6" rx="1"/></svg>')
HINT = "\u2190 \u2192 or click to navigate \u00b7 G for all slides"


def chrome_html(n: int) -> str:
    """The navigation chrome deck.js drives: previous and next buttons, a
    progress bar, the counter (which opens the overview), the cover's hint
    and the overview of every slide. None of it shows in print or shot
    mode (deck.css)."""
    return (
        '<div class="deck-ui">'
        f'<button class="nav-btn prev" type="button" aria-label="Previous slide" title="Previous (\u2190)">{CHEVRON_PREV}</button>'
        f'<button class="nav-btn next" type="button" aria-label="Next slide" title="Next (\u2192)">{CHEVRON_NEXT}</button>'
        '<div class="progress" aria-hidden="true"><div class="progress-bar"></div></div>'
        f'<button class="counter" type="button" aria-haspopup="dialog" title="All slides (G)">{GRID_ICON}'
        f'<span class="counter-text">1 / {n}</span></button>'
        f'<p class="hint" role="status" hidden>{esc(HINT)}</p>'
        '</div>\n'
        '<div class="overview deck-ui" role="dialog" aria-modal="true" aria-label="All slides" hidden>'
        f'<div class="overview-head"><p class="overview-title">All slides <span>{n}</span></p>'
        '<button class="overview-close" type="button">Close <kbd>Esc</kbd></button></div>'
        '<div class="overview-grid"></div></div>'
    )


def render(project: Project, deck: Deck) -> str:
    theme = Theme.from_profile(project.profile)
    mono = project.profile.fonts.get("mono")
    css = (ASSETS / "deck.css").read_text()
    js = (ASSETS / "deck.js").read_text()
    sections = []
    for s in deck.slides:
        notes = f'<aside class="notes">{esc(s.notes)}</aside>' if s.notes else ""
        chap = f' data-chapter="{s.chapter}"' if s.chapter else ""
        if s.fill:
            chap += ' data-fill=""' + (' data-complete=""' if s.complete else "")
        sections.append(f'<section class="slide bg-{s.bg}" id="{esc(s.id)}" data-kind="{s.kind}" '
                        f'data-title="{esc(s.title)}"{chap}>\n{s.html}\n{notes}\n</section>')
    title = f"{project.title} v{project.version}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{esc(_google_fonts(theme, mono))}">
<style>
{tokens_css(theme, mono)}
{css}
</style>
</head>
<body data-deck="{esc(project.short)} v{esc(project.version)}" tabindex="-1">
<div class="stage">
{chr(10).join(sections)}
</div>
<div class="notes-panel" aria-live="polite"></div>
{chrome_html(len(deck.slides))}
<script>
{js}
</script>
</body>
</html>
"""


def build(project: Project, out_dir: str | Path | None = None) -> list[Path]:
    """Write ``<out>/deck/index.html`` and its media. ``out_dir`` defaults
    to ``<project>/out``. Returns the files written."""
    out = Path(out_dir) if out_dir is not None else project.root / "out"
    deck = plan(project)
    prints = [s.picture.fingerprint for s in deck.slides if s.picture is not None]
    if len(prints) != len(set(prints)):            # plan() never repeats one; keep it so
        raise DeckError("a generated picture appears on two slides")
    for i in deck.issues:
        print(i, file=sys.stderr)
    ddir = out / "deck"
    ddir.mkdir(parents=True, exist_ok=True)
    mdir = ddir / "media"
    if mdir.exists():
        shutil.rmtree(mdir)
    written = []
    index = ddir / "index.html"
    index.write_text(render(project, deck))
    written.append(index)
    if deck.media:
        mdir.mkdir()
        for name, src in deck.media.items():
            dst = mdir / name
            if name in TRIMS:
                from PIL import Image
                with Image.open(src) as im:
                    im.crop(TRIMS[name]).save(dst)
            else:
                shutil.copyfile(src, dst)
            written.append(dst)
    return written


__all__ = ["build", "plan", "render", "load_deck_yaml", "Deck", "Slide", "DeckError", "DeckIssue",
           "chapter_groups", "chapter_figure", "image_size", "first_sentence", "DETAIL_MIN_ROWS", "ASPECT"]
