---
name: arch-doc
description: Write architecture design documents for review boards (solution architecture documents or SADs, capability and platform designs, high-level designs or HLDs, and any architecture design document) as one project of typed registers and chapter files, built into a Word document (the organisation's own template or a neutral one), a review site with anchored comments, and a TL;DR slide deck. Use when asked to write, draft, extend or rework a solution architecture document, SAD, capability design, platform design, HLD, architecture design document, or a design for the architecture review board or design authority; to turn notes, a repository or an old document into one; to extract a metamodel from an organisation's SAD template; or to read review comments back into a design.
---

# arch-doc: architecture design documents for review boards

One project builds three outputs: a Word document, a review site with
anchored comments, and a TL;DR deck with three slides per chapter. Facts live
in typed registers, the prose cites them, and `archdoc check` catches the
places where the two have drifted. The chapter structure comes from a
metamodel (the bundled `seed`, or one extracted from the organisation's
template). The organisation's systems and forums come from a profile that
you build by interview.

## Running the CLI

Every command is the same Python script run through uv. `<skill-dir>` is the
base directory shown when this skill loaded (it holds `scripts/archdoc.py`):

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py -C <project> <command>
```

- `-C <project>` goes before the command; `init` takes the directory as its
  own argument instead.
- Write the whole command each time. Shell variables do not survive between
  Bash calls, and zsh does not split a command stored in a variable:
  `AD="uv run ..."; $AD check` fails with "no such file or directory". A
  variable holding only the script path is fine.
- When `uv` is missing, ask the user to install it (https://docs.astral.sh/uv/)
  rather than installing packages another way.

Commands: `init`, `profile --show|--validate`, `extract`, `check [--json]`,
`build docx|site|deck|all [--force]`, `diagrams [--render] [--force] [--json]`,
`numbering`, `comments import <file>`, `status`. Exit code 1 means findings or
failures; 2 means the project could not be loaded.

## References

Read the reference for a step before doing it:

| Step | Reference |
|---|---|
| The interview and the profile | `references/interview.md` |
| The metamodel, extending it, extracting one from a template | `references/metamodel.md` |
| Project layout, arch-doc.yaml, registers, the content format, placeholders | `references/project.md` |
| Voice, TBC rules, and what each chapter's story, detail and picture should say | `references/writing.md` |
| Every check: what it catches, how to fix it, what it cannot see | `references/checks.md` |
| Diagrams: arch-diagram or Mermaid, figure names, rendering | `references/diagrams.md` |
| Building, publishing the site and deck, reading comments back | `references/outputs.md` |

`<skill-dir>/examples/` holds two complete projects that build cleanly:
`northwind-platform` (a capability design) and `northwind-parcels` (a solution
design that depends on it), sharing `northwind-profile.yaml`. Read a chapter of
one before drafting the same chapter, to see the format and the voice.

## Procedure

### 1. Find or start the project

Look for `arch-doc.yaml` where the user points, in the working directory and
under `docs/`. When one exists, run `status` and `check` and carry on from what
they report.

When there is none, run the interview (`references/interview.md`). Ask a few
short batches, each with its defaults, so the user can answer "yes" to most:

1. the document: kind (solution or capability), title, version, layer, owner,
   and the designs it depends on;
2. the systems: ITSM, EA repository, EA metamodel, cloud, identity, CI/CD,
   monitoring and source control;
3. the governance forums and roles;
4. whether the organisation has a design template to extract (`extract`).

Skip any question the user has already answered. Write `profile.yaml` (or
reuse a shared one), validate it with `profile --validate --file <path>`, then
run `init`. The profile decides which chapters and sections exist, so write it
before `init`. Show the user the structure with `numbering`.

### 2. Put facts into registers before prose

Fill `registers/<type>.yaml` from what the user gives you: documents,
repositories, notes, tickets. Each register file starts with a comment listing
its fields and status values. Every requirement, decision, risk, integration,
component and owner is a record with an id. Ask only for what changes the
design. A value nobody knows yet is `TBC: <owner>`, never a guess and never a
blank. Run `check` after each register: id and schema errors are cheaper to fix
before the prose cites them.

### 3. Draft the chapters

Write `content/NN-<key>.md` in metamodel order, following
`references/writing.md`, and draft the executive summary last. Each section's
scaffold comment holds the guidance; replace it with the content it asks for.
Show registers with `REGISTER <type> [where ...]`, cite records by id, and write
every count and id range as a placeholder (`{count:risk where rating=high}`,
`{ids:decision}`), never as a typed number. A thin section stays thin: one
sentence saying why it is empty passes the checks.

Then write `deck.yaml`: one claim per chapter, three to six points or cards,
up to three callouts on the picture, and short speaker notes
(`references/writing.md`, `references/outputs.md`). `check` validates it the
way `build deck` does, so a broken deck.yaml fails before anything is built.

### 4. Diagrams

Run `diagrams` first: it lists each chapter's figures and says whether
arch-diagram and Node are installed.

- **arch-diagram installed:** draw EA views as `.ead` view files over one
  `diagrams/model.json`, in the profile's EA metamodel, and other figures as
  `.ead` or `.py`. Use the arch-diagram skill's own references for the view
  language (`references/dsl.md` and the metamodel's file); when that skill is
  not loaded in this session, read them under the path `diagrams` reports.
  `references/diagrams.md` lists the viewpoint keys a `VIEW` takes.
- **arch-diagram not installed:** tell the user once, with the commands, and
  then use Mermaid (`.mmd`) without asking again:

  ```
  /plugin marketplace add warrendeanlangeveldt/arch-diagram
  /plugin install arch-diagram@arch-diagram
  ```

Cite each figure with `FIGURE <name> | <caption>` or
`VIEW <name> | <title> | <viewpoint>` and reference it in the text with
`{fig:<name>}` or `{view:<name>}`. Render with `diagrams --render`, then read
every PNG and fix what you see before going on. Chapters without a figure get
a generated picture in the deck, so not every chapter needs one.
`references/diagrams.md` has the naming rules and the tool details.

### 5. Check, and fix at the source

Run `check`. Fix every error where it starts: the register when a count or
owner is wrong, the content when a placeholder or reference is wrong, the
figure source when a label disagrees. Never weaken the prose to quiet a check,
and never type the number a check asked for: cite the placeholder.
`references/checks.md` says what each finding means. Read the warnings too;
most are real.

### 6. Build

Run `build all`. It runs the checks first and refuses on errors (`--force`
builds anyway; use it only to show a draft, and say so). It writes
`out/<Title> v<version>.docx`, `out/site/index.html` and `out/deck/index.html`.
Look at what you built: screenshot a few deck slides and the site with
headless Chrome and read the PNGs (`references/outputs.md` has the commands).

### 7. Share

When the user wants the site or the deck shared and the Artifact tool is
available, publish them as Artifacts: the site with the `comments`, `db` and
`downloads` capabilities, so reviewers can comment on any paragraph, set a
review status per section and save their comments, and the deck as a plain
page. `out/site/PUBLISH.md` holds
the exact site publish call for this build. Otherwise give the user the local
paths. `references/outputs.md` covers both.

### 8. The review loop

Read the comments back: `ArtifactComments` `read` on a published site, or the
JSON file a reviewer exported from a local copy. Import them with
`comments import <file>` so they are kept in `out/comments.json` against their
anchors. Fix each one at its source (a register, a chapter, a figure), run
`check`, rebuild, and republish to the same URL. Tell the user which comments
you resolved and which need a decision from them.

## Rules

- Registers hold the facts. Prose cites them; it never restates a count, an id
  range or an owner by hand.
- Every TBC names an owner: `TBC: Integration lead`. A bare TBC in a record
  takes the record's `owner`.
- Organisation, product and forum names come from the profile through
  `{p:...}` placeholders, or from the user's own words. Never invent them.
- A `layer: logical` document names what a thing does, not the product that
  does it. Give each profile system a `logical_name`. A name the design keeps
  on purpose goes in arch-doc.yaml `allowed_terms` (or the system's
  `keep_name: true`), never past the check by rewording.
- A solution design uses its platforms through their published interfaces and
  cites them with `{dep:...}`; it does not describe their insides.
- Never edit anything under `out/`. Change the project and rebuild.
- Write in the voice of `references/writing.md`: declarative, brief, first
  person plural, the bad news stated plainly.
