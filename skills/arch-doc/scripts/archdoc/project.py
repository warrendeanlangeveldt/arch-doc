"""A loaded project: arch-doc.yaml, profile, metamodel, registers and content.

:meth:`Project.load` reads everything into one object that every output and
check reads from. Loading:

1. reads ``arch-doc.yaml`` and the profile it names;
2. loads the metamodel and applies the profile and document kind to it;
3. loads one register per artefact type (a missing file is an empty register);
4. parses ``content/*.md``, places blocks in the effective sections and adds
   ``[new]`` sections where they appear;
5. numbers chapters and sections sequentially (after filtering), assigns
   anchors and figure/view numbers;
6. resolves placeholders, including ``{dep:}`` through the projects named by
   ``depends_on[].path``.

Problems in the data never stop loading; they are collected in
``Project.issues`` for the checks. Only an unreadable arch-doc.yaml, profile
or metamodel raises :class:`ProjectError`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

from . import content as C
from .metamodel import EffectiveModel, Metamodel, MetamodelError, load_metamodel
from .profile import Profile, ProfileError, load_profile, slug
from .registers import Problem, Record, Register, Source, Tbc, as_list, is_owner

CONFIG = "arch-doc.yaml"
KINDS = ("solution", "capability")
LAYERS = ("logical", "logical-and-physical")
REQUIRED = ("title", "kind", "version")
# A dependency title ending in one of these already names the document.
DOC_NOUNS = ("design", "document", "sad", "hld", "lld", "specification", "architecture")
EXCLUDED = "is excluded by the profile, the document kind or arch-doc.yaml exclude"


class ProjectError(ValueError):
    """Raised when a project cannot be loaded at all."""


def person(entry: Any) -> tuple[str, list[str]]:
    """An arch-doc.yaml person (``author``, ``owner``): the name, and the
    role and team that describe it. A role or team the name already says is
    left out, so ``{name: Solution Architect, role: Architect}`` reads as
    "Solution Architect" and not "Solution Architect, Architect". A plain
    value is a name with no details."""
    if not isinstance(entry, dict):
        return ("" if entry in (None, "") else str(entry)), []
    name = "" if entry.get("name") in (None, "") else str(entry["name"])
    said = [name.lower()] if name else []
    details: list[str] = []
    for k in ("role", "team"):
        v = entry.get(k)
        if v in (None, ""):
            continue
        v = str(v)
        low = v.lower()
        if any(low == x or re.search(rf"(?<!\w){re.escape(low)}(?!\w)", x) for x in said):
            continue
        details.append(v)
        said.append(low)
    return name, details


def person_line(entry: Any) -> str:
    """A person as one line of text: "Priya Nair, Solution Architect, Parcels Digital"."""
    name, details = person(entry)
    return ", ".join([x for x in [name] if x] + details)


@dataclass
class Section:
    """A numbered section. ``new`` is True for a ``## Title [new]`` section
    not in the metamodel (it has no guidance or artefacts)."""

    key: str
    title: str
    number: str
    anchor: str
    chapter: "Chapter"
    guidance: str = ""
    artefacts: list = field(default_factory=list)
    optional: bool = False
    new: bool = False
    source: Source | None = None
    blocks: list[C.Block] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    template_columns: list[list[str]] = field(default_factory=list)

    @property
    def path(self) -> str:
        return f"{self.chapter.key}/{self.key}"

    @property
    def filled(self) -> bool:
        return bool(self.blocks)


@dataclass
class Chapter:
    """A numbered chapter: metamodel attributes, the lead-in blocks and its
    sections."""

    key: str
    title: str
    number: int
    anchor: str
    question: str
    story: str
    picture: dict
    deck: dict
    viewpoints: list[str]
    sections: list[Section] = field(default_factory=list)
    lead: list[C.Block] = field(default_factory=list)
    source: Source | None = None

    def section(self, key: str) -> Section | None:
        for s in self.sections:
            if s.key == key:
                return s
        return None

    def blocks(self) -> Iterator[C.Block]:
        """Lead-in blocks, then each section's, in order."""
        yield from self.lead
        for s in self.sections:
            yield from s.blocks

    @property
    def figures(self) -> list[C.Figure]:
        return [b for b in self.blocks() if isinstance(b, C.Figure)]

    @property
    def registers_used(self) -> list[str]:
        out: list[str] = []
        for s in self.sections:
            for a in s.artefacts:
                if a.type not in out:
                    out.append(a.type)
            for b in s.blocks:
                if isinstance(b, C.RegisterTable) and b.type not in out:
                    out.append(b.type)
        return out


