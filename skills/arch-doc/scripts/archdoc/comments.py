"""Review comments read back into the project (``archdoc comments import``).

The review site keeps comments in two places. Published as an Artifact, the
page posts threads whose bodies start with ``[anchor] <section>``; opened as a
local file, it keeps them in the browser and exports them as JSON::

    {"format": "arch-doc-comments", "version": 1,
     "document": {"title": ..., "short": ..., "version": ...},
     "exported": "<ISO time>",
     "comments": [{"id", "anchor", "section", "label", "quote", "text", "author", "at"}],
     "review": {"<section anchor>": {"status", "section", "at"}}}

``import`` accepts that export, or a JSON list of comment objects (for
threads read back from the published page), where a comment with no
``anchor`` takes it from a leading ``[anchor]`` in its text. It merges the
file into ``<project>/out/comments.json`` (a comment already there is not
added twice; for review status the latest ``at`` wins) and prints the
comments grouped by anchor, in document order, with the section number and
title from the current numbering.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

from .project import Project
from .site_build import anchor_index, place_of

FORMAT = "arch-doc-comments"
STORE = Path("out") / "comments.json"
_PREFIX = re.compile(r"^\s*\[([A-Za-z0-9][A-Za-z0-9_-]*)\]")
STATUSES = ("in-review", "changes", "agreed")


class CommentsError(ValueError):
    """Raised when an import file cannot be read as comments."""


def _key(c: dict) -> str:
    if c.get("id"):
        return str(c["id"])
    raw = json.dumps([c.get("anchor"), c.get("text"), c.get("at"), c.get("author")], sort_keys=True)
    return "h-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def normalise(data) -> dict:
    """An import file's content as ``{document, comments, review}``."""
    if isinstance(data, list):
        data = {"comments": data}
    if not isinstance(data, dict):
        raise CommentsError("expected a JSON object (an arch-doc export) or a list of comments")
    if data.get("format") not in (None, FORMAT):
        raise CommentsError(f"format '{data.get('format')}' is not {FORMAT}")
    raw = data.get("comments") or []
    if not isinstance(raw, list):
        raise CommentsError("'comments' must be a list")
    out = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise CommentsError(f"comment {i + 1} is not an object")
        text = str(c.get("text") or c.get("body") or "").strip()
        anchor = str(c.get("anchor") or "").strip()
        if not anchor:
            m = _PREFIX.match(text)
            if m:
                anchor = m.group(1)
        if not text:
            raise CommentsError(f"comment {i + 1} has no text")
        item = {"id": c.get("id"), "anchor": anchor, "section": c.get("section") or "",
                "label": c.get("label") or "", "quote": c.get("quote") or "", "text": text,
                "author": c.get("author") or "", "at": c.get("at") or ""}
        item["id"] = _key(item)
        out.append(item)
    review = data.get("review") or {}
    if not isinstance(review, dict):
        raise CommentsError("'review' must be an object of section anchor to status")
    rv = {}
    for sec, v in review.items():
        if isinstance(v, str):
            v = {"status": v}
        if not isinstance(v, dict) or v.get("status") not in STATUSES:
            raise CommentsError(f"review status for {sec} must be one of {', '.join(STATUSES)}")
        rv[str(sec)] = {"status": v["status"], "section": v.get("section") or "", "at": v.get("at") or ""}
    return {"document": data.get("document") or {}, "comments": out, "review": rv}


def load_store(path: Path) -> dict:
    if not path.exists():
        return {"format": FORMAT, "version": 1, "document": {}, "comments": [], "review": {}, "imports": []}
    data = json.loads(path.read_text())
    data.setdefault("comments", [])
    data.setdefault("review", {})
    data.setdefault("imports", [])
    return data


def merge(store: dict, incoming: dict, source: str, project: Project) -> tuple[int, int]:
    """Merge normalised comments into the store. Returns (comments added,
    review statuses changed)."""
    have = {c["id"] for c in store["comments"]}
    added = 0
    for c in incoming["comments"]:
        if c["id"] in have:
            continue
        store["comments"].append(c)
        have.add(c["id"])
        added += 1
    changed = 0
    for sec, v in incoming["review"].items():
        cur = store["review"].get(sec)
        if cur is None or (v.get("at") or "") >= (cur.get("at") or ""):
            if cur != v:
                changed += 1
            store["review"][sec] = v
    store["document"] = {"title": project.title, "short": project.short, "version": project.version}
    store["imports"].append({"file": source, "at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                             "added": added, "from_version": (incoming["document"] or {}).get("version")})
    return added, changed


def report(store: dict, project: Project, out=sys.stdout) -> None:
    """Print the comments grouped by anchor, in document order."""
    index = anchor_index(project)
    groups: dict[str, list[dict]] = {}
    for c in store["comments"]:
        groups.setdefault(c.get("anchor") or "", []).append(c)

    def order(anchor: str) -> tuple[int, int, str]:
        if anchor in index:
            return (0, index[anchor].order, anchor)
        pl = place_of(index, anchor) if anchor else None
        return (1, pl.order if pl else 10 ** 9, anchor)

    for anchor in sorted(groups, key=order):
        place = place_of(index, anchor) if anchor else None
        if not anchor:
            head = "(no anchor)"
        elif anchor in index:
            head = f"{anchor}  {index[anchor].label}"
        elif place:
            head = f"{anchor}  {place.label}  (anchor not in this version; nearest is {place.anchor})"
        else:
            head = f"{anchor}  (not in this version)"
        print(head, file=out)
        for c in sorted(groups[anchor], key=lambda x: x.get("at") or ""):
            who = " · ".join(x for x in (c.get("author"), (c.get("at") or "")[:16].replace("T", " ")) if x)
            if who:
                print(f"  {who}", file=out)
            if c.get("quote"):
                print(f"    “{c['quote']}”", file=out)
            text = c["text"]
            if c.get("quote") or not _PREFIX.match(text):
                body = text
            else:
                body = text.split("\n\n", 1)[1] if "\n\n" in text else text
            for line in body.splitlines() or [""]:
                print(f"    {line}", file=out)
        print(file=out)
    if store["review"]:
        print("Review status", file=out)
        for sec in sorted(store["review"], key=order):
            v = store["review"][sec]
            label = index[sec].label if sec in index else (v.get("section") or sec)
            print(f"  {sec:<8} {v['status']:<10} {label}", file=out)


def import_file(project: Project, file: Path, out=sys.stdout) -> Path:
    try:
        data = json.loads(Path(file).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CommentsError(f"{file}: {e}") from e
    incoming = normalise(data)
    path = project.root / STORE
    store = load_store(path)
    added, changed = merge(store, incoming, str(file), project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n")
    v = (incoming["document"] or {}).get("version")
    print(f"{file}: {added} new comment{'s' if added != 1 else ''} of {len(incoming['comments'])}, "
          f"{changed} review status{'es' if changed != 1 else ''} changed; "
          f"{len(store['comments'])} in {project.rel(path)}", file=out)
    if v and str(v) != project.version:
        print(f"note: exported from v{v}; this document is v{project.version}, so anchors may have moved",
              file=out)
    print(file=out)
    report(store, project, out)
    return path


def cli(args) -> int:
    if getattr(args, "comments_command", "import") != "import":
        print(f"archdoc comments: unknown command {args.comments_command}", file=sys.stderr)
        return 2
    project = Project.load(args.project)
    try:
        import_file(project, Path(args.file))
    except CommentsError as e:
        print(f"archdoc comments import: {e}", file=sys.stderr)
        return 2
    return 0


__all__ = ["cli", "import_file", "normalise", "merge", "report", "CommentsError", "FORMAT"]
