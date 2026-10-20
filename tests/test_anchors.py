"""Stable positional anchors, assigned in the core (SPEC 6.2)."""
from archdoc import ANCHOR_DC, ANCHOR_OPEN_ITEMS, Project

RISKS = """
- {id: RSK-01, title: A, category: architecture, owner: X, status: open}
- {id: RSK-02, title: B, category: architecture, owner: X, status: open}
"""


def test_anchors(make_project):
    root = make_project(content={
        "02-context.md": """
            # context
            Lead one.

            Lead two.

            - lead item
            FIGURE lead-fig | First figure
            ## in-scope
            P one.
            FIGURE f2 | Second figure
            """,
        "07-application.md": """
            # application
            ## components
            Para one.

            - a
            - b

            Para two.

            | h1 | h2 |
            |---|---|
            | r1 | x |
            | r2 | y |
            | r3 | z |

            - c
            - d
            - e
            - f

            REGISTER risk
            VIEW v1 | View one | application-context
            ## New Bit [new]
            New para.
            VIEW v2 | View two | logical-data
            FIGURE f3 | Third figure
            """}, registers={"risk": RISKS})
    p = Project.load(root)
    ctx = p.chapter("context")
    assert ctx.anchor == "s2"
    assert [b.anchor for b in ctx.lead] == ["s2-p1", "s2-p2", "s2-l1", "fig-1"]
    assert ctx.lead[2].item_anchors == ["s2-l1-i1"]
    assert ctx.section("in-scope").anchor == "s2-1"
    assert [b.anchor for b in ctx.section("in-scope").blocks] == ["s2-1-p1", "fig-2"]

    app = p.chapter("application")
    comp = app.section("components")
    assert comp.anchor == "s7-3"
    assert [b.anchor for b in comp.blocks] == [
        "s7-3-p1", "s7-3-l1", "s7-3-p2", "s7-3-t1", "s7-3-l2", "s7-3-t2", "view-1"]
    table, second_list, reg = comp.blocks[3], comp.blocks[4], comp.blocks[5]
    assert table.header_anchor == "s7-3-t1-h"
    assert table.row_anchors == ["s7-3-t1-r1", "s7-3-t1-r2", "s7-3-t1-r3"]
    assert second_list.item_anchors[3] == "s7-3-l2-i4"
    assert reg.row_anchors == ["s7-3-t2-r1", "s7-3-t2-r2"]
    new = app.section("new-bit")
    assert new.anchor == "s7-4" and new.number == "7.4"
    assert [b.anchor for b in new.blocks] == ["s7-4-p1", "view-2", "fig-3"]
    assert [f.anchor for f in p.figures] == ["fig-1", "fig-2", "fig-3"]
    assert [v.anchor for v in p.views] == ["view-1", "view-2"]
    tbcs = {(t.record, t.anchor) for t in p.tbcs()}
    assert tbcs == set()
    assert ANCHOR_DC == "dc" and ANCHOR_OPEN_ITEMS == "app-open-items"


def test_anchors_are_unique(make_project):
    root = make_project(content={"07-application.md": """
        # application
        ## scope
        A.
        ## components
        B.

        | a |
        |---|
        | 1 |
        """})
    p = Project.load(root)
    seen = []
    for b in p.blocks():
        seen.append(b.anchor)
        seen += getattr(b, "item_anchors", []) + getattr(b, "row_anchors", [])
    assert len(seen) == len(set(seen))
    assert [s.anchor for c in p.chapters for s in c.sections][:3] == ["s1-1", "s1-2", "s1-3"]


def test_register_tbc_takes_the_citing_row_anchor(make_project):
    root = make_project(content={"19-risks.md": "# risks\n## architecture-risks\nREGISTER risk\n"},
                        registers={"risk": "- {id: RSK-01, title: A, rating: TBC, owner: X, status: open}\n"
                                           "- {id: RSK-02, title: B, rating: TBC, owner: Y, status: open}\n"})
    p = Project.load(root)
    got = {(t.record, t.owner, t.anchor) for t in p.tbcs()}
    assert got == {("RSK-01", "X", "s19-1-t1-r1"), ("RSK-02", "Y", "s19-1-t1-r2")}
