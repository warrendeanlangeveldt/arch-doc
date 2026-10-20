"""``archdoc extract <template.docx>``: a metamodel from an organisation's
own template (SPEC 4, "Extraction").

The template is read for structure, not names:

- chapters are its Heading 1 paragraphs and sections its Heading 2s, with
  the heading styles detected by outline level (through ``basedOn``), so a
  template whose headings are called anything at all still reads;
- each chapter is matched to the closest seed chapter by title similarity
  plus section overlap, in document order; a matched chapter takes the seed
  chapter's key, question, story, picture, deck run, viewpoints and
  ``when:``, and keeps the template's own title; its sections are matched
  the same way and inherit the seed section's key, guidance, artefacts and
  ``when:``;
- chapters and sections that match nothing are kept with
  ``unmatched: true`` and the template's own guidance text, for Claude to
  complete with the user;
- every table header in a section is recorded as ``template_columns``;
  for an unmatched section, a header that reads like an artefact type's
  columns proposes that type as the section's register, with
  ``column_map`` from header text to field.

It also writes the profile fragment the docx build needs to fill the
template in place: ``template.path``, ``template.styles`` (the detected
style for each role) and ``template.fields`` (cover text to replace, with
a guess for the title and version).

The metamodel written always loads with :func:`archdoc.metamodel.load_metamodel`.
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from docx.oxml.ns import qn

from . import metamodel as M
from .docx_build import (norm, match, chapter_score, detect_styles, own_text, paragraph_outline, pstyle_id,
                         similarity, style_table, tag, is_toc_sdt, ptext)
from .profile import slug

CHAPTER_THRESHOLD = 0.4
SECTION_THRESHOLD = 0.5
TYPE_THRESHOLD = 0.55
GENERIC_COLUMNS = {"id", "title", "status", "owner"}
_P = re.compile(r"\{p:[^{}]*\}")


class ExtractError(ValueError):
    """The template cannot be read as a design template."""


# ------------------------------------------------------------------ reading

def read_template(path: str | Path) -> tuple[Any, dict[str, str], list[dict]]:
    """``(doc, styles, chapters)``: the detected style roles and the
    chapter outline, each chapter ``{title, lead, sections}`` and each
    section ``{title, guidance: [text], tables: [[header]]}``."""
    doc = Document(str(path))
    styles = detect_styles(doc)
    if "h1" not in styles:
        raise ExtractError(f"{path}: no paragraphs at outline level 1 (Heading 1), so no chapters to read")
    st = style_table(doc)
    by_name = {s.name: sid for sid, s in st.items()}
    h1 = by_name.get(styles["h1"])
    h2 = by_name.get(styles.get("h2", ""), None)
    chapters: list[dict] = []
    target: dict | None = None

    def add_text(el):
        t = " ".join(own_text(el).split())
        if t and target is not None:
            target["guidance"].append(t)

    for el in doc.element.body.iterchildren():
        if tag(el) == "p":
            text = own_text(el).strip()
            sid = pstyle_id(el)
            if sid == h1 and text:
                chapters.append({"title": text, "lead": {"guidance": [], "tables": []}, "sections": []})
                target = chapters[-1]["lead"]
                continue
            if h2 and sid == h2 and text and chapters:
                sec = {"title": text, "guidance": [], "tables": []}
                chapters[-1]["sections"].append(sec)
                target = sec
                continue
            if paragraph_outline(el, st) is None:
                add_text(el)
        elif tag(el) == "tbl" and target is not None:
            trs = el.findall(qn("w:tr"))
            if trs:
                header = [ptext(tc) for tc in trs[0].findall(qn("w:tc"))]  # as written, spaces and all
                if any(header):
                    target["tables"].append(header)
        elif tag(el) == "sdt" and not is_toc_sdt(el) and target is not None:
            for p in el.iter(qn("w:p")):
                add_text(p)
    if not chapters:
        raise ExtractError(f"{path}: no chapters found in style '{styles['h1']}'")
    return doc, styles, chapters


def cover_fields(doc, styles: dict[str, str]) -> dict[str, str | None]:
    """Cover text a fill should replace: the text in front-matter text
    boxes and the paragraphs before the first table, page break or table of
    contents. The first is guessed to be the title, version-like text the
    version; the rest are left for the user (None)."""
    texts: list[str] = []
    st = style_table(doc)
    by_name = {s.name: sid for sid, s in st.items()}
    h1 = by_name.get(styles["h1"])

    def add(t: str):
        t = t.strip()
        if t and t not in texts and not re.fullmatch(r"\[[^\]]*\]", t):
            texts.append(t)
    cover_done = False
    for el in doc.element.body.iterchildren():
        if tag(el) == "p" and pstyle_id(el) == h1 and own_text(el).strip():
            break
        for box in el.iter(qn("w:txbxContent")):
            for p in box.iter(qn("w:p")):
                add(ptext(p))
        if cover_done:
            continue
        if tag(el) in ("tbl", "sdt") or el.find(".//" + qn("w:sectPr")) is not None:
            cover_done = True
            continue
        if tag(el) == "p":
            if el.find(".//" + qn("w:txbxContent")) is None:
                add(own_text(el))
            if any(b.get(qn("w:type")) == "page" for b in el.iter(qn("w:br"))):
                cover_done = True
    out: dict[str, str | None] = {}
    title_given = False
    for t in texts:
        m = re.fullmatch(r"(?i)(v(?:ersion)?\s*)?\d+(\.\d+)+", t)
        if m:
            out[t] = f"{m.group(1) or ''}{{doc:version}}"
        elif not title_given:
            out[t] = "{doc:title}"
            title_given = True
        else:
            out[t] = None
    return out


# ----------------------------------------------------------------- matching

def _plain_title(t: str) -> str:
    """A seed title for comparison: a profile placeholder becomes the words
    of its path ("{p:systems.itsm.cmdb_title}" reads "itsm cmdb")."""
    def words(m):
        parts = re.split(r"[._]", m.group(0)[3:-1])
        return " ".join(w for w in parts if w not in ("systems", "name", "title", "short"))
    return " ".join(_P.sub(words, str(t)).split())


def _guidance(texts: list[str], title: str, tables: list[list[str]] | None = None) -> str:
    """The template's own guidance for a section: its paragraphs, or, when
    it gives only a table, that table's columns."""
    out = []
    for t in texts:
        t = re.sub(r"^\[|\]$", "", t.strip()).strip()
        t = re.sub(r"^(guidance|note)\s*:\s*", "", t, flags=re.I)
        if t:
            out.append(t)
    text = " ".join(out)
    if not text and tables:
        text = " ".join("The template's table: " + ", ".join(c.strip() for c in h if c.strip()) + "."
                        for h in tables if any(c.strip() for c in h))
    if len(text) > 700:
        text = text[:700].rsplit(" ", 1)[0] + " ..."
    return text or f"The template gives no guidance for {title}; agree what it should hold."


