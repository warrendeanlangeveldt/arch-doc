"""Project.open_items: one resolved line per record or prose location."""
from archdoc import OpenItem, Project
from archdoc.project import one_line, tbc_sentence

REGS = {
    "risk": """
    - id: RSK-01
      title: Rate limits throttle peak scans
      likelihood: TBC
      impact: TBC
      rating: TBC
      mitigation: "Queue and back off. Quota uplift TBC: Carrier manager, requested in {sec:risks/issues}."
      owner: Integration lead
      status: open
    - id: RSK-02
      title: Coverage gaps in two depots
      mitigation: TBC
      residual: "TBC: Service owner"
      owner: Depot manager
      status: open
    - id: RSK-03
      title: Nobody owns this
      rating: TBC
      status: open
    - id: RSK-04
      title: Not cited anywhere
      rating: "TBC: Data owner"
      owner: Data owner
      status: open
    """,
}

CONTENT = {
    "19-risks.md": """
    # risks
    We list the risks here. The review date is TBC: Architecture lead, after {ch:transition} is agreed.
    ## architecture-risks
    REGISTER risk where category!=security cols id,title,rating,owner,status
    ## issues
    | Item | Detail | Note |
    |---|---|---|
    | Peering between hubs | Dev runtime subscription TBC: Cloud Platform | Size TBC: Cloud Platform |
    | Plain | nothing open | here |

    - First item, TBC.
    """,
}


def load(make_project):
    root = make_project(content=CONTENT, registers=REGS)
    # RSK-04 is filtered out of every table by giving it the security category
    text = (root / "registers" / "risk.yaml").read_text().replace(
        "title: Not cited anywhere", "title: Not cited anywhere\n  category: security")
    (root / "registers" / "risk.yaml").write_text(text)
    return Project.load(root)


def test_one_item_per_record_and_prose_location(make_project):
    p = load(make_project)
    items = p.open_items()
    assert all(isinstance(i, OpenItem) for i in items)
    assert [i.id for i in items] == ["s19-p1", "RSK-01", "RSK-02", "RSK-03",
                                     "s19-3-t1-r1", "s19-3-l1-i1", "RSK-04"]
    tbcs = p.tbcs()
    assert len(tbcs) == 12 and len(items) == 7
    by = {i.id: i for i in items}
    lead = items[0]
    assert lead.id == "s19-p1" and lead.origin == "content"
    assert lead.text == "The review date is TBC: Architecture lead, after 18 is agreed."
    assert lead.section == "19 Risks, Issues & Dependencies" and lead.section_anchor == "s19"
    assert lead.owner == "Architecture lead"

    r1 = by["RSK-01"]
    assert r1.fields == ["likelihood", "impact", "rating", "mitigation"]
    assert r1.owner == "Integration lead" and r1.owners == ["Integration lead", "Carrier manager"]
    assert not r1.inherited and r1.anchor == "s19-1-t1-r1"
    assert r1.section == "19.1 Architecture Risks" and r1.section_anchor == "s19-1"
    assert r1.text == "Rate limits throttle peak scans: Quota uplift TBC: Carrier manager, requested in 19.3."
    assert "{" not in r1.text

    r2 = by["RSK-02"]
    assert r2.owner == "Depot manager" and r2.owners == ["Depot manager", "Service owner"]
    assert r2.text == "Coverage gaps in two depots"
    assert by["RSK-03"].owner is None and by["RSK-03"].inherited is False
    r4 = by["RSK-04"]
    assert r4.anchor is None and r4.section is None and r4.owner == "Data owner"

    row = by["s19-3-t1-r1"]
    assert row.text == "Peering between hubs: Dev runtime subscription TBC: Cloud Platform"
    assert " | " not in row.text and len(row.tbcs) == 2
    assert row.owner == "Cloud Platform" and row.section == "19.3 Issues"
    assert by["s19-3-l1-i1"].owner is None


