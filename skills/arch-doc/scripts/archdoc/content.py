"""The chapter content format: parsing, blocks, placeholders and anchors.

One Markdown file per chapter::

    # <chapter key>                text before the first ## is the lead-in
    ## <section key or title>      ## Title [new] adds a section not in the metamodel
    plain paragraph
    - bullet  /  1. ordered item   (indented lines continue the item)
    | a | b |                      a table; the first row is the header
    REGISTER <type> [where k=v ...] [cols a,b,c] [labels a="Header" b=Other]
    FIGURE <name> | <caption>
    VIEW <name> | <view title> | <viewpoint>
    CATALOGUE [<model.json>]
    <!-- comment -->               ignored, may span lines

:func:`parse_file` turns a file into a :class:`ParsedChapter` of raw blocks,
each carrying its source file and line. The project then places the blocks in
numbered sections, gives each a stable positional anchor
(:func:`assign_anchors`), and fills placeholders through a :class:`Resolver`.
After resolution every block has ``.text`` (placeholders replaced, inline
Markdown such as ``**bold**`` kept; see :func:`inline_runs` and
:func:`plain`) and ``.unresolved`` (the placeholders that did not resolve,
with their location).

Anchors (SPEC 6.2), computed here so the site, the deck and the checks agree:

=================  ==================================================
``s7``             chapter 7
``s7-p1``          lead-in paragraph 1 of chapter 7
``s7-3``           section 7.3
``s7-3-p2``        paragraph 2 of section 7.3
``s7-3-l1``        list 1 of section 7.3; ``s7-3-l1-i4`` its item 4
``s7-3-t1``        table 1 (plain, register or catalogue)
``s7-3-t1-h``      its header row; ``s7-3-t1-r4`` its data row 4
``fig-4``          Figure 4; ``view-2`` View 2 (numbered through the document)
``dc``             document control (cover matter)
``app-*``          generated back matter: ``app-open-items``, ``app-references``
=================  ==================================================

Paragraphs, lists and tables are counted separately within each section (or
lead-in), from 1, in document order. Figures and views are counted through
the whole document.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .registers import (EMBEDDED_TBC, Problem, Record, Source, Tbc, Where, display, embedded_tbcs, id_list,
                        parse_conditions, split_args, tbc_markers)  # noqa: F401 (tbc_markers re-exported)

if TYPE_CHECKING:  # pragma: no cover
    from .project import Project

ANCHOR_DC = "dc"
ANCHOR_OPEN_ITEMS = "app-open-items"
ANCHOR_REFERENCES = "app-references"

PLACEHOLDER = re.compile(r"\{(sec|ch|fig|view|count|ids|reg|dep|p|doc|cat):([^{}]*)\}")
CONTENT_TBC = EMBEDDED_TBC
DEFAULT_MODEL = "diagrams/model.json"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BULLET = re.compile(r"^(?P<indent>\s*)(?P<mark>[-*]|\d+[.)])\s+(?P<text>.*)$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
DIRECTIVES = ("REGISTER", "FIGURE", "VIEW", "CATALOGUE")


# ------------------------------------------------------------------ blocks

@dataclass
class Unresolved:
    """A placeholder that did not resolve: the token as written, why, and
    where it is."""

    token: str
    reason: str
    source: Source | None = None
    anchor: str | None = None

    def __str__(self) -> str:
        where = f"{self.source}: " if self.source else ""
        return f"{where}{self.token}: {self.reason}"


@dataclass
class Block:
    """Common fields of every content block.

    ``kind`` is para, bullets, table, register, figure, view or catalogue.
    ``raw`` is the text as written; ``text`` the resolved text; ``anchor``
    the stable anchor; ``source`` the file and line.
    """

    kind: str = field(init=False, default="")
    source: Source = None  # type: ignore[assignment]
    raw: str = ""
    anchor: str | None = None
    text: str = ""
    unresolved: list[Unresolved] = field(default_factory=list)

    @property
    def rows(self) -> list[list[str]]:
        return []


@dataclass
class Para(Block):
    def __post_init__(self):
        self.kind = "para"


@dataclass
class Bullets(Block):
    """A list. ``items`` are resolved texts, ``levels`` their nesting depth
    (0 for top level), ``item_anchors`` one per item, ``item_sources`` the
    line of each."""

    ordered: bool = False
    raw_items: list[str] = field(default_factory=list)
    levels: list[int] = field(default_factory=list)
    item_sources: list[Source] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    item_anchors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.kind = "bullets"


@dataclass
class Table(Block):
    """A table. ``header`` and ``rows`` are resolved cell texts;
    ``header_anchor`` and ``row_anchors`` follow SPEC 6.2."""

    raw_header: list[str] = field(default_factory=list)
    raw_rows: list[list[str]] = field(default_factory=list)
    row_sources: list[Source] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    body: list[list[str]] = field(default_factory=list)
    header_anchor: str | None = None
    row_anchors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.kind = "table"

    @property
    def rows(self) -> list[list[str]]:
        """Data rows (the header is ``.header``)."""
        return self.body


@dataclass
class RegisterTable(Table):
    """A ``REGISTER`` directive: the matching records of one type as a
    table. ``records`` are the :class:`~archdoc.registers.Record` objects,
    one per row; ``columns`` the field names; ``chips`` each row's status
    chip. ``rows`` (``body``) are display values (placeholders resolved,
    enum and status values labelled, every TBC as "TBC: <owner>");
    ``compact_rows`` are the same with an inherited TBC shortened to "TBC"
    where the row already names the owner (its owner is the record's
    ``accountable``); ``raw_rows`` are the stored values."""

    type: str = ""
    where: Where = field(default_factory=Where)
    columns: list[str] = field(default_factory=list)
    columns_given: bool = False
    records: list[Record] = field(default_factory=list)
    chips: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)   # field -> header, from the directive's labels clause
    compact_rows: list[list[str]] = field(default_factory=list)   # rows with the owner named once per row

    def __post_init__(self):
        self.kind = "register"


@dataclass
class Catalogue(Table):
    """A ``CATALOGUE`` directive: the EA model behind the views, summarised
    as object counts by type. ``model_path`` is the model JSON it reads."""

    model_path: str = DEFAULT_MODEL
    found: bool = False

    def __post_init__(self):
        self.kind = "catalogue"


@dataclass
class Figure(Block):
    """A ``FIGURE`` directive. ``number`` counts figures through the
    document; ``label`` is "Figure n"; ``caption`` the resolved caption;
    ``path`` the rendered PNG or SVG when present; ``source_file`` the
    diagram source (.mmd, .ead, .py) when present."""

    name: str = ""
    raw_caption: str = ""
    caption: str = ""
    number: int = 0
    path: Path | None = None
    source_file: Path | None = None

    def __post_init__(self):
        self.kind = "figure"

    @property
    def label(self) -> str:
        return f"Figure {self.number}"


@dataclass
class View(Figure):
    """A ``VIEW`` directive: an EA view, numbered "View n". ``viewpoint``
    is the metamodel viewpoint key and ``ea_name`` its name in the
    profile's EA metamodel."""

    raw_title: str = ""
    title: str = ""
    viewpoint_ref: str = ""
    viewpoint: str | None = None
    ea_name: str | None = None

    def __post_init__(self):
        self.kind = "view"

    @property
    def label(self) -> str:
        return f"View {self.number}"


