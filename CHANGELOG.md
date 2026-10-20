# Changelog

## Unreleased

### Changed

- **The deck viewer shows how to move through it.** Opened in the Artifact viewer, the deck read as a single page: the only navigation was the keyboard, which needs the frame to have focus, and the only sign of more slides was a faint counter. It now has previous and next buttons (on hover, always on touch), click zones on the slide's left and right thirds that leave text selection and links alone, a counter that opens an overview of every slide as live thumbnails (also `G`), a progress bar, a hint on the cover that fades, and it takes focus on load and on the first pointer move. Slides scale to the viewport's width and height; on a tall viewport the controls sit under the slide. None of it appears in print, `?shot=1` or `?check=1`. `?check=ui` and `window.__deckUI()` let a headless browser drive and read it.
- **People on the cover and in document control.** A role the name already says is left out, so the cover no longer reads "Author: Solution Architect, Architect". The deck, site and Word document share one formatter (`project.person_line`).
- **Examples:** both Northwind designs name fictional people as author and owner (Priya Nair and Tom Okafor; Lena Brandt and Marcus Hale), with their roles in `role`, in arch-doc.yaml, the version history and the stakeholder registers.

### Added

- **Citing designs that are not dependencies:** a `consumers` entry may carry a `ref` with a `path` or `sections`, and `cites` lists designs this one only refers to. `{dep:}` looks in `depends_on`, then `consumers`, then `cites`; only `depends_on` is drawn and boundary-checked. Refs must be unique across the three lists, and each list's entries and section maps are validated.
- **Seed field aliases** for template headers: `stakeholder.name` (stakeholder), `functional-requirement.traces_to` (source), `risk.rating` (inherent risk), `risk.mitigation` (control), `cutover-step.order` (step), `cutover-step.after` (dependency), `assumption.validate_by` (validation date). `aliases: {field: [words]}` on any type is read by `extract`.
- **arch-doc.yaml:** `exclude` drops chapters or sections for one document; `allowed_terms` keeps names a logical design uses on purpose; `consumers` lists the designs built on a capability design, which its summary picture draws it under; `captions.view_note` adds a sentence to every Word view caption; `catalogue.columns` limits the Word catalogue's shared and example columns; a `depends_on` entry without a path can give `sections` so `{dep:REF:10.2}` resolves.
- **Profile:** `keep_name: true` on a system lets a logical design name it; `systems.ea_viewpoint_names` renames a viewpoint for every output; `house.date_format` (`long`, `iso` or a strftime pattern) and `house.captions.view_note` for the Word document.
- **Metamodel:** a section's `labels:` and `column_map` head its register columns with the organisation's words (`extract` now writes `column_map` for matched sections too); an artefact type may take a list of prefixes, `value_labels` and `plural`; ids may carry an upper-case namespace (`NW-RSK-21`).
- **Content:** `REGISTER ... labels f="Header"`; `{cat:objects}`, `{cat:relationships}` and `{cat:<object type>}` count the EA model; register values resolve placeholders, and a TBC inside a longer value is an open item.
- **Checks:** a TBC whose owner slot names a time or state warns; a plain table that gives a record's field a value its register contradicts warns (`consistency`); deck.yaml is validated by `check` as `build deck` would, so `build all` writes nothing from a broken deck. The `layer` check keeps the longest overlapping match and no longer bans bare vendor names.
- **Docs:** every option above in the references, each with an example run against a copy of the Northwind examples; a Chrome troubleshooting table in `diagrams.md`.

### Fixed

- **One owner rule:** `registers.owner_problem` and `is_owner` decide what an owner slot may hold, for the checks and every output. Joint owners ("Platform team with the platform owner", "Security / Data owner") pass, with the six-word limit applied to each part; an open item whose slot names no owner shows "No owner" and keeps the slot as `OpenItem.owner_text`.
- **One TBC detector:** `registers.tbc_markers` marks a TBC only where it marks a value. "Every TBC has an owner", "each open TBC" and a quoted 'TBC' are not open items, in the checks, the site or the deck.
- **Table-value check keying:** a table is keyed only on its first column, a column whose header names the id, or one the column map maps to `id`; other id columns are cross-references and are not compared. A section's column map applies only to records of its own registers.
- **A broken artefact type is reported once**, at its cause, instead of again by every section, picture and column map that names it.
- **Extract:** label and alias matches beat containment, "or" and slash alternatives are read on both sides, a shared distinctive word counts, and trailing `?`, `:` and `*` are ignored. Only labels for values that are still enums are copied.
- **Word catalogue:** `catalogue.labels` names its headers; the shared column reads "Shared with the <design>".
- **Deck:** bodies fill to the foot (every table spans the width; the allocator adds until the next addition would not fit) and the layout check judges each lane; no header-only or thin tables; callouts never cover the drawing; a generated picture must say something and never repeats; open items and their count come from `Project.open_items()`, as on the site; dates follow `house.date_format`, now house-wide.

