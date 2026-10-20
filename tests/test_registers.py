"""Registers: TBC values and owners, where filters, schema validation."""
import pytest

from archdoc import Project
from archdoc.registers import Tbc, id_list, parse_conditions, parse_selector, parse_tbc

RISKS = """
- id: RSK-01
  title: Owned risk with a bare TBC
  category: architecture
  likelihood: TBC
  impact: high
  rating: high
  mitigation: "TBC: Security lead"
  owner: Integration lead
  status: open
- id: RSK-02
  title: Risk whose owner is itself to be confirmed
  category: operational
  likelihood: low
  impact: TBC
  rating: medium
  owner: "TBC: Head of Operations"
  status: mitigating
- id: RSK-03
  title: Risk with no owner
  category: architecture
  likelihood: high
  impact: low
  rating: TBC
  status: closed
- id: RSK-04
  title: Risk in dict form
  category: security
  likelihood: medium
  impact: medium
  rating: low
  mitigation: {TBC: Network lead}
  owner: Network lead
  status: open
"""


@pytest.mark.parametrize("value,expected", [
    ("TBC", Tbc(None)), ("tbc", Tbc(None)), ("TBC: Data owner", Tbc("Data owner")),
    ("TBC:Data owner ", Tbc("Data owner")), ({"TBC": "Ops"}, Tbc("Ops")), ({"TBC": None}, Tbc(None)),
    ("TBCX", None), ("not TBC", None), (3, None),
])
def test_parse_tbc(value, expected):
    assert parse_tbc(value) == expected


def test_tbc_owner_inheritance(make_project):
    p = Project.load(make_project(registers={"risk": RISKS}))
    reg = p.registers["risk"]
    r1, r2, r3, r4 = reg.records
    assert r1.get("likelihood") == Tbc("Integration lead", inherited=True)
    assert r1.get("mitigation") == Tbc("Security lead")
    assert r1.display("likelihood") == "TBC: Integration lead"
    assert r2.owner is None and r2.accountable == "Head of Operations"
    assert r2.get("impact") == Tbc("Head of Operations", inherited=True)
    assert r3.get("rating") == Tbc(None)
    assert r4.get("mitigation") == Tbc("Network lead")
    items = {(t.record, t.field): t for t in p.tbcs() if t.origin == "register"}
    assert items[("RSK-01", "likelihood")].inherited
    assert items[("RSK-02", "owner")].owner == "Head of Operations"
    assert items[("RSK-03", "rating")].owner is None
    unowned = [i for i in p.issues if i.code == "tbc-owner"]
    assert len(unowned) == 1 and "RSK-03.rating" in unowned[0].message
    assert unowned[0].source.file == "registers/risk.yaml" and unowned[0].source.line == 18


def test_chips(make_project):
    p = Project.load(make_project(registers={"risk": RISKS}))
    assert [r.chip for r in p.registers["risk"]] == ["not-started", "partial", "done", "not-started"]
    assert p.registers["risk"].type.chip("TBC") == "tbc"


def test_where_filters(make_project):
    p = Project.load(make_project(registers={"risk": RISKS}))
    reg = p.registers["risk"]
    ids = lambda w: [r.id for r in reg.filter(w)]
    assert ids("category=architecture") == ["RSK-01", "RSK-03"]
    assert ids("category!=architecture") == ["RSK-02", "RSK-04"]
    assert ids("rating=high|medium") == ["RSK-01", "RSK-02"]
    assert ids("category=architecture status=open") == ["RSK-01"]
    assert ids("likelihood=tbc") == ["RSK-01"]
    assert ids("owner='Network lead'") == ["RSK-04"]
    assert ids(None) == ["RSK-01", "RSK-02", "RSK-03", "RSK-04"]
    assert ids(parse_conditions(["status=OPEN"])) == ["RSK-01", "RSK-04"]


def test_where_on_list_fields(make_project):
    p = Project.load(make_project(registers={
        "component": """
        - {id: CMP-01, title: Api, interfaces: [INT-01, INT-02], status: built}
        - {id: CMP-02, title: Ui, interfaces: [INT-03], status: planned}
        """}))
    assert [r.id for r in p.registers["component"].filter("interfaces=int-02")] == ["CMP-01"]


def test_selector_and_condition_errors():
    assert parse_selector("risk")[0] == "risk"
    t, w = parse_selector("risk where category=architecture rating!=low")
    assert str(w) == "category=architecture rating!=low"
    with pytest.raises(ValueError):
        parse_selector("risk category=architecture")
    with pytest.raises(ValueError):
        parse_selector("risk where")
    with pytest.raises(ValueError):
        parse_conditions(["category"])