def _unique(key: str, used: set[str], fallback: str) -> str:
    key = slug(key) or fallback
    if not key[0].isalpha():
        key = f"{fallback}-{key}"
    base, n = key, 2
    while key in used:
        key, n = f"{base}-{n}", n + 1
    used.add(key)
    return key


# Header words that name a field by industry convention rather than by its name.
HEADER_SYNONYMS = {"moscow": "priority", "rag": "status", "raci": "involvement"}
_ID_HEADER = re.compile(r"(^|\s)(id|ref|reference)$")
_STOPWORDS = {"and", "the", "of", "for", "to", "a", "an", "in", "on", "with", "or", "by", "if", "is", "are"}


def _toks(text: str) -> set[str]:
    out = set()
    for w in norm(text).split():
        if w in _STOPWORDS:
            continue
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return out


def _alternatives(header: str) -> list[str]:
    """A header and its slash or parenthesis alternatives: "Business
    Unit/Team" reads as itself, "Business Unit" and "Team"."""
    plain = re.sub(r"[?*:]+", " ", header).strip()
    parts = [p.strip() for p in re.split(r"[/\\()]|\bor\b", plain) if p.strip()]
    return [plain] + (parts if len(parts) > 1 else [])


def _name_score(alt: str, name: str) -> float:
    """How well one reading of a header matches one name of a field: exact
    (1.0) above every containment, containment above a shared distinctive
    word, and that above a near spelling."""
    if not alt or not name:
        return 0.0
    if norm(alt) == norm(name):
        return 1.0
    a, n = _toks(alt), _toks(name)
    if a and n:
        if n <= a:   # every word of the field's name is in the header: "Risk Owner" -> owner
            return 0.7 + 0.25 * len(n) / len(a)
        if a <= n:   # the header is a shorter form of the name: "Step" in "Cutover step"
            return 0.62 + 0.25 * len(a) / len(n)
        shared = {w for w in a & n if len(w) >= 6}
        if shared:   # a distinctive word in common: "Compensating Action" and "Compensating control"
            return 0.6 + 0.2 * len(a & n) / len(a | n)
    v = similarity(alt, name)
    return v * 0.9 if v >= 0.6 else 0.0


