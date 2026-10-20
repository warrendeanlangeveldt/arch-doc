"""The checks (SPEC 7): every way a design document drifts from its model.

:func:`run` takes a loaded :class:`~archdoc.project.Project` and returns
:class:`Finding` objects, each with an ``id`` (the check), a ``severity``
(``error`` or ``warn``), a ``message``, a ``source`` (file and line) and the
``anchor`` the place will have in the outputs. ``archdoc check`` prints them
and exits 1 on any error; ``archdoc build`` refuses on errors unless
``--force``.

=================  ========  ==================================================
Id                 Severity  Catches
=================  ========  ==================================================
``count-prose``    error     A count in prose next to a register noun ("seven
                             risks") that disagrees with the register, or a
                             count introducing a table ("at four points:")
                             that disagrees with the table's rows
``count-prose``    warn      The same counted noun phrase for the same subject
                             spelled with two different numbers
``count-model``    error     EA catalogue counts that disagree with registers
``xref``           error     Unresolved placeholders; a literal "section n.n"
                             that does not exist or whose cited title differs;
                             a contents table that skips or misnames a chapter
``xref``           warn      "decisions in section 4.4" when 4.4 is not about
                             decisions and another section is
``version``        error     A literal version that is not this document's
``tbc-owner``      error     A TBC with no owner; TBD or TBA written for TBC
``layer``          error     Product names, SKUs, IPs, CIDRs or resource names
                             in a ``layer: logical`` document
``boundary``       warn      A dependency's internal components described in
                             a solution design, or a consumer's in a capability
``ids``            error     Duplicate ids, ids off their prefix, references
                             to ids no register (or dependency) holds
``ids``            warn      View and exception sequences that cross
``empty``          error     A section with no content; a per-record table that
                             misses records of its parent register
``figure``         error     A missing figure file; a figure never referenced;
                             a views table that says an existing view was not
                             produced
``figure``         warn      A caption count that disagrees with its register;
                             a figure not rendered yet; an unused diagram
``figure-table``   warn      A figure label that contradicts a register or
                             table ("read access TBC" against "read")
``stale-template`` error     Template guidance or placeholder text left in
``voice``          warn      Banned phrases (``data/voice.yaml``)
``consistency``    warn      The same noun phrase approved in one place and
                             not reviewed in another
``schema``,        error     Load problems the core collects (register
``content``                  schema, content format), reported as they are
=================  ========  ==================================================

Heuristics are warnings. Every check is built to stay silent on correct
text: a finding on clean text is a bug in the check.
"""
from __future__ import annotations

import functools
import itertools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml

from . import content as C
from .content import PLACEHOLDER, plain
from .registers import (Record, Source, Tbc, Where, display, owner_problem, parse_conditions, parse_tbc,
                        tbc_markers)

DATA = Path(__file__).resolve().parent / "data"
ERROR, WARN = "error", "warn"

CHECK_IDS = ("count-prose", "count-model", "xref", "version", "tbc-owner", "layer", "boundary", "ids",
             "empty", "figure", "figure-table", "stale-template", "voice", "consistency")
FOLDED_CODES = ("ids", "schema", "tbc-owner", "content", "xref")


# ----------------------------------------------------------------- findings

@dataclass
class Finding:
    """One problem: which check found it, how bad it is, what it is, where it
    is in the sources and the anchor it will have in the outputs."""

    id: str
    severity: str
    message: str
    source: Source | None = None
    anchor: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "severity": self.severity, "message": self.message,
            "source": str(self.source) if self.source else None,
            "file": self.source.file if self.source else None,
            "line": self.source.line if self.source else None,
            "anchor": self.anchor,
        }

    def __str__(self) -> str:
        where = f"{self.source}: " if self.source else ""
        tail = f" (#{self.anchor})" if self.anchor else ""
        return f"{where}{self.severity} [{self.id}] {self.message}{tail}"


# ------------------------------------------------------------------- words

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
WORD_FOR = {v: k for k, v in NUMBER_WORDS.items()}

# A number right after one of these is a label, not a count ("section 7 risks").
LABEL_WORDS = {"section", "sections", "chapter", "chapters", "figure", "figures", "view", "views", "table",
               "step", "phase", "stage", "release", "version", "wave", "sprint", "page", "appendix", "level",
               "tier", "priority", "item", "row", "column", "line", "number", "no", "rule", "option", "case",
               "round", "iteration", "milestone", "day", "week", "month", "year", "q", "h", "p", "v", "sev",
               "severity", "class", "type", "zone", "region", "slide", "part", "annex", "gate", "checkpoint"}
# Before a count, these make it approximate or relative: never compared.
APPROX_WORDS = {"about", "around", "roughly", "nearly", "almost", "approximately", "over", "under", "some",
                "max", "maximum", "minimum", "min", "every", "each", "per", "first", "last", "top", "next",
                "another", "other", "extra", "additional", "further", "only", "just", "than", "least", "most",
                "to", "or", "and", "between", "from", "within", "after", "before", "by", "x", "every"}
APPROX_PAIRS = {("at", "least"), ("up", "to"), ("more", "than"), ("fewer", "than"), ("less", "than"),
                ("no", "more"), ("as", "many"), ("as", "few")}
# Modifiers between a count and its noun that make it relative.
RELATIVE_MODS = {"more", "other", "further", "additional", "extra", "remaining", "new-ish", "fewer", "less",
                 "similar", "such", "different", "separate", "distinct", "same"}
# Modifiers that do not change which records are counted.
NEUTRAL_MODS = {"registered", "recorded", "listed", "named", "documented", "known", "tracked", "identified",
                "logged", "formal", "separate", "distinct", "individual", "key", "main", "major", "principal",
                "defined", "agreed-upon", "in-scope"}
FUNCTION_WORDS = {"the", "a", "an", "of", "for", "to", "in", "on", "at", "by", "with", "from", "and", "or",
                  "but", "that", "which", "who", "whose", "where", "when", "is", "are", "was", "were", "be",
                  "been", "has", "have", "had", "will", "would", "can", "could", "should", "must", "may",
                  "might", "not", "no", "each", "per", "than", "as", "into", "onto", "across", "between",
                  "through", "over", "under", "via", "if", "so", "we", "they", "it", "its", "our", "their",
                  "this", "these", "those", "then", "also", "all", "both", "every", "any", "do", "does", "did",
                  "until", "while", "because", "since", "after", "before", "within", "without", "about",
                  "against", "among", "around", "behind", "below", "above", "beside", "beyond", "during",
                  "except", "inside", "outside", "toward", "towards", "upon", "using"}
DETERMINERS = {"the", "a", "an", "this", "that", "these", "those", "its", "our", "their", "his", "her", "my",
               "your", "each", "every", "all", "any", "some", "only"}
# Verbs that make "<self> <verb> N things" a claim about the whole set.
TOTAL_VERBS = {"has", "have", "holds", "hold", "lists", "list", "records", "record", "names", "name",
               "carries", "carry", "covers", "cover", "contains", "contain", "defines", "define",
               "identifies", "identify", "tracks", "track", "registers", "register", "raises", "raise",
               "includes", "include", "comprises", "comprise", "counts", "count", "spans", "span",
               "totals", "total", "shows", "show", "describes", "describe", "sets", "set", "makes", "make",
               "takes", "take", "logs", "log", "documents", "document"}
SUBJECT_VERBS = TOTAL_VERBS | {
    "uses", "use", "needs", "need", "requires", "require", "stores", "store", "manages", "manage", "keeps",
    "keep", "exposes", "expose", "publishes", "publish", "consumes", "consume", "runs", "run", "owns", "own",
    "reads", "read", "writes", "write", "calls", "call", "serves", "serve", "supports", "support", "handles",
    "handle", "sends", "send", "receives", "receive", "rotates", "rotate", "says", "say", "issues", "issue",
    "provides", "provide", "offers", "offer", "creates", "create", "maintains", "maintain", "operates",
    "operate"}
ADVERBS = {"now", "currently", "still", "already", "also", "today", "together", "altogether", "jointly"}
SELF_WORDS = {"we", "design", "document", "solution", "register", "registers", "project", "sad", "release",
              "this", "chapter", "section"}
PASSIVE_TOTAL = {"recorded", "listed", "registered", "identified", "tracked", "logged", "documented", "named",
                 "defined", "raised", "captured", "known", "in"}
RESTRICTORS = {"for", "that", "which", "with", "in", "on", "where", "whose", "who", "from", "to", "across",
               "per", "under", "between", "using", "via", "at", "by", "of", "into", "against", "carrying",
               "holding", "covering", "needing", "requiring", "owned", "run", "used", "rated", "marked",
               "classed", "classified", "flagged", "still", "remain", "remaining", "outstanding"}
# Nouns whose counts measure time or quantity, not things the document lists.
UNITS = {"second", "minute", "hour", "day", "week", "month", "year", "time", "percent", "ms", "sec", "min",
         "hr", "gb", "mb", "tb", "kb", "pb", "gib", "mib", "tib", "kib", "byte", "bit", "decade", "quarter",
         "fortnight", "night", "shift", "business", "working", "calendar", "x", "fold", "pm", "am", "o'clock",
         "people", "person", "user", "member", "customer", "staff", "fte", "dollar", "cent", "cost", "point-in-time"}
STOP_TOPIC = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "see", "our",
              "its", "their", "this", "that", "these", "those", "are", "is", "detail", "details", "more",
              "information", "approach", "described", "covered", "set", "out", "listed", "shown", "full",
              "further", "as", "which", "where", "how", "what", "we", "record", "recorded", "given", "list",
              "&", "architecture", "design", "management", "s"}


def stem(word: str) -> str:
    """A crude singular: enough to compare "decisions" with "Decision"."""
    w = word.lower().strip("'’")
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "shes", "ches", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def pluralise(word: str) -> str:
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def norm(text: str) -> str:
    """Lowercase words and digits only."""
    return " ".join(re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", plain(text).lower()))


def stems(text: str, stop: set[str] = STOP_TOPIC) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9]+", plain(text).lower()) if w not in stop and stem(w) not in stop}


def number_value(token: str) -> int | None:
    t = token.lower()
    if t in NUMBER_WORDS:
        return NUMBER_WORDS[t]
    if re.fullmatch(r"[1-9]\d{0,3}", t):
        return int(t)
    return None


def spell(n: int) -> str:
    return WORD_FOR.get(n, str(n))


MASK = "¤"


DEP_MASK = "¤dep¤"


def mask(raw: str) -> str:
    """Text as written with every placeholder replaced by a mark, so a
    resolved count or section number is never mistaken for a literal one.
    A ``{dep:}`` placeholder keeps a mark of its own: it says the sentence is
    about a dependency."""
    return PLACEHOLDER.sub(lambda m: DEP_MASK if m.group(1) == "dep" else MASK, raw)


