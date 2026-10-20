"""Shared fixtures: paths, and a builder for small throwaway projects."""
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "arch-doc"
SCRIPTS = SKILL / "scripts"
EXAMPLES = SKILL / "examples"
SEED = SKILL / "metamodels" / "seed.yaml"
CLI = SCRIPTS / "archdoc.py"
sys.path.insert(0, str(SCRIPTS))

NORTHWIND_PROFILE = EXAMPLES / "northwind-profile.yaml"


def northwind_profile() -> dict:
    return yaml.safe_load(NORTHWIND_PROFILE.read_text())


def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                          cwd=cwd)


@pytest.fixture
def make_project(tmp_path):
    """make_project(content={file: text}, registers={type: yaml text},
    profile=dict, kind=..., extra=dict, name=...) -> project root."""

    def make(content=None, registers=None, profile=None, kind="solution", extra=None, name="doc",
             diagrams=None):
        root = tmp_path / name
        root.mkdir()
        cfg = {"title": "Test Design", "short": "TD", "kind": kind, "version": "0.3", "date": "2026-10-20",
               "profile": "profile.yaml", "metamodel": "seed"}
        cfg.update(extra or {})
        (root / "arch-doc.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
        (root / "profile.yaml").write_text(yaml.safe_dump(northwind_profile() if profile is None else profile))
        (root / "content").mkdir()
        for fname, text in (content or {}).items():
            (root / "content" / fname).write_text(textwrap.dedent(text).lstrip("\n"))
        (root / "registers").mkdir()
        for rtype, text in (registers or {}).items():
            (root / "registers" / f"{rtype}.yaml").write_text(textwrap.dedent(text).lstrip("\n"))
        (root / "diagrams").mkdir()
        for fname, text in (diagrams or {}).items():
            (root / "diagrams" / fname).write_text(text)
        return root
    return make


@pytest.fixture
def examples_copy(tmp_path):
    """Both examples and their shared profile, copied so a test can edit them."""
    dst = tmp_path / "examples"
    shutil.copytree(EXAMPLES, dst)
    return dst