@dataclass
class TbcItem:
    """One open TBC: who owns it and where it is.

    ``origin`` is ``register`` (a record field) or ``content`` (prose).
    ``record`` and ``field`` are set for register TBCs; ``anchor`` is where
    it shows in the document (the register row citing the record, or the
    block), or None when nothing cites the record.
    """

    owner: str | None
    origin: str
    source: Source | None
    anchor: str | None
    record: str | None = None
    field: str | None = None
    inherited: bool = False
    context: str = ""        # the resolved, plain text it sits in (first 120 characters)
    text: str = ""           # that text in full: the field's shown value, or the sentence / cell around the TBC

    @property
    def key(self) -> str:
        """What the TBC is open on, for de-duplication: its record, or the
        paragraph, list item or table row it is written in."""
        if self.record:
            return f"record:{self.record}"
        return f"content:{self.anchor or self.source}"


@dataclass
class OpenItem:
    """One open item: every TBC on one record, or in one paragraph, list
    item or table row, folded into one entry.

    ``id`` is the record id, or the anchor of the prose it is in. ``text`` is
    one line of resolved plain text (no placeholders, no inline Markdown),
    cut at a word boundary: the record's title, followed by the open value
    when a TBC sits inside a longer value, or the sentence or table cell
    around the TBC. ``owner`` is None when any of the item's TBCs has no
    owner; otherwise the record's accountable owner when it holds one of
    them, else the first named. ``owners`` lists every owner named.
    ``inherited`` is True when every TBC took its owner from the record.
    An owner slot that names no owner (:func:`~archdoc.registers.is_owner`)
    leaves ``owner`` None and is kept as ``owner_text``.
    ``section`` is the section (or chapter) it shows in, as
    "7.3 Component Design", with ``section_anchor``; both None for a record
    no REGISTER table shows. ``fields`` are the record fields that are TBC.
    ``tbcs`` are the folded :class:`TbcItem` entries."""

    id: str
    text: str
    owner: str | None
    anchor: str | None
    section: str | None
    section_anchor: str | None
    inherited: bool
    origin: str
    record: str | None = None
    fields: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    source: Source | None = None
    tbcs: list[TbcItem] = field(default_factory=list)
    owner_text: str | None = None   # an owner slot that names no owner ("whether ..."); then ``owner`` is None


