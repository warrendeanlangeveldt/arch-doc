"""Diagrams: tool detection, the listing, rendering and the docx PNG."""
import json
import os
import re
import shutil

import pytest

from conftest import run_cli
from archdoc import Project
from archdoc import diagrams as D

CHAPTERS = {
    "06-target.md": """
        # target
        ## diagram
        The whole design on one page.
        FIGURE overview | Parcel tracking in one picture
        ## principles
        FIGURE static | A hand-drawn principle sketch
    """,
    "07-application.md": """
        # application
        ## views
        VIEW components | Components | application-components
        ## components
        FIGURE missing | Not drawn yet
    """,
}

MMD = "flowchart LR\n  A[Depot scan] --> B[Tracking service]\n"
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">' \
      '<rect width="120" height="60" fill="#2F6F7C"/></svg>'


@pytest.fixture
def no_tools(monkeypatch, tmp_path):
    """No ARCH_DIAGRAM_HOME and an empty Claude directory."""
    monkeypatch.delenv("ARCH_DIAGRAM_HOME", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-empty"))
    return tmp_path


def fake_cache(root, versions):
    for v in versions:
        d = root / "plugins" / "cache" / "arch-diagram" / "arch-diagram" / v / "skills" / "arch-diagram" / "scripts"
        d.mkdir(parents=True)
        (d / "ea.py").write_text("")
    return root


# ------------------------------------------------------------- detection

def test_detects_nothing_without_home_or_cache(no_tools):
    assert D.find_arch_diagram() is None


def test_detects_arch_diagram_home(no_tools, monkeypatch, tmp_path):
    home = tmp_path / "ad"
    (home / "skills" / "arch-diagram" / "scripts").mkdir(parents=True)
    (home / "skills" / "arch-diagram" / "scripts" / "ea.py").write_text("")
    monkeypatch.setenv("ARCH_DIAGRAM_HOME", str(home))
    ad = D.find_arch_diagram()
    assert ad.how == "ARCH_DIAGRAM_HOME"
    assert ad.ea_py == home / "skills" / "arch-diagram" / "scripts" / "ea.py"
    # The scripts directory itself also works as the home.
    monkeypatch.setenv("ARCH_DIAGRAM_HOME", str(home / "skills" / "arch-diagram" / "scripts"))
    assert D.find_arch_diagram().ea_py is not None


def test_arch_diagram_home_wins_and_counts_even_without_scripts(no_tools, monkeypatch, tmp_path):
    fake_cache(tmp_path / "claude-empty", ["2.1.0"])
    monkeypatch.setenv("ARCH_DIAGRAM_HOME", str(tmp_path / "elsewhere"))
    ad = D.find_arch_diagram()
    assert ad.how == "ARCH_DIAGRAM_HOME" and ad.ea_py is None
    assert "no scripts/ea.py" in ad.describe()


def test_plugin_cache_takes_the_highest_version(no_tools, tmp_path):
    fake_cache(tmp_path / "claude-empty", ["1.0.0", "2.1.0", "10.0.1", "2.10.0"])
    ad = D.find_arch_diagram()
    assert ad.how == "the plugin cache"
    assert ad.version == "10.0.1"
    assert ad.ea_py.parts[-5] == "10.0.1"


def test_cache_versions_without_scripts_are_ignored(no_tools, tmp_path):
    fake_cache(tmp_path / "claude-empty", ["2.0.0"])
    (tmp_path / "claude-empty" / "plugins" / "cache" / "arch-diagram" / "arch-diagram" / "3.0.0").mkdir()
    assert D.find_arch_diagram().version == "2.0.0"


def test_detects_the_installed_plugins_record_and_a_skill_dir(no_tools, tmp_path):
    cdir = tmp_path / "claude-empty"
    install = tmp_path / "somewhere" / "arch-diagram"
    (install / "skills" / "arch-diagram" / "scripts").mkdir(parents=True)
    (install / "skills" / "arch-diagram" / "scripts" / "ea.py").write_text("")
    (cdir / "plugins").mkdir(parents=True)
    (cdir / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"arch-diagram@arch-diagram": [{"installPath": str(install), "version": "9.9"}]}}))
    ad = D.find_arch_diagram()
    assert ad.how == "the installed plugins record" and ad.version == "9.9"
    (cdir / "plugins" / "installed_plugins.json").unlink()
    skill = cdir / "skills" / "arch-diagram"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: arch-diagram\n---\n")
    ad = D.find_arch_diagram()
    assert ad.how == "the skill directory" and ad.ea_py is None


