"""Figures and views: the tools that draw them, what each chapter shows, and
rendering (SPEC 9).

A figure's source sits in the project's ``diagrams/`` directory under the
figure's name, beside the PNG and SVG rendered from it:

``<name>.mmd``
    Mermaid, rendered by ``npx -y @mermaid-js/mermaid-cli@11.12.0`` (pinned in
    :data:`MERMAID_CLI`) to SVG and to PNG at twice the size, themed from the
    profile's house palette and fonts through a generated Mermaid config
    (:func:`mermaid_config`).
``<name>.ead``
    An arch-diagram view file (its view language), rendered with
    arch-diagram's ``ea.py render``. When the file holds several views, the
    figure draws the one whose id matches the figure name.
``<name>.py``
    A script, run with the interpreter running archdoc from the diagrams
    directory. It must write ``<name>.png`` or ``<name>.svg`` beside itself.
    A script that imports arch-diagram's ``ealib`` needs arch-diagram; it
    finds the scripts through ``ARCH_DIAGRAM_SCRIPTS``. ``ARCHDOC_FIGURE``,
    ``ARCHDOC_OUT`` and ``ARCHDOC_PALETTE`` (JSON) are set for it, and
    ``PYTHONDONTWRITEBYTECODE`` so no ``__pycache__`` lands in diagrams/.
    A ``.py`` that no FIGURE or VIEW names is a helper module, not an unused
    source, when a figure script imports it or its name starts with ``_`` or
    ends with ``lib``.

A PNG or SVG with no source is a static figure: listed, never rendered.

arch-diagram counts as installed when ``ARCH_DIAGRAM_HOME`` is set, when the
plugin cache holds
``<claude dir>/plugins/cache/arch-diagram/arch-diagram/<version>/skills/arch-diagram/scripts/ea.py``
(the highest version wins), or when the skill is reachable another way: the
installed-plugins record, ``<claude dir>/skills/arch-diagram`` or the
project's ``.claude/skills/arch-diagram``. The Claude directory is
``CLAUDE_CONFIG_DIR`` when set, else ``~/.claude``.

When a tool is missing, rendering says how to install it once and fails the
figures that need it. It never writes a placeholder image.

Public API
----------

``find_arch_diagram()``, ``find_npx()``, ``find_chrome()``
    Tool detection.
``figure_tool(figure)``
    ``"mermaid"``, ``"arch-diagram"``, ``"python"`` or None (static or missing).
``listing(project)``
    A :class:`Listing`: every figure and view per chapter, with source,
    output, whether it is rendered and with which tool, and the chapters
    with no figure.
``render(project, force=False)``
    Render every figure with a source that is missing or out of date.
``ensure_png(figure, project=None)``
    The figure's PNG for the docx builder, rendering it when needed.
``mermaid_source(figure)``
    The Mermaid text of a ``.mmd`` figure, for in-browser rendering.
``mermaid_config(profile)``
    The Mermaid configuration (theme variables) from the house palette.
``cli(args)``
    ``archdoc diagrams [--render] [--force] [--json]``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import chrome
from .content import Figure, View
from .profile import load_profile

if TYPE_CHECKING:  # pragma: no cover
    from .profile import Profile
    from .project import Chapter, Project

# Pinned to an exact release so every machine renders the same figures. Raise
# it deliberately, to a release at least two weeks old, and re-render the
# examples (archdoc diagrams --render --force) when you do.
MERMAID_CLI = "@mermaid-js/mermaid-cli@11.12.0"
SOURCE_EXTS = (".mmd", ".ead", ".py")
OUTPUT_EXTS = (".png", ".svg")
TOOL_OF = {".mmd": "mermaid", ".ead": "arch-diagram", ".py": "python"}

INSTALL = {
    "arch-diagram": ("arch-diagram is not installed. In Claude Code run:\n"
                     "    /plugin marketplace add warrendeanlangeveldt/arch-diagram\n"
                     "    /plugin install arch-diagram@arch-diagram\n"
                     "or set ARCH_DIAGRAM_HOME to its directory."),
    "mermaid": ("Node.js is not installed, so Mermaid figures cannot be rendered here. Install Node.js "
                f"(https://nodejs.org); npx then runs {MERMAID_CLI}. The site and deck still draw "
                "Mermaid in the browser; the docx needs the PNG."),
    "chrome": ("Chrome or Chromium is needed to turn an SVG into a PNG. Install it or set CHROME_PATH."),
}

RENDER_TIMEOUT = 300


class DiagramError(RuntimeError):
    """A figure could not be rendered. ``tool`` names a missing tool
    (``arch-diagram``, ``mermaid``, ``chrome``) when that is the cause."""

    def __init__(self, message: str, tool: str | None = None):
        super().__init__(message)
        self.tool = tool


# ----------------------------------------------------------- detection

def claude_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def _version_key(v: str) -> tuple:
    parts = re.split(r"[.\-+]", v)
    return tuple((0, int(p)) if p.isdigit() else (-1, p) for p in parts)


@dataclass
class ArchDiagram:
    """Where arch-diagram was found. ``scripts`` is its scripts directory
    and ``ea_py`` its EA command line, when present; ``how`` says how it
    was found."""

    how: str
    home: Path
    scripts: Path | None
    version: str | None = None

    @property
    def ea_py(self) -> Path | None:
        if self.scripts is None:
            return None
        p = self.scripts / "ea.py"
        return p if p.exists() else None

    def describe(self) -> str:
        ver = f" {self.version}" if self.version else ""
        where = self.scripts or self.home
        note = "" if self.ea_py else " (no scripts/ea.py there, so .ead views cannot be rendered)"
        return f"installed{ver}, found via {self.how}: {where}{note}"


def _scripts_under(home: Path) -> Path | None:
    """The arch-diagram scripts directory for a plugin root, skill directory
    or scripts directory."""
    for cand in (home / "skills" / "arch-diagram" / "scripts", home / "scripts", home):
        if (cand / "ea.py").exists():
            return cand
    return None


def _version_of(home: Path) -> str | None:
    for manifest in (home / ".claude-plugin" / "plugin.json", home.parent.parent / ".claude-plugin" / "plugin.json"):
        if manifest.exists():
            try:
                v = json.loads(manifest.read_text()).get("version")
                if v:
                    return str(v)
            except (OSError, ValueError):
                pass
    return None


def find_arch_diagram(project_root: str | Path | None = None) -> ArchDiagram | None:
    """arch-diagram's location, or None when it is not installed."""
    env = os.environ.get("ARCH_DIAGRAM_HOME")
    if env:
        home = Path(env).expanduser()
        return ArchDiagram("ARCH_DIAGRAM_HOME", home, _scripts_under(home), _version_of(home))
    cdir = claude_dir()
    cache = cdir / "plugins" / "cache" / "arch-diagram" / "arch-diagram"
    if cache.is_dir():
        found = []
        for vdir in cache.iterdir():
            ea = vdir / "skills" / "arch-diagram" / "scripts" / "ea.py"
            if vdir.is_dir() and ea.exists():
                found.append(vdir)
        if found:
            best = max(found, key=lambda d: _version_key(d.name))
            return ArchDiagram("the plugin cache", best, best / "skills" / "arch-diagram" / "scripts", best.name)
    record = cdir / "plugins" / "installed_plugins.json"
    if record.exists():
        try:
            data = json.loads(record.read_text())
        except (OSError, ValueError):
            data = {}
        plugins = data.get("plugins", data) if isinstance(data, dict) else {}
        for key, entries in (plugins or {}).items():
            if not str(key).startswith("arch-diagram@"):
                continue
            for e in entries if isinstance(entries, list) else [entries]:
                path = e.get("installPath") if isinstance(e, dict) else None
                if path and _scripts_under(Path(path)):
                    home = Path(path)
                    return ArchDiagram("the installed plugins record", home, _scripts_under(home),
                                       e.get("version") or _version_of(home))
    homes = [cdir / "skills" / "arch-diagram"]
    if project_root is not None:
        homes.insert(0, Path(project_root) / ".claude" / "skills" / "arch-diagram")
    for home in homes:
        if (home / "SKILL.md").exists() or _scripts_under(home):
            return ArchDiagram("the skill directory", home, _scripts_under(home), _version_of(home))
    return None


