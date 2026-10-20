# The project

A project is one document:

```
arch-doc.yaml          the document: identity, kind, layer, dependencies, history
profile.yaml           the organisation profile (or `profile: ../org/profile.yaml`, shared)
registers/<type>.yaml  typed records, one file per artefact type
content/NN-<key>.md    one file per chapter: prose and directives
diagrams/              figure sources (.mmd, .ead, .py), their PNG and SVG, model.json
deck.yaml              per-chapter slide text (optional; derived when absent)
metamodel.yaml         only when the project has its own metamodel
out/                   build output; never edit it
```

## arch-doc.yaml

```yaml
title: Parcel Tracking Solution
short: PTS                      # footers, the deck, the site badge
kind: solution                  # solution | capability
layer: logical-and-physical     # logical | logical-and-physical
version: "0.1"                  # quote it, so 0.10 stays 0.10
date: 2026-10-20
author: {name: Priya Nair, role: Solution Architect, team: Parcels Digital}
owner: {name: Tom Okafor, role: Head of Parcels}
metamodel: seed                 # seed, or a path relative to the project
profile: ../northwind-profile.yaml
template: null                  # a .docx to fill in place, relative to the project
depends_on:
  - {title: Northwind Platform, kind: capability, version: "0.2", path: ../northwind-platform, ref: NP}
history:
  - {date: 2026-10-20, version: "0.1", author: Priya Nair, change: First draft}
banned_terms: []                # extra terms the layer check rejects in a logical design
```

`title`, `kind` and `version` are required. A bare `TBC` anywhere here falls
to `owner.name`; with no owner it fails `tbc-owner`. Add a history row for
every version you issue; the Word document-control table is built from it.

A person (`author`, `owner`) is a name, then a role and a team. Every output
writes it as one line and leaves out a role or team the name already says,
so `{name: Solution Architect, role: Architect}` reads "Solution Architect".
`init` writes an unknown name as `TBC: <the profile's architect role>`, takes
the author's role from the profile's `roles.architect`, and leaves out an
unknown team or owner role.

### Optional keys

| Key | Does |
|---|---|
| `exclude: [<chapter>, <chapter>/<section>]` | drops chapters or sections for this document only, after the profile and kind; numbering closes up. A key the metamodel does not have is an `xref` error; content still written for an excluded section is a `content` error. |
| `allowed_terms: [<name>, ...]` | names a `layer: logical` document keeps on purpose, such as a system it consumes; the `layer` check leaves them alone. |
| `consumers: [<title>, {title, kind, version, ref, path, sections}]` | the designs built on this one. A capability design's summary picture draws it under them; sibling projects whose `depends_on` names it count too, without being listed. An entry with a `ref` can be cited (below). |
| `cites: [{title, ref, path or sections}]` | designs this one only refers to: neither a dependency nor a consumer, so they are never drawn or boundary-checked. |
| `captions: {view_note: <text>}` | a sentence added to every view caption in the Word document and on the site; placeholders resolve. Overrides the profile's `house.captions.view_note`. |
| `catalogue: {columns: [shared, examples], labels: {type, objects, shared, examples}}` | which extra columns the Word catalogue table may add when the model has the data (objects shared from another design, through `shared_with` or `inheritedFrom` on an object, and example object names; `[]` keeps only the counts), and the headers it uses. Labels take placeholders; without them the headers are "Object type", "Objects" (or "Objects in this design"), "Shared with the <design>" and "Examples". |

### Citing other designs

`{dep:<ref>}` cites an entry in `depends_on` (a design this one builds on),
`consumers` (one built on this one) or `cites` (one it only refers to),
looked up in that order. Only `depends_on` makes a design a dependency; the
`boundary` check and the layers picture see nothing else. A cited entry
needs a `ref`; to cite its sections it needs a `path` to its arch-doc
project, or a `sections` map. Quote the numbers in the map, or YAML reads
`10.10` as `10.1`:

