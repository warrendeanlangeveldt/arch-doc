# Writing

A review board reads a design to decide something. Write so that a reviewer
finds the decision, the evidence and the open items fast, and can trust every
number.

## Voice

- **Declarative and brief.** Say what the design does: "Scans wait on the
  platform for seven days when ingest is down." Not what it aims, seeks or
  is designed to do.
- **First person plural.** "We poll carrier B because it has no webhooks."
  The design team owns the choices; the document does not talk about itself
  ("this section describes ...").
- **Say the bad thing plainly.** "The restore runbook does not exist, so the
  recovery objective is a design figure." An open problem stated once, with
  an owner, earns more trust than a hedge.
- **No marketing words, no padding.** No "seamless", "robust", "leverage",
  "best-in-class", "it is worth noting", "at the end of the day". The `voice`
  check lists them (`scripts/archdoc/data/voice.yaml`); quoted text and code
  are exempt.
- **No rhetorical reversals.** Not "it's not X, it's Y", "not just X but Y",
  "less about X and more about Y". State Y.
- **A thin chapter stays thin.** When a section has nothing to say for this
  design, one sentence says why: "No data is migrated; the legacy lookup
  stays read-only until it is archived (ADR-07)." Do not pad it.
- **Organisation names from the profile.** Systems and forums through
  `{p:...}`; dependencies through `{dep:...}`.

## Facts and citations

- Registers hold the facts. A section shows its register with `REGISTER`, and
  the prose around it says what the rows mean together, what is unusual,
  what is open. It does not repeat the rows.
- Cite records by id in brackets where the reader may want the detail:
  "requiring the postcode treats it (ADR-04)".
- Every count of records and every id range is a placeholder:
  `{count:risk where rating=high|extreme}`, `{ids:exception}`. Counts that
  are not records ("seven days", "99.9%", "three times peak") are written as
  they are.
- Cross-references are placeholders: `{sec:integration/contracts}`,
  `{fig:scan-journey}`, `{view:pts-integration}`, `{dep:NP:integration/contracts}`.
  Never type "section 8.3".
- Versions are `{doc:version}` when they are this document's.

## TBC

- A value nobody knows yet is `TBC: <owner>`: the person or role who will
  confirm it. "Retention for notification records is TBC: Privacy officer." A house
  style that writes "TBC — Privacy officer" (em or en dash) reads the same;
  a hyphen does not.
- In a register, a bare `TBC` takes the record's `owner`. Use the explicit
  form whenever someone other than the owner confirms it.
- The owner slot names who confirms it, not when: not "TBC: at concept
  endorsement" but "confirmed at concept endorsement (TBC: Head of
  Facilities)".
- Never write TBD, TBA, "to be confirmed" with no owner, or a guess dressed
  as a fact. Every TBC appears in the site's open-items panel with its owner, one item per record or place in the prose.

## The executive summary

Draft it last. It answers the chapter's question: what is being approved, and
why now. In order: the decision sought and who makes it; what the design is,
in two or three sentences; what it depends on and the date that matters; the
risks rated high or worse, by count and id; what is still open. Cite counts
and ids; the reader checks them against chapter 19.

## Story, detail and picture

The deck gives every chapter three slides, and the document should support
all three:

- **Story** (`chNN-a`): the chapter's claim in one sentence, and three to six
  points or cards. This is what a board member remembers.
- **Detail** (`chNN-b`): the registers the chapter shows, as dense tables.
  Built for you from the registers; it is only as good as they are.
- **Picture** (`chNN-c`): the chapter's figure or view when its aspect ratio
  is between 0.9 and 2.6, or else its generated picture, with up to three
  callouts that point at what matters.

Chapters marked `min_slides: 2` (runbooks, lifecycle, appendix), or whose
registers give fewer than three detail rows, get story and picture only.

