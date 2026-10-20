"""The metamodel: chapters, sections, artefact types and viewpoints.

:func:`load_metamodel` reads and validates a metamodel YAML (``seed`` names
the bundled default). :meth:`Metamodel.apply` applies a profile and a
document kind, giving the :class:`EffectiveModel`: the chapters and sections
this document carries, with ``when:`` resolved, ``{p:...}`` filled in titles
and guidance, and ``guidance_by`` variants selected. Numbering is not done
here; the project numbers chapters and sections after filtering and after
adding ``[new]`` sections from the content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .profile import Profile
from .registers import ArtefactType, Where, display, parse_selector

PICTURE_KINDS = ("layers", "timeline", "traceability", "heatmap", "matrix",
                 "swimlane", "flow", "bars", "map")
EA_NAMES = ("coreea", "archimate", "togaf", "essential")
DECK_RUNS = (1, 2, 3, 4)
KEY_RE = re.compile(r"^[a-z][a-z0-9-]*$")
P_PLACEHOLDER = re.compile(r"\{p:([A-Za-z0-9_.-]+)\}")

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "metamodels"


class MetamodelError(ValueError):
    """Raised when a metamodel fails validation or a profile cannot be
    applied to it."""

    def __init__(self, errors: list[str], path: Path | None = None):
        self.errors = errors
        self.path = path
        where = f"{path}: " if path else ""
        super().__init__(where + "; ".join(errors))


# ------------------------------------------------------------- conditions

def check_when(expr: Any, where: str) -> list[str]:
    """Problems with the shape of a ``when:`` expression."""
    if isinstance(expr, str):
        return [] if re.match(r"^[A-Za-z0-9_.-]+$", expr) else [f"{where}: bad when path '{expr}'"]
    if isinstance(expr, dict):
        errs = []
        for k, v in expr.items():
            if k in ("all", "any"):
                if not isinstance(v, list) or not v:
                    errs.append(f"{where}: '{k}' takes a non-empty list")
                else:
                    for i, sub in enumerate(v):
                        errs += check_when(sub, f"{where}.{k}[{i}]")
            elif k == "not":
                errs += check_when(v, f"{where}.not")
            elif not re.match(r"^[A-Za-z0-9_.-]+$", str(k)):
                errs.append(f"{where}: bad when path '{k}'")
        return errs
    return [f"{where}: when must be a path or a mapping"]


def evaluate_when(expr: Any, profile: Profile) -> bool:
    """Whether a ``when:`` expression holds for the profile.

    - ``"systems.itsm"``: the value is set and not a "none" value;
    - ``{path: value}`` / ``{path: [a, b]}``: equality (case-insensitive);
    - ``{not: e}``, ``{all: [...]}``, ``{any: [...]}``.
    Several keys in one mapping must all hold.
    """
    if expr is None:
        return True
    if isinstance(expr, str):
        return profile.is_set(expr)
    if isinstance(expr, dict):
        for k, v in expr.items():
            if k == "all":
                ok = all(evaluate_when(e, profile) for e in v)
            elif k == "any":
                ok = any(evaluate_when(e, profile) for e in v)
            elif k == "not":
                ok = not evaluate_when(v, profile)
            else:
                actual = profile.text(k)
                wanted = v if isinstance(v, list) else [v]
                ok = actual is not None and actual.lower() in {display(w).lower() for w in wanted}
            if not ok:
                return False
        return True
    raise MetamodelError([f"bad when expression: {expr!r}"])


def fill_profile(text: str | None, profile: Profile, where: str, strict: bool = True,
                 logical: bool = False) -> str | None:
    """Replace ``{p:path}`` with profile values (logical names when
    ``logical``). Other placeholders are left for the content resolver.
    Raises when ``strict`` and a path is unset."""
    if text is None:
        return None

    def sub(m: re.Match) -> str:
        path = m.group(1)
        if not profile.is_set(path) or profile.text(path) is None:
            if strict:
                raise MetamodelError([f"{where}: profile value '{path}' is not set"])
            return f"[{path} is not set in the profile]"
        return profile.text(path, logical=logical)
    return P_PLACEHOLDER.sub(sub, text)


# --------------------------------------------------------- effective model

@dataclass(frozen=True)
class ArtefactRef:
    """A section's register: a type and an optional filter."""

    type: str
    where: Where = Where()

    def __str__(self) -> str:
        return f"{self.type} where {self.where}" if self.where else self.type


