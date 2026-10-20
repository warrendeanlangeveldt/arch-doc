# arch-doc: specification

arch-doc is a Claude Code plugin that writes architecture design documents for review boards. It works for capability designs, which describe a platform others build on, and solution designs, which describe one solution on those platforms. From one project it builds three outputs:

1. the Word document, built from the organisation's own template or a neutral default;
2. a review site with anchored comments and per-section review status;
3. a TL;DR slide deck, three slides per chapter, one of which is a full-slide architecture picture.

It belongs to no organisation. The chapter structure comes from a **metamodel**. The organisation's systems (ITSM, EA repository, cloud, identity, CI/CD, monitoring) and its governance forums come from a **profile** that arch-doc asks for at the start. Diagrams use the `arch-diagram` plugin when it is installed. arch-doc suggests installing it and falls back to Mermaid when it isn't.

The repo is `github.com/warrendeanlangeveldt/arch-doc`, MIT licence, laid out like `arch-diagram`.

This specification describes arch-doc 0.1.0 as built. Where the build departed from the first draft, the section says so under **As built**.

## 1. Principles

- **The model comes first.** Facts live in registers (typed YAML). The prose cites them and never restates them by hand, so counts, ids and owners can't drift.
- **One project, three outputs.** Word, site and deck all read the same parsed project. The site and deck never re-parse the docx.
- **Organisation-neutral.** No organisation, person, product or forum name is hard-coded. Anything system-specific is a profile variable, or a section that is included only when the profile says so.
- **Layered designs.** A document declares the designs it depends on. Each kind of design has boundaries, and the checker enforces them. For example, a capability design stays logical when `layer: logical`, and a solution design treats its platform as a dependency, not as content.
- **TBC is a value, not a gap.** Every TBC names an owner. The checker fails a TBC that has none.
- **Writing.** Write declaratively and briefly, in the first person plural. Say the bad thing plainly. Use no marketing words and no padding. A thin chapter stays thin.

## 2. Repo layout

```
.claude-plugin/plugin.json, marketplace.json
README.md  CHANGELOG.md  LICENSE
docs/SPEC.md
skills/arch-doc/
  SKILL.md                     routing and the procedure
  references/
    interview.md               the profile interview: questions and how answers map to the profile
    metamodel.md               metamodel file format and how to extend or extract one
    project.md                 project layout, arch-doc.yaml, registers, content format
    writing.md                 voice and TBC rules, story / detail / picture guidance per chapter
    checks.md                  every check, what it catches, how to fix it
    diagrams.md                arch-diagram vs Mermaid, figure naming, picture slides
    outputs.md                 docx, site and deck build, publish, reading review comments back
  metamodels/
    seed.yaml                  the default metamodel (section 4)
  scripts/
    archdoc.py                 the CLI (section 8)
    archdoc/                   the package
      project.py  metamodel.py  profile.py  content.py  registers.py  scaffold.py
      docx_build.py  site_build.py  deck_build.py  checks.py  diagrams.py  extract.py  pictures.py  comments.py
      assets/site.css site.js deck.css deck.js
      data/products.yaml       cloud product names and patterns the layer check rejects
      data/voice.yaml          phrases the voice check warns about
  examples/
    northwind-parcels/         a complete worked example (a solution design)
    northwind-platform/        the capability design it depends on
    northwind-profile.yaml     the fictional profile both share
docs/
  SPEC.md                      this file
  *.png                        README screenshots, rendered from the examples
tests/
```

Runtime: Python 3.10+ through `uv run --with python-docx --with pyyaml --with pillow`. No pandoc. Mermaid rendering uses `npx -y @mermaid-js/mermaid-cli@11.12.0` when Node is present; the version is pinned (`diagrams.MERMAID_CLI`) so every machine renders the same figure, and is raised deliberately to a release at least two weeks old. Without Node, the site renders Mermaid in the browser from a pinned CDN build, the deck shows the chapter's generated picture instead, and the docx build stops and names the missing tool (section 9).

## 3. The project

A project is one document:

```
arch-doc.yaml          document identity and settings
profile.yaml           the organisation profile (may be shared: `profile: ../org/profile.yaml`)
registers/*.yaml       typed artefacts (requirements, decisions, risks, ...)
content/NN-<slug>.md   one file per chapter, prose and directives
diagrams/              figure sources (.ead / .py for arch-diagram, .mmd for Mermaid) and rendered PNG/SVG
deck.yaml              per-chapter slide claims (written by Claude; optional, defaults derived)
out/                   build outputs: <Title> v<ver>.docx, site/, deck/
```