def strip_md(text: str) -> str:
    """Inline Markdown removed, keeping underscores inside words."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?!\w)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)\s]+\)", r"\1", text)
    return text


_ABBREV = {"e.g", "i.e", "etc", "vs", "cf", "no", "approx", "incl", "fig", "sec"}


def sentences(text: str) -> list[tuple[int, str]]:
    """``(offset, sentence)`` pairs. Splits after . ! ? followed by a space
    and a capital, digit or mark, and not after common abbreviations."""
    out, start = [], 0
    for m in re.finditer(r"[.!?](?=\s+[A-Z0-9¤\"“(\[])", text):
        before = re.search(r"([A-Za-z.]+)$", text[start:m.start()])
        if before and before.group(1).lower().rstrip(".") in _ABBREV:
            continue
        out.append((start, text[start:m.end()]))
        start = m.end()
        while start < len(text) and text[start].isspace():
            start += 1
    if start < len(text):
        out.append((start, text[start:]))
    return out


_TOKEN = re.compile(r"[A-Za-z0-9¤](?:[A-Za-z0-9'’¤/_-]|\.(?=[A-Za-z0-9]))*")


@dataclass
class Tok:
    text: str
    low: str
    start: int
    end: int
    gap: str  # text between the previous token and this one


def tokens(sentence: str) -> list[Tok]:
    out, last = [], 0
    for m in _TOKEN.finditer(sentence):
        out.append(Tok(m.group(0), m.group(0).lower(), m.start(), m.end(), sentence[last:m.start()]))
        last = m.end()
    return out


def joined(gap: str) -> bool:
    """Whether two tokens are in the same clause (only spaces between them)."""
    return gap.strip() == ""


# ------------------------------------------------------------------ pieces

@dataclass
class Piece:
    """One run of document text the checks read: a paragraph, a list item, a
    table cell, a caption, a register field or a deck.yaml string."""

    raw: str
    text: str
    source: Source
    anchor: str | None
    kind: str  # para | item | cell | header | caption | heading | record | deck
    chapter: Any = None
    section: Any = None
    block: Any = None
    row: list[str] | None = None
    col: int | None = None
    record: Record | None = None
    field: str | None = None

    @property
    def masked(self) -> str:
        return strip_md(mask(self.raw))


class Doc:
    """What every check needs from a project, computed once."""

    def __init__(self, project):
        self.p = project
        self.deck_unresolved: list[C.Unresolved] = []
        self.deck_problems: list[Finding] = []
        self.record_unresolved: list[tuple] = []
        self.pieces: list[Piece] = list(self._pieces())
        self.row_anchor: dict[str, str] = {}
        for b in project.blocks():
            if isinstance(b, C.RegisterTable):
                for rec, anc in zip(b.records, b.row_anchors):
                    self.row_anchor.setdefault(rec.id, anc)
        for pc in self.pieces:
            if pc.kind == "record" and pc.record is not None:
                pc.anchor = self.row_anchor.get(pc.record.id)
        self.lexicon = self._lexicon()
        self.dep_markers = self._dep_markers()
        self._lines: dict[str, list[str]] = {}

    # -- text pieces
    def _pieces(self) -> Iterator[Piece]:
        p = self.p
        for ch in p.chapters:
            containers = [(None, ch.lead)] + [(s, s.blocks) for s in ch.sections]
            for sec in ch.sections:
                if sec.new and sec.source is not None:
                    yield Piece(sec.title, sec.title, sec.source, sec.anchor, "heading", ch, sec)
            for sec, blocks in containers:
                for b in blocks:
                    yield from self._block_pieces(ch, sec, b)
        for reg in p.registers.values():
            for rec in reg:
                for fname, v in rec.data.items():
                    if fname in ("id", "status"):
                        continue
                    for s in _strings(v):
                        text, unresolved = p.resolve_text(s, rec.source)
                        self.record_unresolved += [(rec, fname, u) for u in unresolved]
                        yield Piece(s, text, rec.source, None, "record", record=rec, field=fname)
        yield from self._deck_pieces()

    def _block_pieces(self, ch, sec, b) -> Iterator[Piece]:
        if isinstance(b, C.Para):
            yield Piece(b.raw, b.text, b.source, b.anchor, "para", ch, sec, b)
        elif isinstance(b, C.Bullets):
            for raw, text, src, anc in zip(b.raw_items, b.items, b.item_sources, b.item_anchors):
                yield Piece(raw, text, src, anc, "item", ch, sec, b)
        elif isinstance(b, (C.RegisterTable, C.Catalogue)):
            return
        elif isinstance(b, C.Table):
            for i, (raw, text) in enumerate(zip(b.raw_header, b.header)):
                yield Piece(raw, text, b.source, b.header_anchor, "header", ch, sec, b, b.header, i)
            for raw_row, row, src, anc in zip(b.raw_rows, b.body, b.row_sources, b.row_anchors):
                for i, (raw, text) in enumerate(zip(raw_row, row)):
                    yield Piece(raw, text, src, anc, "cell", ch, sec, b, row, i)
        elif isinstance(b, C.View):
            yield Piece(b.raw_title, b.title, b.source, b.anchor, "caption", ch, sec, b)
        elif isinstance(b, C.Figure):
            yield Piece(b.raw_caption, b.caption, b.source, b.anchor, "caption", ch, sec, b)

    def _deck_pieces(self) -> Iterator[Piece]:
        path = self.p.root / "deck.yaml"
        if not path.exists():
            return
        text = path.read_text()
        try:
            node = yaml.compose(text)
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            line = mark.line + 1 if mark is not None else None
            why = getattr(e, "problem", None) or str(e).split("\n")[0]
            self.deck_problems.append(Finding("content", ERROR, f"deck.yaml is not valid YAML: {why}; the deck "
                                              f"cannot be built", Source("deck.yaml", line)))
            return
        anchors = {ch.key: ch.anchor for ch in self.p.chapters}

        def walk(n, keys):
            if isinstance(n, yaml.ScalarNode):
                if n.tag.endswith(":str") and n.value.strip():
                    anc = next((anchors[k] for k in keys if k in anchors), None)
                    src = Source("deck.yaml", n.start_mark.line + 1)
                    resolved, unresolved = self.p.resolve_text(n.value, src)
                    self.deck_unresolved.extend(unresolved)
                    yield Piece(n.value, resolved, src, anc, "deck")
            elif isinstance(n, yaml.SequenceNode):
                for c in n.value:
                    yield from walk(c, keys)
            elif isinstance(n, yaml.MappingNode):
                for k, v in n.value:
                    yield from walk(v, keys + [getattr(k, "value", "")])
        if node is not None:
            yield from walk(node, [])

    # -- register nouns
    def _lexicon(self) -> dict[tuple[str, ...], set[str]]:
        """Noun phrases (singular and plural token tuples) to the register
        types they name, from each type's key, label and title label."""
        lex: dict[tuple[str, ...], set[str]] = {}

        def add(phrase: str, t: str):
            words = [w for w in re.findall(r"[a-z0-9]+", phrase.lower())]
            if not words:
                return
            for form in (words, words[:-1] + [pluralise(words[-1])]):
                lex.setdefault(tuple(form), set()).add(t)
        for key, at in self.p.model.artefact_types.items():
            add(key.replace("-", " "), key)
            label = at.label.lower()
            for part in re.split(r"\s+or\s+", label):
                add(part, key)
                if " or " in label:
                    # "deviation or exception": each word is the head noun
                    add(part.split()[-1], key)
            title = at.labels.get("title", "").lower()
            if title and (title == label.split()[-1] or title == key.split("-")[-1]):
                add(title, key)
        return lex

    def _dep_markers(self) -> list[str]:
        out = []
        for d in self.p.config.get("depends_on") or []:
            if isinstance(d, dict):
                if d.get("title"):
                    out.append(d["title"].lower())
                if d.get("ref"):
                    out.append(str(d["ref"]))
        return out

    def mentions_dependency(self, raw_sentence: str) -> bool:
        if "{dep:" in raw_sentence or DEP_MASK in raw_sentence:
            return True
        low = raw_sentence.lower()
        for m in self.dep_markers:
            if m.isupper():
                if re.search(rf"\b{re.escape(m)}\b", raw_sentence):
                    return True
            elif m in low:
                return True
        return False

    # -- lines
    def line_of(self, piece: Piece, needle: str) -> Source:
        """The exact line of ``needle`` inside a multi-line paragraph."""
        src = piece.source
        if piece.kind not in ("para", "item", "record") or not src or not src.line:
            return src
        lines = self._file_lines(src.file)
        if not lines:
            return src
        words = needle.split()
        probe = " ".join(words[:2]).lower() if words else ""
        if not probe:
            return src
        for n in range(src.line, min(len(lines), src.line + 60) + 1):
            if probe in lines[n - 1].lower():
                return Source(src.file, n)
        first = words[0].lower()
        for n in range(src.line, min(len(lines), src.line + 60) + 1):
            if first in lines[n - 1].lower():
                return Source(src.file, n)
        return src

    def _file_lines(self, rel: str) -> list[str]:
        if rel not in self._lines:
            path = self.p.root / rel
            self._lines[rel] = path.read_text().split("\n") if path.exists() else []
        return self._lines[rel]

    # -- register facts
    def selections(self, rtype: str) -> list[tuple[str, int]]:
        """``(where shown, count)`` for every filtered view of a register the
        document uses: section artefacts and REGISTER directives."""
        reg = self.p.registers.get(rtype)
        if reg is None:
            return []
        out = []
        union: set[str] = set()
        for ch in self.p.chapters:
            for s in ch.sections:
                for a in s.artefacts:
                    if a.type == rtype and a.where:
                        out.append((s.number, len(reg.filter(a.where))))
                for b in s.blocks:
                    if isinstance(b, C.RegisterTable) and b.type == rtype:
                        out.append((s.number, len(b.records)))
                        union |= {r.id for r in b.records}
        if union:
            out.append(("the register tables together", len(union)))
        return list(dict.fromkeys(out))

    def counts_for(self, types: set[str]) -> set[int]:
        out: set[int] = set()
        total = 0
        for t in types:
            reg = self.p.registers.get(t)
            if reg is None:
                continue
            out.add(len(reg))
            total += len(reg)
            out |= {n for _, n in self.selections(t)}
        out.add(total)
        return out

    def total(self, types: set[str]) -> int:
        return sum(len(self.p.registers[t]) for t in types if t in self.p.registers)

    def record_terms(self, rtype: str) -> dict[str, Record]:
        """Lower-case id and title of each record of a type, to the record."""
        out: dict[str, Record] = {}
        for rec in self.p.registers.get(rtype, []):
            out[rec.id.lower()] = rec
            if len(rec.title) >= 4:
                out[norm(rec.title)] = rec
        return out


def _strings(v: Any) -> Iterator[str]:
    if isinstance(v, str):
        if v.strip():
            yield v
    elif isinstance(v, Tbc):
        return
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)


# ----------------------------------------------------------------- run

def run(project) -> list[Finding]:
    """Every check on one project, sorted by file and line."""
    doc = Doc(project)
    found: list[Finding] = []
    for check in CHECKS:
        found.extend(check(doc))
    seen: set[tuple] = set()
    out = []
    for f in found:
        key = (f.id, f.severity, f.message, str(f.source))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)

    def order(f: Finding):
        s = f.source
        return (s.file if s else "~", s.line or 0 if s else 0, f.id)
    return sorted(out, key=order)


# ------------------------------------------------------------ folded issues

def check_issues(doc: Doc) -> list[Finding]:
    """The core's load problems: ids, schema, tbc-owner, content and xref."""
    out = []
    by_source: dict[str, str] = {}
    for reg in doc.p.registers.values():
        for rec in reg:
            if rec.id in doc.row_anchor:
                by_source[str(rec.source)] = doc.row_anchor[rec.id]
    for issue in doc.p.issues:
        code = issue.code if issue.code in FOLDED_CODES else "content"
        anchor = issue.anchor or (by_source.get(str(issue.source)) if issue.source else None)
        out.append(Finding(code, ERROR, issue.message, issue.source, anchor))
    for u in doc.deck_unresolved:
        out.append(Finding("xref", ERROR, f"{u.token}: {u.reason}", u.source))
    out += doc.deck_problems
    out += _deck_structure(doc)
    # Placeholders in register values, unless the core already reports them.
    core = {(str(i.source), i.message) for i in doc.p.issues if i.code == "xref"}
    for rec, fname, u in doc.record_unresolved:
        if any(src == str(rec.source) and u.token in msg for src, msg in core):
            continue
        out.append(Finding("xref", ERROR, f"{rec.id}.{fname}: {u.token}: {u.reason}", rec.source,
                           doc.row_anchor.get(rec.id)))
    return out


def _deck_structure(doc: Doc) -> list[Finding]:
    """deck.yaml's structure, judged by the deck builder's own validator, so
    a deck the build would refuse fails the check first and ``build all``
    writes nothing. Parse errors and unresolved placeholders are reported
    above with their exact line, so they are not repeated."""
    if doc.deck_problems or not (doc.p.root / "deck.yaml").exists():
        return []
    try:
        from . import deck_build
    except ImportError:
        return []
    _, issues = deck_build.load_deck_yaml(doc.p)
    try:
        root = yaml.compose((doc.p.root / "deck.yaml").read_text())
    except yaml.YAMLError:
        root = None
    out = []
    for i in issues:
        if i.message.startswith("YAML error") or re.search(r": \{(?:sec|ch|fig|view|count|ids|reg|dep|p|doc|cat):",
                                                          i.message):
            continue
        src = i.source if i.source is not None and i.source.line else Source("deck.yaml", _deck_line(root, i.message))
        out.append(Finding("content", ERROR if i.severity == "error" else WARN, i.message, src))
    return out


def _deck_line(root, message: str) -> int | None:
    """The deck.yaml line a validator message is about: follow the path it
    starts with ('chapters.integration.callouts[1]: ...') through the YAML
    nodes, then the key it names ("unknown key 'x'"), if any."""
    if root is None:
        return None
    node, line = root, root.start_mark.line + 1
    m = re.match(r"^([\w-]+(?:\.[\w-]+|\[\d+\])*)(?::|\s|$)", message)
    steps = re.findall(r"[\w-]+|\[\d+\]", m.group(1)) if m else []
    key = re.search(r"\bkey '([^']+)'", message)
    if key:
        steps.append(key.group(1))
    for step in steps:
        if isinstance(node, yaml.MappingNode):
            hit = next(((k, v) for k, v in node.value if getattr(k, "value", None) == step), None)
            if hit is None:
                break
            line, node = hit[0].start_mark.line + 1, hit[1]
        elif isinstance(node, yaml.SequenceNode) and step.startswith("["):
            idx = int(step[1:-1])
            if idx >= len(node.value):
                break
            node = node.value[idx]
            line = node.start_mark.line + 1
        else:
            break
    return line


# ------------------------------------------------------------- count-prose

@dataclass
class Phrase:
    n: int
    count_text: str
    noun: list[str]          # noun tokens (lowercase)
    mods: list[str]
    types: set[str] | None   # register types the noun names
    prev: list[str]          # words before the count, same clause, lowercase
    after: list[str]         # words after the noun, same clause
    after_gap: str           # punctuation right after the noun
    start: int               # offset of the count in the sentence
    end: int                 # offset of the end of the noun
    approx: bool = False

    @property
    def key(self) -> str:
        return " ".join(self.mods + [stem(self.noun[-1])])


