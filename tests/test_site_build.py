"""The review site (SPEC 6.2): anchors, open items, media, theme, publish
recipe, both comment paths in a real browser, and both examples."""
import json
import os
import re
import shutil
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PIL import Image

from archdoc import ANCHOR_DC, ANCHOR_OPEN_ITEMS, Project, chrome
from archdoc import site_build
from archdoc.site_build import anchor_index, block_anchors, theme_tokens
from conftest import EXAMPLES

FIXTURE = Path(__file__).parent / "fixtures" / "site_build" / "review"
CHROME = os.environ.get("CHROME") or chrome.find()


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.oi = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if "id" in a:
            self.ids.append(a["id"])
        if "oi-item" in (a.get("class") or "").split():
            self.oi.append(a.get("data-anchor-ref") or None)


def parse(path):
    p = Ids()
    p.feed(path.read_text())
    return p


@pytest.fixture
def built(tmp_path):
    root = tmp_path / "review"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("out"))
    p = Project.load(root)
    outs = site_build.build(p, tmp_path / "out")
    return p, tmp_path / "out" / "site", outs


def core_anchors(p):
    out = []
    for ch in p.chapters:
        out.append(ch.anchor)
        for b in ch.lead:
            out += block_anchors(b)
        for s in ch.sections:
            out.append(s.anchor)
            for b in s.blocks:
                out += block_anchors(b)
    return out


def test_build_writes_page_media_and_recipe(built):
    p, site, outs = built
    assert outs == [site / "index.html", site / "PUBLISH.md"]
    page = (site / "index.html").read_text()
    assert page.startswith("<title>Depot Scanning Service</title>")
    assert "<!doctype" not in page.lower() and "<body" not in page.lower()
    assert page.isascii()
    assert "fonts.googleapis.com/css2?family=Source+Serif+4" in page


def test_every_core_anchor_is_an_id_once(built):
    p, site, _ = built
    ids = Counter(parse(site / "index.html").ids)
    for a in core_anchors(p) + [ANCHOR_DC, ANCHOR_OPEN_ITEMS, "dc-t1", "dc-t1-r1", "dc-t3-r2"]:
        assert ids[a] == 1, a
    dupes = [i for i, n in ids.items() if n > 1]
    assert dupes == []
    # spot checks against the core's scheme
    for a in ("s1", "s1-p1", "s1-1-p1", "s1-2-t1", "s1-2-t1-h", "s1-2-t1-r2", "s1-3-l1-i4", "s7-3-t2-r3",
              "fig-1", "view-1", "s19-1-t1-r2"):
        assert ids[a] == 1, a


def test_anchor_index_follows_document_order(built):
    p, _, _ = built
    idx = anchor_index(p)
    assert idx["s7-3-t1-r2"].label == "7.3 Component Design"
    assert idx["s1-p1"].label == "1 Executive Architecture Summary"
    assert idx["dc-t2-r1"].label == "Document control"
    order = [a for a in idx if a in set(core_anchors(p))]
    assert order == [a for a in core_anchors(p)]
    assert site_build.place_of(idx, "s7-3-t1-r99").anchor == "s7-3-t1"


def test_open_items_are_the_cores_open_items(built):
    p, site, _ = built
    items = p.open_items()
    parsed = parse(site / "index.html")
    # the panel renders each item twice: grouped by section and by owner
    assert len(parsed.oi) == 2 * len(items)
    want = Counter(it.anchor for it in items)
    assert Counter(parsed.oi[: len(items)]) == want and Counter(parsed.oi[len(items):]) == want
    page = (site / "index.html").read_text()
    html_page = __import__("html").unescape(re.sub(r"<[^>]+>", "", page))
    for it in items:
        assert it.text in html_page                     # the core's text as given, no phrasing added
        if it.anchor:
            i = page.index(f'data-anchor-ref="{it.anchor}"')
            item = page[i:page.index("</li>", i)]
            assert f'href="#{it.anchor}"' in item
            assert (it.owner or "No owner") in __import__("html").unescape(item)
        if it.section:
            assert f'<a href="#{it.section_anchor}">{it.section}</a>' in page
    assert "No owner" in page and "not cited" in page          # s1-3-l1-i5 and RSK-04
    assert f"Open items <b>{len(items)}</b>" in page
    # a TBC inside a longer record value is listed against its row
    i = page.index('data-anchor-ref="s19-1-t1-r1"')
    assert "Order by sequence number; replay window <mark" in page[i:page.index("</li>", i)]
    # placeholders inside a TBC row are resolved, never shown as written
    i = page.index('data-anchor-ref="s7-3-t2-r4"')
    row = page[i:page.index("</li>", i)]
    assert "3 components sized for RSK-01 and RSK-03" in row and "{" not in row


