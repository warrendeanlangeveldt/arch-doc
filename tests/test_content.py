"""The content format: every directive, placeholder, [new] section and source line."""
import json

from archdoc import Project, inline_runs, plain
from archdoc.content import Bullets, Catalogue, Figure, Para, RegisterTable, Table, View, parse_text

RISKS = """
- {id: RSK-01, title: Rate limits, category: architecture, likelihood: medium, impact: high, rating: high, owner: Integration lead, status: open}
- {id: RSK-02, title: Coverage gaps, category: operational, likelihood: high, impact: medium, rating: high, owner: Depot manager, status: open}
- {id: RSK-03, title: Ordering, category: architecture, likelihood: medium, impact: medium, rating: medium, owner: Integration lead, status: mitigated}
- {id: RSK-04, title: Spare, category: architecture, likelihood: low, impact: low, rating: low, owner: Integration lead, status: closed}
"""

APPLICATION = """
# application
Lead-in paragraph citing {ch:application}.

<!-- a comment
that spans lines -->
## components
First paragraph, split
over two lines.

- one
- two with **bold**
  continued here
  - nested
1. first ordered

| Component | Owner |
|---|---|
| Tracking API | {p:roles.architect} |
| Notifier | TBC: Product owner |

REGISTER risk where category=architecture status!=closed cols id,title,owner,status
FIGURE tracking-context | Tracking in context of {doc:short}
VIEW app-coop | Application cooperation | integration-flows

## Delivery Notes [new]
A section the metamodel does not have, see {sec:application/delivery-notes}.

## environments
Environments come after the new section.
"""


def load(make_project, content, registers=None, **kw):
    return Project.load(make_project(content=content, registers=registers or {"risk": RISKS}, **kw))


def test_parse_every_block_kind():
    pc = parse_text(APPLICATION.lstrip("\n"), "content/07-application.md")
    assert pc.key == "application" and not pc.problems
    assert [type(b) for b in pc.lead] == [Para]
    comp = pc.sections[0]
    assert comp.heading == "components" and not comp.new
    kinds = [type(b) for b in comp.blocks]
    assert kinds == [Para, Bullets, Bullets, Table, RegisterTable, Figure, View]
    para, bullets, ordered, table, reg, fig, view = comp.blocks
    assert para.raw == "First paragraph, split over two lines."
    assert para.source.line == 7
    assert bullets.raw_items == ["one", "two with **bold** continued here", "nested"]
    assert bullets.levels == [0, 0, 1]
    assert [s.line for s in bullets.item_sources] == [10, 11, 13]
    assert ordered.ordered and ordered.raw_items == ["first ordered"]
    assert table.raw_header == ["Component", "Owner"]
    assert table.raw_rows == [["Tracking API", "{p:roles.architect}"], ["Notifier", "TBC: Product owner"]]
    assert [s.line for s in table.row_sources] == [18, 19]
    assert reg.type == "risk" and str(reg.where) == "category=architecture status!=closed"
    assert reg.columns == ["id", "title", "owner", "status"]
    assert fig.name == "tracking-context" and fig.raw_caption == "Tracking in context of {doc:short}"
    assert view.name == "app-coop" and view.raw_title == "Application cooperation"
    assert view.viewpoint_ref == "integration-flows"
    new = pc.sections[1]
    assert new.heading == "Delivery Notes" and new.new
    assert pc.sections[2].heading == "environments"


def test_parse_problems():
    pc = parse_text("text first\n# summary\n### too deep\nFIGURE nocaption\nVIEW a | b\nREGISTER\n"
                    "REGISTER risk where\nREGISTER risk sideways\n# again\n", "x.md")
    msgs = [p.message for p in pc.problems]
    assert any("text before" in m for m in msgs)
    assert any("only '#'" in m for m in msgs)
    assert any("needs a caption" in m for m in msgs)
    assert any("VIEW takes three parts" in m for m in msgs)
    assert any("REGISTER needs a type" in m for m in msgs)
    assert any("'where' with no conditions" in m for m in msgs)
    assert any("unexpected 'sideways'" in m for m in msgs)
    assert any("one '# <chapter key>'" in m for m in msgs)
    lines = sorted(p.source.line for p in pc.problems)
    assert lines == [1, 3, 4, 5, 6, 7, 8, 9]


