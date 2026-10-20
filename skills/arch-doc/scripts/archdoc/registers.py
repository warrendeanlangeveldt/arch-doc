"""Registers: typed records, TBC values and ``where`` filters.

Each artefact type in the metamodel has a schema (:class:`ArtefactType`) and
one register file, ``registers/<type>.yaml``, holding a list of records.
Loading a register never raises on bad data: every problem is collected as a
:class:`Problem` so the checks can report them all at once with their
location.

Any field value may be ``TBC`` or ``TBC: <owner>`` (also written
``{TBC: <owner>}``), and a longer text value may carry one ("Queue and back
off; TBC: Cloud Platform"). A bare ``TBC`` takes the record's ``owner``; when
the record has no owner the TBC has none, which the ``tbc-owner`` check fails.

Display: :meth:`Record.shown` is a field's value as a reader sees it
(placeholders resolved, enum and status values labelled, "Must" not
"must"); :meth:`Record.cells` is a table row of those, with an inherited
TBC shortened to "TBC" when the row already names the owner. The stored
values in ``Record.data`` never change.
"""
from __future__ import annotations

import datetime as _dt
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml

CHIPS = ("done", "partial", "not-started", "tbc")
SCALAR_TYPES = ("text", "date", "number", "list")
ALWAYS = ("id", "title", "status")

# "TBC: owner", or with an em or en dash: "TBC — owner", "TBC – owner".
_TBC = re.compile(r"^\s*TBC\s*(?:[:—–]\s*(?P<owner>.*\S))?\s*$", re.IGNORECASE)
# A TBC inside longer text; the owner runs to the next punctuation mark.
EMBEDDED_TBC = re.compile(r"\bTBC\b(?:\s*[:—–]\s*(?P<owner>[^.;,)\]\n|]*[^.;,)\]\n|\s]))?")
# Any placeholder, so a resolved {reg:} value is never read as a TBC of its own.
ANY_PLACEHOLDER = re.compile(r"\{[a-z]+:[^{}]*\}")
_PREFIX = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*$")
_SEGMENT = re.compile(r"^[A-Za-z0-9]+$")
_NAMESPACE = re.compile(r"^[A-Z][A-Z0-9]*$")


@dataclass(frozen=True)
class Source:
    """Where something came from: a file and a 1-based line."""

    file: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass
class Problem:
    """A problem found while loading: ``code`` is the check id it feeds
    (``ids``, ``schema``, ``tbc-owner``, ``content``, ``xref`` ...)."""

    code: str
    message: str
    source: Source | None = None
    anchor: str | None = None

    def __str__(self) -> str:
        where = f"{self.source}: " if self.source else ""
        return f"{where}[{self.code}] {self.message}"


@dataclass(frozen=True)
class Tbc:
    """A to-be-confirmed value. ``owner`` is who confirms it, or None.
    ``inherited`` is True when the owner came from the record's owner."""

    owner: str | None = None
    inherited: bool = False

    def __str__(self) -> str:
        return f"TBC: {self.owner}" if self.owner else "TBC"


def parse_tbc(value: Any) -> Tbc | None:
    """A :class:`Tbc` when ``value`` is a TBC, else None."""
    if isinstance(value, Tbc):
        return value
    if isinstance(value, str):
        m = _TBC.match(value)
        if m:
            return Tbc(m.group("owner"))
        return None
    if isinstance(value, dict) and len(value) == 1:
        (k, v), = value.items()
        if isinstance(k, str) and k.strip().upper() == "TBC":
            return Tbc(str(v).strip() if v is not None and str(v).strip() else None)
    return None


# A word before "TBC" that makes it a noun ("Every TBC has an owner"), not a value.
TBC_NOUN_BEFORE = frozenset((
    "a", "an", "the", "every", "each", "any", "no", "one", "all", "this", "that", "these", "those", "its",
    "their", "our", "your", "his", "her", "which", "another", "per", "some", "such", "single", "same"))
