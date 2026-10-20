"""The TL;DR deck (SPEC 6.3): slide order and count, two-slide chapters,
footers, deck.yaml, the figure aspect-ratio rule, detail overflow, and a
headless-browser check that nothing leaves its slide."""
import html
import json
import re
import shutil
import struct
import zlib
from pathlib import Path

import pytest
import yaml

from archdoc import Project, chrome
from archdoc import deck_build as D
from archdoc.project import person_line

from conftest import EXAMPLES, ROOT

P_W = 1664  # the generated pictures' width (pictures.W)

FIXTURE = ROOT / "tests" / "fixtures" / "deck_build"
CHROME = chrome.find()


@pytest.fixture(scope="module")
def booking():
    return Project.load(FIXTURE / "booking")


@pytest.fixture(scope="module")
def deck(booking):
    return D.plan(booking)


@pytest.fixture
def fx(tmp_path):
    """A writable copy of the deck fixture; returns the booking project dir."""
    dst = tmp_path / "fx"
    shutil.copytree(FIXTURE, dst)
    return dst / "booking"


def expected_ids(p: Project, two_slide: set[int]) -> list[str]:
    ids = ["cover"]
    runs: dict[int, list] = {}
    for ch in p.chapters:
        runs.setdefault(ch.deck["run"], []).append(ch)
    for run in sorted(runs):
        ids.append(f"run-{run}")
        for ch in runs[run]:
            n = f"ch{ch.number:02d}"
            ids += [f"{n}-a", f"{n}-c"] if ch.number in two_slide else [f"{n}-a", f"{n}-b", f"{n}-c"]
    return ids


# ------------------------------------------------------------- order, count

def test_slide_order_and_count(booking, deck):
    two = {s.chapter for s in deck.slides if s.kind == "story"} - {s.chapter for s in deck.slides if s.kind == "detail"}
    assert deck.ids == expected_ids(booking, two)
    assert deck.ids[0] == "cover"
    assert [s.id for s in deck.slides if s.kind == "divider"] == ["run-1", "run-2", "run-3", "run-4"]
    assert len(deck.slides) == 1 + 4 + sum(2 if c.number in two else 3 for c in booking.chapters)
    kinds = {s.id: s.kind for s in deck.slides}
    assert all(kinds[i] == {"a": "story", "b": "detail", "c": "picture"}[i[-1]] for i in kinds if i.startswith("ch"))


def test_two_slide_chapters(booking, deck):
    ids = set(deck.ids)
    # min_slides: 2 in the seed metamodel
    for key in ("runbooks", "lifecycle", "appendix"):
        n = booking.chapter(key).number
        assert f"ch{n:02d}-a" in ids and f"ch{n:02d}-c" in ids and f"ch{n:02d}-b" not in ids
    # thin detail: the summary cites only two decision requests
    assert "ch01-b" not in ids
    # a chapter with real registers keeps its detail slide
    assert "ch19-b" in ids and "ch08-b" in ids


def test_footers(booking, deck):
    for s in deck.slides:
        if s.kind in ("cover", "divider"):
            assert 'class="footer"' not in s.html
        else:
            assert f'<p class="footer">FBS v0.4 · {s.chapter}</p>' in s.html, s.id


def test_every_slide_has_speaker_notes(deck):
    for s in deck.slides:
        assert s.notes, s.id
        n = len(re.findall(r"[.!?](\s|$)", s.notes))
        assert 1 <= n <= 6, (s.id, s.notes)
    story = next(s for s in deck.slides if s.id == "ch08-a")
    assert 2 <= len(re.findall(r"[.!?](\s|$)", story.notes)) <= 5


# --------------------------------------------------------------- deck.yaml

def test_deck_yaml_claims_points_cards_and_placeholders(deck):
    risks = next(s for s in deck.slides if s.id == "ch19-a")
    assert "The carrier API limits are the risk that matters most." in risks.html
    assert "9 risks are recorded; 3 are rated high or extreme." in risks.html     # {count:} resolved
    assert risks.html.count('class="point"') == 3
    gov = next(s for s in deck.slides if s.id == "ch03-a")
    assert gov.html.count('<div class="card">') == 3 and "Design authority" in gov.html
    assert risks.notes.startswith("The carrier API limits matter most.")
    cover = deck.slides[0]
    assert "We ask the ARB to approve the booking design on 30 October." in cover.html
    run1 = next(s for s in deck.slides if s.id == "run-1")
    assert "Why we are building a booking service" in run1.html