def test_resolved_project_content(make_project):
    p = load(make_project, {"07-application.md": APPLICATION})
    ch = p.chapter("application")
    assert ch.lead[0].text == "Lead-in paragraph citing 7."
    keys = [s.key for s in ch.sections]
    assert keys == ["views", "scope", "components", "delivery-notes", "environments", "channels"]
    new = ch.section("delivery-notes")
    assert new.new and new.title == "Delivery Notes" and new.number == "7.4"
    assert p.number("application", "environments") == "7.5"
    assert new.blocks[0].text == "A section the metamodel does not have, see 7.4."
    comp = ch.section("components")
    table = comp.blocks[3]
    assert table.header == ["Component", "Owner"]
    assert table.rows == [["Tracking API", "Solution Architect"], ["Notifier", "TBC: Product owner"]]
    reg = comp.blocks[4]
    assert [r.id for r in reg.records] == ["RSK-01", "RSK-03"]
    assert reg.header == ["ID", "Risk", "Owner", "Status"]
    assert reg.rows == [["RSK-01", "Rate limits", "Integration lead", "Open"],
                        ["RSK-03", "Ordering", "Integration lead", "Mitigated"]]
    assert reg.raw_rows[0][3] == "open"
    assert reg.chips == ["not-started", "done"]
    fig, view = comp.blocks[5], comp.blocks[6]
    assert fig.label == "Figure 1" and fig.caption == "Tracking in context of TD"
    assert view.label == "View 1" and view.viewpoint == "integration-flows"
    assert view.ea_name == "Application Cooperation"
    assert p.figures == [fig] and p.views == [view]
    assert not p.unresolved()
    assert not [i for i in p.issues if i.code == "content"]


def test_section_matched_by_title_and_unknown_sections(make_project):
    p = load(make_project, {"19-risks.md": """
        # risks
        ## Architecture Risks
        REGISTER risk where category=architecture
        ## Made Up Section
        Lost text.
        """, "14-operations.md": """
        # operations
        ## service-records
        Excluded when there is no ITSM.
        """}, profile={"systems": {"itsm": {"name": "none"}}})
    assert p.section("risks", "architecture-risks").blocks[0].type == "risk"
    msgs = [i.message for i in p.issues if i.code == "content"]
    assert any("'Made Up Section' is not a section" in m for m in msgs)
    assert any("'service-records' is excluded by the profile" in m for m in msgs)


def test_unknown_and_excluded_chapters(make_project):
    p = load(make_project, {"01-x.md": "# nonsense\n", "07-a.md": "# application\n",
                            "08-b.md": "# application\n"}, kind="solution")
    msgs = [i.message for i in p.issues if i.code == "content"]
    assert any("'nonsense' is not a chapter" in m for m in msgs)
    assert any("chapter 'application' is also in" in m for m in msgs)


def test_every_placeholder(make_project):
    text = """
    # risks
    ## architecture-risks
    s={sec:risks/architecture-risks} c={ch:risks} f={fig:heat} v={view:ctx}
    n={count:risk} na={count:risk where category=architecture} nh={count:risk where rating=high}
    ids={ids:risk} ida={ids:risk where category=architecture} idn={ids:risk where rating=extreme}
    r={reg:RSK-02.owner} rt={reg:RSK-01.title}
    p={p:systems.itsm.name} pf={p:forums.design_authority.short}
    d={doc:version} dt={doc:title} do={doc:owner.name}
    FIGURE heat | Risk heat map
    VIEW ctx | Context | application-context
    """
    p = load(make_project, {"19-risks.md": text}, extra={"owner": {"name": "Head of Parcels"}})
    para = p.section("risks", "architecture-risks").blocks[0]
    assert para.text == (
        "s=19.1 c=19 f=Figure 1 v=View 1 n=4 na=3 nh=2 ids=RSK-01 to RSK-04 "
        "ida=RSK-01, RSK-03 and RSK-04 idn=none r=Depot manager rt=Rate limits p=ServiceNow pf=ARB "
        "d=0.3 dt=Test Design do=Head of Parcels")
    assert not para.unresolved


