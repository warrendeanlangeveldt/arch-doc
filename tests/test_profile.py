"""Profiles: defaults, validation, lookup, and how they shape the document."""
import copy

import pytest

from conftest import northwind_profile
from archdoc import Project
from archdoc.metamodel import evaluate_when, from_dict as metamodel_from_dict, load_metamodel
from archdoc.profile import DEFAULTS, ProfileError, from_dict

SERVICE_MANAGEMENT = {"operations/service-records", "operations/model-mapping", "monitoring/event-mapping",
                      "service-processes/request", "service-processes/itil-readiness"}


def keys(model):
    return {f"{c.key}/{s.key}" for c in model.chapters for s in c.sections}


def section(model, ch, sec):
    return model.chapter(ch).section(sec)


def test_defaults_are_neutral_and_complete():
    p = from_dict({})
    assert p.palette == DEFAULTS["house"]["palette"]
    assert p.fonts["heading"] == "Source Serif 4" and p.fonts["body"] == "IBM Plex Sans"
    assert p.get("forums.design_authority.short") == "ARB"
    assert p.get("template.styles.h1") == "Heading 1"
    assert not p.is_set("systems.itsm")
    assert p.ea_metamodel is None


def test_lookup_and_is_set():
    p = from_dict(northwind_profile())
    assert p.get("systems.itsm.name") == "ServiceNow"
    assert p.text("systems.itsm") == "ServiceNow"
    assert p.text("systems.cloud") == "azure"
    assert p.text("systems.itsm.has_cmdb") == "yes"
    assert p.is_set("systems.itsm.has_cmdb")
    assert not p.is_set("systems.ea_repository")
    assert p.get("systems.nothing.here", "fallback") == "fallback"
    assert p.ea_metamodel == "archimate"


def test_system_none_hides_its_fields():
    p = from_dict({"systems": {"itsm": {"name": "none", "has_cmdb": True}}})
    assert not p.is_set("systems.itsm.has_cmdb")


def test_itsm_defaults_fill_titles():
    p = from_dict({"systems": {"itsm": {"name": "BMC Helix"}}})
    assert p.get("systems.itsm.framework") == "none"
    assert p.get("systems.itsm.cmdb_title") == "BMC Helix Configuration Records"
    assert p.get("systems.itsm.has_cmdb") is False


@pytest.mark.parametrize("raw,needle", [
    ({"systems": {"ea_metamodel": "uml"}}, "ea_metamodel 'uml'"),
    ({"systems": {"cloud": ["mainframe"]}}, "cloud entry 'mainframe'"),
    ({"systems": {"itsm": {"name": "X", "framework": "cobit"}}}, "framework 'cobit'"),
    ({"house": {"palette": {"ink": "blue"}}}, "#RRGGBB"),
    ({"forums": {"privacy": {"name": "Privacy Board"}}}, "short name"),
    ({"colour": "red"}, "unknown top-level key"),
])
def test_validation(raw, needle):
    with pytest.raises(ProfileError) as e:
        from_dict(raw)
    assert any(needle in m for m in e.value.errors), e.value.errors


def test_when_forms():
    p = from_dict(northwind_profile())
    assert evaluate_when("systems.itsm", p)
    assert evaluate_when({"systems.itsm.framework": "itil"}, p)
    assert evaluate_when({"systems.itsm.framework": ["other", "ITIL"]}, p)
    assert not evaluate_when({"not": {"systems.itsm.framework": "itil"}}, p)
    assert evaluate_when({"all": ["systems.itsm.has_cmdb", "systems.ea_metamodel"]}, p)
    assert not evaluate_when({"all": ["systems.itsm", "systems.ea_repository"]}, p)
    assert evaluate_when({"any": ["systems.ea_repository", "systems.itsm"]}, p)


def test_itsm_none_drops_service_management_sections():
    m = load_metamodel("seed")
    with_itsm = m.apply(from_dict(northwind_profile()), "solution")
    prof = northwind_profile()
    prof["systems"]["itsm"] = {"name": "none"}
    without = m.apply(from_dict(prof), "solution")
    dropped = keys(with_itsm) - keys(without)
    assert dropped == SERVICE_MANAGEMENT
    assert keys(without) - keys(with_itsm) == {"service-processes/process-readiness"}
    assert len(without.chapters) == 22


def test_itsm_none_numbering_is_gap_free(make_project):
    prof = northwind_profile()
    prof["systems"]["itsm"] = {"name": "none"}
    p = Project.load(make_project(profile=prof))
    assert [c.number for c in p.chapters] == list(range(1, 23))
    for c in p.chapters:
        assert [s.number for s in c.sections] == [f"{c.number}.{i}" for i in range(1, len(c.sections) + 1)]
    ops = p.chapter("operations")
    assert [s.key for s in ops.sections] == ["views", "readiness", "support-model", "raci"]
    assert p.number("operations", "service-records") is None
    assert p.number("monitoring", "acceptance") == "15.4"