### arch-doc.yaml

```yaml
title: Parcel Tracking Solution
short: PTS                      # footer and deck short name
kind: solution                  # solution | capability
layer: logical-and-physical     # logical | logical-and-physical; logical bans product names (section 7)
version: "0.1"
date: 2026-10-20
author: {name: ..., role: Architect, team: ...}
owner: {name: ..., role: ...}
metamodel: seed                 # seed | path to a metamodel YAML
profile: profile.yaml
template: null                  # path to the organisation's .docx template, or null for the neutral default
depends_on:
  - {title: Northwind Platform, kind: capability, version: "0.2", path: ../northwind-platform, ref: NP}
history:
  - {date: 2026-10-20, version: "0.1", author: ..., change: First draft}
banned_terms: []                # extra terms the layer check rejects
```

**As built**, arch-doc.yaml also takes `exclude` (chapter or `chapter/section` keys dropped for this document after profile filtering), `allowed_terms` (names the `layer` check keeps), `consumers` (designs built on this one, drawn in its pictures, citable when they carry a `ref`), `cites` (designs it only refers to; `{dep:}` looks in `depends_on`, then `consumers`, then `cites`, and only `depends_on` is a dependency), `captions.view_note` `catalogue.columns` and `catalogue.labels` (Word only); a `depends_on` entry without a path may give `sections: {"10.2": Hosting Model}` so `{dep:REF:10.2}` resolves. People print as one line with any role the name already says left out; `init` writes an unknown name as `TBC: <roles.architect>`.

`depends_on[].path` lets `{dep:NP:7.3}` resolve to "the Northwind Platform design, section 7.3 Component Design", using that project's numbering.

### Registers

Each artefact type in the metamodel (section 4) has one register file, `registers/<type>.yaml`: a list of records. Fields come from the type's schema. `id`, `title` and `status` are always present; `owner` is present where the type declares it. Example:

```yaml
- id: RSK-03
  title: Carrier API rate limits throttle peak scans
  category: architecture        # architecture | operational
  likelihood: medium
  impact: high
  rating: high
  owner: Integration lead
  mitigation: Queue and back off; carrier quota uplift requested
  status: open
```

Any field value may be `TBC` or `TBC: <owner>`. A bare `TBC` takes the record's `owner`. If the record has no owner, the check `tbc-owner` fails.

**As built:** a TBC inside a longer value is an open item with the same owner rule. Values may hold placeholders, resolved wherever they are shown. Ids may use any of a type's prefixes and may start with an upper-case namespace (`NW-RSK-21`). Tables show enum and status values labelled (`in-build` as "In build", or the type's `value_labels`).

### Content format

One Markdown file per chapter. This generalises the format the SAD builds already use:

```
# <chapter key>                     e.g. `# requirements`; text before the first ## is the chapter lead-in
## <section key or title>           a metamodel section; `## Title [new]` adds a section not in the metamodel
plain paragraph
- bullet
| a | b |                           a table, first row is the header
REGISTER <type> [where k=v ...] [cols a,b,c]   a register table, columns from the type unless given
FIGURE <name> | <caption>           diagrams/<name>.png (or .svg / .mmd), numbered "Figure n"
VIEW <name> | <view title> | <viewpoint>   an EA view, numbered "View n"; the viewpoint is a key, a title or its EA name
CATALOGUE [<model.json>]            the EA model summary (default diagrams/model.json), when the profile has an EA metamodel
<!-- comment -->                    ignored
```

Placeholders, resolved at build time:

| Placeholder | Becomes |
|---|---|
| `{sec:<chapter key>/<section key>}` | this document's section number, e.g. `7.3` |
| `{ch:<chapter key>}` | the chapter number |
| `{fig:<name>}`, `{view:<name>}` | "Figure n", "View n" |
| `{count:<type>[ where k=v]}` | the number of matching register records |
| `{ids:<type>[ where k=v]}` | an id range or list, e.g. "RSK-01 to RSK-07" |
| `{reg:<id>.<field>}` | a field of a record |
| `{dep:<ref>:<n.n>}` | a dependency's section reference (above) |
| `{p:<profile path>}` | a profile value, e.g. `{p:systems.itsm.name}`, `{p:forums.design_authority.short}` |
| `{doc:version}`, `{doc:title}` | from arch-doc.yaml |
| `{cat:objects}`, `{cat:relationships}`, `{cat:<type>}` | counts from the EA model (as built) |

**As built:** `REGISTER` also takes `labels f="Header" ...`; headers come from the directive's labels, then the section's `labels:` or `column_map`, then the type's.

A literal number that should be a count, such as "seven risks", is a check failure when the register disagrees (section 7, `count-prose`).

## 4. The metamodel

`metamodels/seed.yaml` is the default. It is derived from a 22-chapter enterprise solution architecture document template, the structure arch-doc was first used with. It is genericised: system-specific chapters become profile-conditional, and organisation names, people and products are removed. All guidance text is written fresh.

Its structure:

```yaml
name: seed
version: 1
document_kinds:
  capability: {purpose: "a platform or zone other designs build on", excludes: [...section keys...]}
  solution:   {purpose: "one solution, on the platforms it depends on"}
