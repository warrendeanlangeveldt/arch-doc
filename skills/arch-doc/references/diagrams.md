# Diagrams

A figure lives in the project's `diagrams/` directory under its name: its
source, and the PNG and SVG rendered from it. The content cites it by that
name.

```
FIGURE scan-journey | A scan from the handheld to the customer's notification
VIEW pts-integration | Parcel Tracking Solution: integrations | integration-flows
```

`FIGURE` numbers it "Figure n"; `VIEW` numbers it "View n", ties it to a
metamodel viewpoint, and its caption carries that viewpoint's name in the
profile's EA metamodel ("ArchiMate: Application Cooperation"). Reference each
one where the text discusses it with `{fig:<name>}` or `{view:<name>}`; a
figure nobody references fails `figure`.

The seed's viewpoint keys, with their ArchiMate names (CoreEA, TOGAF and
Essential names are in `metamodels/seed.yaml` under `viewpoints:`):

| Key | Title | ArchiMate |
|---|---|---|
| `solution-context` | Solution Context | Layered |
| `project-traceability` | Requirement Traceability | Requirements Realization |
| `business-outcome` | Business Outcome Alignment | Goal Realization |
| `capability-map` | Capability Alignment | Capability Map |
| `application-landscape` | Application Landscape | Application Structure |
| `application-context` | Application Context | Application Usage |
| `application-components` | Application Components | Application Structure |
| `integration-flows` | Integration Flows | Application Cooperation |
| `logical-data` | Logical Data | Information Structure |
| `crud` | Data Access Matrix | (none; use CoreEA or TOGAF) |
| `infrastructure` | Infrastructure | Implementation and Deployment |
| `control-traceability` | Control Traceability | Motivation |
| `operational-support` | Operational Support | Organization |
| `release-scope` | Release Scope | Implementation and Migration |
| `retirement-impact` | Retirement Impact | Migration |

## Which tool

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py -C <project> diagrams
```

lists every figure and view per chapter with its source, its outputs and
whether they are current, and says which tools it found:

- **arch-diagram** counts as installed when `ARCH_DIAGRAM_HOME` points at it,
  when the plugin cache holds it (the highest version wins), when the
  installed-plugins record names it, or when it is a skill in the Claude
  directory or the project's `.claude/skills/`. The Claude directory is
  `CLAUDE_CONFIG_DIR`, else `~/.claude`.
- **Node** (`npx`) renders Mermaid with `@mermaid-js/mermaid-cli@11.12.0`,
  pinned so every machine draws the same figure.
- **Chrome** (or `CHROME_PATH`) turns a static SVG into a PNG for Word.

When arch-diagram is missing, suggest installing it once, with these
commands, and then carry on in Mermaid without asking again:

```
/plugin marketplace add warrendeanlangeveldt/arch-diagram
/plugin install arch-diagram@arch-diagram
```

## Source types

| Source | Rendered by | Use for |
|---|---|---|
| `<name>.mmd` | Mermaid CLI through `npx`, themed from the profile's `house.palette` and fonts; SVG, and PNG at twice the size | flows, sequences, states, gantt timelines; every figure when arch-diagram is not installed |
| `<name>.ead` | arch-diagram's `ea.py render` | EA views in the profile's metamodel (ArchiMate, CoreEA, TOGAF, Essential), C4 and house diagrams |
| `<name>.py` | the Python running archdoc, from `diagrams/` | a view placed by hand with arch-diagram's `ealib`, or any figure a script draws |
| `<name>.png` / `.svg` alone | nothing: a static figure | an image the user supplies |

- **`.ead`:** one file per figure, named for the figure. When a file declares
  several views, the figure draws the one whose id matches its name. Start
  each file with `model "model.json"` so every view draws from one
  `diagrams/model.json`, the same model `CATALOGUE` counts. Give each model
  object that stands for a register record a `ref` with the record's id, so
  `count-model` can match them; register external systems drawn as
  Application Components as `application` records.
- **`.py`:** runs with `ARCHDOC_FIGURE` (the figure name), `ARCHDOC_OUT` (the
  directory to write `<name>.png` or `.svg` into) and `ARCHDOC_PALETTE` (the
  house palette as JSON) set. With arch-diagram installed,
  `ARCH_DIAGRAM_SCRIPTS` holds its scripts directory and is on `PYTHONPATH`,
  so `from ealib import ...` works; a script that imports `ealib` without
  arch-diagram fails with the install hint. Scripts and arch-diagram renders
  run with `PYTHONDONTWRITEBYTECODE=1`, so `diagrams/` gets no
  `__pycache__`.
- **Helper modules:** a `.py` that no `FIGURE` or `VIEW` names is a helper,
  not an unused source, when a figure script imports it (directly or through
  another helper), or when its name starts with `_` or ends with `lib`
  (`_shapes.py`, `viewlib.py`). `diagrams` lists helpers separately.

## Rendering

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py -C <project> diagrams --render
```