def test_itil_is_conditional_on_the_framework():
    m = load_metamodel("seed")
    itil = m.apply(from_dict(northwind_profile()), "solution").chapter("service-processes")
    prof = northwind_profile()
    prof["systems"]["itsm"]["framework"] = "other"
    other = m.apply(from_dict(prof), "solution").chapter("service-processes")
    assert itil.section("itil-readiness").title == "ITIL Practice Readiness"
    assert itil.section("process-readiness") is None
    assert other.section("itil-readiness") is None
    assert other.section("process-readiness") is not None


def test_titles_and_guidance_come_from_the_profile():
    m = load_metamodel("seed")
    sn = m.apply(from_dict(northwind_profile()), "solution")
    assert section(sn, "operations", "service-records").title == "ServiceNow CMDB & CSDM"
    assert section(sn, "operations", "model-mapping").title == "Architecture Model to ServiceNow Mapping"
    assert "CSDM" in section(sn, "operations", "service-records").guidance
    assert "{p:" not in section(sn, "governance", "forums").guidance
    assert "Architecture Review Board (ARB)" in section(sn, "governance", "forums").guidance

    jsm = northwind_profile()
    jsm["systems"]["itsm"] = {"name": "Jira Service Management", "has_cmdb": True, "cmdb_title": "Jira Assets"}
    j = m.apply(from_dict(jsm), "solution")
    assert section(j, "operations", "service-records").title == "Jira Assets"
    assert "Assets object" in section(j, "operations", "service-records").guidance
    assert "request types" in section(j, "service-processes", "incident").guidance

    generic = northwind_profile()
    generic["systems"]["itsm"] = {"name": "BMC Helix", "has_cmdb": True}
    g = m.apply(from_dict(generic), "solution")
    assert section(g, "operations", "service-records").title == "BMC Helix Configuration Records"
    assert section(g, "operations", "service-records").guidance.startswith(
        "Identify the configuration records the service needs in BMC Helix")


def test_unset_profile_value_in_guidance_is_marked():
    m = load_metamodel("seed")
    prof = northwind_profile()
    prof["systems"]["cicd"] = {"name": "none"}
    e = m.apply(from_dict(prof), "solution")
    assert "[systems.cicd.name is not set in the profile]" in section(e, "infrastructure", "deployment").guidance


def test_ea_repository_and_metamodel_sections():
    m = load_metamodel("seed")
    prof = northwind_profile()
    prof["systems"]["ea_repository"] = {"name": "LeanIX"}
    e = m.apply(from_dict(prof), "solution")
    assert section(e, "context", "repository").title == "LeanIX Repository"
    assert section(e, "appendix", "repository-views").title == "LeanIX Views"
    prof["systems"]["ea_metamodel"] = "none"
    e2 = m.apply(from_dict(prof), "solution")
    assert not any(s.key == "views" for c in e2.chapters for s in c.sections)
    assert section(e2, "appendix", "object-guide") is None


def test_capability_kind_excludes_its_sections():
    m = load_metamodel("seed")
    e = m.apply(from_dict(northwind_profile()), "capability")
    assert section(e, "application", "channels") is None
    assert section(e, "data", "migration") is None
    assert section(e, "application", "components") is not None


def test_conditional_chapter_drop_renumbers():
    raw = copy.deepcopy(load_metamodel("seed").raw)
    raw["chapters"][1]["when"] = "systems.ea_repository"
    m = metamodel_from_dict(raw)
    e = m.apply(from_dict(northwind_profile()), "solution")
    assert len(e.chapters) == 21
    assert e.chapters[1].key == "governance"


def test_logical_layer_uses_logical_names(make_project):
    m = load_metamodel("seed")
    prof = from_dict(northwind_profile())
    physical = m.apply(prof, "capability", "logical-and-physical")
    logical = m.apply(prof, "capability", "logical")
    assert "(Entra ID)" in section(physical, "security", "identity").guidance
    assert "(identity provider)" in section(logical, "security", "identity").guidance
    assert "(delivery pipeline)" in section(logical, "infrastructure", "deployment").guidance
    assert prof.text("systems.identity", logical=True) == "identity provider"
    assert prof.text("systems.source_control.name", logical=True) == "GitHub"
    root = make_project(kind="capability", extra={"layer": "logical"}, content={
        "11-security.md": "# security\n## identity\nUsers sign in through the {p:systems.identity.name}.\n"})
    p = Project.load(root)
    assert p.section("security", "identity").blocks[0].text == "Users sign in through the identity provider."


def test_logical_variant_of_any_system_text_field():
    """A logical design takes logical_<field> for a system's other text fields too."""
    m = load_metamodel("seed")
    prof = from_dict(northwind_profile())
    logical = m.apply(prof, "capability", "logical")
    physical = m.apply(prof, "solution", "logical-and-physical")
    assert section(physical, "operations", "service-records").title == "ServiceNow CMDB & CSDM"
    assert section(logical, "operations", "service-records").title == "Configuration Management Database"
    assert prof.text("systems.itsm.cmdb_title", logical=True) == "Configuration Management Database"
    assert prof.text("systems.itsm.category_title", logical=True) == "Service Management & Configuration Records"
    assert "ServiceNow" not in section(logical, "operations", "model-mapping").title