def test_unresolved_placeholders_keep_location(make_project):
    text = """
    # summary
    ## scope
    Bad {sec:nowhere/none} {ch:nowhere} {fig:missing} {view:missing} {count:widgets}
    {count:risk where colour=red} {reg:RSK-99.title} {reg:RSK-01.colour} {p:systems.ea_repository.name}
    {doc:missing} {dep:XX:1.1} {ch:summary/scope}

    - item {sec:summary/nope}
    """
    p = load(make_project, {"01-summary.md": text})
    un = p.unresolved()
    tokens = [u.token for u in un]
    assert tokens == ["{sec:nowhere/none}", "{ch:nowhere}", "{fig:missing}", "{view:missing}", "{count:widgets}",
                      "{count:risk where colour=red}", "{reg:RSK-99.title}", "{reg:RSK-01.colour}",
                      "{p:systems.ea_repository.name}", "{doc:missing}", "{dep:XX:1.1}", "{ch:summary/scope}",
                      "{sec:summary/nope}"]
    para = p.section("summary", "scope").blocks[0]
    assert "{sec:nowhere/none}" in para.text
    assert all(u.source.file == "content/01-summary.md" for u in un)
    assert un[0].source.line == 3 and un[0].anchor == "s1-1-p1"
    assert un[-1].source.line == 7 and un[-1].anchor == "s1-1-l1-i1"
    assert len([i for i in p.issues if i.code == "xref"]) == len(un)


def test_register_directive_problems(make_project):
    p = load(make_project, {"19-risks.md": """
        # risks
        ## issues
        REGISTER widget
        REGISTER risk where colour=red
        REGISTER risk cols id,colour
        """})
    reasons = [u.reason for u in p.unresolved()]
    assert "'widget' is not an artefact type" in reasons
    assert "'colour' is not a field of risk" in reasons
    reg = p.section("risks", "issues").blocks[2]
    assert reg.columns == ["id"]


def test_figure_files_and_catalogue(make_project):
    model = {"metamodel": "archimate", "objects": [
        {"id": "AC-1", "type": "Application Component"}, {"id": "AC-2", "type": "Application Component"},
        {"id": "DO-1", "type": "Data Object"}]}
    p = load(make_project, {"22-appendix.md": """
        # appendix
        ## object-guide
        CATALOGUE
        FIGURE ctx | Context
        FIGURE flow | Flow
        """}, diagrams={"model.json": json.dumps(model), "ctx.png": "x", "ctx.mmd": "graph LR", "flow.ead": "v"})
    sec = p.section("appendix", "object-guide")
    cat, ctx, flow = sec.blocks
    assert isinstance(cat, Catalogue) and cat.found
    assert cat.header == ["Object type", "Objects"]
    assert cat.rows == [["Application Component", "2"], ["Data Object", "1"]]
    assert ctx.path.name == "ctx.png" and ctx.source_file.name == "ctx.mmd"
    assert flow.path is None and flow.source_file.name == "flow.ead"
    assert not p.unresolved()


def test_catalogue_needs_an_ea_metamodel_and_model(make_project):
    p = load(make_project, {"22-appendix.md": "# appendix\n## glossary\nCATALOGUE\n"},
             profile={"systems": {"ea_metamodel": "none"}})
    reasons = [u.reason for u in p.unresolved()]
    assert "the profile names no EA metamodel" in reasons
    assert "model file diagrams/model.json not found" in reasons


def test_content_tbcs(make_project):
    p = load(make_project, {"08-integration.md": """
        # integration
        ## overview
        The retry limit is TBC: Integration lead. The protocol is TBC.
        {reg:RSK-01.owner} owns the risk; no TBCs here.

        | Interface | Version |
        |---|---|
        | Scan | TBC: API owner |
        """})
    content = [t for t in p.tbcs() if t.origin == "content"]
    assert [(t.owner, t.anchor) for t in content] == [
        ("Integration lead", "s8-2-p1"), (None, "s8-2-p1"), ("API owner", "s8-2-t1-r1")]
    assert content[0].source.line == 3


def test_inline_runs():
    runs = inline_runs("Plain **bold** and *em* with `code` and [a link](https://example.org).")
    assert runs == [("Plain ", set(), None), ("bold", {"bold"}, None), (" and ", set(), None),
                    ("em", {"em"}, None), (" with ", set(), None), ("code", {"code"}, None),
                    (" and ", set(), None), ("a link", set(), "https://example.org"), (".", set(), None)]
    assert plain("**a** _b_") == "a b"