def one_line(text: str, limit: int = 140) -> str:
    """Plain text on one line, at most ``limit`` characters, cut at a word
    boundary with an ellipsis."""
    t = " ".join(C.plain(text).split())
    if len(t) <= limit:
        return t
    cut = t[:limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-\u2013\u2014") + "\u2026"


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9{(\[\"'])")


def tbc_sentence(text: str) -> str:
    """The sentence of ``text`` that holds a TBC (all of it when none
    does)."""
    for sent in _SENTENCE.split(text):
        if re.search(r"\bTBC\b", sent):
            return sent
    return text


class Project:
    """One document. See the package docstring for the public API."""

    def __init__(self, root: Path):
        self.root = root
        self.config: dict = {}
        self.profile: Profile = None  # type: ignore[assignment]
        self.metamodel: Metamodel = None  # type: ignore[assignment]
        self.model: EffectiveModel = None  # type: ignore[assignment]
        self.registers: dict[str, Register] = {}
        self.chapters: list[Chapter] = []
        self.figures: list[C.Figure] = []
        self.views: list[C.View] = []
        self.issues: list[Problem] = []
        self._deps: dict[str, Project | None] | None = None
        self._cited: dict[str, Project | None] = {}
        self._stack: tuple[Path, ...] = ()
        self._row_anchor: dict[str, str] = {}

    # ----------------------------------------------------------- loading
    @classmethod
    def load(cls, root: str | Path = ".", _stack: tuple[Path, ...] = ()) -> "Project":
        root = Path(root).resolve()
        p = cls(root)
        p._stack = _stack + (root,)
        p._load_config()
        p._load_profile_and_model()
        p._load_registers()
        p._load_content()
        p._resolve()
        return p

    def rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def _load_config(self) -> None:
        cfg = self.root / CONFIG
        if not cfg.exists():
            raise ProjectError(f"no {CONFIG} in {self.root}")
        try:
            data = yaml.safe_load(cfg.read_text()) or {}
        except yaml.YAMLError as e:
            raise ProjectError(f"{cfg}: YAML error: {e}") from e
        if not isinstance(data, dict):
            raise ProjectError(f"{cfg}: must be a mapping")
        missing = [k for k in REQUIRED if not data.get(k)]
        if missing:
            raise ProjectError(f"{cfg}: missing {', '.join(missing)}")
        if data["kind"] not in KINDS:
            raise ProjectError(f"{cfg}: kind '{data['kind']}' is not one of {', '.join(KINDS)}")
        data.setdefault("layer", "logical-and-physical")
        if data["layer"] not in LAYERS:
            raise ProjectError(f"{cfg}: layer '{data['layer']}' is not one of {', '.join(LAYERS)}")
        data["version"] = str(data["version"])
        if data.get("date") is not None:
            data["date"] = str(data["date"])
        data.setdefault("short", "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", data["title"])).upper())
        data.setdefault("metamodel", "seed")
        data.setdefault("profile", "profile.yaml")
        data.setdefault("template", None)
        data.setdefault("depends_on", [])
        data.setdefault("history", [])
        data.setdefault("banned_terms", [])
        data.setdefault("exclude", [])
        if not isinstance(data["exclude"], list):
            raise ProjectError(f"{cfg}: exclude must be a list of chapter or chapter/section keys")
        data.setdefault("consumers", [])
        data.setdefault("cites", [])
        for key in ("depends_on", "consumers", "cites"):
            if not isinstance(data[key] or [], list):
                raise ProjectError(f"{cfg}: {key} must be a list")
        refs: dict[str, str] = {}
        for key in ("depends_on", "consumers", "cites"):
            for i, d in enumerate(data[key] or []):
                if key == "consumers" and isinstance(d, str):
                    continue  # a consumer named by title only: drawn, not citable
                if not isinstance(d, dict) or not d.get("title") or (key != "consumers" and not d.get("ref")):
                    need = "a title" if key == "consumers" else "at least a title and a ref"
                    self.issues.append(Problem("xref", f"{key}[{i}] needs {need}", Source(CONFIG)))
                    continue
                ref = d.get("ref")
                if ref:
                    if ref in refs:
                        self.issues.append(Problem("xref", f"{key} {ref}: the ref is also used in {refs[ref]}; "
                                                   f"a ref names one design", Source(CONFIG)))
                    refs.setdefault(ref, key)
                elif d.get("sections") or d.get("path"):
                    self.issues.append(Problem("xref", f"{key}[{i}] {d['title']}: give it a ref so "
                                               f"{{dep:<ref>:n.n}} can cite it", Source(CONFIG)))
                secs = d.get("sections")
                if secs is not None and not isinstance(secs, dict):
                    self.issues.append(Problem("xref", f"{key} {ref or d['title']}: sections must map section "
                                               f"numbers to titles", Source(CONFIG)))
                elif secs:
                    bad = [k for k in secs if not isinstance(k, str)]
                    if bad:
                        self.issues.append(Problem("xref", f"{key} {ref or d['title']}: quote the section numbers "
                                                   f"in sections ({', '.join(map(str, bad))}); unquoted, YAML "
                                                   f"reads 10.10 as the number 10.1", Source(CONFIG)))
        self.config = data

    def _load_profile_and_model(self) -> None:
        try:
            self.profile = load_profile(self.root / self.config["profile"])
        except ProfileError as e:
            raise ProjectError(str(e)) from e
        try:
            self.metamodel = load_metamodel(str(self.config["metamodel"]), self.root)
            exclude = [str(e) for e in self.config["exclude"]]
            known = self.metamodel.keys()
            for e in exclude:
                if e not in known:
                    self.issues.append(Problem("xref", f"exclude: '{e}' is not a chapter or chapter/section key "
                                               f"of the metamodel", Source(CONFIG)))
            self.model = self.metamodel.apply(self.profile, self.config["kind"], self.config["layer"], exclude)
        except MetamodelError as e:
            raise ProjectError(str(e)) from e

    def _load_registers(self) -> None:
        rdir = self.root / "registers"
        for key, t in self.metamodel.artefact_types.items():
            path = rdir / f"{key}.yaml"
            reg = Register.load(t, path, self.rel(path))
            self.registers[key] = reg
            self.issues.extend(reg.problems)
        if rdir.exists():
            for f in sorted(rdir.glob("*.yaml")):
                if f.stem not in self.metamodel.artefact_types:
                    self.issues.append(Problem("schema", f"'{f.stem}' is not an artefact type of the metamodel",
                                               Source(self.rel(f))))
        # References between records.
        for reg in self.registers.values():
            for rec in reg:
                for fname, spec in rec.type.fields.items():
                    if spec.kind not in ("ref", "refs"):
                        continue
                    target = self.registers.get(spec.ref_type)
                    for rid in as_list(rec.data.get(fname)):
                        if isinstance(rid, Tbc):
                            continue
                        if target is None or target.get(str(rid)) is None:
                            self.issues.append(Problem(
                                "ids", f"{rec.id}.{fname}: no {spec.ref_type} with id '{rid}'", rec.source))

    def _load_content(self) -> None:
        cdir = self.root / "content"
        parsed: dict[str, C.ParsedChapter] = {}
        if cdir.exists():
            for f in sorted(cdir.glob("*.md")):
                pc = C.parse_file(f, self.rel(f))
                self.issues.extend(pc.problems)
                if pc.key is None:
                    continue
                if pc.key in parsed:
                    self.issues.append(Problem("content", f"chapter '{pc.key}' is also in {parsed[pc.key].source.file}",
                                               pc.source))
                    continue
                if self.model.chapter(pc.key) is None:
                    why = EXCLUDED if self.metamodel.chapter(pc.key) else "is not a chapter of the metamodel"
                    self.issues.append(Problem("content", f"chapter '{pc.key}' {why}", pc.source))
                    continue
                parsed[pc.key] = pc
        figs, views = [0], [0]
        for ci, ech in enumerate(self.model.chapters, start=1):
            ch = Chapter(ech.key, ech.title, ci, f"s{ci}", ech.question, ech.story, ech.picture, ech.deck,
                         ech.viewpoints)
            pc = parsed.get(ech.key)
            order = self._section_order(ech, pc)
            for si, (es, ps, new_heading) in enumerate(order, start=1):
                if es is not None:
                    sec = Section(es.key, es.title, f"{ci}.{si}", f"s{ci}-{si}", ch, es.guidance,
                                  list(es.artefacts), es.optional, False, labels=dict(es.labels),
                                  template_columns=[list(h) for h in es.template_columns])
                else:
                    sec = Section(new_heading[0], new_heading[1], f"{ci}.{si}", f"s{ci}-{si}", ch, new=True)
                if ps is not None:
                    sec.source = ps.source
                    sec.blocks = ps.blocks
                ch.sections.append(sec)
            if pc is not None:
                ch.source = pc.source
                ch.lead = pc.lead
            C.assign_anchors(ch.anchor, ch.lead, figs, views)
            for sec in ch.sections:
                C.assign_anchors(sec.anchor, sec.blocks, figs, views)
            self.chapters.append(ch)
        for b in self.blocks():
            if isinstance(b, C.View):
                self.views.append(b)
            elif isinstance(b, C.Figure):
                self.figures.append(b)

    def _section_order(self, ech, pc: C.ParsedChapter | None):
        """The final section order for one chapter: effective sections in
        metamodel order, with [new] sections inserted after the section
        that precedes them in the content file. Each entry is
        ``(EffectiveSection | None, ParsedSection | None, (key, title) | None)``."""
        entries: list[list[Any]] = [[es, None, None] for es in ech.sections]
        if pc is None:
            return [tuple(e) for e in entries]
        by_key = {es.key: i for i, es in enumerate(ech.sections)}
        by_title = {es.title.lower(): i for i, es in enumerate(ech.sections)}
        excluded = {}
        raw = self.metamodel.chapter(ech.key) or {}
        for s in raw.get("sections") or []:
            if s["key"] not in by_key:
                excluded[s["key"]] = s
        used_keys = set(by_key)
        prev: list[Any] | None = None
        for ps in pc.sections:
            idx = by_key.get(ps.heading)
            if idx is None:
                idx = by_title.get(ps.heading.lower())
            if idx is not None and not ps.new:
                entry = next(e for e in entries if e[0] is ech.sections[idx])
                if entry[1] is not None:
                    self.issues.append(Problem("content", f"section '{ps.heading}' appears twice in "
                                               f"chapter '{ech.key}'", ps.source))
                    entry[1].blocks.extend(ps.blocks)
                else:
                    entry[1] = ps
                prev = entry
                continue
            if ps.new:
                key = slug(ps.heading) or "section"
                base, n = key, 2
                while key in used_keys:
                    key, n = f"{base}-{n}", n + 1
                used_keys.add(key)
                entry = [None, ps, (key, ps.heading)]
                pos = next(i for i, e in enumerate(entries) if e is prev) + 1 if prev is not None else 0
                entries.insert(pos, entry)
                prev = entry
                continue
            if ps.heading in excluded:
                why = EXCLUDED
            else:
                why = "is not a section of this chapter (mark an added section '## Title [new]')"
            self.issues.append(Problem("content", f"section '{ps.heading}' {why}", ps.source))
        return [tuple(e) for e in entries]

    def _resolve(self) -> None:
        r = C.Resolver(self)
        record_issues = self._resolve_records(r)
        for ch in self.chapters:
            for sec in [None] + ch.sections:
                for b in (ch.lead if sec is None else sec.blocks):
                    self._resolve_block(r, b, sec)
        for b in self.blocks():
            for u in b.unresolved:
                self.issues.append(Problem("xref", f"{u.token}: {u.reason}", u.source, u.anchor))
        for rec, issue in record_issues:
            issue.anchor = self._row_anchor.get(rec.id)
            self.issues.append(issue)

    def _resolve_records(self, r: C.Resolver) -> list[tuple[Record, Problem]]:
        """Fill placeholders in record values, as in table cells. The text
        goes to ``Record.resolved``; the stored value is untouched."""
        out = []
        for reg in self.registers.values():
            for rec in reg:
                for fname, v in rec.data.items():
                    if fname in ("id", "status"):
                        continue
                    items = v if isinstance(v, list) else [v]
                    if not any(isinstance(x, str) and "{" in x for x in items):
                        continue
                    texts = []
                    for x in items:
                        if isinstance(x, str):
                            t, un = r.resolve(x, rec.source)
                            texts.append(t)
                            out += [(rec, Problem("xref", f"{rec.id}.{fname}: {u.token}: {u.reason}", rec.source))
                                    for u in un]
                        else:
                            texts.append(C.display(x))
                    rec.resolved[fname] = ", ".join(texts)
        return out

    def header_label(self, rtype: str, column: str, section: Section | None = None,
                     block: C.RegisterTable | None = None) -> str:
        """A register column's header: the REGISTER directive's labels, then
        the section's (its ``labels:`` or the template's ``column_map``),
        then the type's."""
        if block is not None and column in block.labels:
            return block.labels[column]
        if section is not None and column in section.labels:
            return section.labels[column]
        return self.registers[rtype].type.header(column)

    def _resolve_block(self, r: C.Resolver, b: C.Block, section: Section | None = None) -> None:
        if isinstance(b, C.Para):
            b.text, b.unresolved = r.resolve(b.raw, b.source, b.anchor)
        elif isinstance(b, C.Bullets):
            b.items = []
            for raw, src, anc in zip(b.raw_items, b.item_sources, b.item_anchors):
                t, u = r.resolve(raw, src, anc)
                b.items.append(t)
                b.unresolved += u
            b.text = "\n".join(b.items)
        elif isinstance(b, C.RegisterTable):
            reg = self.registers.get(b.type)
            if reg is None:
                b.unresolved.append(C.Unresolved(f"REGISTER {b.type}", f"'{b.type}' is not an artefact type",
                                                 b.source, b.anchor))
                return
            for e in reg.type.check_where(b.where):
                b.unresolved.append(C.Unresolved(b.raw, e, b.source, b.anchor))
            if not b.columns:
                b.columns = list(reg.type.columns)
            known = {"id", "title", "status"} | set(reg.type.fields)
            bad = [c for c in b.columns if c not in known]
            for c in bad:
                b.unresolved.append(C.Unresolved(b.raw, f"'{c}' is not a field of {b.type}", b.source, b.anchor))
            for c in b.labels:
                if c not in known:
                    b.unresolved.append(C.Unresolved(b.raw, f"label for '{c}', not a field of {b.type}",
                                                     b.source, b.anchor))
            b.columns = [c for c in b.columns if c in known]
            b.records = reg.filter(b.where)
            b.header = [self.header_label(b.type, c, section, b) for c in b.columns]
            b.raw_header = list(b.header)
            b.body = [rec.cells(b.columns, short=False) for rec in b.records]
            b.compact_rows = [rec.cells(b.columns) for rec in b.records]
            b.raw_rows = [rec.row(b.columns) for rec in b.records]
            b.chips = [rec.chip for rec in b.records]
            b.row_anchors = C.row_anchors(b, len(b.records))
            b.row_sources = [rec.source for rec in b.records]
            for rec, anc in zip(b.records, b.row_anchors):
                self._row_anchor.setdefault(rec.id, anc)
            b.text = "\n".join(" | ".join(row) for row in b.body)
        elif isinstance(b, C.Catalogue):
            if not self.profile.ea_metamodel:
                b.unresolved.append(C.Unresolved("CATALOGUE", "the profile names no EA metamodel",
                                                 b.source, b.anchor))
            C.load_catalogue(b, self.root)
            if not b.found:
                b.unresolved.append(C.Unresolved("CATALOGUE", f"model file {b.model_path} not found",
                                                 b.source, b.anchor))
            b.header = list(b.raw_header)
            b.body = [list(row) for row in b.raw_rows]
            b.row_anchors = C.row_anchors(b, len(b.body))
            b.text = "\n".join(" | ".join(row) for row in b.body)
        elif isinstance(b, C.Table):
            b.header = []
            for cell in b.raw_header:
                t, u = r.resolve(cell, b.source, b.header_anchor)
                b.header.append(t)
                b.unresolved += u
            b.row_anchors = C.row_anchors(b, len(b.raw_rows))
            b.body = []
            for row, src, anc in zip(b.raw_rows, b.row_sources, b.row_anchors):
                out = []
                for cell in row:
                    t, u = r.resolve(cell, src, anc)
                    out.append(t)
                    b.unresolved += u
                b.body.append(out)
            b.text = "\n".join(" | ".join(row) for row in b.body)
        elif isinstance(b, C.View):
            b.title, b.unresolved = r.resolve(b.raw_title, b.source, b.anchor)
            b.caption = b.title
            vp = self._viewpoint(b.viewpoint_ref)
            if vp is None:
                b.unresolved.append(C.Unresolved(b.viewpoint_ref, "is not a viewpoint of the metamodel",
                                                 b.source, b.anchor))
            else:
                b.viewpoint = vp.key
                b.ea_name = vp.name_for(self.profile.ea_metamodel)
                # the organisation may call a viewpoint something else: profile
                # systems.ea_viewpoint_names maps a viewpoint key, or its standard EA name, to theirs
                names = self.profile.get("systems.ea_viewpoint_names") or {}
                if isinstance(names, dict):
                    b.ea_name = names.get(vp.key) or names.get(b.ea_name or "") or b.ea_name
            self._find_figure_files(b)
            b.text = f"{b.label}. {b.title}"
        elif isinstance(b, C.Figure):
            b.caption, b.unresolved = r.resolve(b.raw_caption, b.source, b.anchor)
            self._find_figure_files(b)
            b.text = f"{b.label}. {b.caption}"

    def _viewpoint(self, ref: str):
        vps = self.model.viewpoints
        if ref in vps:
            return vps[ref]
        low = ref.lower()
        ea = self.profile.ea_metamodel
        for vp in vps.values():
            if vp.title.lower() == low or (ea and (vp.ea.get(ea) or "").lower() == low):
                return vp
        return None

    def _find_figure_files(self, f: C.Figure) -> None:
        d = self.root / "diagrams"
        for ext in (".png", ".svg"):
            if (d / f"{f.name}{ext}").exists():
                f.path = d / f"{f.name}{ext}"
                break
        for ext in (".mmd", ".ead", ".py"):
            if (d / f"{f.name}{ext}").exists():
                f.source_file = d / f"{f.name}{ext}"
                break

    # ------------------------------------------------------------- queries
    @property
    def title(self) -> str:
        return self.config["title"]

    @property
    def short(self) -> str:
        return self.config["short"]

    @property
    def kind(self) -> str:
        return self.config["kind"]

    @property
    def layer(self) -> str:
        return self.config["layer"]

    @property
    def version(self) -> str:
        return self.config["version"]

    def chapter(self, key: str) -> Chapter | None:
        for c in self.chapters:
            if c.key == key:
                return c
        return None

    def section(self, chapter_key: str, section_key: str) -> Section | None:
        ch = self.chapter(chapter_key)
        return ch.section(section_key) if ch else None

    def number(self, chapter_key: str, section_key: str | None = None) -> str | None:
        """The rendered number of a chapter ("7") or section ("7.3"), or None
        when it is not in this document."""
        ch = self.chapter(chapter_key)
        if ch is None:
            return None
        if not section_key:
            return str(ch.number)
        s = ch.section(section_key)
        return s.number if s else None

    def by_number(self, number: str) -> Chapter | Section | None:
        """The chapter or section with a rendered number."""
        for ch in self.chapters:
            if str(ch.number) == number:
                return ch
            for s in ch.sections:
                if s.number == number:
                    return s
        return None

    def blocks(self) -> Iterator[C.Block]:
        for ch in self.chapters:
            yield from ch.blocks()

    def record(self, rid: str) -> Record | None:
        for reg in self.registers.values():
            r = reg.get(rid)
            if r is not None:
                return r
        return None

    def unresolved(self) -> list[C.Unresolved]:
        return [u for b in self.blocks() for u in b.unresolved]

    def catalogue_model(self) -> Path:
        """The EA model the catalogue reads: the first CATALOGUE directive's
        path, else diagrams/model.json."""
        for b in self.blocks():
            if isinstance(b, C.Catalogue):
                return self.root / b.model_path
        return self.root / C.DEFAULT_MODEL

    def catalogue_count(self, what: str) -> str:
        """``{cat:objects}``, ``{cat:relationships}`` or ``{cat:<object type>}``
        from the EA model. Raises LookupError when it does not resolve."""
        path = self.catalogue_model()
        data = C.read_model(path)
        if data is None:
            raise LookupError(f"model file {self.rel(path)} not found")
        if what == "objects":
            return str(len(data.get("objects", [])))
        if what == "relationships":
            return str(len(data.get("relationships", [])))
        counts = C.model_counts(data)
        for t, n in counts.items():
            if t.lower() == what.lower() or slug(t) == slug(what):
                return str(n)
        raise LookupError(f"the model has no objects of type '{what}' (it has {', '.join(sorted(counts)) or 'none'})")

    def resolve_text(self, text: str, source: Source | None = None) -> tuple[str, list[C.Unresolved]]:
        """Fill placeholders in any text (deck claims, notes, captions)."""
        return C.Resolver(self).resolve(text, source)

    def tbcs(self) -> list[TbcItem]:
        """Every TBC in the registers and the prose, with its owner (None when
        it has none) and its anchor. A register TBC is one per record field;
        a prose TBC one per occurrence. ``context`` and ``text`` are resolved
        text. See :meth:`open_items` for one entry per record or prose
        location."""
        out: list[TbcItem] = []
        for reg in self.registers.values():
            for rec in reg:
                for fname, t in rec.all_tbcs():
                    shown = rec.shown(fname)
                    out.append(TbcItem(t.owner, "register", rec.source, self._row_anchor.get(rec.id),
                                       rec.id, fname, t.inherited, f"{rec.id} {fname}", shown))
        for raw, text, src, anc in self._content_pieces():
            for t in C.content_tbcs(raw):
                flat = " ".join(C.plain(text).split())
                out.append(TbcItem(t.owner, "content", src, anc, context=flat[:120], text=flat))
        return out

    def _content_pieces(self) -> Iterator[tuple[str, str, Source, str | None]]:
        """(raw, resolved, source, anchor) for every piece of prose a TBC can
        be written in. A table cell is one piece, read with its row's first
        cell ("Peering: TBC: Network team"), never the row joined."""
        for b in self.blocks():
            if isinstance(b, C.Para):
                yield b.raw, b.text, b.source, b.anchor
            elif isinstance(b, C.Bullets):
                yield from zip(b.raw_items, b.items, b.item_sources, b.item_anchors)
            elif isinstance(b, (C.RegisterTable, C.Catalogue)):
                continue
            elif isinstance(b, C.Table):
                for raw, text in zip(b.raw_header, b.header):
                    yield raw, text, b.source, b.header_anchor
                for raw_row, row, src, anc in zip(b.raw_rows, b.body, b.row_sources, b.row_anchors):
                    for i, (raw, text) in enumerate(zip(raw_row, row)):
                        lead = row[0].strip() if i > 0 and row and row[0].strip() else ""
                        yield raw, (f"{lead}: {text}" if lead else text), src, anc
            elif isinstance(b, C.Figure):
                yield b.raw_caption, b.caption, b.source, b.anchor

    def anchor_sections(self) -> dict[str, tuple[int, Chapter, Section | None]]:
        """Every anchor (block, list item, table header and row) to its
        document order, chapter and section (None for a lead-in)."""
        out: dict[str, tuple[int, Chapter, Section | None]] = {}
        n = 0
        for ch in self.chapters:
            for sec in [None] + ch.sections:
                blocks = ch.lead if sec is None else sec.blocks
                for a in [ch.anchor if sec is None else sec.anchor]:
                    out.setdefault(a, (n, ch, sec))
                    n += 1
                for b in blocks:
                    anchors = [b.anchor, getattr(b, "header_anchor", None)]
                    anchors += list(getattr(b, "item_anchors", [])) + list(getattr(b, "row_anchors", []))
                    for a in anchors:
                        if a:
                            out.setdefault(a, (n, ch, sec))
                            n += 1
        return out

    def open_items(self, limit: int = 140) -> list[OpenItem]:
        """One :class:`OpenItem` per record with a TBC and per paragraph,
        list item or table row with one, in document order (records no
        table shows last). Built from :meth:`tbcs`, so the two always
        agree; ``len(open_items())`` is the open-item count."""
        where = self.anchor_sections()
        groups: dict[str, list[TbcItem]] = {}
        for t in self.tbcs():
            groups.setdefault(t.key, []).append(t)
        out: list[tuple[tuple, OpenItem]] = []
        for i, (key, ts) in enumerate(groups.items()):
            first = ts[0]
            loc = where.get(first.anchor) if first.anchor else None
            if loc is None:
                section = section_anchor = None
            elif loc[2] is None:
                section, section_anchor = f"{loc[1].number} {loc[1].title}", loc[1].anchor
            else:
                section, section_anchor = f"{loc[2].number} {loc[2].title}", loc[2].anchor
            named = []
            for t in ts:
                if t.owner and t.owner not in named:
                    named.append(t.owner)
            if first.origin == "register":
                rec = self.record(first.record)
                who = rec.accountable if rec else None
                owner = None if any(t.owner is None for t in ts) else (
                    who if who in named else (named[0] if named else None))
                title = rec.text("title") if rec else first.record
                details = []
                for t in ts:
                    if rec is None or t.field == "title" or isinstance(rec.get(t.field), Tbc):
                        continue  # the title is the text already; a whole-value TBC says nothing more
                    d = tbc_sentence(" ".join(C.plain(t.text).split()))
                    if d and d != " ".join(C.plain(title).split()) and d not in details:
                        details.append(d)
                text = one_line(title + (": " + "; ".join(details) if details else ""), limit)
                item = OpenItem(first.record, text, owner, first.anchor, section, section_anchor,
                                all(t.inherited for t in ts), "register", first.record,
                                [t.field for t in ts], named, first.source, ts)
            else:
                owner = None if any(t.owner is None for t in ts) else named[0]
                text = one_line(tbc_sentence(first.text), limit)
                item = OpenItem(first.anchor or str(first.source), text, owner, first.anchor, section,
                                section_anchor, False, "content", None, [], named, first.source, ts)
            if item.owner and not is_owner(item.owner):
                item.owner_text, item.owner = item.owner, None   # the outputs show "No owner"
            out.append(((0, loc[0], i) if loc else (1, 0, i), item))
        return [item for _, item in sorted(out, key=lambda x: x[0])]

    # -------------------------------------------------------- dependencies
    @property
    def dependencies(self) -> dict[str, "Project | None"]:
        """Each ``depends_on`` ref to its loaded project (None when it has no
        path or cannot be loaded; the reason is in ``issues``)."""
        if self._deps is None:
            self._deps = {}
            for d in self.config.get("depends_on") or []:
                if not isinstance(d, dict) or not d.get("ref"):
                    continue
                ref = d["ref"]
                path = d.get("path")
                if not path:
                    self._deps[ref] = None
                    continue
                droot = (self.root / path).resolve()
                if droot in self._stack:
                    self.issues.append(Problem("xref", f"depends_on {ref}: dependency cycle through {path}",
                                               Source(CONFIG)))
                    self._deps[ref] = None
                    continue
                try:
                    self._deps[ref] = Project.load(droot, self._stack)
                except ProjectError as e:
                    self.issues.append(Problem("xref", f"depends_on {ref}: {e}", Source(CONFIG)))
                    self._deps[ref] = None
        return self._deps

    def dependency(self, ref: str) -> dict | None:
        """The ``depends_on`` entry with this ref, or None."""
        for d in self.config.get("depends_on") or []:
            if isinstance(d, dict) and d.get("ref") == ref:
                return d
        return None

    def citation(self, ref: str) -> tuple[dict, str] | None:
        """The entry ``{dep:<ref>}`` cites and where it is listed:
        ``depends_on`` (a design this one builds on), ``consumers`` (a design
        built on this one) or ``cites`` (one it only refers to). Only
        ``depends_on`` makes a design a dependency; the others are cited
        without being drawn or checked as one."""
        for key in ("depends_on", "consumers", "cites"):
            for d in self.config.get(key) or []:
                if isinstance(d, dict) and d.get("ref") == ref:
                    return d, key
        return None

    def cited_project(self, ref: str) -> "Project | None":
        """The loaded project of a cited design (any of the three lists)
        with a ``path``, or None. ``depends_on`` entries come from
        :attr:`dependencies`; ``consumers`` and ``cites`` load here, apart
        from them."""
        found = self.citation(ref)
        if found is None:
            return None
        d, key = found
        if key == "depends_on":
            return self.dependencies.get(ref)
        if ref not in self._cited:
            self._cited[ref] = None
            if d.get("path"):
                droot = (self.root / d["path"]).resolve()
                if droot in self._stack:
                    self.issues.append(Problem("xref", f"{key} {ref}: citation cycle through {d['path']}",
                                               Source(CONFIG)))
                else:
                    try:
                        self._cited[ref] = Project.load(droot, self._stack)
                    except ProjectError as e:
                        self.issues.append(Problem("xref", f"{key} {ref}: {e}", Source(CONFIG)))
        return self._cited[ref]

    def dependency_reference(self, ref: str, target: str = "") -> str:
        """The text ``{dep:<ref>:<target>}`` becomes. ``target`` is a rendered
        number ("7.3", "7") or a key path ("application/components",
        "application"). The ref may name a ``depends_on``, ``consumers`` or
        ``cites`` entry. Raises LookupError when it does not resolve."""
        found = self.citation(ref)
        if found is None:
            raise LookupError(f"no depends_on, consumers or cites entry with ref '{ref}'")
        d, key = found
        title = str(d["title"])
        words = re.findall(r"[A-Za-z]+", title)
        name = f"the {title}" if words and words[-1].lower() in DOC_NOUNS else f"the {title} design"
        if not target:
            return name
        dep = self.cited_project(ref)
        if dep is None:
            sections = d.get("sections") or {}
            if isinstance(sections, dict) and sections:
                if target not in {str(k) for k in sections}:
                    raise LookupError(f"{title} has no section {target} in its {key} sections")
                stitle = next(v for k, v in sections.items() if str(k) == target)
                kind = "section" if "." in target else "chapter"
                return f"{name}, {kind} {target} {stitle}"
            raise LookupError(f"{key} {ref} has no loadable path or sections map, so '{target}' "
                              f"cannot be looked up")
        if re.match(r"^\d+(\.\d+)?$", target):
            node = dep.by_number(target)
        else:
            ck, _, sk = target.partition("/")
            node = dep.section(ck, sk) if sk else dep.chapter(ck)
        if node is None:
            raise LookupError(f"{d['title']} has no section {target}")
        if isinstance(node, Chapter):
            return f"{name}, chapter {node.number} {node.title}"
        return f"{name}, section {node.number} {node.title}"

    # ------------------------------------------------------------ helpers
    def numbering(self) -> list[tuple[str, str, str]]:
        """``(number, title, key path)`` for every chapter and section."""
        out = []
        for ch in self.chapters:
            out.append((str(ch.number), ch.title, ch.key))
            for s in ch.sections:
                out.append((s.number, s.title, s.path + (" [new]" if s.new else "")))
        return out


__all__ = ["Project", "ProjectError", "Chapter", "Section", "TbcItem", "OpenItem", "one_line", "person",
           "person_line"]