chapters:
  - key: summary
    title: Executive Architecture Summary
    question: What is being approved, and why now?
    story: the decision sought and the state of the design in one view
    picture: {kind: layers, from: depends_on}       # default picture when the chapter has no figure (section 6)
    sections:
      - key: scope
        title: Delivery Scope
        guidance: ...
        artefacts: []
      - key: decision-sought
        title: Decision Sought
        artefacts: [decision-request]
      ...
  - key: service-management
    title: "{p:systems.itsm.category_title}"          # e.g. "Service Management & Configuration Records"
    when: systems.itsm                                 # include only when the profile names an ITSM
    sections:
      - key: cmdb
        title: "{p:systems.itsm.cmdb_title}"           # profile supplies "ServiceNow CMDB & CSDM", "Jira Assets", ...
        when: systems.itsm.has_cmdb
artefact_types:
  risk:
    prefix: RSK
    fields: {category: [architecture, operational], likelihood: [low, medium, high], impact: [low, medium, high],
             rating: [low, medium, high, extreme], owner: text, mitigation: text, residual: [low, medium, high], status: [open, mitigated, accepted, closed]}
    columns: [id, title, likelihood, impact, rating, owner, status]
  ...
viewpoints:
  context: {title: Solution Context, ea: {coreea: Application Context, archimate: Application Cooperation, togaf: Solution Concept}}
  ...