renders every figure whose PNG or SVG is missing or older than its source (or
than `model.json`, for `.ead`). `--force` renders all of them; `--json` gives
the listing and results as JSON. arch-diagram's layout warnings are printed
under each view. A missing tool fails the figures that need it and prints its
install hint once; nothing is ever drawn as a placeholder.

`build docx` renders a stale or missing PNG itself. When the tool is missing
and an older PNG exists it uses that; when there is no PNG at all it stops and
names the figure, the line that cites it and the tool to install. The site and
the deck draw a `.mmd` with no render in the browser and on the generated
picture respectively, so only Word needs the PNG.

**Look at every PNG after rendering.** Check that no label is clipped, no
line crosses a label, nothing is cut off, and the figure says what the
caption says. When an arch-diagram layout is untidy, steer it with the view
language's hints before anything else:

| Hint | Effect |
|---|---|
| `same A B C` | these boxes share a row |
| `A above B` | A goes in a higher row (same band) |
| `hide A -[flow]-> B` | leave that relationship off this view |
| `width 1100` | a wider page when a row cannot be narrower |

A data access matrix (the `crud` viewpoint) is a matrix view in the view
language (`matrix "<relationship>" rows ... cols ...`, or CoreEA's
`matrix writes=CU reads=R rows ... cols ...`); a matrix view holds only the
matrix and its key.

A changed profile makes every `.mmd` stale, because the Mermaid theme comes
from its palette and fonts; a changed `model.json` makes every `.ead` that
names it stale.

## The deck's picture slides

Every chapter's third slide is a picture. It uses the chapter's first
rendered figure or view whose aspect ratio is between 0.9 and 2.6,
letterboxed, so draw the chapter's main figure landscape or square. A
generated picture must show something (two statuses, or three nodes) and
never repeats another slide's; a chapter falls through to its other
registers' pictures until one does. Otherwise, and when a figure has only a `.mmd` source and no
render, the slide draws the chapter's generated picture from its registers
(the metamodel's `picture`), which needs no tool. Not every chapter needs a
figure.

## Chrome, and when it fails

Chrome turns a static SVG into a PNG for Word (`ensure_png`); the deck's and
site's browser tests drive it the same way, through `archdoc/chrome.py`.
Each run gets its own temporary profile (`--user-data-dir`, removed
afterwards), `--no-first-run` and `--no-default-browser-check`, so it shares
no profile lock or DevTools port with any other Chrome on the machine. It
runs in its own process group and its output is read as it streams.

A run is judged by its output, not its exit code: under load Chrome can
finish its work and then hang or exit non-zero on the way out. As soon as
Chrome has reported writing the screenshot and the PNG is complete (its
signature and closing chunk present), the whole process group is killed and
the PNG is used, whatever the exit code. A run that exits 0 with a complete
PNG is accepted too. Otherwise the run ends at exit or after 120 seconds and
raises an error naming the cause, with the end of Chrome's output. Nothing
is retried and no placeholder image is written.

| Message | Means | Do |
|---|---|---|
| `no PNG, and Chrome is not installed to make one` | no Chrome or Chromium found | install it, or set `CHROME_PATH` |
| `Chrome could not rasterise it (exited N)` | Chrome exited non-zero without a complete image | read the output shown; open the SVG in a browser to see whether it draws |
| `Chrome could not rasterise it (did not exit within 120s)` | Chrome neither finished the image nor exited | close other headless Chrome runs and render again |
| `Chrome could not rasterise it (wrote no complete screenshot)` | Chrome exited 0 but the file is missing or cut short | check that the SVG has a size (`width`/`height` or `viewBox`) and opens on its own |
| `Chrome could not rasterise it (exited without complete output)` | Chrome's process ended with no exit code and no complete image | render again; if it repeats, run the command from the message by hand |

When Chrome cannot run at all on a machine, render the figure elsewhere and
commit its PNG beside the source: a current PNG is used as it is.
