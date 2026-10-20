# Phase 2: shared brief

Phase 1 is done. It covers the core package (`skills/arch-doc/scripts/archdoc/`), the seed metamodel, the CLI (`init`, `profile`, `numbering`, `status`), the Northwind example skeletons and 92 passing tests. Five builders now work **in parallel in the same repo**, each owning its own modules.

| Owner | Modules | CLI |
|---|---|---|
| docx | `docx_build.py`, `extract.py` | `build docx`, `extract` |
| site | `site_build.py`, `assets/site.css`, `assets/site.js`, `comments.py` | `build site`, `comments import` |
| deck | `deck_build.py`, `pictures.py`, `assets/deck.css`, `assets/deck.js` | `build deck` |
| checks | `checks.py` | `check`, plus the pre-build gate in `build` |
| examples | `diagrams.py`, the content, registers, diagrams and `deck.yaml` of both examples | `diagrams` |

## Rules for working side by side

- **Read first.** That means `docs/SPEC.md` in full, the public API docstring in `archdoc/__init__.py`, and then the core modules you consume.
- **Own your files.** Edit only the files you own and their tests (`tests/test_<module>.py`, plus fixtures under `tests/fixtures/<module>/`).
- **Shared files.**
  - Core modules, `archdoc.py` and `conftest.py` are shared. Change them only when you must, keep the change small and additive (never rename or remove anything), and commit it on its own straight away so the others pick it up.
  - Don't edit README.md, CHANGELOG.md, docs/SPEC.md or seed.yaml. Report anything they need; phase 3 owns them. The exception is examples: a metamodel defect it finds may be fixed in seed.yaml with a small additive change, mentioned in its report.
- **Commits.** Commit only your own paths, by explicit path: `git add <paths> && git commit -m ...`. Never `git add -A`, `commit -a`, stash, reset, rebase or checkout of another's files.
  - If `index.lock` exists, wait a few seconds and retry.
  - Author: the repo's configured user. End each message with:
    ```
    Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
    Claude-Session: https://claude.ai/code/session_01SRX7VfCvkGLi8oXh6LDiCp
    ```
  - Say *why* in the message.
- **Tests.** Run `uv run --with pytest --with pyyaml --with python-docx --with pillow pytest` from the repo root. Your tests must pass, and the whole suite must still pass when you finish. If someone else's test breaks because of a shared change you made, fix your change.
- **Organisation-neutral.** No real organisation, person or product name in code or assets. Products appear only through the profile, and in the fictional Northwind examples.
- **No placeholders, no stubs, no "coming soon".** Each feature you own must work end to end on both examples.
- **Contracts.**
  - Builders: `build(project, out_dir=None) -> list[Path]`. The default `out_dir` is `<project>/out/`.
  - `checks.run(project) -> list[Finding]`.
  - CLI modules: `cli(args) -> int`.
  - The `archdoc.py` wiring already exists. Follow it, and extend it additively if you need flags.
- **Verify by looking.**
  - HTML outputs: render with headless Chrome (`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --screenshot=<png> --window-size=W,H file://...`) and read the PNG.
  - The docx: convert to PDF with `soffice --headless --convert-to pdf` if available, or render page images another way, and look.
  - Fix what you see.
- **Outputs.** Write them under each example's `out/`, which is gitignored. Never commit build outputs.
- **Sandbox.** Work only inside `the repository root`. Reading the reference paths given in your prompt is fine.

## Report

Report:
- what you built;
- the CLI usage;
- your tests and the full-suite result;
- every shared-file change, with its commit hash;
- what phase 3 must document (README, references/*.md);
- any SPEC deviation and why.