```

The seed's 22 chapters, in order, with their keys:

1. `summary`: Executive Architecture Summary
2. `context`: Solution Context & Blueprint Alignment
3. `governance`: Stakeholders, Governance & Decision Rights
4. `requirements`: Requirements & Design Drivers
5. `current-state`: Current State Architecture
6. `target`: Target Solution Overview
7. `application`: Application & Component Architecture
8. `integration`: Integration & API Architecture
9. `data`: Data & Information Architecture
10. `infrastructure`: Infrastructure, Hosting & Deployment
11. `security`: Security & Controls
12. `nfr`: Non-Functional Requirements Realisation
13. `decisions`: Local Architecture Decisions, Deviations & Exceptions
14. `operations`: Operational Readiness & Service Transition (its service-management subsection is profile-conditional)
15. `monitoring`: Monitoring & Event Management
16. `service-processes`: Service Management Process Readiness (ITIL when `systems.itsm.framework: itil`)
17. `runbooks`: Runbooks & Operational Procedures
18. `transition`: Cutover, Release, Hypercare & Handover
19. `risks`: Risks, Issues & Dependencies
20. `assurance`: Architecture Assurance & Acceptance Evidence
21. `lifecycle`: Decommissioning & Lifecycle Management
22. `appendix`: Appendix (glossary, required views, EA object guide when the profile has an EA metamodel, repository views when it has an EA repository)

Artefact types in the seed:

- requirements: `business-requirement`, `functional-requirement`, `nfr`
- governance: `stakeholder`, `forum`, `checkpoint`
- decision records: `decision`, `decision-request`, `assumption`, `constraint`, `dependency`
- design: `capability`, `application`, `component`, `environment`, `integration`, `data-object`, `data-flow`, `control`
- risk and exceptions: `risk`, `issue`, `exception`
- operations: `runbook`, `readiness-item`, `process-readiness`, `alert`
- transition and assurance: `cutover-step`, `acceptance-item`
- lifecycle and reference: `retired-component`, `glossary-term`

Each type carries a field schema, default columns and a status vocabulary that maps to the outputs' status chips (`done` / `partial` / `not-started` / `tbc`).

**As built**, artefact types also take a list-valued `prefix`, `value_labels`, `plural` and `aliases` (template header words per field, read by `extract`), and sections `labels:`, `column_map` and `template_columns`. Sections also take:

- `optional: true`: exempt from the `empty` check;
- `guidance_on: <profile path>` with `guidance_by`, so the variant is chosen by one named system;
- `covers: <type>`: the section answers per record of a register it does not show (the seed sets it on `integration/failure-handling` and `data/retention`); the `empty` check then wants every record in its table. Guidance that says "For each <register noun>" has the same effect without the key.

A chapter's `picture` may also name `fallback` (a kind, a list, or picture mappings), or give a list-valued `by`; the deck draws the first that has records and ends at `layers` from `depends_on`. Artefact types carry `labels` (column headings per field) as well as `columns`.

**Extraction.** `archdoc extract <template.docx>` reads an organisation's own template and writes a metamodel YAML. It takes chapters from Heading 1, sections from Heading 2, and table headers as candidate artefact columns. It matches each chapter to the closest seed chapter by title, and inherits that chapter's artefacts, picture and guidance where they match. Chapters it can't match are marked `unmatched: true` for Claude to fill in with the user. It maps the template's heading and table styles into the profile's `template.styles`, so the docx build can fill that template in place.

**As built:** `archdoc extract <template.docx> [-o metamodel.yaml] [--profile-out fragment.yaml] [--seed <metamodel>] [--profile-out fragment.yaml] [--seed <metamodel>]`. Headings are found by outline level through `basedOn`, whatever the styles are called. The metamodel written carries `extracted_from` (the template file), `unmatched: true` on chapters and sections with no seed counterpart, `template_columns` (each table header in a section) and, for an unmatched section whose header reads like an artefact type, that type as its register with a `column_map` from header to field. The profile fragment holds `template.path`, `template.styles` (roles `h1`, `h2`, `body`, `bullet`, `table`, `caption`, `toc1`, `toc2`) and `template.fields`: cover text to replace, `{template text: replacement}`, where a replacement may use placeholders and `null` leaves the text as it is. The fragment is printed unless `--profile-out` names a file. The metamodel always loads.

## 5. The profile and the interview

`profile.yaml` describes the organisation, not the document. Many projects can share one. Claude builds it by interview (`references/interview.md`), one short batch of questions at a time, with the defaults offered:

```yaml
org: {name: Northwind, short: NW}
systems:
  itsm: {name: ServiceNow, framework: itil, has_cmdb: true, cmdb_title: "ServiceNow CMDB & CSDM",
         category_title: "Service Management & Configuration Records"}   # or Jira Service Management, BMC Helix, none
  ea_repository: {name: none}            # OrbusInfinity, LeanIX, Ardoq, Sparx, BiZZdesign, none
  ea_metamodel: archimate                # coreea | archimate | togaf | essential | none
  cloud: [azure]                         # azure | aws | gcp | on-prem (list)
  identity: {name: Entra ID}
  cicd: {name: GitHub Actions}
  monitoring: {name: Datadog}
  source_control: {name: GitHub}
forums:
  design_authority: {name: Architecture Review Board, short: ARB}
  change: {name: Change Advisory Board, short: CAB}
  security: {name: Security Review, short: SR}
roles: {architect: Solution Architect, service_owner: Service Owner}
house:
  palette: {ink: "#15252B", accent: "#2F6F7C", ...}   # outputs' tokens; defaults are neutral
  fonts: {heading: Source Serif 4, body: IBM Plex Sans}
template:
  path: null
  styles: {h1: Heading 1, h2: Heading 2, body: Normal, bullet: List Paragraph, table: Table Grid, caption: Caption}