| Ch | Key | The claim answers | Points or cards | The detail shows | The picture (generated when no figure) |
|---|---|---|---|---|---|
| 1 | `summary` | What is being approved, and why now? | the decision, the worst risks by count, the open dependency, the date that decides | decision requests | the design over what it depends on (`layers`) |
| 2 | `context` | Where does this sit, and what does it inherit? | in, out, not here (cards) | parent requirements and constraints | integrations around the system (`map`) |
| 3 | `governance` | Who decides, and when? | the forums in order, the dates, the missing role | stakeholders, forums, checkpoints | checkpoints on a timeline |
| 4 | `requirements` | What must the design satisfy? | requirement counts by kind, the one or two hardest targets | requirements, assumptions, constraints, dependencies | requirements to what satisfies them (`traceability`) |
| 5 | `current-state` | What exists today, and what is wrong with it? | what runs today, what breaks, who suffers | current applications, capabilities, integrations | applications by lifecycle (`bars`) |
| 6 | `target` | What are we building? | one card per user group or outcome | target capabilities | components by layer (`layers`) |
| 7 | `application` | What are the parts, and what does each do? | what is built, what is not started, what waits | applications, components, environments | applications around the system (`map`) |
| 8 | `integration` | How does it talk to everything else? | how each kind of integration fails safe | integrations, acceptance items | integrations around the system (`map`) |
| 9 | `data` | What data moves, and who is accountable for it? | the personal data, where it lives, how long it is kept | data objects, data flows | data flows source to target (`flow`) |
| 10 | `infrastructure` | Where does it run, and how does it get there? | hosting, network exposure, release path | (its own tables) | environments (`layers`) |
| 11 | `security` | How is it protected, and what risk remains? | the exposure that matters and its treatment | controls, security risks | controls by area against status (`matrix`) |
| 12 | `nfr` | How does the design meet its quality targets? | the hardest targets and what proves them | non-functional requirements | requirements by category against status (`matrix`) |
| 13 | `decisions` | What did we decide, and where do we depart from the standard? | the decisions that need approval elsewhere | decisions, deviations, exceptions | decisions by status (`bars`) |
| 14 | `operations` | Who runs it, and are they ready? | the missing owner or team, support hours, records | readiness items | readiness by area (`matrix`) |
| 15 | `monitoring` | How will we know it is unwell? | what alerts, where it goes, what is suppressed | alerts, acceptance items | alerts by severity (`bars`) |
| 16 | `service-processes` | Do the service processes know about it? | which processes are ready and which wait | process readiness | one lane per process (`swimlane`) |
| 17 | `runbooks` | Can support act without the build team? | tested, untested, missing | runbooks | runbooks against status (`matrix`) |
| 18 | `transition` | How do we go live, and how do we back out? | the cutover order, the point of no return, hypercare | cutover steps, readiness and acceptance items | cutover steps in order (`flow`) |
| 19 | `risks` | What could go wrong, and what already has? | the worst risks by id, the dependency at risk | risks, issues, dependencies | risks by likelihood and impact (`heatmap`) |
| 20 | `assurance` | What proves the design is ready for approval? | what is met, which reviews are outstanding | acceptance items | acceptance items by stage (`matrix`) |
| 21 | `lifecycle` | What retires, and when? | what stops, when, and what is kept | retired components | retirements on a timeline |
| 22 | `appendix` | What does a reader need to look things up? | the glossary, the views, the model | glossary | every register's size (`bars`) |

## deck.yaml

```yaml
cover:
  line: Approve parcel tracking for build, so customers see each scan within a minute
runs:
  1: What we ask for, what the solution covers and what it must satisfy
chapters:
  integration:
    claim: Every integration can fail without losing a scan.
    points:
      - Scans wait on the platform for seven days when ingest is down
      - Carriers retry webhooks for 24 hours
      - Carrier B polling backs off and resumes from its last position
    callouts:
      - {text: "Carrier B is polled under EXC-01", x: 0.55, y: 0.92}
    notes: >-
      The failure table shows a detector, a recovery and an owner for each
      integration. The messaging provider's interface is open until the
      contract is signed.
```

- **cover.line**: what the document asks for, in one line.
- **runs**: one sentence per run (1 to 4) for its divider slide.
- **claim**: one sentence, a statement a reviewer can disagree with. Not a
  topic ("Integration overview") and not a question.
- **points**: three to six, each under about twelve words, no full stops. Or
  **cards**: three to six `{title, text}` pairs, for things that sit side by
  side (in, out, not here). Not both.
- **callouts**: up to three short tags on the picture. `x` and `y` are
  fractions of the picture's width and height (0 to 1) where the tag points.
  Put them on what the picture shows, and check the screenshot.
- **notes**: two to five sentences the presenter says, or
  `{story: ..., detail: ..., picture: ...}` for one note per slide. Lead with
  what is open.
- Every text takes placeholders. Counts in points and claims are
  `{count:...}`, as in the prose; `check` reads deck.yaml too.