def test_schema_problems(make_project):
    p = Project.load(make_project(registers={
        "risk": """
        - {id: RSK-01, title: Fine, rating: high, status: open}
        - {id: RISK-2, title: Bad prefix, status: open}
        - {id: RSK-03, title: Bad enum, rating: huge, status: open}
        - {id: RSK-04, title: Bad status, status: pondering}
        - {id: RSK-05, title: Unknown field, colour: red, status: open}
        - {id: RSK-01, title: Duplicate, status: open}
        - {id: RSK-07, status: open}
        """,
        "control": """
        - {id: CTL-01, title: Gate, area: network, mitigates: [RSK-01, RSK-99], status: planned}
        """,
    }))
    msgs = [(i.code, i.message) for i in p.issues]
    joined = " | ".join(m for _, m in msgs)
    assert ("ids", "id 'RISK-2' does not match the risk prefix RSK-") in msgs
    assert "rating 'huge' is not one of" in joined
    assert "status 'pondering'" in joined
    assert "'colour' is not a field of risk" in joined
    assert any(c == "ids" and "duplicate id RSK-01" in m for c, m in msgs)
    assert "risk record is missing 'title'" in joined
    assert any(c == "ids" and "no risk with id 'RSK-99'" in m for c, m in msgs)
    assert "RSK-01'" not in joined.split("mitigates")[-1]


def test_values_are_normalised(make_project):
    p = Project.load(make_project(registers={
        "runbook": """
        - {id: RBK-01, title: Restart, tested: yes, test_date: 2026-11-02, status: tested, owner: Ops}
        """}))
    r = p.registers["runbook"][0]
    assert r.get("tested") == "yes" and r.get("test_date") == "2026-11-02"
    assert not p.issues


def test_bad_yaml_and_non_list(make_project):
    p = Project.load(make_project(registers={"risk": "- id: [unclosed\n", "issue": "id: ISS-01\n"}))
    codes = [(i.code, i.source.file) for i in p.issues]
    assert ("schema", "registers/risk.yaml") in codes
    assert ("schema", "registers/issue.yaml") in codes


def test_id_list():
    assert id_list([]) == "none"
    assert id_list(["RSK-01"]) == "RSK-01"
    assert id_list(["RSK-01", "RSK-02"]) == "RSK-01 and RSK-02"
    assert id_list(["RSK-01", "RSK-02", "RSK-03"]) == "RSK-01 to RSK-03"
    assert id_list(["RSK-01", "RSK-03", "RSK-04"]) == "RSK-01, RSK-03 and RSK-04"
    assert id_list(["RSK-1", "RSK-2", "RSK-3", "RSK-4"]) == "RSK-1 to RSK-4"


# ------------------------------------------------- display, ids, embedded TBCs

def test_namespaced_ids_and_prefix_lists(make_project):
    import copy
    import yaml as _yaml
    from conftest import SEED
    from archdoc.metamodel import MetamodelError, from_dict as mm_from_dict
    raw = _yaml.safe_load(SEED.read_text())
    raw["artefact_types"]["risk"]["prefix"] = ["RSK", "RISK", "SEC-RISK"]
    raw["artefact_types"]["decision"]["prefix"] = ["ADR", "DEC"]
    t = mm_from_dict(raw).artefact_types["risk"]
    assert t.prefix == "RSK" and t.prefixes == ("RSK", "RISK", "SEC-RISK")
    for good in ("RSK-01", "RISK-2", "NW-RSK-01", "NW-SEC-RISK-03", "NW-RISK-03", "RSK-CRM", "A1-B2-RSK-7"):
        assert t.matches_id(good), good
    for bad in ("RSK", "RSKX-01", "XRSK-01", "nw-RSK-01", "NW-SEC-01", "RSK--01", "SEC-RISK"):
        assert not t.matches_id(bad), bad
    dup = copy.deepcopy(raw)
    dup["artefact_types"]["issue"]["prefix"] = ["ISS", "DEC"]
    with pytest.raises(MetamodelError, match="prefix DEC is also used by decision"):
        mm_from_dict(dup)
    bad = copy.deepcopy(raw)
    bad["artefact_types"]["issue"]["prefix"] = ["ISS", "iss"]
    with pytest.raises(MetamodelError, match="prefix must be upper-case"):
        mm_from_dict(bad)
    root = make_project(registers={"risk": """
        - {id: NW-RSK-01, title: Namespaced, owner: X, status: open}
        - {id: NW-EXC-02, title: Wrong type, owner: X, status: open}
        """})
    msgs = [i.message for i in Project.load(root).issues]
    assert msgs == ["id 'NW-EXC-02' does not match the risk prefix RSK-"]


def test_shown_values_label_enums_and_statuses(make_project):
    p = Project.load(make_project(registers={
        "integration": """
        - {id: INT-01, title: Scans, pattern: api, criticality: high, owner: Ops, status: in-build}
        """,
        "business-requirement": """
        - {id: BR-01, title: Track, priority: must, owner: Ops, status: proposed}
        """}))
    r = p.registers["integration"][0]
    assert r.data["pattern"] == "api" and r.display("pattern") == "api"
    assert r.shown("pattern") == "API" and r.shown("criticality") == "High"
    assert r.shown("status") == "In build" and r.shown("title") == "Scans"
    assert p.registers["business-requirement"][0].shown("priority") == "Must"
    assert p.model.artefact_types["process-readiness"].value_label("status", "not-started") == "Not started"
    assert r.type.value_label("trigger", "api") == "api"