- **Word build:** generated text never carries a template's strike-through or highlight; every header row repeats and keeps with the first data row; a table too wide even at 8pt is named by anchor, section and source line.
- **Site:** view captions, dates (`house.date_format`) and dependency names read as in the Word document.
- **Checks:** the owner-slot rule is structural (a clause, a condition, a state, a design stage, a date or more than six words is not an owner; "May Chen" is); table values are matched to fields through the section's `column_map` and labels first; deck.yaml findings carry their line and print the file name once.
- **Open items:** `Project.open_items()` folds the TBCs into one item per record and per paragraph, list item or table row, with resolved text cut at a word boundary. The site's panel and the deck list and count these.

- **Chrome runs** (`archdoc/chrome.py`, shared by diagram rendering and the deck and site browser tests): each run has its own temporary profile and process group, and its output is read as it streams. Rendering an SVG accepts the PNG as soon as Chrome has reported writing it and it is complete, killing the process group, whatever the exit code; any other run raises an error naming the cause ("exited N", "did not exit within 120s", "wrote no complete screenshot" or "exited without complete output") with Chrome's output. No retry.

### Verified

- Navigation tests in headless Chrome at 1810 x 1000 for both examples (buttons, click zones, G, Escape, counter, thumbnail jump, no duplicate ids) and shot mode hiding the chrome; the layout check stays empty for both examples.

## 0.1.0 (2026-10-20)

The first release: one project of typed registers and chapter files, built into a Word document, a review site with anchored comments and a TL;DR deck, with the skill that tells Claude how to run the interview, fill the registers, draft, draw, check, build, publish and take review comments back.

### Added

- **The skill.** `skills/arch-doc/SKILL.md`: the procedure, from finding or starting a project through the interview, registers before prose, drafting, diagrams, checks and the build, to publishing and the review loop. Seven references: `interview.md` (the questions in batches with defaults, and how each answer changes the document), `metamodel.md` (the format, extending it, extracting one from a template), `project.md` (arch-doc.yaml, registers, the content format and placeholders), `writing.md` (voice, TBC, and what each chapter's story, detail and picture should say), `checks.md` (each check, its fix and what it cannot see), `diagrams.md` (arch-diagram or Mermaid, rendering, picture slides) and `outputs.md` (the three outputs, publishing the site and deck as Artifacts, reading the review back).
- **The core.** The seed metamodel (22 chapters, 30 artefact types, 15 viewpoints in CoreEA, ArchiMate, TOGAF and Essential), the profile with defaults and `logical_<field>` variants, the project loader with numbering after profile filtering, stable anchors, `[new]` sections and `{dep:}` references into the designs a document depends on.
- **The Word document** (`build docx`): the organisation's template filled in place, or a neutral A4 document; `template.fields` for cover text; style resolution from the profile, then the template, then the defaults; figures rendered or the build stopped, never a placeholder.
- **Template extraction** (`extract`): chapters and sections matched to the seed, `unmatched`, `template_columns`, `column_map`, `extracted_from`, and a profile fragment (`--profile-out`); `--seed` matches against another metamodel.
- **The review site** (`build site`): anchored paragraphs, rows and figures, open items, per-section review status, comments through the Artifact `comments` and `db` capabilities or kept locally and exported, `PUBLISH.md` with the publish call; `comments import` reads them back.
- **The TL;DR deck** (`build deck`): cover, run dividers, and story, detail and picture slides per chapter from `deck.yaml` or derived, generated pictures of nine kinds, speaker notes, print to PDF, and a layout check the browser runs.
- **The checks** (`check`): fourteen check ids plus the core's `schema` and `content`, each with file, line and anchor; `build` refuses on errors.
- **Diagrams** (`diagrams`): arch-diagram detection, Mermaid, arch-diagram view files and scripts, staleness by modification time, `--render`, `--force`, `--json`.
- **Examples:** `northwind-platform` (a capability design) and `northwind-parcels` (a solution design on it), complete and clean.
- README with install, quick start, the outputs (screenshots rendered from the examples) and the relationship to arch-diagram; `docs/SPEC.md` brought in line with the build.

### Changed

- Mermaid figures render with `@mermaid-js/mermaid-cli@11.12.0`, pinned, and the examples' figures are re-rendered with it.
- The seed marks `integration/failure-handling` and `data/retention` with `covers:`, so their per-record tables are checked against the register.

### Verified

- 309 tests pass.
- A fresh headless Claude Code session, with only this plugin loaded through `--plugin-dir` and nothing installed, took an inline interview (Jira Service Management, no EA repository, ArchiMate, AWS, Okta, GitLab CI, Grafana), picked the skill, scaffolded the project, filled registers and chapters, drew figures, ran the checks clean and built all three outputs. It was run twice; what the first run stumbled on (viewpoint keys, quoted TBCs in tables, a command stored in a zsh variable, the author's role repeated) is answered in the skill and references.