def find_npx() -> Path | None:
    """npx, which runs mermaid-cli, or None when Node is not installed."""
    p = shutil.which("npx")
    return Path(p) if p else None


def find_chrome() -> Path | None:
    """Chrome or Chromium (``archdoc.chrome.find``)."""
    return chrome.find()


# --------------------------------------------------------------- figures

def source_of(figure: Figure) -> Path | None:
    return figure.source_file


def figure_tool(figure: Figure) -> str | None:
    """The tool that renders a figure's source, or None when it has none."""
    src = source_of(figure)
    return TOOL_OF.get(src.suffix) if src is not None else None


def outputs_of(figure: Figure, diagrams_dir: Path) -> dict[str, Path]:
    return {ext: diagrams_dir / f"{figure.name}{ext}" for ext in OUTPUT_EXTS
            if (diagrams_dir / f"{figure.name}{ext}").exists()}


def mermaid_source(figure: Figure) -> str | None:
    """The Mermaid text of a ``.mmd`` figure, or None for any other source."""
    src = source_of(figure)
    if src is None or src.suffix != ".mmd" or not src.exists():
        return None
    return src.read_text()


def mermaid_config(profile: "Profile") -> dict[str, Any]:
    """A Mermaid configuration themed from the profile's house palette and
    fonts. The site and deck pass the same object to ``mermaid.initialize``
    so figures drawn in the browser match the rendered ones."""
    pal = profile.palette
    fonts = profile.fonts
    family = f"\"{fonts['body']}\", \"Helvetica Neue\", Arial, sans-serif"
    return {
        "theme": "base",
        "themeVariables": {
            "background": pal["paper"],
            "fontFamily": family,
            "fontSize": "15px",
            "primaryColor": pal["accent_soft"],
            "primaryTextColor": pal["ink"],
            "primaryBorderColor": pal["accent"],
            "secondaryColor": pal["panel"],
            "secondaryTextColor": pal["ink"],
            "secondaryBorderColor": pal["rule"],
            "tertiaryColor": pal["paper"],
            "tertiaryTextColor": pal["ink"],
            "tertiaryBorderColor": pal["rule"],
            "lineColor": pal["muted"],
            "textColor": pal["ink"],
            "mainBkg": pal["accent_soft"],
            "nodeBorder": pal["accent"],
            "clusterBkg": pal["panel"],
            "clusterBorder": pal["rule"],
            "titleColor": pal["ink"],
            "edgeLabelBackground": pal["paper"],
            "noteBkgColor": pal["panel"],
            "noteBorderColor": pal["rule"],
            "noteTextColor": pal["ink"],
            "actorBkg": pal["accent_soft"],
            "actorBorder": pal["accent"],
            "actorTextColor": pal["ink"],
            "actorLineColor": pal["rule"],
            "signalColor": pal["muted"],
            "signalTextColor": pal["ink"],
            "labelBoxBkgColor": pal["panel"],
            "labelBoxBorderColor": pal["rule"],
            "labelTextColor": pal["ink"],
            "loopTextColor": pal["ink"],
            "activationBkgColor": pal["panel"],
            "activationBorderColor": pal["accent"],
            "sequenceNumberColor": pal["paper"],
            "sectionBkgColor": pal["accent_soft"],
            "altSectionBkgColor": pal["panel"],
            "taskBkgColor": pal["accent"],
            "taskBorderColor": pal["accent"],
            "taskTextColor": pal["paper"],
            "taskTextOutsideColor": pal["ink"],
            "doneTaskBkgColor": pal["done"],
            "doneTaskBorderColor": pal["done"],
            "critBkgColor": pal["tbc"],
            "critBorderColor": pal["tbc"],
            "todayLineColor": pal["tbc"],
            "gridColor": pal["rule"],
        },
        "flowchart": {"htmlLabels": True, "curve": "basis", "padding": 12, "nodeSpacing": 40, "rankSpacing": 56,
                      "wrappingWidth": 260},
        "sequence": {"mirrorActors": False, "actorMargin": 40},
    }


