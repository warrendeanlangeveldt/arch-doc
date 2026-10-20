"""The two example projects, {dep:} between them, and the CLI on both."""
import importlib.util
import json

import pytest
import yaml

from conftest import EXAMPLES, NORTHWIND_PROFILE, run_cli
from archdoc import Project

PLATFORM = EXAMPLES / "northwind-platform"
PARCELS = EXAMPLES / "northwind-parcels"


def test_examples_load_cleanly():
    for root in (PLATFORM, PARCELS):
        p = Project.load(root)
        assert not p.issues, [str(i) for i in p.issues]
        assert len(p.chapters) == 22
    assert Project.load(PLATFORM).kind == "capability"
    assert Project.load(PLATFORM).layer == "logical"
    assert Project.load(PARCELS).kind == "solution"


def test_examples_have_register_data():
    p = Project.load(PARCELS)
    for rtype in ("risk", "decision", "integration"):
        assert len(p.registers[rtype]) >= 2, rtype
    assert p.registers["risk"].get("RSK-03").title == "Carrier API rate limits throttle peak scans"
    assert all(t.owner for t in p.tbcs())
    assert len(Project.load(PLATFORM).registers["decision"]) >= 5


def test_dependency_reference_resolves_across_examples():
    p = Project.load(PARCELS)
    assert set(p.dependencies) == {"NP"}
    platform = p.dependencies["NP"]
    assert platform.title == "Northwind Platform"
    assert platform.number("application", "components") == "7.3"
    text, un = p.resolve_text("See {dep:NP:7.3} and {dep:NP:application/environments}, {dep:NP:7}, {dep:NP}.")
    assert not un
    assert text == ("See the Northwind Platform design, section 7.3 Component Design and the Northwind "
                    "Platform design, section 7.4 Environments, the Northwind Platform design, chapter 7 "
                    "Application & Component Architecture, the Northwind Platform design.")


def test_dependency_numbering_uses_the_dependency_profile(examples_copy):
    """The capability design drops application/channels, so its 7.x differs from the solution's."""
    parcels = Project.load(examples_copy / "northwind-parcels")
    assert parcels.number("application", "channels") == "7.5"
    assert parcels.dependencies["NP"].number("application", "channels") is None


def test_unresolvable_dependency_references(examples_copy):
    p = Project.load(examples_copy / "northwind-parcels")
    _, un = p.resolve_text("{dep:NP:7.9} {dep:NP:nowhere/none} {dep:ZZ:1}")
    assert [u.reason for u in un] == ["Northwind Platform has no section 7.9",
                                      "Northwind Platform has no section nowhere/none",
                                      "no depends_on, consumers or cites entry with ref 'ZZ'"]
    cfg = examples_copy / "northwind-parcels" / "arch-doc.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["depends_on"][0]["path"] = "../missing"
    cfg.write_text(yaml.safe_dump(data))
    p2 = Project.load(examples_copy / "northwind-parcels")
    _, un2 = p2.resolve_text("{dep:NP:7.3}")
    assert "no loadable path" in un2[0].reason
    assert any("depends_on NP" in i.message for i in p2.issues)


def test_dependency_cycle_is_reported(examples_copy):
    cfg = examples_copy / "northwind-platform" / "arch-doc.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["depends_on"] = [{"title": "Parcel Tracking Solution", "kind": "solution", "version": "0.1",
                           "path": "../northwind-parcels", "ref": "PTS"}]
    cfg.write_text(yaml.safe_dump(data))
    p = Project.load(examples_copy / "northwind-parcels")
    platform = p.dependencies["NP"]
    assert platform.dependencies["PTS"] is None
    assert any("cycle" in i.message for i in platform.issues)


