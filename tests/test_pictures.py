"""Generated pictures (SPEC 6.3): every kind draws from fixture registers,
in the house palette, with measured text no smaller than 24px; an empty
register gives None and the chapter falls back."""
import math
import re
import shutil

import pytest

from archdoc import Project
from archdoc import pictures as P
from archdoc.metamodel import PICTURE_KINDS

from conftest import ROOT

FIXTURE = ROOT / "tests" / "fixtures" / "deck_build"

# One spec per kind, as the seed metamodel names them.
SPECS = {
    "layers": [{"from": "depends_on"}, {"from": "component", "by": "layer"}, {"from": "environment"}],
    "timeline": [{"from": "checkpoint"}, {"from": "retired-component"}],
    "traceability": [{"from": "functional-requirement"}],
    "heatmap": [{"from": "risk"}],
    "matrix": [{"from": "acceptance-item", "by": "stage"}, {"from": "control", "by": "area"}, {"from": "runbook"}],
    "swimlane": [{"from": "process-readiness"}],
    "flow": [{"from": "cutover-step"}, {"from": "data-flow"}],
    "bars": [{"from": "registers"}, {"from": "application", "by": "lifecycle"}, {"from": "decision", "by": "status"}],
    "map": [{"from": "integration"}, {"from": "application"}],
}


@pytest.fixture(scope="module")
def booking():
    return Project.load(FIXTURE / "booking")


@pytest.fixture
def empty(tmp_path):
    """The booking fixture with every register emptied."""
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    for f in (dst / "booking" / "registers").glob("*.yaml"):
        f.write_text("")
    return Project.load(dst / "booking")


def test_every_kind_has_a_spec():
    assert set(SPECS) == set(PICTURE_KINDS) == set(P.DRAWERS)


@pytest.mark.parametrize("kind,spec", [(k, s) for k, specs in SPECS.items() for s in specs],
                         ids=lambda v: v if isinstance(v, str) else v.get("from"))
def test_each_kind_draws_from_fixture_registers(booking, kind, spec):
    pic = P.draw(kind, booking, spec)
    assert pic is not None and pic.kind == kind
    svg = pic.svg
    assert svg.startswith("<svg") and f'viewBox="0 0 {P.W} {P.H}"' in svg
    # Text is measured and never under 24px.
    sizes = [float(x) for x in re.findall(r'font-size="([\d.]+)"', svg)]
    assert sizes and min(sizes) >= P.MIN_FONT
    # Every placed line stays inside the picture and inside its box.
    for t in pic.texts:
        assert -1 <= t.x and t.x + t.w <= P.W + 1, t.text
        assert -1 <= t.y and t.y + t.h <= P.H + 1, t.text
    for m in re.finditer(r'<text [^>]*data-in="([\d.\- ]+)"[^>]*>(.*?)</text>', svg):
        assert len(m.group(1).split()) == 4
    # Labels do not sit on each other (estimated geometry; the browser check
    # in test_deck_build verifies the rendered result).
    assert not P.overlaps(pic.texts, tol=4), [(a.text, b.text) for a, b in P.overlaps(pic.texts, tol=4)][:3]
    assert pic.description


@pytest.mark.parametrize("kind", [k for k in PICTURE_KINDS])
def test_empty_registers_give_none(empty, kind):
    for spec in SPECS[kind]:
        pic = P.draw(kind, empty, spec)
        if kind == "layers" and spec["from"] == "depends_on":
            assert pic is not None       # the design itself is always there
        else:
            assert pic is None, spec


def test_generate_falls_back_to_layers(empty):
    ch = empty.chapter("risks")
    pic = P.generate(empty, ch)
    assert pic.kind == "layers" and pic.source == "depends_on"


def test_chain_honours_fallback_and_list_by():
    chain = P.chain({"kind": "heatmap", "from": "risk", "fallback": ["matrix", {"kind": "bars", "from": "issue"}]})
    assert [c["kind"] for c in chain] == ["heatmap", "matrix", "bars", "layers"]
    chain = P.chain({"kind": "map", "from": "integration", "by": ["flow", "timeline"]})
    assert [c["kind"] for c in chain] == ["map", "flow", "timeline", "layers"]
    assert "by" not in chain[0]


def test_generate_uses_next_fallback(tmp_path):
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    (dst / "booking" / "registers" / "risk.yaml").write_text("")
    p = Project.load(dst / "booking")
    ch = p.chapter("risks")
    ch.picture = {"kind": "heatmap", "from": "risk", "fallback": [{"kind": "matrix", "from": "acceptance-item"}]}
    assert P.generate(p, ch).kind == "matrix"


