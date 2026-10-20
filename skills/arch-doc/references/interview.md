# The interview

The interview gives you two files before `init`: the organisation's
`profile.yaml`, and the answers `init` needs to write `arch-doc.yaml`. The
profile decides which chapters and sections the document carries and fills
their titles and guidance, so it comes first.

## How to ask

- Ask in short batches of three to six questions, in the order below. Put the
  default after each question, so "yes, defaults" answers the batch.
- Skip what the user has already told you: in their request, in a document
  they gave you, or in an existing profile.
- Look for a profile to reuse before asking batches 2 and 3. Another arch-doc
  project nearby (`../*/profile.yaml`, or a `profile:` path in its
  arch-doc.yaml) usually means the same organisation. Offer it, and pass it to
  `init --profile <path>` so both documents share it.
- Ask what changes the document. Do not ask for anything the defaults cover
  well enough to start; the user can change the profile later.

## Batch 1: the document

| Question | Default | Where it goes |
|---|---|---|
| Is this a solution design (one solution on platforms) or a capability design (a platform others build on)? | solution | `init --kind` |
| What is it called, and its short name for footers? | short name: the title's initials | `init --title`, `--short` |
| Which version? | 0.1 | `init --version` |
| Logical only, or logical and physical? A logical design names no products, SKUs, addresses or resource names. | capability: logical; solution: logical-and-physical | `init --layer` |
| Who owns it (approves its content), and who writes it? | author: you, owner: TBC | `init --owner`, `--author` (both become `{name: ...}`; set `role` and `team` in arch-doc.yaml) |
| Which designs does it depend on? | none | `init --depends-on <path>:<REF>` for each one that is an arch-doc project; others by hand (below) |

