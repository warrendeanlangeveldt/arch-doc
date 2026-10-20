"""The checks (SPEC 7): each catches its defect on a failing fixture and stays
silent on the corrected one.

The corrected fixture is ``tests/fixtures/checks/clean``: a five-chapter
solution design (``doc``) on a dependency (``platform``). Every check must
find nothing there. Each case below copies it, introduces one real defect
and expects one finding; the clean original is the corrected fixture.
"""
import importlib.util
import json
import shutil
import sys
import types
from pathlib import Path

import pytest
import yaml

from conftest import CLI, EXAMPLES, ROOT, SEED, run_cli

from archdoc import Project
from archdoc import checks
from archdoc.checks import Finding
from archdoc.registers import is_owner, owner_problem

CLEAN = ROOT / "tests" / "fixtures" / "checks" / "clean"


class Fixture:
    """A copy of the clean fixture that a test can break."""

    def __init__(self, root: Path):
        self.root = root
        self.doc = root / "doc"
        self.platform = root / "platform"

    def edit(self, rel: str, old: str, new: str, project: str = "doc") -> "Fixture":
        path = (self.doc if project == "doc" else self.platform) / rel
        text = path.read_text()
        assert old in text, f"{old!r} not in {rel}"
        path.write_text(text.replace(old, new, 1))
        return self

    def append(self, rel: str, text: str, project: str = "doc") -> "Fixture":
        path = (self.doc if project == "doc" else self.platform) / rel
        path.write_text(path.read_text().rstrip("\n") + "\n\n" + text.strip("\n") + "\n")
        return self

    def config(self, **changes) -> "Fixture":
        path = self.doc / "arch-doc.yaml"
        data = yaml.safe_load(path.read_text())
        for k, v in changes.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        return self

    def findings(self, project: str = "doc") -> list[Finding]:
        return checks.run(Project.load(self.doc if project == "doc" else self.platform))


@pytest.fixture
def fx(tmp_path):
    shutil.copytree(CLEAN, tmp_path / "fx")
    return Fixture(tmp_path / "fx")


def only(findings, check_id, severity=None):
    return [f for f in findings if f.id == check_id and (severity is None or f.severity == severity)]


def show(findings):
    return "\n".join(str(f) for f in findings)


# ------------------------------------------------------------ the fixture

def test_clean_fixture_has_no_findings(fx):
    found = fx.findings()
    assert found == [], show(found)


def test_fixture_metamodel_is_the_seed_trimmed():
    seed = yaml.safe_load(SEED.read_text())
    mm = yaml.safe_load((CLEAN / "doc" / "metamodel.yaml").read_text())
    by_key = {c["key"]: c for c in seed["chapters"]}
    assert [c["key"] for c in mm["chapters"]] == ["application", "integration", "decisions", "risks", "appendix"]
    for c in mm["chapters"]:
        assert c == by_key[c["key"]], f"fixture chapter {c['key']} drifted from the seed"
    # Types and viewpoints by key: an additive change to a type in the seed
    # (a new label, say) needs no fixture change.
    assert set(mm["artefact_types"]) == set(seed["artefact_types"])
    assert set(mm["viewpoints"]) == set(seed["viewpoints"])


def test_finding_shape(fx):
    fx.edit("content/04-risks.md", "TBC: Data owner.", "TBC.")
    f = only(fx.findings(), "tbc-owner")[0]
    assert f.severity == "error" and f.source.file == "content/04-risks.md" and f.source.line == 3
    assert f.anchor == "s4-p1"
    d = f.to_dict()
    assert d == {"id": "tbc-owner", "severity": "error", "message": f.message, "source": "content/04-risks.md:3",
                 "file": "content/04-risks.md", "line": 3, "anchor": "s4-p1"}
    assert str(f).startswith("content/04-risks.md:3: error [tbc-owner] ") and str(f).endswith("(#s4-p1)")


# -------------------------------------------- the defects found by hand
#
# (id, severity, file, old, new, a fragment the message must carry)