# An adjective that may sit between such a word and "TBC" ("each open TBC").
TBC_NOUN_ADJECTIVE = frozenset((
    "open", "unowned", "owned", "bare", "remaining", "outstanding", "new", "inherited", "unresolved",
    "resolved", "settled", "unsettled", "whole", "inline", "embedded"))
_QUOTES = "'\"`\u2018\u201c"
_WORDS_BEFORE = re.compile(r"([A-Za-z]+)\W*$")


def _is_quoted(text: str, start: int) -> bool:
    """Whether the TBC at ``start`` opens a quotation ("write 'TBC: owner'"),
    which mentions the marker rather than using it."""
    return start > 0 and text[start - 1] in _QUOTES


def _is_noun_use(text: str, start: int) -> bool:
    """Whether the TBC at ``start`` is the word used as a noun, judged from
    the text before it: "Every TBC", "each open TBC", "a TBC". Only what
    precedes it counts, so a caller that cuts the text at a TBC still reads
    it as a value marker."""
    before = text[max(0, start - 60):start]
    words = re.findall(r"[A-Za-z']+", before)
    if not words or not re.search(r"[A-Za-z']\s+$", before):
        return False
    prev = words[-1].lower()
    if prev in TBC_NOUN_BEFORE:
        return True
    return prev in TBC_NOUN_ADJECTIVE and len(words) > 1 and words[-2].lower() in TBC_NOUN_BEFORE


def tbc_markers(text: str) -> list[tuple[int, int, Tbc]]:
    """Every TBC that marks an open value in ``text``, as ``(start, end,
    Tbc)`` positions in ``text`` itself: a bare ``TBC`` ("Due date TBC") or
    ``TBC: <owner>`` (or with an em or en dash). "TBC" used as a noun
    ("Every TBC has an owner", "a TBC") or quoted is not a marker, and a
    placeholder is never read as one. The one rule every output and check
    uses."""
    clean = ANY_PLACEHOLDER.sub(lambda m: " " * len(m.group(0)), text)
    out = []
    for m in EMBEDDED_TBC.finditer(clean):
        owner = (m.group("owner") or "").strip() or None
        if _is_quoted(clean, m.start()) or (owner is None and _is_noun_use(clean, m.start())):
            continue
        out.append((m.start(), m.end(), Tbc(owner)))
    return out


_SLOT_PREP = frozenset({
    "at", "on", "in", "by", "for", "after", "before", "until", "once", "when", "during", "from", "to", "with",
    "within", "upon", "pending", "subject", "per", "if", "as", "via", "following", "prior", "post", "pre",
    "between", "around", "about", "over", "under"})
_SLOT_VERB = frozenset({
    "not", "proposed", "measured", "agreed", "confirmed", "decided", "awaiting", "waiting", "expected", "planned",
    "scheduled", "required", "needed", "depends", "depending", "being", "be", "tbd", "still", "yet", "due",
    "needs", "requires", "awaits", "see", "to-be", "unknown", "unconfirmed", "undecided", "open", "outstanding",
    "raised", "discussed", "reviewed", "submitted"})
_SLOT_CLAUSE = frozenset({
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "will", "would", "should", "shall",
    "can", "could", "may", "might", "must", "do", "does", "did", "whether", "if", "unless", "until", "once",
    "when", "while", "because", "since", "how", "what", "which", "why", "who", "where", "depends", "depending",
    "requires", "needs", "awaits", "awaiting"})
_SLOT_STAGE = frozenset({
    "concept", "design", "detailed", "high-level", "hld", "lld", "build", "go-live", "golive", "cutover",
    "procurement", "endorsement", "approval", "review", "discovery", "mobilisation", "mobilization", "stage",
    "phase", "gate", "sprint", "release", "pilot", "hypercare", "uat"})
_MONTHS = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
           r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