def _name_forms(name: str) -> list[str]:
    """A field name or label and its alternatives: "Standard or requirement"
    also reads as "Standard" and "requirement"."""
    parts = [p.strip() for p in re.split(r"/|\bor\b", name) if p.strip()]
    return [name] + (parts if len(parts) > 1 else [])


def column_map_for(header: list[str], types: list[M.ArtefactType],
                   aliases: dict[str, list[str]] | None = None) -> dict[str, str]:
    """Template header -> register field for the fields of ``types``.

    Each header is read with its slash alternatives against each field's
    names: the field name, its label, the type's label for the title, and
    any ``aliases`` the metamodel gives the field. A header ending in ID or
    Ref is the id; a conventional word names its field (MoSCoW is
    priority). Pairs are assigned best first, one field per header and one
    header per field, so "Role" takes the title before "Stakeholder" can.
    The first text column then becomes the title when nothing claimed it
    and it matched no field, or only an enum (a category). Headers
    that match nothing are left out."""
    names: dict[str, list[tuple[str, float]]] = {}
    for t in types:
        for c in ["id", "title", "status"] + list(t.fields):
            lst = names.setdefault(c, [])
            lst += [(f, 1.0) for f in _name_forms(c.replace("_", " ")) + _name_forms(t.header(c))]
            if c == "title":
                lst += [(f, 0.95) for f in _name_forms(t.label)]
    for f, words in (aliases or {}).items():
        if f in names:
            names[f] += [(str(w), 1.0) for w in (words or [])]
    cands = []
    for hi, cell in enumerate(header):
        if not cell or not cell.strip():
            continue
        n = norm(cell)
        if _ID_HEADER.search(n) and "id" in names:
            cands.append((1.0, hi, "id"))
            continue
        if n in HEADER_SYNONYMS and HEADER_SYNONYMS[n] in names:
            cands.append((1.0, hi, HEADER_SYNONYMS[n]))
            continue
        for f, nm in names.items():
            best = max((_name_score(a, x) * w for a in _alternatives(cell) for x, w in nm), default=0.0)
            if best >= 0.6:
                cands.append((best, hi, f))
    cands.sort(key=lambda c: (-c[0], c[1]))
    by_header: dict[int, str] = {}
    for score, hi, f in cands:
        if hi in by_header or f in by_header.values():
            continue
        by_header[hi] = f
    if "title" in names and "title" not in by_header.values():
        # the first text column names the record: it is the title when it is unclaimed, or when it
        # only matched an enum field (a category such as "Readiness Area" is not what a row is called)
        enums = {f for t in types for f, spec in t.fields.items() if spec.kind == "enum"}
        first = next((hi for hi, cell in enumerate(header) if cell and cell.strip() and by_header.get(hi) != "id"),
                     None)
        if first is not None and (first not in by_header or by_header[first] in enums):
            by_header[first] = "title"
    return {header[hi]: f for hi, f in sorted(by_header.items())}