@dataclass
class EffectiveSection:
    """A section the document carries. ``labels`` maps a register field to
    the column header this section's tables use (from the section's
    ``labels:``, or the inverse of an extracted ``column_map``);
    ``template_columns`` are the organisation template's table headers, as
    ``archdoc extract`` recorded them."""

    key: str
    title: str
    guidance: str
    artefacts: list[ArtefactRef]
    optional: bool = False
    labels: dict[str, str] = field(default_factory=dict)
    template_columns: list[list[str]] = field(default_factory=list)


@dataclass
class EffectiveChapter:
    key: str
    title: str
    question: str
    story: str
    picture: dict
    deck: dict
    viewpoints: list[str]
    sections: list[EffectiveSection]

    def section(self, key: str) -> EffectiveSection | None:
        for s in self.sections:
            if s.key == key:
                return s
        return None


@dataclass
class Viewpoint:
    key: str
    title: str
    purpose: str
    ea: dict[str, str | None]

    def name_for(self, metamodel: str | None) -> str | None:
        """This viewpoint's name in an EA metamodel, or None."""
        return self.ea.get(metamodel) if metamodel else None


@dataclass
class EffectiveModel:
    """The chapters and sections one document carries, after the profile and
    the document kind are applied. Unnumbered."""

    metamodel: "Metamodel"
    kind: str
    chapters: list[EffectiveChapter]
    artefact_types: dict[str, ArtefactType]
    viewpoints: dict[str, Viewpoint]
    runs: dict[int, str]

    def chapter(self, key: str) -> EffectiveChapter | None:
        for c in self.chapters:
            if c.key == key:
                return c
        return None

    def used_types(self) -> list[str]:
        """Artefact types any effective section draws on, in first-use order."""
        out: list[str] = []
        for c in self.chapters:
            for s in c.sections:
                for a in s.artefacts:
                    if a.type not in out:
                        out.append(a.type)
        return out


# --------------------------------------------------------------- metamodel

@dataclass
class Metamodel:
    name: str
    version: Any
    document_kinds: dict[str, dict]
    chapters: list[dict]
    artefact_types: dict[str, ArtefactType]
    viewpoints: dict[str, Viewpoint]
    runs: dict[int, str]
    path: Path | None = None
    raw: dict = field(default_factory=dict)

    def apply(self, profile: Profile, kind: str, layer: str | None = None,
              exclude: list[str] | None = None) -> EffectiveModel:
        """Resolve ``when:``, fill titles and guidance from the profile, pick
        ``guidance_by`` variants, and drop what the document kind excludes
        and what ``exclude`` names (``chapter`` or ``chapter/section`` keys,
        from arch-doc.yaml). With ``layer="logical"``, system names are
        filled with their ``logical_name`` where the profile gives one."""
        lg = layer == "logical"
        if kind not in self.document_kinds:
            raise MetamodelError([f"document kind '{kind}' is not one of {', '.join(self.document_kinds)}"], self.path)
        excludes = set(self.document_kinds[kind].get("excludes") or []) | set(exclude or [])
        slugs = profile.system_slugs()
        chapters = []
        for ch in self.chapters:
            if ch["key"] in excludes or not evaluate_when(ch.get("when"), profile):
                continue
            where = f"chapters.{ch['key']}"
            sections = []
            for s in ch.get("sections") or []:
                skey = f"{ch['key']}/{s['key']}"
                if skey in excludes or not evaluate_when(s.get("when"), profile):
                    continue
                guidance = s.get("guidance") or ""
                variants = s.get("guidance_by") or {}
                if variants:
                    on = s.get("guidance_on")
                    names = [slugs[on]] if on and on in slugs else ([] if on else list(slugs.values()))
                    for n in names:
                        if n in variants:
                            guidance = variants[n]
                            break
                sections.append(EffectiveSection(
                    key=s["key"],
                    title=fill_profile(s["title"], profile, f"{where}.{s['key']}.title", logical=lg),
                    guidance=" ".join(fill_profile(guidance, profile, f"{where}.{s['key']}.guidance",
                                                   strict=False, logical=lg).split()),
                    artefacts=[_artefact_ref(a) for a in s.get("artefacts") or []],
                    optional=bool(s.get("optional", False)),
                    labels=section_labels(s),
                    template_columns=[list(h) for h in s.get("template_columns") or []],
                ))
            chapters.append(EffectiveChapter(
                key=ch["key"],
                title=fill_profile(ch["title"], profile, f"{where}.title", logical=lg),
                question=fill_profile(ch.get("question") or "", profile, f"{where}.question"),
                story=fill_profile(ch.get("story") or "", profile, f"{where}.story"),
                picture=dict(ch.get("picture") or {}),
                deck={"run": ch.get("deck", {}).get("run"), "min_slides": ch.get("deck", {}).get("min_slides", 3)},
                viewpoints=list(ch.get("viewpoints") or []),
                sections=sections,
            ))
        return EffectiveModel(self, kind, chapters, self.artefact_types, self.viewpoints, self.runs)

    def chapter(self, key: str) -> dict | None:
        for c in self.chapters:
            if c["key"] == key:
                return c
        return None

    def keys(self) -> set[str]:
        """Every chapter key and chapter/section key."""
        out = set()
        for c in self.chapters:
            out.add(c["key"])
            out |= {f"{c['key']}/{s['key']}" for s in c.get("sections") or []}
        return out