_SLOT_DATE = re.compile(rf"\b(?:19|20)\d\d\b|\bq[1-4]\b|\b\d{{1,2}}/\d{{1,2}}\b|^(?:{_MONTHS})$|"
                        rf"\b(?:{_MONTHS})\s+\d")
_SLOT_JOIN = re.compile(r"\s+(?:with|and|&)\s+|\s*[,/+]\s*", re.IGNORECASE)


def owner_problem(text: str) -> str | None:
    """Why a TBC's owner slot is not an owner, or None when it is one.

    An owner is a short noun phrase naming a role, team or person ("Head of
    Parcels", "Cyber Security", "J. Smith"), or several joined by "with",
    "and", "&", "/" or a comma ("Platform team with the platform owner"). A
    slot that reads as a clause ("whether the hosting is recorded as
    configuration items", "the X owner once named"), a time or condition
    ("at concept endorsement"), a state ("not measured", "proposed for this
    review"), a design stage ("detailed design") or a date ("Q3 2026") is
    not one; nor is a part longer than six words. "May", "Will" and "Can"
    are also names, so as clause words they count only in lower case. The
    one rule the checks and the outputs use."""
    words = re.findall(r"[A-Za-z0-9][\w'.-]*", text or "")
    if not words:
        return None
    low = [w.lower().rstrip(".") for w in words]
    if low[0] in _SLOT_PREP:
        return "a time or condition"
    if any(x in _SLOT_CLAUSE and (x not in ("may", "will", "can") or orig.islower())
           for x, orig in zip(low, words)):
        return "a question or condition"
    if low[0] in _SLOT_VERB or (len(low[0]) > 4 and low[0].endswith("ed") and len(words) > 1):
        return "a state or topic"
    if all(x in _SLOT_STAGE for x in low):
        return "a design stage"
    if _SLOT_DATE.search(text.lower().strip()):
        return "a date"
    for part in _SLOT_JOIN.split(text.strip()):
        if len(re.findall(r"[A-Za-z0-9][\w'.-]*", part)) > 6:
            return "a sentence"
    return None


def is_owner(text: str) -> bool:
    """Whether a TBC's owner slot names an owner (see :func:`owner_problem`)."""
    return bool((text or "").strip()) and owner_problem(text) is None


def embedded_tbcs(text: str) -> list[Tbc]:
    """The TBCs marking open values inside text (see :func:`tbc_markers`)."""
    return [t for _, _, t in tbc_markers(text)]


def label_value(value: str) -> str:
    """An enum or status value as a reader sees it: "must" -> "Must",
    "in-build" -> "In build", "not-started" -> "Not started"."""
    text = value.replace("-", " ").replace("_", " ")
    return text[:1].upper() + text[1:]