def candidate_type(header: list[str], section_title: str, types: dict[str, M.ArtefactType],
                   aliases: dict[str, dict[str, list[str]]] | None = None
                   ) -> tuple[str | None, dict[str, str], float]:
    """The artefact type a table header reads like: ``(type, column_map,
    score)``, or ``(None, {}, best score)``."""
    best = (None, {}, 0.0)
    for key, t in types.items():
        cmap = column_map_for(header, [t], (aliases or {}).get(key))
        specific = sum(1 for f in cmap.values() if f not in GENERIC_COLUMNS)
        cells = [c for c in header if c]
        if not cells or not specific:
            continue
        frac = len(cmap) / len(cells)
        label = max([similarity(t.label, section_title), similarity(key.replace("-", " "), section_title)]
                    + [similarity(t.label, c) for c in cells])
        score = 0.6 * frac + 0.4 * label
        if score > best[2]:
            best = (key, cmap, score)
    if best[2] < TYPE_THRESHOLD:
        return None, {}, best[2]
    return best


# Sections that instruct the author ("EA Viewpoint / Repository Guidance") rather than hold content.
GUIDE_TITLE = re.compile(r"\b(guidance|instructions?|how to (use|complete))\b", re.I)
VIEWS_TITLE = re.compile(r"\bviews?\b", re.I)


def _match_sections(tsecs: list[dict], ssecs: list[dict]) -> dict[int, int]:
    """Template section index to seed section index. A guidance section
    (one titled as instructions to the author) always goes to the seed
    chapter's views section when it has one, since those instructions say
    which views the chapter must show; the rest align by title and
    position."""
    out: dict[int, int] = {}
    views = next((b for b, s in enumerate(ssecs) if VIEWS_TITLE.search(_plain_title(s["title"]))), None)
    guides = [a for a, t in enumerate(tsecs) if GUIDE_TITLE.search(t["title"])]
    if views is not None and guides:
        out[guides[0]] = views
    rest = [a for a in range(len(tsecs)) if a not in guides]
    seed_rest = [b for b in range(len(ssecs)) if b not in out.values()]
    pairs = match(len(rest), len(seed_rest),
                  lambda i, j: similarity(tsecs[rest[i]]["title"], _plain_title(ssecs[seed_rest[j]]["title"])),
                  SECTION_THRESHOLD)
    for i, j in pairs:
        out[rest[i]] = seed_rest[j]
    return out


def _enum_value_labels(types: dict) -> None:
    """Keep each type's value_labels only for values its fields and status
    still have, so a field made free text leaves no label behind."""
    for td in types.values():
        vl = td.get("value_labels") if isinstance(td, dict) else None
        if not isinstance(vl, dict):
            continue
        values = {str(v).lower() for spec in (td.get("fields") or {}).values() if isinstance(spec, list) for v in spec}
        values |= {str(v).lower() for v in (td.get("status") or {})}
        kept = {k: v for k, v in vl.items() if str(k).lower() in values}
        if kept:
            td["value_labels"] = kept
        else:
            del td["value_labels"]


def _load_target(seed: str) -> M.Metamodel:
    """The metamodel matched against, with value_labels cleaned before it is
    validated, so extract never carries a label for a field that is not an
    enum in the target."""
    path = M.resolve_path(seed)
    if not path.exists():
        raise ExtractError(f"metamodel not found: {seed}")
    data = yaml.safe_load(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("artefact_types"), dict):
        _enum_value_labels(data["artefact_types"])
    try:
        return M.from_dict(data, path)
    except M.MetamodelError as e:
        raise ExtractError(f"the metamodel to match against does not load: {e}") from None