def test_register_rows_carry_status_chips_and_tbc_marks(built):
    p, site, _ = built
    page = (site / "index.html").read_text()
    assert '<span class="chip" data-chip="partial">In build</span>' in page
    assert '<span class="chip" data-chip="done">Built</span>' in page
    assert 'data-record="CMP-02"' in page
    # compact rows: the row names its owner once, so the cell reads "TBC" and the mark carries the owner
    i = page.index('data-record="CMP-02"')
    row = page[i:page.index("</tr>", i)]
    assert '<mark class="tbc" title="Owner: Parcels team">TBC</mark>' in row
    assert "TBC: Parcels team" not in row
    assert "Component register" in page and "Risk register &#183; category is architecture" in page


def test_every_block_kind_renders(built):
    p, site, _ = built
    page = (site / "index.html").read_text()
    kinds = {b.kind for b in p.blocks()}
    assert {"para", "bullets", "table", "register", "figure", "view"} <= kinds
    assert '<ol id="s1-3-l2" class="doc-list">' in page and 'data-n="2."' in page
    assert 'class="blk lv1"' in page                          # nested list item
    assert "<strong>Architecture Review Board</strong>" in page
    assert "<code>scan.v2</code>" in page
    assert '<a href="https://example.com/events" target="_blank" rel="noopener">the event guide</a>' in page
    assert '<pre class="mermaid">flowchart LR' in page        # .mmd without a render
    assert '<span class="fig-vp">Integration Flows</span>' in page


def test_catalogue_and_missing_figure(make_project):
    root = make_project(content={"22-appendix.md": """
        # appendix
        ## glossary
        CATALOGUE
        FIGURE nothing | A figure with no file
        FIGURE drawn | A source with no render
        """}, diagrams={"model.json": json.dumps({"objects": [{"type": "Node"}, {"type": "Node"},
                                                              {"type": "Application Component"}]}),
                        "drawn.ead": "view x\n"})
    p = Project.load(root)
    site = root / "out" / "site"
    site_build.build(p)
    page = (site / "index.html").read_text()
    assert "EA model catalogue" in page and "<td>Application Component</td>" in page
    assert "diagrams/nothing.png (or .svg, .mmd) does not exist" in page
    assert "diagrams/drawn.ead has no rendered PNG or SVG" in page


def test_media_downscaled_with_original_kept(built):
    p, site, _ = built
    with Image.open(site / "media" / "fig-1.png") as im:
        assert im.width == 1600
    with Image.open(site / "media" / "full" / "fig-1.png") as im:
        assert im.width == 2400
    page = (site / "index.html").read_text()
    assert 'src="media/fig-1.png" data-full="media/full/fig-1.png" width="1600" height="733"' in page


def test_theme_from_house_tokens(built):
    p, site, _ = built
    page = (site / "index.html").read_text()
    light, dark = theme_tokens(p.profile.palette)
    assert light["accent"] == "#2F6F7C" and light["ink"] == "#15252B"
    root = page.index(":root {")
    assert page.index("--accent: #2F6F7C;") > root
    assert '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {' in page
    assert ':root[data-theme="dark"] {' in page and "color-scheme: dark" in page
    assert set(light) == set(dark)
    # dark keeps contrast: text light on a dark ground
    assert site_build._lightness(dark["ink"]) > 0.85 > 0.15 > site_build._lightness(dark["bg"])


def test_publish_recipe(built):
    p, site, _ = built
    md = (site / "PUBLISH.md").read_text()
    assert f"**file_path**: `{site / 'index.html'}`" in md
    assert f"**root**: `{site}`" in md
    assert '["media/fig-1.png", "media/full/fig-1.png"]' in md
    assert "ArtifactComments" in md and "ArtifactData" in md and 'collection: "review"' in md
    assert "archdoc -C" in md and "comments import" in md


