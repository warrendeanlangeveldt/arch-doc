"""The organisation profile: systems, forums, roles, house style, template.

A profile describes the organisation, not the document, so many projects can
share one. :func:`load_profile` reads it, fills defaults (a neutral house
palette and fonts, generic forum names, template style names) and validates
it. :class:`Profile` answers dotted-path lookups such as
``systems.itsm.name`` and decides whether a path is "set" for the metamodel's
``when:`` conditions.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

EA_METAMODELS = ("coreea", "archimate", "togaf", "essential", "none")
ITSM_FRAMEWORKS = ("itil", "none", "other")
CLOUDS = ("azure", "aws", "gcp", "on-prem")
NAMED_SYSTEMS = ("itsm", "ea_repository", "identity", "cicd", "monitoring", "source_control")
TOP_LEVEL = ("org", "systems", "forums", "roles", "house", "template")

DEFAULTS: dict[str, Any] = {
    "org": {"name": None, "short": None},
    "systems": {
        "itsm": {"name": "none"},
        "ea_repository": {"name": "none"},
        "ea_metamodel": "none",
        "cloud": [],
        "identity": {"name": "none"},
        "cicd": {"name": "none"},
        "monitoring": {"name": "none"},
        "source_control": {"name": "none"},
    },
    "forums": {
        "design_authority": {"name": "Architecture Review Board", "short": "ARB"},
        "change": {"name": "Change Advisory Board", "short": "CAB"},
        "security": {"name": "Security Review", "short": "SR"},
    },
    "roles": {"architect": "Solution Architect", "service_owner": "Service Owner"},
    "house": {
        "palette": {
            "ink": "#1F2328",
            "muted": "#5B636B",
            "paper": "#FFFFFF",
            "panel": "#F3F4F5",
            "rule": "#D0D4D8",
            "accent": "#3A5A78",
            "accent_soft": "#E2E9F0",
            "done": "#2E7D4F",
            "partial": "#A86A12",
            "not_started": "#7A828A",
            "tbc": "#A8382B",
        },
        "fonts": {"heading": "Source Serif 4", "body": "IBM Plex Sans", "mono": "IBM Plex Mono"},
    },
    "template": {
        "path": None,
        "styles": {
            "h1": "Heading 1",
            "h2": "Heading 2",
            "body": "Normal",
            "bullet": "List Paragraph",
            "table": "Table Grid",
            "caption": "Caption",
        },
    },
}

# Defaults that only apply once an ITSM is named.
ITSM_DEFAULTS = {
    "framework": "none",
    "has_cmdb": False,
    "category_title": "Service Management & Configuration Records",
}

_MISSING = object()
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ProfileError(ValueError):
    """Raised when a profile cannot be loaded or fails validation."""

    def __init__(self, errors: list[str], path: Path | None = None):
        self.errors = errors
        self.path = path
        where = f"{path}: " if path else ""
        super().__init__(where + "; ".join(errors))


def slug(text: Any) -> str:
    """Lower-case, hyphenated form of a system name: 'Jira Service Management'
    becomes 'jira-service-management'."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def is_none(value: Any) -> bool:
    """True for the values a profile uses to say "we have none"."""
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("", "none", "null", "n/a")
    if isinstance(value, dict):
        if not value:
            return True
        if "name" in value:
            return is_none(value["name"])
        return False
    if isinstance(value, (list, tuple)):
        return not value or all(is_none(v) for v in value)
    return False


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _normalise(data: dict) -> dict:
    systems = data.setdefault("systems", {})
    for key in NAMED_SYSTEMS:
        v = systems.get(key)
        if v is None or isinstance(v, str):
            systems[key] = {"name": v if v is not None else "none"}
    cloud = systems.get("cloud")
    if isinstance(cloud, str):
        systems["cloud"] = [] if is_none(cloud) else [cloud]
    elif cloud is None:
        systems["cloud"] = []
    if systems.get("ea_metamodel") is None:
        systems["ea_metamodel"] = "none"
    itsm = systems["itsm"]
    if not is_none(itsm):
        for k, v in ITSM_DEFAULTS.items():
            itsm.setdefault(k, v)
        itsm.setdefault("cmdb_title", f"{itsm['name']} Configuration Records")
    return data


