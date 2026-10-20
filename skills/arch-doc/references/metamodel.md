# The metamodel

The metamodel is the document's structure: its chapters and sections, the
registers each section draws on, the artefact types those registers hold, the
viewpoints views are drawn from, and the deck's four runs. arch-doc.yaml names
it with `metamodel:`: `seed` for the bundled default
(`<skill-dir>/metamodels/seed.yaml`), or a path relative to the project.

The seed has 22 chapters, 30 artefact types and 15 viewpoints. It names no
organisation, product or forum: anything that depends on the organisation is
a `{p:...}` profile value, or a section included only when the profile says so.

## Chapters

```yaml
chapters:
  - key: integration                  # lower-case, hyphenated; the content file is NN-integration.md
    title: Integration & API Architecture
    question: How does it talk to everything else?
    story: every integration, its contract and what happens when it fails
    picture: {kind: map, from: integration}
    deck: {run: 2}                    # run 1-4; min_slides: 2 drops the detail slide
    viewpoints: [integration-flows]
    when: systems.itsm                # optional: include only when the profile holds
    sections: [...]
```

- `question` and `story` guide the writing and the deck's story slide
  (`writing.md`).
- `picture` is the generated picture for the deck's picture slide when the
  chapter has no figure it can use. `kind` is one of `layers`, `timeline`,
  `traceability`, `heatmap`, `matrix`, `swimlane`, `flow`, `bars`, `map`.
  `from` is a register type, `depends_on` or `registers`; `by` is the field
  that groups it. `fallback` (a kind, a list of kinds, or picture mappings)
  names what to draw when that register is empty, and a list-valued `by`
  does the same. When everything is empty the deck draws `layers` from
  `depends_on`, which always has the design itself.
- `deck.run` places the chapter in one of the four runs; `deck.min_slides: 2`
  gives it a story slide and a picture slide only.

## Sections

```yaml
    sections:
      - key: failure-handling
        title: Integration Failure Handling
        guidance: >-
          For each integration, name the failure that matters, its business
          impact, how we detect it, how we recover and who acts.
        covers: integration           # optional: answered per record of this type
        artefacts: []                 # register selectors, [] for none
      - key: overview
        title: Integration Overview
        guidance: ...
        artefacts: ["integration where state=target"]
      - key: service-records
        title: "{p:systems.itsm.cmdb_title}"
        when: systems.itsm.has_cmdb
        guidance_on: systems.itsm.name
        guidance: generic text
        guidance_by:
          servicenow: text for ServiceNow
          jira-service-management: text for Jira Service Management
        optional: true                # optional: may be left empty
        artefacts: []
```

- `artefacts`: register selectors, `"<type>"` or `"<type> where field=value"`.
  `init` creates a register for every type a kept section names, the deck's
  detail slide shows them, and the scaffold comment suggests the
  `REGISTER` line.
- `when`: `systems.itsm` (set and not "none"); `{systems.itsm.framework: itil}`
  (equals, or one of a list); `{not: ...}`, `{all: [...]}`, `{any: [...]}`.
- `guidance_by` picks a variant by the slug of the named system
  (`Jira Service Management` becomes `jira-service-management`).
  `guidance_on` says which profile value to read; without it, any named
  system's slug can match.
- `optional: true` exempts the section from the `empty` check.
- `covers: <type>` says the section answers per record of a register it does
  not show. When it answers with a table, the `empty` check wants every
  record of that type the chapter shows to appear in it. Without `covers`,
  guidance that starts "For each <register noun>" has the same effect.
- `labels: {<field>: <header>}` renames a register's column headers in this
  section's tables, and `column_map: {<header>: <field>}` does the same from
  the other side (`extract` writes it). `labels` wins where both name a
  field; a `REGISTER ... labels` clause wins over both. `template_columns`
  records the template's own table headers, as `extract` read them.

  ```yaml
      - key: architecture-risks
        title: Architecture Risks
        column_map: {"Risk ID": id, "Risk description": title}
        labels: {mitigation: Treatment}
        artefacts: ["risk where category=architecture"]
  ```

  The table reads "Risk ID, Risk description, Likelihood, Impact, Rating,
  Treatment, Owner, Status".
- Titles and guidance may use `{p:...}`; guidance may also use any content
  placeholder, which the scaffold comment carries as written.

## Artefact types

```yaml
artefact_types:
  integration:
    label: Integration
    prefix: INT                       # ids are INT-01, INT-02 ...
    fields:
      source: text
      pattern: [api, event, file, etl, message, manual]   # an enum
      criticality: [high, medium, low]
      owner: text
      satisfied_by: list
      traces_to: refs:business-requirement                # ids of another type
      forum: ref:forum
      date: date
    labels: {title: Integration, trigger: Frequency or trigger}   # column headings
    columns: [id, title, source, target, data, pattern, trigger, criticality, status]
    status: {planned: not-started, in-build: partial, tested: partial, live: done, retired: done}
```

`id`, `title` and `status` are always present and are not declared. Field
kinds: an enum list, `text`, `date`, `number`, `list`, `ref:<type>`,
`refs:<type>`. `status` maps each status value to one of the four chips the
outputs show: `done`, `partial`, `not-started`, `tbc`. Prefixes must be unique.

Optional keys on a type:

- `prefix: [RSK, RISK]`: a list accepts any of them; the first is the one
  `init` suggests. A prefix may have segments (`SEC-RISK`). Any id may also
  start with an upper-case namespace (`NW-RSK-21`).