@pytest.mark.parametrize("name", ["northwind-platform", "northwind-parcels"])
def test_examples_build(name, tmp_path):
    p = Project.load(EXAMPLES / name)
    outs = site_build.build(p, tmp_path / "out")
    page = outs[0].read_text()
    ids = Counter(parse(outs[0]).ids)
    for a in core_anchors(p):
        assert ids[a] == 1, a
    assert len(parse(outs[0]).oi) == 2 * len(p.open_items())
    assert page.isascii()


# ------------------------------------------------------------- in a browser

def run_page(site: Path, tmp_path: Path, prelude: str, script: str) -> dict:
    """Load the built page in headless Chrome with ``prelude`` before it and
    ``script`` after it; the script stores its result as JSON in
    ``document.body.dataset.result``."""
    page = (site / "index.html").read_text()
    probe = site / "probe.html"
    probe.write_text(f"<script>{prelude}</script>\n{page}\n<script>{script}</script>")
    profile = tmp_path / "chrome-profile"
    # The DOM is complete once its closing </html> has arrived; then Chrome's
    # process group is killed, since under load it can print the DOM and
    # hang on shutdown (archdoc.chrome).
    out = chrome.run([str(CHROME), "--headless", "--disable-gpu", f"--user-data-dir={profile}", "--no-first-run",
                      "--no-default-browser-check", "--virtual-time-budget=6000", "--window-size=1440,1000", "--dump-dom",
                      probe.as_uri()], done=lambda o, e: "</html>" in o, timeout=90)
    assert out.complete, f"Chrome {out.why()} before the DOM was complete:\n{out.stderr[-3000:]}"
    m = re.search(r'data-result="([^"]*)"', out.stdout)
    assert m, out.stdout[-2000:] + out.stderr[-2000:]
    import html
    return json.loads(html.unescape(m.group(1)))


DRIVE = """
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => document.querySelector(s);
async function go() {
  const r = {};
  await wait(300);
  %s
  document.body.dataset.result = JSON.stringify(r);
}
window.addEventListener("load", () => { go().catch((e) => { document.body.dataset.result = JSON.stringify({error: String(e)}); }); });
"""

LOCAL = """
  r.mode = $("#tb-mode").textContent;
  r.cmBtn = !$("#cm-btn").hidden;
  $('[data-ref="s1-1-p1"]').click();
  r.open = !$("#composer").hidden;
  r.save = !$("#cmp-save").hidden; r.post = !$("#cmp-post").hidden;
  r.where = $("#cmp-where").textContent;
  $("#cmp-text").value = "Name the rural depots.";
  $("#cmp-name").value = "Reviewer A";
  $("#cmp-save").click();
  const key = "archdoc:" + JSON.parse($("#doc-meta").textContent).key + ":";
  r.stored = JSON.parse(localStorage.getItem(key + "comments"));
  r.noted = $("#s1-1-p1").classList.contains("noted");
  const sel = $("#rs-s1-1"); sel.value = "changes"; sel.dispatchEvent(new Event("change"));
  await wait(50);
  r.review = JSON.parse(localStorage.getItem(key + "review"));
  r.dot = $('[data-dot="s1-1"]').dataset.s;
  r.progress = $("#progress").textContent;
  location.hash = "app-comments"; await wait(100);
  r.panel = !$("#app-comments").hidden && $("#doc").hidden;
  r.items = document.querySelectorAll(".cm-item").length;
  // Capture the export synchronously. --virtual-time-budget fast-forwards
  // timers while the page is idle, and a Blob read is not work it waits
  // for, so awaiting blob.text() let the DOM dump before the result landed.
  let text = null, name = null;
  const RealBlob = window.Blob;
  window.Blob = function (parts, opts) { text = parts.join(""); return new RealBlob(parts, opts); };
  URL.createObjectURL = () => "blob:test";
  HTMLAnchorElement.prototype.click = function () { name = this.download; };
  $("#cm-export").click();
  window.Blob = RealBlob;
  r.download = name;
  r.exported = JSON.parse(text);
  r.exportShown = !$("#cm-export").hidden;
  location.hash = "app-open-items"; await wait(100);
  r.oi = !$("#app-open-items").hidden;
  $('.seg[data-group="owner"]').click();
  r.ownerView = !$('.oi-view[data-view="owner"]').hidden && $('.oi-view[data-view="section"]').hidden;
"""