def extract(template: str | Path, seed: str = "seed") -> tuple[dict, dict, list[str]]:
    """``(metamodel, profile fragment, report lines)`` for a template."""
    template = Path(template)
    doc, styles, tchapters = read_template(template)
    base = _load_target(seed)
    raw = base.raw
    seed_chapters = raw["chapters"]
    # optional per-type field aliases: artefact_types.<type>.aliases: {field: [header words]}
    type_aliases = {k: (v or {}).get("aliases") or {} for k, v in (raw.get("artefact_types") or {}).items()}
    report: list[str] = []

    def seed_secs(ch):
        return [_plain_title(s["title"]) for s in ch.get("sections") or []]
    pairs = match(len(tchapters), len(seed_chapters),
                  lambda i, j: chapter_score(tchapters[i]["title"], [s["title"] for s in tchapters[i]["sections"]],
                                             _plain_title(seed_chapters[j]["title"]), seed_secs(seed_chapters[j])),
                  CHAPTER_THRESHOLD)
    cmatch = dict(pairs)
    used_keys = {seed_chapters[j]["key"] for _, j in pairs}
    chapters = []
    run = 1
    for i, tc in enumerate(tchapters):
        j = cmatch.get(i)
        if j is not None:
            sch = seed_chapters[j]
            ch = {k: copy.deepcopy(v) for k, v in sch.items() if k != "sections"}
            ch["title"] = tc["title"]
            run = (ch.get("deck") or {}).get("run", run)
            ssecs = sch.get("sections") or []
            smatch = _match_sections(tc["sections"], ssecs)
            report.append(f"chapter '{tc['title']}' -> {sch['key']} ({_plain_title(sch['title'])})")
        else:
            ch = {"key": _unique(tc["title"], used_keys, "chapter"), "title": tc["title"], "unmatched": True,
                  "question": "", "story": "", "picture": {"kind": "bars", "from": "registers"},
                  "deck": {"run": run}, "viewpoints": []}
            ssecs, smatch = [], {}
            report.append(f"chapter '{tc['title']}' -> {ch['key']} (unmatched)")
        sec_keys: set[str] = set()
        sections = []
        guide = []
        for a, ts in enumerate(tc["sections"]):
            b = smatch.get(a)
            if b is None and GUIDE_TITLE.search(ts["title"]):
                # an instruction to the author with no views section to land in: not content
                guide.append({"title": ts["title"], "guidance": _guidance(ts["guidance"], ts["title"], ts["tables"]),
                              **({"template_columns": ts["tables"]} if ts["tables"] else {})})
                report.append(f"  section '{ts['title']}' is guidance for the author, not content")
                continue
            if b is not None:
                sec = copy.deepcopy(ssecs[b])
                sec["title"] = ts["title"]
                sec_keys.add(sec["key"])
                types = [base.artefact_types[M.parse_selector(str(a))[0]] for a in sec.get("artefacts") or []
                         if M.parse_selector(str(a))[0] in base.artefact_types]
                if types and ts["tables"]:
                    # the template's own headers become the register's labels
                    al: dict[str, list[str]] = {}
                    for tt in types:
                        for f, ws in (type_aliases.get(tt.key) or {}).items():
                            al.setdefault(f, []).extend(ws or [])
                    best = max((column_map_for(h, types, al) for h in ts["tables"]), key=len)
                    if best:
                        sec["column_map"] = best
            else:
                sec = {"key": None, "title": ts["title"], "unmatched": True,
                       "guidance": _guidance(ts["guidance"], ts["title"], ts["tables"]), "artefacts": []}
                for header in ts["tables"]:
                    t, cmap, score = candidate_type(header, ts["title"], base.artefact_types, type_aliases)
                    if t and t not in sec["artefacts"]:
                        sec["artefacts"].append(t)
                        sec.setdefault("column_map", {}).update(cmap)
                report.append(f"  section '{ts['title']}' unmatched"
                              + (f"; register {', '.join(sec['artefacts'])}" if sec["artefacts"] else ""))
            if ts["tables"]:
                sec["template_columns"] = ts["tables"]
            sections.append(sec)
        for sec in sections:
            if sec["key"] is None:
                sec["key"] = _unique(sec["title"], sec_keys, "section")
            sec.setdefault("artefacts", [])
            if not sec.get("guidance"):
                sec["guidance"] = _guidance([], sec["title"])
        ch["sections"] = sections
        if guide:
            ch["template_guidance"] = guide
        if tc["lead"]["tables"]:
            ch["template_columns"] = tc["lead"]["tables"]
        chapters.append(ch)
    all_keys = {c["key"] for c in chapters} | {f"{c['key']}/{s['key']}" for c in chapters for s in c["sections"]}
    kinds = {}
    for k, v in (raw.get("document_kinds") or {}).items():
        v = copy.deepcopy(v or {})
        if v.get("excludes"):
            v["excludes"] = [e for e in v["excludes"] if e in all_keys]
            if not v["excludes"]:
                del v["excludes"]
        kinds[k] = v
    types_out = copy.deepcopy(raw["artefact_types"])
    mm = {
        "name": slug(template.stem) or "extracted",
        "version": 1,
        "extracted_from": template.name,
        "document_kinds": kinds,
        "deck": copy.deepcopy(raw.get("deck") or {}),
        "chapters": chapters,
        "artefact_types": types_out,
        "viewpoints": copy.deepcopy(raw.get("viewpoints") or {}),
    }
    errors = M.validate(mm)
    if errors:
        raise ExtractError("the extracted metamodel does not validate: " + "; ".join(errors))
    full_styles = {k: styles[k] for k in ("h1", "h2", "body", "bullet", "table", "caption", "toc1", "toc2")
                   if k in styles}
    fragment = {"template": {"path": str(template.resolve()), "styles": full_styles,
                             "fields": cover_fields(doc, styles)}}
    return mm, fragment, report