@pytest.mark.parametrize("entry,line", [
    ({"name": "Priya Nair", "role": "Solution Architect", "team": "Parcels Digital"},
     "Priya Nair, Solution Architect, Parcels Digital"),
    ({"name": "Solution Architect", "role": "Architect", "team": "Parcels"}, "Solution Architect, Parcels"),
    ({"name": "Head of Parcels", "role": "head of parcels"}, "Head of Parcels"),
    ({"name": "Ann Lee", "role": "Architect", "team": "Architect"}, "Ann Lee, Architect"),
    ("Tom Okafor", "Tom Okafor"),
])
def test_person_line_leaves_out_a_role_the_name_says(entry, line):
    assert person_line(entry) == line


@pytest.mark.parametrize("name,author,owner", [
    ("northwind-parcels", "Priya Nair, Solution Architect, Parcels Digital", "Tom Okafor, Head of Parcels"),
    ("northwind-platform", "Lena Brandt, Platform Architect, Platform Engineering", "Marcus Hale, Head of Platform"),
])
def test_example_covers_name_people(name, author, owner):
    cover = D.plan(Project.load(EXAMPLES / name)).slides[0]
    assert f"<p>Author: {author}</p>" in cover.html and f"<p>Owner: {owner}</p>" in cover.html


def test_deck_yaml_reports_unknown_chapter_keys(deck):
    warn = [i for i in deck.issues if i.severity == "warn"]
    assert any("not-a-chapter" in i.message for i in warn)


def test_callouts_on_the_picture(deck):
    pic = next(s for s in deck.slides if s.id == "ch19-c")
    assert pic.html.count('class="callout"') == 1 and "RSK-01: queue and back-off" in pic.html


@pytest.mark.parametrize("entry,fragment", [
    ({"points": ["one", "two"]}, "points must be a list of 3 to 6"),
    ({"cards": [{"title": "a", "text": "b"}] * 7}, "cards must be a list of 3 to 6"),
    ({"points": ["a", "b", "c"], "cards": [{"title": "a", "text": "b"}] * 3}, "points or cards, not both"),
    ({"callouts": [{"text": "x", "x": 1.5, "y": 0.2}]}, "must be a fraction"),
    ({"callouts": [{"text": "a", "x": 0, "y": 0}] * 4}, "up to 3"),
    ({"claim": "fine", "colour": "red"}, "unknown key 'colour'"),
    ({"claim": "{count:nonsense}"}, "{count:nonsense}"),
    ({"notes": {"story": "a", "other": "b"}}, "unknown slide 'other'"),
])
def test_deck_yaml_errors_stop_the_build(fx, entry, fragment):
    (fx / "deck.yaml").write_text(yaml.safe_dump({"chapters": {"risks": entry}}))
    p = Project.load(fx)
    with pytest.raises(D.DeckError) as e:
        D.plan(p)
    assert fragment in str(e.value)


def test_deck_yaml_chapter_keys_at_top_level(fx):
    (fx / "deck.yaml").write_text(yaml.safe_dump({"risks": {"claim": "Top-level keys work too."}}))
    deck = D.plan(Project.load(fx))
    assert "Top-level keys work too." in next(s for s in deck.slides if s.id == "ch19-a").html


def test_derived_story_when_deck_yaml_is_silent(fx):
    (fx / "deck.yaml").unlink()
    deck = D.plan(Project.load(fx))
    story = next(s for s in deck.slides if s.id == "ch18-a")
    # the lead-in's first sentence is the claim; section first sentences are cards
    assert '<p class="claim"' in story.html and "Cutover runs over one weekend with two rollback points." in story.html
    assert "The spreadsheet freezes on Friday evening" in story.html
    assert "If carrier traffic fails on Saturday" in story.html
    # no deck.yaml: the cover falls back to the summary's claim
    assert "We ask the ARB to approve the booking service design" in deck.slides[0].html


# ------------------------------------------------------------ detail slides