def display(value: Any) -> str:
    """A field value as table text."""
    if value is None:
        return ""
    if isinstance(value, Tbc):
        return str(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(display(v) for v in value)
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    return str(value)


# --------------------------------------------------------------- filters

@dataclass(frozen=True)
class Condition:
    field: str
    op: str  # "=" or "!="
    values: tuple[str, ...]

    def matches(self, record: "Record") -> bool:
        v = record.get(self.field)
        if isinstance(v, (list, tuple)):
            cands = [display(x).lower() for x in v]
        elif isinstance(v, Tbc):
            cands = ["tbc"]
        else:
            cands = [display(v).lower()]
        hit = any(c in self.values for c in cands)
        return hit if self.op == "=" else not hit

    def __str__(self) -> str:
        return f"{self.field}{self.op}{'|'.join(self.values)}"


@dataclass(frozen=True)
class Where:
    """A conjunction of conditions: ``where category=architecture
    status!=closed rating=high|extreme``."""

    conditions: tuple[Condition, ...] = ()

    def matches(self, record: "Record") -> bool:
        return all(c.matches(record) for c in self.conditions)

    def __bool__(self) -> bool:
        return bool(self.conditions)

    def __str__(self) -> str:
        return " ".join(str(c) for c in self.conditions)

    @property
    def fields(self) -> list[str]:
        return [c.field for c in self.conditions]


_COND = re.compile(r"^(?P<f>[A-Za-z_][\w-]*)\s*(?P<op>!=|=)\s*(?P<v>.+)$")


def parse_conditions(tokens: Iterable[str]) -> Where:
    """Conditions from ``k=v`` / ``k!=v`` tokens; ``v`` may be ``a|b``."""
    conds = []
    for t in tokens:
        m = _COND.match(t.strip())
        if not m:
            raise ValueError(f"bad condition '{t}' (expected field=value or field!=value)")
        vals = tuple(v.strip().lower() for v in m.group("v").split("|") if v.strip())
        if not vals:
            raise ValueError(f"condition '{t}' has no value")
        conds.append(Condition(m.group("f"), m.group("op"), vals))
    return Where(tuple(conds))


def split_args(text: str) -> list[str]:
    """Shell-like split that keeps quoted values together."""
    try:
        return shlex.split(text, posix=True)
    except ValueError as e:
        raise ValueError(f"cannot split '{text}': {e}") from e


def parse_selector(text: str) -> tuple[str, Where]:
    """``'risk where category=architecture'`` -> ``('risk', Where(...))``.
    Used by metamodel ``artefacts:`` entries and the ``{count:}`` / ``{ids:}``
    placeholders."""
    parts = split_args(text)
    if not parts:
        raise ValueError("empty register selector")
    rtype, rest = parts[0], parts[1:]
    if rest:
        if rest[0] != "where":
            raise ValueError(f"expected 'where' after '{rtype}', got '{rest[0]}'")
        if len(rest) == 1:
            raise ValueError(f"'where' with no conditions in '{text}'")
        return rtype, parse_conditions(rest[1:])
    return rtype, Where()


# ---------------------------------------------------------------- schema

@dataclass
class FieldSpec:
    name: str
    kind: str  # enum | text | date | number | list | ref | refs
    enum: tuple[str, ...] = ()
    ref_type: str | None = None

    @classmethod
    def parse(cls, name: str, spec: Any) -> "FieldSpec":
        if isinstance(spec, list):
            if not spec:
                raise ValueError(f"field '{name}': empty enum")
            return cls(name, "enum", tuple(display(v).lower() for v in spec))
        if isinstance(spec, str):
            if spec in SCALAR_TYPES:
                return cls(name, spec)
            m = re.match(r"^(ref|refs):([a-z][a-z0-9-]*)$", spec)
            if m:
                return cls(name, m.group(1), ref_type=m.group(2))
        raise ValueError(
            f"field '{name}': type '{spec}' is not an enum list, "
            f"one of {', '.join(SCALAR_TYPES)}, or ref:<type> / refs:<type>")


@dataclass
class ArtefactType:
    """One artefact type's schema: prefix, fields, columns and the status
    vocabulary mapped to chips."""

    key: str
    prefix: str
    label: str
    fields: dict[str, FieldSpec]
    columns: list[str]
    status: dict[str, str]
    labels: dict[str, str] = field(default_factory=dict)
    plural: str = ""        # the label's plural when adding an "s" is wrong ("process readiness records")
    prefixes: tuple[str, ...] = ()       # every accepted prefix; ``prefix`` is the first
    value_labels: dict[str, str] = field(default_factory=dict)   # enum value -> display label ("api": "API")

    def __post_init__(self):
        if not self.prefixes:
            self.prefixes = (self.prefix,)

    @classmethod
    def from_dict(cls, key: str, d: Any) -> tuple["ArtefactType | None", list[str]]:
        errs: list[str] = []
        where = f"artefact_types.{key}"
        if not isinstance(d, dict):
            return None, [f"{where} must be a mapping"]
        raw_prefix = d.get("prefix")
        prefixes = raw_prefix if isinstance(raw_prefix, list) else [raw_prefix]
        if not prefixes or not all(isinstance(x, str) and _PREFIX.match(x) for x in prefixes):
            errs.append(f"{where}.prefix must be upper-case letters and digits (segments joined by '-'), "
                        f"or a list of them")
        prefixes = [x for x in prefixes if isinstance(x, str)]
        prefix = prefixes[0] if prefixes else ""
        fields: dict[str, FieldSpec] = {}
        for fname, spec in (d.get("fields") or {}).items():
            if fname in ALWAYS:
                errs.append(f"{where}.fields.{fname}: {fname} is always present; do not declare it")
                continue
            try:
                fields[str(fname)] = FieldSpec.parse(str(fname), spec)
            except ValueError as e:
                errs.append(f"{where}.{e}")
        status = d.get("status")
        if not isinstance(status, dict) or not status:
            errs.append(f"{where}.status must map each status value to a chip")
            status = {}
        status = {display(k).lower(): str(v) for k, v in status.items()}
        for k, v in status.items():
            if v not in CHIPS:
                errs.append(f"{where}.status.{k}: chip '{v}' is not one of {', '.join(CHIPS)}")
        columns = d.get("columns") or ["id", "title", "status"]
        known = set(ALWAYS) | set(fields)
        for c in columns:
            if c not in known:
                errs.append(f"{where}.columns: '{c}' is not a field of {key}")
        labels = {str(k): str(v) for k, v in (d.get("labels") or {}).items()}
        for k in labels:
            if k not in known:
                errs.append(f"{where}.labels: '{k}' is not a field of {key}")
        label = d.get("label") or key.replace("-", " ").capitalize()
        vlabels_raw = d.get("value_labels") or {}
        if not isinstance(vlabels_raw, dict):
            errs.append(f"{where}.value_labels must map values to labels")
            vlabels_raw = {}
        vlabels = {display(k).lower(): str(v) for k, v in vlabels_raw.items()}
        values = set(status) | {v for f in fields.values() for v in f.enum}
        for k in vlabels:
            if k not in values:
                errs.append(f"{where}.value_labels: '{k}' is not an enum or status value of {key}")
        if errs:
            return None, errs
        plural = str(d.get("plural") or "")
        return cls(key, prefix, label, fields, list(columns), status, labels, plural, tuple(prefixes), vlabels), []

    def matches_id(self, rid: str) -> bool:
        """Whether an id fits this type: one of its prefixes as whole
        segments, optionally after a namespace (``NW-SEC-RISK-03`` fits
        ``RISK``), followed by at least one segment (``-03``, ``-CRM``)."""
        segs = rid.split("-")
        if not all(segs):
            return False
        for prefix in sorted(self.prefixes, key=lambda x: -x.count("-")):
            ps = prefix.split("-")
            for i in range(0, len(segs) - len(ps)):
                if segs[i:i + len(ps)] == ps and all(_NAMESPACE.match(n) for n in segs[:i]) \
                        and all(_SEGMENT.match(x) for x in segs[i + len(ps):]):
                    return True
        return False

    def value_label(self, field_name: str, value: Any) -> str:
        """The display label of an enum or status value; any other value as
        text."""
        if isinstance(value, Tbc):
            return str(value)
        text = display(value)
        if field_name == "status":
            known = text.lower() in self.status
        else:
            spec = self.fields.get(field_name)
            known = spec is not None and spec.kind == "enum" and text.lower() in spec.enum
        if not known:
            return text
        return self.value_labels.get(text.lower()) or label_value(text)

    @property
    def has_owner(self) -> bool:
        return "owner" in self.fields

    def header(self, column: str) -> str:
        if column in self.labels:
            return self.labels[column]
        if column == "id":
            return "ID"
        if column == "title":
            return self.label
        return column.replace("_", " ").capitalize()

    def chip(self, status: Any) -> str:
        if parse_tbc(status) is not None:
            return "tbc"
        return self.status.get(display(status).lower(), "tbc")

    def check_where(self, where: Where) -> list[str]:
        """Problems with a filter against this schema."""
        errs = []
        for c in where.conditions:
            if c.field in ("id", "title"):
                continue
            if c.field == "status":
                allowed = set(self.status) | {"tbc"}
            elif c.field in self.fields:
                spec = self.fields[c.field]
                if spec.kind != "enum":
                    continue
                allowed = set(spec.enum) | {"tbc"}
            else:
                errs.append(f"'{c.field}' is not a field of {self.key}")
                continue
            for v in c.values:
                if v not in allowed:
                    errs.append(f"'{v}' is not a value of {self.key}.{c.field} ({', '.join(sorted(allowed))})")
        return errs


# --------------------------------------------------------------- records

@dataclass
class Record:
    """One register record. ``data`` holds normalised values: dates as ISO
    strings, yes/no enums as strings, TBCs as :class:`Tbc`."""

    type: ArtefactType
    data: dict[str, Any]
    source: Source
    resolved: dict[str, str] = field(default_factory=dict)   # field -> text with placeholders filled

    @property
    def id(self) -> str:
        return display(self.data.get("id"))

    @property
    def title(self) -> str:
        return display(self.data.get("title"))

    @property
    def status(self) -> Any:
        return self.data.get("status")

    @property
    def chip(self) -> str:
        return self.type.chip(self.status)

    @property
    def owner(self) -> str | None:
        """The record's owner as text, or None when absent or itself an
        unowned TBC."""
        o = self.data.get("owner")
        if o is None:
            return None
        t = parse_tbc(o)
        if t is not None:
            return None
        s = display(o).strip()
        return s or None

    @property
    def accountable(self) -> str | None:
        """Who a bare TBC in this record falls to: the owner, or, when the
        owner is itself ``TBC: <who>``, the person confirming it."""
        if self.owner:
            return self.owner
        t = parse_tbc(self.data.get("owner"))
        return t.owner if t is not None else None

    def get(self, field_name: str, default: Any = None) -> Any:
        v = self.data.get(field_name, default)
        t = v if isinstance(v, Tbc) else None
        if t is not None and t.owner is None and field_name != "owner" and self.accountable:
            return Tbc(self.accountable, inherited=True)
        return v

    def display(self, field_name: str) -> str:
        """The stored value as text (placeholders as written, a bare TBC
        with its inherited owner)."""
        return display(self.get(field_name))

    def text(self, field_name: str) -> str:
        """The value with placeholders resolved (once the project has
        resolved it), otherwise as :meth:`display`. Enum values stay as
        stored, for use in prose."""
        v = self.get(field_name)
        if isinstance(v, Tbc):
            return str(v)
        return self.resolved.get(field_name, display(v))

    def shown(self, field_name: str) -> str:
        """The value as a reader sees it in a table: placeholders resolved,
        enum and status values labelled ("Must", "In build"), a TBC in full."""
        v = self.get(field_name)
        if isinstance(v, Tbc):
            return str(v)
        if field_name not in self.resolved and (field_name == "status" or (
                field_name in self.type.fields and self.type.fields[field_name].kind == "enum")):
            return self.type.value_label(field_name, v)
        return self.text(field_name)

    def cells(self, columns: list[str], short: bool = True) -> list[str]:
        """A table row of :meth:`shown` values. With ``short``, a TBC owned
        by the record's accountable owner reads "TBC" when the row shows the
        owner column or has already said "TBC: <owner>" once, so the owner
        is named once per row; the cell's owner is then ``accountable``."""
        who = self.accountable
        named = "owner" in columns and who is not None
        out = []
        for c in columns:
            v = self.get(c)
            if short and isinstance(v, Tbc) and c != "owner" and v.owner and v.owner == who:
                out.append("TBC" if named else str(v))
                named = True
            else:
                out.append(self.shown(c))
        return out

    def row(self, columns: list[str]) -> list[str]:
        """The stored values of ``columns`` (see :meth:`cells` for display)."""
        return [self.display(c) for c in columns]

    def tbcs(self) -> list[tuple[str, Tbc]]:
        """Each field whose whole value is a TBC, with its owner (a bare TBC
        takes the record's accountable owner). One per field."""
        out = []
        for k in self.data:
            v = self.get(k)
            if isinstance(v, Tbc):
                out.append((k, v))
        return out

    def embedded_tbcs(self) -> list[tuple[str, Tbc]]:
        """Each field with a TBC inside a longer value ("Queue and back off;
        TBC: Cloud Platform"), once per field: by its unowned TBC if it has
        one, else its first. A bare one takes the record's accountable owner
        (``inherited``)."""
        out = []
        who = self.accountable
        for k, raw in self.data.items():
            if k == "id" or isinstance(raw, Tbc):
                continue
            found: list[Tbc] = []
            for s in (raw if isinstance(raw, list) else [raw]):
                if isinstance(s, Tbc):
                    found.append(s if s.owner or not who else Tbc(who, inherited=True))
                elif isinstance(s, str):
                    found += [t if t.owner or not who else Tbc(who, inherited=True) for t in embedded_tbcs(s)]
            if found:
                out.append((k, next((t for t in found if t.owner is None), found[0])))
        return out

    def all_tbcs(self) -> list[tuple[str, Tbc]]:
        """:meth:`tbcs` and :meth:`embedded_tbcs` together, one per field."""
        return self.tbcs() + self.embedded_tbcs()


def _normalise_value(spec: FieldSpec | None, value: Any) -> Any:
    t = parse_tbc(value)
    if t is not None:
        return t
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, bool) and spec is not None and spec.kind == "enum":
        return "yes" if value else "no"
    if spec is not None and spec.kind in ("list", "refs") and isinstance(value, list):
        return [_normalise_value(None, v) for v in value]
    return value