# --------------------------------------------------------------- listing

@dataclass
class FigureEntry:
    """One figure or view as the listing reports it."""

    figure: Figure
    chapter: int
    section: str | None
    source: Path | None
    outputs: dict[str, Path]
    tool: str | None
    stale: bool

    @property
    def kind(self) -> str:
        return "view" if isinstance(self.figure, View) else "figure"

    @property
    def rendered(self) -> bool:
        return ".png" in self.outputs or ".svg" in self.outputs

    @property
    def state(self) -> str:
        if self.source is None and not self.outputs:
            return "missing"
        if self.source is None:
            return "static"
        if not self.rendered:
            return "not rendered"
        return "out of date" if self.stale else "rendered"

    def to_dict(self, root: Path) -> dict:
        def rel(p: Path | None) -> str | None:
            if p is None:
                return None
            try:
                return str(p.relative_to(root))
            except ValueError:
                return str(p)
        return {"label": self.figure.label, "name": self.figure.name, "kind": self.kind,
                "caption": self.figure.caption, "chapter": self.chapter, "section": self.section,
                "anchor": self.figure.anchor, "source": rel(self.source), "tool": self.tool,
                "outputs": [rel(p) for p in self.outputs.values()], "rendered": self.rendered,
                "state": self.state}


@dataclass
class ChapterEntry:
    number: int
    key: str
    title: str
    picture: dict
    figures: list[FigureEntry] = field(default_factory=list)