@pytest.mark.skipif(not (CHROME and Path(CHROME).exists()), reason="needs Google Chrome")
def test_local_comments_status_and_export_in_browser(built, tmp_path):
    p, site, _ = built
    r = run_page(site, tmp_path, "", DRIVE % LOCAL)
    assert "error" not in r, r
    assert r["cmBtn"] and "in this browser" in r["mode"]
    assert r["open"] and r["save"] and not r["post"]
    assert r["where"] == "1.1 Delivery Scope"
    [c] = r["stored"]
    assert c["anchor"] == "s1-1-p1" and c["section"] == "1.1 Delivery Scope"
    assert c["text"] == "Name the rural depots." and c["author"] == "Reviewer A" and c["id"]
    assert r["noted"]
    assert r["review"]["s1-1"]["status"] == "changes" and r["review"]["s1-1"]["section"] == "1.1 Delivery Scope"
    assert r["dot"] == "changes" and "1 need changes" in r["progress"]
    assert r["panel"] and r["items"] == 1
    assert r["download"] == "DSS-v0.3-comments.json" and r["exportShown"]   # no claude at all: the blob link
    ex = r["exported"]
    assert ex["format"] == "arch-doc-comments" and ex["document"]["version"] == "0.3"
    assert ex["comments"][0]["anchor"] == "s1-1-p1" and ex["review"]["s1-1"]["status"] == "changes"
    assert r["oi"] and r["ownerView"]

    # the exported file goes back through `archdoc comments import`
    from archdoc import comments
    f = tmp_path / "export.json"
    f.write_text(json.dumps(ex))
    import io
    buf = io.StringIO()
    comments.import_file(p, f, buf)
    out = buf.getvalue()
    assert "s1-1-p1  1.1 Delivery Scope" in out and "Name the rural depots." in out


STUB = """
window.__calls = [];
const listeners = [];
const docs = {};
const snap = () => ({ docs: Object.keys(docs).map((id) => ({ id, exists: true, data: () => docs[id] })) });
const comments = {
  anchorFor: async (el) => ({ path: el.id, x: 1, y: 2 }),
  create: async (o) => { __calls.push(["create", o]); return { threadId: "t1", commentId: "c1" }; },
  sendToClaude: async (o) => { __calls.push(["send", o]); return { threadId: "t2", commentId: "c2" }; },
  canSendToClaude: async () => "available",
  openComposer: async (t) => { __calls.push(["open", Object.keys(t)[0]]); return { opened: true }; },
};
const db = {
  collection: (name) => ({ onSnapshot: (next) => { __calls.push(["watch", name]); listeners.push(next); next(snap()); return () => {}; } }),
  doc: (path) => ({
    set: async (b) => { __calls.push(["set", path, b]); docs[path.split("/")[1]] = b; listeners.forEach((l) => l(snap())); },
    delete: async () => { __calls.push(["delete", path]); },
  }),
};
window.claude = { use: (n) => Promise.resolve(n === "comments" ? comments : n === "db" ? db : null) };
"""

ARTIFACT = """
  r.mode = $("#tb-mode").textContent;
  r.cmBtn = !$("#cm-btn").hidden;
  $('[data-ref="fig-1"].fig-btn').click();
  await wait(50);
  r.save = !$("#cmp-save").hidden; r.post = !$("#cmp-post").hidden; r.claude = !$("#cmp-claude").hidden;
  $("#cmp-text").value = "Label the platform services.";
  $("#cmp-claude").click();
  await wait(50);
  $('[data-ref="s7-3-t1-r2"]').click();
  $("#cmp-text").value = "Which runtime?";
  $("#cmp-post").click();
  await wait(50);
  const sel = $("#rs-s7-3"); sel.value = "agreed"; sel.dispatchEvent(new Event("change"));
  await wait(50);
  r.dot = $('[data-dot="s7-3"]').dataset.s;
  r.calls = window.__calls;
  r.exportShown = !$("#cm-export").hidden || !$("#cm-copyjson").hidden;
  location.hash = "app-comments"; await wait(100);
  r.panelShown = !$("#app-comments").hidden;
  r.docShown = !$("#doc").hidden;
"""