DEFECTS = {
    # 1. Prose count against its table: "four points" next to five rows.
    "prose-vs-table-colon": ("count-prose", "error", "content/01-application.md",
                             "People take part at five points:", "People take part at four points:",
                             "table below, which has 5 rows"),
    "prose-vs-table-header": ("count-prose", "error", "content/01-application.md",
                              "People take part at five points:", "People take part at four points.",
                              "which has 5 rows"),
    # 2. Prose count against its register.
    "prose-vs-register": ("count-prose", "error", "content/04-risks.md", "records ten risks",
                          "records eight risks", "the risk register has 10"),
    "prose-filtered-by-modifier": ("count-prose", "error", "content/04-risks.md", "records ten risks",
                                   "records four architecture risks", "6 matching 'architecture'"),
    "prose-part-larger-than-whole": ("count-prose", "error", "content/02-integration.md",
                                     "shows them.", "shows them. Seven integrations are file-based.",
                                     "has only 5"),
    # 3. Contents and cross-references.
    "toc-skips-a-chapter": ("xref", "error", "content/05-appendix.md",
                            "| 3 | Local Architecture Decisions, Deviations & Exceptions |\n", "",
                            "skips chapter 3 Local Architecture Decisions"),
    "toc-misnames-a-chapter": ("xref", "error", "content/05-appendix.md",
                               "| 4 | Risks, Issues & Dependencies |", "| 4 | Runbooks |", "but 4 is"),
    "literal-section-wrong-title": ("xref", "error", "content/02-integration.md", "The design decisions",
                                    "See Section 3.1: issues. The design decisions",
                                    "cited as 'issues', but 3.1 is 'Local Architecture Decisions'"),
    "literal-section-missing": ("xref", "error", "content/02-integration.md", "The design decisions",
                                "See section 9.2. The design decisions", "no section 9.2"),
    "literal-section-wrong-topic": ("xref", "warn", "content/02-integration.md", "{sec:decisions/decisions}.",
                                    "section 2.1.", "looks like section 3.1 Local Architecture Decisions"),
    "placeholder-wrong-topic": ("xref", "warn", "content/02-integration.md", "{sec:decisions/decisions}.",
                                "{sec:integration/views}.", "looks like section 3.1 Local Architecture Decisions"),
    "unresolved-placeholder": ("xref", "error", "content/02-integration.md", "{sec:decisions/decisions}.",
                               "{sec:decisions/nowhere}.", "{sec:decisions/nowhere}"),
    # 4. A stale version in a v0.3 document.
    "stale-version": ("version", "error", "content/03-decisions.md", "We record",
                      "This document (v0.1) is not yet submitted. We record", "'v0.1' but this document is version 0.3"),
    # 5. An appendix row says a view that exists was not produced.
    "view-said-not-produced": ("figure", "error", "content/05-appendix.md",
                               "| {view:int-flows} | Integration Flows | Produced |",
                               "| {view:int-flows} | Integration Flows | Not produced |", "has it as View 2"),
    # 6. Two places disagree: four secrets in the component register, five later.
    "two-places-disagree": ("count-prose", "warn", "content/01-application.md", "holds four secrets",
                            "holds five secrets", "says Four secrets for secret store, but content/01-application.md:20 says five"),
    # 7. The figure says TBC where the table says read.
    "figure-tbc-vs-table": ("figure-table", "warn", "diagrams/access.mmd", "-->|read| TH", "-->|read access TBC| TH",
                            "but the table at content/01-application.md:"),
    "figure-pattern-vs-register": ("figure-table", "warn", "diagrams/int-flows.mmd", "-->|api| APP01",
                                   "-->|file| APP01", "INT-02 pattern is 'api'"),
    # 8. Exceptions out of view order.
    "exceptions-cross-views": ("ids", "warn", "content/03-decisions.md",
                               "| {view:app-context} | EXC-03 |\n| {view:int-flows} | EXC-04 |",
                               "| {view:app-context} | EXC-04 |\n| {view:int-flows} | EXC-03 |",
                               "sequences cross"),
    # 9. A failure-handling table with rows for three of four integrations.
    "per-record-table-misses-rows": ("empty", "error", "content/02-integration.md",
                                     "| INT-03 | Rejected notification | Bounce report | Resend once |\n", "",
                                     "covers 3 of the 4 records in 2.2 Integration Overview; missing INT-03"),
    # 10. Approval scope: approved in one place, not reviewed in another.
    "approved-and-not-reviewed": ("consistency", "warn", "content/03-decisions.md",
                                  "approved the incumbent design", "approved the network design",
                                  "'has not been reviewed' contradicts 'approved the network design' at content/03-decisions.md:2"),
    # 12. A TBC with no owner.
    "tbc-without-owner": ("tbc-owner", "error", "content/04-risks.md", "TBC: Data owner.", "TBC.", "no owner"),
    "tbd-for-tbc": ("tbc-owner", "error", "content/04-risks.md", "TBC: Data owner.", "TBD.", "'TBD' is not a value"),
    # Other checks.
    "unknown-id-in-prose": ("ids", "error", "content/04-risks.md", "across", "(and RSK-11) across",
                            "RSK-11 is not in any register"),
    "empty-section": ("empty", "error", "content/03-decisions.md", "REGISTER decision\n", "",
                      "3.1 Local Architecture Decisions has no content"),
    "only-empty-register": ("empty", "error", "content/04-risks.md", "REGISTER issue\n",
                            "REGISTER issue where severity=critical\n", "only empty register tables"),
    "figure-never-referenced": ("figure", "error", "content/01-application.md",
                                "{fig:access} shows who reads and writes tracking data.", "We list access below.",
                                "Figure 1 'access' is never referenced"),
    "caption-count": ("figure", "warn", "content/02-integration.md", "Tracking integration flows",
                      "Six integrations and their flows", "has only 5"),
    "dependency-internals": ("boundary", "warn", "content/01-application.md", "The secret store holds",
                             "The partition manager rebalances our topics. The secret store holds",
                             "'partition manager' is an internal component of Northwind Platform (CMP-02)"),
    "template-guidance-left": ("stale-template", "error", "content/04-risks.md", "The register records",
                               "[Write this section last.] The register records", "[Write this section last.]"),
    "template-field-left": ("stale-template", "error", "content/04-risks.md", "The register records",
                            "[Solution / Project name] The register records", "[Solution / Project"),
    "metamodel-guidance-left": ("stale-template", "error", "content/02-integration.md", "Every new interface",
                                "For each interface that is new or changed, give the contract a builder needs at "
                                "design level. Every new interface",
                                "the metamodel's guidance"),
    "marketing-word": ("voice", "warn", "content/04-risks.md", "The register records",
                       "We deliver a seamless handover. The register records", "'seamless': a marketing word"),
    "reversal": ("voice", "warn", "content/04-risks.md", "The register records",
                 "It's not a queue, it's a buffer. The register records", "a rhetorical reversal"),
    "self-reference": ("voice", "warn", "content/04-risks.md", "The register records",
                       "This section lists the risks. The register records", "the document talking about itself"),
}


@pytest.mark.parametrize("name", sorted(DEFECTS))
def test_defect_is_caught_and_corrected_fixture_is_clean(fx, name):
    check_id, severity, rel, old, new, fragment = DEFECTS[name]
    assert not only(fx.findings(), check_id), "the corrected fixture must be clean"
    fx.edit(rel, old, new)
    found = only(fx.findings(), check_id, severity)
    assert any(fragment in f.message for f in found), f"{name}: expected '{fragment}' in\n{show(fx.findings())}"


# --------------------------------------------------- per-check detail

def test_count_model_catalogue_against_register(fx):
    """2. The EA catalogue counts 8 risks while the risk register has 10."""
    path = fx.doc / "diagrams" / "model.json"
    model = json.loads(path.read_text())
    model["objects"] = [o for o in model["objects"] if o.get("ref") not in ("RSK-09", "RSK-10")]
    path.write_text(json.dumps(model))
    found = only(fx.findings(), "count-model")
    assert len(found) == 1 and found[0].severity == "error"
    assert "counts 8 Risk objects; the risk register has 10 (6 in 4.1, 4 in 4.2" in found[0].message
    assert found[0].anchor and found[0].anchor.startswith("s5-3-t1-r")