@dataclass
class Listing:
    """Every chapter with its figures and views, plus diagram sources no
    figure uses."""

    project: "Project"
    chapters: list[ChapterEntry]
    unused: list[Path]
    helpers: list[Path] = field(default_factory=list)

    @property
    def entries(self) -> list[FigureEntry]:
        return [f for c in self.chapters for f in c.figures]

    @property
    def without_figures(self) -> list[ChapterEntry]:
        return [c for c in self.chapters if not c.figures]


def _newest_input(project: "Project", src: Path) -> float:
    """The newest mtime among a source and what its rendering depends on:
    the model or scripts it names, and the profile for themed Mermaid."""
    t = src.stat().st_mtime
    if src.suffix == ".mmd" and project.profile.path is not None and Path(project.profile.path).exists():
        t = max(t, Path(project.profile.path).stat().st_mtime)
    if src.suffix == ".ead":
        for dep in _ead_dependencies(src):
            if dep.exists():
                t = max(t, dep.stat().st_mtime)
    return t


def _ead_dependencies(src: Path) -> list[Path]:
    text = src.read_text()
    out = [src.parent / m for m in re.findall(r'^\s*model\s+"([^"]+)"', text, re.MULTILINE)]
    out += [src.parent / m for m in re.findall(r'script="([^"]+)"', text)]
    return out


def _is_stale(project: "Project", src: Path | None, outputs: dict[str, Path]) -> bool:
    if src is None or not outputs:
        return False
    newest = _newest_input(project, src)
    return any(p.stat().st_mtime < newest for p in outputs.values())


def _section_of(chapter: "Chapter", figure: Figure) -> str | None:
    for s in chapter.sections:
        if any(b is figure for b in s.blocks):
            return s.number
    return None


def listing(project: "Project") -> Listing:
    """Every figure and view per chapter, and the sources no figure uses."""
    ddir = project.root / "diagrams"
    chapters = []
    used: set[Path] = set()
    for ch in project.chapters:
        ce = ChapterEntry(ch.number, ch.key, ch.title, dict(ch.picture or {}))
        for f in ch.figures:
            src = source_of(f)
            outs = outputs_of(f, ddir)
            if src is not None:
                used.add(src.resolve())
                if src.suffix == ".ead":
                    used.update(d.resolve() for d in _ead_dependencies(src))
            ce.figures.append(FigureEntry(f, ch.number, _section_of(ch, f), src, outs, figure_tool(f),
                                          _is_stale(project, src, outs)))
        chapters.append(ce)
    unused: list[Path] = []
    helpers: list[Path] = []
    if ddir.is_dir():
        imported = _imported_modules(ddir, [u for u in used if u.suffix == ".py"])
        for p in sorted(ddir.iterdir()):
            if p.suffix not in SOURCE_EXTS or p.resolve() in used:
                continue
            if p.suffix == ".py" and is_helper(p, imported):
                helpers.append(p)
            else:
                unused.append(p)
    return Listing(project, chapters, unused, helpers)


_IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\b|import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*))",
                     re.MULTILINE)


def script_imports(path: Path) -> set[str]:
    """The top-level module names a Python file imports."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return set()
    out: set[str] = set()
    for m in _IMPORT.finditer(text):
        names = [m.group(1)] if m.group(1) else [n.strip() for n in m.group(2).split(",")]
        out |= {n.split(".")[0] for n in names if n}
    return out


def _imported_modules(ddir: Path, scripts: list[Path]) -> set[str]:
    """Modules the figure scripts import, followed through any module in
    ``diagrams/`` they import in turn."""
    seen: set[str] = set()
    todo = list(scripts)
    while todo:
        for name in script_imports(todo.pop()):
            if name in seen:
                continue
            seen.add(name)
            local = ddir / f"{name}.py"
            if local.exists():
                todo.append(local)
    return seen


def is_helper(path: Path, imported: set[str] = frozenset()) -> bool:
    """A ``.py`` in ``diagrams/`` that is a library for figure scripts, not a
    figure: a figure script imports it, or its name starts with ``_`` or
    ends with ``lib``."""
    stem = path.stem
    return stem in imported or stem.startswith("_") or stem.lower().endswith("lib")


# ------------------------------------------------------------- rendering

@dataclass
class RenderResult:
    entry: FigureEntry
    written: list[Path] = field(default_factory=list)
    error: DiagramError | None = None
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise DiagramError(f"{Path(cmd[0]).name} timed out after {RENDER_TIMEOUT}s") from e


def _no_bytecode(env: dict) -> dict:
    """Scripts and the view scripts arch-diagram imports run without
    writing __pycache__ into the project's diagrams/."""
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _tail(text: str, n: int = 6) -> str:
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def _place(tmp: Path, dest: Path) -> Path:
    """Move a finished output into place (never a partial file)."""
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise DiagramError(f"the renderer produced no {dest.suffix} for {dest.stem}")
    shutil.move(str(tmp), str(dest))
    return dest