@pytest.mark.skipif(not (CHROME and Path(CHROME).exists()), reason="needs Google Chrome")
def test_artifact_comments_and_db_status_in_browser(built, tmp_path):
    p, site, _ = built
    r = run_page(site, tmp_path, STUB, DRIVE % ARTIFACT)
    assert "error" not in r, r
    assert not r["cmBtn"] and "comment threads" in r["mode"]
    assert r["post"] and r["claude"] and not r["save"]
    calls = r["calls"]
    assert ["watch", "review"] in calls
    send = next(c for c in calls if c[0] == "send")[1]
    assert send["anchor"] == {"path": "fig-1", "x": 1, "y": 2}
    assert send["text"].startswith("[fig-1] Figure 1 · 7.3 Component Design\n\nLabel the platform services.")
    create = next(c for c in calls if c[0] == "create")[1]
    assert create["text"] == "[s7-3-t1-r2] 7.3 Component Design\n\nWhich runtime?"
    sets = [c for c in calls if c[0] == "set"]
    assert sets[0][1] == "review/s7-3"
    assert sets[0][2]["status"] == "agreed" and sets[0][2]["section"] == "7.3 Component Design"
    assert r["dot"] == "agreed"
    # published: comments live in the shared store, so no browser-only panel or download
    assert not r["exportShown"] and not r["panelShown"] and r["docShown"]


def test_svg_figure_is_copied_as_is(make_project):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 5"><rect width="10" height="5"/></svg>'
    root = make_project(content={"06-target.md": "# target\n## diagram\nFIGURE shape | A drawn shape\n"},
                        diagrams={"shape.svg": svg})
    p = Project.load(root)
    site_build.build(p)
    site = root / "out" / "site"
    assert (site / "media" / "fig-1.svg").read_text() == svg
    assert (site / "media" / "full" / "fig-1.svg").read_text() == svg
    assert 'src="media/fig-1.svg" data-full="media/full/fig-1.svg" alt="Figure 1"' in (site / "index.html").read_text()
    assert '"media/fig-1.svg", "media/full/fig-1.svg"' in (site / "PUBLISH.md").read_text()


def test_no_org_name_without_profile_org(make_project):
    from conftest import northwind_profile
    prof = northwind_profile()
    prof.pop("org")
    root = make_project(profile=prof)
    site_build.build(Project.load(root))
    page = (root / "out" / "site" / "index.html").read_text()
    assert "Northwind" not in page and "Organisation" not in page


# A hosted view whose comments stay in the browser (comments and db resolve
# null) hands the export to the downloads capability.
STUB_DOWNLOADS = """
window.__saves = [];
const dl = { save: async (req) => {
  window.__saves.push({ filename: req.filename, data: String(req.data) });
  if (window.__dlMode === "declined") throw { code: "declined", message: "no" };
  if (window.__dlMode === "unavailable") throw { code: "unavailable", message: "off" };
  return { status: "saved" };
} };
window.claude = { use: (n) => Promise.resolve(n === "downloads" && window.__dlMode !== "null" ? dl : null) };
"""

HOSTED_EXPORT = """
  $('[data-ref="s1-1-p1"]').click();
  $("#cmp-text").value = "Name the rural depots.";
  $("#cmp-save").click();
  location.hash = "app-comments"; await wait(100);
  r.exportShown = !$("#cm-export").hidden;
  let anchorClicks = 0;
  HTMLAnchorElement.prototype.click = function () { anchorClicks += 1; };
  if (r.exportShown) { $("#cm-export").click(); await wait(50); }
  r.saves = window.__saves;
  r.anchorClicks = anchorClicks;
  r.msg = $("#cm-msg").textContent;
  r.exportAfter = !$("#cm-export").hidden;
"""