```

What the answers change:

- Profile-conditional chapters and sections are included or dropped. Titles are filled from profile values.
- Guidance text switches to the variant for the named system, where the metamodel has one (`guidance_by: {servicenow: ..., jira-service-management: ...}`), and falls back to generic text otherwise.
- Default diagrams use the cloud's icon pack (with arch-diagram) and the EA metamodel's notation for views.

**As built**, the profile also takes:

- `logical_name` on any system, and `logical_<field>` for any other text field of it (`logical_cmdb_title`). In a `layer: logical` document `{p:...}` renders the logical variant, and the system's `name` joins the `layer` check's banned terms.
- `house.palette` keys `ink`, `muted`, `paper`, `panel`, `rule`, `accent`, `accent_soft`, `done`, `partial`, `not_started`, `tbc` (each `#RRGGBB`) and `house.fonts` `heading`, `body`, `mono`. The docx, site, deck, generated pictures and the Mermaid theme all read them.
- `template.fields` (above). Style resolution is the profile's own `template.styles`, then the styles detected in the template, then the defaults.
- `org.name` and `org.short`, unset by default: the outputs name no organisation unless the profile does.
- `keep_name: true` on a system (the `layer` check lets its name through), `systems.ea_viewpoint_names` (the organisation's names for viewpoints, by key or standard EA name), `house.date_format` (`long`, `iso` or strftime; every output) and `house.captions.view_note`.

`references/interview.md` asks the questions in four batches (the document; the systems; forums and roles; the template) with an optional fifth for house style.

## 6. Outputs

### 6.1 Word document (`archdoc build docx`)

- **With a template:** fill it in place. This generalises the SAD builds:
  - clean tracked changes and comments;
  - map chapters to the template's Heading 1s, in metamodel order;
  - replace each kept section's guidance with content;
  - clone a template table whose header matches, otherwise create a new table in the template's table style;
  - remove the sections the content doesn't name;
  - keep section breaks;
  - rebuild the TOC field cache from the live headings and mark it dirty;
  - fill the document-control tables (owner, history) from arch-doc.yaml.
- **Without a template:** generate a neutral document. It has a cover, document control, TOC field, numbered headings, captions and house tables, styled from `house`.
- **Figures:** sized to the text width; portrait figures capped at the page height. Captions read "Figure n. ..." and "View n. ...".
- **Numbering:** chapters and sections are numbered sequentially after profile filtering, and every `{sec:}` resolves to the rendered number.

**As built:** the output is `out/<Title> v<version>.docx`. The template is arch-doc.yaml's `template` (relative to the project) first, then the profile's `template.path` (relative to the profile). Cover text in `template.fields` is replaced. Headings a template leaves unnumbered (an appendix) stay unnumbered, and the build warns when a `{sec:}` points at one. The TOC field's cache lists every heading with its number; Word fills in page numbers when it updates fields on open. View captions add the EA metamodel and viewpoint name, then any `view_note`. Dates follow `house.date_format`. Columns are sized to their longest unbreakable word; a table that cannot fit drops to 8pt and, in the neutral document, turns its page; one that still cannot fit is warned about. The catalogue adds shared and example columns when the model has them. The neutral document is A4. A figure's PNG comes from `diagrams.ensure_png`, which renders a stale or missing PNG, uses an older PNG when the tool is missing, and otherwise stops the build naming the figure, its citation and the tool.

### 6.2 Review site (`archdoc build site`)

One self-contained `out/site/index.html` plus `media/`, a generalisation of the SAD review sites:

- **Layout:** a left TOC, chapters with stable positional anchors (`s7`, `s7-3`, `s7-3-p2`, `s7-3-t1-r4`, `fig-4`, `view-2`, `dc`), a lightbox for figures, and an open-items panel listing every TBC with its owner and anchor.
- **Comments:**
  - When published as a claude.ai Artifact with the `comments` and `db` capabilities, the page posts anchored threads and per-section review status (`in-review` / `changes` / `agreed`), using the runtime capability API.
  - Opened as a local file, it keeps comments and status in the browser and offers an "Export comments" JSON file, which `archdoc comments import <file>` reads back.
- **Publish:** `references/outputs.md` documents the Artifact publish call and the comment read-back. The page carries no organisation name unless the profile supplies it.

**As built:** the build also writes `out/site/PUBLISH.md`, the exact publish call for that build: `file_path` `out/site/index.html`, `root` `out/site`, `files` the plain list of `media/...` and `media/full/...` paths, `capabilities` `{"comments": {}, "db": {}, "downloads": true}` and icon `document`; a redeploy omits icon and capabilities. `comments` and `db` make the artifact organisation-internal. Published with comments, the page hides the browser-only My comments panel and its export; where a hosted page keeps comments in the browser, Export comments saves through `downloads` and is hidden until that capability answers. The page is written without a document skeleton, because the publish wraps it. Panels: open items (`app-open-items`) and the reviewer's comments (`app-comments`). Review status lives in db collection `review`, one document per section anchor (`{status, section, at}`). Read-back: `ArtifactComments` `read` gives the threads, saved as a list of `{text, author, at}` for `archdoc comments import`; `ArtifactData` `list` on `review` gives the status. The export format is documented in `comments.py`. Anchors are positional, so an inserted paragraph shifts the numbers after it; import falls back to the nearest parent anchor. With `--force`, a figure with no file shows a "Not rendered" notice naming the file.

### 6.3 TL;DR deck (`archdoc build deck`)

A self-contained HTML deck in `out/deck/index.html`:

- **Format:** 1920×1080 slides, scaled to fit the viewport's width and height (letterboxed). Previous and next buttons, clicks on the slide's outer thirds, arrow keys and swipe navigate; the counter or `G` opens an overview of every slide; `P` prints to PDF one slide per page, and `N` toggles speaker notes. Fonts load from Google Fonts with system fallbacks.
- **Order:** a cover, then a divider before each of four runs ("Why and what", "The design", "Running it", "Delivering and governing"; run membership is set in the metamodel), then three slides per chapter:
  1. **Story** (`chNN-a`): the eyebrow "Chapter n", the title, the chapter's claim (one sentence), and the chapter's main content: three to six points or cards, drawn from `deck.yaml`, or from the lead-in and section first sentences when deck.yaml is silent.
  2. **Detail** (`chNN-b`): the chapter's registers as dense tables and card grids, with status chips spelled out in words ("TBC: Integration lead", "Not built"). Long registers split across columns. Above about 14 rows, the slide shows the first rows and says "n more in section x.y".
  3. **Picture** (`chNN-c`): a full-slide architecture picture. If the chapter has a figure or view whose aspect ratio is between 1.2 and 2.4, it uses that (**as built:** 0.9 to 2.6, letterboxed). Otherwise it uses the chapter's generated picture (`pictures.py`, below). Up to three callout tags come from `deck.yaml`.
- **Generated pictures** (`pictures.py`): native SVG drawn from registers, in the house palette:
  - `layers`: dependency stack from `depends_on`;
  - `timeline`: checkpoints and forums;
  - `traceability`: requirements to what satisfies them;
  - `heatmap`: risks placed by likelihood × impact;
  - `matrix`: status of acceptance and readiness items;
  - `swimlane`: support or incident flow from RACI or process records;
  - `flow`: cutover steps or data flows;
  - `bars`: catalogue counts;
  - `map`: integrations around the system.

  Every chapter in the seed names one.
- **Thin chapters:** a chapter whose content and registers are thin (metamodel `deck.min_slides: 2`, or detail below a threshold) gets story plus picture only.
- **Footer:** `<short> v<version> · <chapter n>`. Cover and dividers have none.
- **Speaker notes:** two to five sentences, from deck.yaml, or else derived (the claim plus the most important open item).
- **Publish:** `outputs.md` also explains how to publish the deck as an Artifact.

**As built:**

- `deck.yaml`: `cover: {line}`; `runs: {1..4: description}`; `chapters: {<key>: {claim, points (3-6) | cards [{title, text}] (3-6), callouts [{text, x, y}] (up to 3, fractions of the picture), notes (text, or {story, detail, picture})}}`; chapter keys may also sit at the top level. Structural errors stop `build deck` with every problem listed; a chapter key the document does not carry is a warning. Texts take placeholders and are read by `check`.
- Two-slide chapters: `deck.min_slides: 2` in the metamodel, or a detail slide with fewer than 3 rows.
- A figure with only a `.mmd` and no render uses the generated picture.
- As built after 0.1.0: detail bodies fill to the foot and the layout check judges each lane; no header-only or thin tables; callouts never cover the drawing; a generated picture draws only cited records, must show at least two statuses or three nodes, and never repeats; open items and their count come from `Project.open_items()`, the same list the site shows; dates follow `house.date_format`.
- Viewer: previous and next buttons (on hover; always on touch), a click on the left or right third of the slide (not on a link or button, not when text is selected, and a click on text waits so a double click can still select a word), arrow keys, Page Up/Down, Space, Home/End, swipe; the counter and `G` open an overview of live, scaled thumbnails (ids inside each copy renamed so SVG markers still resolve), Escape or `G` closes it; a progress bar on the slide's foot; a hint on the cover that fades; the page takes focus on load and on the first pointer move so the keys work inside an Artifact frame; none of this shows in print, `?shot=1` or `?check=1`. On a tall viewport the controls sit under the slide. `#<slide-id>` opens a slide; `?slide=<id>&shot=1` shows one slide unscaled for a screenshot; `?check=1` writes the layout check's JSON into `#deck-check`; `?check=ui` drives the navigation and writes what each step showed; `window.__deckOverflow()`, `window.__deckCallouts()` and `window.__deckUI()` expose the checks.
- The deck is published as a plain Artifact: `file_path` `out/deck/index.html`, `root` `out/deck`, `files` the `media/...` list, icon `slides`, no capabilities. It plays in the artifact viewer as it does locally.
- **Deviation:** sending the slides to a Slides Artifact type is not built. The deck HTML is the deliverable.

## 7. Checks (`archdoc check`)

Each check has an id, a severity (error or warn) and a location: file, line, and the anchor it will have.

| Id | Severity | Catches |
|---|---|---|
| `count-prose` | error | A spelled-out or numeric count in prose next to a register noun ("four points", "7 risks") that disagrees with the register, or a count introducing a table that disagrees with its rows |
| `count-prose` | warn | The same counted noun phrase for the same subject given two different numbers in two places |
| `count-model` | error | EA catalogue counts that disagree with registers. Application Component objects count against the application and component registers together, so external systems in the model must be registered as applications |
| `xref` | error | `{sec:}`, `{fig:}`, `{view:}`, `{dep:}` or any placeholder that doesn't resolve (content and deck.yaml); a literal "section n.n" that does not exist or points at a different title than the one cited; a hand-written contents list that skips or misnames a chapter |
| `xref` | warn | A topic cited "in section n.n" that belongs to another section |
| `version` | error | Literal versions of this document (`v0.1`) that differ from `arch-doc.yaml`, except in history rows and dependency references |
| `tbc-owner` | error | A TBC with no owner; TBD or TBA. A TBC in arch-doc.yaml falls to `owner.name` |
| `layer` | error | Product names, SKUs, IPs, CIDRs or resource names in a `layer: logical` document. The banned list combines `data/products.yaml` (case-sensitive; generic words only with their vendor prefix), the profile's systems that have a `logical_name`, and `banned_terms` |
| `boundary` | warn | A solution design naming a dependency's internal components, and a capability design naming its consumers' internals |
| `ids` | error | Duplicate ids, ids that don't match the type prefix, and references to unknown ids |
| `ids` | warn | View and exception sequences that cross |
| `empty` | error / warn | A metamodel section with no content, unless `optional` or the content says why; a per-record (`covers`) table missing records (error by id, warn by title) |
| `figure` | error / warn | A missing figure file; a figure never referenced; a views table that says an existing view was "not produced" (error); a figure not rendered, an unused source, a caption count that disagrees with its register (warn) |
| `figure-table` | warn | A label in a figure source (`.ead`, `.mmd`) that contradicts a register field or table, e.g. access "TBC" in the figure but "read" in the register |
| `stale-template` | error | Template guidance or placeholder text left in the content |
| `voice` | warn | Banned phrases from `data/voice.yaml`; quotes and code spans are exempt |
| `consistency` | warn | The same noun phrase approved in one place and not reviewed (or rejected) in another; a plain table citing a record with a field value its register or another table contradicts |
| `tbc-owner` | warn | A TBC whose owner slot is not an owner by the core's rule (`registers.owner_problem`): a clause, a condition or time, a state, only design-stage words, a date, or a part of more than six words; joint owners joined by with, and, &, / or a comma pass (as built). Only a TBC that marks a value counts (`registers.tbc_markers`); "every TBC" is a noun |
| `schema`, `content` | error | The core's load problems: register schema and content format; deck.yaml validated as `build deck` would (as built) |

**As built:** `consistency`, `schema` and `content` were added to the first draft's thirteen; the sub-checks above (two places disagreeing, crossing exceptions, coverage, "not produced") are folded into existing ids. `references/checks.md` describes each check, its fix, and what it cannot see.

`archdoc check --json` returns machine-readable findings. `build` runs `check` first and refuses on errors unless `--force`.

## 8. CLI

```
archdoc init [dir] --kind solution|capability [--profile path] [--template path]
                                 scaffold a project: arch-doc.yaml, content files with guidance comments, empty registers
archdoc profile [--show|--validate]
archdoc extract <template.docx> [-o metamodel.yaml]
archdoc check [--json]
archdoc build docx|site|deck|all [--force]
archdoc diagrams [--render] [--force] [--json]
                                 list figures per chapter, render stale sources (--force: all), report what's missing
archdoc numbering [--json]       print the rendered chapter/section numbering
archdoc comments import <file>   merge exported site comments into out/comments.json
archdoc status [--json] [--issues N]
                                 per chapter: sections filled, registers, figures, open TBCs, check findings
```

Global: `-C <dir>` names the project (default: the current directory). `init` also takes `--title`, `--short`, `--layer`, `--version`, `--metamodel`, `--depends-on <path>:<ref>` (repeatable), `--author`, `--owner`, `--date` and `--force` (rewrites arch-doc.yaml, adds missing files, never overwrites content or registers). Exit codes: 0 clean, 1 findings or failures, 2 the project cannot be loaded.

## 9. Diagrams

- **Detection:** arch-diagram counts as installed when the arch-diagram skill is available to the session, or when its scripts are found via `ARCH_DIAGRAM_HOME` or the plugin cache. `archdoc diagrams` reports which is in use.
- **With arch-diagram:** figure sources are its `.ead` views or `.py` scripts, rendered with its `ea.py render`. EA views use the profile's `ea_metamodel`.
- **Without it:** SKILL.md tells Claude to suggest installing it once, with the install command, and then use Mermaid. Figure sources are `.mmd`. They are rendered to SVG and PNG by `npx -y @mermaid-js/mermaid-cli@11.12.0` when Node is present. Otherwise the site renders them in the browser, the deck uses the generated picture, and the docx gets the PNG, or, if none can be produced, the build stops and names the missing tool (no placeholder figure).
- **Picture slides:** these always work, because generated pictures need neither tool.

**As built:**

- Detection order: `ARCH_DIAGRAM_HOME`; the plugin cache (`<claude dir>/plugins/cache/arch-diagram/arch-diagram/<version>`, highest version); `plugins/installed_plugins.json`; the skills directory (`<claude dir>/skills/arch-diagram`, or the project's `.claude/skills/arch-diagram`). The Claude directory is `CLAUDE_CONFIG_DIR` or `~/.claude`.
- Sources: `.mmd`; `.ead`, one file per figure, drawing the view whose id matches the figure name when the file declares several; `.py`, run with `ARCHDOC_FIGURE`, `ARCHDOC_OUT`, `ARCHDOC_PALETTE` (JSON) and, with arch-diagram, `ARCH_DIAGRAM_SCRIPTS` on `PYTHONPATH`. `.ead` files share one `diagrams/model.json` (`model "model.json"`), which `CATALOGUE` also reads.
- A `.py` no figure names is a helper when a figure script imports it or its name starts with `_` or ends with `lib`. Chrome runs through `archdoc/chrome.py` with its own temporary profile and process group, its output streamed; once Chrome reports a complete PNG the group is killed and the PNG used, whatever the exit code, and anything else raises `DiagramError` naming the cause, with no retry.
- Staleness is by modification time: a source newer than its PNG/SVG, a `model.json` newer than the views that name it, a profile newer than its Mermaid figures. `diagrams --render` renders stale figures, `--force` all, `--json` reports as JSON.
- `ensure_png` gives the docx its PNG: current file, else render, else an older PNG when only the tool is missing, else a clear error. Nothing ever writes a placeholder image.
- Layout steering for `.ead` views uses arch-diagram's view-language hints (`same`, `above`, `hide`, `width`); matrix views serve as data access matrices.

## 10. Skill procedure (SKILL.md)

1. **Find or start the project.**
   - If there is no `arch-doc.yaml`, run the interview. It covers:
     - the kind of document, its title and its version;
     - what it depends on;
     - which template to use, and whether to extract its metamodel;
     - the systems in the profile and the forums.
   - Then run `archdoc init`.
2. **Gather facts before prose.** Fill the registers from what the user gives (documents, repos, notes). Ask only for what changes the design.
3. **Draft chapters** in metamodel order, following `writing.md`. Cite registers, and keep facts out of the prose.
4. **Diagrams:** one per chapter that needs a picture, through arch-diagram or Mermaid. Look at every rendered PNG.
5. **`archdoc check`:** fix every error at its source.
6. **`archdoc build all`:** publish the site and the deck when the user wants them shared.
7. **Review loop:** read the comments back, fix at source, rebuild and republish to the same URLs.

## 11. Definition of done

- Both example projects (`northwind-platform` capability, `northwind-parcels` solution depending on it) build all three outputs with zero check errors. Each has at least one figure via Mermaid and one via arch-diagram.
- The tests cover:
  - the content parser and placeholders;
  - numbering after profile filtering;
  - each check, with a failing and a passing fixture;
  - extraction from a generated template;
  - docx in both modes (template and neutral);
  - site anchors;
  - deck slide count and order, two-slide chapters, footers, and generated pictures for every picture kind;
  - the Mermaid fallback path.
- Installed locally as a plugin, a fresh session can run the interview, scaffold, draft one chapter and build. **As built:** proven with `claude -p --plugin-dir <repo>` in a fresh scratch directory, without installing (CHANGELOG 0.1.0).
- No organisation-specific names in the repo, except the fictional Northwind examples.