def count_phrases(sentence: str, lexicon: dict[tuple[str, ...], set[str]]) -> list[Phrase]:
    toks = tokens(sentence)
    out = []
    for i, t in enumerate(toks):
        n = number_value(t.text)
        if n is None or t.low == "one":
            continue
        if i + 1 >= len(toks) or not joined(toks[i + 1].gap):
            continue
        prev: list[str] = []
        for j in range(i - 1, -1, -1):
            if not joined(toks[j + 1].gap):
                break
            prev.insert(0, toks[j].low)
        p1 = prev[-1] if prev else ""
        p2 = prev[-2] if len(prev) > 1 else ""
        if p1 in LABEL_WORDS or t.gap.endswith(("#", "§", "-", "/")):
            continue
        approx = p1 in APPROX_WORDS or (p2, p1) in APPROX_PAIRS
        if p1 in ("to", "or", "and", "between") and p2 and number_value(p2) is not None:
            approx = True
        nxt = toks[i + 1]
        if nxt.low in ("to", "or", "and") and i + 2 < len(toks) and number_value(toks[i + 2].text) is not None:
            continue
        if nxt.low in ("of", "times", "percent", "per") or nxt.low in FUNCTION_WORDS:
            continue
        follow: list[Tok] = []
        for j in range(i + 1, min(len(toks), i + 5)):
            if j > i + 1 and not joined(toks[j].gap):
                break
            follow.append(toks[j])
        words = [f.low for f in follow]
        found = None
        for j in range(0, min(3, len(words))):
            if words[j] in FUNCTION_WORDS:
                break
            for L in (3, 2, 1):
                cand = tuple(words[j:j + L])
                if len(cand) == L and cand in lexicon:
                    found = (j, L, lexicon[cand])
                    break
            if found:
                break
        if found:
            j, L, types = found
            mods, noun = words[:j], words[j:j + L]
        else:
            # Without a register noun: the noun is the first plural word
            # ("four integration secrets", "eighteen months online"), or the
            # first word when none of the next three is plural.
            run_ = []
            for w in words[:3]:
                if w in FUNCTION_WORDS or number_value(w) is not None:
                    break
                run_.append(w)
                if len(w) > 2 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
                    break
            else:
                run_ = run_[:1]
            if not run_ or not (run_[-1].endswith("s") or len(run_) == 1):
                continue
            mods, noun, types = run_[:-1], run_[-1:], None
            j, L = len(mods), 1
        last = j + L - 1
        end_tok = follow[last]
        after = []
        after_gap = ""
        k = toks.index(end_tok) + 1
        if k < len(toks):
            after_gap = toks[k].gap
            if joined(toks[k].gap):
                for q in range(k, min(len(toks), k + 4)):
                    if q > k and not joined(toks[q].gap):
                        break
                    after.append(toks[q].low)
        else:
            after_gap = sentence[end_tok.end:]
        out.append(Phrase(n, t.text, noun, mods, types, prev, after, after_gap, t.start, end_tok.end, approx))
    return out


def _mod_filters(doc: Doc, rtype: str, mod: str) -> list[tuple[str, str]]:
    """The (field, value) filters a modifier word can mean for a type."""
    reg = doc.p.registers.get(rtype)
    if reg is None:
        return []
    at = reg.type
    out = []
    for fname, spec in at.fields.items():
        if spec.kind == "enum" and mod in spec.enum:
            out.append((fname, mod))
    if mod in at.status:
        out.append(("status", mod))
    return out


def _filtered_counts(doc: Doc, types: set[str], mods: list[str]) -> set[int] | None:
    """Counts the phrase could mean once its modifiers are read as filters,
    or None when a modifier is not a value of any field."""
    real = [m for m in mods if m not in NEUTRAL_MODS]
    if not real:
        return doc.counts_for(types)
    out: set[int] = set()
    per_type_any = False
    for t in types:
        options = [_mod_filters(doc, t, m) for m in real]
        if not all(options):
            continue
        per_type_any = True
        reg = doc.p.registers[t]
        for combo in itertools.product(*options):
            where = Where(tuple(parse_conditions([f"{f}={v}"]).conditions[0] for f, v in combo))
            out.add(len(reg.filter(where)))
    return out if per_type_any else None


def _is_total(doc: Doc, ph: Phrase, piece_raw: str) -> bool:
    """Whether a counted phrase claims the whole set ("the register has seven
    risks") rather than a part of it ("two integrations are file-based")."""
    after = ph.after
    if after and after[0] in RESTRICTORS:
        allowed = (after[:2] in (["in", "total"], ["in", "scope"], ["in", "all"]) or
                   (len(after) > 1 and after[1] == MASK.lower()) or
                   (after[0] == "in" and len(after) > 1 and (after[1] in (MASK, "this") or
                                                            after[1:3] == ["the", "register"])))
        if not allowed:
            return False
    prev = ph.prev
    p1 = prev[-1] if prev else ""
    if prev[-2:] in (["there", "are"], ["there", "were"], ["total", "of"], ["in", "all"]) or p1 == "all":
        return True
    if after[:2] in (["in", "total"], ["in", "all"]):
        return True
    if p1 in ("the", "these", "those", "its", "our", "their"):
        if ph.types and _mentions_records(doc, piece_raw, ph.types):
            return False
        if p1 == "the" and len(prev) >= 2 and prev[-2] in SUBJECT_VERBS - TOTAL_VERBS:
            return False
        return True
    verb_at = None
    if p1 in TOTAL_VERBS:
        verb_at = len(prev) - 1
    elif p1 in ADVERBS and len(prev) >= 2 and prev[-2] in TOTAL_VERBS:
        verb_at = len(prev) - 2
    if verb_at is not None:
        subject = [w for w in prev[max(0, verb_at - 4):verb_at] if w not in DETERMINERS]
        own = {w.lower() for w in re.findall(r"[a-z0-9]+", doc.p.title.lower())} | {doc.p.short.lower()}
        if doc.p.kind == "capability":
            own |= {"platform", "capability"}
        if subject and (set(subject) & SELF_WORDS or " ".join(subject) in (doc.p.title.lower(), doc.p.short.lower())
                        or (len(subject) == 1 and subject[0] in own)):
            return True
        return False
    if after and after[0] in ("are", "is", "were") and len(after) > 1 and after[1] in PASSIVE_TOTAL:
        return True
    if ph.after_gap.strip().startswith(":") and ph.types is None:
        return True
    return False


def _mentions_records(doc: Doc, raw: str, types: set[str]) -> bool:
    low = raw.lower()
    for t in types:
        for rec in doc.p.registers.get(t, []):
            if re.search(rf"\b{re.escape(rec.id.lower())}\b", low):
                return True
            if len(rec.title) > 5 and rec.title.lower() in low:
                return True
    return "{reg:" in raw or "{ids:" in raw


def _subject(ph: Phrase, piece: Piece) -> str | None:
    """Who or what the count is about, for comparing two counts of the same
    thing: the words before a verb, or the row's first cell in a table."""
    prev = ph.prev
    for k in range(len(prev) - 1, max(-1, len(prev) - 3), -1):
        if prev[k] in SUBJECT_VERBS:
            subj = [w for w in prev[max(0, k - 4):k] if w not in DETERMINERS and w not in ADVERBS]
            return " ".join(stem(w) for w in subj) or None
    if piece.kind == "record" and piece.record is not None:
        return " ".join(stem(w) for w in norm(piece.record.title).split() if w not in DETERMINERS) or None
    if piece.kind == "cell" and piece.col and piece.row:
        return " ".join(stem(w) for w in norm(piece.row[0]).split() if w not in DETERMINERS) or None
    if prev[-2:] in (["there", "are"], ["in", "all"]) or (prev and prev[-1] == "all") or \
            ph.after[:2] in (["in", "total"],):
        return "*"
    return None


def _adjacent_table(piece: Piece) -> tuple[C.Table | None, C.Table | None]:
    """The tables immediately after and before a paragraph in its section."""
    if piece.kind != "para" or piece.block is None:
        return None, None
    blocks = piece.section.blocks if piece.section is not None else piece.chapter.lead
    try:
        i = next(k for k, b in enumerate(blocks) if b is piece.block)
    except StopIteration:
        return None, None
    nxt = blocks[i + 1] if i + 1 < len(blocks) and isinstance(blocks[i + 1], C.Table) else None
    prv = blocks[i - 1] if i > 0 and isinstance(blocks[i - 1], C.Table) else None
    return nxt, prv


def _data_rows(t: C.Table) -> int:
    rows = t.rows
    return sum(1 for r in rows if not (r and norm(r[0]) in ("total", "totals", "all")))


def _header_stems(t: C.Table) -> set[str]:
    return {stem(w) for h in t.header for w in re.findall(r"[a-z0-9]+", plain(h).lower())}


def check_count_prose(doc: Doc) -> list[Finding]:
    out = []
    groups: dict[tuple[str, str], list[tuple[Phrase, Piece, Source]]] = {}
    for pc in doc.pieces:
        if pc.kind not in ("para", "item", "cell", "caption", "record", "deck"):
            continue
        text = pc.masked
        nxt, prv = _adjacent_table(pc)
        compare = pc.kind != "record"  # a record's own text only joins the same-subject comparison
        sents = sentences(text)
        for si, (off, sent) in enumerate(sents):
            dep = doc.mentions_dependency(sent)
            for ph in count_phrases(sent, doc.lexicon):
                if ph.approx or set(ph.mods) & RELATIVE_MODS:
                    continue
                span = sent[ph.start:ph.end]
                src = doc.line_of(pc, span)
                cid, sev = ("figure", WARN) if pc.kind == "caption" else ("count-prose", ERROR)
                noun_text = " ".join(ph.mods + ph.noun)
                if not compare:
                    pass
                elif ph.types:
                    if not dep:
                        f = _register_count(doc, ph, pc, span, src, cid, sev)
                        if f:
                            out.append(f)
                    table = _table_for(ph, sent, si == len(sents) - 1, nxt, prv)
                    if table is not None and not isinstance(table, C.RegisterTable) and not dep \
                            and not (set(ph.mods) - NEUTRAL_MODS):
                        rows = _data_rows(table)
                        if ph.n != rows and ph.n not in doc.counts_for(ph.types):
                            out.append(Finding(cid, sev, f"'{span}' introduces a table of {rows} rows",
                                               src, pc.anchor))
                elif stem(ph.noun[-1]) not in UNITS and not dep:
                    table = _table_for(ph, sent, si == len(sents) - 1, nxt, prv)
                    if table is not None and not (set(ph.mods) - NEUTRAL_MODS):
                        rows = _data_rows(table)
                        if ph.n != rows:
                            where = "below" if table is nxt else "above"
                            out.append(Finding(cid, sev, f"'{span}' introduces the table {where}, which has "
                                               f"{rows} {'row' if rows == 1 else 'rows'}; write {spell(rows)} "
                                               f"{noun_text.rsplit(' ', 1)[0] + ' ' if ' ' in noun_text else ''}"
                                               f"{ph.noun[-1]}", src, pc.anchor))
                if stem(ph.noun[-1]) in UNITS or dep:
                    continue
                subj = _subject(ph, pc)
                if subj is None:
                    continue
                if subj == "*" and not _is_total(doc, ph, pc.raw):
                    continue
                groups.setdefault((subj, ph.key), []).append((ph, pc, src))
    for (subj, key), occ in groups.items():
        values = {ph.n for ph, _, _ in occ}
        if len(values) < 2:
            continue
        first_ph, first_pc, first_src = occ[0]
        for ph, pc, src in occ[1:]:
            if ph.n == first_ph.n or pc is first_pc or (pc.kind == "cell" and pc.anchor == first_pc.anchor):
                continue  # two counts in one place (or one table row) are alternatives, not a disagreement
            what = f" for {subj}" if subj != "*" else ""
            out.append(Finding("count-prose", WARN,
                               f"says {ph.count_text} {' '.join(ph.mods + ph.noun)}{what}, but {first_src} says "
                               f"{first_ph.count_text}: one of them is out of date", src, pc.anchor))
    return out


def _table_for(ph: Phrase, sent: str, last_sentence: bool, nxt, prv):
    """The table a counted phrase introduces: the table right after the
    paragraph when the count ends the sentence before a colon, or names the
    table's header noun; the table before it when the phrase says 'above'."""
    noun_stem = stem(ph.noun[-1])
    if nxt is not None:
        tail = sent[ph.end:].strip()
        if last_sentence and tail.endswith(":") and len(tokens(tail)) <= 3:
            return nxt
        if noun_stem in _header_stems(nxt) and last_sentence:
            return nxt
        if ph.after[:1] == ["below"]:
            return nxt
    if prv is not None and ph.after[:1] == ["above"]:
        return prv
    return None


def _register_count(doc: Doc, ph: Phrase, pc: Piece, span: str, src: Source, cid: str, sev: str):
    types = ph.types or set()
    total = doc.total(types)
    names = " and ".join(sorted(types))
    filtered = _filtered_counts(doc, types, ph.mods)
    if filtered is not None and _is_total(doc, ph, pc.raw):
        if ph.n not in filtered:
            shown = sorted(filtered)
            detail = f"the {names} register has {total}"
            sel = [f"{n} in {w}" for t in types for w, n in doc.selections(t)]
            if set(ph.mods) - NEUTRAL_MODS:
                detail = f"the {names} register has {', '.join(map(str, shown))} matching '{' '.join(ph.mods)}'"
            elif sel:
                detail += f" ({', '.join(sel)})"
            return Finding(cid, sev, f"'{span}': {detail}; cite {{count:{sorted(types)[0]}}} instead of a literal "
                           f"number", src, pc.anchor)
        return None
    if ph.n > total:
        if total == 0:
            return Finding(cid, WARN, f"'{span}': the {names} register has no records", src, pc.anchor)
        return Finding(cid, sev, f"'{span}': the {names} register has only {total}", src, pc.anchor)
    return None


