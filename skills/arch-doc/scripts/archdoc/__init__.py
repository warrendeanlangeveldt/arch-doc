"""arch-doc core: one parsed project that every output and check reads.

The docx, site and deck builders, the checks and the diagram tools all read
the same :class:`~archdoc.project.Project`. None of them re-parses content,
re-numbers sections or invents anchors: the core does that once, here.

Loading
-------

>>> from archdoc import Project
>>> p = Project.load("examples/northwind-parcels")

``Project.load(dir)`` raises :class:`ProjectError` only when arch-doc.yaml,
the profile or the metamodel cannot be read. Every problem in registers or
content is collected in ``p.issues`` (a list of
:class:`~archdoc.registers.Problem` with ``code``, ``message``, ``source``
and ``anchor``) for the checks to report.

Project
-------

``p.title``, ``p.short``, ``p.kind``, ``p.layer``, ``p.version``
    From arch-doc.yaml; ``p.config`` is the whole mapping (with defaults).
``p.profile``
    :class:`~archdoc.profile.Profile`: ``get("systems.itsm.name")``,
    ``is_set(path)``, ``text(path)``, ``palette``, ``fonts``, ``ea_metamodel``.
``p.metamodel`` / ``p.model``
    The loaded :class:`~archdoc.metamodel.Metamodel` and the
    :class:`~archdoc.metamodel.EffectiveModel` after the profile and kind
    are applied (``model.viewpoints``, ``model.runs``, ``model.artefact_types``).
``p.chapters``
    Numbered :class:`~archdoc.project.Chapter` objects in document order.
    A chapter has ``key``, ``title``, ``number`` (int), ``anchor`` (``s7``),
    ``question``, ``story``, ``picture`` ({kind, from, by}), ``deck``
    ({run, min_slides}), ``viewpoints``, ``lead`` (lead-in blocks),
    ``sections`` and ``blocks()`` (lead-in then every section's blocks).
``Chapter.sections``
    :class:`~archdoc.project.Section` objects: ``key``, ``title``,
    ``number`` ("7.3"), ``anchor`` (``s7-3``), ``guidance``, ``artefacts``
    (``ArtefactRef(type, where)``), ``optional``, ``new`` (a ``[new]``
    section), ``source``, ``blocks``, ``labels`` (field -> column header
    from the metamodel section's ``labels:`` or extracted ``column_map``)
    and ``template_columns`` (the organisation template's table headers).
Blocks (:mod:`archdoc.content`)
    Every block has ``kind``, ``anchor``, ``text`` (placeholders resolved,
    inline Markdown kept; :func:`~archdoc.content.inline_runs` splits it
    into styled runs, :func:`~archdoc.content.plain` strips it), ``raw``,
    ``source`` (file, line) and ``unresolved``.

    - ``Para``
    - ``Bullets``: ``items``, ``levels``, ``ordered``, ``item_anchors``
    - ``Table``: ``header``, ``rows``, ``header_anchor``, ``row_anchors``
    - ``RegisterTable`` (kind ``register``): a Table plus ``type``,
      ``where``, ``columns``, ``records``, ``chips`` (one per row) and
      ``labels`` (from ``REGISTER ... labels f="Header"``). ``header`` uses
      the directive's labels, then the section's, then the type's.
      ``rows`` are display values: placeholders resolved, enum and status
      values labelled ("Must", "In build", "API"), each TBC as
      "TBC: <owner>". ``compact_rows`` name the owner once per row (an
      inherited TBC reads "TBC" where the row already names the owner;
      that cell's owner is ``records[i].accountable``). ``raw_rows`` are
      the stored values.
    - ``Catalogue``: a Table of EA model object counts by type
    - ``Figure``: ``name``, ``number``, ``label`` ("Figure 4"), ``caption``,
      ``path`` (PNG/SVG if rendered), ``source_file`` (.mmd/.ead/.py)
    - ``View``: a Figure numbered "View n" plus ``title``, ``viewpoint``
      and ``ea_name`` (the viewpoint's name in the profile's EA metamodel)
``p.figures`` / ``p.views``
    Every Figure / View block in document order.
``p.registers[type]``
    :class:`~archdoc.registers.Register`: iterable of
    :class:`~archdoc.registers.Record` (``id``, ``title``, ``status``,
    ``chip``, ``owner``, ``accountable``, ``get(field)``, ``source``), with
    ``get(id)`` and ``filter(where)``. A record's values:

    - ``display(field)``: stored, as text (placeholders as written);
    - ``text(field)``: placeholders resolved, enums as stored (for prose);
    - ``shown(field)``: as a table shows it (resolved and labelled);
    - ``cells(cols, short=True)``: a table row of ``shown`` values;
    - ``row(cols)``: stored values;
    - ``tbcs()`` (whole-value TBCs), ``embedded_tbcs()`` (inside longer
      text), ``all_tbcs()``: one per field.

    ``register.type`` is the :class:`~archdoc.registers.ArtefactType`
    (``prefix`` (the first), ``prefixes`` (all), ``matches_id(id)``,
    ``fields``, ``columns``, ``status`` → chip, ``header(col)``,
    ``value_label(field, value)``). Ids may carry a namespace before the
    prefix (``NW-SEC-RISK-03``).
``p.number(chapter_key, section_key=None)``
    "7" or "7.3", or None when not in this document.
``p.section(ch, sec)``, ``p.chapter(key)``, ``p.by_number("7.3")``, ``p.record(id)``
``p.tbcs()``
    Every TBC as :class:`~archdoc.project.TbcItem`: ``owner`` (None when it
    has none), ``origin`` (register or content), ``record``, ``field``,
    ``source``, ``anchor``, ``inherited``, ``context`` / ``text`` (resolved
    plain text) and ``key``. A register TBC is one per record field,
    whole-value or inside longer text; a prose TBC one per occurrence.
``p.open_items(limit=140)``
    The open-items list every output shows: one
    :class:`~archdoc.project.OpenItem` per record with a TBC and per
    paragraph, list item or table row with one, in document order. Each has
    ``id`` (record id or prose anchor), ``text`` (one resolved plain line,
    cut at a word boundary), ``owner`` (None if any of its TBCs has none),
    ``owners``, ``anchor``, ``section`` ("7.3 Component Design") and
    ``section_anchor``, ``inherited``, ``origin``, ``record``, ``fields``
    and the folded ``tbcs``. Count open items with ``len(p.open_items())``.
``p.unresolved()``
    Every placeholder that did not resolve, with its location.
``p.resolve_text(text)``
    Fill placeholders in any other text (deck.yaml claims and notes).
``p.dependencies``
    ``{ref: Project}`` for each ``depends_on`` entry with a ``path``. An
    entry without one can give ``sections: {"10.2": "Hosting Model"}`` for
    ``{dep:REF:10.2}``.
``p.catalogue_count(what)``
    ``{cat:objects}``, ``{cat:relationships}``, ``{cat:<object type>}``.
``p.numbering()``
    ``(number, title, key path)`` rows for every chapter and section.

Anchors
-------

Computed in the core (:mod:`archdoc.content`, SPEC 6.2): ``s7``, ``s7-3``,
``s7-3-p2``, ``s7-3-l1-i4``, ``s7-3-t1``, ``s7-3-t1-h``, ``s7-3-t1-r4``,
lead-in blocks as ``s7-p1``, ``fig-n`` and ``view-n`` through the document,
``dc`` for document control (:data:`~archdoc.content.ANCHOR_DC`) and
``app-*`` for generated back matter (``app-open-items``, ``app-references``).

Phase 2 module contracts
------------------------

The CLI (``scripts/archdoc.py``) calls these; each module is optional until
it exists, and the CLI says "not built yet" when it is missing.

- ``archdoc.checks.run(project) -> list[Finding]``; a Finding has ``id``,
  ``severity`` ("error" or "warn"), ``message``, ``source``, ``anchor``,
  ``to_dict()`` and a one-line ``str()``.
- ``archdoc.docx_build.build(project) -> list[Path]``, likewise
  ``site_build`` and ``deck_build``.
- ``archdoc.extract.cli(args) -> int``, ``archdoc.diagrams.cli(args) -> int``,
  ``archdoc.comments.cli(args) -> int``, given the parsed argparse namespace
  (``args.project`` is the project directory).
"""
from .content import ANCHOR_DC, ANCHOR_OPEN_ITEMS, ANCHOR_REFERENCES, inline_runs, plain
from .metamodel import Metamodel, MetamodelError, evaluate_when, load_metamodel
from .profile import Profile, ProfileError, load_profile
from .project import Chapter, OpenItem, Project, ProjectError, Section, TbcItem
from .registers import Problem, Record, Register, Source, Tbc

__version__ = "0.1.0"

__all__ = [
    "ANCHOR_DC", "ANCHOR_OPEN_ITEMS", "ANCHOR_REFERENCES", "Chapter", "Metamodel", "MetamodelError", "OpenItem",
    "Problem", "Profile", "ProfileError", "Project", "ProjectError", "Record", "Register", "Section",
    "Source", "Tbc", "TbcItem", "evaluate_when", "inline_runs", "load_metamodel", "load_profile", "plain",
]
