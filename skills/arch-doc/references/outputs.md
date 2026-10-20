# Outputs

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py -C <project> build all
```

`build docx`, `build site` and `build deck` build one each. Every build runs
`check` first and stops on errors; `--force` builds anyway, for a draft you
say is a draft. All three read the same loaded project, so numbering,
anchors, figure numbers and counts agree across them. Outputs go to
`<project>/out/`; never edit them, rebuild them.

## The Word document

`out/<Title> v<version>.docx`.

**Neutral mode** (no template): an A4 document with a cover, a
document-control section (the document's details, the designs it depends on,
the history from arch-doc.yaml), a table of contents, numbered chapters and
sections, captions, and tables in the house style. Status chips are coloured
words. Colours and fonts come from the profile's `house`.

**Template mode** (arch-doc.yaml `template:`, else the profile's
`template.path`): the organisation's own .docx is filled in place. Tracked
changes and comments are cleaned; the template's chapter and section headings
are matched to the document's in metamodel order; each kept section's
guidance is replaced by content; a template table whose header matches a
content table is cloned for it, otherwise a new table takes the template's
table style; template sections the document does not carry are removed;
section breaks are kept; the document-control tables are filled from
arch-doc.yaml; cover text in `template.fields` is replaced. Styles come from
`template.styles` you set, then the ones detected in the template, then the
defaults. `references/metamodel.md` covers extraction and the fragment.

In both modes:

- figures and views are sized to the text width, and portrait ones are
  capped at the page height; captions read "Figure n. ..." and "View n. ...",
  and a view's caption adds its EA metamodel and viewpoint name ("(ArchiMate
  Application Cooperation)", or the profile's `ea_viewpoint_names`) and the
  `view_note` when one is set (`project.md`, `interview.md`);
- dates follow the profile's `house.date_format` (`long` by default), as
  they do on the site;
- each table column gets at least the width of its longest unbreakable word
  (ids and statuses never break), and the rest goes to the long-text
  columns; hyphens inside ids are non-breaking. A table that cannot fit
  steps its font down to 8pt; in the neutral document it then turns its page
  to landscape, while template mode keeps the template's layout. A table
  that still cannot hold its longest word gets a warning naming it by
  anchor, section and source line, with what to do: give a `REGISTER` fewer
  columns with `cols`, or split a plain table;
- every header row repeats on each page and keeps with the first data row;
- in template mode, text the build writes never carries the template's
  strike-through or highlight review marks;
- the catalogue table adds "Shared with ..." and "Examples" columns when the
  model has the data, limited by arch-doc.yaml `catalogue.columns`;
- every `{sec:}` renders the number the heading has; the build verifies the
  rendered numbering against `numbering`;
- the table of contents lists every heading with its number; Word fills in
  the page numbers when the document is opened (it asks to update fields);
- a figure with no PNG is rendered first (`references/diagrams.md`); when that
  is impossible the build stops and names the figure and the missing tool.

To look at it: `soffice --headless --convert-to pdf --outdir <dir> "<docx>"`
when LibreOffice is installed, then read pages of the PDF.

## The review site

`out/site/index.html`, `out/site/media/` (figures at 1600 px for the page) and
`out/site/media/full/` (the originals, for the lightbox), and
`out/site/PUBLISH.md`, the publish call for this build.

- A left contents list, the chapters, and two panels: **Open items**
  (`#app-open-items`: one item per record, paragraph, list item or table
  row that holds a TBC, with its resolved text, owner and section) and
  **My comments** (`#app-comments`).
- Every heading, paragraph, list item, table row and figure has a stable
  anchor: `s7` (chapter 7), `s7-p1` (its lead-in paragraph 1), `s7-3`
  (section 7.3), `s7-3-p2`, `s7-3-l1-i4` (list 1, item 4), `s7-3-t1`,
  `s7-3-t1-h`, `s7-3-t1-r4` (table 1, header, row 4), `fig-4`, `view-2`, `dc`
  (document control). A comment names its anchor, so it can be placed again.
  Anchors are positional: inserting a paragraph moves the numbers after it in
  that section, and an imported comment whose anchor no longer exists falls
  back to the nearest parent (`s7-3-p5` to `s7-3`).
- View captions read as in the Word document: the title, the EA metamodel
  and viewpoint name, and any `view_note`. Dates follow `house.date_format`.
  A dependency is named as `{dep:}` names it.
- Figures open in a lightbox with zoom. A `.mmd` figure with no render is
  drawn in the browser. A figure with no file at all (a `--force` build)
  shows a "Not rendered" notice naming the file it needs.
