#!/usr/bin/env python3
"""archdoc: the arch-doc command line.

Run from a project directory, or point at one with -C:

    uv run --with pyyaml --with python-docx --with pillow python archdoc.py init docs/pts --kind solution
    uv run --with pyyaml --with python-docx --with pillow python archdoc.py -C docs/pts numbering

Commands (SPEC 8): init, profile, extract, check, build, diagrams, numbering,
comments, status.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from archdoc import Project, ProjectError  # noqa: E402
from archdoc.metamodel import MetamodelError  # noqa: E402
from archdoc.profile import ProfileError, load_profile  # noqa: E402
from archdoc.project import CONFIG  # noqa: E402
from archdoc import scaffold  # noqa: E402


class NotBuilt(RuntimeError):
    def __init__(self, command: str, module: str):
        super().__init__(f"archdoc {command}: not built yet (archdoc/{module}.py is part of phase 2)")


def phase2(command: str, module: str):
    """Import a phase 2 module, or raise NotBuilt when it does not exist
    yet. An import error inside an existing module is not hidden."""
    try:
        return importlib.import_module(f"archdoc.{module}")
    except ModuleNotFoundError as e:
        if e.name == f"archdoc.{module}":
            raise NotBuilt(command, module) from None
        raise


def load(args) -> Project:
    return Project.load(args.project)


# ------------------------------------------------------------------ init

def cmd_init(args) -> int:
    files = scaffold.init(
        args.dir, kind=args.kind, profile=args.profile, template=args.template, title=args.title,
        short=args.short, layer=args.layer, version=args.version, metamodel=args.metamodel,
        depends_on=args.depends_on, author=args.author, owner=args.owner, date=args.date, force=args.force)
    root = Path(args.dir).resolve()
    for f in files:
        print(f"wrote {f.relative_to(root)}")
    p = Project.load(root)
    print(f"{p.title}: {len(p.chapters)} chapters, {sum(len(c.sections) for c in p.chapters)} sections, "
          f"{sum(1 for _ in (root / 'registers').glob('*.yaml'))} registers")
    return 0


# --------------------------------------------------------------- profile

def cmd_profile(args) -> int:
    if args.file:
        path = Path(args.file)
    else:
        cfg = Path(args.project) / CONFIG
        if not cfg.exists():
            print(f"archdoc profile: no {CONFIG} in {args.project}; pass --file", file=sys.stderr)
            return 2
        import yaml
        path = Path(args.project) / ((yaml.safe_load(cfg.read_text()) or {}).get("profile") or "profile.yaml")
    prof = load_profile(path, strict=False)
    from archdoc.profile import validate
    errors = validate(prof.data)
    if args.validate:
        if errors:
            for e in errors:
                print(f"{path}: {e}")
            return 1
        print(f"{path}: valid")
        return 0
    sys.stdout.write(prof.to_yaml())
    for e in errors:
        print(f"# problem: {e}", file=sys.stderr)
    return 1 if errors else 0


# ------------------------------------------------------------- numbering

def cmd_numbering(args) -> int:
    p = load(args)
    rows = p.numbering()
    if args.json:
        print(json.dumps([{"number": n, "title": t, "key": k} for n, t, k in rows], indent=2))
        return 0
    wn = max(len(n) for n, _, _ in rows)
    wt = max(len(t) + (2 if "." in n else 0) for n, t, _ in rows)
    for n, t, k in rows:
        title = ("  " + t) if "." in n else t
        print(f"{n.ljust(wn)}  {title.ljust(wt)}  {k}")
    return 0


# ---------------------------------------------------------------- status

def _chapter_of(p: Project) -> dict[str, int]:
    """Every anchor in the document to its chapter number."""
    out: dict[str, int] = {}
    for ch in p.chapters:
        out[ch.anchor] = ch.number
        for s in ch.sections:
            out[s.anchor] = ch.number
        for b in ch.blocks():
            for a in [b.anchor, getattr(b, "header_anchor", None)] + list(getattr(b, "item_anchors", [])) \
                    + list(getattr(b, "row_anchors", [])):
                if a:
                    out[a] = ch.number
    return out


def cmd_status(args) -> int:
    p = load(args)
    where = _chapter_of(p)
    findings = None
    try:
        findings = phase2("status", "checks").run(p)
    except NotBuilt:
        pass
    tbcs = p.tbcs()
    rows = []
    for ch in p.chapters:
        filled = sum(1 for s in ch.sections if s.filled)
        regs = ", ".join(f"{t} {len(p.registers[t])}" for t in ch.registers_used if t in p.registers)
        figs = ch.figures
        missing = sum(1 for f in figs if f.path is None)
        ch_tbcs = [t for t in tbcs if t.anchor and where.get(t.anchor) == ch.number]
        unowned = sum(1 for t in ch_tbcs if not t.owner)
        f_count = "-" if findings is None else str(sum(
            1 for f in findings if f.anchor and where.get(f.anchor) == ch.number))
        rows.append({
            "number": ch.number, "key": ch.key, "sections": f"{filled}/{len(ch.sections)}",
            "registers": regs or "-", "figures": f"{len(figs)}" + (f" ({missing} not rendered)" if missing else ""),
            "tbcs": f"{len(ch_tbcs)}" + (f" ({unowned} unowned)" if unowned else ""),
            "findings": f_count,
        })
    uncited = [t for t in tbcs if not t.anchor]
    summary = {
        "title": p.title, "version": p.version, "kind": p.kind, "layer": p.layer,
        "tbcs": len(tbcs), "unowned_tbcs": sum(1 for t in tbcs if not t.owner),
        "uncited_register_tbcs": len(uncited), "issues": len(p.issues),
        "checks": "not built yet (archdoc/checks.py is part of phase 2)" if findings is None else len(findings),
    }
    if args.json:
        print(json.dumps({"summary": summary, "chapters": rows}, indent=2))
        return 0
    cols = [("number", "Ch"), ("key", "Chapter"), ("sections", "Sections"), ("registers", "Registers"),
            ("figures", "Figures"), ("tbcs", "TBCs"), ("findings", "Findings")]
    widths = {c: max(len(h), *(len(str(r[c])) for r in rows)) for c, h in cols}
    print(f"{p.title} v{p.version} ({p.kind}, {p.layer})")
    print("  ".join(h.ljust(widths[c]) for c, h in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c, _ in cols))
    print(f"TBCs: {summary['tbcs']} ({summary['unowned_tbcs']} unowned, "
          f"{summary['uncited_register_tbcs']} in register records no section cites)")
    print(f"Load issues: {summary['issues']}")
    for i in p.issues[:args.issues]:
        print(f"  {i}")
    if len(p.issues) > args.issues:
        print(f"  ... {len(p.issues) - args.issues} more (archdoc status --issues N)")
    print(f"Checks: {summary['checks']}")
    return 0


# ---------------------------------------------------------- phase 2 wiring

def cmd_extract(args) -> int:
    # phase 2: archdoc/extract.py
    return phase2("extract", "extract").cli(args)


def cmd_check(args) -> int:
    # phase 2: archdoc/checks.py
    checks = phase2("check", "checks")
    findings = checks.run(load(args))
    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        for f in findings:
            print(f)
        errors = sum(1 for f in findings if f.severity == "error")
        print(f"{errors} errors, {len(findings) - errors} warnings")
    return 1 if any(f.severity == "error" for f in findings) else 0


BUILDERS = {"docx": "docx_build", "site": "site_build", "deck": "deck_build"}


def cmd_build(args) -> int:
    # phase 2: archdoc/docx_build.py, archdoc/site_build.py, archdoc/deck_build.py (and archdoc/checks.py)
    targets = list(BUILDERS) if args.target == "all" else [args.target]
    modules = [phase2(f"build {t}", BUILDERS[t]) for t in targets]
    p = load(args)
    if not args.force:
        findings = phase2("build", "checks").run(p)
        errors = [f for f in findings if f.severity == "error"]
        if errors:
            for f in errors:
                print(f, file=sys.stderr)
            print(f"archdoc build: {len(errors)} check errors; fix them or pass --force", file=sys.stderr)
            return 1
    for m in modules:
        for out in m.build(p):
            print(f"wrote {out}")
    return 0


def cmd_diagrams(args) -> int:
    # phase 2: archdoc/diagrams.py
    return phase2("diagrams", "diagrams").cli(args)


def cmd_comments(args) -> int:
    # phase 2: archdoc/comments.py
    return phase2("comments", "comments").cli(args)


# ------------------------------------------------------------------ main

def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="archdoc", description="Architecture design documents from one project.")
    ap.add_argument("-C", "--project", default=".", help="project directory (default: current)")
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="scaffold a project")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--kind", required=True, choices=["solution", "capability"])
    s.add_argument("--profile", help="shared profile to use (default: write profile.yaml)")
    s.add_argument("--template", help="the organisation's .docx template")
    s.add_argument("--title")
    s.add_argument("--short")
    s.add_argument("--layer", choices=["logical", "logical-and-physical"])
    s.add_argument("--version", default="0.1")
    s.add_argument("--metamodel", default="seed")
    s.add_argument("--depends-on", action="append", default=[], metavar="PATH:REF",
                   help="a design this one depends on, e.g. ../platform:NP (repeatable)")
    s.add_argument("--author")
    s.add_argument("--owner")
    s.add_argument("--date")
    s.add_argument("--force", action="store_true", help="rewrite arch-doc.yaml; never overwrites content")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("profile", help="show or validate the profile")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--show", action="store_true", help="print the profile with defaults (default)")
    g.add_argument("--validate", action="store_true")
    s.add_argument("--file", help="a profile file (default: the project's)")
    s.set_defaults(func=cmd_profile)

    s = sub.add_parser("extract", help="write a metamodel from an organisation's .docx template")
    s.add_argument("template")
    s.add_argument("-o", "--output", default="metamodel.yaml")
    s.add_argument("--profile-out", help="write the profile fragment (template path, styles, fields) here "
                   "instead of printing it")
    s.add_argument("--seed", default="seed", help="the metamodel chapters are matched against (default: seed)")
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("check", help="run the checks")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("build", help="build docx, site, deck or all")
    s.add_argument("target", choices=["docx", "site", "deck", "all"])
    s.add_argument("--force", action="store_true", help="build despite check errors")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("diagrams", help="list, render and report figures")
    s.add_argument("--render", action="store_true")
    s.add_argument("--force", action="store_true", help="with --render, render every figure, not only stale ones")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_diagrams)

    s = sub.add_parser("numbering", help="print the rendered chapter and section numbering")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_numbering)

    s = sub.add_parser("comments", help="review comments")
    csub = s.add_subparsers(dest="comments_command", required=True)
    c = csub.add_parser("import", help="merge exported site comments into out/comments.json")
    c.add_argument("file")
    s.set_defaults(func=cmd_comments)

    s = sub.add_parser("status", help="per chapter: sections, registers, figures, TBCs, findings")
    s.add_argument("--json", action="store_true")
    s.add_argument("--issues", type=int, default=10, help="load issues to list (default 10)")
    s.set_defaults(func=cmd_status)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except NotBuilt as e:
        print(e, file=sys.stderr)
        return 2
    except (ProjectError, ProfileError, MetamodelError, scaffold.ScaffoldError) as e:
        print(f"archdoc {args.command}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