# ---------------------------------------------------------------------- CLI

def dump(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def cli(args) -> int:
    template = Path(args.template)
    if not template.exists():
        print(f"archdoc extract: {template} does not exist", file=sys.stderr)
        return 2
    try:
        mm, fragment, report = extract(template, getattr(args, "seed", None) or "seed")
    except ExtractError as e:
        print(f"archdoc extract: {e}", file=sys.stderr)
        return 2
    out = Path(args.output)
    header = (f"# Metamodel extracted from {template.name} by archdoc extract.\n"
              f"# Chapters and sections marked unmatched: true have no seed counterpart; complete their\n"
              f"# question, story, picture and guidance with the user (references/metamodel.md).\n")
    out.write_text(header + dump(mm))
    M.load_metamodel(str(out.resolve()))  # it must load with the core's loader
    for line in report:
        print(line)
    unmatched = sum(1 for c in mm["chapters"] if c.get("unmatched"))
    print(f"wrote {out}: {len(mm['chapters'])} chapters ({unmatched} unmatched), "
          f"{sum(len(c['sections']) for c in mm['chapters'])} sections")
    unguessed = [k for k, v in fragment["template"]["fields"].items() if v is None]
    frag_text = ("# Profile fragment for filling this template in place: merge it into profile.yaml.\n"
                 + ("# template.fields with a null value were found on the cover; give each a replacement\n"
                    "# (placeholders such as {doc:title} work) or delete it.\n" if unguessed else "")
                 + dump(fragment))
    if getattr(args, "profile_out", None):
        Path(args.profile_out).write_text(frag_text)
        print(f"wrote {args.profile_out}")
    else:
        print()
        sys.stdout.write(frag_text)
    return 0


__all__ = ["ExtractError", "candidate_type", "cli", "cover_fields", "extract", "read_template"]