```yaml
consumers:
  - {title: Parcel Tracking Solution, kind: solution, version: "0.1", path: ../northwind-parcels, ref: PTS}
  - Customer Portal                      # a title only: drawn, not citable
cites:
  - title: Identity Platform SAD
    ref: IDP
    sections: {"6.2": Federation, "10.10": Break-glass Access}
```

In the platform design, `{dep:PTS:integration/contracts}` becomes "the
Parcel Tracking Solution design, section 8.3 Interface Contracts", and
`{dep:IDP:6.2}` "the Identity Platform SAD, section 6.2 Federation". A title
that already ends in design, document, SAD, HLD, LLD, specification or
architecture is not given a second "design". A number the map does not list
fails `xref`, as does a target with neither a path nor a map.

`arch-doc.yaml` problems in these lists are `xref` errors:

| Message | Cause |
|---|---|
| `cites[1] needs at least a title and a ref` | a `depends_on` or `cites` entry without both (a `consumers` entry needs only a title) |
| `consumers[0] Billing: give it a ref so {dep:<ref>:n.n} can cite it` | a consumer with a `path` or `sections` but no `ref` |
| `cites PTS: the ref is also used in consumers; a ref names one design` | a ref repeated across the three lists |
| `consumers BM: sections must map section numbers to titles` | `sections` given as a list or a value |
| `consumers XR: quote the section numbers in sections (1.1) ...` | an unquoted section number |

## Registers

`registers/<type>.yaml` is a YAML list of records. `init` writes each file
with a comment listing the type's fields, their kinds and its status values;
read it before adding records.

```yaml
- id: RSK-03
  title: Carrier API rate limits throttle peak scans
  category: architecture
  likelihood: medium
  impact: high
  rating: high
  owner: Integration lead
  mitigation: Queue and back off; carrier quota uplift requested
  status: open
```

- `id` carries one of the type's prefixes (`RSK-03`) and is unique in its
  register. It may start with a namespace of upper-case segments
  (`NW-RSK-21`), so ids kept from another document need not be renumbered.
  When the metamodel gives a type several prefixes (`prefix: [RSK, RISK]`),
  any of them is accepted; the register's header comment lists them.
- `title` is a short noun phrase or statement, not a sentence with a full stop.
- `status` is one of the type's status values; each maps to a chip
  (done, partial, not started, TBC) in every output.
- Enum fields take one of their listed values. `ref:<type>` fields take an
  id, `refs:<type>` and `list` fields a YAML list.