def render_mermaid(src: Path, dest_dir: Path, name: str, profile: "Profile") -> list[Path]:
    """Render a ``.mmd`` file to ``<name>.svg`` and ``<name>.png`` (2x)."""
    npx = find_npx()
    if npx is None:
        raise DiagramError(f"{src.name}: Node.js (npx) is not installed", "mermaid")
    paper = profile.palette["paper"]
    written = []
    with tempfile.TemporaryDirectory(prefix="archdoc-mmd-") as td:
        cfg = Path(td) / "mermaid.json"
        cfg.write_text(json.dumps(mermaid_config(profile)))
        for ext, extra in ((".svg", []), (".png", ["-s", "2"])):
            out = Path(td) / f"{name}{ext}"
            r = _run([str(npx), "-y", MERMAID_CLI, "-q", "-i", str(src), "-o", str(out), "-c", str(cfg),
                      "-b", paper, *extra])
            if r.returncode != 0:
                raise DiagramError(f"{src.name}: mermaid-cli failed:\n{_tail(r.stderr or r.stdout)}")
            written.append(_place(out, dest_dir / f"{name}{ext}"))
    return written


def ead_views(src: Path) -> list[str]:
    """The view ids an arch-diagram view file declares, in order."""
    return re.findall(r"^\s*view\s+([A-Za-z0-9_][A-Za-z0-9_.-]*)", src.read_text(), re.MULTILINE)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def view_for(src: Path, name: str) -> str:
    """The view in a ``.ead`` file that the figure ``name`` draws."""
    views = ead_views(src)
    if not views:
        raise DiagramError(f"{src.name}: declares no view")
    if len(views) == 1:
        return views[0]
    for v in views:
        if _norm(v) == _norm(name):
            return v
    raise DiagramError(f"{src.name}: holds views {', '.join(views)}; the figure '{name}' draws the one with "
                       f"its own name, and none matches")


def render_ead(src: Path, dest_dir: Path, name: str, tool: ArchDiagram | None) -> tuple[list[Path], list[str]]:
    """Render an arch-diagram view file's view to ``<name>.svg`` and
    ``<name>.png``. Returns the files and the layout warnings."""
    if tool is None:
        raise DiagramError(f"{src.name}: arch-diagram is not installed", "arch-diagram")
    if tool.ea_py is None:
        raise DiagramError(f"{src.name}: arch-diagram at {tool.home} has no scripts/ea.py", "arch-diagram")
    vid = view_for(src, name)
    written = []
    with tempfile.TemporaryDirectory(prefix="archdoc-ead-") as td:
        r = _run([sys.executable, str(tool.ea_py), "render", str(src), "--out", td, "--view", vid],
                 cwd=src.parent, env=_no_bytecode(dict(os.environ)))
        if r.returncode != 0:
            raise DiagramError(f"{src.name}: ea.py render failed:\n{_tail(r.stderr or r.stdout, 12)}")
        for ext in (".svg", ".png"):
            written.append(_place(Path(td) / f"{vid}{ext}", dest_dir / f"{name}{ext}"))
    warnings = [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip().startswith("warning:")]
    return written, warnings