- Each chapter and section has a review status: not reviewed, in review,
  changes needed, agreed.

Opened as a local file, comments and review status stay in that browser, and
**Export comments** under My comments saves them as JSON for the author.
Published with the `comments` capability, the comments live in the
artifact's shared store, so the page hides My comments and its export
controls. Where a hosted page keeps comments in the browser (the comments
capability does not resolve), **Export comments** saves through the
`downloads` capability, and the viewer confirms each save; until
`downloads` answers, or when it is unavailable, the button is hidden and
**Copy as JSON** remains.

The open-items panel lists a TBC inside a longer register value against its
row, with the value, and a register table names an inherited TBC's owner
once per row rather than in every cell.

### Publishing the site

With the Artifact tool, publish with exactly the call in
`out/site/PUBLISH.md`:

- `file_path`: `out/site/index.html`
- `root`: `out/site`
- `files`: the plain list of `media/...` and `media/full/...` paths it gives
- `capabilities`: `{"comments": {}, "db": {}, "downloads": true}`. Load the
  `artifact-capabilities` skill before passing them.
- `icon`: `document`

`comments` lets reviewers post threads that start with their anchor;
`db` keeps the review status per section in the collection `review`, shared
with everyone on the page; `downloads` lets Export comments save a file
where the page keeps comments in the browser. `comments` and `db` make the
artifact organisation-internal. The page carries no organisation name unless the
profile gives one.

To republish after a rebuild, publish the same `file_path` with the same
`root` and `files`, and leave out `icon` and `capabilities` so the artifact
keeps them. Comments and status survive the republish. From another
conversation, pass the artifact's `url`.

The Artifact tool publishes files under the session's working directory or
its scratchpad. When the project's `out/` is outside both, copy `out/site`
into the scratchpad and publish from the copy, with `root` set to it.

### Reading the review back

From the published page:

1. `ArtifactComments` with `action: "read"` and the artifact URL gives the
   threads. A comment posted from the page starts with `[<anchor>]`, then the
   section, any quoted selection, then the note.
2. Write them to a JSON file as a list of `{"text": ..., "author": ...,
   "at": ...}`, keeping each body as written.
3. Run `comments import <file>`.
4. Review status: `ArtifactData` with `action: "list"` and
   `collection: "review"`. One document per section anchor that has a status:
   `{"status": "changes", "section": "7.3 Component Design", "at": "..."}`;
   `status` is `in-review`, `changes` or `agreed`.

Threads opened from the shell's own comment mode carry no `[anchor]`; place
them by their quoted text.

From a local copy: the reviewer sends the file **Export comments** saved, and

```bash
uv run -q --with pyyaml --with python-docx --with pillow python <skill-dir>/scripts/archdoc.py -C <project> comments import <file>
```

merges it into `out/comments.json` (an import adds only comments it has not
seen; for review status the latest wins) and prints the comments grouped by
anchor, in document order, with each section's current number and title.
Fix each at its source, rebuild, and republish.

## The TL;DR deck

`out/deck/index.html` and `out/deck/media/` (the figures it shows).

- 1920 x 1080 slides scaled to fit the window's width and height,
  letterboxed. The previous and next buttons (shown on hover, always on a
  touch screen), a click on the left or right third of the slide, the arrow
  keys, Page Up and Down, Space, Home and End, or a swipe move between
  slides. The counter, or **G**, opens every slide as a thumbnail; click
  one to go to it. A progress bar runs along the slide's foot, and the
  cover shows a short hint that fades. **N** shows the speaker notes; **P**
  prints one slide per page, for a PDF. None of the navigation shows in
  print, `?shot=1` or `?check=1`.

  | Control | Does |
  |---|---|
  | Right, Down, Page Down, Space; next button; click on the right third; swipe left | next slide |
  | Left, Up, Page Up; previous button; click on the left third; swipe right | previous slide |
  | Home, End | first, last slide |
  | G, or click the counter | overview of every slide; G or Escape closes it |
  | N | speaker notes on or off; Escape hides them |
  | P | print, one slide per page |

  A click on a link, a button or selected text does not move the slide, and
  a click on text waits a moment so a double click can still select a word.
  The page takes focus when it loads and when the pointer first moves, so
  the keys work inside an Artifact frame.
- Order: a cover; a divider before each of the four runs; then three slides
  per chapter: `chNN-a` story, `chNN-b` detail, `chNN-c` picture. Chapters
  with `deck.min_slides: 2` in the metamodel, or fewer than three detail
  rows, get story and picture only. Footer: `<short> v<version> · <chapter>`.
