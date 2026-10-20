"""`archdoc comments import`: merge exported or read-back comments into
out/comments.json and print them by anchor with the section number and title."""
import io
import json
import shutil
from pathlib import Path

import pytest

from archdoc import Project
from archdoc import comments
from conftest import run_cli

FIXTURE = Path(__file__).parent / "fixtures" / "site_build" / "review"

EXPORT = {
    "format": "arch-doc-comments", "version": 1,
    "document": {"title": "Depot Scanning Service", "short": "DSS", "version": "0.3"},
    "exported": "2026-10-20T10:00:00.000Z",
    "comments": [
        {"id": "a1", "anchor": "s7-3-t1-r2", "section": "7.3 Component Design", "label": "", "quote": "",
         "text": "Which runtime?", "author": "Reviewer A", "at": "2026-10-20T09:00:00.000Z"},
        {"id": "a2", "anchor": "s1-1-p1", "section": "1.1 Delivery Scope", "label": "",
         "quote": "Rural depots join in a later release", "text": "Name the release.", "author": "Reviewer A",
         "at": "2026-10-20T09:05:00.000Z"},
        {"id": "a3", "anchor": "fig-1", "section": "7.3 Component Design", "label": "Figure 1", "quote": "",
         "text": "Label the arrows.", "author": "", "at": "2026-10-20T09:06:00.000Z"},
    ],
    "review": {"s7-3": {"status": "changes", "section": "7.3 Component Design", "at": "2026-10-20T09:10:00.000Z"}},
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "review"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("out"))
    return root


def write(tmp_path, data, name="export.json"):
    f = tmp_path / name
    f.write_text(json.dumps(data))
    return f


def test_import_merges_and_prints_by_anchor(project, tmp_path):
    f = write(tmp_path, EXPORT)
    r = run_cli("-C", project, "comments", "import", f)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "3 new comments of 3" in out
    # document order: 1.1 before 7.3 table row before figure 1
    i1, i2, i3 = out.index("s1-1-p1  1.1 Delivery Scope"), out.index("s7-3-t1-r2  7.3 Component Design"), \
        out.index("fig-1  7.3 Component Design")
    assert i1 < i2 < i3
    assert "Reviewer A" in out and "Which runtime?" in out and "“Rural depots join in a later release”" in out
    assert "s7-3     changes    7.3 Component Design" in out
    store = json.loads((project / "out" / "comments.json").read_text())
    assert [c["id"] for c in store["comments"]] == ["a1", "a2", "a3"]
    assert store["review"]["s7-3"]["status"] == "changes"
    assert store["document"]["version"] == "0.3"


def test_reimport_adds_nothing_and_latest_status_wins(project, tmp_path):
    p = Project.load(project)
    comments.import_file(p, write(tmp_path, EXPORT), io.StringIO())
    later = json.loads(json.dumps(EXPORT))
    later["comments"].append({"id": "b1", "anchor": "s19-1-t1-r1", "text": "Raise the rating.",
                              "at": "2026-10-21T08:00:00Z"})
    later["review"]["s7-3"] = {"status": "agreed", "at": "2026-10-21T08:00:00Z"}
    buf = io.StringIO()
    comments.import_file(p, write(tmp_path, later, "later.json"), buf)
    assert "1 new comment of 4" in buf.getvalue()
    older = {"comments": [], "review": {"s7-3": {"status": "in-review", "at": "2026-10-19T08:00:00Z"}}}
    comments.import_file(p, write(tmp_path, older, "older.json"), io.StringIO())
    store = json.loads((project / "out" / "comments.json").read_text())
    assert len(store["comments"]) == 4
    assert store["review"]["s7-3"]["status"] == "agreed"
    assert len(store["imports"]) == 3


def test_read_back_threads_take_their_anchor_from_the_prefix(project, tmp_path):
    threads = [{"text": "[s7-3-p1] 7.3 Component Design\n\nSay which store.", "author": "Reviewer B"},
               {"text": "[s7-3-t1-r9] 7.3 Component Design\n\nA row that moved."},
               {"text": "A shell comment with no prefix."}]
    p = Project.load(project)
    buf = io.StringIO()
    comments.import_file(p, write(tmp_path, threads), buf)
    out = buf.getvalue()
    assert "s7-3-t1-r9  7.3 Component Design  (anchor not in this version; nearest is s7-3-t1)" in out
    assert "(no anchor)" in out and "A shell comment with no prefix." in out
    assert "    Say which store." in out and "[s7-3-p1]" not in out.split("s7-3-p1", 1)[1].split("\n\n")[0]
    # a second import of the same threads adds nothing (ids are derived from the content)
    buf = io.StringIO()
    comments.import_file(p, write(tmp_path, threads), buf)
    assert "0 new comments of 3" in buf.getvalue()


def test_version_mismatch_is_noted(project, tmp_path):
    old = json.loads(json.dumps(EXPORT))
    old["document"]["version"] = "0.2"
    buf = io.StringIO()
    comments.import_file(Project.load(project), write(tmp_path, old), buf)
    assert "exported from v0.2; this document is v0.3" in buf.getvalue()


@pytest.mark.parametrize("data,msg", [
    ({"format": "other"}, "is not arch-doc-comments"),
    ({"comments": [{"anchor": "s1"}]}, "has no text"),
    ({"comments": [], "review": {"s1": {"status": "done"}}}, "must be one of"),
    ("text", "expected a JSON object"),
])
def test_bad_files_are_refused(project, tmp_path, data, msg):
    r = run_cli("-C", project, "comments", "import", write(tmp_path, data))
    assert r.returncode == 2 and msg in r.stderr
    assert not (project / "out" / "comments.json").exists()


def test_unreadable_file(project, tmp_path):
    f = tmp_path / "broken.json"
    f.write_text("{")
    r = run_cli("-C", project, "comments", "import", f)
    assert r.returncode == 2 and "broken.json" in r.stderr