- Any value may be `TBC` or `TBC: <owner>`. In YAML quote it
  (`evidence: 'TBC: Privacy officer'`); in content and tables write it bare
  (`TBC: Privacy officer`), without the quotes. An em or en dash works in
  place of the colon (`TBC — Privacy officer`, `TBC – Privacy officer`); a
  hyphen does not, so an id such as `TBC-01` is never read as a TBC.
  A bare TBC takes the record's `owner`; with no owner it fails `tbc-owner`.
  A TBC inside a longer value ("signing date TBC") is an open item too, with
  the same owner rule. "TBC" used as a noun ("Every TBC has an owner", "each
  open TBC") or quoted is not a value and is not an open item.
- An owner is a role, team or person, or several joined by "with", "and",
  "&", "/" or a comma: `TBC: Platform team with the platform owner`. A
  clause, a time, a state, a design stage or a date in the owner slot is not
  an owner (`checks.md`, `tbc-owner`); the outputs show such an item as
  having no owner.
- Values may use placeholders (`see {sec:integration/contracts}`). They
  resolve wherever the value is shown; the file keeps them as written.
- Tables show enum and status values labelled: `in-build` reads "In build",
  and the type's `value_labels` give the rest (`api` reads "API").
- A missing register file is an empty register.

Records in other registers, the content and figure sources may cite a record
by id. An id that no register holds (here or in a dependency) fails `ids`.

## Content files

One Markdown file per chapter, `content/NN-<chapter key>.md`. `init` writes
them with each section's guidance in a comment.

```markdown
# integration
Text before the first section is the chapter's lead-in: one or two sentences
on what the chapter establishes.

## overview
REGISTER integration where state=target

The messaging provider's interface is open until the contract is signed (INT-06, DEP-03).

## failure-handling
| Integration | Failure that matters | Detection | Recovery | Who acts |
|---|---|---|---|---|
| INT-01 Depot scans | Ingest stops | ALT-01 | Replay (RBK-01) | Support |

## Partner Onboarding [new]
A section the metamodel does not have.
```

- `# <chapter key>` starts the file. `## <section key>` (or the section's
  title) starts each section; `numbering` lists the keys.
- Paragraphs, `-` bullets and `1.` ordered items (indent to nest), and
  tables whose first row is the header. Inline `**bold**`, `*italic*`,
  `` `code` `` and `[links](url)` render in every output.
- `<!-- comments -->` are ignored and may span lines.
- `## Title [new]` adds a section after the one before it.
- A section the profile or document kind excludes is a `content` error if the
  file still has it.

### Directives

| Directive | Renders |
|---|---|
| `REGISTER <type> [where k=v ...] [cols a,b,c] [labels f="Header" ...]` | the register as a table; columns from the type unless `cols` names them. `labels` renames column headers for this table |
| `FIGURE <name> \| <caption>` | `diagrams/<name>.png` (or `.svg`), numbered "Figure n" |
| `VIEW <name> \| <view title> \| <viewpoint>` | an EA view, numbered "View n"; the viewpoint is a metamodel viewpoint key, its title, or its name in the profile's EA metamodel |
| `CATALOGUE [<model.json>]` | the EA model's object counts by type (default `diagrams/model.json`) |

A directive is a line of its own. `where` takes `field=value`,
`field!=value` and `field=a|b`, all of which must hold; values compare
without case.

A register table's column headers come from the directive's `labels`, then
the section's `labels:` or extracted `column_map` in the metamodel
(`metamodel.md`), then the type's:

```markdown
REGISTER risk where category=architecture labels id="Risk ID" title="Risk description"
```

### Placeholders

| Placeholder | Becomes |
|---|---|
| `{sec:<chapter>/<section>}` | that section's number, `8.4` |
| `{ch:<chapter>}` | the chapter's number |
| `{fig:<name>}`, `{view:<name>}` | "Figure 3", "View 4" |
| `{count:<type>[ where k=v]}` | how many records match |
| `{ids:<type>[ where k=v]}` | their ids: "RSK-01 to RSK-07", or a list |
| `{reg:<id>.<field>}` | one field of one record |
| `{dep:<ref>}`, `{dep:<ref>:<n.n or chapter/section>}` | "the Northwind Platform design", with its section number and title |
| `{p:<profile path>}` | a profile value: `{p:systems.itsm.name}`, `{p:forums.design_authority.short}`; a logical design gets `logical_name` |
| `{doc:<key>}` | an arch-doc.yaml value: `{doc:version}`, `{doc:title}` |
| `{cat:objects}`, `{cat:relationships}`, `{cat:<object type>}` | counts from the EA model the catalogue reads (the first `CATALOGUE`'s file, else `diagrams/model.json`): `{cat:Application Component}` |

Placeholders work in content, captions, register values, `deck.yaml` and
`template.fields`. A placeholder that does not resolve stays in the text as
written and fails `xref`.

Write numbers the registers know as placeholders. "We have
{count:decision} decisions" stays right when a decision is added; "we have
seven decisions" becomes a `count-prose` error. A number that is not a count
of records (a target, a duration, a volume) is written as it is.

## deck.yaml

Optional. Without it, the deck takes each chapter's claim from the first
sentence of its lead-in and a card per section from that section's first
sentence, topped up with register counts. `references/outputs.md`
has the format and `references/writing.md` what to write in it.

## Commands that read the project

| Command | Shows |
|---|---|
| `numbering [--json]` | every chapter and section with its number and key |
| `status [--json] [--issues N]` | per chapter: sections filled, registers, figures, TBCs, findings |
| `profile --show` / `--validate` | the profile with defaults filled, or its problems |
| `check [--json]` | the findings (`checks.md`) |
| `diagrams [--json]` | figures per chapter and the tools found (`diagrams.md`) |
