<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/warrendeanlangeveldt/arch-doc/main/assets/logo-dark.png">
    <img src="https://raw.githubusercontent.com/warrendeanlangeveldt/arch-doc/main/assets/logo.png" alt="ArchDoc" width="300">
  </picture>
</p>

# arch-doc

A Claude Code plugin that writes architecture design documents for review boards. It covers solution architecture documents (SADs), which describe one solution on the platforms it uses, and capability designs, which describe a platform others build on. From one project it builds three things: a Word document, a review site with anchored comments, and a TL;DR slide deck.

The facts live in typed registers: requirements, decisions, risks, integrations, components and their owners. The prose cites those registers rather than retyping them. A checker catches the places where the two drift: a count typed by hand that the register no longer agrees with, a section number that moved, a TBC with no owner, a product name in a logical design.

Nothing in arch-doc is tied to one organisation. The chapter structure comes from a metamodel. Your systems and governance forums come from a profile that Claude builds by asking you a few questions. Your organisation's own words carry through: its template's column headers, its names for EA viewpoints, its date format, its id prefixes.

**Pairs with [arch-diagram](https://github.com/warrendeanlangeveldt/arch-diagram).** arch-diagram draws the pictures: house-style SVG, C4, and EA views in CoreEA, ArchiMate, TOGAF and Essential, all from one validated model. arch-doc writes the document those pictures go in, and checks the model's counts against the registers. Without arch-diagram, figures are drawn in Mermaid.

<p align="center">
  <img src="https://raw.githubusercontent.com/warrendeanlangeveldt/arch-doc/main/assets/workflow.svg" alt="How arch-doc works: your template, an interview and the registers and chapters feed archdoc check, which gates the build of a Word document, a review site and a TL;DR deck; review comments come back into the project by anchor." width="820">
</p>

## Quick start

You need Claude Code and [uv](https://docs.astral.sh/uv/). In Claude Code:

```text
/plugin marketplace add warrendeanlangeveldt/arch-doc
/plugin install arch-doc@arch-doc
```

Then ask in plain words. For example:
- "write a solution architecture document for the booking service"
- "draft a capability design for our integration platform"
- "turn these notes into a SAD"
- "extract the metamodel from our SAD template"
- "read the review comments back into the design"

Claude asks a few short batches of questions. They cover the kind of document and what it depends on, and your ITSM, EA repository, cloud, identity, CI/CD and monitoring. They also cover your governance forums, and whether you have a template. From the answers it scaffolds the project, fills the registers, drafts the chapters, draws the figures, runs the checks and builds.

## Why

A design document for a review board is long, cross-referenced and edited by many hands over months. The same facts appear in five places, and they drift:
- the executive summary says eight integrations and the integration chapter now lists eleven;
- a risk is closed in the risk register and still open in the chapter that cites it;
- a section is renumbered, and every "see 7.3" in the document points at the wrong place;
- a TBC sits in a table with no owner, so nobody ever closes it;
- a logical design names the cloud product it was supposed to stay above;
- the slide deck for the board was made by hand from an older draft and no longer matches.

arch-doc keeps each fact in one register and makes every other mention of it a reference. `archdoc check` refuses the build until counts, references, owners and layer terms agree. The three outputs are built from the same project, so they can't disagree with each other.

## What it builds

**The Word document.** The organisation's own template filled in place:
- chapters are matched to its headings, and its guidance is replaced;
- its tables are cloned and filled, and its header wording is kept;
- document control is filled and the table of contents rebuilt.

Without a template, it builds a neutral A4 document with a cover, document control, numbered headings, captions and house-styled tables.

**The review site.** One page with a contents list, where every paragraph, list item, table row and figure is anchored. An open-items panel lists each TBC with its owner, and every section carries a review status. Published as a claude.ai Artifact, it lets reviewers comment on any paragraph and share each section's status. `comments import` reads their comments back into the project by anchor. Opened as a local file, it keeps comments in the browser and exports them as JSON.

<p align="center">
  <img src="https://raw.githubusercontent.com/warrendeanlangeveldt/arch-doc/main/docs/review-site.png" alt="The review site for the example solution design: contents, open items, review status and anchored tables" width="820">
</p>

**The TL;DR deck.** Three slides per chapter, so someone who reads only the deck still comes away with the design:
- the chapter's claim and its main points;
- the registers as dense tables, with each status written out in words;
- a full-slide picture. That is the chapter's own figure or EA view where it has one. Otherwise it's drawn from the registers: a risk heat map, a cutover timeline, a traceability chain or a status matrix.

It plays in a browser or the Artifact viewer. Navigate with the buttons, clicks on the slide's outer thirds, the arrow keys or a swipe; press `G` for an overview of every slide.

<p align="center">
  <img src="https://raw.githubusercontent.com/warrendeanlangeveldt/arch-doc/main/docs/deck-picture-slide.png" alt="A picture slide: business requirements traced through functional requirements to the components that satisfy them" width="820">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/warrendeanlangeveldt/arch-doc/main/docs/deck-detail-slide.png" alt="A detail slide: dependencies and architecture risks as tables, with status in words and the other sections counted" width="820">
</p>

## What the checks catch

`archdoc check` reports each finding with its file, line and the anchor that place has in the outputs:
- **Counts.** A number in the prose is checked against the register it counts.
- **References.** Every section, record and figure reference must point at something that exists.
- **Tables against registers.** A plain table that contradicts a register is flagged, even when it uses the template's own column headers.
- **TBC owners.** Every TBC needs an owner, and the owner must be a role, team or person. A clause like "whether …" or a date like "at concept endorsement" doesn't count.
- **Layer terms.** A logical design may not name the products below it, unless you allow a name on purpose.
- **EA model counts.** The architecture model must agree with the registers.
- **The deck.** Every slide must fill its space without overflowing. It must have no empty tables and no callout covering a drawing, and its pictures must actually say something.

## Requirements

- [uv](https://docs.astral.sh/uv/), which runs the scripts on Python 3.10 or later with `pyyaml`, `python-docx` and `pillow`.
- Optional: Node.js, so `npx` can render Mermaid figures with `@mermaid-js/mermaid-cli@11.12.0` (pinned).
- Optional: Google Chrome or Chromium. It rasterises static SVG figures for Word and is used to check the site and deck. On macOS the standard install is found; elsewhere put `google-chrome` or `chromium` on the PATH, or set `CHROME_PATH`.
- Optional: the [arch-diagram](https://github.com/warrendeanlangeveldt/arch-diagram) plugin, for EA views.

## The CLI

Claude runs these for you; they also work on their own. From the repository root:

```bash
A=skills/arch-doc/scripts/archdoc.py
uv run --with pyyaml --with python-docx --with pillow python $A init my-design --kind solution --title "Room Booking Service" --owner "Head of Facilities"
uv run --with pyyaml --with python-docx --with pillow python $A -C my-design check
uv run --with pyyaml --with python-docx --with pillow python $A -C my-design build all
```

A fresh scaffold fails `check` until its sections are written. That failure list is your to-do list.

| Command | What it does |
|---|---|
| `init <dir> --kind solution\|capability` | Scaffolds `arch-doc.yaml`, a profile, one content file per chapter with its guidance, an empty register per artefact type, and `diagrams/` |
| `profile --show\|--validate` | Shows the profile with its defaults, or lists its problems |
| `extract <template.docx> -o metamodel.yaml --profile-out fragment.yaml` | Builds a metamodel and a profile fragment from the organisation's own template |
| `check [--json]` | Runs every check |
| `build docx\|site\|deck\|all [--force]` | Builds the outputs, after the checks pass |
| `diagrams [--render] [--force] [--json]` | Lists the figures per chapter and the tools found, and renders them |
| `numbering`, `status` | Prints the numbered structure; shows, per chapter, what is filled, open and failing |
| `comments import <file>` | Reads review comments back into `out/comments.json`, by anchor |

## Examples

`skills/arch-doc/examples/` holds two complete designs for a fictional organisation, Northwind. They share one profile, `northwind-profile.yaml`:
- **`northwind-platform`:** a logical capability design for an integration platform, version 0.2.
- **`northwind-parcels`:** a logical and physical solution design for parcel tracking. It runs on the platform and cites it only through its published interfaces.

Both build all three outputs with no check findings. Their figures are drawn in Mermaid, and their EA views with arch-diagram from one ArchiMate model.

```bash
uv run --with pyyaml --with python-docx --with pillow python skills/arch-doc/scripts/archdoc.py -C skills/arch-doc/examples/northwind-parcels build all
```

## How it is organised

- **`skills/arch-doc/SKILL.md`:** what Claude does, step by step. The detail for each step is in `references/`.
- **`skills/arch-doc/metamodels/seed.yaml`:** the default metamodel, with 22 chapters, 30 artefact types and 15 viewpoints.
- **`skills/arch-doc/scripts/`:** the CLI and the `archdoc` package.
- **`docs/SPEC.md`:** the specification.

## Tests

```bash
uv run --with pytest --with pyyaml --with python-docx --with pillow pytest
```

To keep your own organisation's names out of a fork, list them one per line in `tests/local-banned.txt`. The file is gitignored, so the names are never committed, and a test fails if any tracked file contains one.

## Licence

MIT. See `LICENSE`.