def test_count_model_plain_catalogue_table(fx):
    fx.append("content/05-appendix.md", "\n| Object type | Count |\n|---|---|\n| Risk | 8 |\n| Glossary term | 2 |\n")
    found = only(fx.findings(), "count-model")
    assert [f.message.split(";")[0] for f in found] == ["the EA table counts 8 Risk objects"]


def test_tbc_in_register_without_owner_is_folded_from_the_core(fx):
    fx.edit("registers/glossary-term.yaml", "definition: A site where parcels are sorted", "definition: TBC")
    found = only(fx.findings(), "tbc-owner")
    assert len(found) == 1 and "GLO-02.definition is TBC with no owner" in found[0].message
    assert found[0].source.file == "registers/glossary-term.yaml" and found[0].anchor == "s5-1-t1-r2"


def test_tbc_in_arch_doc_yaml_falls_to_the_document_owner(fx):
    assert not only(fx.findings(), "tbc-owner")  # author.team: TBC, owner Head of Parcels
    fx.config(owner=None)
    found = only(fx.findings(), "tbc-owner")
    assert [f.message for f in found] == ["arch-doc.yaml author.team is TBC and the document has no owner to confirm it"]


@pytest.mark.parametrize("edit, expected", [
    ("duplicate", "duplicate id RSK-02"),
    ("prefix", "id 'RISK-03' does not match the risk prefix RSK-"),
])
def test_ids_from_the_core_are_folded(fx, edit, expected):
    if edit == "duplicate":
        fx.edit("registers/risk.yaml", "id: RSK-03,", "id: RSK-02,")
    else:
        fx.edit("registers/risk.yaml", "id: RSK-03,", "id: RISK-03,")
    assert any(expected in f.message for f in only(fx.findings(), "ids", "error")), show(fx.findings())


def test_unknown_id_in_a_register_field(fx):
    fx.edit("registers/integration.yaml", "source: APP-02", "source: APP-09")
    found = only(fx.findings(), "ids")
    assert any("APP-09 is not in any register (cited by INT-01.source)" in f.message for f in found)


def test_ids_of_a_dependency_are_known(fx):
    fx.edit("content/04-risks.md", "across", "(on the platform's CMP-02) across")
    assert not only(fx.findings(), "ids")


def test_layer_bans_products_ips_and_profile_systems_in_logical_designs(fx):
    fx.config(layer="logical", banned_terms=["Hub X"])
    assert not only(fx.findings(), "layer"), "the clean fixture is already logical"
    fx.append("content/01-application.md", "\nSecrets live in Key Vault inside 10.20.0.0/16. Alerts go to "
              "Datadog and Hub X.\n")
    msgs = [f.message for f in only(fx.findings(), "layer", "error")]
    assert any("'Key Vault' in a logical design (a cloud product)" in m for m in msgs)
    assert any("'10.20.0.0/16' (ip address)" in m for m in msgs)
    assert any("'Datadog' in a logical design (the profile's monitoring system; write 'monitoring platform')" in m
               for m in msgs)
    assert any("'Hub X'" in m for m in msgs)


def test_layer_reads_figure_sources(fx):
    fx.config(layer="logical")
    fx.edit("diagrams/int-flows.mmd", "MSG[Messaging service]", "MSG[Service Bus]")
    found = only(fx.findings(), "layer")
    assert len(found) == 1 and "'Service Bus' in View 2's source" in found[0].message
    assert found[0].source.file == "diagrams/int-flows.mmd" and found[0].source.line == 4


def test_layer_allows_products_in_physical_designs(fx):
    fx.append("content/01-application.md", "\nSecrets live in Key Vault inside 10.20.0.0/16.\n")
    assert not only(fx.findings(), "layer")


def test_boundary_capability_naming_a_consumers_internals(fx):
    """The platform (capability) names a part of the tracking service that
    the tracking service does not expose."""
    fx.append("content/06-target.md", "The secret store of the tracking service caches tokens.", project="platform")
    found = only(fx.findings("platform"), "boundary")
    assert len(found) == 1 and "the consumer Parcel Tracking (CMP-04)" in found[0].message


def test_figure_missing_and_unrendered(fx):
    (fx.doc / "diagrams" / "access.svg").unlink()
    found = only(fx.findings(), "figure")
    assert [f.severity for f in found] == ["warn"] and "not rendered yet" in found[0].message
    (fx.doc / "diagrams" / "access.mmd").unlink()
    found = only(fx.findings(), "figure")
    assert [f.severity for f in found] == ["error"] and "no diagrams/access.png" in found[0].message


def test_figure_unused_diagram_source(fx):
    (fx.doc / "diagrams" / "spare.mmd").write_text("flowchart LR\n  A --> B\n")
    found = only(fx.findings(), "figure")
    assert [(f.severity, f.message) for f in found] == [("warn", "diagrams/spare.mmd is not used by any FIGURE or VIEW")]


def test_views_table_says_produced_for_a_view_the_document_lacks(fx):
    fx.edit("content/05-appendix.md", "| {view:int-flows} | Integration Flows | Produced |",
            "| {view:int-flows} | Integration Flows | Produced |\n| Data Access Matrix | Data Access Matrix | Produced |")
    found = only(fx.findings(), "figure")
    assert len(found) == 1 and found[0].severity == "warn" and "no Data Access Matrix VIEW" in found[0].message


def test_figure_table_on_ead_views(fx):
    """An .ead view's model object whose relationship label contradicts the
    access table."""
    (fx.doc / "diagrams" / "access.mmd").unlink()
    (fx.doc / "diagrams" / "access.ead").write_text(
        'model "access-model.json"\n\nview ACC "Access" {\n  ACT-01\n  DOBJ-01\n}\n')
    (fx.doc / "diagrams" / "access-model.json").write_text(json.dumps({
        "objects": [{"id": "ACT-01", "type": "Business Actor", "name": "Customer service"},
                    {"id": "DOBJ-01", "type": "Data Object", "name": "Tracking history"}],
        "relationships": [{"from": "ACT-01", "to": "DOBJ-01", "type": "access", "label": "read access TBC"}]}))
    found = only(fx.findings(), "figure-table")
    assert len(found) == 1 and "'Customer service → Tracking history' is labelled 'read access TBC'" in found[0].message