def test_register_header_labels_from_directive_and_section(make_project):
    import yaml as _yaml
    from conftest import SEED
    raw = _yaml.safe_load(SEED.read_text())
    risks = next(c for c in raw["chapters"] if c["key"] == "risks")
    arch = next(s for s in risks["sections"] if s["key"] == "architecture-risks")
    arch["column_map"] = {"Risk ID": "id", "Risk": "title", "Rating": "rating"}
    arch["labels"] = {"rating": "Risk Rating"}
    arch["template_columns"] = [["Risk ID", "Risk", "Likelihood", "Rating"]]
    root = make_project(content={"19-risks.md": """
        # risks
        ## architecture-risks
        REGISTER risk where category=architecture cols id,title,rating,owner
        REGISTER risk cols id,title,owner labels owner="Risk Owner" title=Description
        ## operational-risks
        REGISTER risk cols id,title
        """}, registers={"risk": RISKS}, extra={"metamodel": "metamodel.yaml"})
    (root / "metamodel.yaml").write_text(_yaml.safe_dump(raw, sort_keys=False))
    p = Project.load(root)
    sec = p.section("risks", "architecture-risks")
    assert sec.labels == {"id": "Risk ID", "title": "Risk", "rating": "Risk Rating"}
    assert sec.template_columns == [["Risk ID", "Risk", "Likelihood", "Rating"]]
    first, second = sec.blocks
    assert first.header == ["Risk ID", "Risk", "Risk Rating", "Owner"]
    assert second.header == ["Risk ID", "Description", "Risk Owner"]
    assert p.section("risks", "operational-risks").blocks[0].header == ["ID", "Risk"]
    assert not p.issues, [str(i) for i in p.issues]


def test_register_label_problems(make_project):
    p = load(make_project, {"19-risks.md": """
        # risks
        ## issues
        REGISTER risk labels colour=Red
        REGISTER risk labels owner
        """})
    assert "label for 'colour', not a field of risk" in [u.reason for u in p.unresolved()]
    assert any("must be field=" in i.message for i in p.issues if i.code == "content")


def test_section_label_validation():
    import copy
    import pytest as _pytest
    import yaml as _yaml
    from conftest import SEED
    from archdoc.metamodel import MetamodelError, from_dict as mm_from_dict
    raw = _yaml.safe_load(SEED.read_text())
    bad = copy.deepcopy(raw)
    risks = next(c for c in bad["chapters"] if c["key"] == "risks")
    risks["sections"][0]["column_map"] = {"Colour": "colour"}
    with _pytest.raises(MetamodelError, match="maps to 'colour'"):
        mm_from_dict(bad)


def test_catalogue_totals_placeholder(make_project):
    model = {"objects": [{"id": "A1", "type": "Application Component"}, {"id": "A2", "type": "Application Component"},
                         {"id": "D1", "type": "Data Object"}],
             "relationships": [{"from": "A1", "to": "D1", "type": "access"}]}
    p = load(make_project, {"22-appendix.md": """
        # appendix
        ## object-guide
        The model holds {cat:objects} objects and {cat:relationships} relationships: {cat:Application Component} components, {cat:data-object} data object.
        Missing {cat:Node}.
        CATALOGUE
        """}, diagrams={"model.json": json.dumps(model)})
    paras = p.section("appendix", "object-guide").blocks
    assert paras[0].text == ("The model holds 3 objects and 1 relationships: 2 components, 1 data object. "
                             "Missing {cat:Node}.")
    assert [u.reason for u in paras[0].unresolved] == [
        "the model has no objects of type 'Node' (it has Application Component, Data Object)"]


def test_catalogue_placeholder_uses_the_catalogue_model_path(make_project):
    model = {"objects": [{"id": "A1", "type": "Node"}], "relationships": []}
    p = load(make_project, {"22-appendix.md": "# appendix\n## object-guide\n{cat:objects}\nCATALOGUE diagrams/ea.json\n"},
             diagrams={"ea.json": json.dumps(model)})
    assert p.section("appendix", "object-guide").blocks[0].text == "1"
    p2 = load(make_project, {"22-appendix.md": "# appendix\n## object-guide\n{cat:objects}\n"}, name="doc2")
    assert "model file diagrams/model.json not found" in p2.unresolved()[0].reason