def test_placeholders_resolve_in_record_values(make_project):
    root = make_project(content={"07-application.md": """
        # application
        ## components
        REGISTER component
        FIGURE ctx | Context
        """}, registers={"component": """
        - id: CMP-01
          title: Intake
          description: "Shown in {fig:ctx}; see {sec:application/environments} and {count:component}"
          interfaces: ["{sec:integration/overview}", plain]
          owner: Ops
          status: built
        - id: CMP-02
          title: Broken
          description: "See {sec:nowhere/none}"
          owner: Ops
          status: built
        """})
    p = Project.load(root)
    r1, r2 = p.registers["component"].records
    assert r1.data["description"].startswith("Shown in {fig:ctx}")
    assert r1.text("description") == "Shown in Figure 1; see 7.4 and 2"
    assert r1.shown("interfaces") == "8.2, plain"
    reg = p.section("application", "components").blocks[0]
    assert reg.rows[0][2] == "Shown in Figure 1; see 7.4 and 2"
    assert reg.raw_rows[0][2].startswith("Shown in {fig:ctx}")
    xref = [i for i in p.issues if i.code == "xref"]
    assert len(xref) == 1 and xref[0].message == "CMP-02.description: {sec:nowhere/none}: section 'nowhere/none' is not in this document"
    assert xref[0].anchor == "s7-3-t1-r2" and xref[0].source.line == 7
    text, _ = p.resolve_text("{reg:CMP-01.description}")
    assert text == "Shown in Figure 1; see 7.4 and 2"


def test_short_tbc_names_the_owner_once_per_row(make_project):
    root = make_project(content={"18-transition.md": """
        # transition
        ## cutover
        REGISTER cutover-step cols id,title,start,finish,status
        REGISTER cutover-step cols id,title,start,finish,owner
        """}, registers={"cutover-step": """
        - {id: CUT-01, title: Freeze, start: TBC, finish: TBC, owner: Architecture Office, status: TBC}
        - {id: CUT-02, title: Switch, start: "TBC: Ops", finish: TBC, owner: Architecture Office, status: planned}
        """})
    p = Project.load(root)
    no_owner, with_owner = p.section("transition", "cutover").blocks
    assert no_owner.rows[0] == ["CUT-01", "Freeze", "TBC: Architecture Office", "TBC: Architecture Office",
                                "TBC: Architecture Office"]
    assert no_owner.compact_rows[0] == ["CUT-01", "Freeze", "TBC: Architecture Office", "TBC", "TBC"]
    assert no_owner.compact_rows[1] == ["CUT-02", "Switch", "TBC: Ops", "TBC: Architecture Office", "Planned"]
    assert with_owner.compact_rows[0] == ["CUT-01", "Freeze", "TBC", "TBC", "Architecture Office"]
    rec = p.registers["cutover-step"][0]
    assert rec.get("finish") == Tbc("Architecture Office", inherited=True)
    items = [(t.record, t.field) for t in p.tbcs() if t.origin == "register"]
    assert sorted(items) == [("CUT-01", "finish"), ("CUT-01", "start"), ("CUT-01", "status"),
                             ("CUT-02", "finish"), ("CUT-02", "start")]


def test_embedded_tbcs_are_collected_once_per_field(make_project):
    root = make_project(content={"19-risks.md": "# risks\n## architecture-risks\nREGISTER risk\n"},
                        registers={"risk": """
        - id: RSK-01
          title: Owned
          mitigation: "Queue and back off; TBC: Cloud Platform. Quota TBC: Vendor"
          cause: "Rate caps, size TBC"
          consequence: "See {reg:RSK-02.rating}"
          owner: Integration lead
          status: open
        - id: RSK-02
          title: Unowned
          rating: TBC
          mitigation: "Size TBC"
          status: open
        """})
    p = Project.load(root)
    got = {(t.record, t.field): (t.owner, t.inherited, t.anchor) for t in p.tbcs() if t.origin == "register"}
    assert got == {
        ("RSK-01", "mitigation"): ("Cloud Platform", False, "s19-1-t1-r1"),
        ("RSK-01", "cause"): ("Integration lead", True, "s19-1-t1-r1"),
        ("RSK-02", "rating"): (None, False, "s19-1-t1-r2"),
        ("RSK-02", "mitigation"): (None, False, "s19-1-t1-r2"),
    }
    owner_issues = sorted(i.message.split()[0] for i in p.issues if i.code == "tbc-owner")
    assert owner_issues == ["RSK-02.mitigation", "RSK-02.rating"]