def test_empty_optional_section_and_section_saying_why(fx):
    fx.edit("content/04-risks.md", "REGISTER issue\n", "No issues are open.\n")
    assert not only(fx.findings(), "empty")


def test_per_record_table_with_an_all_other_row_covers_the_rest(fx):
    fx.edit("content/02-integration.md", "| INT-03 | Rejected notification | Bounce report | Resend once |",
            "| All other integrations | Delivery fails | Error alert | Retry |")
    assert not only(fx.findings(), "empty")


def test_covers_key_alone_asks_for_every_record(fx):
    # The metamodel's `covers:` names the register even when the guidance
    # does not say "For each ...".
    fx.edit("metamodel.yaml", "guidance: For each integration, name the failure", "guidance: Name the failure")
    fx.edit("content/02-integration.md", "| INT-03 | Rejected notification | Bounce report | Resend once |\n", "")
    found = only(fx.findings(), "empty")
    assert len(found) == 1 and "missing INT-03" in found[0].message, show(found)
    fx.edit("metamodel.yaml", "    covers: integration\n", "")
    assert not only(fx.findings(), "empty")


def test_version_exemptions(fx):
    fx.append("content/02-integration.md", "\nCarrier links use TLS v1.2.\n\n"
              "| Version | Date | Change |\n|---|---|---|\n| v0.1 | 2026-09-01 | First draft |\n")
    assert not only(fx.findings(), "version")


def test_voice_ignores_quoted_text(fx):
    fx.append("content/04-risks.md", 'We avoid words such as "seamless" in our designs.')
    assert not only(fx.findings(), "voice")


# ------------------------------------------------------------ precision

PRECISION = """
Two integrations are file-based at most.
INT-01 and INT-02 are the two integrations that carry events.
Each depot runs two scanners for 24 hours a day.
Retries happen three times over five minutes.
We keep 30 days of scan history and 2 years of audit records.
Section 4 of the carrier agreement sets the rate limit.
Version 2 of the carrier API is due in March, and phase 2 adds three depots.
Two to three carriers join next year.
The ARB will approve the network design once the review closes.
The platform offers an event broker, described in {dep:NP:7}.
View 1 and Figure 1 come first.
The platform design records twelve components of its own in {dep:NP}.
The service targets 99.9% availability with a four-hour recovery time.
Peak load is 2,000 scans a minute, and releases happen every two weeks.
We run three environments: development, test and production. There are three environments.
Two of the five integrations are new, and each of the 4 components logs its errors.
We upgrade to v2.0 of the carrier API next quarter, and carrier links use TLS v1.2.
The integration in section 2.2 uses events. See section 4.3 for open issues.
The ARB approved the design subject to conditions.
Parcel history stays online for twelve months or eighteen months; we choose eighteen months.

| Requirement | Section | Detail |
|---|---|---|
| Scan latency | 2.2 | The queue absorbs depot peaks |
| Label uptime | 2.4 | Labels wait in a queue |
| History lookup | 1.3 | The tracking API answers it |

| View | Supports | Viewpoint |
|---|---|---|
| {view:app-context} | {sec:application/views} | Application Cooperation |
| {view:int-flows} | {sec:integration/views} | Layered |
| {view:app-context} | {sec:application/components} | Application Structure |

| Component | Test | Production | Peak |
|---|---|---|---|
| Tracking API | One replica | Two replicas | Three replicas |

Each quality target in {sec:integration/acceptance} has a test. That departure needs approval and is
recorded in {sec:decisions/deviations}. Integrations, their owners and contracts are in
{sec:integration/overview}.
"""


def test_tricky_but_correct_prose_has_no_findings(fx):
    fx.edit("content/04-risks.md", "## architecture-risks", PRECISION.strip() + "\n\n## architecture-risks")
    (fx.platform / "content" / "07-application.md").write_text("# application\n\n## components\nThe parts.\n")
    found = fx.findings()
    assert found == [], show(found)


# ------------------------------------------------------------- the CLI

def test_cli_check_json_and_exit_codes(fx):
    r = run_cli("-C", fx.doc, "check", "--json")
    assert r.returncode == 0 and json.loads(r.stdout) == []
    fx.edit("content/04-risks.md", "TBC: Data owner.", "TBC.")
    r = run_cli("-C", fx.doc, "check", "--json")
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert [d["id"] for d in data] == ["tbc-owner"]
    assert set(data[0]) == {"id", "severity", "message", "source", "file", "line", "anchor"}
    r = run_cli("-C", fx.doc, "check")
    assert r.returncode == 1 and r.stdout.strip().endswith("1 errors, 0 warnings")


def test_cli_check_warnings_alone_exit_zero(fx):
    fx.edit("content/04-risks.md", "The register records", "We deliver a seamless handover. The register records")
    r = run_cli("-C", fx.doc, "check")
    assert r.returncode == 0 and "0 errors, 1 warnings" in r.stdout