def render_script(src: Path, dest_dir: Path, name: str, profile: "Profile",
                  tool: ArchDiagram | None) -> list[Path]:
    """Run a ``.py`` figure script; it writes ``<name>.png`` / ``<name>.svg``."""
    text = src.read_text()
    needs_ea = bool(re.search(r"^\s*(from|import)\s+ealib\b", text, re.MULTILINE))
    env = dict(os.environ)
    if tool is not None and tool.scripts is not None:
        env["ARCH_DIAGRAM_SCRIPTS"] = str(tool.scripts)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(tool.scripts), env.get("PYTHONPATH")) if p)
    elif needs_ea:
        raise DiagramError(f"{src.name}: imports arch-diagram's ealib, and arch-diagram is not installed",
                           "arch-diagram")
    _no_bytecode(env)
    env["ARCHDOC_FIGURE"] = name
    env["ARCHDOC_OUT"] = str(dest_dir)
    env["ARCHDOC_PALETTE"] = json.dumps(profile.palette)
    started = time.time() - 1
    r = _run([sys.executable, src.name], cwd=src.parent, env=env)
    if r.returncode != 0:
        raise DiagramError(f"{src.name}: exited {r.returncode}:\n{_tail(r.stderr or r.stdout)}")
    written = [dest_dir / f"{name}{ext}" for ext in OUTPUT_EXTS
               if (dest_dir / f"{name}{ext}").exists() and (dest_dir / f"{name}{ext}").stat().st_mtime >= started]
    if not written:
        raise DiagramError(f"{src.name}: ran, but wrote neither {name}.png nor {name}.svg in {dest_dir}")
    return written


def svg_to_png(svg: Path, png: Path, scale: int = 2) -> Path:
    """Rasterise an SVG with headless Chrome at ``scale``."""
    exe = find_chrome()
    if exe is None:
        raise DiagramError(f"{svg.name}: no PNG, and Chrome is not installed to make one", "chrome")
    w, h = svg_size(svg)
    with tempfile.TemporaryDirectory(prefix="archdoc-svg-") as td:
        html = Path(td) / "page.html"
        html.write_text("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;padding:0;"
                        f"background:#fff}}img{{display:block;width:{w}px;height:{h}px}}</style></head><body>"
                        f"<img src='{svg.resolve().as_uri()}'></body></html>")
        out = Path(td) / "out.png"
        # Each run gets its own profile, so it never shares a profile lock or
        # DevTools port with another Chrome running at the same time. The
        # profile goes with the temporary directory.
        profile = Path(td) / "profile"
        # Chrome reports the screenshot once it has written it; from then
        # the image is the result, whatever Chrome does on shutdown (under
        # load it can hang, or exit 2 when its teardown watchdog expires).
        run = chrome.run([str(exe), "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                          "--no-default-browser-check", f"--user-data-dir={profile}",
                          f"--force-device-scale-factor={scale}", "--virtual-time-budget=2000",
                          f"--window-size={w},{h}", f"--screenshot={out}", html.as_uri()],
                         done=lambda o, e: _screenshot_reported(o + e, out) and _complete_png(out),
                         timeout=CHROME_TIMEOUT)
        if _complete_png(out) and (run.complete or run.code == 0):
            return _place(out, png)
        why = "wrote no complete screenshot" if run.code == 0 else run.why()
        raise DiagramError(f"{svg.name}: Chrome could not rasterise it ({why}):\n"
                           f"{_tail(run.output, 12) or '(no output from Chrome)'}")


CHROME_TIMEOUT = 120