# ---------------------------------------------------------------- listing

def test_listing_reports_every_figure_and_chapters_without(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD, "static.svg": SVG,
                                                    "components.ead": 'view components "C" {\n}\n',
                                                    "orphan.mmd": MMD})
    p = Project.load(root)
    lst = D.listing(p)
    by = {e.figure.name: e for e in lst.entries}
    assert set(by) == {"overview", "static", "components", "missing"}
    assert by["overview"].tool == "mermaid" and by["overview"].state == "not rendered"
    assert by["overview"].section == p.number("target", "diagram")
    assert by["static"].tool is None and by["static"].state == "static" and by["static"].rendered
    assert by["components"].kind == "view" and by["components"].tool == "arch-diagram"
    assert by["missing"].state == "missing"
    assert [u.name for u in lst.unused] == ["orphan.mmd"]
    without = [c.key for c in lst.without_figures]
    assert "target" not in without and "application" not in without and "summary" in without
    assert len(without) == len(p.chapters) - 2


def test_listing_marks_out_of_date_output(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD, "overview.png": "x"})
    png = root / "diagrams" / "overview.png"
    os.utime(png, (1_000_000, 1_000_000))
    entry = next(e for e in D.listing(Project.load(root)).entries if e.figure.name == "overview")
    assert entry.state == "out of date"


def test_cli_listing_text_and_json(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD, "static.svg": SVG})
    r = run_cli("-C", root, "diagrams")
    assert r.returncode == 0, r.stderr
    assert "Test Design v0.3: 3 figures, 1 views" in r.stdout
    assert "arch-diagram: not installed" in r.stdout
    assert "Figure 1  overview in 6.3: not rendered (mermaid)" in r.stdout
    assert "no figure: the deck draws its generated layers picture from depends_on" in r.stdout
    assert "Chapters with no figure (20)" in r.stdout
    r = run_cli("-C", root, "diagrams", "--json")
    data = json.loads(r.stdout)
    target = next(c for c in data["chapters"] if c["key"] == "target")
    assert [f["name"] for f in target["figures"]] == ["overview", "static"]
    assert target["figures"][0]["source"] == "diagrams/overview.mmd"
    assert next(c for c in data["chapters"] if c["key"] == "summary")["picture"]["kind"] == "layers"


# -------------------------------------------------------------- rendering

def test_missing_tools_fail_their_figures_without_placeholders(make_project, no_tools, monkeypatch):
    monkeypatch.setattr(D, "find_npx", lambda: None)
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD,
                                                    "components.ead": 'view components "C" {\n}\n'})
    results = {r.entry.figure.name: r for r in D.render(Project.load(root))}
    assert results["overview"].error.tool == "mermaid"
    assert results["components"].error.tool == "arch-diagram"
    assert results["missing"].error is not None and results["missing"].error.tool is None
    assert results["static"].error is not None
    assert not list((root / "diagrams").glob("*.png")) and not list((root / "diagrams").glob("*.svg"))


def test_cli_prints_each_install_suggestion_once(make_project, no_tools, monkeypatch):
    root = make_project(content={"06-target.md": """
        # target
        ## diagram
        VIEW one | One | application-components
        VIEW two | Two | application-components
    """}, diagrams={"one.ead": 'view one "One" {\n}\n', "two.ead": 'view two "Two" {\n}\n'})
    r = run_cli("-C", root, "diagrams", "--render")
    assert r.returncode == 1
    assert r.stderr.count("/plugin marketplace add warrendeanlangeveldt/arch-diagram") == 1
    assert "/plugin install arch-diagram@arch-diagram" in r.stderr
    assert r.stdout.count("failed   ") == 2