- `value_labels: {api: API, etl: ETL}`: how tables show an enum or status
  value. Without one, `in-build` reads "In build". A key that is not one of
  the type's enum or status values is a metamodel error. The seed sets it on
  `application` and `integration`. `extract` copies only labels for values the target's fields
  still enumerate, so an extracted metamodel never labels a text field.
- `plural: <text>`: the label's plural where outputs count records (the
  deck's pictures and story slides). Without it, the label takes an s.
- `aliases: {<field>: [<header words>]}`: other words an organisation's
  template uses for a field's column. `extract` reads them when it maps
  template headers to fields (`column_map`); nothing else does. The seed
  gives the common ones:

  ```yaml
    risk:
      aliases: {rating: [inherent risk], mitigation: [control]}
  ```

  so a template table headed "Risk ID, Risk, Inherent Risk, Control, Owner"
  maps to `id, title, rating, mitigation, owner`; without the aliases,
  "Inherent Risk" and "Control" stay unmapped.

## Viewpoints

```yaml
viewpoints:
  integration-flows:
    title: Integration Flows
    purpose: ...
    ea: {coreea: Application Integration Diagram, archimate: Application Cooperation,
         togaf: Application Communication, essential: Application Information Dependency}
```

A `VIEW` directive names a viewpoint by key, by title, or by its name in the
profile's EA metamodel. Captions and the views tables add that EA name.

## Document kinds and runs

```yaml
document_kinds:
  capability: {purpose: a platform or zone other designs build on, excludes: [application/channels, data/migration]}
  solution: {purpose: one solution, on the platforms it depends on}
deck:
  runs: {1: Why and what, 2: The design, 3: Running it, 4: Delivering and governing}
```

`excludes` lists chapter keys or `chapter/section` keys a kind leaves out.

## Extending the metamodel

- **One extra section in one document:** write `## Title [new]` in the
  chapter file. It is numbered after the section before it, has no guidance
  and no registers, and every check treats it like any other section.
- **A change for every document:** copy `seed.yaml` into the project (or next
  to a shared profile), change it, and set `metamodel: metamodel.yaml`. Keep
  every chapter's `picture` and `deck.run`, and give new sections guidance and
  `artefacts`. `numbering` and `check` load it and report every structural
  problem at once.

## Extracting a metamodel from a template

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py \
  extract <template.docx> -o <dir>/metamodel.yaml --profile-out <dir>/profile-template.yaml
```

`--seed <name or path>` matches against another metamodel instead of the seed.
Without `--profile-out`, the profile fragment is printed.

What it reads:

- chapters from outline-level-1 paragraphs and sections from level 2,
  whatever the styles are called (the level is followed through `basedOn`);
- each chapter matched to the closest seed chapter by title and section
  overlap. A matched chapter takes the seed's key, question, story, picture,
  deck run, viewpoints and `when`, and keeps the template's own title; its
  sections are matched the same way and take the seed section's key,
  guidance, artefacts and `when`;
- every table header in a section, kept as `template_columns`.

What it writes into the metamodel:

- `extracted_from`: the template's file name;
- `unmatched: true` on chapters and sections with no seed counterpart, with
  the template's own guidance text and empty `question` and `story`. Fill
  them in with the user: what the chapter is for, its picture kind, its run,
  and the registers its sections draw on. Delete those the user does not want;
  the Word build removes template chapters the document does not carry;
- `column_map` from each template table header to a field of the section's
  registers. Each header is read as written and as its slash, "or" and
  parenthesis alternatives, with trailing `?`, `:` and `*` ignored, against
  each field's name, its label (and that label's "or" alternatives), the
  type's label for the title, and the type's `aliases` (under Artefact types). A header ending in
  "ID" or "Ref" is the id and "MoSCoW" is `priority`; otherwise an exact
  match beats a header that contains the field's words, which beats one the
  field's name contains, which beats a shared word of six letters or more,
  which beats a near spelling. Pairs are assigned best first, one field per
  header, and the first text column becomes the title when nothing claimed
  it or it matched only an enum. The Word build then heads the
  register's columns with the template's own words. On an unmatched section
  whose header reads like an artefact type's columns, that type is proposed
  as the section's register. Check both before relying on them.

The metamodel always loads (`extract` loads it before it returns).

The profile fragment:

```yaml
template:
  path: /path/to/template.docx
  styles: {h1: Org Chapter, h2: Org Section, body: Org Body, bullet: Org Bullet,
           table: Org Table, caption: caption, toc1: toc 1, toc2: toc 2}
  fields:                              # cover and front-matter text to replace
    Document Title Goes Here: "{doc:title}"
    V0.0: "V{doc:version}"
```

Merge it into `profile.yaml`. `styles` are the template's styles detected by
use for each role (`h1`, `h2`, `body`, `bullet`, `table`, `caption`, `toc1`,
`toc2`); styles you set by hand win over detected ones, and detected ones over
the defaults. `fields` maps text found on the cover to its replacement, which
may use placeholders. A field `extract` found but could not guess is `null`,
and the build leaves that text as it is: give it a replacement, or delete it.

The template to fill is arch-doc.yaml's `template:` (relative to the project)
when it is set, else the profile's `template.path` (relative to the profile).
Headings the template leaves unnumbered (an appendix, say) stay unnumbered in
the build, and the build warns when a `{sec:}` points at one, because the
number it renders appears nowhere on the page.