class Register:
    """All records of one type, in file order."""

    def __init__(self, rtype: ArtefactType, records: list[Record] | None = None,
                 path: Path | None = None, problems: list[Problem] | None = None):
        self.type = rtype
        self.records = records or []
        self.path = path
        self.problems = problems or []

    def __iter__(self) -> Iterator[Record]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, i: int) -> Record:
        return self.records[i]

    def get(self, rid: str) -> Record | None:
        for r in self.records:
            if r.id == rid:
                return r
        return None

    def filter(self, where: Where | str | None = None) -> list[Record]:
        if where is None:
            return list(self.records)
        if isinstance(where, str):
            where = parse_conditions(split_args(where))
        return [r for r in self.records if where.matches(r)]

    @classmethod
    def load(cls, rtype: ArtefactType, path: Path, display_path: str | None = None) -> "Register":
        """Read ``path`` (a YAML list of records) and validate each record.
        A missing file is an empty register."""
        shown = display_path or str(path)
        if not path.exists():
            return cls(rtype, [], path, [])
        text = path.read_text()
        problems: list[Problem] = []
        try:
            node = yaml.compose(text)
            raw = yaml.safe_load(text)
        except yaml.YAMLError as e:
            line = getattr(getattr(e, "problem_mark", None), "line", None)
            return cls(rtype, [], path, [Problem("schema", f"YAML error: {e}",
                                                 Source(shown, line + 1 if line is not None else None))])
        if raw is None:
            return cls(rtype, [], path, [])
        if not isinstance(raw, list):
            return cls(rtype, [], path, [Problem("schema", "a register file must be a list of records",
                                                 Source(shown, 1))])
        lines = [n.start_mark.line + 1 for n in node.value] if isinstance(node, yaml.SequenceNode) else []
        records = []
        for i, item in enumerate(raw):
            src = Source(shown, lines[i] if i < len(lines) else None)
            if not isinstance(item, dict):
                problems.append(Problem("schema", "a record must be a mapping", src))
                continue
            data = {str(k): _normalise_value(rtype.fields.get(str(k)), v) for k, v in item.items()}
            rec = Record(rtype, data, src)
            problems.extend(validate_record(rec))
            records.append(rec)
        seen: dict[str, Source] = {}
        for r in records:
            if r.id in seen:
                problems.append(Problem("ids", f"duplicate id {r.id} (first at {seen[r.id]})", r.source))
            else:
                seen[r.id] = r.source
        return cls(rtype, records, path, problems)