`--author` and `--owner` set names. `init` takes the author's role from the
profile's `roles.architect`, writes an unknown name as
`TBC: <roles.architect>`, and leaves out a team or owner role it does not
know. When the user gives a role rather than a name ("written by me as
Solution Architect"), put the role in `role` and keep `name` for a person or
a TBC. The outputs leave out a role the name already says, so
`{name: Solution Architect, role: Architect}` still reads "Solution
Architect".

Ask for the owner even when the user says "TBC": a bare TBC in arch-doc.yaml
falls to `owner.name`, so a document with no owner fails `tbc-owner`.

A dependency that is an arch-doc project gets `path` and `ref`, so
`{dep:NP:7.3}` resolves to its section number and title and the `boundary`
check can read its registers. One that is not gets a hand-written entry with
no path; `{dep:NP}` then names it, and nothing can look inside it:

```yaml
depends_on:
  - {title: Northwind Platform, kind: capability, version: "0.2", path: ../northwind-platform, ref: NP}
  - {title: Identity Platform, kind: capability, version: "3.1", ref: IDP}
```

## Batch 2: the systems

| Question | Profile key | Default | What changes |
|---|---|---|---|
| Which service management tool (ITSM)? ServiceNow, Jira Service Management, BMC Helix, other, none | `systems.itsm.name` | none | With a name: the configuration-record, model-mapping, event-mapping and request sections exist, titled from the profile. ServiceNow and Jira Service Management get their own guidance text. |
| Does it follow ITIL? | `systems.itsm.framework` (`itil`, `none`, `other`) | none | `itil` gives the ITIL practice readiness section; otherwise the generic process readiness section. |
| Does it hold configuration records (a CMDB, Jira Assets)? What is that called? | `systems.itsm.has_cmdb`, `cmdb_title` | false; "\<ITSM\> Configuration Records" | `has_cmdb: true` adds the service-records section, titled with `cmdb_title`, and event-to-record mapping. |
| Is there an EA repository? OrbusInfinity, LeanIX, Ardoq, Sparx, BiZZdesign, none | `systems.ea_repository.name` | none | Adds the repository and repository-source sections in chapter 2 and the repository views in the appendix. |
| Which EA metamodel are views drawn in? CoreEA, ArchiMate, TOGAF, Essential, none | `systems.ea_metamodel` (`coreea`, `archimate`, `togaf`, `essential`, `none`) | none | Adds an Architecture Views section to most chapters, the view register, view exceptions and view acceptance, and the object guide (a `CATALOGUE`). View captions carry the viewpoint's name in that metamodel. arch-diagram draws in its notation. |
| Which cloud? Azure, AWS, GCP, on-premises (a list) | `systems.cloud` (`azure`, `aws`, `gcp`, `on-prem`) | `[]` | The icon pack arch-diagram uses. |
| Identity provider? | `systems.identity.name` | none | Fills `{p:systems.identity.name}` in guidance and prose. |
| CI/CD? | `systems.cicd.name` | none | As above, in the deployment guidance. |
| Monitoring? | `systems.monitoring.name` | none | As above. |
| Source control? | `systems.source_control.name` | none | As above. |

When any document on this profile is `layer: logical` (every capability
design is, by default), give each named system a `logical_name`. A logical
document's `{p:systems.identity.name}` then renders "identity provider", and
the `layer` check rejects the product name if it appears anyway. Any other
text field of a system can carry its own logical variant the same way:
`cmdb_title` gives way to `logical_cmdb_title`.

When a logical design consumes a system rather than designing it, and must
name it, give the system `keep_name: true`. The `layer` check then lets its
`name` through in every document on the profile; `{p:...}` still renders the
`logical_name`. For one document only, use arch-doc.yaml `allowed_terms`
(`project.md`).

```yaml
  identity: {name: Entra ID, logical_name: identity provider, keep_name: true}
```

When the organisation calls a standard viewpoint something else, map it in
`systems.ea_viewpoint_names`, by viewpoint key or by its standard EA name.
Every caption and views table then uses the organisation's name:

```yaml
systems:
  ea_metamodel: archimate
  ea_viewpoint_names: {integration-flows: Integration Map, Layered: Layered Overview}
```

## Batch 3: forums and roles

| Question | Profile key | Default |
|---|---|---|
| Which forum approves designs? | `forums.design_authority` | Architecture Review Board, ARB |
| Which approves changes? | `forums.change` | Change Advisory Board, CAB |
| Which reviews security? | `forums.security` | Security Review, SR |
| Any others this design must pass (privacy, data, steering)? | `forums.<key>` | none |
| What are the architect and service owner roles called? | `roles.architect`, `roles.service_owner` | Solution Architect, Service Owner |

Every forum needs a `name` and a `short`. Content names them through
`{p:forums.design_authority.name}` and `{p:forums.design_authority.short}`.
The forums this design goes through are also records in the `forum`
register, with their dates and outcomes.

## Batch 4: the template

Ask whether the organisation has a Word template for this kind of design.

- **Yes:** extract it before `init` (`references/metamodel.md`, "Extracting a
  metamodel"). Go through the chapters it marks `unmatched: true` with the
  user, merge the profile fragment it writes into `profile.yaml`, and pass
  `init --metamodel metamodel.yaml --template <template.docx>`. The Word build
  then fills that template in place.
- **No:** use the `seed` metamodel and the neutral A4 document.

## Batch 5: house style (offer, don't press)

| Key | Default | Used by |
|---|---|---|
| `org.name`, `org.short` | unset | the site's title block, the deck cover, the Word cover. Unset, the outputs name no organisation. |
| `house.palette`: `ink`, `muted`, `paper`, `panel`, `rule`, `accent`, `accent_soft`, `done`, `partial`, `not_started`, `tbc` | a neutral grey and slate-blue set | the Word tables and chips, the site, the deck, the generated pictures and the Mermaid theme. Each is `#RRGGBB`. |
| `house.fonts`: `heading`, `body`, `mono` | Source Serif 4, IBM Plex Sans, IBM Plex Mono | the site and deck load them from Google Fonts with system fallbacks; the Word build names them. |
| `house.date_format` | `long` ("20 October 2026") | every date the outputs print (the Word document, the site and the deck): `long`, `iso`, or a strftime pattern such as `"%d/%m/%Y"`. |
| `house.captions.view_note` | unset | a sentence after every view caption in the Word document and on the site, such as `"Source: the {doc:short} model"`; arch-doc.yaml `captions.view_note` overrides it. |

## Writing the profile

An example, for "Jira Service Management with Assets, ITIL, no EA repository,
ArchiMate, AWS, Okta, GitLab CI, Grafana, GitLab":

```yaml
org: {name: Fabrikam, short: FB}
systems:
  itsm:
    name: Jira Service Management
    framework: itil
    has_cmdb: true
    cmdb_title: Jira Assets
    logical_name: service management platform
    logical_cmdb_title: configuration database
  ea_repository: {name: none}
  ea_metamodel: archimate
  cloud: [aws]
  identity: {name: Okta, logical_name: identity provider}
  cicd: {name: GitLab CI, logical_name: delivery pipeline}
  monitoring: {name: Grafana, logical_name: monitoring platform}
  source_control: {name: GitLab}
forums:
  design_authority: {name: Architecture Review Board, short: ARB}
  change: {name: Change Advisory Board, short: CAB}
  security: {name: Security Review, short: SR}
roles: {architect: Solution Architect, service_owner: Service Owner}
```

Anything left out takes its default. Then:

```bash
# validate it on its own, before there is a project
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py profile --validate --file <dir>/profile.yaml

# scaffold the project; init keeps a profile.yaml already in <dir>
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py init <dir> --kind solution \
  --title "Room Booking Service" --owner "Head of Facilities" --author "Solution Architect"

# or share a profile kept elsewhere
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py init <dir> --kind solution --profile ../org/profile.yaml
```

`init` writes `arch-doc.yaml`, one content file per chapter with each
section's guidance as a comment, an empty register for every type the
chapters use, and `diagrams/`. Without `--profile` and with no `profile.yaml`
in the directory, it writes a profile of defaults.

## Changing the profile later

A changed profile can add or drop chapters and sections. Run
`profile --validate`, then `init <dir> --kind <kind> --force`: it adds the
content and register files that are missing and never overwrites content or
registers. It does rewrite arch-doc.yaml from the flags you give, so copy the
file aside first and put back its history, dependencies without a path and
anything else you wrote by hand. A section the profile now drops but the
content still has is reported by `check` as a `content` error naming it;
move or delete that text. A section the profile adds to an existing chapter
file needs its `## <key>` heading written by hand; `numbering` lists the keys.