- The story slide carries a strip of register facts, the claim and its
  points or cards with each section's story beneath (cards grow to the room),
  the open item that matters most, and its registers beside the story or,
  when the story is short, stacked under the points. A register never shows
  twice on one slide.
- The detail slide spans every table across the width and fills the body
  to its foot: the main register's rows first, then each summarised section
  opened with as many rows as fit, then rows round the open tables;
  summaries share a line three at a time, and each table has one footnote
  such as "9 more rows · 1 more column in section 4.3". A table that would
  show no rows collapses to its summary line, and a thin table (under two
  columns, or one row of fewer than three columns) is always a summary, so
  no slide shows a bare header or a stub.
- The layout check judges each lane: a column that holds rows back must
  not stop 120 px short across half its width, and a full-width body must
  reach 85% unless less room is left than the cheapest addition that did
  not fit. It also fails a header-only or thin table and a callout over the
  picture.
- The picture slide uses the chapter's first rendered figure or view with an
  aspect ratio between 0.9 and 2.6, letterboxed as large as the area allows,
  otherwise its generated picture (`references/diagrams.md`). Callouts avoid
  the picture's text and drawn boxes; with no free room they go to a strip
  under a shortened picture, never over the drawing. A generated picture
  draws only the records the chapter cites and must say something (a status
  picture at least two statuses, a node picture at least three nodes);
  otherwise the chapter falls through to its other registers' pictures. No
  picture repeats on two slides: the build refuses a repeat.
- Dividers carry the run's open items and its risks by rating and status.
- Open items in the deck are the core's (`Project.open_items()`), the same
  list the site shows: one item per record, paragraph, list item or table
  row that holds a TBC. The deck's "n open items" and the site's "Open items
  n" are the same count. An item whose owner slot names no owner says "No
  owner".
- Dates follow `house.date_format`, as in the Word document and on the site.
- Text is measured before it is placed and never set below 24 px.

### deck.yaml

```yaml
cover: {line: <what the document asks for>}
runs: {1: <one sentence>, 2: ..., 3: ..., 4: ...}
chapters:
  <chapter key>:
    claim: <one sentence>
    points: [<3 to 6 short points>]          # or
    cards: [{title: ..., text: ...}, ...]     # 3 to 6, not both
    callouts: [{text: ..., x: 0.4, y: 0.2}]   # up to 3; x, y are fractions of the picture
    notes: <2 to 5 sentences>                 # or {story: ..., detail: ..., picture: ...}
```

The chapter keys may also sit at the top level, without `chapters:`. Every
text takes placeholders. A structural error (points and cards both, four
callouts, two points, an unknown field in a chapter, a cover key other than
`line`) stops `build deck` with every problem listed; a chapter key the
document does not carry is a warning and its slides are ignored. Without
deck.yaml, claims and cards come from each chapter's first sentences and
register counts. `references/writing.md` says what to write.

### Looking at the deck

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --hide-scrollbars \
  --virtual-time-budget=4000 --window-size=1920,1080 --screenshot=/tmp/ch08-c.png \
  "file://<project>/out/deck/index.html?slide=ch08-c&shot=1"
```

`?slide=<id>&shot=1` shows that slide alone, unscaled. `#<id>` opens a slide
in the normal viewer. `?check=1` runs the layout check once the fonts load
and writes its JSON into `#deck-check`; `?check=ui` steps through the
buttons, click zones, overview and a thumbnail and writes what each step
showed (`window.__deckUI()`) the same way; in a browser console,
`window.__deckOverflow()` lists every element that leaves its slide or box
and `window.__deckCallouts()` where each callout landed. On Linux use
`google-chrome` or `chromium`, or `CHROME_PATH`.

The site is a page fragment, so screenshot it whole, at the top
(`--window-size=1440,900 file://.../out/site/index.html`); headless Chrome
paints a blank page when the URL has a `#anchor`.

### Publishing the deck

The deck is a plain page with no capabilities:

- `file_path`: `out/deck/index.html`
- `root`: `out/deck`
- `files`: every file in `out/deck/media/`, as `media/<name>`
- `icon`: `slides`
- `description`: one sentence, such as "TL;DR deck for the <title> design".

It plays in the artifact viewer as it does locally. The deck takes focus
when it loads and when the pointer first moves over it, so the keys work
inside the viewer's frame; the buttons, click zones and counter work
without it. Republish the same way after a rebuild; omit `icon`. When
`out/` is outside the working directory and the scratchpad, publish from a
copy in the scratchpad, as for the site.