@pytest.mark.parametrize("name,args", [
    ("northwind-platform", ["--kind", "capability", "--layer", "logical", "--title", "Northwind Platform",
                            "--short", "NP", "--version", "0.2"]),
    ("northwind-parcels", ["--kind", "solution", "--title", "Parcel Tracking Solution", "--short", "PTS",
                           "--version", "0.1", "--depends-on", "../northwind-platform:NP"]),
])
def test_init_then_numbering_matches_the_example(tmp_path, name, args):
    work = tmp_path / "examples"
    work.mkdir()
    (work / "northwind-profile.yaml").write_text(NORTHWIND_PROFILE.read_text())
    if name == "northwind-parcels":
        r = run_cli("init", "northwind-platform", "--kind", "capability", "--layer", "logical",
                    "--title", "Northwind Platform", "--short", "NP", "--version", "0.2",
                    "--profile", "northwind-profile.yaml", cwd=work)
        assert r.returncode == 0, r.stderr
    r = run_cli("init", name, "--profile", "northwind-profile.yaml", *args, cwd=work)
    assert r.returncode == 0, r.stderr
    assert "22 chapters" in r.stdout
    fresh = work / name
    example = EXAMPLES / name
    assert sorted(f.name for f in (fresh / "content").iterdir()) == \
        sorted(f.name for f in (example / "content").iterdir())
    assert sorted(f.name for f in (fresh / "registers").iterdir()) == \
        sorted(f.name for f in (example / "registers").iterdir())
    cfg = yaml.safe_load((fresh / "arch-doc.yaml").read_text())
    assert cfg["profile"] == "../northwind-profile.yaml"
    a = run_cli("-C", fresh, "numbering", "--json")
    b = run_cli("-C", example, "numbering", "--json")
    assert a.returncode == 0 and b.returncode == 0
    assert json.loads(a.stdout) == json.loads(b.stdout)
    fresh_project = Project.load(fresh)
    assert not fresh_project.issues
    sec = fresh_project.section("risks", "architecture-risks")
    text = (fresh / "content" / "19-risks.md").read_text()
    assert "## architecture-risks" in text and sec.guidance.split(":")[0][:20] in " ".join(text.split())
    assert "Register: REGISTER risk where category=architecture" in text
    reg = (fresh / "registers" / "risk.yaml").read_text()
    assert reg.rstrip().endswith("[]") and "# Status: open (not-started)" in reg


def test_init_refuses_to_overwrite(tmp_path):
    r = run_cli("init", tmp_path / "d", "--kind", "solution")
    assert r.returncode == 0, r.stderr
    (tmp_path / "d" / "content" / "01-summary.md").write_text("# summary\n## scope\nMine.\n")
    r = run_cli("init", tmp_path / "d", "--kind", "solution")
    assert r.returncode == 2 and "already exists" in r.stderr
    r = run_cli("init", tmp_path / "d", "--kind", "solution", "--force")
    assert r.returncode == 0
    assert (tmp_path / "d" / "content" / "01-summary.md").read_text() == "# summary\n## scope\nMine.\n"
    p = Project.load(tmp_path / "d")
    assert p.profile.ea_metamodel is None
    assert p.section("operations", "service-records") is None