def test_script_figures_run_with_this_interpreter(make_project, no_tools):
    script = ("import os, pathlib\n"
              "out = pathlib.Path(os.environ['ARCHDOC_OUT'])\n"
              "(out / (os.environ['ARCHDOC_FIGURE'] + '.svg')).write_text(" + repr(SVG) + ")\n")
    root = make_project(content=CHAPTERS, diagrams={"overview.py": script})
    results = {r.entry.figure.name: r for r in D.render(Project.load(root))}
    assert results["overview"].ok, results["overview"].error
    assert (root / "diagrams" / "overview.svg").exists()
    again = {r.entry.figure.name: r for r in D.render(Project.load(root))}
    assert again["overview"].skipped


def test_script_that_needs_ealib_fails_without_arch_diagram(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={"overview.py": "from ealib import View\n"})
    res = next(r for r in D.render(Project.load(root)) if r.entry.figure.name == "overview")
    assert res.error.tool == "arch-diagram"


def test_script_that_writes_nothing_fails(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={"overview.py": "print('hello')\n"})
    res = next(r for r in D.render(Project.load(root)) if r.entry.figure.name == "overview")
    assert "wrote neither overview.png nor overview.svg" in str(res.error)


def test_ead_view_choice(tmp_path):
    one = tmp_path / "a.ead"
    one.write_text('model "model.json"\nview ACD "A" {\n  X\n}\n')
    assert D.view_for(one, "anything") == "ACD"
    many = tmp_path / "b.ead"
    many.write_text('view ctx "A" {\n}\nview COMPONENTS "B" {\n}\n')
    assert D.view_for(many, "components") == "COMPONENTS"
    with pytest.raises(D.DiagramError, match="none matches"):
        D.view_for(many, "other")


def test_mermaid_config_uses_the_house_palette(make_project):
    p = Project.load(make_project())
    cfg = D.mermaid_config(p.profile)
    assert cfg["theme"] == "base"
    assert cfg["themeVariables"]["primaryBorderColor"] == p.profile.palette["accent"]
    assert p.profile.fonts["body"] in cfg["themeVariables"]["fontFamily"]


def test_mermaid_cli_is_pinned_to_an_exact_release():
    # Every machine renders with the same mermaid-cli, never "latest".
    assert re.fullmatch(r"@mermaid-js/mermaid-cli@\d+\.\d+\.\d+", D.MERMAID_CLI)
    assert D.MERMAID_CLI in D.INSTALL["mermaid"]


def test_mermaid_source(make_project):
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD, "static.svg": SVG})
    p = Project.load(root)
    figs = {f.name: f for f in p.figures}
    assert D.mermaid_source(figs["overview"]) == MMD
    assert D.mermaid_source(figs["static"]) is None


def test_ensure_png_returns_an_existing_png_and_fails_without_tools(make_project, no_tools, monkeypatch):
    monkeypatch.setattr(D, "find_npx", lambda: None)
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD})
    p = Project.load(root)
    fig = next(f for f in p.figures if f.name == "overview")
    with pytest.raises(D.DiagramError) as e:
        D.ensure_png(fig, p)
    assert e.value.tool == "mermaid"
    assert not (root / "diagrams" / "overview.png").exists()
    png = root / "diagrams" / "overview.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    os.utime(png, (1_000_000, 1_000_000))  # older than the source, but the tool is missing
    assert D.ensure_png(fig) == png
    missing = next(f for f in p.figures if f.name == "missing")
    with pytest.raises(D.DiagramError, match="no file in diagrams"):
        D.ensure_png(missing)


needs_npx = pytest.mark.skipif(shutil.which("npx") is None, reason="Node (npx) is not installed")
needs_chrome = pytest.mark.skipif(D.find_chrome() is None, reason="Chrome is not installed")


