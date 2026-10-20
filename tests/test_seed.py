"""The seed metamodel: shape, completeness and organisation-neutrality."""
import copy
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import SEED
from archdoc.metamodel import (EA_NAMES, PICTURE_KINDS, MetamodelError, from_dict, load_metamodel,
                               validate)
from archdoc.registers import CHIPS

CHAPTER_KEYS = [
    "summary", "context", "governance", "requirements", "current-state", "target", "application",
    "integration", "data", "infrastructure", "security", "nfr", "decisions", "operations", "monitoring",
    "service-processes", "runbooks", "transition", "risks", "assurance", "lifecycle", "appendix",
]

ARTEFACT_TYPES = [
    "business-requirement", "functional-requirement", "nfr",
    "stakeholder", "forum", "checkpoint",
    "decision", "decision-request", "assumption", "constraint", "dependency",
    "capability", "application", "component", "environment", "integration", "data-object", "data-flow",
    "control",
    "risk", "issue", "exception",
    "runbook", "readiness-item", "process-readiness", "alert",
    "cutover-step", "acceptance-item",
    "retired-component", "glossary-term",
]


@pytest.fixture(scope="module")
def raw():
    return yaml.safe_load(SEED.read_text())


def test_seed_validates():
    m = load_metamodel("seed")
    assert m.name == "seed"
    assert [c["key"] for c in m.chapters] == CHAPTER_KEYS


def test_deck_runs_follow_the_spec(raw):
    runs = [c["deck"]["run"] for c in raw["chapters"]]
    assert runs == [1] * 4 + [2] * 8 + [3] * 5 + [4] * 5
    assert set(raw["deck"]["runs"]) == {1, 2, 3, 4}


def test_every_chapter_names_a_picture_question_and_story(raw):
    for c in raw["chapters"]:
        assert c["picture"]["kind"] in PICTURE_KINDS, c["key"]
        assert c["question"].endswith("?"), c["key"]
        assert c["story"], c["key"]
        assert c["sections"], c["key"]
    kinds = {c["picture"]["kind"] for c in raw["chapters"]}
    assert kinds == set(PICTURE_KINDS)


def test_every_artefact_type_is_complete_and_used():
    m = load_metamodel("seed")
    assert sorted(m.artefact_types) == sorted(ARTEFACT_TYPES)
    used = set()
    for c in m.chapters:
        for s in c["sections"]:
            used |= {a.split()[0] for a in s["artefacts"]}
    assert used == set(ARTEFACT_TYPES)
    for t in m.artefact_types.values():
        assert t.prefix.isupper()
        assert t.fields
        assert any(f.kind == "enum" for f in t.fields.values()) or t.key == "glossary-term", t.key
        if t.has_owner:
            assert t.fields["owner"].kind == "text", t.key
        assert t.columns
        assert set(t.status.values()) <= set(CHIPS)
        assert {"done"} <= set(t.status.values()), t.key


def test_viewpoints_name_every_ea_metamodel():
    m = load_metamodel("seed")
    assert len(m.viewpoints) >= 10
    for vp in m.viewpoints.values():
        assert set(vp.ea) == set(EA_NAMES), vp.key
        assert vp.ea["coreea"] and vp.ea["togaf"], vp.key


def test_service_management_sections_have_guidance_variants(raw):
    ch = {c["key"]: c for c in raw["chapters"]}
    keyed = {(c, s["key"]): s for c in ch for s in ch[c]["sections"]}
    for k in [("operations", "service-records"), ("operations", "model-mapping"),
              ("monitoring", "event-mapping"), ("service-processes", "incident"),
              ("service-processes", "change"), ("service-processes", "request"),
              ("service-processes", "knowledge")]:
        assert set(keyed[k]["guidance_by"]) >= {"servicenow", "jira-service-management"}, k
        assert keyed[k]["guidance_on"] == "systems.itsm.name"


def test_capability_excludes_are_few_and_real():
    m = load_metamodel("seed")
    ex = m.document_kinds["capability"]["excludes"]
    assert 0 < len(ex) <= 3
    assert "excludes" not in m.document_kinds["solution"]


REPO = Path(__file__).resolve().parent.parent

# Organisation names stay out of the repo, so they live in an untracked file:
# one term per line, "#" for comments. Without the file, only product names are checked.
LOCAL_BANNED = REPO / "tests" / "local-banned.txt"


def local_banned() -> list[str]:
    if not LOCAL_BANNED.exists():
        return []
    lines = (ln.strip() for ln in LOCAL_BANNED.read_text().splitlines())
    return [ln for ln in lines if ln and not ln.startswith("#")]


def test_no_organisation_or_product_names_in_generic_text():
    text = SEED.read_text()
    for banned in ("Orbus", "Blueprint", "ServiceNow", "Jira", "Azure", "Entra", "Datadog", "GitHub",
                   *local_banned()):
        assert banned not in text, banned


def test_no_local_banned_term_anywhere_in_the_repo():
    terms = local_banned()
    if not terms:
        pytest.skip(f"no {LOCAL_BANNED.name}")
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.splitlines()
    hits = []
    for name in tracked:
        path = REPO / name
        if name == "tests/test_seed.py" or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        hits += [f"{name}: {t}" for t in terms if t.lower() in text.lower()]
    assert not hits, hits


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["chapters"][0]["picture"].update(kind="pie"), "picture: kind"),
    (lambda d: d["chapters"][0]["sections"][1].update(artefacts=["nonsense"]), "unknown type 'nonsense'"),
    (lambda d: d["chapters"][0]["sections"][1].update(artefacts=["risk where colour=red"]), "not a field of risk"),
    (lambda d: d["chapters"][0]["sections"][1].update(artefacts=["risk where rating=huge"]), "'huge' is not a value"),
    (lambda d: d["chapters"][0].update(when={"all": []}), "non-empty list"),
    (lambda d: d["chapters"][0]["deck"].update(run=7), "deck.run"),
    (lambda d: d["artefact_types"]["risk"]["status"].update(open="maybe"), "chip 'maybe'"),
    (lambda d: d["artefact_types"]["issue"].update(prefix="RSK"), "prefix RSK is also used"),
    (lambda d: d["artefact_types"]["risk"].update(columns=["id", "colour"]), "'colour' is not a field"),
    (lambda d: d["chapters"][1]["sections"].append(copy.deepcopy(d["chapters"][1]["sections"][0])), "duplicate section key"),
    (lambda d: d["document_kinds"]["capability"].update(excludes=["nowhere/none"]), "'nowhere/none'"),
    (lambda d: d["viewpoints"]["crud"]["ea"].update(lean="x"), "'lean' is not one of"),
])
def test_validation_catches(raw, mutate, needle):
    d = copy.deepcopy(raw)
    mutate(d)
    errs = validate(d)
    assert any(needle in e for e in errs), errs
    with pytest.raises(MetamodelError):
        from_dict(d)