def section_labels(s: dict) -> dict[str, str]:
    """Field -> header label for a section: an extracted ``column_map``
    (template header -> field) inverted, overridden by explicit ``labels``
    (field -> header)."""
    out: dict[str, str] = {}
    for header, fname in (s.get("column_map") or {}).items():
        out.setdefault(str(fname), str(header))
    out.update({str(k): str(v) for k, v in (s.get("labels") or {}).items()})
    return out


def _artefact_ref(entry: str) -> ArtefactRef:
    t, w = parse_selector(entry)
    return ArtefactRef(t, w)


def validate(data: Any) -> list[str]:
    """Every structural problem with a metamodel mapping."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["metamodel must be a mapping"]
    for k in ("name", "chapters", "artefact_types"):
        if k not in data:
            errs.append(f"missing '{k}'")
    if errs:
        return errs
    types: dict[str, ArtefactType] = {}
    # a type that fails is reported once; what refers to it is not reported again
    broken: set[str] = set()
    for key, td in (data.get("artefact_types") or {}).items():
        if not KEY_RE.match(str(key)):
            errs.append(f"artefact_types: bad key '{key}'")
        t, terrs = ArtefactType.from_dict(str(key), td)
        errs += terrs
        if t:
            types[key] = t
        else:
            broken.add(str(key))
    prefixes: dict[str, str] = {}
    for t in types.values():
        for px in t.prefixes:
            if px in prefixes:
                errs.append(f"artefact_types.{t.key}: prefix {px} is also used by {prefixes[px]}")
            prefixes[px] = t.key
        for f in t.fields.values():
            if f.ref_type and f.ref_type not in types and f.ref_type not in (data.get("artefact_types") or {}):
                errs.append(f"artefact_types.{t.key}.fields.{f.name}: unknown type '{f.ref_type}'")
    viewpoints = data.get("viewpoints") or {}
    for vk, v in viewpoints.items():
        if not isinstance(v, dict) or not v.get("title"):
            errs.append(f"viewpoints.{vk}: needs a title")
            continue
        for ea in (v.get("ea") or {}):
            if ea not in EA_NAMES:
                errs.append(f"viewpoints.{vk}.ea: '{ea}' is not one of {', '.join(EA_NAMES)}")
    runs = (data.get("deck") or {}).get("runs") or {}
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return errs + ["chapters must be a non-empty list"]
    seen_ch: set[str] = set()
    all_keys: set[str] = set()
    for i, ch in enumerate(chapters):
        where = f"chapters[{i}]"
        if not isinstance(ch, dict):
            errs.append(f"{where} must be a mapping")
            continue
        ck = ch.get("key")
        if not isinstance(ck, str) or not KEY_RE.match(ck):
            errs.append(f"{where}: bad key '{ck}'")
            continue
        where = f"chapters.{ck}"
        if ck in seen_ch:
            errs.append(f"{where}: duplicate chapter key")
        seen_ch.add(ck)
        all_keys.add(ck)
        if not ch.get("title"):
            errs.append(f"{where}: missing title")
        if "when" in ch:
            errs += check_when(ch["when"], f"{where}.when")
        pic = ch.get("picture")
        if not isinstance(pic, dict) or pic.get("kind") not in PICTURE_KINDS:
            errs.append(f"{where}.picture: kind must be one of {', '.join(PICTURE_KINDS)}")
        else:
            src = pic.get("from")
            if src not in (None, "depends_on", "registers") and src not in types and src not in broken:
                errs.append(f"{where}.picture.from: '{src}' is not a register type, depends_on or registers")
            by = pic.get("by")
            if by and src in types and by not in types[src].fields and by != "status":
                errs.append(f"{where}.picture.by: '{by}' is not a field of {src}")
        deck = ch.get("deck") or {}
        if deck.get("run") not in DECK_RUNS:
            errs.append(f"{where}.deck.run must be one of 1-4")
        elif runs and deck["run"] not in runs:
            errs.append(f"{where}.deck.run {deck['run']} has no title in deck.runs")
        if "min_slides" in deck and deck["min_slides"] not in (2, 3):
            errs.append(f"{where}.deck.min_slides must be 2 or 3")
        for vp in ch.get("viewpoints") or []:
            if vp not in viewpoints:
                errs.append(f"{where}.viewpoints: unknown viewpoint '{vp}'")
        seen_s: set[str] = set()
        for j, s in enumerate(ch.get("sections") or []):
            sw = f"{where}.sections[{j}]"
            if not isinstance(s, dict):
                errs.append(f"{sw} must be a mapping")
                continue
            sk = s.get("key")
            if not isinstance(sk, str) or not KEY_RE.match(sk):
                errs.append(f"{sw}: bad key '{sk}'")
                continue
            sw = f"{where}.{sk}"
            if sk in seen_s:
                errs.append(f"{sw}: duplicate section key")
            seen_s.add(sk)
            all_keys.add(f"{ck}/{sk}")
            if not s.get("title"):
                errs.append(f"{sw}: missing title")
            if not s.get("guidance"):
                errs.append(f"{sw}: missing guidance")
            if "when" in s:
                errs += check_when(s["when"], f"{sw}.when")
            gb = s.get("guidance_by")
            if gb is not None and (not isinstance(gb, dict) or not all(isinstance(v, str) for v in gb.values())):
                errs.append(f"{sw}.guidance_by must map system slugs to text")
            for lk in ("labels", "column_map"):
                lv = s.get(lk)
                if lv is not None and not isinstance(lv, dict):
                    errs.append(f"{sw}.{lk} must be a mapping")
            sec_types = []
            for a in s.get("artefacts") or [] if isinstance(s.get("artefacts"), list) else []:
                try:
                    sec_types.append(parse_selector(str(a))[0])
                except ValueError:
                    pass
            if isinstance(s.get("artefacts"), list) and not broken & set(sec_types):
                sec_fields = {"id", "title", "status"}
                for a in s["artefacts"]:
                    try:
                        st = parse_selector(str(a))[0]
                    except ValueError:
                        continue
                    if st in types:
                        sec_fields |= set(types[st].fields)
                for k in (s.get("labels") or {}) if isinstance(s.get("labels"), dict) else []:
                    if k not in sec_fields:
                        errs.append(f"{sw}.labels: '{k}' is not a field of this section's registers")
                cmap = s.get("column_map") if isinstance(s.get("column_map"), dict) else {}
                for h, v in cmap.items():
                    if v not in sec_fields:
                        errs.append(f"{sw}.column_map: '{h}' maps to '{v}', not a field of this section's registers")
            if "artefacts" not in s or not isinstance(s.get("artefacts"), list):
                errs.append(f"{sw}: artefacts must be a list (use [] for none)")
                continue
            for a in s["artefacts"]:
                try:
                    t, w = parse_selector(str(a))
                except ValueError as e:
                    errs.append(f"{sw}.artefacts: {e}")
                    continue
                if t in broken:
                    continue
                if t not in types:
                    errs.append(f"{sw}.artefacts: unknown type '{t}'")
                else:
                    errs += [f"{sw}.artefacts: {e}" for e in types[t].check_where(w)]
    kinds = data.get("document_kinds") or {}
    if not kinds:
        errs.append("document_kinds must name at least one kind")
    for kk, kd in kinds.items():
        for ex in (kd or {}).get("excludes") or []:
            if ex not in all_keys:
                errs.append(f"document_kinds.{kk}.excludes: '{ex}' is not a chapter or chapter/section key")
    return errs


_VALUE_LABEL_ERR = re.compile(r"^artefact_types\.([\w-]+)\.value_labels: '([^']+)' is not an enum or status value")


def _value_label_hint(err: str, data: dict) -> str:
    """For an extracted metamodel, say where a stray value label came from:
    archdoc extract copies the seed's value_labels, and a field changed from
    an enum to text leaves its labels behind."""
    m = _VALUE_LABEL_ERR.match(err)
    if not m or not isinstance(data, dict) or not data.get("extracted_from"):
        return err
    key, value = m.group(1), m.group(2)
    fields = ((data.get("artefact_types") or {}).get(key) or {}).get("fields") or {}
    origin = None
    try:
        seed = load_metamodel("seed").raw["artefact_types"].get(key) or {}
        origin = next((f for f, spec in (seed.get("fields") or {}).items()
                       if isinstance(spec, list) and value in {display(v).lower() for v in spec}), None)
    except MetamodelError:
        pass
    if origin and not isinstance(fields.get(origin), list):
        return (f"{err} (archdoc extract copied the seed's value_labels for {key}; {key}.{origin} is no "
                f"longer an enum here, so remove '{value}' from artefact_types.{key}.value_labels or make "
                f"{origin} an enum again)")
    return (f"{err} (archdoc extract copied the seed's value_labels for {key}; remove '{value}' from "
            f"artefact_types.{key}.value_labels or add it back to the field's values)")


def from_dict(data: Any, path: Path | None = None) -> Metamodel:
    errs = validate(data)
    if errs:
        raise MetamodelError([_value_label_hint(e, data) for e in errs], path)
    types = {}
    for key, td in data["artefact_types"].items():
        t, _ = ArtefactType.from_dict(key, td)
        types[key] = t
    vps = {k: Viewpoint(k, v["title"], v.get("purpose", ""), dict(v.get("ea") or {}))
           for k, v in (data.get("viewpoints") or {}).items()}
    runs = {int(k): str(v) for k, v in ((data.get("deck") or {}).get("runs") or {}).items()}
    return Metamodel(
        name=data["name"], version=data.get("version"),
        document_kinds={k: dict(v or {}) for k, v in data["document_kinds"].items()},
        chapters=data["chapters"], artefact_types=types, viewpoints=vps, runs=runs,
        path=path, raw=data)


def resolve_path(name_or_path: str, base: Path | None = None) -> Path:
    """``seed`` (or any bare name of a bundled metamodel) to its file;
    anything else is a path relative to ``base``."""
    p = Path(name_or_path)
    if p.suffix not in (".yaml", ".yml") and "/" not in name_or_path:
        bundled = SEED_DIR / f"{name_or_path}.yaml"
        if bundled.exists():
            return bundled
    if not p.is_absolute() and base is not None:
        p = base / p
    return p


def load_metamodel(name_or_path: str = "seed", base: Path | None = None) -> Metamodel:
    """Load and validate a metamodel by bundled name or path."""
    p = resolve_path(name_or_path, base)
    if not p.exists():
        raise MetamodelError([f"metamodel not found: {name_or_path}"], p)
    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        raise MetamodelError([f"YAML error: {e}"], p) from e
    return from_dict(data, p)