# ------------------------------------------------------------- count-model

EA_ALIASES = {
    "application component": {"application", "component"},
    "requirement": {"business-requirement", "functional-requirement", "nfr"},
    "business requirement": {"business-requirement"},
    "functional requirement": {"functional-requirement"},
    "non functional requirement": {"nfr"},
    "data object": {"data-object"},
    "business object": {"data-object"},
    "information": {"data-object"},
    "decision": {"decision"},
    "architecture decision": {"decision"},
}


def _ea_types(doc: Doc, name: str) -> set[str]:
    n = " ".join(re.findall(r"[a-z0-9]+", name.lower().replace("-", " ")))
    if n in EA_ALIASES:
        return {t for t in EA_ALIASES[n] if t in doc.p.registers}
    words = tuple(n.split())
    if words in doc.lexicon:
        return set(doc.lexicon[words])
    return set()


def _model_ref_types(doc: Doc, model_path: Path) -> dict[str, set[str]]:
    """EA object type to the registers its objects' ``ref`` ids point at, by
    majority. One EA type may stand for several registers (ArchiMate's
    Application Component holds applications and components): each register
    with at least a quarter of the votes is kept, and the kept registers
    must account for more than half of the type's objects. A ref that names
    no record of this project (a dependency's record, a typo) has no vote,
    so one stray ref cannot map 28 Technology objects to decisions."""
    try:
        data = json.loads(model_path.read_text())
    except (OSError, ValueError):
        return {}
    totals: dict[str, int] = {}
    votes: dict[str, dict[str, int]] = {}
    for o in data.get("objects", []):
        otype = str(o.get("type", ""))
        totals[otype] = totals.get(otype, 0) + 1
        ref = o.get("ref")
        if not isinstance(ref, str):
            continue
        rec = doc.p.record(ref)
        if rec is None:
            continue
        votes.setdefault(otype, {})
        votes[otype][rec.type.key] = votes[otype].get(rec.type.key, 0) + 1
    out: dict[str, set[str]] = {}
    for otype, v in votes.items():
        cast = sum(v.values())
        kept = {t for t, n in v.items() if n * 4 >= cast}
        if sum(v[t] for t in kept) * 2 > totals[otype]:
            out[otype] = kept
    return out


def check_count_model(doc: Doc) -> list[Finding]:
    out = []
    for ch in doc.p.chapters:
        for sec in [None] + list(ch.sections):
            blocks = ch.lead if sec is None else sec.blocks
            for b in blocks:
                if isinstance(b, C.Catalogue):
                    refs = _model_ref_types(doc, doc.p.root / b.model_path) if b.found else {}
                    rows = [(r[0], r[1]) for r in b.body]
                    out += _catalogue_rows(doc, rows, refs, b, b.row_anchors, [b.source] * len(rows), "catalogue")
                elif type(b) is C.Table and _is_count_table(b):
                    ci = _count_col(b)
                    rows = [(r[0], r[ci]) for r in b.body]
                    out += _catalogue_rows(doc, rows, {}, b, b.row_anchors, b.row_sources, "table")
    return out


def _is_count_table(t: C.Table) -> bool:
    if len(t.header) < 2 or not t.body:
        return False
    first = norm(t.header[0])
    if not re.search(r"\b(object|element|type|artefact|artifact|concept)\b", first):
        return False
    return _count_col(t) is not None


def _count_col(t: C.Table) -> int | None:
    for i, h in enumerate(t.header[1:], start=1):
        if re.search(r"\b(count|objects|number|records|total|elements|instances)\b|^#$|^n$", norm(h) or h.strip()):
            if all(re.fullmatch(r"\d+", plain(r[i]).strip() or "x") for r in t.body if len(r) > i):
                return i
    return None


def _catalogue_rows(doc, rows, refs, block, anchors, sources, what) -> list[Finding]:
    out = []
    for (name, count), anc, src in zip(rows, anchors, sources):
        try:
            n = int(plain(count).strip())
        except ValueError:
            continue
        types = refs.get(name) or _ea_types(doc, name)
        if not types or doc.total(types) == 0:
            continue  # an empty register is not a count; the model may run ahead of it
        cands = doc.counts_for(types)
        if n in cands:
            continue
        total = doc.total(types)
        sel = [f"{c} in {w}" for t in sorted(types) for w, c in doc.selections(t)]
        regs = " and ".join(sorted(types))
        out.append(Finding("count-model", ERROR,
                           f"the EA {what} counts {n} {plain(name)} objects; the {regs} register has {total}"
                           + (f" ({', '.join(sel)})" if sel else "") + ": the model and the registers disagree",
                           src, anc))
    return out


# -------------------------------------------------------------------- xref

_SEC_REF = re.compile(r"\b(?P<word>[Ss]ections?|[Cc]hapters?|§)\s*(?P<num>\d+(?:\.\d+)*)(?![\d.]*\d)")
_FIG_REF = re.compile(r"\b(?P<word>Figure|View)\s+(?P<num>\d+)\b")
_TITLE_AFTER = re.compile(r"^\s*(?::|\(|,|–|—| - )\s*[\"“‘']?(?P<title>[^.;:()\"”’\n]{2,80}?)[\"”’']?\s*(?:\)|[.;:,]|$)")


def _title_match(cited: str, actual: str) -> bool:
    c = [stem(w) for w in re.findall(r"[a-z0-9]+", plain(cited).lower()) if w not in STOP_TOPIC]
    a = stems(actual)
    if not c:
        return True
    if c[0] in a:
        return True
    inter = len(set(c) & a)
    return inter / max(1, len(set(c) | a)) >= 0.5


def _node_label(node) -> str:
    return f"{'chapter' if not hasattr(node, 'chapter') else 'section'} {node.number} {node.title}"


def _sections_matching(doc: Doc, words: set[str], exclude=None) -> list:
    out = []
    for ch in doc.p.chapters:
        for node in [ch] + list(ch.sections):
            if node is exclude:
                continue
            if words and words <= stems(node.title):
                out.append(node)
    return out


def check_xref(doc: Doc) -> list[Finding]:
    out = []
    n_figs, n_views = len(doc.p.figures), len(doc.p.views)
    for pc in doc.pieces:
        if pc.kind not in ("para", "item", "cell", "caption", "deck", "record"):
            continue
        text = pc.masked
        for off, sent in sentences(text):
            if doc.mentions_dependency(sent):
                continue
            for m in _SEC_REF.finditer(sent):
                after = sent[m.end():]
                if re.match(r"\s+(?:of|in)\s+(?:the\s+)?(?!this\b)[A-Z{¤]", after) or \
                        re.match(r"\s+of\s+(?:the\s+)?[A-Za-z]+\s+(?:standard|policy|act|framework|design|"
                                 r"document|guide|specification|contract|agreement)", after):
                    continue
                num = m.group("num")
                node = doc.p.by_number(num)
                src = doc.line_of(pc, m.group(0))
                if node is None:
                    out.append(Finding("xref", ERROR, f"'{m.group(0)}': this document has no "
                                       f"{'chapter' if '.' not in num else 'section'} {num}", src, pc.anchor))
                    continue
                tm = _TITLE_AFTER.match(after)
                if tm:
                    cited = tm.group("title").strip()
                    if cited and not cited[0].isdigit() and not _title_match(cited, node.title):
                        first = [stem(w) for w in re.findall(r"[a-z0-9]+", cited.lower()) if w not in STOP_TOPIC][:1]
                        better = _sections_matching(doc, set(first), node)
                        hint = f"; '{cited}' is {_node_label(better[0])}" if len(better) == 1 else ""
                        out.append(Finding("xref", ERROR, f"'{m.group(0)}' is cited as '{cited}', but {num} is "
                                           f"'{node.title}'{hint}", src, pc.anchor))
                        continue
                f = _topic_mismatch(doc, sent[:m.start()], node, m.group(0), src, pc)
                if f:
                    out.append(f)
            for m in _FIG_REF.finditer(sent):
                n = int(m.group("num"))
                limit = n_figs if m.group("word") == "Figure" else n_views
                if n > limit:
                    out.append(Finding("xref", ERROR, f"'{m.group(0)}': the document has "
                                       f"{limit} {m.group('word').lower()}{'s' if limit != 1 else ''}",
                                       doc.line_of(pc, m.group(0)), pc.anchor))
        # {sec:} placeholders pointing at a section about something else
        for m in re.finditer(r"\{sec:([^{}]+)\}", pc.raw):
            ck, _, sk = m.group(1).strip().partition("/")
            node = doc.p.section(ck, sk) if sk else doc.p.chapter(ck)
            if node is None:
                continue
            before = strip_md(mask(pc.raw[:m.start()]))
            f = _topic_mismatch(doc, before, node, m.group(0), doc.line_of(pc, "{sec:"), pc)
            if f:
                out.append(f)
    out += _toc_tables(doc)
    return out


def _topic_mismatch(doc: Doc, before: str, node, cited: str, src: Source, pc: Piece):
    """'design decisions in section 4.4' when 4.4 is Views and 4.5 is
    Design Decisions (warn). The topic is the noun phrase right before the
    preposition; every content word of it must be in the other section's
    title and none in the cited one's."""
    m = re.search(r"((?:[A-Za-z][\w-]*\s+){0,3}[A-Za-z][\w-]*)\s+(?:are\s+|is\s+)?(?:in|at|under|see|per|from|"
                  r"within)\s*(?:the\s+)?$", before)
    if not m:
        return None
    words = re.findall(r"[a-z0-9][a-z0-9-]*", m.group(1).lower())
    while words and words[-1] in ("are", "is", "was", "were", "sit", "sits", "live", "lives"):
        words.pop()
    phrase: list[str] = []
    for w in reversed(words):
        if w in FUNCTION_WORDS or w in DETERMINERS or w in SUBJECT_VERBS:
            break
        phrase.insert(0, w)
    if not phrase or re.search(r"(ed|ing)$", phrase[-1]) or number_value(phrase[-1]) is not None:
        return None  # "is recorded in", "running in": a verb, not a topic
    topic = [stem(w) for w in phrase if w not in STOP_TOPIC]
    if not topic:
        return None
    target = stems(node.title)
    sec_types: set[str] = set()
    for a in getattr(node, "artefacts", []) or []:
        sec_types.add(a.type)
    # A Section holds a list of blocks; a Chapter's blocks() is a method that
    # yields its lead-in's and every section's blocks.
    blocks = getattr(node, "blocks", None)
    for b in (blocks() if callable(blocks) else blocks) or []:
        if isinstance(b, C.RegisterTable):
            sec_types.add(b.type)
    head = topic[-1]
    noun_types = doc.lexicon.get((head,), set()) | doc.lexicon.get((pluralise(head),), set())
    if set(topic) & target or (noun_types & sec_types):
        return None
    # "Alerts, their thresholds and runbooks are in ...": one member of a
    # list that matches the cited section clears the whole list.
    clause = re.split(r"[;:.!?]", before)[-1]
    if re.search(r"\b(?:and|or)\b|,", clause):
        for member in re.split(r",|\band\b|\bor\b", clause):
            for w in re.findall(r"[a-z0-9]+", member.lower()):
                if w in FUNCTION_WORDS or w in STOP_TOPIC:
                    continue
                st = stem(w)
                types = doc.lexicon.get((st,), set()) | doc.lexicon.get((w,), set())
                if st in target or (types & sec_types):
                    return None
    if hasattr(node, "sections") and any(set(topic) & stems(s.title) for s in node.sections):
        return None
    better = [b for b in _sections_matching(doc, set(topic), node)]
    if not better:
        return None
    better = [b for b in better if hasattr(b, "chapter")] or better
    names = " or ".join(_node_label(b) for b in better[:3])
    return Finding("xref", WARN, f"'{' '.join(phrase)} … {cited}' points at {_node_label(node)}; "
                   f"'{' '.join(phrase)}' looks like {names}", src, pc.anchor)