def _complete_png(path: Path) -> bool:
    """A PNG with its signature and closing IEND chunk: written in full."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return data.startswith(b"\x89PNG\r\n\x1a\n") and data[-12:-4] == b"\x00\x00\x00\x00IEND"


def _screenshot_reported(log: str, out: Path) -> bool:
    return bool(re.search(r"\d+ bytes written to file " + re.escape(str(out)), log))


def svg_size(svg: Path) -> tuple[int, int]:
    """An SVG's width and height in CSS pixels, from its attributes or
    viewBox."""
    head = svg.read_text()[:4000]
    m = re.search(r"<svg\b[^>]*>", head, re.DOTALL)
    tag = m.group(0) if m else ""

    def attr(n: str) -> float | None:
        a = re.search(rf'\b{n}="([\d.]+)(px)?"', tag)
        return float(a.group(1)) if a else None
    w, h = attr("width"), attr("height")
    vb = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)"', tag)
    if (w is None or h is None) and vb:
        vw, vh = float(vb.group(1)), float(vb.group(2))
        if w is None and h is None:
            w, h = vw, vh
        elif w is None:
            w = h * vw / vh
        else:
            h = w * vh / vw
    return int(round(w or 800)), int(round(h or 600))


def render_entry(project: "Project", entry: FigureEntry, tool: ArchDiagram | None) -> RenderResult:
    res = RenderResult(entry)
    src = entry.source
    ddir = project.root / "diagrams"
    try:
        if src is None:
            raise DiagramError(f"{entry.figure.name}: no source (.mmd, .ead or .py) in diagrams/")
        if src.suffix == ".mmd":
            res.written = render_mermaid(src, ddir, entry.figure.name, project.profile)
        elif src.suffix == ".ead":
            res.written, res.warnings = render_ead(src, ddir, entry.figure.name, tool)
        else:
            res.written = render_script(src, ddir, entry.figure.name, project.profile, tool)
    except DiagramError as e:
        res.error = e
    if res.ok:
        _refresh(entry.figure, ddir)
    return res


def _refresh(figure: Figure, ddir: Path) -> None:
    for ext in OUTPUT_EXTS:
        if (ddir / f"{figure.name}{ext}").exists():
            figure.path = ddir / f"{figure.name}{ext}"
            break


def render(project: "Project", force: bool = False, names: list[str] | None = None) -> list[RenderResult]:
    """Render every figure with a source whose output is missing or older
    than its inputs (every one with ``force``). A figure used twice is
    rendered once."""
    tool = find_arch_diagram(project.root)
    out: list[RenderResult] = []
    done: dict[str, RenderResult] = {}
    for entry in listing(project).entries:
        name = entry.figure.name
        if names and name not in names:
            continue
        if name in done:
            continue
        if entry.source is None:
            res = RenderResult(entry, skipped=True)
            if not entry.outputs:
                res.error = DiagramError(f"{name}: no source (.mmd, .ead or .py) and no image in diagrams/")
        elif not force and entry.rendered and not entry.stale:
            res = RenderResult(entry, skipped=True)
        else:
            res = render_entry(project, entry, tool)
        done[name] = res
        out.append(res)
    return out


# ------------------------------------------------------------- ensure_png

def _project_for(figure: Figure, project: "Project | None") -> tuple[Path, "Profile"]:
    if project is not None:
        return project.root / "diagrams", project.profile
    base = (figure.source_file or figure.path)
    if base is None:
        raise DiagramError(f"{figure.name}: no file in diagrams/ (no source, PNG or SVG)")
    ddir = base.parent
    root = ddir.parent
    import yaml
    cfg = root / "arch-doc.yaml"
    prof_name = "profile.yaml"
    if cfg.exists():
        prof_name = (yaml.safe_load(cfg.read_text()) or {}).get("profile") or prof_name
    from .profile import from_dict
    prof_path = root / prof_name
    profile = load_profile(prof_path) if prof_path.exists() else from_dict({})
    return ddir, profile


def ensure_png(figure: Figure, project: "Project | None" = None) -> Path:
    """The figure's PNG, for the docx builder.

    Returns ``diagrams/<name>.png`` when it exists and is not older than its
    source. Otherwise renders the source (Mermaid, arch-diagram or script),
    or rasterises a static SVG with Chrome. Raises :class:`DiagramError`
    naming the missing tool when none of that is possible; it never writes a
    placeholder."""
    ddir, profile = _project_for(figure, project)
    png = ddir / f"{figure.name}.png"
    src = figure.source_file
    if src is None:
        for ext in SOURCE_EXTS:
            if (ddir / f"{figure.name}{ext}").exists():
                src = ddir / f"{figure.name}{ext}"
                break
    if png.exists() and (src is None or png.stat().st_mtime >= src.stat().st_mtime):
        return png
    if src is not None:
        tool = find_arch_diagram(ddir.parent)
        try:
            if src.suffix == ".mmd":
                render_mermaid(src, ddir, figure.name, profile)
            elif src.suffix == ".ead":
                render_ead(src, ddir, figure.name, tool)
            else:
                render_script(src, ddir, figure.name, profile, tool)
        except DiagramError as e:
            # SPEC 9: without the tool, the docx still gets the PNG already
            # rendered; the build stops only when there is none.
            if e.tool and png.exists():
                return png
            raise
        if not png.exists():
            svg = ddir / f"{figure.name}.svg"
            if svg.exists():
                svg_to_png(svg, png)
        _refresh(figure, ddir)
        if png.exists():
            return png
        raise DiagramError(f"{figure.name}: rendering produced no PNG")
    svg = ddir / f"{figure.name}.svg"
    if svg.exists():
        svg_to_png(svg, png)
        return png
    raise DiagramError(f"{figure.name}: no source (.mmd, .ead or .py) and no image in diagrams/")


# -------------------------------------------------------------------- CLI

def _picture_note(ch: ChapterEntry) -> str:
    pic = ch.picture or {}
    kind = pic.get("kind", "generated")
    src = pic.get("from")
    return f"generated {kind} picture" + (f" from {src}" if src else "")


def _tools_text(project: "Project") -> list[str]:
    ad = find_arch_diagram(project.root)
    npx = find_npx()
    lines = [f"arch-diagram: {ad.describe() if ad else 'not installed'}",
             f"mermaid: {'npx at ' + str(npx) + ' runs ' + MERMAID_CLI if npx else 'Node.js (npx) not installed'}"]
    return lines


def print_listing(lst: Listing, out=sys.stdout) -> None:
    p = lst.project
    ents = lst.entries
    nf = sum(1 for e in ents if e.kind == "figure")
    nv = len(ents) - nf
    print(f"{p.title} v{p.version}: {nf} figures, {nv} views", file=out)
    for line in _tools_text(p):
        print(line, file=out)
    root = p.root
    for ch in lst.chapters:
        print(f"\n{ch.number:>2} {ch.title}", file=out)
        if not ch.figures:
            print(f"   no figure: the deck draws its {_picture_note(ch)}", file=out)
            continue
        for e in ch.figures:
            src = str(e.source.relative_to(root)) if e.source else "no source"
            outs = ", ".join(str(o.relative_to(root)) for o in e.outputs.values()) or "nothing rendered"
            tool = f" ({e.tool})" if e.tool else ""
            sec = f" in {e.section}" if e.section else ""
            print(f"   {e.figure.label:<9} {e.figure.name}{sec}: {e.state}{tool}", file=out)
            print(f"             {src} -> {outs}", file=out)
    without = lst.without_figures
    print(f"\nChapters with no figure ({len(without)}), which get generated pictures in the deck: "
          + (", ".join(str(c.number) for c in without) or "none"), file=out)
    if lst.helpers:
        print("Helper modules the figure scripts use: " + ", ".join(str(h.relative_to(root)) for h in lst.helpers),
              file=out)
    if lst.unused:
        print("Sources no FIGURE or VIEW uses: " + ", ".join(str(u.relative_to(root)) for u in lst.unused),
              file=out)


def cli(args) -> int:
    from .project import Project
    project = Project.load(args.project)
    as_json = getattr(args, "json", False)
    results: list[RenderResult] = []
    if getattr(args, "render", False):
        results = render(project, force=getattr(args, "force", False))
    lst = listing(project)
    if as_json:
        ad = find_arch_diagram(project.root)
        data = {
            "title": project.title, "version": project.version,
            "tools": {"arch_diagram": None if ad is None else {"how": ad.how, "home": str(ad.home),
                                                               "scripts": str(ad.scripts) if ad.scripts else None,
                                                               "version": ad.version},
                      "npx": str(find_npx()) if find_npx() else None},
            "chapters": [{"number": c.number, "key": c.key, "title": c.title,
                          "figures": [e.to_dict(project.root) for e in c.figures],
                          "picture": None if c.figures else c.picture} for c in lst.chapters],
            "unused": [str(u.relative_to(project.root)) for u in lst.unused],
            "helpers": [str(h.relative_to(project.root)) for h in lst.helpers],
            "render": [{"name": r.entry.figure.name, "ok": r.ok, "skipped": r.skipped,
                        "written": [str(w.relative_to(project.root)) for w in r.written],
                        "error": str(r.error) if r.error else None, "missing_tool": r.error.tool if r.error else None,
                        "warnings": r.warnings} for r in results],
        }
        print(json.dumps(data, indent=2))
    else:
        print_listing(lst)
        if results:
            print()
            for r in results:
                name = r.entry.figure.name
                if r.error:
                    print(f"failed   {name}: {r.error}")
                elif r.skipped:
                    print(f"current  {name}")
                else:
                    print(f"rendered {name}: " + ", ".join(str(w.relative_to(project.root)) for w in r.written))
                for w in r.warnings:
                    print(f"         {w}")
            for t in sorted({r.error.tool for r in results if r.error and r.error.tool}):
                print(f"\n{INSTALL[t]}", file=sys.stderr)
    return 1 if any(r.error for r in results) else 0


__all__ = [
    "ArchDiagram", "DiagramError", "FigureEntry", "ChapterEntry", "Listing", "RenderResult", "INSTALL",
    "MERMAID_CLI", "cli", "ensure_png", "figure_tool", "find_arch_diagram", "find_chrome", "find_npx",
    "listing", "mermaid_config", "mermaid_source", "render", "svg_to_png",
]