def validate(data: dict) -> list[str]:
    """Every problem with a merged, normalised profile, as messages."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["profile must be a mapping"]
    for k in data:
        if k not in TOP_LEVEL:
            errors.append(f"unknown top-level key '{k}' (expected one of {', '.join(TOP_LEVEL)})")
    systems = data.get("systems", {})
    if not isinstance(systems, dict):
        return errors + ["systems must be a mapping"]
    for key in NAMED_SYSTEMS:
        v = systems.get(key)
        if not isinstance(v, dict) or "name" not in v:
            errors.append(f"systems.{key} must be a mapping with a name (use name: none)")
    ea = systems.get("ea_metamodel")
    if str(ea).lower() not in EA_METAMODELS:
        errors.append(f"systems.ea_metamodel '{ea}' is not one of {', '.join(EA_METAMODELS)}")
    itsm = systems.get("itsm", {})
    if isinstance(itsm, dict) and not is_none(itsm):
        fw = itsm.get("framework")
        if str(fw).lower() not in ITSM_FRAMEWORKS:
            errors.append(f"systems.itsm.framework '{fw}' is not one of {', '.join(ITSM_FRAMEWORKS)}")
        if not isinstance(itsm.get("has_cmdb"), bool):
            errors.append("systems.itsm.has_cmdb must be true or false")
        for t in ("category_title", "cmdb_title"):
            if not isinstance(itsm.get(t), str) or not itsm.get(t).strip():
                errors.append(f"systems.itsm.{t} must be a non-empty string")
    cloud = systems.get("cloud")
    if not isinstance(cloud, list):
        errors.append("systems.cloud must be a list")
    else:
        for c in cloud:
            if str(c).lower() not in CLOUDS:
                errors.append(f"systems.cloud entry '{c}' is not one of {', '.join(CLOUDS)}")
    forums = data.get("forums", {})
    if not isinstance(forums, dict):
        errors.append("forums must be a mapping")
    else:
        for k, v in forums.items():
            if not isinstance(v, dict) or not v.get("name") or not v.get("short"):
                errors.append(f"forums.{k} needs a name and a short name")
    palette = data.get("house", {}).get("palette", {})
    for k, v in (palette or {}).items():
        if not isinstance(v, str) or not _HEX.match(v):
            errors.append(f"house.palette.{k} '{v}' is not a #RRGGBB colour")
    fonts = data.get("house", {}).get("fonts", {})
    for k in ("heading", "body"):
        if not isinstance(fonts.get(k), str) or not fonts.get(k):
            errors.append(f"house.fonts.{k} must name a font")
    styles = data.get("template", {}).get("styles", {})
    if not isinstance(styles, dict):
        errors.append("template.styles must be a mapping")
    return errors


class Profile:
    """A loaded profile with defaults applied.

    ``data`` is the merged dictionary. ``get('systems.itsm.name')`` looks a
    dotted path up; ``is_set(path)`` says whether a ``when:`` condition on it
    holds.
    """

    def __init__(self, data: dict, path: Path | None = None, raw: dict | None = None):
        self.data = data
        self.path = path
        self.raw = raw if raw is not None else {}

    # -- lookup -------------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        v = self.lookup(dotted)
        return default if v is _MISSING else v

    def lookup(self, dotted: str) -> Any:
        """The value at a dotted path, or the module's ``_MISSING`` sentinel."""
        cur: Any = self.data
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                return _MISSING
        return cur

    def has(self, dotted: str) -> bool:
        return self.lookup(dotted) is not _MISSING

    def is_set(self, dotted: str) -> bool:
        """True when the path exists and its value is not a "none" value. A
        path under a system whose name is none is never set."""
        parts = dotted.split(".")
        for i in range(1, len(parts)):
            parent = self.lookup(".".join(parts[:i]))
            if isinstance(parent, dict) and "name" in parent and is_none(parent["name"]):
                return False
        v = self.lookup(dotted)
        return v is not _MISSING and not is_none(v)

    def text(self, dotted: str, logical: bool = False) -> str | None:
        """The value as display text: a system's name, a list joined, or None
        when missing. With ``logical`` (a ``layer: logical`` document), a
        system's ``name`` gives way to its ``logical_name`` when the profile
        has one, so a logical design never names the product."""
        if logical:
            parent, _, leaf = dotted.rpartition(".")
            holder = self.lookup(parent) if leaf == "name" else self.lookup(dotted)
            if isinstance(holder, dict) and holder.get("logical_name") and (leaf == "name" or "name" in holder):
                return str(holder["logical_name"])
            # Any other text field of a system may carry its own logical
            # variant: systems.itsm.cmdb_title gives way to
            # systems.itsm.logical_cmdb_title.
            owner = self.lookup(parent) if parent else _MISSING
            if leaf != "name" and isinstance(owner, dict) and owner.get(f"logical_{leaf}"):
                return str(owner[f"logical_{leaf}"])
        v = self.lookup(dotted)
        if v is _MISSING or v is None:
            return None
        if isinstance(v, dict):
            if "name" in v:
                return str(v["name"])
            return None
        if isinstance(v, (list, tuple)):
            return ", ".join(str(x) for x in v)
        if isinstance(v, bool):
            return "yes" if v else "no"
        return str(v)

    def system_slugs(self) -> dict[str, str]:
        """Each named system's slug by its profile path, for ``guidance_by``."""
        out: dict[str, str] = {}
        systems = self.data.get("systems", {})
        for key in NAMED_SYSTEMS:
            v = systems.get(key, {})
            if isinstance(v, dict) and not is_none(v):
                out[f"systems.{key}.name"] = slug(v["name"])
        if not is_none(systems.get("ea_metamodel")):
            out["systems.ea_metamodel"] = slug(systems["ea_metamodel"])
        for i, c in enumerate(systems.get("cloud") or []):
            out[f"systems.cloud.{i}"] = slug(c)
        return out

    @property
    def ea_metamodel(self) -> str | None:
        v = self.data.get("systems", {}).get("ea_metamodel")
        return None if is_none(v) else str(v).lower()

    @property
    def palette(self) -> dict[str, str]:
        return self.data["house"]["palette"]

    @property
    def fonts(self) -> dict[str, str]:
        return self.data["house"]["fonts"]

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True)


def from_dict(raw: dict | None, path: Path | None = None, strict: bool = True) -> Profile:
    """Build a Profile from a raw mapping, applying defaults. Raises
    :class:`ProfileError` when ``strict`` and validation fails."""
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ProfileError(["profile must be a mapping"], path)
    data = _normalise(_merge(DEFAULTS, raw))
    errors = validate(data)
    if errors and strict:
        raise ProfileError(errors, path)
    return Profile(data, path, raw)


def load_profile(path: str | Path, strict: bool = True) -> Profile:
    """Load, default and validate a profile file."""
    p = Path(path)
    if not p.exists():
        raise ProfileError([f"profile file not found: {p}"], p)
    with p.open() as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ProfileError([f"YAML error: {e}"], p) from e
    return from_dict(raw, p, strict)