# ----------------------------------------------------------------- parsing

@dataclass
class ParsedSection:
    """A ``##`` section as written: ``heading`` is the text after ``##``
    with any ``[new]`` marker removed."""

    heading: str
    new: bool
    source: Source
    blocks: list[Block] = field(default_factory=list)


@dataclass
class ParsedChapter:
    key: str | None
    source: Source
    lead: list[Block] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def strip_comments(text: str) -> str:
    """Remove ``<!-- -->`` comments, keeping line numbers."""
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if s[i] == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(s[i])
        i += 1
    cells.append("".join(cur).strip())
    return cells


def parse_directive(line: str, src: Source) -> tuple[Block | None, Problem | None]:
    word = line.split(None, 1)[0]
    rest = line[len(word):].strip()
    if word == "REGISTER":
        try:
            toks = split_args(rest)
        except ValueError as e:
            return None, Problem("content", str(e), src)
        if not toks:
            return None, Problem("content", "REGISTER needs a type", src)
        rtype, toks = toks[0], toks[1:]
        conds: list[str] = []
        cols: list[str] = []
        labels: dict[str, str] = {}
        mode = None
        for t in toks:
            if t == "where" and mode is None:
                mode = "where"
            elif t in ("cols", "labels"):
                mode = t
            elif mode == "where":
                conds.append(t)
            elif mode == "cols":
                cols += [c.strip() for c in t.split(",") if c.strip()]
            elif mode == "labels":
                k, eq, v = t.partition("=")
                if not eq or not k.strip() or not v.strip():
                    return None, Problem("content", f"REGISTER: label '{t}' must be field=\"Header\"", src)
                labels[k.strip()] = v.strip()
            else:
                return None, Problem("content", f"REGISTER: unexpected '{t}' (expected where ..., cols ... "
                                     f"or labels ...)", src)
        if mode == "where" and not conds:
            return None, Problem("content", "REGISTER: 'where' with no conditions", src)
        try:
            where = parse_conditions(conds)
        except ValueError as e:
            return None, Problem("content", f"REGISTER: {e}", src)
        return RegisterTable(source=src, raw=line, type=rtype, where=where, columns=cols,
                             columns_given=bool(cols), labels=labels), None
    if word == "FIGURE":
        parts = [p.strip() for p in rest.split("|", 1)]
        if not parts[0]:
            return None, Problem("content", "FIGURE needs a name", src)
        caption = parts[1] if len(parts) > 1 else ""
        if not caption:
            return None, Problem("content", f"FIGURE {parts[0]} needs a caption: FIGURE <name> | <caption>", src)
        return Figure(source=src, raw=line, name=parts[0], raw_caption=caption), None
    if word == "VIEW":
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) != 3 or not all(parts):
            return None, Problem("content", "VIEW takes three parts: VIEW <name> | <view title> | <viewpoint>", src)
        return View(source=src, raw=line, name=parts[0], raw_title=parts[1], raw_caption=parts[1],
                    viewpoint_ref=parts[2]), None
    if word == "CATALOGUE":
        cat = Catalogue(source=src, raw=line)
        if rest:
            cat.model_path = rest
        return cat, None
    return None, Problem("content", f"unknown directive {word}", src)