def _toc_tables(doc: Doc) -> list[Finding]:
    """A hand-written table of contents: a table or list whose entries are
    numbers and titles. It must not skip a chapter or misname one."""
    out = []
    numbering = {n: t for n, t, _ in doc.p.numbering()}
    chapters = {str(ch.number): ch.title for ch in doc.p.chapters}
    for b in doc.p.blocks():
        entries: list[tuple[str, str, Source, str | None]] = []
        toc_header = False
        if type(b) is C.Table:
            cols = set()
            for row, raw_row, src, anc in zip(b.body, b.raw_rows, b.row_sources, b.row_anchors):
                cells = [plain(c).strip() for c in row]
                # Only a number written by hand: a {sec:} number is always right.
                nums = [i for i, c in enumerate(cells)
                        if re.fullmatch(r"\d+(?:\.\d+)*", c) and i < len(raw_row) and "{" not in raw_row[i]]
                if len(nums) == 1 and len(cells) > nums[0] + 1:
                    entries.append((cells[nums[0]], cells[nums[0] + 1], src, anc))
                    cols.add(nums[0])
            if len(cols) == 1:
                i = cols.pop()
                hn = norm(b.header[i]) if i < len(b.header) else ""
                ht = norm(b.header[i + 1]) if i + 1 < len(b.header) else ""
                toc_header = bool(re.search(r"\b(chapter|section|no)\b|^#?$", hn) and
                                  re.search(r"\b(title|name|heading|chapter|section|contents)\b", ht))
        elif isinstance(b, C.Bullets):
            for item, src, anc in zip(b.items, b.item_sources, b.item_anchors):
                m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", plain(item).strip())
                if m:
                    entries.append((m.group(1), m.group(2), src, anc))
        if len(entries) < 3:
            continue
        matches = sum(1 for n, t, _, _ in entries if any(_title_match(t, title) and stems(t) & stems(title)
                                                          for title in numbering.values()))
        if matches * 2 < len(entries) and not toc_header:
            continue
        prev_ch = None
        for n, t, src, anc in entries:
            actual = numbering.get(n)
            if actual is None:
                out.append(Finding("xref", ERROR, f"the contents list '{n} {t}': this document has no {n}",
                                   src, anc))
            elif not _title_match(t, actual):
                out.append(Finding("xref", ERROR, f"the contents list '{n} {t}', but {n} is '{actual}'", src, anc))
            if "." not in n:
                k = int(n)
                if prev_ch is not None and k > prev_ch + 1:
                    missing = [str(i) for i in range(prev_ch + 1, k) if str(i) in chapters]
                    if missing:
                        out.append(Finding("xref", ERROR, "the contents list skips chapter "
                                           + ", ".join(f"{i} {chapters[i]}" for i in missing), src, anc))
                prev_ch = k
    return out


# ----------------------------------------------------------------- version

_VERSION = re.compile(r"(?<![\w.])(?:[vV](?=\d)|[Vv]ersion\s+)(?P<v>\d+(?:\.\d+){1,2})(?![\w.]*\d)")
_SELF_DOC = re.compile(r"\b(?:this|the|our)\s+(?:document|design|draft|paper|sad|version)\b|\bdocument\b|\bdraft\b|"
                       r"\bsubmitted\b|\bissued\b|\bfor review\b|\bbaseline\b|\bsign-?off\b", re.I)
_DOC_WORDS = {"this", "the", "document", "design", "draft", "version", "our", "sad", "paper"}


def check_version(doc: Doc) -> list[Finding]:
    """A literal version of this document that is not its version. Only a
    sentence about the document itself is read ("This document (v0.1) is
    not yet submitted"); another thing's version ("TLS v1.2", "upgrade to
    v2.0 of the carrier API"), history tables and dependency references are
    left alone."""
    out = []
    mine = str(doc.p.version)
    own = {doc.p.short.lower(), doc.p.title.lower()}
    for pc in doc.pieces:
        if pc.kind not in ("para", "item", "cell", "caption", "deck", "heading", "record"):
            continue
        if pc.kind == "cell" and pc.block is not None and _is_history(pc):
            continue
        if pc.section is not None and re.search(r"\b(history|change log|changelog|revision)", pc.section.title.lower()):
            continue
        for off, sent in sentences(pc.masked):
            if doc.mentions_dependency(sent):
                continue
            about_us = bool(_SELF_DOC.search(sent)) or any(o in sent.lower() for o in own)
            for m in _VERSION.finditer(sent):
                v = m.group("v")
                if v == mine:
                    continue
                before = sent[:m.start()].rstrip(" (")
                pw = re.search(r"([A-Za-z0-9/+'’-]+)$", before)
                prev = pw.group(1) if pw else ""
                named_us = prev.lower() in own or prev.lower() in _DOC_WORDS
                if prev and not named_us and (prev[0].isupper() or re.search(r"[A-Z]{2}", prev)):
                    continue  # "TLS v1.2", "OpenAPI version 3.1": another thing's version
                if not (about_us or named_us):
                    continue
                out.append(Finding("version", ERROR, f"'{m.group(0)}' but this document is version {mine}; "
                                   f"write {{doc:version}}", doc.line_of(pc, m.group(0)), pc.anchor))
    return out


def _is_history(pc: Piece) -> bool:
    return any(re.search(r"\b(version|revision|history)\b", plain(h).lower()) for h in pc.block.header)


# --------------------------------------------------------------- tbc-owner

def check_tbc_owner(doc: Doc) -> list[Finding]:
    out = []
    core = {(str(i.source), i.message) for i in doc.p.issues if i.code == "tbc-owner"}

    def slot(owner: str | None, what: str, src, anchor):
        why = owner_problem(owner or "")  # the core's one owner rule
        if why:
            out.append(Finding("tbc-owner", WARN, f"TBC: {owner}{what} names {why}, not who confirms it; write "
                               f"'TBC: <role or team>' and put the timing in the text", src, anchor))

    # Register TBCs with no owner come from the core's issues (check_issues);
    # prose TBCs are read here piece by piece, with the same rule as
    # Project.tbcs(), so each finding has its own line and cell anchor.
    for pc in doc.pieces:
        if pc.kind in ("para", "item", "cell", "header", "caption", "deck"):
            # The core's one TBC rule: "Every TBC has an owner" names TBCs,
            # it does not mark an open value.
            text = pc.raw
            for start, end, t in tbc_markers(text):
                owner = t.owner
                src = doc.line_of(pc, _line_probe(text, start))
                if owner:
                    slot(owner, "", src, pc.anchor)
                    continue
                snippet = strip_md(mask(text[max(0, start - 50):end + 10])).strip()
                where = " in deck.yaml" if pc.kind == "deck" else ""
                out.append(Finding("tbc-owner", ERROR, f"TBC with no owner{where}: '…{snippet}'; write "
                                   f"'TBC: <owner>'", src, pc.anchor))
        elif pc.kind == "record" and pc.record is not None and parse_tbc(pc.raw) is None:
            # A TBC inside a longer value ("Monthly; TBC"). A bare one falls
            # to the record's owner, as a whole-value TBC does.
            rec = pc.record
            text = pc.raw
            for start, end, t in tbc_markers(text):
                owner = t.owner
                src = doc.line_of(pc, _line_probe(text, start))
                if owner:
                    slot(owner, f" in {rec.id}.{pc.field}", src, pc.anchor)
                    continue
                if rec.accountable:
                    continue
                if any(c_src == str(rec.source) and f"{rec.id}.{pc.field}" in msg for c_src, msg in core):
                    continue
                out.append(Finding("tbc-owner", ERROR, f"{rec.id}.{pc.field} has a TBC with no owner, and the "
                                   f"record has none to fall back on; write 'TBC: <owner>'", src, pc.anchor))
        for m in re.finditer(r"\b(TBD|TBA)\b", mask(pc.raw)):
            out.append(Finding("tbc-owner", ERROR, f"'{m.group(1)}' is not a value: write 'TBC: <owner>'",
                               doc.line_of(pc, m.group(1)), pc.anchor))
    for reg in doc.p.registers.values():
        for rec in reg:
            for fname, t in rec.tbcs():
                if t.owner and not t.inherited:
                    slot(t.owner, f" in {rec.id}.{fname}", rec.source, doc.row_anchor.get(rec.id))
    # arch-doc.yaml: a bare TBC falls to the document owner, as a record's
    # falls to its owner.
    owner = doc.p.config.get("owner") or {}
    owner_name = owner.get("name") if isinstance(owner, dict) else owner
    for path, v in _walk_config(doc.p.config):
        t = parse_tbc(v)
        if t is None:
            continue
        if t.owner:
            slot(t.owner, f" in arch-doc.yaml {path}", Source("arch-doc.yaml"), "dc")
        elif not owner_name or parse_tbc(owner_name) is not None:
            out.append(Finding("tbc-owner", ERROR, f"arch-doc.yaml {path} is TBC and the document has no "
                               f"owner to confirm it", Source("arch-doc.yaml"), "dc"))
    return out


def _line_probe(text: str, at: int) -> str:
    """Two words that end at ``at``, to find the line of a match inside a
    paragraph joined from several lines."""
    words = re.findall(r"\S+", text[:at + 3])
    return " ".join(words[-2:]) if words else text[at:at + 3]


def _walk_config(v, path=""):
    if isinstance(v, dict):
        for k, x in v.items():
            if k in ("history", "depends_on"):
                continue
            yield from _walk_config(x, f"{path}.{k}" if path else str(k))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _walk_config(x, f"{path}[{i}]")
    else:
        yield path, v


# ------------------------------------------------------------------- layer

@functools.lru_cache(maxsize=1)
def _products() -> tuple[tuple[str, ...], dict[str, str]]:
    data = yaml.safe_load((DATA / "products.yaml").read_text())
    names: list[str] = []
    for k, v in data.items():
        if k != "patterns":
            names += [str(x) for x in v or []]
    return tuple(names), dict(data.get("patterns") or {})


def _banned_terms(doc: Doc) -> list[tuple[str, str]]:
    """``(term, why)`` pairs: the cloud products, each profile system with a
    ``logical_name`` (unless it has ``keep_name: true``: the design consumes
    that system rather than designing it), and ``banned_terms``."""
    names, _ = _products()
    out = [(str(t), "a banned term of this document") for t in doc.p.config.get("banned_terms") or []]
    systems = doc.p.profile.get("systems") or {}
    for key, s in systems.items():
        if isinstance(s, dict) and s.get("logical_name") and s.get("name") and not s.get("keep_name"):
            out.append((str(s["name"]), f"the profile's {key} system; write '{s['logical_name']}'"))
    out += [(n, "a cloud product") for n in names]
    return out


def _allowed_terms(doc: Doc) -> list[str]:
    """Names a logical design deliberately keeps: arch-doc.yaml
    ``allowed_terms`` and the profile systems marked ``keep_name: true``."""
    out = [str(t) for t in doc.p.config.get("allowed_terms") or [] if str(t).strip()]
    systems = doc.p.profile.get("systems") or {}
    for s in systems.values():
        if isinstance(s, dict) and s.get("keep_name") and s.get("name"):
            out.append(str(s["name"]))
    return out


@functools.lru_cache(maxsize=32)
def _term_rx(term: str) -> re.Pattern:
    return re.compile(rf"(?<![\w/-]){re.escape(term)}(?![\w-]|/\w)")


def _layer_hits(doc: Doc, text: str, terms, pats, allowed) -> list[tuple[int, int, str, str]]:
    """Banned spans in one text as ``(start, end, shown, why)``. Overlapping
    matches keep the longest ("Microsoft Entra ID" over "Entra ID"); at one
    span a document or profile reason wins over the generic product one.
    Anything inside an allowed term is not a hit."""
    keep = [(m.start(), m.end()) for a in allowed for m in _term_rx(a).finditer(text)]
    cands = []
    for rank, (t, why) in enumerate(terms):
        for m in _term_rx(t).finditer(text):
            cands.append((m.start(), m.end(), t, f"'{t}' in a logical design ({why})", rank))
    for kind, rx in pats:
        for m in rx.finditer(text):
            if kind == "ipv6-address" and not _ipv6_ok(m.group(0)):
                continue
            cands.append((m.start(), m.end(), m.group(0), f"'{m.group(0)}' ({kind.replace('-', ' ')}) in a logical "
                          f"design", len(terms)))
    cands.sort(key=lambda c: (-(c[1] - c[0]), c[4], c[0]))
    taken: list[tuple[int, int]] = []
    out = []
    for s_, e, shown, msg, _ in cands:
        if any(a <= s_ and e <= b for a, b in keep):
            continue
        if any(s_ < b and a < e for a, b in taken):
            continue
        taken.append((s_, e))
        out.append((s_, e, shown, msg))
    return sorted(out)


def check_layer(doc: Doc) -> list[Finding]:
    if doc.p.layer != "logical":
        return []
    out = []
    terms = _banned_terms(doc)
    _, patterns = _products()
    pats = [(k, re.compile(v)) for k, v in patterns.items()]
    allowed = _allowed_terms(doc)
    for pc in doc.pieces:
        for _, _, shown, msg in _layer_hits(doc, pc.text, terms, pats, allowed):
            out.append(Finding("layer", ERROR, msg, doc.line_of(pc, shown), pc.anchor))
    for f in doc.p.figures + doc.p.views:
        for label, line in _figure_labels(f):
            for _, _, shown, msg in _layer_hits(doc, label, terms, pats, allowed):
                out.append(Finding("layer", ERROR, msg.replace("in a logical design", f"in {f.label}'s source"),
                                   Source(doc.p.rel(f.source_file), line), f.anchor))
    return out


# ---------------------------------------------------------------- boundary

def _surface(dep) -> tuple[dict[str, str], set[str]]:
    """A dependency's internal components (normalised title -> id) and its
    published surface (normalised interface and application names)."""
    surface: set[str] = set()
    for rec in dep.registers.get("component", []):
        for i in _strings(rec.data.get("interfaces")):
            surface.add(norm(i))
    for rec in dep.registers.get("integration", []):
        for f in ("interface", "title"):
            v = rec.data.get(f)
            if isinstance(v, str):
                surface.add(norm(v))
    for t in ("application", "capability"):
        for rec in dep.registers.get(t, []):
            surface.add(norm(rec.title))
    internals = {}
    for rec in dep.registers.get("component", []):
        n = norm(rec.title)
        if not n or any(n in s_ for s_ in surface):
            continue  # a component its own interfaces are named after is part of the surface
        if len(n.split()) >= 2 or len(n) >= 8:
            internals[n] = rec.id
    return internals, surface