def test_numbering_and_status_commands():
    r = run_cli("-C", PARCELS, "numbering")
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert lines[0].startswith("1 ") and lines[0].rstrip().endswith("summary")
    assert any(l.startswith("14.5") and "ServiceNow CMDB & CSDM" in l for l in lines)
    r = run_cli("-C", PARCELS, "status", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    p = Project.load(PARCELS)
    assert data["summary"]["tbcs"] == len(p.tbcs()) >= 5
    assert data["summary"]["unowned_tbcs"] == 0
    risks = next(c for c in data["chapters"] if c["key"] == "risks")
    assert risks["registers"] == (f"risk {len(p.registers['risk'])}, issue {len(p.registers['issue'])}, "
                                  f"dependency {len(p.registers['dependency'])}")
    r = run_cli("-C", PARCELS, "status")
    assert r.returncode == 0 and "Parcel Tracking Solution v0.1" in r.stdout


def test_profile_command():
    r = run_cli("-C", PARCELS, "profile", "--validate")
    assert r.returncode == 0 and "valid" in r.stdout
    r = run_cli("-C", PARCELS, "profile", "--show")
    assert r.returncode == 0
    shown = yaml.safe_load(r.stdout)
    assert shown["systems"]["itsm"]["name"] == "ServiceNow"
    assert shown["house"]["fonts"]["body"] == "IBM Plex Sans"


def test_profile_command_reports_errors(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("systems: {ea_metamodel: uml}\n")
    r = run_cli("profile", "--validate", "--file", bad)
    assert r.returncode == 1 and "ea_metamodel 'uml'" in r.stdout


@pytest.mark.parametrize("args,module", [
    (["extract", "t.docx"], "extract"), (["check"], "checks"), (["build", "docx"], "docx_build"),
    (["build", "site"], "site_build"), (["build", "deck"], "deck_build"), (["diagrams"], "diagrams"),
    (["comments", "import", "c.json"], "comments"),
])
def test_phase2_commands_say_not_built_yet(args, module):
    if importlib.util.find_spec(f"archdoc.{module}") is not None:
        pytest.skip(f"archdoc.{module} exists")
    r = run_cli("-C", PARCELS, *args)
    assert r.returncode == 2
    assert f"not built yet (archdoc/{module}.py is part of phase 2)" in r.stderr


@pytest.mark.parametrize("root", [PLATFORM, PARCELS], ids=["platform", "parcels"])
def test_examples_are_complete_check_clean_and_drawn(root):
    """The worked examples: every section filled, no check findings, and at
    least four figures, each rendered, drawn through both Mermaid and
    arch-diagram."""
    from archdoc import checks, diagrams
    p = Project.load(root)
    assert not [s.path for c in p.chapters for s in c.sections if not s.filled]
    findings = checks.run(p)
    assert not findings, [str(f) for f in findings]
    entries = diagrams.listing(p).entries
    assert len(entries) >= 4
    assert {"mermaid", "arch-diagram"} <= {e.tool for e in entries}
    assert all(e.rendered for e in entries), [e.figure.name for e in entries if not e.rendered]
    assert (root / "deck.yaml").exists()
    deck = yaml.safe_load((root / "deck.yaml").read_text())
    assert set(deck["chapters"]) == {c.key for c in p.chapters}


# ------------------------------------------------------------ core fixes

def test_dep_reference_does_not_double_the_noun(make_project):
    root = make_project(extra={"depends_on": [
        {"title": "Group Platform SAD", "ref": "GP"}, {"title": "Zone HLD", "ref": "Z"},
        {"title": "Payments Platform", "ref": "PP"}, {"title": "Data Design", "ref": "DD"}]})
    p = Project.load(root)
    assert p.resolve_text("{dep:GP}")[0] == "the Group Platform SAD"
    assert p.resolve_text("{dep:Z}")[0] == "the Zone HLD"
    assert p.resolve_text("{dep:PP}")[0] == "the Payments Platform design"
    assert p.resolve_text("{dep:DD}")[0] == "the Data Design"


def test_dep_sections_map_without_a_path(make_project):
    root = make_project(extra={"depends_on": [
        {"title": "Group Platform SAD", "ref": "GP", "version": "1.2",
         "sections": {"10": "Infrastructure", "10.2": "Hosting Model", "10.10": "Backups"}}]})
    p = Project.load(root)
    text, un = p.resolve_text("{dep:GP:10.2}, {dep:GP:10.10} and {dep:GP:10}")
    assert not un
    assert text == ("the Group Platform SAD, section 10.2 Hosting Model, the Group Platform SAD, section "
                    "10.10 Backups and the Group Platform SAD, chapter 10 Infrastructure")
    _, un = p.resolve_text("{dep:GP:10.3}")
    assert un[0].reason == "Group Platform SAD has no section 10.3 in its depends_on sections"
    assert not p.issues


def test_dep_sections_map_needs_quoted_numbers(make_project):
    root = make_project()
    (root / "arch-doc.yaml").write_text((root / "arch-doc.yaml").read_text() +
                                        "depends_on:\n- {title: X, ref: X, sections: {10.10: Backups}}\n")
    p = Project.load(root)
    assert any("quote the section numbers" in i.message for i in p.issues)


def test_exclude_drops_sections_and_chapters_and_renumbers(make_project):
    root = make_project(extra={"exclude": ["application/channels", "lifecycle", "nowhere/none"]},
                        content={"07-application.md": "# application\n## channels\nText.\n"})
    p = Project.load(root)
    assert p.section("application", "channels") is None
    assert p.chapter("lifecycle") is None and len(p.chapters) == 21
    assert p.chapter("appendix").number == 21
    msgs = [i.message for i in p.issues]
    assert "exclude: 'nowhere/none' is not a chapter or chapter/section key of the metamodel" in msgs
    assert "section 'channels' is excluded by the profile, the document kind or arch-doc.yaml exclude" in msgs


def test_init_resolves_paths_against_the_project_dir(tmp_path):
    org = tmp_path / "org"
    org.mkdir()
    (org / "profile.yaml").write_text(NORTHWIND_PROFILE.read_text())
    (tmp_path / "elsewhere").mkdir()
    # ../org/profile.yaml exists relative to the project directory, not to the cwd
    r = run_cli("init", tmp_path / "docs" / "design", "--kind", "solution",
                "--profile", "../../org/profile.yaml", cwd=tmp_path / "elsewhere")
    assert r.returncode == 0, r.stderr
    cfg = yaml.safe_load((tmp_path / "docs" / "design" / "arch-doc.yaml").read_text())
    assert cfg["profile"] == "../../org/profile.yaml"
    assert Project.load(tmp_path / "docs" / "design").profile.get("systems.itsm.name") == "ServiceNow"
    r = run_cli("init", tmp_path / "docs" / "two", "--kind", "solution", "--profile", "../org/profile.yaml",
                "--template", "missing.docx", cwd=tmp_path / "elsewhere")
    assert r.returncode == 2 and "--template missing.docx: not found" in r.stderr


def test_init_writes_no_unowned_tbc(tmp_path):
    from archdoc.registers import parse_tbc
    r = run_cli("init", tmp_path / "d", "--kind", "solution")
    assert r.returncode == 0, r.stderr
    cfg = yaml.safe_load((tmp_path / "d" / "arch-doc.yaml").read_text())
    assert cfg["author"] == {"name": "TBC: Solution Architect", "role": "Solution Architect"}
    assert cfg["owner"] == {"name": "TBC: Solution Architect"}

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)
        else:
            yield v
    tbcs = [parse_tbc(v) for v in walk(cfg) if parse_tbc(v)]
    assert tbcs and all(t.owner for t in tbcs)
    r = run_cli("init", tmp_path / "e", "--kind", "solution", "--author", "Priya Nair", "--owner", "Head of Parcels")
    cfg = yaml.safe_load((tmp_path / "e" / "arch-doc.yaml").read_text())
    assert cfg["author"] == {"name": "Priya Nair", "role": "Solution Architect"}
    assert cfg["history"][0]["author"] == "Priya Nair"


# ------------------------------------------------------ cite-only designs

def test_consumers_and_cites_are_citable_without_being_dependencies(make_project):
    root = make_project(kind="capability", extra={
        "consumers": ["Plain Consumer",
                      {"title": "Payments Solution SAD", "ref": "PAY", "sections": {"4.2": "Ledger Interface"}}],
        "cites": [{"title": "Security Pattern", "ref": "SEC", "sections": {"3": "Controls"}}]})
    p = Project.load(root)
    assert p.dependencies == {}
    text, un = p.resolve_text("{dep:PAY:4.2}; {dep:SEC:3}; {dep:PAY}")
    assert not un and not p.issues
    assert text == ("the Payments Solution SAD, section 4.2 Ledger Interface; the Security Pattern design, "
                    "chapter 3 Controls; the Payments Solution SAD")
    _, un = p.resolve_text("{dep:PAY:9.9}")
    assert un[0].reason == "Payments Solution SAD has no section 9.9 in its consumers sections"
    assert p.citation("PAY")[1] == "consumers" and p.citation("SEC")[1] == "cites"


def test_consumer_with_a_path_resolves_by_its_numbering(examples_copy):
    cfg = examples_copy / "northwind-platform" / "arch-doc.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["consumers"] = [{"title": "Parcel Tracking Solution", "kind": "solution", "ref": "PTS",
                          "path": "../northwind-parcels"}]
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    p = Project.load(examples_copy / "northwind-platform")
    assert p.dependencies == {}
    text, un = p.resolve_text("{dep:PTS:application/channels}")
    assert not un
    assert text == "the Parcel Tracking Solution design, section 7.5 User Experience & Channels"
    # the consumer's own depends_on points back here: no cycle is reported for this project
    assert not [i for i in p.issues if "cycle" in i.message]


def test_citation_validation(make_project):
    root = make_project(extra={
        "depends_on": [{"title": "A", "ref": "X"}],
        "consumers": [{"title": "B", "ref": "X"}, {"title": "C", "sections": {"1": "One"}}, {"ref": "D"}],
        "cites": [{"title": "E"}, {"title": "F", "ref": "F", "sections": ["1"]}]})
    msgs = [i.message for i in Project.load(root).issues]
    assert "consumers X: the ref is also used in depends_on; a ref names one design" in msgs
    assert "consumers[1] C: give it a ref so {dep:<ref>:n.n} can cite it" in msgs
    assert "consumers[2] needs a title" in msgs
    assert "cites[0] needs at least a title and a ref" in msgs
    assert "cites F: sections must map section numbers to titles" in msgs