def parse_text(text: str, display_path: str) -> ParsedChapter:
    """Parse one chapter file's text."""
    lines = strip_comments(text).split("\n")
    chapter = ParsedChapter(None, Source(display_path, 1))
    target: list[Block] | None = None  # blocks list being filled
    para: list[tuple[int, str]] = []
    bullets: Bullets | None = None
    table: Table | None = None

    def src(n: int) -> Source:
        return Source(display_path, n)

    def flush():
        nonlocal para, bullets, table
        if para and target is not None:
            target.append(Para(source=src(para[0][0]), raw=" ".join(t.strip() for _, t in para)))
        para = []
        if bullets is not None and target is not None:
            bullets.raw = "\n".join(bullets.raw_items)
            target.append(bullets)
        bullets = None
        if table is not None and target is not None:
            table.raw = "\n".join(["| " + " | ".join(table.raw_header) + " |"] +
                                  ["| " + " | ".join(r) + " |" for r in table.raw_rows])
            target.append(table)
        table = None

    for n, line in enumerate(lines, start=1):
        stripped = line.strip()
        if line.startswith("# ") or stripped == "#":
            flush()
            if chapter.key is not None:
                chapter.problems.append(Problem("content", "a chapter file has one '# <chapter key>' heading", src(n)))
                target = None
                continue
            chapter.key = stripped[1:].strip()
            chapter.source = src(n)
            if not chapter.key:
                chapter.problems.append(Problem("content", "chapter heading has no key", src(n)))
            target = chapter.lead
            continue
        if line.startswith("## ") or stripped == "##":
            flush()
            heading = stripped[2:].strip()
            new = False
            m = re.match(r"^(.*?)\s*\[new\]\s*$", heading, re.IGNORECASE)
            if m:
                heading, new = m.group(1).strip(), True
            if chapter.key is None:
                chapter.problems.append(Problem("content", "section before the '# <chapter key>' heading", src(n)))
            if not heading:
                chapter.problems.append(Problem("content", "section heading is empty", src(n)))
            sec = ParsedSection(heading, new, src(n))
            chapter.sections.append(sec)
            target = sec.blocks
            continue
        if re.match(r"^#{3,}\s", line):
            flush()
            chapter.problems.append(Problem(
                "content", "only '#' (chapter) and '##' (section) headings are allowed", src(n)))
            continue
        if not stripped:
            flush()
            continue
        if target is None:
            chapter.problems.append(Problem("content", "text before the '# <chapter key>' heading", src(n)))
            continue
        word = stripped.split(None, 1)[0]
        if word in DIRECTIVES and line == line.lstrip():
            flush()
            block, prob = parse_directive(stripped, src(n))
            if prob:
                chapter.problems.append(prob)
            if block:
                target.append(block)
            continue
        if stripped.startswith("|"):
            if para or bullets is not None:
                flush()
            if table is None:
                table = Table(source=src(n))
                table.raw_header = split_row(stripped)
                continue
            if _TABLE_SEP.match(stripped) and not table.raw_rows:
                continue
            table.raw_rows.append(split_row(stripped))
            table.row_sources.append(src(n))
            continue
        if table is not None:
            flush()
        m = _BULLET.match(line)
        if m:
            if para:
                flush()
            ordered = m.group("mark")[0].isdigit()
            if bullets is None or (bullets.ordered != ordered and len(m.group("indent")) == 0):
                flush()
                bullets = Bullets(source=src(n), ordered=ordered)
            bullets.raw_items.append(m.group("text").strip())
            bullets.levels.append(len(m.group("indent").replace("\t", "  ")) // 2)
            bullets.item_sources.append(src(n))
            continue
        if bullets is not None and line.startswith((" ", "\t")):
            bullets.raw_items[-1] += " " + stripped
            continue
        if bullets is not None:
            flush()
        para.append((n, line))
    flush()
    if chapter.key is None:
        chapter.problems.append(Problem("content", "missing '# <chapter key>' heading", Source(display_path, 1)))
    return chapter


def parse_file(path: Path, display_path: str | None = None) -> ParsedChapter:
    """Parse a chapter file from disk."""
    return parse_text(path.read_text(), display_path or str(path))


# ----------------------------------------------------------------- anchors

class AnchorCounter:
    """Counts paragraphs, lists and tables within one section or lead-in."""

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.p = self.l = self.t = 0

    def assign(self, block: Block) -> None:
        if isinstance(block, Para):
            self.p += 1
            block.anchor = f"{self.prefix}-p{self.p}"
        elif isinstance(block, Bullets):
            self.l += 1
            block.anchor = f"{self.prefix}-l{self.l}"
            block.item_anchors = [f"{block.anchor}-i{i}" for i in range(1, len(block.raw_items) + 1)]
        elif isinstance(block, Table):
            self.t += 1
            block.anchor = f"{self.prefix}-t{self.t}"
            block.header_anchor = f"{block.anchor}-h"


def assign_anchors(prefix: str, blocks: list[Block], fig_counter: list[int], view_counter: list[int]) -> None:
    """Give each block in one section (or lead-in) its anchor. Figure and
    view counters are one-element lists shared across the document."""
    c = AnchorCounter(prefix)
    for b in blocks:
        if isinstance(b, View):
            view_counter[0] += 1
            b.number = view_counter[0]
            b.anchor = f"view-{b.number}"
        elif isinstance(b, Figure):
            fig_counter[0] += 1
            b.number = fig_counter[0]
            b.anchor = f"fig-{b.number}"
        else:
            c.assign(b)


def row_anchors(table: Table, count: int) -> list[str]:
    return [f"{table.anchor}-r{i}" for i in range(1, count + 1)]


# ----------------------------------------------------------- placeholders

class Resolver:
    """Fills placeholders against a loaded project.

    ``resolve(text)`` returns ``(text, unresolved)``. An unresolved
    placeholder is left in the text as written, so a draft shows it.
    """

    def __init__(self, project: "Project"):
        self.project = project

    def resolve(self, text: str, source: Source | None = None, anchor: str | None = None
                ) -> tuple[str, list[Unresolved]]:
        missing: list[Unresolved] = []

        def sub(m: re.Match) -> str:
            kind, arg = m.group(1), m.group(2).strip()
            try:
                return self._one(kind, arg)
            except LookupError as e:
                missing.append(Unresolved(m.group(0), str(e.args[0]) if e.args else "does not resolve",
                                          source, anchor))
                return m.group(0)
        return PLACEHOLDER.sub(sub, text), missing

    def _one(self, kind: str, arg: str) -> str:
        p = self.project
        if kind in ("sec", "ch"):
            if kind == "ch" and "/" in arg:
                raise LookupError("{ch:} takes a chapter key; use {sec:chapter/section}")
            ch, _, sec = arg.partition("/")
            num = p.number(ch, sec or None)
            if num is None:
                what = f"section '{arg}'" if sec else f"chapter '{ch}'"
                raise LookupError(f"{what} is not in this document")
            return num
        if kind in ("fig", "view"):
            items = p.figures if kind == "fig" else p.views
            for f in items:
                if f.name == arg:
                    return f.label
            raise LookupError(f"no {'FIGURE' if kind == 'fig' else 'VIEW'} named '{arg}'")
        if kind in ("count", "ids"):
            rtype, where = _selector(arg)
            reg = p.registers.get(rtype)
            if reg is None:
                raise LookupError(f"'{rtype}' is not an artefact type of this document")
            bad = reg.type.check_where(where)
            if bad:
                raise LookupError("; ".join(bad))
            recs = reg.filter(where)
            return str(len(recs)) if kind == "count" else id_list([r.id for r in recs])
        if kind == "reg":
            rid, dot, fname = arg.rpartition(".")
            if not dot or not rid:
                raise LookupError("{reg:} takes <id>.<field>")
            rec = p.record(rid)
            if rec is None:
                raise LookupError(f"no record with id '{rid}'")
            if fname not in ("id", "title", "status") and fname not in rec.type.fields:
                raise LookupError(f"'{fname}' is not a field of {rec.type.key}")
            v = rec.get(fname)
            if v is None or v == "":
                raise LookupError(f"{rid}.{fname} is empty")
            return rec.text(fname)
        if kind == "dep":
            ref, _, target = arg.partition(":")
            return p.dependency_reference(ref, target)
        if kind == "p":
            logical = p.layer == "logical"
            if not p.profile.is_set(arg) or p.profile.text(arg, logical) is None:
                raise LookupError(f"profile value '{arg}' is not set")
            return p.profile.text(arg, logical)
        if kind == "cat":
            return p.catalogue_count(arg)
        if kind == "doc":
            v: Any = p.config
            for part in arg.split("."):
                if isinstance(v, dict) and part in v:
                    v = v[part]
                else:
                    raise LookupError(f"arch-doc.yaml has no '{arg}'")
            if isinstance(v, (dict, list)) or v is None:
                raise LookupError(f"arch-doc.yaml '{arg}' is not a single value")
            return display(v)
        raise LookupError(f"unknown placeholder kind '{kind}'")


def _selector(arg: str) -> tuple[str, Where]:
    toks = split_args(arg)
    if not toks:
        raise LookupError("needs a register type")
    rtype, rest = toks[0], toks[1:]
    if rest:
        if rest[0] != "where" or len(rest) == 1:
            raise LookupError("expected '<type> where field=value'")
        try:
            return rtype, parse_conditions(rest[1:])
        except ValueError as e:
            raise LookupError(str(e)) from e
    return rtype, Where()


def content_tbcs(text: str) -> list[Tbc]:
    """The TBCs written in prose: ``TBC`` or ``TBC: <owner>``. The owner runs
    to the next punctuation mark. Placeholders are ignored, so a resolved
    ``{reg:}`` value is not counted twice, and "TBC" used as a noun ("Every
    TBC has an owner") is not a TBC (:func:`archdoc.registers.tbc_markers`)."""
    return embedded_tbcs(text)


# ------------------------------------------------------------------ inline

_INLINE = re.compile(
    r"(?P<code>`[^`]+`)|(?P<bold>\*\*[^*]+\*\*|__[^_]+__)|(?P<em>\*[^*\s][^*]*\*|_[^_\s][^_]*_)"
    r"|(?P<link>\[[^\]]+\]\([^)\s]+\))")


def inline_runs(text: str) -> list[tuple[str, set[str], str | None]]:
    """Split text into ``(text, styles, href)`` runs. Styles are any of
    ``bold``, ``em``, ``code``; ``href`` is set for links."""
    out: list[tuple[str, set[str], str | None]] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], set(), None))
        tok = m.group(0)
        if m.group("code"):
            out.append((tok[1:-1], {"code"}, None))
        elif m.group("bold"):
            out.append((tok[2:-2], {"bold"}, None))
        elif m.group("em"):
            out.append((tok[1:-1], {"em"}, None))
        else:
            lm = re.match(r"\[([^\]]+)\]\(([^)\s]+)\)", tok)
            out.append((lm.group(1), set(), lm.group(2)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], set(), None))
    return out


def plain(text: str) -> str:
    """Text with inline Markdown removed."""
    return "".join(t for t, _, _ in inline_runs(text))


def read_model(path: Path) -> dict | None:
    """An EA model JSON (arch-diagram's format), or None when absent."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def model_counts(data: dict) -> dict[str, int]:
    """Objects by type."""
    counts: dict[str, int] = {}
    for o in data.get("objects", []):
        t = o.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def load_catalogue(cat: Catalogue, root: Path) -> None:
    """Fill a catalogue's rows from its EA model JSON: object counts by
    type, largest first."""
    data = read_model(root / cat.model_path)
    cat.raw_header = ["Object type", "Objects"]
    if data is None:
        cat.found = False
        cat.raw_rows = []
        return
    counts = model_counts(data)
    cat.found = True
    cat.raw_rows = [[t, str(n)] for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