def _cli_module():
    spec = importlib.util.spec_from_file_location("archdoc_cli_for_checks", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_refuses_on_check_errors_unless_forced(fx, monkeypatch, capsys):
    cli = _cli_module()
    built = []
    fake = types.ModuleType("archdoc.checks_fake_build")
    fake.build = lambda p, out_dir=None: built.append(p.title) or []
    monkeypatch.setitem(sys.modules, "archdoc.checks_fake_build", fake)
    monkeypatch.setitem(cli.BUILDERS, "docx", "checks_fake_build")
    assert cli.main(["-C", str(fx.doc), "build", "docx"]) == 0 and built == ["Parcel Tracking"]
    fx.edit("content/04-risks.md", "TBC: Data owner.", "TBC.")
    assert cli.main(["-C", str(fx.doc), "build", "docx"]) == 1 and len(built) == 1
    err = capsys.readouterr().err
    assert "[tbc-owner]" in err and "1 check errors; fix them or pass --force" in err
    assert cli.main(["-C", str(fx.doc), "build", "docx", "--force"]) == 0 and len(built) == 2


def test_status_counts_findings_per_chapter(fx):
    fx.edit("content/04-risks.md", "TBC: Data owner.", "TBC.")
    r = run_cli("-C", fx.doc, "status", "--json")
    data = json.loads(r.stdout)
    assert data["summary"]["checks"] == 1
    assert [c["findings"] for c in data["chapters"]] == ["0", "0", "0", "1", "0"]


# ------------------------------------------------------------ the examples

@pytest.mark.parametrize("example", ["northwind-parcels", "northwind-platform"])
def test_examples_load_and_check(example):
    """The checks run on both examples without failing. Zero errors on them
    is the examples' definition of done (SPEC 11), checked by
    test_examples_have_no_check_errors once they are complete."""
    found = checks.run(Project.load(EXAMPLES / example))
    assert all(f.id in checks.CHECK_IDS + ("schema", "content") for f in found)
    assert all(f.severity in ("error", "warn") for f in found)


def test_deck_yaml_text_is_checked(fx):
    (fx.doc / "deck.yaml").write_text(
        "chapters:\n  risks:\n    claim: Twelve risks are recorded; review date TBC.\n"
        "    notes: The design is seamless. See {sec:risks/nowhere}.\n")
    found = fx.findings()
    got = {(f.id, f.source.line) for f in found}
    assert ("count-prose", 3) in got and ("tbc-owner", 3) in got
    assert ("voice", 4) in got and ("xref", 4) in got
    assert all(f.anchor in (None, "s4") for f in found if f.source.file == "deck.yaml")


def test_topic_check_on_a_cited_chapter(fx):
    # "in chapter n" resolves to a Chapter, whose blocks() is a method, not a list.
    fx.append("content/04-risks.md", "Carrier retention rules are in chapter 2.")
    assert isinstance(fx.findings(), list)


# ------------------------------------------- acceptance-run fixes (round 2)

def test_deck_yaml_parse_error_is_a_content_error(fx):
    (fx.doc / "deck.yaml").write_text("chapters:\n  risks:\n    claim: [unclosed\n")
    found = only(fx.findings(), "content")
    assert len(found) == 1 and found[0].severity == "error"
    assert found[0].source.file == "deck.yaml" and "not valid YAML" in found[0].message


def test_deck_yaml_structure_is_judged_by_the_deck_builder(fx):
    pytest.importorskip("archdoc.deck_build")
    (fx.doc / "deck.yaml").write_text("chapters:\n  risks:\n    claim: Ten risks.\n    colour: red\n")
    found = only(fx.findings(), "content")
    assert len(found) == 1, show(found)
    f = found[0]
    assert f.message.startswith("chapters.risks") and "unknown key 'colour'" in f.message
    assert "deck.yaml:" not in f.message and (f.source.file, f.source.line) == ("deck.yaml", 4)
    assert str(f).startswith("deck.yaml:4: error [content] chapters.risks")


def test_build_all_writes_nothing_when_deck_yaml_is_broken(fx, monkeypatch):
    cli = _cli_module()
    built = []
    for target in ("docx", "site", "deck"):
        mod = types.ModuleType(f"archdoc.checks_fake_{target}")
        mod.build = (lambda t: lambda p, out_dir=None: built.append(t) or [])(target)
        monkeypatch.setitem(sys.modules, f"archdoc.checks_fake_{target}", mod)
        monkeypatch.setitem(cli.BUILDERS, target, f"checks_fake_{target}")
    (fx.doc / "deck.yaml").write_text("chapters: [unclosed\n")
    assert cli.main(["-C", str(fx.doc), "build", "all"]) == 1 and built == []


def _profile(fx, **systems):
    path = fx.root / "profile.yaml"
    data = yaml.safe_load(path.read_text())
    for k, v in systems.items():
        data["systems"][k] = v
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_layer_one_finding_per_name_keeping_the_longest(fx):
    fx.config(layer="logical")
    _profile(fx, cicd={"name": "Azure DevOps", "logical_name": "delivery pipeline"})
    fx.append("content/01-application.md", "Builds run in Azure DevOps and sign-in uses Microsoft Entra ID.")
    msgs = [f.message for f in only(fx.findings(), "layer")]
    assert msgs == ["'Azure DevOps' in a logical design (the profile's cicd system; write 'delivery pipeline')",
                    "'Microsoft Entra ID' in a logical design (a cloud product)"], msgs


def test_layer_allow_path(fx):
    fx.config(layer="logical", allowed_terms=["Azure Monitor"])
    _profile(fx, cicd={"name": "Azure DevOps", "logical_name": "delivery pipeline", "keep_name": True},
             itsm={"name": "ServiceNow", "logical_name": "service management platform", "keep_name": True,
                   "framework": "itil", "has_cmdb": True, "cmdb_title": "Configuration records",
                   "category_title": "Service Management & Configuration Records"})
    fx.append("content/01-application.md", "The cloud landing zone in Azure Australia East sends tickets to "
              "ServiceNow, work items to Azure DevOps and metrics to Azure Monitor. AWS and Google Cloud are out "
              "of scope.")
    assert not only(fx.findings(), "layer"), show(fx.findings())
    fx.config(allowed_terms=None)
    assert [f.message for f in only(fx.findings(), "layer")] == [
        "'Azure Monitor' in a logical design (a cloud product)"]


def test_views_table_row_view_comes_from_its_view_column(fx):
    fx.append("content/05-appendix.md", "| View | Viewpoint | Notes |\n|---|---|---|\n"
              "| Activity log | Logical Data | Not drawn. Activity routes to central logging, shown in "
              "{view:int-flows} |\n| {view:app-context} | Application Context | Drawn |")
    assert not only(fx.findings(), "figure"), show(fx.findings())
    fx.edit("content/05-appendix.md", "| {view:app-context} | Application Context | Drawn |",
            "| {view:app-context} | Application Context | Not drawn yet |")
    found = only(fx.findings(), "figure")
    assert len(found) == 1 and "has it as View 1" in found[0].message


def test_count_model_ignores_refs_to_no_record_and_needs_a_majority(fx):
    path = fx.doc / "diagrams" / "model.json"
    model = json.loads(path.read_text())
    model["objects"] += [{"id": f"TEC-{i}", "type": "Technology", "name": f"Node {i}"} for i in range(5)]
    model["objects"][-1]["ref"] = "ADR-15"      # the dependency's decision: no record here
    model["objects"][-2]["ref"] = "ADR-01"      # one real ref among five objects: no majority
    path.write_text(json.dumps(model))
    assert not only(fx.findings(), "count-model"), show(fx.findings())


def test_count_model_one_ea_type_for_two_registers(fx):
    """Application Component objects referencing applications and
    components: the type maps to both, and their sum is the count."""
    path = fx.doc / "diagrams" / "model.json"
    model = json.loads(path.read_text())
    refs = ["APP-01", "APP-02", "APP-03", "CMP-01", "CMP-02", "CMP-03", "CMP-04"]
    for o, r in zip([o for o in model["objects"] if o["type"] == "Application Component"], refs):
        o["ref"] = r
    path.write_text(json.dumps(model))
    assert not only(fx.findings(), "count-model")
    model["objects"] = [o for o in model["objects"] if o.get("ref") != "CMP-04"]
    path.write_text(json.dumps(model))
    assert [f.message.split(";")[0] for f in only(fx.findings(), "count-model")] == [
        "the EA catalogue counts 6 Application Component objects"]


@pytest.mark.parametrize("old, new, check_id, fragment", [
    ("impact: Testing is late", "impact: Testing is late; see section 9.2", "xref", "no section 9.2"),
    ("impact: Testing is late", "impact: 'Testing is late, see Section 3.1: issues'", "xref",
     "cited as 'issues'"),
    ("impact: Testing is late", "impact: Testing is late until this document (v0.1) is approved", "version",
     "'v0.1' but this document is version 0.3"),
    ("impact: Testing is late", "impact: 'Testing is late (see {sec:risks/nowhere})'", "xref",
     "ISS-01.impact: {sec:risks/nowhere}"),
])
def test_register_values_are_checked_like_prose(fx, old, new, check_id, fragment):
    fx.edit("registers/issue.yaml", old, new)
    found = only(fx.findings(), check_id)
    assert any(fragment in f.message for f in found), show(fx.findings())
    assert all(f.source.file == "registers/issue.yaml" for f in found)


def test_embedded_tbc_in_a_register_value(fx):
    fx.edit("registers/risk.yaml", "mitigation: Monitor, status: open}", "mitigation: 'Monitor; TBC', status: open}")
    assert not only(fx.findings(), "tbc-owner"), "a bare TBC falls to the record's owner"
    fx.edit("registers/glossary-term.yaml", "definition: A site where parcels are sorted",
            "definition: 'A sorting site; size TBC'")
    found = only(fx.findings(), "tbc-owner")
    assert len(found) == 1 and "GLO-02.definition has a TBC with no owner" in found[0].message


@pytest.mark.parametrize("where, old, new, fragment", [
    ("content/04-risks.md", "TBC: Data owner.", "TBC: at concept endorsement.", "a time or condition"),
    ("content/04-risks.md", "TBC: Data owner.", "TBC: proposed for this review.", "a state or topic"),
    ("registers/risk.yaml", "mitigation: Monitor, status: open}", "mitigation: 'TBC: not measured', status: open}",
     "in RSK-01.mitigation names a state or topic"),
])
def test_tbc_owner_slot_holding_a_time_or_topic(fx, where, old, new, fragment):
    fx.edit(where, old, new)
    found = only(fx.findings(), "tbc-owner", "warn")
    assert len(found) == 1 and fragment in found[0].message, show(fx.findings())


OWNERS = ("Data owner", "Head of Parcels", "Cyber Security", "Platform engineering", "Marketing", "J. Smith",
          "Design authority", "Release manager", "Architecture Review Board", "UAT lead", "Procurement team",
          "May Chen", "Will Ng", "Security architect")
NOT_OWNERS = ("whether the platform's hosting is recorded as configuration items", "if funded",
              "depends on the vendor", "at concept endorsement", "proposed for this review", "not measured",
              "detailed design", "concept stage", "Q3 2026", "end of March 2027", "once the contract is signed",
              "the vendor may confirm", "how many tenants join")
JOINT_OWNERS = ("integration platform team with the platform owner", "Cyber security with the integration platform team",
                "Platform team and Security architect", "Data owner & Privacy officer",
                "Integration lead / Depot manager", "Head of Parcels, Service owner")
NOT_JOINT_OWNERS = ("the platform owner once named", "with the platform team",
                    "the platform team with whoever owns the network design at the time",
                    "a very long description of an owner that just keeps going on")


@pytest.mark.parametrize("owner", OWNERS + JOINT_OWNERS)
def test_tbc_owner_slot_accepts_roles_teams_and_people(owner):
    assert owner_problem(owner) is None and is_owner(owner)


@pytest.mark.parametrize("slot", NOT_OWNERS + NOT_JOINT_OWNERS)
def test_tbc_owner_slot_rejects_clauses_times_states_and_stages(slot):
    assert owner_problem(slot) is not None and not is_owner(slot)


def test_tbc_owner_slot_whether_clause_in_a_document(fx):
    fx.edit("content/04-risks.md", "TBC: Data owner.",
            "TBC: whether the platform's hosting is recorded as configuration items.")
    found = only(fx.findings(), "tbc-owner")
    assert len(found) == 1 and found[0].severity == "warn" and "a question or condition" in found[0].message


@pytest.mark.parametrize("dash", ["—", "–"])
def test_tbc_with_a_dash_before_the_owner(fx, dash):
    fx.edit("content/04-risks.md", "TBC: Data owner.", f"TBC {dash} Data owner.")
    fx.edit("registers/glossary-term.yaml", "definition: A site where parcels are sorted",
            f"definition: 'TBC {dash} Depot manager'")
    assert not only(fx.findings(), "tbc-owner"), show(fx.findings())
    tbcs = {t.owner for t in Project.load(fx.doc).tbcs()}
    assert {"Data owner", "Depot manager"} <= tbcs


def test_tbc_with_a_hyphen_is_not_an_owner_form(fx):
    fx.edit("content/04-risks.md", "TBC: Data owner.", "TBC - Data owner.")
    assert [f.severity for f in only(fx.findings(), "tbc-owner")] == ["error"]


def test_table_values_follow_the_sections_column_map(fx):
    """The template header 'Impact if Delayed' is mapped to impact by the
    section's extracted column_map; the field's label is 'Impact if late'."""
    mm_path = fx.doc / "metamodel.yaml"
    mm = yaml.safe_load(mm_path.read_text())
    risks = next(c for c in mm["chapters"] if c["key"] == "risks")
    dep = next(sct for sct in risks["sections"] if sct["key"] == "dependencies")
    dep["column_map"] = {"Ref": "id", "Delivery effect": "impact"}
    mm_path.write_text(yaml.safe_dump(mm, sort_keys=False))
    fx.edit("content/04-risks.md", "REGISTER dependency\n",
            "REGISTER dependency\n\n| Ref | Delivery effect |\n|---|---|\n| DEP-01 | No scan feed |\n")
    assert not only(fx.findings(), "consistency")
    fx.edit("content/04-risks.md", "| DEP-01 | No scan feed |", "| DEP-01 | Labels are delayed |")
    found = only(fx.findings(), "consistency")
    assert len(found) == 1 and "DEP-01 delivery effect is 'Labels are delayed'" in found[0].message


def test_table_values_header_with_another_condition(fx):
    fx.edit("content/04-risks.md", "REGISTER dependency\n",
            "REGISTER dependency\n\n| ID | Impact if Delayed |\n|---|---|\n| DEP-01 | Labels are delayed |\n")
    found = only(fx.findings(), "consistency")
    assert len(found) == 1 and "but the dependency register says 'No scan feed'" in found[0].message


def test_table_value_against_the_register_and_another_table(fx):
    fx.edit("content/04-risks.md", "REGISTER dependency\n",
            "REGISTER dependency\n\n| ID | Impact if late |\n|---|---|\n| DEP-01 | No scan feed |\n")
    assert not only(fx.findings(), "consistency")
    fx.edit("content/04-risks.md", "| DEP-01 | No scan feed |", "| DEP-01 | Labels are delayed |")
    found = only(fx.findings(), "consistency")
    assert len(found) == 1 and "DEP-01 impact if late is 'Labels are delayed' here, but the dependency register " \
                               "says 'No scan feed'" in found[0].message


def test_table_values_compared_between_tables_when_the_register_is_silent(fx):
    fx.edit("content/04-risks.md", "REGISTER issue\n",
            "REGISTER issue\n\n| Issue | Due |\n|---|---|\n| ISS-01 | Before the carrier test |\n")
    fx.edit("registers/issue.yaml", " due: 2026-11-01,", "")
    fx.append("content/02-integration.md", "| Issue | Due |\n|---|---|\n| ISS-01 | Before the carrier test |")
    assert not only(fx.findings(), "consistency")
    fx.edit("content/02-integration.md", "| ISS-01 | Before the carrier test |", "| ISS-01 | After go-live |")
    found = only(fx.findings(), "consistency")
    assert len(found) == 1 and "is 'Before the carrier test' here, but 'After go-live' at content/02-integration.md" in found[0].message


# ------------------------------------------- namespaced and multi-prefix ids

@pytest.fixture
def nsfx(fx):
    """The clean fixture with list prefixes (risk: RSK or RISK; exception:
    EXC or DEV) and namespaced ids: the risks are PT-SEC-RISK-nn and the view
    exceptions PT-DEV-nn. It must be as clean as the original."""
    mm_path = fx.doc / "metamodel.yaml"
    mm = yaml.safe_load(mm_path.read_text())
    mm["artefact_types"]["risk"]["prefix"] = ["RSK", "RISK"]
    mm["artefact_types"]["exception"]["prefix"] = ["EXC", "DEV"]
    mm_path.write_text(yaml.safe_dump(mm, sort_keys=False))
    for rel in ("registers/risk.yaml", "diagrams/model.json"):
        path = fx.doc / rel
        path.write_text(path.read_text().replace("RSK-", "PT-SEC-RISK-"))
    for old, new in (("EXC-03", "PT-DEV-03"), ("EXC-04", "PT-DEV-04")):
        fx.edit("registers/exception.yaml", old, new)
        fx.edit("content/03-decisions.md", old, new)
    return fx


def test_namespaced_fixture_is_clean(nsfx):
    found = nsfx.findings()
    assert found == [], show(found)


def test_namespaced_and_second_prefix_ids_are_checked(nsfx):
    nsfx.edit("content/04-risks.md", "across", "(PT-SEC-RISK-03, PT-SEC-RISK-99 and DEV-07) across")
    msgs = [f.message for f in only(nsfx.findings(), "ids")]
    assert msgs == ["PT-SEC-RISK-99 is not in any register", "DEV-07 is not in any register"], msgs


def test_crossing_with_namespaced_second_prefix_exceptions(nsfx):
    nsfx.edit("content/03-decisions.md", "| {view:app-context} | PT-DEV-03 |\n| {view:int-flows} | PT-DEV-04 |",
              "| {view:app-context} | PT-DEV-04 |\n| {view:int-flows} | PT-DEV-03 |")
    found = only(nsfx.findings(), "ids", "warn")
    assert len(found) == 1 and "View 2 → PT-DEV-03 comes after View 1 → PT-DEV-04" in found[0].message


def test_count_model_maps_namespaced_refs(nsfx):
    path = nsfx.doc / "diagrams" / "model.json"
    model = json.loads(path.read_text())
    model["objects"] = [o for o in model["objects"] if o.get("ref") not in ("PT-SEC-RISK-09", "PT-SEC-RISK-10")]
    path.write_text(json.dumps(model))
    found = only(nsfx.findings(), "count-model")
    assert len(found) == 1 and "counts 8 Risk objects; the risk register has 10" in found[0].message


def test_table_values_with_namespaced_ids(nsfx):
    nsfx.edit("content/04-risks.md", "REGISTER issue\n",
              "REGISTER issue\n\n| ID | Owner |\n|---|---|\n| PT-SEC-RISK-02 | Depot manager |\n")
    found = only(nsfx.findings(), "consistency")
    assert len(found) == 1 and "PT-SEC-RISK-02 owner is 'Depot manager' here, but the risk register says " \
                               "'Integration lead'" in found[0].message


def test_core_and_check_report_record_problems_once(fx):
    """Core raises unowned embedded TBCs and unresolved record placeholders;
    the check reports each once."""
    fx.edit("registers/glossary-term.yaml", "definition: A site where parcels are sorted",
            "definition: 'A sorting site; size TBC; see {sec:risks/nowhere}'")
    found = fx.findings()
    assert len(only(found, "tbc-owner")) == 1, show(found)
    assert len([f for f in only(found, "xref") if "{sec:risks/nowhere}" in f.message]) == 1, show(found)


def test_deck_cat_placeholder_reported_once(fx):
    (fx.doc / "deck.yaml").write_text("chapters:\n  risks:\n    claim: The {cat:nowhere} risks.\n")
    found = [f for f in fx.findings() if "{cat:nowhere}" in f.message]
    assert len(found) == 1 and found[0].id == "xref" and found[0].source.line == 3, show(fx.findings())


def test_tbc_named_as_a_noun_is_not_an_open_value(fx):
    """'Every TBC has an owner' talks about TBCs; 'Hosting TBC.' marks one."""
    fx.append("content/04-risks.md", "Every TBC has an owner, and a TBC is closed at the next review.")
    assert not only(fx.findings(), "tbc-owner"), show(fx.findings())
    fx.append("content/04-risks.md", "Hosting TBC.")
    found = only(fx.findings(), "tbc-owner")
    assert len(found) == 1 and found[0].severity == "error" and "Hosting TBC" in found[0].message
    lines = (fx.doc / "content/04-risks.md").read_text().split("\n")
    assert lines[found[0].source.line - 1] == "Hosting TBC."


def test_joint_owner_in_a_document(fx):
    fx.edit("content/04-risks.md", "TBC: Data owner.", "TBC: Cyber security with the integration platform team.")
    assert not only(fx.findings(), "tbc-owner"), show(fx.findings())


def test_open_item_with_a_non_owner_slot_has_no_owner(fx):
    """The outputs read open_items(): a slot the check rejects shows as no
    owner there too, with the slot kept."""
    fx.edit("content/04-risks.md", "TBC: Data owner.",
            "TBC: whether the platform's hosting is recorded as configuration items.")
    items = Project.load(fx.doc).open_items()
    assert [(i.owner, i.owner_text) for i in items] == [
        (None, "whether the platform's hosting is recorded as configuration items")]
    fx.edit("content/04-risks.md", "TBC: whether the platform's hosting is recorded as configuration items.",
            "TBC: Cyber security with the integration platform team.")
    items = Project.load(fx.doc).open_items()
    assert [(i.owner, i.owner_text) for i in items] == [("Cyber security with the integration platform team", None)]


XREF_TABLE = ("| Control Area | Control | Control / Risk |\n|---|---|---|\n"
              "| Encryption at rest | Keys rotate yearly | RSK-01 |\n"
              "| Encryption in transit | TLS everywhere | RSK-02 |\n")


def test_table_values_ignore_cross_reference_columns(fx):
    """A table whose ids sit in a cross-reference column is not keyed on
    them: 'Control Area', which the section's column map gives as the title
    of its own register, is not compared with each risk's title."""
    mm_path = fx.doc / "metamodel.yaml"
    mm = yaml.safe_load(mm_path.read_text())
    risks = next(c for c in mm["chapters"] if c["key"] == "risks")
    sec = next(x for x in risks["sections"] if x["key"] == "issues")
    sec["column_map"] = {"Control Area": "title"}
    mm_path.write_text(yaml.safe_dump(mm, sort_keys=False))
    fx.edit("content/04-risks.md", "REGISTER issue\n", "REGISTER issue\n\n" + XREF_TABLE)
    assert not only(fx.findings(), "consistency"), show(fx.findings())


@pytest.mark.parametrize("header", ["Risk", "Risk ID", "ID", "Ref", "RSK"])
def test_table_values_keyed_on_an_id_named_column(fx, header):
    table = (f"| Area | {header} | Risk |\n|---|---|---|\n| Encryption | RSK-01 | Keys are lost |\n")
    fx.edit("content/04-risks.md", "REGISTER issue\n", "REGISTER issue\n\n" + table)
    found = only(fx.findings(), "consistency")
    assert len(found) == 1 and "RSK-01" in found[0].message and "'Risk number 1'" in found[0].message, \
        show(fx.findings())


def test_table_values_keyed_through_the_column_map(fx):
    mm_path = fx.doc / "metamodel.yaml"
    mm = yaml.safe_load(mm_path.read_text())
    risks = next(c for c in mm["chapters"] if c["key"] == "risks")
    sec = next(x for x in risks["sections"] if x["key"] == "issues")
    sec["column_map"] = {"Tracker": "id", "Raised against": "title"}
    mm_path.write_text(yaml.safe_dump(mm, sort_keys=False))
    table = "| Area | Tracker | Raised against |\n|---|---|---|\n| Testing | ISS-01 | Sandbox outage |\n"
    fx.edit("content/04-risks.md", "REGISTER issue\n", "REGISTER issue\n\n" + table)
    found = only(fx.findings(), "consistency")
    assert len(found) == 1 and "ISS-01 raised against is 'Sandbox outage'" in found[0].message