def validate_record(rec: Record) -> list[Problem]:
    """Schema problems with one record (unknown references are checked at
    project level, where every register is known)."""
    t = rec.type
    out: list[Problem] = []
    src = rec.source
    for k in ALWAYS:
        if rec.data.get(k) in (None, ""):
            out.append(Problem("schema", f"{t.key} record is missing '{k}'", src))
    rid = rec.data.get("id")
    if rid not in (None, "") and not t.matches_id(display(rid)):
        expected = " or ".join(f"{p}-" for p in t.prefixes)
        out.append(Problem("ids", f"id '{display(rid)}' does not match the {t.key} prefix {expected}", src))
    st = rec.data.get("status")
    if st not in (None, "") and not isinstance(st, Tbc) and display(st).lower() not in t.status:
        out.append(Problem("schema", f"{rec.id}: status '{display(st)}' is not one of {', '.join(t.status)}", src))
    for k, v in rec.data.items():
        if k in ALWAYS:
            continue
        spec = t.fields.get(k)
        if spec is None:
            out.append(Problem("schema", f"{rec.id}: '{k}' is not a field of {t.key}", src))
            continue
        if isinstance(v, Tbc) or v is None:
            continue
        if spec.kind == "enum" and display(v).lower() not in spec.enum:
            out.append(Problem("schema", f"{rec.id}: {k} '{display(v)}' is not one of {', '.join(spec.enum)}", src))
        elif spec.kind == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
            out.append(Problem("schema", f"{rec.id}: {k} must be a number", src))
        elif spec.kind == "date" and not re.match(r"^\d{4}-\d{2}-\d{2}", display(v)):
            out.append(Problem("schema", f"{rec.id}: {k} '{display(v)}' is not a YYYY-MM-DD date", src))
        elif spec.kind in ("list", "refs") and not isinstance(v, list):
            if not isinstance(v, str):
                out.append(Problem("schema", f"{rec.id}: {k} must be a list", src))
    for k, tbc in rec.tbcs():
        if tbc.owner is None:
            out.append(Problem("tbc-owner", f"{rec.id}.{k} is TBC with no owner (give 'TBC: <owner>' or an owner field)", src))
    for k, tbc in rec.embedded_tbcs():
        if tbc.owner is None:
            out.append(Problem("tbc-owner", f"{rec.id}.{k} has a TBC with no owner, and the record has none to "
                               f"fall back on; write 'TBC: <owner>'", src))
    return out


def as_list(value: Any) -> list[Any]:
    """A refs/list value as a list (a single string becomes one item; a
    comma-separated string is split)."""
    if value is None or isinstance(value, Tbc):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [value]


def id_list(ids: list[str]) -> str:
    """'RSK-01 to RSK-07' for a contiguous run of three or more ids with one
    prefix, otherwise 'RSK-01, RSK-03 and RSK-05'. Empty is 'none'."""
    if not ids:
        return "none"
    parsed = []
    for i in ids:
        m = re.match(r"^(.*?)(\d+)$", i)
        parsed.append((m.group(1), int(m.group(2)), len(m.group(2))) if m else None)
    if len(ids) >= 3 and all(parsed) and len({p[0] for p in parsed}) == 1:
        nums = [p[1] for p in parsed]
        if nums == list(range(nums[0], nums[0] + len(nums))):
            return f"{ids[0]} to {ids[-1]}"
    if len(ids) == 1:
        return ids[0]
    return ", ".join(ids[:-1]) + f" and {ids[-1]}"