def test_detail_chips_in_words_and_overflow(booking, deck):
    acc = next(s for s in deck.slides if s.id == f"ch{booking.chapter('assurance').number:02d}-b")
    assert '<span class="chip tbc">TBC: Test lead</span>' in acc.html
    assert '<span class="chip done">Met</span>' in acc.html
    risks = next(s for s in deck.slides if s.id == "ch19-b")
    # sections citing one register with the same columns read as one table
    assert "19.1 Architecture Risks · 19.2 Operational Risks" in risks.html
    # rows that do not fit are pointed at, never silently dropped
    shown = len(re.findall(r'<td class="idc">', risks.html))
    pointed = sum(int(n) for n in re.findall(r"(\d+) more in sections?", risks.html)) + \
        sum(int(n) for n in re.findall(r'class="more">(\d+) in sections?', risks.html))
    assert shown + pointed == 6 + 2 + 3     # architecture and operational risks, issues, dependencies


def test_long_register_caps_at_fourteen_rows(fx):
    rows = "\n".join(f"- {{id: RSK-{i:02d}, title: Risk number {i}, likelihood: low, impact: low, rating: low, "
                     f"owner: Lead, status: open}}" for i in range(1, 31))
    (fx / "registers" / "risk.yaml").write_text(rows + "\n")
    (fx / "content" / "19-risks.md").write_text("# risks\nThirty risks.\n\n## architecture-risks\nREGISTER risk\n")
    deck = D.plan(Project.load(fx))
    s = next(s for s in deck.slides if s.id == "ch19-b")
    # the cap is per table: the risk table renders 14 rows and says where the rest are
    risk_table = s.html.split('data-where="section 19.1"')[1].split("</table>")[0]
    shown = len(re.findall(r'<td class="idc">', risk_table))
    assert shown == D.DETAIL_MAX_ROWS
    assert f"{30 - shown} more rows in section 19.1" in s.html


def test_narrow_register_splits_across_columns(fx):
    rows = "\n".join(f"- {{id: GLO-{i:02d}, title: Term {i}, definition: Short, domain: Ops, status: agreed}}"
                     for i in range(1, 13))
    (fx / "registers" / "glossary-term.yaml").write_text(rows + "\n")
    (fx / "registers" / "business-requirement.yaml").write_text("")
    (fx / "content" / "02-context.md").write_text(
        "# context\nTerms.\n\n## in-scope\nThe terms.\n\nREGISTER glossary-term cols title,definition\n")
    deck = D.plan(Project.load(fx))
    s = next(s for s in deck.slides if s.id == "ch02-b")
    assert '<div class="cols gridrow">' in s.html and "(continued)" in s.html
    assert len(re.findall(r"<td>Term \d+</td>", s.html)) == 12


# ------------------------------------------------------- the aspect rule

