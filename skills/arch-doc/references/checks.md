# The checks

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py -C <project> check [--json]
```

Each finding is one line: `file:line: severity [id] message (#anchor)`. The
anchor is where the place appears in the site and the deck. `--json` gives
`id`, `severity`, `message`, `source`, `file`, `line` and `anchor` for each.
`check` exits 1 when any finding is an error. `build` runs the same checks
and refuses on errors unless `--force`.

Errors are defects. Warnings come from heuristics; most are real, and each
check is built to stay silent on correct text, so a warning on text that is
right is a bug in the check worth reporting rather than prose worth bending.

Fix at the source. A count is wrong in the register or in the prose, never in
the output; a placeholder replaces a typed number; a figure label is fixed in
the figure's source and the figure re-rendered.

## Summary

| Id | Severity | Catches |
|---|---|---|
| `count-prose` | error | A count in prose next to a register noun ("seven risks") that disagrees with the register; a count introducing a table ("at four points:") that disagrees with its rows |
| `count-prose` | warn | The same counted noun for the same subject given two different numbers in two places |
| `count-model` | error | EA catalogue counts that disagree with the registers |
| `xref` | error | A placeholder that does not resolve (content and deck.yaml); "section n.n" that does not exist, or whose cited title is another section's; a hand-written contents list that skips or misnames a chapter |
| `xref` | warn | "decisions in section 4.4" when 4.4 is not about decisions and another section is |
| `version` | error | A literal version of this document that is not its version |
| `tbc-owner` | error | A TBC with no owner; TBD or TBA written for TBC |
| `tbc-owner` | warn | A TBC whose owner slot names a time, condition or state ("TBC: at concept endorsement", "TBC: not measured") rather than who confirms it |
| `layer` | error | Product names, SKUs, IP addresses, CIDRs or resource names in a `layer: logical` document |
| `boundary` | warn | A dependency's internal components named in a solution design, or a consumer's in a capability design |
| `ids` | error | Duplicate ids, ids off their type's prefix, ids no register (or dependency) holds |
| `ids` | warn | View and exception numbering that cross |
| `empty` | error | A section with no content; a section with only empty register tables; a per-record table that misses records (cited by id) |
| `empty` | warn | The same per-record table, when the records are matched by title |
| `figure` | error | A missing figure file; a figure never referenced; a views table that says an existing view was not produced |
| `figure` | warn | A figure not rendered yet; a diagram source no figure uses; a caption count that disagrees with its register; a views table that says a view was produced when the document has none |
| `figure-table` | warn | A figure label that contradicts a register or a table ("read access TBC" against "read") |
| `stale-template` | error | Template guidance or placeholder text left in the content |
| `voice` | warn | Banned phrases (`scripts/archdoc/data/voice.yaml`) |
| `consistency` | warn | The same noun phrase called approved in one place and not reviewed, or rejected, in another; a plain table that cites a record and gives one of its fields a value the register, or another table, contradicts |
| `schema` | error | A metamodel artefact type that fails validation, reported once at its cause rather than again by every section, picture and column map that names it; a register that is not a list of records, a record without `id`, `title` or `status`, an unknown field, a value outside its enum, a bad date or number, a register file for a type the metamodel does not have |
| `content` | error | A chapter or section the profile, kind or `exclude` drops, or that the chapter does not have; a section written twice; an unknown or malformed directive; deck.yaml that does not parse or that the deck builder would refuse |
| `content` | warn | A deck.yaml chapter key the document does not carry |

`schema` and `content` are the core's load problems, reported as they are.
`check` also runs the deck builder's own deck.yaml validator, so a deck that
`build deck` would refuse fails `check` first and `build all` writes
nothing. Each finding carries the deck.yaml line its key is on:
`deck.yaml:100: error [content] chapters.integration: unknown key 'claimz'
(expected claim, points, cards, callouts, notes)`. deck.yaml texts are read like the prose.

Register values are read like the prose too: placeholders in them must
resolve (`xref`), a literal version must be this document's (`version`), and
a TBC inside a longer value needs an owner (a bare one falls to the record's
owner).

## count-prose

Reads numbers written as digits or as the words two to twenty, followed
within a few words by a noun: a register's key, label or title label, singular
or plural ("risks", "decision requests", "integrations").

- When the sentence claims the whole set ("We have seven decisions", "There
  are 12 risks", "The register holds four exceptions"), the number must equal
  the register's size, or the size of a filtered view the document shows, or
  match the modifier read as a filter ("three high risks" against
  `rating=high`).
- A partial count ("two integrations are file-based") only fails when it is
  larger than the whole register.
- A count that introduces a table ("Integrations fail at four points:") must
  equal the table's data rows.
- Warn: the same subject and noun counted with two numbers in two places
  ("holds four secrets" and "holds five secrets").

**Fix:** write `{count:<type> where ...}`, or correct the register.

**Does not catch:** numbers above twenty in words; counts after a label word
("section 7 risks", "phase 2 decisions"); approximate or relative counts
("about", "over", "at least", "up to", "more", "other", "remaining");
sentences that mention a dependency; units and people ("seven days",
"three users"); nouns no register names, unless they introduce a table.

## count-model

Compares a `CATALOGUE` (or a hand-written table whose first column is object
or element types and which has a count column) with the registers. An EA
object type maps to the register types its objects' `ref` ids point at, or by
name: Application Component counts against the application and component
registers together, requirements against all three requirement registers,
Data Object and Business Object against data objects.

**Fix:** add the missing records, or the missing objects to `model.json`.
External systems drawn as Application Components must be registered as
applications, or the counts disagree.

**Does not catch:** object types with no matching register; registers that
are still empty (the model may run ahead of them).

## xref

- Every placeholder in content, captions and deck.yaml must resolve; the
  message says why one does not.
- A literal "section 8.3", "chapter 8" or "§8.3" must exist. When a title
  follows it (`section 8.3 (Interface Contracts)`), it must be that section's
  title; the message names the section the title belongs to.
- "Figure 9" or "View 5" beyond the number of figures or views.
- A hand-written contents table or list of numbers and titles must match the
  numbering and not skip a chapter.
- Warn: the noun before "in section 4.4" names another section's topic.

**Fix:** use `{sec:<chapter>/<section>}`, `{fig:}`, `{view:}` and `{dep:}`
instead of numbers. `numbering` lists the keys.

**Does not catch:** sections of another document ("section 4 of the
retention standard"), and sentences that mention a dependency; a literal
figure number that points at the wrong figure but exists.

## version

Reads sentences about this document ("This document (v0.2) ...", "the draft",
"for review") for `v0.2` or `version 0.2`.

**Fix:** write `{doc:version}`.

**Does not catch:** another thing's version ("TLS v1.2", "OpenAPI version
3.1", "v2.0 of the carrier API"), which it leaves alone by design; history
tables and sections, and dependency references, which are exempt; a bare
"0.2" with no `v` or "version".

## tbc-owner

- In prose, tables, captions and deck.yaml: `TBC` must be followed by
  `: <owner>`; the owner runs to the next punctuation mark.
- `TBD` and `TBA` are not values.
- In registers: a TBC with no owner in a record with no `owner` field.
- In arch-doc.yaml: a bare TBC when the document has no `owner.name`.

- Warn: the owner slot is not an owner. An owner is a short noun phrase
  naming a role, team or person, or several joined by "with", "and", "&",
  "/" or a comma ("Platform team with the platform owner", "Security / Data
  owner"). The rule is the core's (`registers.owner_problem`, `is_owner`),
  so the site and the deck read it the same way: an open item whose slot is
  not an owner shows "No owner". A slot is flagged when it

  | Holds | Example | Flagged as |
  |---|---|---|
  | a clause marker anywhere (whether, if, is, will, depends ...) | `TBC: whether the hosting is recorded as configuration items` | a question or condition |
  | a preposition first (at, by, after, until, once, pending ...) | `TBC: at concept endorsement` | a time or condition |
  | a state first (not, proposed, measured, awaiting ...), or an -ed word before more words | `TBC: not measured`, `TBC: detailed design` | a state or topic |
  | only design-stage words (concept, design, build, cutover, UAT ...) | `TBC: concept endorsement` | a design stage |
  | a date | `TBC: Q3 2026` | a date |
  | a part of more than six words | `TBC: one long description of who might confirm this later` | a sentence |

  "Head of Parcels", "May Chen" and "the platform team and the security team
  together" pass: the six-word limit applies to each joined part, and may,
  will and can count as clause markers only in lower case, so a person named
  May or Will is an owner. "The platform owner once named" is flagged ("once"
  makes it a clause).

  Only a TBC that marks a value counts. "Every TBC has an owner", "each open
  TBC" and "a TBC" use the word as a noun, and a quoted 'TBC' mentions it;
  neither is an open value, in the checks or in any output.

**Fix:** `TBC: <role or person>`; give the record an owner; set
arch-doc.yaml's owner. Put the timing in the sentence: "Confirmed at concept
endorsement (TBC: Head of Facilities)".

**Does not catch:** "to be confirmed" written in words; an owner that is not
a real role.

## layer

Only in a `layer: logical` document. Rejects, in content, registers,
deck.yaml and figure sources:

- cloud product names from `scripts/archdoc/data/products.yaml`, matched
  case-sensitively and as written ("Key Vault", not "a key vault"); a generic
  word that is also a product is listed only with its vendor prefix ("Azure
  Functions", "AWS Lambda");
- the `name` of every profile system that has a `logical_name` and no
  `keep_name: true`, with the logical name as the suggested replacement;
- arch-doc.yaml `banned_terms`;
- IPv4 and IPv6 addresses and CIDRs, VM and plan SKUs, instance and machine
  types, ARNs, resource ids, cloud hostnames and Azure-style resource names
  (`rg-...`, `kv-...`).

Where matches overlap, the longest wins ("Microsoft Entra ID", not also
"Entra ID"), so one name gives one finding. Bare vendor names (Azure, AWS,
Google Cloud) are allowed: a logical design may say whose cloud it is about.

**Fix:** name the function ("secrets store", "identity provider") or use
`{p:systems.<x>.name}`, which renders the logical name. A name the design
keeps on purpose goes in arch-doc.yaml `allowed_terms`, or, for every
document on the profile, the system's `keep_name: true`:

```yaml
allowed_terms: [Entra ID]
```

**Does not catch:** products missing from the list (add them to
`banned_terms`), lower-case spellings, profile systems without a
`logical_name`, resource naming conventions other than the patterns above.

## boundary

- Solution design: names a dependency's internal components. Internal means a
  `component` record of the dependency whose title is not part of its
  published surface (its components' interfaces, its integrations, its
  applications and capabilities) and is at least two words or eight letters.
- Capability design: names an internal component of a consumer, found as a
  sibling project whose `depends_on` points here.

**Fix:** describe what the platform offers through its published interfaces,
and cite them with `{dep:NP:...}`.

**Does not catch:** internals described without their registered titles;
dependencies with no `path`; deck.yaml.

## ids

- Errors from loading: duplicate ids in a register, ids that do not carry the
  type's prefix.
- Any id a type accepts, by any of its prefixes and with or without a
  namespace (`RISK-20`, `NW-RSK-21`), in content, captions or register
  fields, that no register of this project or its dependencies holds.
- Warn: a table (or the exception register) that maps View n to an exception
  and View n+1 to an earlier exception: number exceptions in view order.

**Fix:** add the record, correct the id, or renumber.

**Does not catch:** ids with prefixes no type uses; ids in deck.yaml; a real
id cited for the wrong thing.

## empty

- A section with no blocks, unless the metamodel marks it `optional`. One
  sentence saying why it is empty is content.
- A section whose only blocks are register tables with no records.
- Coverage: a section the metamodel marks `covers: <type>`, or whose guidance
  says "For each <register noun>", and which answers with a plain table, must
  list every record of that type that the chapter's register sections show.
  An error when the table cites records by id, a warning when it matches them
  by title. A row such as "All other integrations" covers the rest.

**Fix:** write the section, say why it is empty, or add the missing rows.

**Does not catch:** coverage written as prose; filler.

## figure

- Error: a `FIGURE` or `VIEW` with no `diagrams/<name>.png`, `.svg`, `.mmd`,
  `.ead` or `.py`.
- Error: a figure never referenced by `{fig:<name>}`, `{view:<name>}` or its
  label.
- Warn: a source with no PNG or SVG yet (run `diagrams --render`).
- Warn: a `.mmd` or `.ead` file in `diagrams/` that no figure uses.
- Warn: a count in a caption that disagrees with its register.
- Views tables (the appendix's required views, a view register): a row that
  says "not produced" for a view the document has is an error; one that says
  "produced" for a viewpoint with no `VIEW` is a warning.

**Fix:** render or add the source, cite the figure where the text discusses
it, correct the table (or record the missing view as an exception).

## figure-table

Best effort, warn only. Reads edge labels in `.mmd` files and relationship
labels in `.ead` views, and compares them with integration and data-flow
records whose source and target match the edge's ends (an enum value such as
`pattern: api` against a label "file"; a label with TBC against a record with
nothing TBC), then with table rows naming both ends (access words such as
read, write, read-write; TBC against a settled value).

**Fix:** correct the label in the source and re-render, or correct the record.

**Does not catch:** `.py` figures, PNG or SVG with no source, node labels,
Mermaid syntax beyond flowchart and sequence edges.

## stale-template

Text left from a template: bracketed guidance ("[Write this section last.]"),
unclosed or slash fields ("[Solution / Project"), angle-bracket and
double-brace fields, lorem ipsum, TODO, FIXME and XXX, the scaffold's own
comment text, and ten consecutive words copied from the section's metamodel
guidance.

**Fix:** replace it with the content it asks for.

**Does not catch:** guidance rewritten in other words.

## voice

The marketing words, padding, self-reference ("this section", "as mentioned
above") and rhetorical reversals listed in `scripts/archdoc/data/voice.yaml`.
Text in `code` or "double quotes" is exempt, so a sentence can quote a banned
phrase; table headers are not read.

**Fix:** say it plainly (`writing.md`).

## consistency

The same noun phrase called approved, endorsed or signed off in one place and
not reviewed, not approved or rejected in another ("the network design was
approved" against "the network design has not been reviewed").
Conditional uses ("must be approved", "once approved") are ignored.

**Fix:** say which one was approved and which was not.

It also reads plain tables whose rows cite a record by id. A table is keyed
on one column of ids: its first column, a column whose header names the
type's id ("ID", "Ref", "No.", "DEP ID", "Risk ref") or one the section's
`column_map` maps to `id`. Any other column of ids is a cross-reference
("Control / Risk") and is not compared, and a section's `column_map` is
applied only to records of the registers that section draws on. A column is
matched to one of the record's fields through, in order: the section's
`column_map` and `labels` in the metamodel; the type's field names and
column labels; the same with a trailing "if ..." or a parenthesis dropped,
so "Impact if Delayed" matches the field labelled "Impact if late". The
cell must agree with the register:

```
| Dependency | Owner |
|---|---|
| DEP-03 | Facilities manager |
```

warns "DEP-03 owner is 'Facilities manager' here, but the dependency
register says 'Product owner'; cite {reg:DEP-03.owner} instead". Where the
register leaves the field empty, two tables are compared with each other.
TBC cells, `id` and `status` are not compared.

**Fix:** cite `{reg:<id>.<field>}`, or correct the register.

**Does not catch:** the same thing named with different words; columns whose
header names no field.