@needs_npx
def test_mermaid_renders_svg_and_png_at_2x(make_project):
    from PIL import Image
    root = make_project(content=CHAPTERS, diagrams={"overview.mmd": MMD})
    p = Project.load(root)
    res = next(r for r in D.render(p) if r.entry.figure.name == "overview")
    assert res.ok, res.error
    svg, png = root / "diagrams" / "overview.svg", root / "diagrams" / "overview.png"
    assert svg.exists() and png.exists()
    assert p.profile.palette["accent"].lower() in svg.read_text().lower()
    w, _ = D.svg_size(svg)
    assert Image.open(png).size[0] >= int(w * 1.9)
    fig = next(f for f in p.figures if f.name == "overview")
    assert D.ensure_png(fig, p) == png


@needs_chrome
def test_ensure_png_rasterises_a_static_svg(make_project):
    from PIL import Image
    root = make_project(content=CHAPTERS, diagrams={"static.svg": SVG})
    fig = next(f for f in Project.load(root).figures if f.name == "static")
    png = D.ensure_png(fig)
    assert png == root / "diagrams" / "static.png"
    assert Image.open(png).size == (240, 120)


def test_ead_renders_through_arch_diagram_when_installed(make_project, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    ad = D.find_arch_diagram()
    if ad is None or ad.ea_py is None or D.find_chrome() is None:
        pytest.skip("arch-diagram or Chrome is not installed")
    ead = ('metamodel archimate\n'
           'ACMP-01: Application Component "Tracking service" status=Built\n'
           'ACMP-02: Application Component "Notification service" status=Designed\n'
           'ACMP-01 -[flow]-> ACMP-02 "status changes"\n'
           'view components "Tracking components" {\n  ACMP-01\n  ACMP-02\n}\n')
    root = make_project(content=CHAPTERS, diagrams={"components.ead": ead})
    res = next(r for r in D.render(Project.load(root)) if r.entry.figure.name == "components")
    assert res.ok, res.error
    assert (root / "diagrams" / "components.png").exists() and (root / "diagrams" / "components.svg").exists()


HELPER_SCRIPT = ("import os, pathlib\n"
                 "from shared_views import svg\n"
                 "out = pathlib.Path(os.environ['ARCHDOC_OUT'])\n"
                 "(out / (os.environ['ARCHDOC_FIGURE'] + '.svg')).write_text(svg())\n")


def test_helper_modules_are_not_unused_sources(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={
        "overview.py": HELPER_SCRIPT,
        "shared_views.py": "import palette_bits\ndef svg():\n    return " + repr(SVG) + "\n",
        "palette_bits.py": "INK = '#000'\n",
        "_common.py": "", "drawlib.py": "", "stray.py": "", "orphan.mmd": MMD})
    lst = D.listing(Project.load(root))
    assert sorted(h.name for h in lst.helpers) == ["_common.py", "drawlib.py", "palette_bits.py", "shared_views.py"]
    assert sorted(u.name for u in lst.unused) == ["orphan.mmd", "stray.py"]
    r = run_cli("-C", root, "diagrams", "--json")
    data = json.loads(r.stdout)
    assert "diagrams/shared_views.py" in data["helpers"] and "diagrams/shared_views.py" not in data["unused"]


def test_rendering_scripts_leaves_no_pycache(make_project, no_tools):
    root = make_project(content=CHAPTERS, diagrams={
        "overview.py": HELPER_SCRIPT,
        "shared_views.py": "def svg():\n    return " + repr(SVG) + "\n"})
    res = next(r for r in D.render(Project.load(root)) if r.entry.figure.name == "overview")
    assert res.ok, res.error
    assert (root / "diagrams" / "overview.svg").exists()
    assert not (root / "diagrams" / "__pycache__").exists()


def real_png(tmp_path):
    from PIL import Image
    path = tmp_path / "real.png"
    Image.new("RGB", (4, 2), "#2F6F7C").save(path)
    return path


def fake_chrome(tmp_path, body):
    """A stand-in for Chrome that logs its arguments, then runs ``body``."""
    exe = tmp_path / "fake-chrome"
    log = tmp_path / "chrome-args.log"
    exe.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {log}\necho --- >> {log}\n{body}\n")
    exe.chmod(0o755)
    return exe, log


def test_each_chrome_run_has_its_own_removed_profile(make_project, monkeypatch, tmp_path):
    png = real_png(tmp_path)
    exe, log = fake_chrome(tmp_path, 'for a in "$@"; do case "$a" in --screenshot=*) '
                                     f'cp {png} "${{a#--screenshot=}}";; --user-data-dir=*) '
                                     'test -d "$(dirname "${a#--user-data-dir=}")" || exit 7;; esac; done')
    monkeypatch.setenv("CHROME_PATH", str(exe))
    root = make_project(diagrams={"a.svg": SVG, "b.svg": SVG})
    for name in ("a", "b"):
        D.svg_to_png(root / "diagrams" / f"{name}.svg", root / "diagrams" / f"{name}.png")
    runs = [r.split("\n") for r in log.read_text().strip().split("---") if r.strip()]
    dirs = [next(a for a in r if a.startswith("--user-data-dir=")).split("=", 1)[1] for r in runs]
    assert len(dirs) == 2 and dirs[0] != dirs[1]
    assert not any(os.path.exists(d) for d in dirs)
    assert all("--no-first-run" in r and "--no-default-browser-check" in r for r in runs)


def test_chrome_failure_reports_its_exit_and_stderr(make_project, monkeypatch, tmp_path):
    exe, _ = fake_chrome(tmp_path, "echo 'Failed to create a ProcessSingleton' >&2\nexit 21")
    monkeypatch.setenv("CHROME_PATH", str(exe))
    root = make_project(diagrams={"a.svg": SVG})
    with pytest.raises(D.DiagramError, match=r"exited 21[\s\S]*ProcessSingleton"):
        D.svg_to_png(root / "diagrams" / "a.svg", root / "diagrams" / "a.png")
    assert not (root / "diagrams" / "a.png").exists()
    (tmp_path / "silent").mkdir()
    exe, _ = fake_chrome(tmp_path / "silent", "exit 0")
    monkeypatch.setenv("CHROME_PATH", str(exe))
    with pytest.raises(D.DiagramError, match="wrote no complete screenshot"):
        D.svg_to_png(root / "diagrams" / "a.svg", root / "diagrams" / "a.png")


SHOT = 'for a in "$@"; do case "$a" in --screenshot=*) out="${a#--screenshot=}";; esac; done\n'


def test_a_completed_screenshot_survives_a_chrome_teardown_crash(make_project, monkeypatch, tmp_path):
    """Under load Chrome can write and report the screenshot, then exit 2
    when its teardown watchdog expires. The image is complete, so it is
    used; a truncated image is not."""
    png = real_png(tmp_path)
    exe, _ = fake_chrome(tmp_path, SHOT + f'cp {png} "$out"\necho "88 bytes written to file $out"\n'
                         'echo "Teardown watchdog expired; recording dump and terminating." >&2\nexit 2')
    monkeypatch.setenv("CHROME_PATH", str(exe))
    root = make_project(diagrams={"a.svg": SVG})
    out = D.svg_to_png(root / "diagrams" / "a.svg", root / "diagrams" / "a.png")
    assert out.read_bytes() == png.read_bytes()
    (tmp_path / "cut").mkdir()
    exe, _ = fake_chrome(tmp_path / "cut", SHOT + f'head -c 20 {png} > "$out"\necho "20 bytes written to file $out"\n'
                         'echo "Teardown watchdog expired" >&2\nexit 2')
    monkeypatch.setenv("CHROME_PATH", str(exe))
    with pytest.raises(D.DiagramError, match="exited 2"):
        D.svg_to_png(root / "diagrams" / "a.svg", root / "diagrams" / "b.png")
    assert not (root / "diagrams" / "b.png").exists()


def test_a_hung_chrome_is_killed_and_reported(make_project, monkeypatch, tmp_path):
    exe, _ = fake_chrome(tmp_path, "echo starting >&2\nsleep 30")
    monkeypatch.setenv("CHROME_PATH", str(exe))
    monkeypatch.setattr(D, "CHROME_TIMEOUT", 1)
    root = make_project(diagrams={"a.svg": SVG})
    with pytest.raises(D.DiagramError, match=r"did not exit within 1s[\s\S]*starting"):
        D.svg_to_png(root / "diagrams" / "a.svg", root / "diagrams" / "a.png")