def _consumers(p) -> list:
    """Projects next to this one whose depends_on names it."""
    from .project import Project, ProjectError
    out = []
    parent = p.root.parent
    for cfg in sorted(parent.glob("*/arch-doc.yaml")):
        if cfg.parent == p.root:
            continue
        try:
            data = yaml.safe_load(cfg.read_text()) or {}
        except yaml.YAMLError:
            continue
        for d in data.get("depends_on") or []:
            if isinstance(d, dict) and d.get("path") and (cfg.parent / d["path"]).resolve() == p.root:
                try:
                    out.append(Project.load(cfg.parent, (p.root,)))
                except ProjectError:
                    pass
                break
    return out


def check_boundary(doc: Doc) -> list[Finding]:
    out = []
    own = {norm(r.title) for reg in doc.p.registers.values() for r in reg}
    others = []
    if doc.p.kind == "solution":
        others = [(ref, d, "dependency") for ref, d in doc.p.dependencies.items() if d is not None]
    elif doc.p.kind == "capability":
        others = [(c.short, c, "consumer") for c in _consumers(doc.p)]
    for ref, other, role in others:
        internals, _ = _surface(other)
        internals = {k: v for k, v in internals.items() if k not in own}
        if not internals:
            continue
        rx = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(internals, key=len, reverse=True)) + r")\b")
        for pc in doc.pieces:
            if pc.kind == "deck":
                continue
            for m in rx.finditer(norm(pc.text)):
                rid = internals[m.group(1)]
                if role == "dependency":
                    msg = (f"'{m.group(1)}' is an internal component of {other.title} ({rid}), not one of its "
                           f"interfaces; describe what the platform offers, not how it is built")
                else:
                    msg = (f"'{m.group(1)}' is an internal component of the consumer {other.title} ({rid}); a "
                           f"capability design names what consumers use, not their parts")
                out.append(Finding("boundary", WARN, msg, doc.line_of(pc, m.group(1).split()[0]), pc.anchor))
                break
    return out


# --------------------------------------------------------------------- ids

class _IdMatcher:
    """Finds register ids in text: any token of upper-case segments joined
    by '-' that one of the metamodel's types accepts (``t.matches_id``),
    so every prefix of a multi-prefix type counts, and so do namespaced ids
    (``NW-SEC-RISK-03``). ``finditer``, ``findall`` and ``match`` behave as
    a compiled pattern's would."""

    _TOKEN = re.compile(r"(?<![\w-])[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+(?![\w-])")

    def __init__(self, types):
        self.types = list(types)

    def type_of(self, rid: str):
        for t in self.types:
            if t.matches_id(rid):
                return t
        return None

    def finditer(self, text: str):
        return (m for m in self._TOKEN.finditer(text) if self.type_of(m.group(0)) is not None)

    def findall(self, text: str) -> list[str]:
        return [m.group(0) for m in self.finditer(text)]

    def match(self, text: str):
        m = self._TOKEN.match(text)
        return m if m and self.type_of(m.group(0)) is not None else None


def _id_regex(doc: Doc) -> _IdMatcher:
    return _IdMatcher(doc.p.model.artefact_types.values())


def check_ids(doc: Doc) -> list[Finding]:
    out = []
    rx = _id_regex(doc)
    known = {r.id for reg in doc.p.registers.values() for r in reg}
    dep_known: set[str] = set()
    for d in doc.p.dependencies.values():
        if d is not None:
            dep_known |= {r.id for reg in d.registers.values() for r in reg}
    for pc in doc.pieces:
        if pc.kind == "deck":
            continue
        for m in rx.finditer(mask(pc.raw)):
            rid = m.group(0)
            if rid in known or rid in dep_known:
                continue
            out.append(Finding("ids", ERROR, f"{rid} is not in any register"
                               + (f" (cited by {pc.record.id}.{pc.field})" if pc.record else ""),
                               doc.line_of(pc, rid), pc.anchor))
    out += _crossing(doc)
    return out


def _crossing(doc: Doc) -> list[Finding]:
    """View n mapped to exception m and view n+1 to m-1: the two sequences
    cross (warn)."""
    pairs: list[tuple[int, int, str, Source, str | None]] = []
    exc = doc.p.model.artefact_types.get("exception")
    if exc is None:
        return []
    ids = _IdMatcher([exc])

    def number(rid: str) -> int | None:
        m = re.search(r"(\d+)$", rid)
        return int(m.group(1)) if m else None
    vrx = re.compile(r"\bView (\d+)\b")
    names = {}
    for v in doc.p.views:
        names[norm(v.title)] = v.number
        names[v.name.lower()] = v.number
    for b in doc.p.blocks():
        if type(b) is C.Table:
            for row, src, anc in zip(b.body, b.row_sources, b.row_anchors):
                text = " | ".join(row)
                vs, es = vrx.findall(text), ids.findall(text)
                if len(vs) == 1 and len(es) == 1 and number(es[0]) is not None:
                    pairs.append((int(vs[0]), number(es[0]), f"View {vs[0]} → {es[0]}", src, anc))
    if not pairs:
        for rec in doc.p.registers.get("exception", []):
            n = number(rec.id)
            if n is None or not exc.matches_id(rec.id):
                continue
            text = " ".join(_strings({k: v for k, v in rec.data.items() if k != "id"}))
            vs = vrx.findall(text)
            vn = int(vs[0]) if len(vs) == 1 else None
            if vn is None:
                hits = {n_ for k, n_ in names.items() if k and len(k) > 3 and k in norm(text)}
                vn = hits.pop() if len(hits) == 1 else None
            if vn is not None:
                pairs.append((vn, n, f"View {vn} → {rec.id}", rec.source, doc.row_anchor.get(rec.id)))
    pairs.sort(key=lambda x: (x[0], x[1]))
    out = []
    for a, b in zip(pairs, pairs[1:]):
        if b[0] > a[0] and b[1] < a[1]:
            out.append(Finding("ids", WARN, f"{b[2]} comes after {a[2]}: the view and exception sequences cross; "
                               f"number the exceptions in view order", b[3], b[4]))
    return out


# ------------------------------------------------------------------- empty

def check_empty(doc: Doc) -> list[Finding]:
    out = []
    for ch in doc.p.chapters:
        for s in ch.sections:
            if s.optional:
                continue
            src = s.source or ch.source or Source(f"content/ (chapter '{ch.key}')")
            if not s.blocks:
                out.append(Finding("empty", ERROR, f"{s.number} {s.title} has no content; write it, or say why it "
                                   f"is empty", src, s.anchor))
                continue
            if all(isinstance(b, C.RegisterTable) and not b.records for b in s.blocks):
                out.append(Finding("empty", ERROR, f"{s.number} {s.title} shows only empty register tables; say "
                                   f"why there are no records", src, s.anchor))
        out += _coverage(doc, ch)
    return out


def _coverage_type(doc: Doc, ch, s) -> str | None:
    raw = doc.p.metamodel.chapter(ch.key) or {}
    for rs in raw.get("sections") or []:
        if rs.get("key") == s.key and rs.get("covers"):
            return str(rs["covers"])
    m = re.search(r"\b[Ff]or each ([a-z][a-z-]*(?: [a-z][a-z-]*)?)", s.guidance or "")
    if not m:
        return None
    words = m.group(1).split()
    for L in (2, 1):
        types = doc.lexicon.get(tuple(words[:L]))
        if types and len(types) == 1:
            return next(iter(types))
    return None


def _coverage(doc: Doc, ch) -> list[Finding]:
    """A section whose guidance asks for something per record of a register
    ("For each integration ...") and that answers with a plain table must
    cover every record of that register in the chapter."""
    out = []
    for s in ch.sections:
        rtype = _coverage_type(doc, ch, s)
        if rtype is None or rtype not in doc.p.registers:
            continue
        if any(a.type == rtype for a in s.artefacts):
            continue
        parent = None
        for other in ch.sections:
            for a in other.artefacts:
                if a.type == rtype:
                    parent = (other, a.where)
                    break
            if parent:
                break
        reg = doc.p.registers[rtype]
        records = reg.filter(parent[1]) if parent else list(reg)
        if not records:
            continue
        for b in s.blocks:
            if type(b) is not C.Table:
                continue
            rows_text = [norm(" ".join(r)) for r in b.body]
            raw_rows = [" ".join(r) for r in b.body]
            if any(re.search(r"\b(all other|every other|remaining|others|all the rest)\b", t) for t in rows_text):
                continue
            cited, by_id = set(), False
            for rec in records:
                if any(re.search(rf"\b{re.escape(rec.id)}\b", t) for t in raw_rows):
                    cited.add(rec.id)
                    by_id = True
                elif len(rec.title) > 3 and any(norm(rec.title) in t for t in rows_text):
                    cited.add(rec.id)
            if not cited:
                continue
            missing = [r.id for r in records if r.id not in cited]
            if missing:
                scope = f"{parent[0].number} {parent[0].title}" if parent else f"the {rtype} register"
                out.append(Finding("empty", ERROR if by_id else WARN,
                                   f"{s.number} {s.title} covers {len(cited)} of the {len(records)} records in "
                                   f"{scope}; missing {', '.join(missing)}", b.source, b.anchor))
    return out


# ------------------------------------------------------------------ figure

NOT_PRODUCED = re.compile(r"^(?:not (?:yet )?(?:produced|drawn|created|started|done|available|included|built)|"
                          r"missing|to be (?:produced|drawn|created)|to do|todo|pending|outstanding|not provided|"
                          r"no|not in (?:this )?document)\b")
PRODUCED = re.compile(r"^(?:produced|included|done|drawn|complete|completed|available|provided|in (?:this )?document|"
                      r"present)\b")


def check_figure(doc: Doc) -> list[Finding]:
    out = []
    p = doc.p
    raws = "\n".join(b.raw for b in p.blocks()) + "\n" + "\n".join(pc.raw for pc in doc.pieces if pc.kind != "deck")
    texts = "\n".join(pc.text for pc in doc.pieces if pc.kind not in ("deck", "caption", "record"))
    used = set()
    for f in p.figures + p.views:
        kind = "fig" if not isinstance(f, C.View) else "view"
        used.add(f.name)
        if f.path is None and f.source_file is None:
            out.append(Finding("figure", ERROR, f"{f.label} '{f.name}': no diagrams/{f.name}.png, .svg, .mmd, .ead or "
                               f".py", f.source, f.anchor))
        elif f.path is None:
            out.append(Finding("figure", WARN, f"{f.label} '{f.name}' is not rendered yet; run archdoc diagrams "
                               f"--render", f.source, f.anchor))
        if f"{{{kind}:{f.name}}}" not in raws and not re.search(rf"\b{f.label}\b(?!\.)", texts):
            out.append(Finding("figure", ERROR, f"{f.label} '{f.name}' is never referenced; cite it with "
                               f"{{{kind}:{f.name}}} where the text discusses it", f.source, f.anchor))
    ddir = p.root / "diagrams"
    if ddir.exists():
        stems_used = used
        for path in sorted(ddir.iterdir()):
            if path.suffix in (".mmd", ".ead") and path.stem not in stems_used:
                out.append(Finding("figure", WARN, f"diagrams/{path.name} is not used by any FIGURE or VIEW",
                                   Source(f"diagrams/{path.name}")))
    out += _views_table(doc)
    return out


def _views_table(doc: Doc) -> list[Finding]:
    """A table that says a view was not produced while the document has it,
    or produced while it has none."""
    out = []
    p = doc.p
    idents: dict[str, Any] = {}
    for f in p.figures + p.views:
        idents[f.label.lower()] = f
        idents[f.name.lower()] = f
        idents[norm(f.caption)] = f
        if isinstance(f, C.View):
            vp = p.model.viewpoints.get(f.viewpoint) if f.viewpoint else None
            if vp:
                idents[norm(vp.title)] = f
            if f.ea_name:
                idents[norm(f.ea_name)] = f
    vp_titles = {}
    for vp in p.model.viewpoints.values():
        vp_titles[norm(vp.title)] = vp
        name = vp.name_for(p.profile.ea_metamodel)
        if name:
            vp_titles[norm(name)] = vp
    for b in p.blocks():
        if type(b) is not C.Table:
            continue
        status_cols = [i for i, h in enumerate(b.header)
                       if re.search(r"\b(status|produced|state|included|in document|available|done)\b", norm(h))]
        # The row's own view is named in its view (or link) column, or the
        # first column when no header says which. A view cited in another
        # cell ("Not drawn ... shown in {view:V5}") is not the row's.
        id_cols = [i for i, h in enumerate(b.header)
                   if re.search(r"\b(view|views|diagram|diagrams|figure|figures|link|picture)\b", norm(h))
                   and i not in status_cols] or [0]
        for raw_row, row, src, anc in zip(b.raw_rows, b.body, b.row_sources, b.row_anchors):
            cells = [norm(c) for c in row]
            hit = None
            for i in id_cols:
                if i >= len(cells):
                    continue
                for m in re.finditer(r"\{(?:fig|view):([^{}]+)\}", raw_row[i]):
                    if re.search(r"\b(?:shown|see|cf|in|under|like|as)\s*$", raw_row[i][:m.start()], re.I):
                        continue
                    if m.group(1).strip().lower() in idents:
                        hit = idents[m.group(1).strip().lower()]
                        break
                if hit is None and cells[i] in idents:
                    hit = idents[cells[i]]
                if hit:
                    break
            cols = status_cols or [i for i in range(len(cells))]
            for i in cols:
                if i >= len(cells):
                    continue
                c = cells[i]
                multi = bool(re.match(r"^(?:not (?:yet )?(?:produced|drawn|created|included)|to be (?:produced|"
                                      r"drawn))\b", c))
                if hit is not None and NOT_PRODUCED.match(c) and (status_cols or multi):
                    out.append(Finding("figure", ERROR, f"the row for '{row[0]}' says '{row[i]}', but the document "
                                       f"has it as {hit.label}", src, anc))
                    break
                if hit is None and status_cols and PRODUCED.match(c):
                    vp = next((vp_titles[x] for x in cells if x in vp_titles), None)
                    if vp is not None and not any(v.viewpoint == vp.key for v in p.views):
                        out.append(Finding("figure", WARN, f"the row for '{row[0]}' says '{row[i]}', but the "
                                           f"document has no {vp.title} VIEW", src, anc))
                        break
    return out