@pytest.mark.skipif(not (CHROME and Path(CHROME).exists()), reason="needs Google Chrome")
@pytest.mark.parametrize("mode", ["saved", "declined", "unavailable", "null"])
def test_hosted_export_goes_through_downloads(built, tmp_path, mode):
    p, site, _ = built
    r = run_page(site, tmp_path, f'window.__dlMode = "{mode}";' + STUB_DOWNLOADS, DRIVE % HOSTED_EXPORT)
    assert "error" not in r, r
    assert r["anchorClicks"] == 0                       # never a download link inside a viewer
    if mode == "null":
        assert not r["exportShown"] and r["saves"] == []  # no capability: no dead button
        return
    assert r["exportShown"]
    [save] = r["saves"]
    assert save["filename"] == "DSS-v0.3-comments.json"
    data = json.loads(save["data"])
    assert data["format"] == "arch-doc-comments" and data["comments"][0]["anchor"] == "s1-1-p1"
    if mode == "saved":
        assert r["msg"].startswith("Saved 1 comment as DSS-v0.3-comments.json")
    elif mode == "declined":
        assert r["msg"].startswith("Not saved.") and r["exportAfter"]
    else:
        assert "not available here" in r["msg"] and not r["exportAfter"]


def test_publish_recipe_declares_downloads(built):
    p, site, _ = built
    md = (site / "PUBLISH.md").read_text()
    assert '`{"comments": {}, "db": {}, "downloads": true}`' in md
    assert "`downloads`: lets a viewer" in md



def test_view_caption_matches_the_word_document(make_project):
    from archdoc import docx_build
    root = make_project(content={"07-application.md": """
        # application
        ## views
        VIEW flow | Scan event flow | integration-flows
        """}, extra={"captions": {"view_note": "Drawn from the model of {doc:version}"}},
        diagrams={"flow.mmd": "flowchart LR\n  A --> B\n"})
    p = Project.load(root)
    site_build.build(p)
    page = (root / "out" / "site" / "index.html").read_text()
    [v] = p.views
    want = docx_build.view_caption(p, v)
    assert want == "Scan event flow (ArchiMate Application Cooperation). Drawn from the model of 0.3."
    assert f'<b class="fig-label">View 1.</b> {want}</figcaption>' in page


@pytest.mark.parametrize("fmt,shown", [(None, "20 October 2026"), ("iso", "2026-10-20"),
                                       ("%d/%m/%Y", "20/10/2026")])
def test_dates_follow_house_date_format(make_project, fmt, shown):
    from conftest import northwind_profile
    prof = northwind_profile()
    if fmt:
        prof.setdefault("house", {})["date_format"] = fmt
    root = make_project(profile=prof, extra={"history": [{"date": "2026-10-20", "version": "0.3",
                                                          "author": "SA", "change": "First"}]})
    site_build.build(Project.load(root))
    page = (root / "out" / "site" / "index.html").read_text()
    assert f"<td>Date</td><td>{shown}</td>" in page
    assert f"<td>{shown}</td><td>0.3</td>" in page                       # version history
    assert f"v0.3 &#183; {shown}</p>" in page                             # title block


def test_dependency_noun_follows_the_core(make_project):
    root = make_project(extra={"depends_on": [
        {"title": "Group Platform SAD", "kind": "capability", "version": "0.3", "ref": "GP"},
        {"title": "Northwind Platform", "kind": "capability", "version": "0.2", "ref": "NP"}]})
    site_build.build(Project.load(root))
    page = (root / "out" / "site" / "index.html").read_text()
    assert ('Depends on the Group Platform SAD v0.3; the Northwind Platform design v0.2.' in page)
    assert "SAD design" not in page



def test_tbc_noun_use_is_not_highlighted(make_project):
    root = make_project(content={"20-assurance.md": """
        # assurance
        ## checklist
        Every TBC has an owner before approval. The cutover date is TBC: Release manager.
        """})
    site_build.build(Project.load(root))
    page = (root / "out" / "site" / "index.html").read_text()
    assert "Every TBC has an owner" in page
    assert '<mark class="tbc" title="Owner: Release manager">TBC: Release manager</mark>' in page
    assert page.count('<mark class="tbc"') == 1