def test_house_palette_from_profile(tmp_path):
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    prof = dst / "profile.yaml"
    prof.write_text(prof.read_text() + "house:\n  palette: {accent: '#7B2D8E', ink: '#101820'}\n"
                    "  fonts: {heading: Merriweather, body: Inter}\n")
    p = Project.load(dst / "booking")
    pic = P.draw("layers", p, {"from": "depends_on"})
    assert "#7B2D8E" in pic.svg and "#101820" in pic.svg and "Inter" in pic.svg
    # Every colour used comes from the theme (its tokens or their soft tints).
    t = P.Theme.from_profile(p.profile)
    allowed = {v.upper() for k, v in vars(t).items() if isinstance(v, str) and v.startswith("#")}
    for c in (t.done, t.partial, t.not_started, t.tbc, t.accent, t.paper):
        for amt in (0.6, 0.82, 0.86, 0.9):
            allowed.add(t.soft(c, amt).upper())
    used = {c.upper() for c in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', pic.svg)}
    assert used <= allowed, used - allowed


def test_arrowheads_stop_two_pixels_short(booking):
    t = P.Theme.from_profile(booking.profile)
    svg = P.Svg(t, "t")
    a = svg.rect(0, 100, 200, 80, t.paper, t.rule)
    b = svg.rect(600, 100, 200, 80, t.paper, t.rule)
    svg.arrow(a, b)
    d = re.search(r'<path d="M([\d.]+),([\d.]+) L([\d.]+),([\d.]+)"', svg.render("x"))
    x2 = float(d.group(3))
    assert math.isclose(600 - x2, 2, abs_tol=0.05)
    out = svg.render("x")
    assert 'refX="10"' in out and 'marker-end="url(#ah-t-' in out


def test_marker_ids_are_unique_per_picture(booking):
    one = P.draw("map", booking, {"from": "integration"}, booking.chapter("integration"))
    two = P.draw("map", booking, {"from": "application"}, booking.chapter("application"))
    ids1 = set(re.findall(r'<marker id="([^"]+)"', one.svg))
    ids2 = set(re.findall(r'<marker id="([^"]+)"', two.svg))
    assert ids1 and ids2 and not ids1 & ids2


def test_map_puts_the_new_application_at_the_centre(booking):
    pic = P.draw("map", booking, {"from": "integration"})
    assert "around Booking Service" in pic.description


def test_traceability_links_requirements_to_satisfiers(booking):
    pic = P.draw("traceability", booking, {"from": "functional-requirement"})
    assert "3 business requirements" in pic.description and "6 functional requirements" in pic.description
    assert pic.svg.count("<path") >= 6


def test_heatmap_places_every_rated_risk_and_names_the_unrated(booking):
    pic = P.draw("heatmap", booking, {"from": "risk"})
    for i in range(1, 9):
        assert f"RSK-0{i}" in pic.svg
    assert "Not rated: RSK-09" in pic.svg


def test_status_in_words(booking):
    pic = P.draw("timeline", booking, {"from": "checkpoint"})
    assert "Passed" in pic.svg and "Planned" in pic.svg
    for word in ("Done", "In progress", "Not started"):
        assert word in pic.svg      # the legend names each colour


def test_wrap_and_measure():
    assert P.text_width("abcd", 24) == pytest.approx(4 * 24 * 0.55)
    lines = P.wrap("one two three four five six seven", 200, 24)
    assert all(P.text_width(ln, 24) <= 200 for ln in lines)
    cut = P.wrap("one two three four five six seven eight nine ten", 150, 24, max_lines=2)
    assert len(cut) == 2 and cut[-1].endswith("…")
    assert P.ellipsize("short", 500, 24) == "short"


def _with_integrations(tmp_path, rows: str):
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    (dst / "booking" / "registers" / "integration.yaml").write_text(rows)
    return Project.load(dst / "booking")


def test_map_prefers_the_design_over_a_new_third_party_app(tmp_path):
    # Carrier Gateway is a new application too, and has more flows; the node
    # named for the design still takes the centre.
    p = _with_integrations(tmp_path, """
- {id: INT-01, title: a, source: Freight Booking Service, target: Carrier Gateway, pattern: api, state: target, status: planned}
- {id: INT-02, title: b, source: Carrier Gateway, target: Finance Ledger, pattern: api, state: target, status: planned}
- {id: INT-03, title: c, source: Customer Portal, target: Carrier Gateway, pattern: api, state: target, status: planned}
""")
    pic = P.draw("map", p, {"from": "integration"})
    assert pic.description.endswith("around Freight Booking Service")


def test_map_draws_the_design_as_a_container_of_its_components(tmp_path):
    p = _with_integrations(tmp_path, """
- {id: INT-01, title: a, source: Customer Portal, target: Booking API, pattern: api, state: target, status: planned}
- {id: INT-02, title: b, source: Carrier adapter, target: Carrier Gateway, pattern: event, state: target, status: planned}
- {id: INT-03, title: c, source: Freight Booking Service, target: Finance Ledger, pattern: file, state: target, status: planned}
- {id: INT-04, title: d, source: Messaging provider, target: Booking API, pattern: api, state: target, status: planned}
""")
    pic = P.draw("map", p, {"from": "integration"})
    assert pic.description.endswith("around Freight Booking Service")
    # the components sit inside the container; the title node is the container itself
    words = " ".join(t.text for t in pic.texts)
    assert "Booking API" in words and "Carrier" in words and "adapter" in words
    assert words.count("Freight Booking Service") == 1


# ---- acceptance fixes ------------------------------------------------------

def _y_of(pic, text):
    return min(t.y for t in pic.texts if t.text == text)


def test_capability_sits_under_its_consumers():
    base = Project.load(FIXTURE / "base")          # booking depends on it
    pic = P.draw("layers", base, {"from": "depends_on"})
    assert "under the designs built on it: Freight Booking Service" in pic.description
    assert _y_of(pic, "Freight Booking Service") < _y_of(pic, "Shared Hosting Base")
    layered = P.draw("layers", base, {"from": "component", "by": "layer"})
    assert _y_of(layered, "Freight Booking Service") < _y_of(layered, "Shared Hosting Base")


def test_solution_sits_over_what_it_depends_on(booking):
    pic = P.draw("layers", booking, {"from": "depends_on"})
    assert _y_of(pic, "Freight Booking Service") < _y_of(pic, "Shared Hosting Base")


def test_consumers_from_config(tmp_path):
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    cfg = dst / "base" / "arch-doc.yaml"
    cfg.write_text(cfg.read_text() + "consumers:\n  - Returns Portal\n  - {title: Claims Service, kind: solution, version: '1.0'}\n")
    names = [c[0] for c in P.consumers_of(Project.load(dst / "base"))]
    assert names[:2] == ["Returns Portal", "Claims Service"] and "Freight Booking Service" in names


def test_heatmap_by_rating_without_impact(tmp_path):
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    risk = dst / "booking" / "registers" / "risk.yaml"
    risk.write_text(re.sub(r", impact: \w+", "", risk.read_text()))
    p = Project.load(dst / "booking")
    pic = P.draw("heatmap", p, {"from": "risk"})
    assert pic.description.endswith("likelihood and rating") and "RSK-01" in pic.svg
    risk.write_text(re.sub(r", (likelihood|rating): \w+", "", risk.read_text()))
    assert P.draw("heatmap", Project.load(dst / "booking"), {"from": "risk"}) is None


def test_matrix_without_grouping_is_a_status_board(booking):
    pic = P.draw("matrix", booking, {"from": "runbook"})
    assert pic.description.startswith("each of the 3 runbooks")
    words = " ".join(t.text for t in pic.texts)
    assert "Replay failed carrier bookings" in words and "Tested" in words and "Required" in words


def test_bars_name_each_record(booking):
    pic = P.draw("bars", booking, {"from": "decision", "by": "status"})
    words = " ".join(t.text for t in pic.texts)
    assert "ADR-01 · Accepted" in words and "Proposed" in words


def test_generate_never_repeats_a_picture(booking):
    used = set()
    ch = booking.chapter("integration")
    first = P.generate(booking, ch, exclude=used, registers=["integration"])
    used.add(first.fingerprint)
    second = P.generate(booking, booking.chapter("context"), exclude=used, registers=["integration"])
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize("label,n,want", [
    ("Process readiness", 7, "process readiness records"), ("Process readiness", 1, "process readiness record"),
    ("Deviation or exception", 5, "deviations or exceptions"), ("Business requirement", 2, "business requirements"),
    ("Dependency", 3, "dependencies")])
def test_plurals(label, n, want):
    assert P._plural(label, n) == want


def test_metamodel_plural_wins(booking):
    booking.metamodel.artefact_types["runbook"].plural = "runbook sets"
    try:
        P.use_plurals(booking)
        assert P._plural("Runbook", 2) == "runbook sets"
    finally:
        booking.metamodel.artefact_types["runbook"].plural = ""
        P.PLURALS.pop("runbook", None)