# ------------------------------------------------------------ figure-table

_MMD_NODE = re.compile(r"(?<![\w-])([A-Za-z_][\w-]*)\s*(?:\[\[|\[\(|\(\[|\(\(|\[/|\[\\|\{\{|\[|\(|\{|>)\s*"
                       r"\"?([^\]\)\}\"\n|]+?)\"?\s*(?:\]\]|\)\]|\]\)|\)\)|/\]|\\\]|\}\}|\]|\)|\})")
_MMD_EDGE = re.compile(r"(?<![\w-])(?P<a>[A-Za-z_][\w-]*)(?:\s*(?:\[\[|\[\(|\(\[|\(\(|\[|\(|\{)[^\]\)\}\n]*"
                       r"(?:\]\]|\)\]|\]\)|\)\)|\]|\)|\}))?\s*(?:(?P<op1>-{2,3}>|={2,3}>|-\.->|-{2,3}|-->>|--x|--o)"
                       r"\s*(?:\|(?P<l1>[^|]+)\|)?|--\s*(?P<l2>[^->|\n][^>|\n]*?)\s*-->|==\s*(?P<l3>[^=>|\n]+?)\s*==>)"
                       r"\s*(?P<b>[A-Za-z_][\w-]*)")
_SEQ_EDGE = re.compile(r"^\s*(?P<a>[A-Za-z_][\w-]*)\s*-{1,2}>{1,2}[+-]?\s*(?P<b>[A-Za-z_][\w-]*)\s*:\s*(?P<l>.+)$")
ACCESS_WORDS = {"read", "write", "read-write", "read/write", "readwrite", "create", "update", "delete", "crud",
                "none", "no access", "full", "admin", "owner", "contributor", "reader", "writer", "read-only",
                "write-only"}


def _figure_labels(f) -> list[tuple[str, int | None]]:
    """Visible text in a figure source: Mermaid labels, or the names of the
    EA model objects an .ead view shows."""
    src = getattr(f, "source_file", None)
    if src is None or not Path(src).exists():
        return []
    text = Path(src).read_text()
    out = []
    if src.suffix == ".mmd":
        for n, line in enumerate(text.split("\n"), start=1):
            if line.strip().startswith("%%"):
                continue
            for m in _MMD_NODE.finditer(line):
                out.append((m.group(2).strip(), n))
            for m in _MMD_EDGE.finditer(line):
                lab = m.group("l1") or m.group("l2") or m.group("l3")
                if lab:
                    out.append((lab.strip(), n))
            m = _SEQ_EDGE.match(line)
            if m:
                out.append((m.group("l").strip(), n))
    elif src.suffix == ".ead":
        model, ids = _ead_model(src, text)
        objs = {o.get("id"): o for o in model.get("objects", [])}
        for n, line in enumerate(text.split("\n"), start=1):
            for tok in re.findall(r"\b[A-Z][A-Z0-9]*-[A-Za-z0-9-]+\b", line):
                o = objs.get(tok)
                if o:
                    out.append((str(o.get("name", "")), n))
                    if o.get("status"):
                        out.append((str(o["status"]), n))
    return out


def _ead_model(src: Path, text: str) -> tuple[dict, set[str]]:
    m = re.search(r'^\s*model\s+"([^"]+)"', text, re.M)
    if not m:
        return {}, set()
    path = src.parent / m.group(1)
    try:
        model = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}, set()
    ids = set(re.findall(r"\b[A-Z][A-Z0-9]*-[A-Za-z0-9-]+\b", text))
    return model, ids


def _mmd_edges(src: Path) -> list[tuple[str, str, str, int]]:
    """(source label, target label, edge label, line) for each labelled edge."""
    text = src.read_text()
    labels: dict[str, str] = {}
    for line in text.split("\n"):
        for m in _MMD_NODE.finditer(line):
            labels.setdefault(m.group(1), m.group(2).strip())
        m = re.match(r"^\s*participant\s+(\w+)\s+as\s+(.+)$", line)
        if m:
            labels[m.group(1)] = m.group(2).strip()
    out = []
    for n, line in enumerate(text.split("\n"), start=1):
        if line.strip().startswith("%%"):
            continue
        for m in _MMD_EDGE.finditer(line):
            lab = m.group("l1") or m.group("l2") or m.group("l3")
            if lab:
                out.append((labels.get(m.group("a"), m.group("a")), labels.get(m.group("b"), m.group("b")),
                            lab.strip(), n))
        m = _SEQ_EDGE.match(line)
        if m:
            out.append((labels.get(m.group("a"), m.group("a")), labels.get(m.group("b"), m.group("b")),
                        m.group("l").strip(), n))
    return out


def _ead_edges(src: Path) -> list[tuple[str, str, str, int]]:
    text = src.read_text()
    model, ids = _ead_model(src, text)
    objs = {o.get("id"): o for o in model.get("objects", [])}
    out = []
    for r in model.get("relationships", []):
        lab = r.get("label") or r.get("name")
        if not lab or r.get("from") not in ids or r.get("to") not in ids:
            continue
        a, b = objs.get(r["from"], {}), objs.get(r["to"], {})
        line = next((n for n, ln in enumerate(text.split("\n"), start=1) if r["from"] in ln), None)
        out.append((str(a.get("name", r["from"])), str(b.get("name", r["to"])), str(lab), line or 1))
    return out


def _endpoint(label: str, cell: str) -> bool:
    a, c = norm(label), norm(cell)
    if not a or not c:
        return False
    return a == c or (len(a) > 3 and (a in c or c in a))


def _access(text: str) -> set[str]:
    low = text.lower()
    found = {w for w in ACCESS_WORDS if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", low)}
    if {"read-write"} & found or "read/write" in found:
        found -= {"read", "write"}
    return {"read-write" if w in ("read/write", "readwrite") else w for w in found}


def check_figure_table(doc: Doc) -> list[Finding]:
    out = []
    p = doc.p
    facts: list[tuple[list[str], str, Source, str | None]] = []  # cells, what, source, anchor
    for b in p.blocks():
        if type(b) is C.Table:
            for row, src, anc in zip(b.body, b.row_sources, b.row_anchors):
                facts.append(([plain(c) for c in row], f"the table at {src}", src, anc))
    records: list[Record] = []
    for t in ("integration", "data-flow"):
        records += list(p.registers.get(t, []))
    for f in p.figures + p.views:
        src = f.source_file
        if src is None or not Path(src).exists():
            continue
        if src.suffix == ".mmd":
            edges = _mmd_edges(Path(src))
        elif src.suffix == ".ead":
            edges = _ead_edges(Path(src))
        else:
            continue
        where_src = lambda n: Source(p.rel(Path(src)), n)  # noqa: E731
        for a, b, label, line in edges:
            lab_tbc = bool(tbc_markers(label))
            lab_acc = _access(label)
            done = False
            for rec in records:
                s_, t_ = display(rec.get("source")), display(rec.get("target"))
                s_names = _record_names(doc, s_)
                t_names = _record_names(doc, t_)
                if not (any(_endpoint(a, x) for x in s_names) and any(_endpoint(b, x) for x in t_names)) and \
                        not (any(_endpoint(b, x) for x in s_names) and any(_endpoint(a, x) for x in t_names)):
                    continue
                has_tbc = bool(rec.tbcs())
                if lab_tbc and not has_tbc:
                    out.append(Finding("figure-table", WARN, f"{f.label}: '{a} → {b}' is labelled '{label}', but "
                                       f"{rec.id} has nothing TBC", where_src(line), f.anchor))
                    done = True
                    break
                for fname, spec in rec.type.fields.items():
                    if spec.kind != "enum":
                        continue
                    val = display(rec.get(fname)).lower()
                    words = {w for w in spec.enum if len(w) > 2 and re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])",
                                                                             label.lower())}
                    if words and val and val not in words and not isinstance(rec.get(fname), Tbc):
                        out.append(Finding("figure-table", WARN, f"{f.label}: '{a} → {b}' is labelled '{label}', "
                                           f"but {rec.id} {fname} is '{val}'", where_src(line), f.anchor))
                        done = True
                        break
                if done:
                    break
            if done:
                continue
            for cells, what, fsrc, anc in facts:
                ia = [i for i, c in enumerate(cells) if _endpoint(a, c)]
                ib = [i for i, c in enumerate(cells) if _endpoint(b, c)]
                if not ia or not ib or set(ia) == set(ib):
                    continue
                rest = " ".join(c for i, c in enumerate(cells) if i not in ia and i not in ib)
                row_tbc = bool(tbc_markers(rest))
                row_acc = _access(rest)
                if lab_tbc and not row_tbc:
                    out.append(Finding("figure-table", WARN, f"{f.label}: '{a} → {b}' is labelled '{label}', but "
                                       f"{what} says '{rest.strip()}'", where_src(line), f.anchor))
                    break
                if row_tbc and not lab_tbc and lab_acc:
                    out.append(Finding("figure-table", WARN, f"{f.label}: '{a} → {b}' is labelled '{label}', but "
                                       f"{what} still has it TBC", where_src(line), f.anchor))
                    break
                if lab_acc and row_acc and lab_acc != row_acc:
                    out.append(Finding("figure-table", WARN, f"{f.label}: '{a} → {b}' is labelled '{label}', but "
                                       f"{what} says '{', '.join(sorted(row_acc))}'", where_src(line), f.anchor))
                    break
    return out


def _record_names(doc: Doc, value: str) -> list[str]:
    """A source or target field as names: the text, and the title of any
    record id it holds."""
    out = [value]
    for rid in re.findall(r"\b[A-Z][A-Z0-9]*-[A-Za-z0-9-]+\b", value):
        rec = doc.p.record(rid)
        if rec is not None:
            out.append(rec.title)
    return out


# ---------------------------------------------------------- stale-template

_TEMPLATE_WORDS = (r"Write|Insert|Describe|Add|List|Enter|Provide|Summari[sz]e|State|Explain|Include|Delete|Remove|"
                   r"Replace|Update|Complete|Fill|Outline|Document|Specify|Identify|Attach|Detail|Define|Name|Solution|"
                   r"Project|Application|Organi[sz]ation|Company|Client|Customer|Date|Version|Title|Owner|Author|"
                   r"System|Product|Service|Vendor|Team|Your|Optional|Guidance|Instruction|Example|Placeholder|"
                   r"Section|Chapter|TBD|TBA|XX+|Text")
_STALE = [
    (re.compile(rf"\[(?:{_TEMPLATE_WORDS})\b[^\]\n]{{0,120}}\](?!\()"), "template guidance in brackets"),
    (re.compile(rf"\[(?:{_TEMPLATE_WORDS})\b(?:[^\]\n]*?/[^\]\n]*?)?$"), "an unclosed template field"),
    (re.compile(rf"\[(?:{_TEMPLATE_WORDS})\s*/\s*[A-Z][^\]\n]*"), "a template field"),
    (re.compile(r"<\s*(?:insert|enter|add|name|date|describe|your|project|solution|system|organi[sz]ation)\b[^>\n]*>",
                re.I), "a template field in angle brackets"),
    (re.compile(r"\{\{[^{}\n]+\}\}|<<[^<>\n]+>>"), "a template field"),
    (re.compile(r"\blorem ipsum\b", re.I), "filler text"),
    (re.compile(r"\b(?:TODO|FIXME|XXX)\b"), "a note left in the text"),
    (re.compile(r"\bCite registers with placeholders\b|\bLead-in: before the first section\b"), "scaffold guidance"),
]


def check_stale_template(doc: Doc) -> list[Finding]:
    out = []
    for pc in doc.pieces:
        text = mask(pc.raw)
        for rx, what in _STALE:
            m = rx.search(text)
            if m:
                out.append(Finding("stale-template", ERROR, f"{what} left in: '{m.group(0)[:60]}'",
                                   doc.line_of(pc, m.group(0)), pc.anchor))
                break
        else:
            if pc.kind in ("para", "item") and pc.section is not None and pc.section.guidance:
                if _copies(pc.section.guidance, pc.raw):
                    out.append(Finding("stale-template", ERROR, f"{pc.section.number} still carries the metamodel's "
                                       f"guidance text; replace it with the content it asks for", pc.source,
                                       pc.anchor))
    return out


def _copies(guidance: str, raw: str, window: int = 10) -> bool:
    g = norm(mask(guidance)).split()
    t = " " + norm(mask(raw)) + " "
    if len(g) < window:
        return len(g) >= 6 and " " + " ".join(g) + " " in t
    for i in range(0, len(g) - window + 1):
        if " " + " ".join(g[i:i + window]) + " " in t:
            return True
    return False