def test_inherited_flag_and_counts(make_project):
    root = make_project(content={"19-risks.md": "# risks\n## architecture-risks\nREGISTER risk\n"},
                        registers={"risk": "- {id: RSK-01, title: A, rating: TBC, impact: TBC, owner: X, "
                                           "status: open}\n"})
    p = Project.load(root)
    [item] = p.open_items()
    assert item.inherited and item.owner == "X" and item.fields == ["rating", "impact"]
    assert len(p.tbcs()) == 2


def test_tbc_context_is_resolved(make_project):
    root = make_project(content={"19-risks.md": "# risks\n## issues\nSee {sec:risks/issues}; owner TBC: Ops.\n"})
    p = Project.load(root)
    [t] = p.tbcs()
    assert t.context == "See 19.3; owner TBC: Ops." and t.key == "content:s19-3-p1"


def test_one_line_cuts_at_a_word_boundary():
    assert one_line("short **bold** text") == "short bold text"
    long = "Dev runtime subscription " * 10
    out = one_line(long, 40)
    assert len(out) <= 40 and out.endswith("…") and not out[:-1].endswith("subscript")
    assert out == "Dev runtime subscription Dev runtime…"
    assert tbc_sentence("First. Second is TBC: X. Third.") == "Second is TBC: X."
    assert tbc_sentence("No marker here.") == "No marker here."


# ------------------------------------------------- TBC as a noun is not open

import pytest  # noqa: E402

from archdoc.registers import Tbc, embedded_tbcs, tbc_markers  # noqa: E402


@pytest.mark.parametrize("text", [
    "Every TBC has an owner and a date", "Each open TBC names who confirms it", "TBCs are tracked weekly",
    "We raise a TBC when a value is missing", "The TBC list is reviewed", "Write 'TBC: owner' for a gap",
    'Mark it "TBC" and move on', "No TBC is left without an owner", "Owners of {reg:RSK-01.title} only",
])
def test_noun_and_quoted_tbc_is_not_open(text):
    assert embedded_tbcs(text) == []


@pytest.mark.parametrize("text, owners", [
    ("Hosting TBC: Cloud team", ["Cloud team"]),
    ("Due date TBC", [None]),
    ("TBC", [None]),
    ("Size TBC — Cloud team; region TBC.", ["Cloud team", None]),
    ("The date is TBC: Data owner. Every TBC has an owner.", ["Data owner"]),
    ("TBC has an owner", [None]),   # cut at the TBC, with nothing before it, it still reads as a value
])
def test_value_markers_are_open(text, owners):
    assert [t.owner for t in embedded_tbcs(text)] == owners


def test_marker_positions_are_in_the_original_text():
    text = "See {sec:risks/issues}; size TBC: Ops."
    [(a, b, t)] = tbc_markers(text)
    assert text[a:b] == "TBC: Ops" and t == Tbc("Ops")


def test_a_title_mentioning_tbc_is_not_an_open_item(make_project):
    root = make_project(content={"20-assurance.md": "# assurance\n## approval-criteria\nREGISTER acceptance-item\n"
                                 "Every TBC has an owner, and the review date is TBC: Architecture lead.\n"},
                        registers={"acceptance-item": """
        - {id: ACC-10, title: Every TBC has an owner and a date, stage: approval, owner: Architect, status: open}
        - {id: ACC-11, title: "Hosting TBC: Cloud team", stage: approval, owner: Architect, status: open}
        - {id: ACC-12, title: Backups agreed, evidence: "Restore test TBC", stage: approval, owner: Ops, status: open}
        """})
    p = Project.load(root)
    items = {i.id: i for i in p.open_items()}
    assert "ACC-10" not in items
    assert items["ACC-11"].text == "Hosting TBC: Cloud team" and items["ACC-11"].owner == "Cloud team"
    assert items["ACC-12"].text == "Backups agreed: Restore test TBC" and items["ACC-12"].owner == "Ops"
    [prose] = [i for i in items.values() if i.origin == "content"]
    assert prose.owner == "Architecture lead" and len(prose.tbcs) == 1
    assert not [i for i in p.issues if i.code == "tbc-owner"]