def _png(path: Path, w: int, h: int) -> None:
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_image_size_reads_png_and_svg(tmp_path):
    _png(tmp_path / "a.png", 32, 20)
    assert D.image_size(tmp_path / "a.png") == (32, 20)
    (tmp_path / "b.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 600"></svg>')
    assert D.image_size(tmp_path / "b.svg") == (1200, 600)
    (tmp_path / "c.svg").write_text('<svg width="300px" height="100px"></svg>')
    assert D.image_size(tmp_path / "c.svg") == (300, 100)


def test_figure_used_inside_the_aspect_range(booking, deck):
    # context.png is 1600x900 (1.78): the picture slide shows it
    ctx = next(s for s in deck.slides if s.id == "ch02-c")
    assert ctx.figure is not None and ctx.picture is None
    assert '<img src="media/figure-1.png"' in ctx.html
    assert "figure-1.png" in deck.media
    # sequence.svg is 600x1000 (0.6): the integration chapter draws its map instead
    integ = next(s for s in deck.slides if s.id == "ch08-c")
    assert integ.figure is None and integ.picture.kind == "map"


@pytest.mark.parametrize("w,h,used", [(900, 1000, True), (2600, 1000, True), (890, 1000, False),
                                      (2610, 1000, False), (1000, 1000, True)])
def test_aspect_ratio_bounds(fx, w, h, used):
    for f in (fx / "diagrams").iterdir():
        f.unlink()
    _png(fx / "diagrams" / "context.png", w, h)
    p = Project.load(fx)
    found = D.chapter_figure(p.chapter("context"))
    assert (found is not None) == used


# ----------------------------------------------------------------- build

def test_build_writes_a_self_contained_deck(booking, tmp_path):
    out = D.build(booking, tmp_path)
    index = tmp_path / "deck" / "index.html"
    assert index in out and (tmp_path / "deck" / "media" / "figure-1.png") in out
    text = index.read_text()
    assert "<script src" not in text and 'rel="stylesheet" href="https://fonts.googleapis.com/' in text
    assert "window.__deckOverflow" in text and "@page { size: 1920px 1080px" in text
    assert text.count('<section class="slide') == len(D.plan(booking).slides)
    # house tokens come from the profile
    assert f"--accent:{booking.profile.palette['accent']}" in text


def test_build_default_out_dir(fx):
    p = Project.load(fx)
    out = D.build(p)
    assert out[0] == fx / "out" / "deck" / "index.html"


@pytest.mark.parametrize("name", ["northwind-platform", "northwind-parcels"])
def test_examples_plan(name):
    p = Project.load(EXAMPLES / name)
    deck = D.plan(p)
    assert deck.ids[0] == "cover" and "run-1" in deck.ids
    stories = [s for s in deck.slides if s.kind == "story"]
    pictures = [s for s in deck.slides if s.kind == "picture"]
    assert len(stories) == len(pictures) == len(p.chapters)
    for s in deck.slides:
        if s.kind in ("story", "detail", "picture"):
            assert f"{p.short} v{p.version} · {s.chapter}" in s.html


# --------------------------------------------------------------- browser

def _dump_dom(url: str, profile: Path, size: str = "1920,1080") -> chrome.Run:
    """Headless Chrome's DOM after the page has run. Each launch has its own
    profile and no network: the deck's web fonts fail at once, so the page
    is measured with its fallback fonts and nothing loads late. The page's
    check modes report synchronously at load and await no real I/O, which
    --virtual-time-budget would not wait for.

    The DOM is complete once its closing ``</html>`` has arrived: from then
    the output is used and Chrome's process group killed, since under load
    Chrome can print the DOM and then hang on shutdown. A run that ends or
    times out before that fails, with what Chrome wrote to stderr."""
    profile.mkdir(parents=True, exist_ok=True)
    run = chrome.run(
        [str(CHROME), "--headless", "--disable-gpu", f"--user-data-dir={profile}", "--no-first-run",
         "--no-default-browser-check", "--host-resolver-rules=MAP * ~NOTFOUND", "--virtual-time-budget=10000",
         f"--window-size={size}", "--dump-dom", url],
        done=lambda out, err: "</html>" in out, timeout=180)
    assert run.complete, f"Chrome {run.why()} before the DOM was complete:\n{run.stderr[-3000:]}"
    return run


def _browser_check(index: Path, query: str = "check=1", size: str = "1920,1080") -> dict:
    proc = _dump_dom(f"file://{index}?{query}", index.parent / "chrome-profile", size)
    found = re.findall(r'<pre id="deck-check">(.*?)</pre>', proc.stdout, re.S)
    assert found, proc.stderr[-2000:]
    return json.loads(html.unescape(found[-1]))


@pytest.mark.skipif(CHROME is None, reason="no Chrome or Chromium for the browser check")
@pytest.mark.parametrize("where", ["fixture", "northwind-platform", "northwind-parcels"])
def test_no_element_overflows_its_slide(where, tmp_path):
    root = FIXTURE / "booking" if where == "fixture" else EXAMPLES / where
    p = Project.load(root)
    D.build(p, tmp_path)
    result = _browser_check(tmp_path / "deck" / "index.html")
    assert result["slides"] == D.plan(p).ids
    assert result["overflow"] == [], result["overflow"][:10]
    # no callout covers a box, cell, card, bar or label the picture draws
    assert result["callouts"] == [], result["callouts"][:10]
    # ?check=1 is shot mode: none of the navigation chrome is laid out
    assert not any(result["ui"]["shown"].values()), result["ui"]


# ------------------------------------------------------------- navigation

def test_render_includes_the_navigation_chrome(booking):
    text = D.render(booking, D.plan(booking))
    n = len(D.plan(booking).slides)
    for hook in ('class="nav-btn prev"', 'class="nav-btn next"', 'class="progress"', 'class="progress-bar"',
                 'class="counter"', f'<span class="counter-text">1 / {n}</span>', 'class="overview deck-ui"',
                 'class="overview-grid"', 'class="hint" role="status" hidden'):
        assert hook in text, hook
    assert "\u2190 \u2192 or click to navigate \u00b7 G for all slides" in text
    assert 'aria-label="Previous slide"' in text and 'aria-label="Next slide"' in text
    # print and shot mode hide every piece of it
    assert "body.shot .deck-ui, body.shot .notes-panel { display: none !important; }" in text
    assert re.search(r"@media print \{[^@]*\.deck-ui, \.notes-panel \{ display: none !important; \}", text)


def _steps(result: dict) -> dict:
    return {s["step"]: s for s in result["steps"]}


@pytest.mark.skipif(CHROME is None, reason="no Chrome or Chromium for the browser check")
@pytest.mark.parametrize("where", ["northwind-platform", "northwind-parcels"])
def test_navigation_in_browser(where, tmp_path):
    """The buttons, a click on the right and left thirds, G, Escape, the
    counter and a thumbnail, in a short wide viewport like the Artifact pane."""
    p = Project.load(EXAMPLES / where)
    D.build(p, tmp_path)
    ids = D.plan(p).ids
    n = len(ids)
    st = _steps(_browser_check(tmp_path / "deck" / "index.html", "check=ui", "1810,1000"))
    load = st["load"]
    assert load["shown"] == {"prev": False, "next": True, "counter": True, "progress": True,
                             "overview": False, "hint": True}         # no previous on the cover
    assert load["counter"] == f"1 / {n}" and load["active"] == "cover"
    assert st["next button"]["active"] == ids[1] and st["next button"]["shown"]["prev"]
    assert st["next button"]["counter"] == f"2 / {n}" and not st["next button"]["shown"]["hint"]
    assert st["previous button"]["active"] == ids[0]
    assert st["right third"]["active"] == ids[1]
    assert st["left third"]["active"] == ids[0]
    g = st["G"]
    assert g["shown"]["overview"] and g["thumbs"] == n and g["thumbSlides"] == n
    assert not g["shown"]["counter"] and not g["shown"]["prev"]
    assert g["duplicateIds"] == []                 # thumbnails rename the ids they copy
    assert not st["Escape"]["shown"]["overview"]
    assert st["counter"]["shown"]["overview"]
    mid = n // 2
    jump = st[f"thumbnail {mid + 1}"]
    assert jump["active"] == ids[mid] and not jump["shown"]["overview"]
    assert jump["counter"] == f"{mid + 1} / {n}"
    assert float(jump["progress"].rstrip("%")) == pytest.approx((mid + 1) / n * 100, abs=0.01)


@pytest.mark.skipif(CHROME is None, reason="no Chrome or Chromium for the browser check")
def test_shot_mode_hides_the_navigation(booking, tmp_path):
    D.build(booking, tmp_path)
    load = _steps(_browser_check(tmp_path / "deck" / "index.html", "shot=1&check=ui", "1810,1000"))["load"]
    assert not any(load["shown"].values()), load


# ------------------------------------------------------------ acceptance fixes

def test_no_generated_picture_repeats(deck):
    prints = [s.picture.fingerprint for s in deck.slides if s.kind == "picture" and s.picture is not None]
    assert len(prints) == len(set(prints))


def test_detail_says_how_many_columns_it_leaves_out():
    # every table that leaves out columns says how many, in its one footnote
    found = 0
    for name in ("northwind-platform", "northwind-parcels"):
        deck = D.plan(Project.load(EXAMPLES / name))
        for s in deck.slides:
            for cols, more in re.findall(r'data-cols="(\d+)".*?<p class="more"[^>]*>([^<]*)</p>', s.html, re.S):
                if int(cols):
                    found += 1
                    assert f"{cols} more column" in more, (s.id, more)
    assert found


def test_tbc_chips_are_never_cut(booking, deck):
    for s in deck.slides:
        for chip in re.findall(r'<span class="chip tbc">([^<]*)</span>', s.html):
            assert "…" not in chip, (s.id, chip)


def test_register_only_cited_by_the_metamodel_is_named_for_its_register(deck):
    # the fixture's requirements chapter has no content: its registers are not shown by a section
    req = next(s for s in deck.slides if s.id == "ch04-b")
    assert "the functional requirements register" in req.html or "the business requirements register" in req.html
    assert "in section 4." not in req.html


def test_story_and_detail_are_marked_for_the_fill_check(deck):
    for s in deck.slides:
        assert s.fill == (s.kind in ("story", "detail")), s.id


def test_divider_carries_the_runs_numbers(deck):
    run4 = next(s for s in deck.slides if s.id == "run-4")
    assert "open items" in run4.html and "risks" in run4.html and 'class="statbar"' in run4.html


@pytest.mark.skipif(CHROME is None, reason="no Chrome or Chromium for the browser check")
def test_fill_check_catches_an_over_trimmed_detail_slide(booking, tmp_path):
    """The layout an earlier build produced (one row a table, the rest
    hidden, half the slide blank) must fail the check, not pass it."""
    D.build(booking, tmp_path)
    index = tmp_path / "deck" / "index.html"
    # Runs straight after the deck's own script (which has fitted the page),
    # synchronously: no timers, no font or other I/O to wait for.
    broken = '''<script>
(function () {
  var s = document.getElementById("ch19-b");
  s.querySelectorAll(".group[data-total]").forEach(function (g) {
    g.removeAttribute("data-collapsed");
    g.querySelectorAll("tr.r").forEach(function (r, i) { r.hidden = i > 0; });
  });
  s.setAttribute("data-trimmed", "");
  var pre = document.createElement("pre"); pre.id = "broken";
  pre.textContent = JSON.stringify(window.__deckOverflow().filter(function (o) { return o.slide === "ch19-b"; }));
  document.body.appendChild(pre);
})();
</script></body>'''
    probe = index.with_name("probe.html")
    probe.write_text(index.read_text().replace("</body>", broken))
    proc = _dump_dom(f"file://{probe}?shot=1", tmp_path / "chrome-profile")
    found = re.findall(r'<pre id="broken">(.*?)</pre>', proc.stdout, re.S)
    assert found, proc.stderr[-1000:]
    problems = [o["problem"] for o in json.loads(html.unescape(found[-1]))]
    assert any("underfilled" in p or "rows fill only" in p for p in problems), problems


def test_one_footnote_per_table(deck):
    for s in deck.slides:
        for group in re.findall(r'<div class="group" data-total.*?</table></div>', s.html, re.S):
            assert group.count('class="more"') == 1, s.id


# The old layouts (a register's first row with its other rows and tables
# hidden, the slide half blank) must fail the check on both examples.
UNDERFILL = '''<script>
(function () {
  var out = {};
  ["story", "detail"].forEach(function (kind) {
    // a slide whose main register (the one that takes rows first) has more than four rows
    var s = Array.prototype.filter.call(document.querySelectorAll('.slide[data-kind="' + kind + '"]'), function (s) {
      var main = s.querySelector('.group[data-weight="2"]');
      return main && main.querySelectorAll("tr.r").length > 4;
    })[0];
    if (!s) return;
    s.querySelectorAll(".group[data-total]").forEach(function (g, j) {
      g.querySelectorAll("tr.r").forEach(function (r, i) { r.hidden = i > 0; });
      if (j > 0) g.setAttribute("data-collapsed", "");
    });
    // the old story slide was a claim and three bars: its cards go too
    s.querySelectorAll(".trim-item, .cardgrid").forEach(function (c) { c.hidden = true; });
    s.setAttribute("data-trimmed", "");
    out[kind] = window.__deckOverflow().filter(function (o) { return o.slide === s.id; })
                                       .map(function (o) { return o.problem; });
  });
  var pre = document.createElement("pre"); pre.id = "underfill"; pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script></body>'''


@pytest.mark.skipif(CHROME is None, reason="no Chrome or Chromium for the browser check")
@pytest.mark.parametrize("name", ["northwind-platform", "northwind-parcels"])
def test_fill_check_fails_the_old_layouts(name, tmp_path):
    p = Project.load(EXAMPLES / name)
    D.build(p, tmp_path)
    index = tmp_path / "deck" / "index.html"
    probe = index.with_name("probe.html")
    probe.write_text(index.read_text().replace("</body>", UNDERFILL))
    proc = _dump_dom(f"file://{probe}?shot=1", tmp_path / "chrome-profile")
    found = re.findall(r'<pre id="underfill">(.*?)</pre>', proc.stdout, re.S)
    assert found, proc.stderr[-1000:]
    result = json.loads(html.unescape(found[-1]))
    for kind in ("story", "detail"):
        assert any(("stops short" in pr or "underfilled" in pr or "rows fill only" in pr)
                   for pr in result.get(kind, [])), (kind, result)


@pytest.mark.parametrize("name", ["northwind-platform", "northwind-parcels"])
def test_list_shaped_pictures_use_the_whole_area(name):
    from archdoc import pictures as P
    p = Project.load(EXAMPLES / name)
    deck = D.plan(p)
    for s in deck.slides:
        pic = s.picture
        if pic is not None and pic.kind in ("matrix", "timeline", "bars"):
            assert pic.extent >= 0.85, (s.id, pic.kind, round(pic.extent, 2))


# ------------------------------------------------------ acceptance run, round 2

def test_picture_draws_only_the_chapters_records(booking):
    from archdoc import pictures as P
    ch = booking.chapter("integration")       # cites acceptance-item where stage=integration
    pic = P.draw("matrix", booking, {"from": "acceptance-item", "by": "stage"}, ch)
    assert pic.description.startswith("the 1 acceptance item"), pic.description
    whole = P.draw("matrix", booking, {"from": "acceptance-item", "by": "stage"})
    assert whole.description.startswith("the 8 acceptance items")


def test_status_column_headers_name_the_values_present(booking):
    from archdoc import pictures as P
    pic = P.draw("matrix", booking, {"from": "component", "by": "layer"})
    words = [t.text for t in pic.texts]
    assert "Planned" in words and "Not started" not in words


def test_fact_counts_count_the_register(booking, deck):
    story = next(s for s in deck.slides if s.id == f"ch{booking.chapter('nfr').number:02d}-a")
    assert "6<span>non-functional requirements</span>" in story.html


def test_one_column_tables_are_not_tables(make_project):
    root = make_project(content={"02-context.md": """
        # context
        Lead.

        ## in-scope
        | Area |
        |---|
        | Hosting |

        | Item | Note |
        |---|---|
        | A | B |
        | C | D |
        | E | F |
        """})
    p = Project.load(root)
    groups = D.chapter_groups(p, p.chapter("context"))
    assert [g.columns for g in groups] == [["Item", "Note"]]


def test_twin_tables_are_told_apart_by_what_they_hold(make_project):
    root = make_project(content={"02-context.md": """
        # context
        Lead.

        ## in-scope
        | Component | Hosting |
        |---|---|
        | A | B |

        | Source | Destination |
        |---|---|
        | C | D |
        """})
    p = Project.load(root)
    labels = [g.label for g in D.chapter_groups(p, p.chapter("context"))]
    assert len(set(labels)) == 2 and not any("table" in l.lower() for l in labels), labels
    assert any("Component and Hosting" in l for l in labels)


def test_plurals_do_not_leak_between_projects(fx, tmp_path):
    from archdoc import pictures as P
    one = Project.load(fx)
    one.metamodel.artefact_types["runbook"].plural = "runbook sets"
    P.use_plurals(one)
    assert P._plural("Runbook", 2) == "runbook sets"
    one.metamodel.artefact_types["runbook"].plural = ""
    other = Project.load(FIXTURE / "base")
    D.plan(other)                       # a second project built in the same process
    assert P._plural("Runbook", 2) == "runbooks"


def test_cover_date_follows_the_house_format(fx):
    prof = fx.parent / "profile.yaml"
    prof.write_text(prof.read_text() + "house:\n  date_format: iso\n")
    p = Project.load(fx)
    from archdoc.formatting import format_date, date_format
    want = format_date(p.config["date"], date_format(p))
    assert f"Version 0.4 · {want}" in D.plan(p).slides[0].html


# A table shown as its header with no rows, and a callout laid on what the
# picture draws, must both fail the check on both examples.
BREAK = '''<script>
(function () {
  var out = {};
  var g = Array.prototype.filter.call(document.querySelectorAll('.group[data-collapsed]:not([data-fixed])'), function (x) {
    return !x.hidden && !x.closest("[hidden]");
  })[0];
  if (g) {
    var s = g.closest(".slide");
    g.removeAttribute("data-collapsed");
    g.querySelector("table").hidden = false;
    g.querySelectorAll("tr.r").forEach(function (r) { r.hidden = true; });
    out.header = window.__deckOverflow().filter(function (o) { return o.slide === s.id; }).map(function (o) { return o.problem; });
  }
  var pic = Array.prototype.filter.call(document.querySelectorAll(".picture"), function (p) {
    return p.querySelector("svg rect");
  })[0];
  if (pic) {
    var r = pic.querySelector("svg rect").getBoundingClientRect(), pr = pic.getBoundingClientRect();
    var c = document.createElement("p"); c.className = "callout"; c.textContent = "On top of the drawing";
    c.style.left = (r.left - pr.left + 4) + "px"; c.style.top = (r.top - pr.top + 4) + "px";
    pic.appendChild(c);
    out.callout = window.__deckCallouts().length;
  }
  var pre = document.createElement("pre"); pre.id = "broken2"; pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script></body>'''


@pytest.mark.skipif(CHROME is None, reason="no Chrome or Chromium for the browser check")
@pytest.mark.parametrize("name", ["northwind-platform", "northwind-parcels"])
def test_check_fails_header_only_tables_and_covering_callouts(name, tmp_path):
    p = Project.load(EXAMPLES / name)
    D.build(p, tmp_path)
    index = tmp_path / "deck" / "index.html"
    probe = index.with_name("probe.html")
    probe.write_text(index.read_text().replace("</body>", BREAK))
    proc = _dump_dom(f"file://{probe}?shot=1", tmp_path / "chrome-profile")
    found = re.findall(r'<pre id="broken2">(.*?)</pre>', proc.stdout, re.S)
    assert found, proc.stderr[-1000:]
    result = json.loads(html.unescape(found[-1]))
    assert "header-only table" in result["header"], result
    assert result["callout"] >= 1, result


@pytest.mark.parametrize("name", ["northwind-platform", "northwind-parcels"])
def test_callouts_are_placed_clear_of_the_drawing(name):
    """Placement measures each callout against every label and box the
    picture draws; one that has no free space goes in the strip below."""
    p = Project.load(EXAMPLES / name)
    deck = D.plan(p)
    placed = strip = 0
    for s in deck.slides:
        if s.picture is None:
            continue
        k = None
        m = re.search(r'class="picture" style="left:[\d.]+px;top:[\d.]+px;width:([\d.]+)px', s.html)
        k = float(m.group(1)) / P_W
        shapes = [(b.x * k, b.y * k, b.w * k, b.h * k) for b in list(s.picture.texts) + list(s.picture.rects)]
        for x, y, w in re.findall(r'<p class="callout" style="left:([\d.]+)px;top:([\d.]+)px;width:([\d.]+)px', s.html):
            x, y, w = float(x), float(y), float(w)
            placed += 1
            for (sx, sy, sw, sh) in shapes:
                assert not (x < sx + sw and sx < x + w and y < sy + sh and sy < y + 30), (s.id, x, y)
        strip += s.html.count('class="callout strip"')
    assert placed + strip > 0


def test_no_register_shows_twice_on_a_slide():
    for name in ("northwind-platform", "northwind-parcels"):
        deck = D.plan(Project.load(EXAMPLES / name))
        for s in deck.slides:
            labels = re.findall(r'class="group-label">([^<]*)<', s.html)
            assert len(labels) == len(set(labels)), (s.id, labels)


# ------------------------------------------------------ acceptance run, round 3

def test_a_status_picture_needs_two_statuses(fx):
    from archdoc import pictures as P
    reg = fx / "registers" / "runbook.yaml"
    reg.write_text(re.sub(r"status: \w+", "status: required", reg.read_text()))
    p = Project.load(fx)
    pic = P.draw("matrix", p, {"from": "runbook"})
    assert pic is not None and not P.says_something(pic, p, {"kind": "matrix", "from": "runbook"})
    assert P.generate(p, p.chapter("runbooks"), registers=["runbook"]).kind != "matrix"


def test_a_node_picture_needs_three_nodes(make_project):
    from archdoc import pictures as P
    p = Project.load(make_project())           # no dependencies, no components: the design alone
    pic = P.draw("layers", p, {"from": "depends_on"})
    assert P.node_count(pic) < 3 and not P.says_something(pic, p, {"kind": "layers", "from": "depends_on"})


def test_thin_tables_are_summaries(make_project):
    root = make_project(
        content={"19-risks.md": """
            # risks
            Lead.

            ## architecture-risks
            REGISTER risk cols title
            """},
        registers={"risk": """
            - {id: RSK-01, title: One risk, category: architecture, likelihood: low, impact: low, rating: low,
               owner: Lead, status: open}
            """})
    p = Project.load(root)
    deck = D.plan(p)
    html_ = "".join(s.html for s in deck.slides if s.chapter == p.chapter("risks").number)
    groups = re.findall(r'<div class="group(?: [^"]*)?" data-total[^>]*>', html_)
    assert groups and all("summary-only" in g and "data-fixed" in g for g in groups), groups


def test_open_item_without_an_owner_says_no_owner(booking):
    item = next(i for i in booking.open_items() if i.owner is None) if any(
        i.owner is None for i in booking.open_items()) else None
    import types
    fake = types.SimpleNamespace(text="Something open", owner=None, section="7.3 Components")
    note = D.open_item_note(fake)
    assert "No owner" in note and "Owner:" not in note