# ------------------------------------------------------------------- voice

@functools.lru_cache(maxsize=1)
def _voice() -> list[tuple[re.Pattern, str, str]]:
    data = yaml.safe_load((DATA / "voice.yaml").read_text())
    out = []
    for group in ("marketing", "padding", "self-reference"):
        for phrase in data.get(group) or []:
            out.append((re.compile(rf"(?<![\w-]){re.escape(str(phrase))}(?![\w-])", re.I), group, str(phrase)))
    for name, pat in (data.get("patterns") or {}).items():
        out.append((re.compile(pat, re.I), name, name))
    return out


def check_voice(doc: Doc) -> list[Finding]:
    out = []
    why = {"marketing": "a marketing word", "padding": "padding", "self-reference": "the document talking about "
           "itself", "reversal": "a rhetorical reversal", "reversal-sentence": "a rhetorical reversal",
           "not-just-but": "a rhetorical reversal", "less-about-more-about": "a rhetorical reversal",
           "isnt-about": "a rhetorical reversal"}
    for pc in doc.pieces:
        if pc.kind in ("header",):
            continue
        text = re.sub(r"`[^`]*`|\"[^\"]*\"|“[^”]*”", " ", mask(pc.raw))
        for rx, group, phrase in _voice():
            m = rx.search(text)
            if m:
                out.append(Finding("voice", WARN, f"'{m.group(0)}': {why.get(group, group)}",
                                   doc.line_of(pc, m.group(0)), pc.anchor))
    return out


# ------------------------------------------------------------- consistency

_POS = r"approved|endorsed|signed[ -]off|ratified"
_NEG_WORD = r"approved|endorsed|reviewed|signed[ -]off|submitted|assessed"
_MODAL = {"will", "must", "should", "shall", "would", "could", "can", "may", "might", "to", "once", "if", "when",
          "until", "before", "after", "unless", "needs", "need", "requires", "require", "seeks", "seek", "asks"}
_PRONOUNS = {"it", "this", "that", "they", "them", "which", "what", "who", "these", "those", "one", "each", "all",
             "nothing", "everything", "something", "anything"}
_PASSIVE = re.compile(rf"\b(?P<aux>was|were|is|are|has|have|had)\s+(?P<neg>not\s+)?(?:yet\s+)?(?:been\s+)?"
                      rf"(?P<w>{_POS}|reviewed|submitted|rejected|declined|assessed)\b", re.I)
_ACTIVE = re.compile(rf"\b(?P<neg>(?:has|have|had|did)\s+not\s+(?:yet\s+)?)?(?P<w>{_POS}|approve|endorse|review|"
                     rf"reviewed|rejected|declined)\s+(?:on\s+)?(?P<np>(?:the|our|its|their)\s+[A-Za-z][\w-]*(?:\s+"
                     rf"[A-Za-z][\w-]*){{0,3}})", re.I)
_ADJ = re.compile(rf"\b(?P<w>unreviewed|unapproved)\s+(?P<np>[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){{0,2}})", re.I)


def _np_before(text: str) -> str | None:
    words = re.findall(r"[A-Za-z][\w-]*", text)
    np_: list[str] = []
    for w in reversed(words[-5:]):
        lw = w.lower()
        if lw in FUNCTION_WORDS or lw in DETERMINERS or lw in _MODAL:
            break
        np_.insert(0, lw)
    return _np_norm(np_)


def _np_norm(words: list[str]) -> str | None:
    words = [w for w in words if w not in DETERMINERS]
    while words and words[-1] in FUNCTION_WORDS:
        words.pop()
    if not words or words[-1] in _PRONOUNS or all(w in _PRONOUNS for w in words):
        return None
    return " ".join(stem(w) for w in words[-4:])


def _np_after(text: str) -> str | None:
    words = re.findall(r"[A-Za-z][\w-]*", text)
    np_: list[str] = []
    for w in words[:5]:
        lw = w.lower()
        if lw in DETERMINERS and not np_:
            continue
        if lw in FUNCTION_WORDS or lw in _MODAL:
            break
        np_.append(lw)
    return _np_norm(np_)


def _modal_before(text: str) -> bool:
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)][-3:]
    return bool(set(words) & _MODAL)


def check_consistency(doc: Doc) -> list[Finding]:
    """The same noun phrase called approved in one place and not reviewed
    (or rejected) in another (warn)."""
    claims: dict[str, list[tuple[bool, str, Source, str | None]]] = {}
    for pc in doc.pieces:
        if pc.kind not in ("para", "item", "cell"):
            continue
        for off, sent in sentences(pc.masked):
            for m in _PASSIVE.finditer(sent):
                if _modal_before(sent[:m.start("aux")]):
                    continue
                w = m.group("w").lower()
                if w in ("reviewed", "submitted", "assessed") and not m.group("neg"):
                    continue
                neg = bool(m.group("neg")) or w in ("rejected", "declined")
                np_ = _np_before(sent[:m.start()])
                if np_:
                    claims.setdefault(np_, []).append((not neg, m.group(0), doc.line_of(pc, m.group(0)), pc.anchor))
            for m in _ACTIVE.finditer(sent):
                if _modal_before(sent[:m.start()]):
                    continue
                w = m.group("w").lower()
                neg = bool(m.group("neg")) or w in ("rejected", "declined")
                if w in ("review", "reviewed", "approve", "endorse") and not m.group("neg"):
                    continue
                np_ = _np_after(m.group("np"))
                if np_:
                    claims.setdefault(np_, []).append((not neg, m.group(0), doc.line_of(pc, m.group(0)), pc.anchor))
            for m in _ADJ.finditer(sent):
                np_ = _np_after(m.group("np"))
                if np_:
                    claims.setdefault(np_, []).append((False, m.group(0), doc.line_of(pc, m.group(0)), pc.anchor))
    out = []
    for np_, cs in claims.items():
        cs = [(pos, re.sub(r"\s+(?:in|on|at|by|for|with|from|during|after|before|last|this)\b.*$", "", said), src, anc)
              for pos, said, src, anc in cs]
        pols = {c[0] for c in cs}
        if len(pols) < 2:
            continue
        first = cs[0]
        for pos, said, src, anc in cs[1:]:
            if pos == first[0]:
                continue
            out.append(Finding("consistency", WARN, f"'{said}' contradicts '{first[1]}' at {first[2]}: say which "
                               f"{np_} was approved and which was not", src, anc))
    return out


def _same_value(a: str, b: str) -> bool:
    x, y = norm(a), norm(b)
    return x == y or (len(x) > 3 and len(y) > 3 and (x in y or y in x))


def _blocks_with_section(doc: Doc):
    for ch in doc.p.chapters:
        for b in ch.lead:
            yield ch, None, b
        for sec in ch.sections:
            for b in sec.blocks:
                yield ch, sec, b


def _column_map(doc: Doc, ch, sec) -> dict[str, str]:
    """Normalised header -> field for one section's tables: the extracted
    ``column_map`` (template header -> field) and the section's ``labels``
    (field -> header)."""
    out: dict[str, str] = {}
    if sec is None:
        return out
    raw = doc.p.metamodel.chapter(ch.key) or {}
    for rs in raw.get("sections") or []:
        if rs.get("key") == sec.key:
            for header, fname in (rs.get("column_map") or {}).items():
                out[norm(str(header))] = str(fname)
    for fname, header in (getattr(sec, "labels", None) or {}).items():
        out.setdefault(norm(str(header)), str(fname))
    return out


def _header_core(h: str) -> str:
    """A header without a trailing condition or note: 'Impact if Delayed'
    and 'Impact if late' are both 'impact'; 'Owner (role)' is 'owner'."""
    t = norm(re.sub(r"\([^)]*\)", " ", h))
    return re.sub(r"\s+if\s+.*$", "", t).strip()


def _column_field(at, header: str, cmap: dict[str, str]) -> str | None:
    """The field a table column holds: the section's column map, then the
    type's field names and labels, then the same with a trailing 'if ...'
    or parenthetical dropped."""
    h = norm(header)
    if h in cmap and (cmap[h] in at.fields or cmap[h] == "title"):
        return cmap[h]
    names: dict[str, str] = {}
    for fname in list(at.fields) + ["title"]:
        names.setdefault(norm(fname.replace("_", " ")), fname)
        names.setdefault(norm(at.header(fname)), fname)
    if h in names:
        return names[h]
    core = _header_core(header)
    cores = {_header_core(k): v for k, v in names.items()}
    return cores.get(core) if core else None


def _names_id(at, header: str) -> bool:
    """Whether a column header names a type's id: 'ID', 'Ref', 'No.',
    'Dependency', 'DEP ID', 'Risk ref'."""
    h = norm(header).replace("-", " ")
    words = h.split()
    if not words:
        return False
    id_words = {"id", "ids", "ref", "reference", "no", "number", "key", "#"}
    if h in id_words or header.strip() == "#":
        return True
    names = {norm(at.label), norm(at.key.replace("-", " ")), norm(at.header("title"))} | \
            {p_.lower() for p_ in at.prefixes}
    if words[-1] in id_words:
        words = words[:-1]
    return " ".join(words) in names


def check_table_values(doc: Doc) -> list[Finding]:
    """A plain table that cites a record by id and gives one of its fields a
    value the register (or another table) contradicts: DEP-03's impact one
    thing in 4.7 and another in 19.4 (warn). The register is the reference
    wherever the column names a field; two tables are compared with each
    other only when the register leaves that field empty. Columns that are
    not fields of the record are not compared."""
    out = []
    rx = _id_regex(doc)
    seen: dict[tuple[str, str], tuple[str, Source, str | None]] = {}
    for ch, sec, b in _blocks_with_section(doc):
        if type(b) is not C.Table or not b.body:
            continue
        width = len(b.header)
        cmap = _column_map(doc, ch, sec)
        id_col = None
        for i in range(width):
            hits, types = 0, {}
            for row in b.body:
                cell = plain(row[i]).strip() if i < len(row) else ""
                m = rx.match(cell)
                rec = doc.p.record(m.group(0)) if m else None
                if rec is not None and len(rx.findall(cell)) == 1:
                    hits += 1
                    types[rec.type.key] = types.get(rec.type.key, 0) + 1
            if not hits or hits * 2 < len(b.body):
                continue
            at = doc.p.model.artefact_types[max(types, key=types.get)]
            # A table is keyed on its first column, or on a column whose
            # header names the type's id; any other column of ids is a
            # cross-reference ("Control / Risk") and is not compared.
            if i == 0 or cmap.get(norm(b.header[i])) == "id" or _names_id(at, b.header[i]):
                id_col = i
                break
        if id_col is None:
            continue
        for row, src, anc in zip(b.body, b.row_sources, b.row_anchors):
            cell = plain(row[id_col]).strip() if id_col < len(row) else ""
            m = rx.match(cell)
            if not m or len(rx.findall(cell)) != 1:
                continue
            rec = doc.p.record(m.group(0))
            if rec is None:
                continue
            at = rec.type
            # A section's column map names its own registers' columns; it says
            # nothing about another register's records cited in its tables.
            sec_types = ({a.type for a in sec.artefacts} | {x.type for x in sec.blocks
                                                            if isinstance(x, C.RegisterTable)}) if sec else set()
            rec_cmap = cmap if not sec_types or at.key in sec_types else {}
            for i, h in enumerate(b.header):
                if i == id_col or i >= len(row):
                    continue
                fname = _column_field(at, h, rec_cmap)
                if fname is None or fname in ("id", "status"):
                    continue
                value = plain(row[i]).strip()
                if not value or tbc_markers(value):
                    continue
                reg_v = rec.get(fname)
                if isinstance(reg_v, Tbc):
                    continue
                reg_text = display(reg_v)
                if reg_text.strip():
                    if not _same_value(value, reg_text):
                        out.append(Finding("consistency", WARN, f"{rec.id} {h.strip().lower()} is '{value}' here, "
                                           f"but the {at.key} register says '{reg_text}'; cite "
                                           f"{{reg:{rec.id}.{fname}}} instead", src, anc))
                    continue
                key = (rec.id, fname)
                if key in seen:
                    v0, s0, _ = seen[key]
                    if not _same_value(value, v0):
                        out.append(Finding("consistency", WARN, f"{rec.id} {h.strip().lower()} is '{value}' here, "
                                           f"but '{v0}' at {s0}; record it once in the {at.key} register", src, anc))
                else:
                    seen[key] = (value, src, anc)
    return out


CHECKS = [check_issues, check_count_prose, check_count_model, check_xref, check_version, check_tbc_owner,
          check_layer, check_boundary, check_ids, check_empty, check_figure, check_figure_table,
          check_stale_template, check_voice, check_consistency, check_table_values]


def cli(args) -> int:
    """``archdoc check [--json]``, for callers that prefer the module's own
    entry point; the CLI in archdoc.py prints the same."""
    from .project import Project
    findings = run(Project.load(args.project))
    if getattr(args, "json", False):
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        for f in findings:
            print(f)
        errors = sum(1 for f in findings if f.severity == ERROR)
        print(f"{errors} errors, {len(findings) - errors} warnings")
    return 1 if any(f.severity == ERROR for f in findings) else 0


__all__ = ["Finding", "run", "cli", "CHECK_IDS"]
