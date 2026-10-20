"""``archdoc init``: scaffold a project (SPEC 8).

Writes arch-doc.yaml, a profile (unless a shared one is named), one content
file per effective chapter with each section's guidance as comments, an empty
register for every artefact type the effective metamodel uses, and an empty
diagrams/ directory.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import textwrap
from pathlib import Path

import yaml

from .metamodel import load_metamodel
from .profile import DEFAULTS, load_profile
from .project import CONFIG, KINDS, LAYERS

WIDTH = 78


class ScaffoldError(ValueError):
    pass


def _q(value) -> str:
    """A YAML scalar for inline use."""
    return yaml.safe_dump(value, default_flow_style=True, width=1000).strip().removesuffix("...").strip()


def _wrap(text: str, indent: str = "") -> list[str]:
    return textwrap.wrap(text, WIDTH - len(indent), initial_indent=indent, subsequent_indent=indent) or [indent]


def _locate(given: str, root: Path, option: str) -> Path:
    """A file named on the command line: relative to the project directory
    first, then to the current directory."""
    p = Path(given)
    if p.is_absolute():
        cands = [p]
    else:
        cands = [(root / p).resolve(), (Path.cwd() / p).resolve()]
    for c in cands:
        if c.exists():
            return c
    raise ScaffoldError(f"{option} {given}: not found relative to {root} or the current directory")


def parse_dependency(spec: str) -> tuple[str, str]:
    """``../northwind-platform:NP`` -> (path, ref)."""
    path, sep, ref = spec.rpartition(":")
    if not sep or not path or not ref:
        raise ScaffoldError(f"--depends-on takes <path>:<ref>, got '{spec}'")
    return path, ref


def register_header(rtype) -> str:
    ids = " or ".join(f"{p}-nn" for p in rtype.prefixes)
    lines = [f"# {rtype.label} register ({rtype.key}). One record per item; ids are {ids}, optionally "
             f"after a namespace (ACME-{rtype.prefix}-nn).",
             "# Fields: id, title, status"]
    for name, spec in rtype.fields.items():
        if spec.kind == "enum":
            desc = " | ".join(spec.enum)
        elif spec.kind in ("ref", "refs"):
            desc = f"{spec.kind}:{spec.ref_type}"
        else:
            desc = spec.kind
        lines.append(f"#   {name}: {desc}")
    lines.append("# Status: " + ", ".join(f"{k} ({v})" for k, v in rtype.status.items()))
    lines.append('# Any value may be TBC or "TBC: <owner>"; a bare TBC takes the record\'s owner.')
    return "\n".join(lines) + "\n"


def chapter_file(number: int, ch) -> str:
    out = [f"# {ch.key}", "<!--", f"Chapter {number}: {ch.title}"]
    if ch.question:
        out += _wrap(f"Question: {ch.question}")
    if ch.story:
        out += _wrap(f"Story: {ch.story}")
    out += _wrap("Lead-in: before the first section, one or two sentences on what this chapter "
                 "establishes. Cite registers with placeholders; do not restate them.")
    out += ["-->", ""]
    for si, s in enumerate(ch.sections, start=1):
        out += [f"## {s.key}", "<!--", f"{number}.{si} {s.title}" + ("  (optional)" if s.optional else "")]
        out += _wrap(s.guidance)
        for a in s.artefacts:
            out.append(f"Register: REGISTER {a}")
        out += ["-->", ""]
    return "\n".join(out).rstrip() + "\n"


def _person(name: str | None, role: str | None, team: str | None, confirm: str) -> str:
    """A person for arch-doc.yaml with nothing unowned: an unknown name is
    ``TBC: <who confirms it>``; an unknown role or team is left out."""
    parts = [f"name: {_q(name or f'TBC: {confirm}')}"]
    if role:
        parts.append(f"role: {_q(role)}")
    if team:
        parts.append(f"team: {_q(team)}")
    return "{" + ", ".join(parts) + "}"


def config_text(title: str, short: str, kind: str, layer: str, version: str, date: str,
                author: str | None, owner: str | None, metamodel: str, profile: str,
                template: str | None, depends: list[dict], author_role: str | None = None,
                author_team: str | None = None, owner_role: str | None = None,
                confirm: str = "Document owner") -> str:
    lines = [
        f"title: {_q(title)}",
        f"short: {_q(short)}",
        f"kind: {kind:<24}# solution | capability",
        f"layer: {layer:<23}# logical | logical-and-physical; logical bans product names",
        f'version: "{version}"',
        f"date: {date}",
        f"author: {_person(author, author_role, author_team, confirm)}",
        f"owner: {_person(owner, owner_role, None, confirm)}",
        f"metamodel: {_q(metamodel)}",
        f"profile: {_q(profile)}",
        f"template: {_q(template) if template else 'null'}",
    ]
    if depends:
        lines.append("depends_on:")
        for d in depends:
            lines.append("  - {" + ", ".join(f"{k}: {_q(v)}" for k, v in d.items()) + "}")
    else:
        lines.append("depends_on: []")
    lines += [
        "history:",
        f"  - {{date: {date}, version: \"{version}\", author: {_q(author or f'TBC: {confirm}')}, "
        f"change: First draft}}",
        "banned_terms: []",
    ]
    return "\n".join(lines) + "\n"


def init(target: str | Path, kind: str, profile: str | None = None, template: str | None = None,
         title: str | None = None, short: str | None = None, layer: str | None = None,
         version: str = "0.1", metamodel: str = "seed", depends_on: list[str] | None = None,
         author: str | None = None, owner: str | None = None, date: str | None = None,
         force: bool = False, author_role: str | None = None, author_team: str | None = None,
         owner_role: str | None = None) -> list[Path]:
    """Scaffold a project in ``target`` and return the files written.

    Relative ``profile``, ``metamodel`` and ``template`` paths are read
    relative to the project directory, as arch-doc.yaml records them; a
    path that exists only relative to the current directory is accepted
    and recorded relative to the project."""
    root = Path(target).resolve()
    if kind not in KINDS:
        raise ScaffoldError(f"--kind must be one of {', '.join(KINDS)}")
    layer = layer or ("logical" if kind == "capability" else "logical-and-physical")
    if layer not in LAYERS:
        raise ScaffoldError(f"--layer must be one of {', '.join(LAYERS)}")
    if (root / CONFIG).exists() and not force:
        raise ScaffoldError(f"{root / CONFIG} already exists (--force rewrites arch-doc.yaml and adds missing files; "
                            "it never overwrites content or registers)")
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if profile:
        prof_path = _locate(profile, root, "--profile")
        prof = load_profile(prof_path)
        profile_ref = os.path.relpath(prof_path, root)
    else:
        prof_path = root / "profile.yaml"
        if not prof_path.exists():
            prof_path.write_text(
                "# Organisation profile. Run the arch-doc interview to fill it; see references/interview.md.\n"
                + yaml.safe_dump({k: v for k, v in DEFAULTS.items()}, sort_keys=False))
            written.append(prof_path)
        prof = load_profile(prof_path)
        profile_ref = "profile.yaml"

    if metamodel.endswith((".yaml", ".yml")) or "/" in metamodel:
        mm_path = _locate(metamodel, root, "--metamodel")
        metamodel = os.path.relpath(mm_path, root)
    mm = load_metamodel(metamodel, root)
    model = mm.apply(prof, kind, layer)
    if template:
        template = os.path.relpath(_locate(template, root, "--template"), root)

    depends = []
    for spec in depends_on or []:
        path, ref = parse_dependency(spec)
        droot = (root / path).resolve() if not Path(path).is_absolute() else Path(path)
        dcfg = droot / CONFIG
        if not dcfg.exists():
            raise ScaffoldError(f"--depends-on {spec}: no {CONFIG} in {droot}")
        d = yaml.safe_load(dcfg.read_text()) or {}
        depends.append({"title": d.get("title"), "kind": d.get("kind"), "version": str(d.get("version")),
                        "path": os.path.relpath(droot, root), "ref": ref})

    title = title or root.name.replace("-", " ").replace("_", " ").title()
    short = short or "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", title)).upper()
    date = date or _dt.date.today().isoformat()
    cfg = root / CONFIG
    confirm = prof.text("roles.architect") or "Document owner"
    cfg.write_text(config_text(title, short, kind, layer, version, date, author, owner, metamodel,
                               profile_ref, template, depends, author_role or prof.text("roles.architect"),
                               author_team, owner_role, confirm))
    written.append(cfg)

    rdir = root / "registers"
    rdir.mkdir(exist_ok=True)
    for key in model.used_types():
        path = rdir / f"{key}.yaml"
        if path.exists():
            continue
        path.write_text(register_header(model.artefact_types[key]) + "[]\n")
        written.append(path)

    cdir = root / "content"
    cdir.mkdir(exist_ok=True)
    for ci, ch in enumerate(model.chapters, start=1):
        path = cdir / f"{ci:02d}-{ch.key}.md"
        if path.exists() or any(cdir.glob(f"*-{ch.key}.md")):
            continue
        path.write_text(chapter_file(ci, ch))
        written.append(path)

    ddir = root / "diagrams"
    ddir.mkdir(exist_ok=True)
    keep = ddir / ".gitkeep"
    if not keep.exists():
        keep.write_text("")
        written.append(keep)
    return written
