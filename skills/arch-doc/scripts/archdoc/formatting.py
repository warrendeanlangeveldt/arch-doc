"""House formatting every output shares: dates and view captions.

The Word document, the review site and the deck must write a date and a view
caption the same way, so the rule lives in the core and the builders import
it from here rather than from each other.

- :func:`format_date` writes a date as the house does (``long``, ``iso`` or a
  strftime pattern); :func:`date_format` reads that choice from the profile
  (``house.date_format``, default ``long``).
- :func:`view_caption` is a VIEW's caption after "View n. ":
  "<title> (<EA metamodel> <viewpoint name>). <note>", with the note from
  :func:`view_note`.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from . import content as C

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
EA_NAMES = {"archimate": "ArchiMate", "coreea": "CoreEA", "togaf": "TOGAF", "essential": "Essential"}


def format_date(value: Any, fmt: str | None = None) -> str:
    """A date as the house writes it: ``long`` (the default, "17 October
    2026"), ``iso``, or a strftime pattern. Text that is not a date is
    returned as written."""
    if value is None or value == "":
        return ""
    d = value if isinstance(value, (_dt.date, _dt.datetime)) else None
    if d is None:
        try:
            d = _dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    fmt = (fmt or "long").strip()
    if fmt == "iso":
        return d.isoformat()[:10]
    if fmt == "long":
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return d.strftime(fmt)


def date_format(project) -> str:
    """The profile's ``house.date_format`` (``long`` when unset)."""
    return str(project.profile.get("house.date_format") or "long")


def view_note(project) -> str | None:
    """The document's note for every view caption: arch-doc.yaml
    ``captions.view_note``, else the profile's ``house.captions.view_note``.
    Placeholders resolve."""
    note = (project.config.get("captions") or {}).get("view_note") if isinstance(
        project.config.get("captions"), dict) else None
    note = note or project.profile.get("house.captions.view_note")
    if not note:
        return None
    return project.resolve_text(str(note))[0].strip()


def view_caption(project, v: C.View) -> str:
    """"<title> (<EA metamodel> <viewpoint name>). <note>" after "View n. "."""
    text = v.title
    ea = project.profile.ea_metamodel
    if v.ea_name:
        text += f" ({EA_NAMES.get(ea, ea or '').strip()} {v.ea_name})".replace("( ", "(")
    note = view_note(project)
    if note:
        text += ". " + note.rstrip(".") + "."
    return text


__all__ = ["EA_NAMES", "MONTHS", "date_format", "format_date", "view_caption", "view_note"]
