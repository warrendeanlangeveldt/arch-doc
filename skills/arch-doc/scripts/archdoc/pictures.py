"""Generated architecture pictures for the deck's picture slides (SPEC 6.3).

Every picture is native SVG drawn only from the project: its registers, its
``depends_on`` designs and its own identity. Nothing is decorative. Each one
is laid out for a 1664 x 640 area (the picture slide's body), in the house
palette from the profile, with text measured before it is placed:

- a character is taken as 0.55 x the font size (0.58 bold, 0.68 capitals),
  so labels are wrapped to the box they sit in and cut with an ellipsis only
  when a box cannot grow;
- no text is smaller than 24px;
- connectors carry arrowheads that stop 2px short of the box they point at.

Kinds (``metamodel.PICTURE_KINDS``):

=============  ============================================================
``layers``     a stack: the design over what it depends on, or records
               banded by a field (components by layer)
``timeline``   dated or staged records on an axis (checkpoints, retirements)
``traceability``  business requirements to functional requirements to what
               satisfies them
``heatmap``    risks placed by likelihood x impact
``matrix``     items by group (``by``) against status
``swimlane``   one lane per process: design, evidence, readiness
``flow``       a sequence (cutover steps, by ``order`` and ``after``) or a
               graph (data flows, source to target)
``bars``       catalogue counts as rows of record tiles, or every register
``map``        integrations or applications around the system
=============  ============================================================

:func:`draw` returns None when the register a picture needs is empty;
:func:`generate` then walks the chapter's fallback chain (its ``picture``
kind, any kinds named in ``picture.fallback`` or in a list-valued
``picture.by``, and finally ``layers`` from ``depends_on``, which always
draws).
"""
from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable

from .metamodel import PICTURE_KINDS
from .registers import Record, Tbc, as_list, display, parse_tbc

if TYPE_CHECKING:  # pragma: no cover
    from .project import Chapter, Project

W, H = 1664, 640
MIN_FONT = 24
CHAR, BOLD, CAPS = 0.55, 0.58, 0.68
LINE = 1.25

# The register each kind reads when the metamodel gives no ``from``.
DEFAULT_FROM = {
    "layers": "depends_on", "timeline": "checkpoint", "traceability": "functional-requirement",
    "heatmap": "risk", "matrix": "acceptance-item", "swimlane": "process-readiness",
    "flow": "cutover-step", "bars": "registers", "map": "integration",
}

CHIP_ORDER = ("done", "partial", "not-started", "tbc")
CHIP_WORDS = {"done": "Done", "partial": "In progress", "not-started": "Not started", "tbc": "TBC"}


# ----------------------------------------------------------------- measure

def text_width(text: str, size: float, bold: bool = False, caps: bool = False) -> float:
    """Estimated rendered width of one line of text."""
    factor = CAPS if caps else (BOLD if bold else CHAR)
    return len(text) * size * factor


def _fit_chars(width: float, size: float, bold: bool = False, caps: bool = False) -> int:
    factor = CAPS if caps else (BOLD if bold else CHAR)
    return max(1, int(width // (size * factor)))


def ellipsize(text: str, width: float, size: float, bold: bool = False, caps: bool = False) -> str:
    """``text`` cut at a word (or character) with an ellipsis to fit ``width``."""
    if text_width(text, size, bold, caps) <= width:
        return text
    n = _fit_chars(width, size, bold, caps) - 1
    if n <= 0:
        return "…"
    cut = text[:n]
    if " " in cut[n // 2:]:
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip(" ,;:-") + "…"


def wrap(text: str, width: float, size: float, bold: bool = False, max_lines: int | None = None,
         caps: bool = False) -> list[str]:
    """Greedy word wrap of ``text`` to ``width`` at ``size``. Words longer
    than a line are broken. With ``max_lines``, the last kept line ends in an
    ellipsis when text is left over."""
    per = _fit_chars(width, size, bold, caps)
    lines: list[str] = []
    cur = ""
    for word in str(text).split():
        while len(word) > per:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:per - 1] + "-")
            word = word[per - 1:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= per:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if not lines:
        lines = [""]
    if max_lines is not None and len(lines) > max_lines:
        rest = " ".join(lines[max_lines - 1:])
        lines = lines[:max_lines - 1] + [ellipsize(rest, width, size, bold, caps)]
    return lines


def human(value: Any) -> str:
    """A field or status value as words: 'in-build' becomes 'In build'."""
    t = parse_tbc(value)
    if t is not None:
        return str(t)
    s = display(value).replace("-", " ").replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else ""


def status_words(r: Record) -> str:
    """A record's status as words: "In build", or "TBC: <owner>"."""
    st = r.get("status")
    if isinstance(st, Tbc):
        owner = st.owner or r.accountable
        return f"TBC: {owner}" if owner else "TBC"
    if hasattr(r, "shown") and st not in (None, ""):
        return r.shown("status")
    return human(st) or "TBC"


# ------------------------------------------------------------------- theme

def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """``a`` moved ``t`` of the way towards ``b`` (0 keeps ``a``)."""
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    return "#{:02X}{:02X}{:02X}".format(round(ra + (rb - ra) * t), round(ga + (gb - ga) * t),
                                        round(ba + (bb - ba) * t))


@dataclass
class Theme:
    """The house tokens a picture is drawn in: the profile's palette and
    fonts (with the profile's neutral defaults), plus soft tints."""

    ink: str
    muted: str
    paper: str
    panel: str
    rule: str
    accent: str
    accent_soft: str
    done: str
    partial: str
    not_started: str
    tbc: str
    heading_font: str
    body_font: str

    @classmethod
    def from_profile(cls, profile) -> "Theme":
        p = dict(profile.palette) if profile is not None else {}
        f = dict(profile.fonts) if profile is not None else {}
        from .profile import DEFAULTS
        d = DEFAULTS["house"]["palette"]
        g = lambda k: p.get(k) or d[k]  # noqa: E731
        return cls(g("ink"), g("muted"), g("paper"), g("panel"), g("rule"), g("accent"), g("accent_soft"),
                   g("done"), g("partial"), g("not_started"), g("tbc"),
                   f.get("heading") or DEFAULTS["house"]["fonts"]["heading"],
                   f.get("body") or DEFAULTS["house"]["fonts"]["body"])

    def chip(self, chip: str) -> str:
        return {"done": self.done, "partial": self.partial, "not-started": self.not_started,
                "tbc": self.tbc}.get(chip, self.muted)

    def soft(self, color: str, t: float = 0.86) -> str:
        return mix(color, self.paper, t)

    @property
    def body_stack(self) -> str:
        return f"'{self.body_font}', 'Helvetica Neue', Arial, sans-serif"

    @property
    def heading_stack(self) -> str:
        return f"'{self.heading_font}', Georgia, 'Times New Roman', serif"


# --------------------------------------------------------------------- svg

def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def edge_point(self, toward: tuple[float, float], gap: float = 0.0) -> tuple[float, float]:
        """Where the line from this box's centre to ``toward`` leaves its
        border, pulled back ``gap`` pixels along the line (outside the box)."""
        dx, dy = toward[0] - self.cx, toward[1] - self.cy
        if dx == 0 and dy == 0:
            return self.cx, self.cy
        sx = (self.w / 2) / abs(dx) if dx else math.inf
        sy = (self.h / 2) / abs(dy) if dy else math.inf
        s = min(sx, sy)
        px, py = self.cx + dx * s, self.cy + dy * s
        d = math.hypot(dx, dy)
        return px + dx / d * gap, py + dy / d * gap


def _along(segs, u: float) -> tuple[float, float]:
    """The point a fraction ``u`` along a polyline given as segments."""
    total = sum(math.dist(p, q) for p, q in segs) or 1
    target, run = total * u, 0.0
    for p, q in segs:
        L = math.dist(p, q)
        if run + L >= target:
            f = (target - run) / (L or 1)
            return p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f
        run += L
    return segs[-1][1]


def _crosses(a: "Box", b: "Box", block: "Box") -> bool:
    """Whether the straight line between two box centres passes through
    ``block``."""
    for i in range(1, 60):
        u = i / 60
        x, y = a.cx + (b.cx - a.cx) * u, a.cy + (b.cy - a.cy) * u
        if block.x <= x <= block.x + block.w and block.y <= y <= block.y + block.h:
            return True
    return False


def _ring_route(a: "Box", b: "Box", block: "Box", off: float, frame: "Box",
                obstacles: Iterable["Box"] = ()) -> list[tuple[float, float]]:
    """Elbow points for a connector from ``a`` to ``b`` that runs round
    ``block`` on a rectangle ``off`` pixels outside it, the shorter way
    round. Each side of the rectangle stays inside ``frame`` and at least
    12px clear of the ``obstacles`` (the boxes round the block), so a lane
    never runs along a box's edge."""
    top, bottom, left, right = frame.y + 4, frame.y + frame.h - 4, frame.x + 4, frame.x + frame.w - 4
    for o in obstacles:
        if o.x < block.x + block.w and o.x + o.w > block.x:
            if o.y + o.h <= block.y:
                top = max(top, o.y + o.h + 12)
            elif o.y >= block.y + block.h:
                bottom = min(bottom, o.y - 12)
        if o.y < block.y + block.h and o.y + o.h > block.y:
            if o.x + o.w <= block.x:
                left = max(left, o.x + o.w + 12)
            elif o.x >= block.x + block.w:
                right = min(right, o.x - 12)

    def lane(edge, limit, sign):
        # off outward from the block's edge, but no further than the limit
        want = edge + sign * off
        return max(want, limit) if sign < 0 else min(want, limit)
    x0 = lane(block.x, left, -1)
    y0 = lane(block.y, top, -1)
    x1 = lane(block.x + block.w, right, 1)
    y1 = lane(block.y + block.h, bottom, 1)
    w, h = x1 - x0, y1 - y0
    per = 2 * (w + h)

    def pos(px, py):
        # nearest point on the ring and its distance round it, clockwise from top-left
        cx_, cy_ = min(max(px, x0), x1), min(max(py, y0), y1)
        d = {"t": abs(cy_ - y0), "r": abs(cx_ - x1), "b": abs(cy_ - y1), "l": abs(cx_ - x0)}
        if not (x0 < px < x1 and y0 < py < y1):
            d = {"t": abs(py - y0) if px >= x0 and px <= x1 else 1e9, "b": abs(py - y1) if x0 <= px <= x1 else 1e9,
                 "l": abs(px - x0) if y0 <= py <= y1 else 1e9, "r": abs(px - x1) if y0 <= py <= y1 else 1e9}
            if min(d.values()) >= 1e9:          # beyond a corner: the nearest corner
                cxn = x0 if px < x0 else x1
                cyn = y0 if py < y0 else y1
                side = "t" if cyn == y0 else "b"
                cx_, cy_ = cxn, cyn
                d = {side: 0}
        side = min(d, key=d.get)
        if side == "t":
            pt = (cx_, y0); t = cx_ - x0
        elif side == "r":
            pt = (x1, cy_); t = w + (cy_ - y0)
        elif side == "b":
            pt = (cx_, y1); t = w + h + (x1 - cx_)
        else:
            pt = (x0, cy_); t = 2 * w + h + (y1 - cy_)
        return pt, t
    pa, ta = pos(a.cx, a.cy)
    pb, tb = pos(b.cx, b.cy)
    corners = [(0.0, (x0, y0)), (w, (x1, y0)), (w + h, (x1, y1)), (2 * w + h, (x0, y1))]
    fwd = (tb - ta) % per
    pts = [pa]
    if fwd <= per - fwd:
        for t, c in sorted(corners, key=lambda tc: (tc[0] - ta) % per):
            if 0 < (t - ta) % per < fwd:
                pts.append(c)
    else:
        for t, c in sorted(corners, key=lambda tc: (ta - tc[0]) % per):
            if 0 < (ta - t) % per < per - fwd:
                pts.append(c)
    pts.append(pb)
    return pts


def _hit(a: "Box", b: "Box", pad: float = 0.0) -> bool:
    return (a.x - pad < b.x + b.w and b.x - pad < a.x + a.w and
            a.y - pad < b.y + b.h and b.y - pad < a.y + a.h)


@dataclass
class Text:
    """One line of measured text: what it says and where it sits, kept so a
    test can confirm no label leaves its box or crosses another."""

    x: float
    y: float
    w: float
    h: float
    text: str


class Svg:
    """A small SVG writer that measures as it places."""

    def __init__(self, theme: Theme, uid: str = "p", width: int = W, height: int = H):
        LAST_SVG.append(self)
        self.t = theme
        self.uid = re.sub(r"[^A-Za-z0-9_-]", "-", uid)
        self.w, self.h = width, height
        self.items: list[str] = []
        self.texts: list[Text] = []
        self.markers: set[str] = set()
        self.labels: list[Box] = []
        self.bottom = 0.0         # the lowest edge drawn, for the fill test
        self.rects: list[Box] = []    # every box drawn: what a callout must not cover
        self.paths: list[Callable[[float], tuple[float, float]]] = []
        self.last: Callable[[float], tuple[float, float]] = lambda u: (self.w / 2, self.h / 2)

    # -- primitives ---------------------------------------------------------
    def rect(self, x, y, w, h, fill, stroke=None, dashed=False, r=10, sw=1.5, cls=""):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        if dashed and stroke:
            st += ' stroke-dasharray="8 6"'
        c = f' class="{cls}"' if cls else ""
        self.bottom = max(self.bottom, y + h)
        self.rects.append(Box(x, y, w, h))
        self.items.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
                          f'fill="{fill}"{st}{c}/>')
        return Box(x, y, w, h)

    def line(self, x1, y1, x2, y2, color, sw=2, dashed=False):
        d = ' stroke-dasharray="8 6"' if dashed else ""
        self.items.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                          f'stroke-width="{sw}"{d}/>')

    def circle(self, cx, cy, r, fill, stroke=None):
        st = f' stroke="{stroke}" stroke-width="2"' if stroke else ""
        self.items.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"{st}/>')

    def text(self, x, y, lines: list[str], size=MIN_FONT, color=None, bold=False, anchor="start",
             caps=False, font=None, within: "Box | None" = None):
        """Lines of text whose first line's top is at ``y``. ``within`` is
        the box the text must stay inside (the whole picture when None); it
        is written as ``data-in`` so the deck's browser check can confirm the
        rendered text really fits."""
        size = max(size, MIN_FONT)
        color = color or self.t.ink
        lh = size * LINE
        fam = font or self.t.body_stack
        weight = ' font-weight="600"' if bold or caps else ""
        spacing = ' letter-spacing="1.5"' if caps else ""
        spans = []
        for i, ln in enumerate(lines):
            shown = ln.upper() if caps else ln
            spans.append(f'<tspan x="{x:.1f}" y="{y + size * 0.92 + i * lh:.1f}">{esc(shown)}</tspan>')
            w = text_width(ln, size, bold, caps)
            left = x if anchor == "start" else (x - w / 2 if anchor == "middle" else x - w)
            self.texts.append(Text(left, y + i * lh, w, lh, ln))
            self.bottom = max(self.bottom, y + (i + 1) * lh)
        b = within or Box(0, 0, self.w, self.h)
        self.items.append(f'<text font-family="{esc(fam)}" font-size="{size}" fill="{color}"{weight}{spacing} '
                          f'text-anchor="{anchor}" data-in="{b.x:.1f} {b.y:.1f} {b.w:.1f} {b.h:.1f}">'
                          f'{"".join(spans)}</text>')
        return len(lines) * lh

    def arrow(self, a: Box, b: Box, color=None, dashed=False, both=False, sw=2.0,
              via: list[tuple[float, float]] | None = None, curve=False,
              bend: tuple[float, float] | None = None, offset: float = 0.0) -> tuple[float, float]:
        """A connector from box ``a`` to box ``b`` whose head stops 2px short
        of ``b``. ``via`` gives elbow points; ``curve`` draws a horizontal
        S-curve between facing sides; ``bend`` is the control point of a
        curve that bows around something in the way; ``offset`` moves a
        straight connector sideways (two flows between the same pair).
        Returns the connector's midpoint."""
        color = color or self.t.muted
        key = f"{self.uid}-{color.lstrip('#')}"
        self.markers.add(color)
        pts: list[tuple[float, float]]
        if bend is not None:
            x1, y1 = a.edge_point(bend, 2 if both else 0)
            x2, y2 = b.edge_point(bend, 2)
            cx_, cy_ = bend
            d = f"M{x1:.1f},{y1:.1f} Q{cx_:.1f},{cy_:.1f} {x2:.1f},{y2:.1f}"
            mid = (0.25 * x1 + 0.5 * cx_ + 0.25 * x2, 0.25 * y1 + 0.5 * cy_ + 0.25 * y2)
            self.last = lambda u, a_=(x1, y1), c_=(cx_, cy_), b_=(x2, y2): (
                (1 - u) ** 2 * a_[0] + 2 * (1 - u) * u * c_[0] + u * u * b_[0],
                (1 - u) ** 2 * a_[1] + 2 * (1 - u) * u * c_[1] + u * u * b_[1])
        elif curve:
            x1, y1 = (a.x + a.w, a.cy) if b.cx >= a.cx else (a.x, a.cy)
            x2, y2 = (b.x - 2, b.cy) if b.cx >= a.cx else (b.x + b.w + 2, b.cy)
            if both:
                x1 += 2 if b.cx >= a.cx else -2
            mx = (x1 + x2) / 2
            d = f"M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
            mid = (mx, (y1 + y2) / 2)
            self.last = lambda u, a_=(x1, y1), b_=(x2, y2), m_=mx: (
                (1 - u) ** 3 * a_[0] + 3 * (1 - u) ** 2 * u * m_ + 3 * (1 - u) * u * u * m_ + u ** 3 * b_[0],
                (1 - u) ** 3 * a_[1] + 3 * (1 - u) ** 2 * u * a_[1] + 3 * (1 - u) * u * u * b_[1] + u ** 3 * b_[1])
        else:
            if via:
                start = a.edge_point(via[0], 2 if both else 0)
                end = b.edge_point(via[-1], 2)
                pts = [start, *via, end]
            else:
                start = a.edge_point((b.cx, b.cy), 2 if both else 0)
                end = b.edge_point((a.cx, a.cy), 2)
                if offset:
                    dx, dy = end[0] - start[0], end[1] - start[1]
                    L = math.hypot(dx, dy) or 1
                    nx, ny = -dy / L * offset, dx / L * offset
                    start, end = (start[0] + nx, start[1] + ny), (end[0] + nx, end[1] + ny)
                pts = [start, end]
            d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
            # midpoint along the polyline
            segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            self.last = lambda u, segs_=segs: _along(segs_, u)
            total = sum(math.dist(p, q) for p, q in segs) or 1
            half, run = total / 2, 0.0
            mid = pts[0]
            for p, q in segs:
                L = math.dist(p, q)
                if run + L >= half:
                    f = (half - run) / (L or 1)
                    mid = (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
                    break
                run += L
        self.paths.append(self.last)
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        start_m = f' marker-start="url(#ah-{key}-s)"' if both else ""
        self.items.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{dash}'
                          f' marker-end="url(#ah-{key})"{start_m}/>')
        return mid

    def label_on_last(self, text: str, color=None, avoid: list[Box] | None = None, max_w=None,
                      order=(0.5, 0.6, 0.4, 0.7, 0.3, 0.75, 0.25, 0.8, 0.2), strict: bool = False) -> Box | None:
        """An edge label for the connector drawn last: on it, or stepped to
        one side of it, at the first place along it that clears the labels
        already placed and the boxes in ``avoid``. A long label wraps (to
        two lines, then three at a narrower width) rather than being cut;
        it never sits on a box. Only when no place is clear does it go where
        it covers least."""
        cap = max_w or 280
        tries = [(cap, 1), (cap, 2), (min(cap, 220), 3)]
        boxes = list(avoid or [])
        for width_cap, n in tries:
            lines = wrap(text, width_cap - 24, MIN_FONT)
            if len(lines) > n:
                continue
            w = max(text_width(ln, MIN_FONT) for ln in lines) + 24
            h = len(lines) * MIN_FONT * LINE + 8
            for u in order:
                x, y = self.last(u)
                x2, y2 = self.last(min(1.0, u + 0.02))
                dx, dy = x2 - x, y2 - y
                L = math.hypot(dx, dy) or 1
                nx, ny = -dy / L, dx / L
                for off in (0, 24, -24, 46, -46):
                    cx_, cy_ = x + nx * off, y + ny * off
                    bx = Box(cx_ - w / 2, cy_ - h / 2, w, h)
                    if bx.x < 0 or bx.y < 0 or bx.x + bx.w > self.w or bx.y + bx.h > self.h:
                        continue
                    if any(_hit(bx, o, 4) for o in self.labels) or any(_hit(bx, o, 2) for o in boxes):
                        continue
                    if strict and self._crosses_other(bx):
                        continue
                    return self.pill(cx_, cy_, lines, color=color, bold=False)
        if strict:
            return None
        lines = wrap(text, min(cap, 220) - 24, MIN_FONT, max_lines=3)
        w = max(text_width(ln, MIN_FONT) for ln in lines) + 24
        h = len(lines) * MIN_FONT * LINE + 8

        def clash(u):
            x, y = self.last(u)
            bx = Box(x - w / 2, y - h / 2, w, h)
            return sum(max(0.0, min(bx.x + bx.w, o.x + o.w) - max(bx.x, o.x)) *
                       max(0.0, min(bx.y + bx.h, o.y + o.h) - max(bx.y, o.y)) for o in list(self.labels) + boxes)
        best = self.last(min(order, key=clash))
        return self.pill(best[0], best[1], lines, color=color, bold=False)

    def _crosses_other(self, b: Box) -> bool:
        """Whether another connector (not the one drawn last) runs through
        the box."""
        for path in self.paths:
            if path is self.last:
                continue
            for i in range(41):
                x, y = path(i / 40)
                if b.x - 3 <= x <= b.x + b.w + 3 and b.y - 3 <= y <= b.y + b.h + 3:
                    return True
        return False

    def pill(self, cx, cy, text, color=None, fill=None, size=MIN_FONT, bold=True, max_w=None):
        """A rounded label centred on a point: status words, edge labels.
        ``text`` may be a list of lines."""
        color = color or self.t.ink
        fill = fill or self.t.paper
        lines = list(text) if isinstance(text, (list, tuple)) else [text]
        if max_w:
            lines = [ellipsize(ln, max_w - 24, size, bold) for ln in lines]
        w = max(text_width(ln, size, bold) for ln in lines) + 24
        h = len(lines) * size * LINE + 8
        r = (size * LINE + 8) / 2 if len(lines) == 1 else 12
        bx = self.rect(cx - w / 2, cy - h / 2, w, h, fill, color, r=r, sw=1.5)
        self.labels.append(bx)
        self.text(cx, cy - h / 2 + 4, lines, size, color, bold, anchor="middle", within=bx)
        return Box(cx - w / 2, cy - h / 2, w, h)

    def chip(self, x, y, text, chip: str, size=MIN_FONT, max_w=None) -> Box:
        """A status chip in words at (x, y) top-left."""
        col = self.t.chip(chip)
        if max_w:
            text = ellipsize(text, max_w - 20, size, True)
        w = text_width(text, size, True) + 20
        h = size * LINE + 6
        bx = self.rect(x, y, w, h, self.t.soft(col), col, dashed=chip in ("tbc", "not-started"), r=6, sw=1.5)
        self.text(x + 10, y + 3, [text], size, col, True, within=bx)
        return Box(x, y, w, h)

    def box(self, x, y, w, h, title: str, subs: Iterable[str] = (), fill=None, stroke=None,
            dashed=False, title_color=None, sub_color=None, title_size=MIN_FONT, align="middle",
            pad=12, bold=True, r=10) -> Box:
        """A box whose title and sub-lines are wrapped to fit inside it. Sub
        lines are dropped from the bottom, then the title cut, until the
        text fits the box's height."""
        fill = fill or self.t.paper
        stroke = stroke or self.t.rule
        self.rect(x, y, w, h, fill, stroke, dashed, r=r, sw=2 if dashed else 1.5)
        inner_w = w - 2 * pad
        inner_h = h - 2 * pad
        subs = [s for s in subs if s]
        lh_t = title_size * LINE
        lh_s = MIN_FONT * LINE
        # The title leaves a line for the first sub-line (the status, an
        # id) when the box has room for two.
        reserve = lh_s if subs and inner_h >= lh_t + lh_s else 0
        max_title = max(1, int((inner_h - reserve) // lh_t))
        t_lines = wrap(title, inner_w, title_size, bold, max_lines=max_title) if title else []
        s_lines: list[str] = []
        room = inner_h - len(t_lines) * lh_t
        for s in subs:
            avail = int(room // lh_s)
            if avail <= 0:
                break
            ln = wrap(s, inner_w, MIN_FONT, False, max_lines=avail)
            s_lines += ln
            room -= len(ln) * lh_s
        total = len(t_lines) * lh_t + len(s_lines) * lh_s
        ty = y + (h - total) / 2
        tx = x + w / 2 if align == "middle" else x + pad
        inside = Box(x, y, w, h)
        if t_lines:
            ty += self.text(tx, ty, t_lines, title_size, title_color or self.t.ink, bold, anchor=align,
                            within=inside)
        if s_lines:
            self.text(tx, ty, s_lines, MIN_FONT, sub_color or self.t.muted, False, anchor=align, within=inside)
        return Box(x, y, w, h)

    def status_box(self, x, y, w, h, title, subs, chip: str, **kw) -> Box:
        col = self.t.chip(chip)
        return self.box(x, y, w, h, title, subs, fill=self.t.soft(col, 0.9), stroke=col,
                        dashed=chip in ("tbc", "not-started"), **kw)

    def legend(self, entries: list[tuple[str, str, bool]], y: float | None = None, x: float = 0):
        """A legend row: (label, colour, dashed) swatches, left to right."""
        y = self.h - 34 if y is None else y
        cx = x
        for label, color, dashed in entries:
            self.rect(cx, y + 4, 28, 24, self.t.soft(color), color, dashed, r=5, sw=1.5)
            self.text(cx + 38, y, [label], MIN_FONT, self.t.muted)
            cx += 38 + text_width(label, MIN_FONT) + 36
        return cx

    def line_legend(self, entries: list[tuple[str, bool]], x: float, y: float | None = None):
        y = self.h - 34 if y is None else y
        cx = x
        for label, dashed in entries:
            self.line(cx, y + 16, cx + 44, y + 16, self.t.muted, 2, dashed)
            self.text(cx + 54, y, [label], MIN_FONT, self.t.muted)
            cx += 54 + text_width(label, MIN_FONT) + 36
        return cx

    def render(self, title: str) -> str:
        defs = []
        for c in sorted(self.markers):
            k = f"{self.uid}-{c.lstrip('#')}"
            defs.append(f'<marker id="ah-{k}" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="12" '
                        f'markerHeight="12" markerUnits="userSpaceOnUse" orient="auto">'
                        f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
            defs.append(f'<marker id="ah-{k}-s" viewBox="0 0 10 10" refX="0" refY="5" markerWidth="12" '
                        f'markerHeight="12" markerUnits="userSpaceOnUse" orient="auto">'
                        f'<path d="M10,0 L0,5 L10,10 z" fill="{c}"/></marker>')
        d = f"<defs>{''.join(defs)}</defs>" if defs else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
                f'height="{self.h}" role="img" aria-label="{esc(title)}" class="pic">'
                f'<title>{esc(title)}</title>{d}{"".join(self.items)}</svg>')


# ------------------------------------------------------------------ context

@dataclass
class Picture:
    """A generated picture: the SVG, its kind and the register it drew
    from, a one-line description (for notes and the alt text), and every
    text line placed, for overlap checks."""

    kind: str
    source: str
    svg: str
    description: str
    texts: list[Text] = field(default_factory=list)
    extent: float = 0.0       # how far down the picture's area the drawing reaches (0-1)
    rects: list = field(default_factory=list)   # every box drawn (Box), for callout placement

    @property
    def fingerprint(self) -> str:
        """What the picture shows, without the per-chapter marker ids: two
        chapters with the same fingerprint would show the same picture."""
        import hashlib
        return hashlib.sha1(re.sub(r"ah-[A-Za-z0-9_-]+", "ah", self.svg).encode()).hexdigest()


@dataclass
class Ctx:
    project: "Project"
    spec: dict
    theme: Theme
    chapter: "Chapter | None" = None

    @property
    def uid(self) -> str:
        """A prefix for this picture's marker ids: every picture sits in one
        HTML page, and a repeated id would point at another slide's marker."""
        n = self.chapter.number if self.chapter is not None else 0
        return f"c{n}-{self.spec['kind']}-{self.source}"

    @property
    def source(self) -> str:
        return self.spec.get("from") or DEFAULT_FROM[self.spec["kind"]]

    @property
    def by(self) -> str | None:
        by = self.spec.get("by")
        return by if isinstance(by, str) else None

    def records(self, rtype: str | None = None) -> list[Record]:
        """The register's records, narrowed to those the chapter shows when
        it cites the register only through filters (a monitoring chapter
        citing ``acceptance-item where stage=monitoring`` draws those, not
        every acceptance item)."""
        key = rtype or self.source
        reg = self.project.registers.get(key)
        if reg is None:
            return []
        wheres = chapter_filters(self.chapter, key) if self.chapter is not None else None
        if not wheres:
            return list(reg)
        keep = {r.id for w in wheres for r in reg.filter(w)}
        return [r for r in reg if r.id in keep]

    def rtype(self, rtype: str | None = None):
        reg = self.project.registers.get(rtype or self.source)
        return reg.type if reg is not None else None

    def name(self, value: Any) -> str:
        """A field value as a name: a record id becomes that record's
        title (a forum its short name)."""
        if isinstance(value, Tbc):
            return str(value)
        s = display(value)
        rec = self.project.record(s) if s else None
        if rec is not None:
            short = rec.get("short")
            return display(short) if short and not isinstance(short, Tbc) else rec.title
        return s


PLURALS: dict[str, str] = {}      # label -> the metamodel's plural, where it gives one


def use_plurals(project: "Project") -> None:
    """Take the plurals the project's metamodel gives (``plural:``), and
    only those: the table is reset for each project, so one project's
    plurals never leak into the next built in the same process."""
    PLURALS.clear()
    for t in project.metamodel.artefact_types.values():
        if getattr(t, "plural", ""):
            PLURALS[t.label.lower()] = t.plural.lower()


def chapter_filters(chapter, rtype: str) -> list | None:
    """The filters through which a chapter cites a register (its REGISTER
    blocks and its sections' metamodel artefacts), or None when it cites the
    register unfiltered or not at all."""
    from . import content as C
    wheres = []
    for sec in chapter.sections:
        for b in sec.blocks:
            if isinstance(b, C.RegisterTable) and b.type == rtype:
                if not b.where:
                    return None
                wheres.append(b.where)
        for a in sec.artefacts:
            if a.type == rtype:
                if not a.where:
                    return None
                wheres.append(a.where)
    return wheres or None


def column_label(cell: list[Record], chip: str) -> str:
    """A status column's header from the status words its records carry
    ("Planned"; "Planned · Draft"), the status family only when they are
    many."""
    words = []
    for r in cell:
        w = status_words(r)
        w = "TBC" if w.startswith("TBC") else w
        if w not in words:
            words.append(w)
    if not words:
        return CHIP_WORDS[chip]
    return " · ".join(words) if len(words) <= 2 else CHIP_WORDS[chip]


def _plural_word(w: str) -> str:
    if w.endswith("y") and not w.endswith(("ay", "ey", "oy")):
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "ch", "sh")):
        return w + "es"
    return w + "s"


def _plural(label: str, n: int) -> str:
    """A label in the number ``n`` asks for: the metamodel's plural when it
    gives one; 'deviation or exception' becomes 'deviations or exceptions';
    an uncountable label ('process readiness') counts records."""
    low = label.lower()
    if n == 1:
        return low + (" record" if low.endswith(("ness", "data", "information")) else "")
    if low in PLURALS:
        return PLURALS[low]
    if low.endswith(("ness", "data", "information")):
        return low + " records"
    if " or " in low:
        return " or ".join(_plural_word(part) for part in low.split(" or "))
    return _plural_word(low)


def count_phrase(label: str, n: int) -> str:
    return f"{n} {_plural(label, n)}"


def group_values(ctx: Ctx, records: list[Record], by: str) -> list[tuple[str, list[Record]]]:
    """Records grouped by a field, in the field's enum (or status) order,
    then any other values in first-seen order; TBC last."""
    rt = records[0].type if records else ctx.rtype()
    order: list[str] = []
    if rt is not None:
        if by == "status":
            order = list(rt.status)
        elif by in rt.fields and rt.fields[by].enum:
            order = list(rt.fields[by].enum)
    groups: dict[str, list[Record]] = {}
    for r in records:
        v = r.get(by)
        key = "tbc" if isinstance(v, Tbc) else (display(v).lower() or "unset")
        groups.setdefault(key, []).append(r)
    keys = [k for k in order if k in groups] + [k for k in groups if k not in order and k != "tbc"]
    if "tbc" in groups and "tbc" not in keys:
        keys.append("tbc")
    return [(k, groups[k]) for k in keys]


def _status_legend(svg: Svg, chips: Iterable[str], x: float = 0, y: float | None = None) -> float:
    seen = [c for c in CHIP_ORDER if c in set(chips)]
    return svg.legend([(CHIP_WORDS[c], svg.t.chip(c), c in ("tbc", "not-started")) for c in seen], y, x)


def _more(svg: Svg, x, y, w, h, n: int, noun: str) -> Box:
    return svg.box(x, y, w, h, f"+{n} more", [noun], fill=svg.t.panel, stroke=svg.t.rule, dashed=True)


# ------------------------------------------------------------------ layers

def _design_label(p: "Project") -> list[str]:
    kind = "Capability design" if p.kind == "capability" else "Solution design"
    return [f"{kind} · v{p.version}"]


def _kind_label(kind: Any, version: Any = None) -> str:
    k = "Capability design" if kind == "capability" else ("Solution design" if kind == "solution" else "Design")
    return k + (f" · v{version}" if version not in (None, "") else "")


def consumers_of(p: "Project") -> list[tuple[str, list[str]]]:
    """The designs built on this one: ``consumers:`` in arch-doc.yaml (a
    title, or {title, kind, version}), and sibling projects whose
    ``depends_on`` points at this project."""
    out: list[tuple[str, list[str]]] = []
    # A design is drawn once: one it depends on is not also a consumer, and
    # one it only cites (cites:) is never drawn.
    seen: set[str] = {str(d.get("title")) for d in p.config.get("depends_on") or [] if isinstance(d, dict)}
    for c in p.config.get("consumers") or []:
        d = c if isinstance(c, dict) else {"title": str(c)}
        if d.get("title") and d["title"] not in seen:
            seen.add(d["title"])
            out.append((d["title"], [_kind_label(d.get("kind"), d.get("version"))]))
    try:
        import yaml as _yaml
        for cfg in sorted(p.root.parent.glob("*/arch-doc.yaml")):
            if cfg.parent.resolve() == p.root.resolve():
                continue
            data = _yaml.safe_load(cfg.read_text()) or {}
            for d in data.get("depends_on") or []:
                if isinstance(d, dict) and d.get("path") and \
                        (cfg.parent / d["path"]).resolve() == p.root.resolve() and data.get("title") not in seen:
                    seen.add(data.get("title"))
                    out.append((str(data.get("title")), [_kind_label(data.get("kind"), data.get("version"))]))
    except (OSError, ValueError):
        pass
    return out


def _layers(ctx: Ctx) -> Picture | None:
    """A stack, top to bottom: what is built on the design, the design and
    its layers, what the design is built on. A solution sits over the
    platforms it uses; a capability design sits under its consumers (from
    ``consumers:`` or the sibling designs that depend on it), so it is drawn
    as the base its consumers build on."""
    p, t = ctx.project, ctx.theme
    svg = Svg(t, ctx.uid)
    src = ctx.source
    capability = p.kind == "capability"
    deps = [d for d in (p.config.get("depends_on") or []) if isinstance(d, dict) and d.get("title")]
    consumers = consumers_of(p)

    bands: list[tuple[str, list[tuple[str, list[str], str]]]] = []  # (label, [(title, subs, chip)])
    recs: list[Record] = []
    if src == "depends_on":
        if not deps and not consumers:
            # A design alone: the design over (or, a capability, under) what it is made of.
            for rtype, by in (("component", "layer"), ("application", "hosting"), ("environment", None)):
                if ctx.records(rtype):
                    pic = _layers(Ctx(p, {"kind": "layers", "from": rtype, "by": by}, t, ctx.chapter))
                    if pic is not None:
                        return pic
    else:
        recs = ctx.records()
        if not recs:
            return None
        rt = ctx.rtype()
        if ctx.by:
            for value, group in group_values(ctx, recs, ctx.by):
                bands.append((human(value) if value != "tbc" else "TBC",
                              [(r.title, [r.id], r.chip) for r in group]))
        else:
            bands.append((rt.label if rt else src, [(r.title, [r.id, _first_text(r)], r.chip) for r in recs]))

    dep_rows: list[tuple[str, list[str]]] = []

    def walk(proj: "Project", seen: set):
        for d in proj.config.get("depends_on") or []:
            if not isinstance(d, dict) or not d.get("title"):
                continue
            key = (d.get("title"), str(d.get("version")))
            if key in seen:
                continue
            seen.add(key)
            dep_rows.append((d["title"], [_kind_label(d.get("kind"), d.get("version"))]))
            dp = proj.dependencies.get(d.get("ref")) if d.get("ref") else None
            if dp is not None:
                walk(dp, seen)
    walk(p, set())

    # The design shows what it adds in the dependency stack: its own
    # applications (not those it retires or only uses today).
    own: list[Record] = []
    if src == "depends_on" and (dep_rows or consumers):
        own = [a for a in ctx.records("application")
               if display(a.get("change")).lower() != "retired" and display(a.get("state")).lower() != "current"]

    # The stack, top to bottom, with each layer's share of the height.
    layers: list[tuple[str, Any, float]] = []
    if consumers:
        layers.append(("consumers", consumers, 1.0))
    design = ("design", None, 2.2 if own else 1.0)
    if capability:
        layers += [("band", b, 1.3) for b in bands] + [design]
    else:
        layers += [design] + [("band", b, 1.3) for b in bands]
    if dep_rows:
        layers.append(("deps", dep_rows, 1.0))
    legend_h = 44 if (bands or own) else 0
    gap = 28
    avail = H - legend_h - gap * (len(layers) - 1)
    unit = avail / sum(w for _, _, w in layers)
    caps = {"consumers": 130, "design": 280 if own else 150, "band": 200, "deps": 130}
    heights = [min(caps[k], unit * w) for k, _, w in layers]
    y = max(0.0, (H - legend_h - sum(heights) - gap * (len(layers) - 1)) / 2)
    label_w = 240
    chips_seen: set[str] = set()
    stack: list[Box] = []
    for (kind, data, _), h in zip(layers, heights):
        if kind in ("consumers", "deps"):
            n = len(data)
            dw = (W - 24 * (n - 1)) / n
            for i, (title, subs) in enumerate(data):
                fill, stroke = (t.paper, t.rule) if kind == "consumers" else (t.accent_soft, t.accent)
                svg.box(i * (dw + 24), y, dw, h, title, subs, fill=fill, stroke=stroke, title_size=28)
        elif kind == "design":
            if own:
                top = svg.rect(0, y, W, h, t.accent, t.accent, r=12)
                svg.text(28, y + 20, [ellipsize(p.title, W / 2, 28, True)], 28, t.paper, True, within=top)
                svg.text(W - 28, y + 24, [_design_label(p)[0]], MIN_FONT, t.accent_soft, anchor="end", within=top)
                n = len(own)
                per = min(n, 5)
                shown = own[:per] if n <= per else own[:per - 1]
                gapx = 20
                bw = (W - 56 - gapx * (per - 1)) / per
                by = y + 20 + 28 * LINE + 20
                bh = h - (by - y) - 24
                for i, a in enumerate(shown):
                    chips_seen.add(a.chip)
                    # The colour is the status (the legend says so); the line under
                    # the name says the status in words, then what changes.
                    change = display(a.get("change")).lower()
                    sub = status_words(a) + (f" · {change}" if change else "")
                    svg.status_box(28 + i * (bw + gapx), by, bw, bh, a.title, [sub], a.chip)
                if len(shown) < n:
                    _more(svg, 28 + len(shown) * (bw + gapx), by, bw, bh, n - len(shown), "applications")
            else:
                svg.box(0, y, W, h, p.title, _design_label(p), fill=t.accent, stroke=t.accent,
                        title_color=t.paper, sub_color=t.accent_soft, title_size=28)
        else:
            label, items = data
            svg.rect(0, y, W, h, t.panel, t.rule, r=12)
            svg.text(20, y + h / 2 - MIN_FONT * LINE / 2, wrap(label, label_w - 40, MIN_FONT, caps=True,
                                                               max_lines=1), MIN_FONT, t.muted, caps=True)
            x0, x1 = label_w, W - 16
            n = len(items)
            gapx = 16
            max_cols = max(1, int((x1 - x0 + gapx) // (180 + gapx)))
            rows_in = 1 if n <= max_cols else 2
            per_row = math.ceil(n / rows_in) if n <= max_cols * 2 else max_cols
            shown = items if n <= per_row * rows_in else items[:per_row * rows_in - 1]
            bw = min(360, (x1 - x0 - gapx * (per_row - 1)) / per_row)
            bh = (h - 24 - 12 * (rows_in - 1)) / rows_in
            for i, (title, subs, chip) in enumerate(shown):
                r_, c_ = divmod(i, per_row)
                chips_seen.add(chip)
                svg.status_box(x0 + c_ * (bw + gapx), y + 12 + r_ * (bh + 12), bw, bh, title, subs, chip)
            if len(shown) < n:
                i = len(shown)
                r_, c_ = divmod(i, per_row)
                _more(svg, x0 + c_ * (bw + gapx), y + 12 + r_ * (bh + 12), bw, bh, n - len(shown),
                      "in the register")
        stack.append(Box(0, y, W, h))
        y += h + gap
    # Connectors: "builds on", in the gap between each layer and the next.
    for xs in (label_w / 2, W / 2):
        for a, b in zip(stack, stack[1:]):
            svg.arrow(Box(xs - 1, a.y, 2, a.h), Box(xs - 1, b.y, 2, b.h), color=t.accent)
    if chips_seen:
        _status_legend(svg, chips_seen)
    if src == "depends_on":
        parts = []
        if consumers:
            parts.append("under the designs built on it: " + ", ".join(c[0] for c in consumers))
        if dep_rows:
            parts.append("over the designs it depends on: " + ", ".join(r[0] for r in dep_rows))
        desc = f"{p.title} " + ("; ".join(parts) if parts else "alone: it depends on no other design")
    else:
        rt = ctx.rtype()
        by = f" by {ctx.by}" if ctx.by else ""
        desc = f"the {count_phrase(rt.label if rt else src, len(recs))}{by}, as layers"
        if capability and consumers:
            desc += ", under " + ", ".join(c[0] for c in consumers)
        if dep_rows:
            desc += ", on " + ", ".join(r[0] for r in dep_rows)
    return Picture("layers", src, svg.render(desc), desc, svg.texts)


def _first_text(r: Record) -> str:
    for name, spec in r.type.fields.items():
        if spec.kind == "text" and name != "owner":
            v = r.get(name)
            if v and not isinstance(v, Tbc):
                return display(v)
    return ""


# ---------------------------------------------------------------- timeline

def _date_field(rt) -> str | None:
    if rt is None:
        return None
    for name, spec in rt.fields.items():
        if spec.kind == "date":
            return name
    return None


def _timeline(ctx: Ctx) -> Picture | None:
    recs = ctx.records()
    if not recs:
        return None
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    rt = ctx.rtype()
    df = _date_field(rt)
    stage = "stage" if rt and "stage" in rt.fields and rt.fields["stage"].enum else None

    def key(ir):
        i, r = ir
        d = r.get(df) if df else None
        ds = display(d) if d and not isinstance(d, Tbc) else ""
        sv = display(r.get(stage)).lower() if stage else ""
        st = rt.fields[stage].enum.index(sv) if stage and sv in rt.fields[stage].enum else 99
        return (0 if ds else 1, ds, st, i)
    ordered = [r for _, r in sorted(enumerate(recs), key=key)]
    max_items = 10
    shown = ordered[:max_items]
    extra = len(ordered) - len(shown)
    n = len(shown)
    legend_h = 48
    avail = H - legend_h
    slot = W / max(n, 1)
    alternate = n > 5
    bw = min(400, slot * (2 if alternate else 1) - 24)
    inner = bw - 28
    lh = MIN_FONT * LINE
    chip_h = MIN_FONT * LINE + 6

    items = []
    for r in shown:
        when = ""
        if df and r.get(df) and not isinstance(r.get(df), Tbc):
            when = display(r.get(df))
        elif "timing" in r.type.fields and r.get("timing"):
            when = display(r.get("timing"))
        elif stage and r.get(stage):
            when = human(r.get(stage))
        subs = []
        for f in ("forum", "replacement"):
            if f in r.type.fields and r.get(f) not in (None, ""):
                v = ctx.name(r.get(f))
                subs.append(f"Forum: {v}" if f == "forum" else f"Replaced by {v}")
        # What else the record says, for cards with room: its owner and
        # its first descriptive field.
        # The rest of what the record says, as labelled lines, for cards
        # with the room: every text, date and choice field not shown yet.
        said = {"forum", "replacement", "timing", stage or "", df or ""}
        facts_ = []
        for f, spec_ in r.type.fields.items():
            v = r.get(f)
            if f in said or v in (None, "", []) or spec_.kind in ("ref", "refs"):
                continue
            facts_.append(f"{r.type.header(f)}: {r.shown(f) if hasattr(r, 'shown') else display(v)}")
        items.append((r, wrap(when or r.id, inner, MIN_FONT, True, 1), wrap(r.title, inner, MIN_FONT, True, 3),
                      [ln for s in subs + facts_ for ln in wrap(s, inner, MIN_FONT, max_lines=3)]))
    # Every box takes the height of the tallest, so the row reads as one.
    need = max(14 + lh * (len(w) + len(tl) + len(sb)) + 10 + chip_h + 14 for _, w, tl, sb in items)
    reach = 36                                   # from the axis to a box
    # The cards take the height there is: below the axis (or both sides of
    # it), down to the legend.
    if alternate:
        bh = avail / 2 - reach - 4
        axis_y = avail / 2
    else:
        axis_y = 40
        bh = avail - axis_y - reach - 8
    svg.line(0, axis_y, W - 14, axis_y, t.rule, 4)
    svg.items.append(f'<path d="M{W - 16},{axis_y - 10} L{W},{axis_y} L{W - 16},{axis_y + 10} z" fill="{t.rule}"/>')
    chips = set()
    for i, (r, when, title, subs) in enumerate(items):
        cx = slot * i + slot / 2
        up = alternate and i % 2 == 0
        by = axis_y - reach - bh if up else axis_y + reach
        bx = min(max(cx - bw / 2, 0), W - bw)
        col = t.chip(r.chip)
        chips.add(r.chip)
        svg.line(cx, axis_y + (-12 if up else 12), cx, by + (bh if up else 0), col, 2)
        svg.circle(cx, axis_y, 12, t.soft(col, 0.6), col)
        box = svg.rect(bx, by, bw, bh, t.paper, col, dashed=r.chip in ("tbc", "not-started"), sw=2)
        chip_y = by + bh - 14 - chip_h
        room = int((chip_y - 10 - by - 14) // lh)
        lines = [("w", ln) for ln in when] + [("t", ln) for ln in title] + [("s", ln) for ln in subs]
        lines = lines[:max(room, 1)]
        yy = by + 14
        for kind_, ln in lines:
            color = t.accent if kind_ == "w" else (t.ink if kind_ == "t" else t.muted)
            yy += svg.text(bx + 14, yy, [ln], MIN_FONT, color, kind_ != "s", within=box)
        word = status_words(r)
        svg.chip(bx + 14, chip_y, word, r.chip, max_w=inner)
    _status_legend(svg, chips, 0, H - 34)
    if extra:
        svg.text(W, H - 34, [f"+{extra} more in the register"], MIN_FONT, t.muted, anchor="end")
    label = rt.label if rt else ctx.source
    desc = f"the {count_phrase(label, len(recs))} in order" + (" of date" if df else "")
    return Picture("timeline", ctx.source, svg.render(desc), desc, svg.texts)


# ------------------------------------------------------------ traceability

def _traceability(ctx: Ctx) -> Picture | None:
    frs = ctx.records("functional-requirement") if ctx.source == "functional-requirement" else ctx.records()
    if not frs:
        return None
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    p = ctx.project
    brs = ctx.records("business-requirement")
    traced = {display(x) for r in frs for x in as_list(r.get("traces_to"))}
    brs = [b for b in brs if b.id in traced] or brs
    sats: list[str] = []
    for r in frs:
        for s in as_list(r.get("satisfied_by")):
            name = ctx.name(s)
            if name and name not in sats:
                sats.append(name)
    cols = [("Business requirements", brs), ("Functional requirements", frs), ("Satisfied by", sats)]
    cols = [c for c in cols if c[1]]
    nc = len(cols)
    gapx = 140
    cw = (W - gapx * (nc - 1)) / nc
    head_h = 44
    legend_h = 44
    area = H - head_h - legend_h
    boxes: dict[tuple[int, str], Box] = {}
    for ci, (head, items) in enumerate(cols):
        x = ci * (cw + gapx)
        svg.text(x, 0, [head], MIN_FONT, t.muted, caps=True)
        n = len(items)
        max_rows = max(1, int((area + 12) // (72 + 12)))
        shown = items[:max_rows] if n <= max_rows else items[:max_rows - 1]
        bh = min(110, (area - 12 * (max(len(shown), 1) - 1) - (0 if len(shown) == n else 84)) / max(len(shown), 1))
        bh = max(bh, 60)
        y = head_h
        for it in shown:
            if isinstance(it, Record):
                b = svg.status_box(x, y, cw, bh, f"{it.id} {it.title}", [], it.chip, align="start",
                                   title_size=MIN_FONT, bold=False, pad=10)
                boxes[(ci, it.id)] = b
            else:
                b = svg.box(x, y, cw, bh, it, [], fill=t.accent_soft, stroke=t.accent, align="start", bold=False,
                            pad=10)
                boxes[(ci, it)] = b
            y += bh + 12
        if len(shown) < n:
            _more(svg, x, y, cw, 72, n - len(shown), "")
    # edges
    ci_fr = next(i for i, c in enumerate(cols) if c[0] == "Functional requirements")
    edges = 0
    for r in frs:
        fb = boxes.get((ci_fr, r.id))
        if fb is None:
            continue
        if ci_fr > 0:
            for bid in as_list(r.get("traces_to")):
                bb = boxes.get((ci_fr - 1, display(bid)))
                if bb is not None:
                    svg.arrow(bb, fb, color=t.accent, curve=True)
                    edges += 1
        if ci_fr + 1 < nc:
            for s in as_list(r.get("satisfied_by")):
                sb = boxes.get((ci_fr + 1, ctx.name(s)))
                if sb is not None:
                    svg.arrow(fb, sb, color=t.muted, curve=True)
                    edges += 1
    lx = _status_legend(svg, {r.chip for r in frs} | {b.chip for b in brs}, 0, H - 34)
    svg.line_legend([("realised by", False)], lx + 20, H - 34)
    desc = (f"{count_phrase('business requirement', len(brs))} traced to "
            f"{count_phrase('functional requirement', len(frs))}"
            + (f" and the {len(sats)} parts that satisfy them" if sats else ""))
    return Picture("traceability", ctx.source, svg.render(desc), desc, svg.texts)


# ----------------------------------------------------------------- heatmap

LEVELS = ("low", "medium", "high")
RATING_ORDER = {"extreme": 0, "high": 1, "medium": 2, "low": 3}


def _heatmap(ctx: Ctx) -> Picture | None:
    risks = ctx.records()
    if not risks:
        return None
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    axis_w, axis_h = 96, 70
    grid_w, grid_h = 1000, H - axis_h - 44
    cw, ch = (grid_w - axis_w) / 3, grid_h / 3
    # The across axis is impact; a register that rates risks without an
    # impact is placed by its rating instead (extreme counts as high).
    def level(v: str) -> str:
        return "high" if v == "extreme" else v
    has_impact = any(display(r.get("impact")).lower() in LEVELS for r in risks)
    has_rating = any(level(display(r.get("rating")).lower()) in LEVELS for r in risks)
    across = "impact" if has_impact else ("rating" if has_rating else None)
    if across is None or not any(display(r.get("likelihood")).lower() in LEVELS for r in risks):
        return None
    placed: dict[tuple[int, int], list[Record]] = {}
    unrated = []
    for r in risks:
        lk, im = display(r.get("likelihood")).lower(), level(display(r.get(across)).lower())
        if lk in LEVELS and im in LEVELS:
            placed.setdefault((LEVELS.index(lk), LEVELS.index(im)), []).append(r)
        else:
            unrated.append(r)
    exposure = {0: ("Low exposure", t.done), 1: ("Medium exposure", t.partial), 2: ("High exposure", t.tbc)}
    for li in range(3):
        for ii in range(3):
            score = (li + 1) * (ii + 1)
            band = 0 if score <= 2 else (1 if score <= 4 else 2)
            x = axis_w + ii * cw
            y = (2 - li) * ch
            svg.rect(x + 4, y + 4, cw - 8, ch - 8, t.soft(exposure[band][1], 0.82), t.rule, r=10)
            cell = placed.get((li, ii), [])
            cx, cy = x + 18, y + 18
            for r in cell:
                label = r.id
                w = text_width(label, MIN_FONT, True) + 20
                if cx + w > x + cw - 14:
                    cx, cy = x + 18, cy + 44
                if cy + 38 > y + ch - 10:
                    svg.text(x + cw - 18, y + ch - 44, ["+more"], MIN_FONT, t.ink, anchor="end")
                    break
                svg.chip(cx, cy, label, r.chip)
                cx += w + 10
    # axes
    for i, lv in enumerate(LEVELS):
        svg.text(axis_w + i * cw + cw / 2, grid_h + 10, [lv.capitalize()], MIN_FONT, t.muted, anchor="middle")
    svg.text(axis_w + (grid_w - axis_w) / 2, grid_h + 40, [across.capitalize()], MIN_FONT, t.ink, True, anchor="middle")
    for i, lv in enumerate(LEVELS):
        y = (2 - i) * ch + ch / 2
        svg.items.append(f'<text font-family="{esc(t.body_stack)}" font-size="{MIN_FONT}" fill="{t.muted}" '
                         f'text-anchor="middle" transform="translate({axis_w - 30},{y:.1f}) rotate(-90)">'
                         f'<tspan x="0" y="8">{esc(lv.capitalize())}</tspan></text>')
    svg.items.append(f'<text font-family="{esc(t.body_stack)}" font-size="{MIN_FONT}" font-weight="600" '
                     f'fill="{t.ink}" text-anchor="middle" transform="translate(20,{grid_h / 2:.1f}) rotate(-90)">'
                     f'<tspan x="0" y="8">Likelihood</tspan></text>')
    # The highest-rated risks, named.
    px = grid_w + 48
    pw = W - px
    svg.text(px, 0, ["Highest rated"], MIN_FONT, t.muted, caps=True)
    ranked = sorted(risks, key=lambda r: (RATING_ORDER.get(display(r.get("rating")).lower(), 4),
                                          CHIP_ORDER.index(r.chip) if r.chip in CHIP_ORDER else 9))
    y = 44
    row_h = 2 * MIN_FONT * LINE + 18
    room = grid_h + 44 - y - (52 if unrated else 0)
    max_rows = int(room // (row_h + 10))
    for r in ranked[:max_rows]:
        rating = human(r.get("rating")) or "Unrated"
        svg.rect(px, y, pw, row_h, t.paper, t.rule, r=8)
        svg.text(px + 14, y + 8, [ellipsize(f"{r.id} · {r.title}", pw - 28, MIN_FONT, True)], MIN_FONT, t.ink, True)
        owner = r.owner or (str(r.get("owner")) if r.get("owner") else "no owner")
        status = status_words(r)
        svg.text(px + 14, y + 8 + MIN_FONT * LINE,
                 [ellipsize(f"{rating} · {status} · {owner}", pw - 28, MIN_FONT)], MIN_FONT, t.muted)
        y += row_h + 10
    if unrated:
        svg.text(px, grid_h + 44 - 40, [ellipsize("Not rated: " + ", ".join(r.id for r in unrated), pw, MIN_FONT)],
                 MIN_FONT, t.tbc, True)
    svg.legend([(exposure[i][0], exposure[i][1], False) for i in range(3)], H - 34, axis_w)
    desc = f"the {count_phrase('risk', len(risks))} placed by likelihood and {across}"
    return Picture("heatmap", ctx.source, svg.render(desc), desc, svg.texts)


# ------------------------------------------------------------------ matrix

def _matrix(ctx: Ctx) -> Picture | None:
    recs = ctx.records()
    if not recs:
        return None
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    rt = ctx.rtype()
    if not ctx.by:
        return _status_board(ctx, recs, svg)
    groups = group_values(ctx, recs, ctx.by)
    cols = [c for c in CHIP_ORDER if any(r.chip == c for r in recs)] or list(CHIP_ORDER[:3])
    label_w = 320
    head_h = 56
    legend_h = 0
    cw = (W - label_w) / len(cols)
    max_rows = int((H - head_h) // 60)          # a row needs its label and one line of chips
    shown = groups[:max_rows]
    rest = groups[max_rows:]
    area = H - head_h - (40 if rest else 0)
    rh = min(220, area / max(len(shown), 1))          # the rows share the whole height
    for ci, c in enumerate(cols):
        x = label_w + ci * cw
        col = t.chip(c)
        svg.rect(x + 4, 0, cw - 8, head_h - 12, t.soft(col), col, dashed=c in ("tbc", "not-started"), r=8)
        svg.text(x + cw / 2, 8, [ellipsize(column_label([r for r in recs if r.chip == c], c), cw - 24, MIN_FONT, True)],
                 MIN_FONT, col, True, anchor="middle")
    for gi, (value, items) in enumerate(shown):
        y = head_h + gi * rh
        svg.rect(0, y + 4, W, rh - 8, t.panel if gi % 2 == 0 else t.paper, t.rule, r=8)
        label = human(value) if value != "tbc" else "TBC"
        room = int((rh - 8 - 24) // (MIN_FONT * LINE))
        lines = wrap(label, label_w - 32, MIN_FONT, True, max_lines=max(1, min(2, room)))
        row_box = Box(0, y + 4, label_w, rh - 8)
        svg.text(16, y + 12, lines, MIN_FONT, t.ink, True, within=row_box)
        if room > len(lines):
            svg.text(16, y + 12 + len(lines) * MIN_FONT * LINE, [count_phrase("item", len(items))], MIN_FONT,
                     t.muted, within=row_box)
        for ci, c in enumerate(cols):
            cell = [r for r in items if r.chip == c]
            x = label_w + ci * cw + 14
            cx, cy = x, y + 14
            limit_x = label_w + (ci + 1) * cw - 14
            show_title = len(cell) == 1 and rh >= 90
            per_line = int((rh - 24) // (MIN_FONT * LINE))
            if len(cell) > 1 and len(cell) <= per_line:
                # Room for a line each: the id in its status colour, then the title.
                cell_box = Box(label_w + ci * cw, y + 4, cw, rh - 8)
                for k, r in enumerate(cell):
                    ly = cy + k * MIN_FONT * LINE
                    iw = text_width(r.id, MIN_FONT, True) + 10
                    svg.text(cx, ly, [r.id], MIN_FONT, t.chip(c), True, within=cell_box)
                    svg.text(cx + iw, ly, [ellipsize(r.title, limit_x - cx - iw, MIN_FONT)], MIN_FONT, t.ink,
                             within=cell_box)
                continue
            for k, r in enumerate(cell):
                if show_title:
                    yy = cy
                    yy += svg.text(cx, yy, [r.id], MIN_FONT, t.chip(c), True)
                    svg.text(cx, yy, wrap(r.title, limit_x - cx, MIN_FONT, max_lines=int((rh - 50) // 30) or 1),
                             MIN_FONT, t.ink)
                    break
                w = text_width(r.id, MIN_FONT, True) + 20
                if cx + w > limit_x:
                    cx, cy = x, cy + 42
                if cy + 36 > y + rh - 8:
                    remaining = len(cell) - k
                    svg.text(limit_x, y + rh - 44, [f"+{remaining}"], MIN_FONT, t.ink, True, anchor="end")
                    break
                svg.chip(cx, cy, r.id, c)
                cx += w + 10
    if rest:
        svg.text(0, H - 34, [f"+{len(rest)} more groups: " + ", ".join(human(v) for v, _ in rest)], MIN_FONT, t.muted)
    label = rt.label if rt else ctx.source
    by = f" by {ctx.by}" if ctx.by else ""
    desc = f"the {count_phrase(label, len(recs))}{by} against their status"
    return Picture("matrix", ctx.source, svg.render(desc), desc, svg.texts)


def _status_board(ctx: Ctx, recs: list[Record], svg: Svg) -> Picture:
    """A matrix with no grouping field: one row per record (id and title),
    and a box in its status column with the status in words and the owner."""
    t = ctx.theme
    rt = ctx.rtype()
    cols = [c for c in CHIP_ORDER if any(r.chip == c for r in recs)] or list(CHIP_ORDER[:3])
    label_w = 640 if len(cols) <= 3 else 560
    head_h = 56
    cw = (W - label_w) / len(cols)
    max_rows = int((H - head_h) // 52)
    shown = recs if len(recs) <= max_rows else recs[:max_rows - 1]
    # Rows stay compact, leaving room under the board for callouts.
    rh = min(110, (H - head_h) / max(1, len(shown) + (len(shown) < len(recs))))
    for ci, c in enumerate(cols):
        x = label_w + ci * cw
        col = t.chip(c)
        svg.rect(x + 4, 0, cw - 8, head_h - 12, t.soft(col), col, dashed=c in ("tbc", "not-started"), r=8)
        svg.text(x + cw / 2, 8, [ellipsize(column_label([r for r in recs if r.chip == c], c), cw - 24, MIN_FONT, True)],
                 MIN_FONT, col, True, anchor="middle")
    for k, r in enumerate(shown):
        y = head_h + k * rh
        row = svg.rect(0, y + 3, W, rh - 6, t.panel if k % 2 == 0 else t.paper, t.rule, r=8)
        two = r.owner and rh >= 2 * MIN_FONT * LINE + 8
        lines = [ellipsize(f"{r.id} {r.title}", label_w - 32, MIN_FONT)] if two else \
            wrap(f"{r.id} {r.title}", label_w - 32, MIN_FONT, max_lines=max(1, int((rh - 12) // 30)))
        ty = y + (rh - (len(lines) + (1 if two else 0)) * MIN_FONT * LINE) / 2
        svg.text(16, ty, lines, MIN_FONT, t.ink, within=row)
        if two:
            svg.text(16, ty + MIN_FONT * LINE, [ellipsize(r.owner, label_w - 32, MIN_FONT)], MIN_FONT, t.muted,
                     within=row)
        ci = cols.index(r.chip) if r.chip in cols else 0
        svg.status_box(label_w + ci * cw + 8, y + 8, cw - 16, rh - 16, status_words(r), [], r.chip, pad=6)
    if len(shown) < len(recs):
        svg.text(16, head_h + len(shown) * rh + 8, [f"+{len(recs) - len(shown)} more in the register"],
                 MIN_FONT, t.muted)
    label = rt.label if rt else ctx.source
    desc = f"each of the {count_phrase(label, len(recs))} against its status"
    return Picture("matrix", ctx.source, svg.render(desc), desc, svg.texts)


# ---------------------------------------------------------------- swimlane

def _swimlane(ctx: Ctx) -> Picture | None:
    recs = ctx.records()
    if not recs:
        return None
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    rt = ctx.rtype()
    lane_field = "process" if rt and "process" in rt.fields else (ctx.by or None)
    lanes = group_values(ctx, recs, lane_field) if lane_field else [(r.title, [r]) for r in recs]
    rows: list[tuple[str, Record]] = [(v, r) for v, rs in lanes for r in rs]
    max_lanes = 7
    shown = rows[:max_lanes]
    rest = len(rows) - len(shown)
    legend_h = 44
    head_h = 40
    lane_h = min(130, (H - head_h - legend_h - (0 if not rest else 0)) / max(len(shown), 1))
    label_w = 300
    steps = ["Process design", "Evidence", "Readiness"]
    gapx = 56
    room = W - label_w - 16 - gapx * (len(steps) - 1)
    widths = [room * 0.44, room * 0.34, room * 0.22]
    xs = [label_w + 16]
    for w_ in widths[:-1]:
        xs.append(xs[-1] + w_ + gapx)
    for si, s_ in enumerate(steps):
        svg.text(xs[si], 0, [s_], MIN_FONT, t.muted, caps=True)
    chips = set()
    for li, (value, r) in enumerate(shown):
        y = head_h + li * lane_h
        svg.rect(0, y + 3, W, lane_h - 6, t.panel if li % 2 == 0 else t.paper, t.rule, r=8)
        title = human(value) if lane_field else r.title
        owner = r.owner or ""
        svg.box(8, y + 8, label_w - 16, lane_h - 16, title, [owner] if owner else [], fill="none", stroke="none",
                align="start", pad=8)
        bh = lane_h - 22
        prev = None
        for si in range(3):
            bx, by = xs[si], y + 11
            if si < 2:
                raw = r.get("design" if si == 0 else "evidence")
                missing = raw in (None, "")
                tb = isinstance(raw, Tbc) or missing
                text = (str(raw) if isinstance(raw, Tbc) else display(raw)) if not missing else (
                    "Not described" if si == 0 else "No evidence yet")
                b = svg.box(bx, by, widths[si], bh, "", [text], fill=t.paper, stroke=t.tbc if tb else t.rule,
                            dashed=tb, align="start", sub_color=t.tbc if tb else t.ink, pad=10)
            else:
                chips.add(r.chip)
                b = svg.status_box(bx, by, widths[si], bh, status_words(r), [], r.chip)
            if prev is not None:
                svg.arrow(prev, b, color=t.muted)
            prev = b
    lx = _status_legend(svg, chips, 0, H - 34)
    if rest:
        svg.text(W, H - 34, [f"+{rest} more in the register"], MIN_FONT, t.muted, anchor="end")
    desc = f"one lane per {lane_field or 'record'}: how each is designed, the evidence, and whether it is ready"
    return Picture("swimlane", ctx.source, svg.render(desc), desc, svg.texts)


# -------------------------------------------------------------------- flow

def _flow(ctx: Ctx) -> Picture | None:
    recs = ctx.records()
    if not recs:
        return None
    rt = ctx.rtype()
    if rt is not None and "source" in rt.fields and "target" in rt.fields:
        return _flow_graph(ctx, recs)
    return _flow_sequence(ctx, recs)


def _flow_sequence(ctx: Ctx, recs: list[Record]) -> Picture:
    t = ctx.theme
    svg = Svg(t, ctx.uid)

    def order(ir):
        i, r = ir
        o = r.get("order")
        return (o if isinstance(o, (int, float)) and not isinstance(o, bool) else 10 ** 6, i)
    steps = [r for _, r in sorted(enumerate(recs), key=order)]
    per_row = 5
    max_rows = 3
    cap = per_row * max_rows
    shown = steps[:cap] if len(steps) <= cap else steps[:cap - 1]
    rows = math.ceil(len(shown) / per_row) if len(shown) < len(steps) or True else 1
    if len(shown) < len(steps):
        rows = max_rows
    legend_h = 44
    gapx, gapy = 72, 56
    bw = (W - gapx * (per_row - 1)) / per_row
    bh = min(190, (H - legend_h - gapy * (rows - 1)) / rows)
    total_h = rows * bh + gapy * (rows - 1)
    oy = (H - legend_h - total_h) / 2
    boxes: dict[str, Box] = {}
    chips = set()
    rollback = False
    seq: list[Box] = []
    for i, r in enumerate(shown):
        rr, cc = divmod(i, per_row)
        if rr % 2 == 1:
            cc = per_row - 1 - cc  # snake, so each row continues where the last ended
        x = cc * (bw + gapx)
        y = oy + rr * (bh + gapy)
        subs = []
        if r.owner:
            subs.append(r.owner)
        when = " to ".join(display(r.get(f)) for f in ("start", "finish") if r.get(f) not in (None, ""))
        if when:
            subs.append(when)
        chips.add(r.chip)
        b = svg.status_box(x, y, bw, bh, f"{r.id} {r.title}", subs, r.chip)
        if display(r.get("rollback_point")).lower() == "yes":
            rollback = True
            svg.pill(x + bw - 16 - text_width("Rollback point", MIN_FONT, True) / 2 - 12, y, "Rollback point",
                     color=t.accent, fill=t.accent_soft)
        boxes[r.id] = b
        seq.append(b)
    if len(shown) < len(steps):
        i = len(shown)
        rr, cc = divmod(i, per_row)
        if rr % 2 == 1:
            cc = per_row - 1 - cc
        _more(svg, cc * (bw + gapx), oy + rr * (bh + gapy), bw, bh, len(steps) - len(shown), "steps")
    has_after = any(as_list(r.get("after")) for r in shown)
    drawn = 0
    if has_after:
        for r in shown:
            for a in as_list(r.get("after")):
                src = boxes.get(display(a))
                if src is not None:
                    svg.arrow(src, boxes[r.id], color=t.ink)
                    drawn += 1
    else:
        for a, b in zip(seq, seq[1:]):
            svg.arrow(a, b, color=t.ink)
            drawn += 1
    lx = _status_legend(svg, chips, 0, H - 34)
    rt = ctx.rtype()
    desc = f"the {count_phrase(rt.label if rt else 'step', len(steps))} in order"
    if rollback:
        desc += ", with the rollback points marked"
    return Picture("flow", ctx.source, svg.render(desc), desc, svg.texts)


def _flow_graph(ctx: Ctx, recs: list[Record]) -> Picture:
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    nodes: list[str] = []
    edges: list[tuple[str, str, Record]] = []
    for r in recs:
        s, d = ctx.name(r.get("source")), ctx.name(r.get("target"))
        if not s or not d:
            continue
        for n in (s, d):
            if n not in nodes:
                nodes.append(n)
        edges.append((s, d, r))
    if not edges:
        return _flow_sequence(ctx, recs)
    # Rank each node by its longest path from a source, after dropping the
    # edges that close a cycle (found by a depth-first walk from the sources).
    out_edges: dict[str, list[str]] = {n: [] for n in nodes}
    incoming = {n: 0 for n in nodes}
    for s_, d_, _r in edges:
        out_edges[s_].append(d_)
        incoming[d_] += 1
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()

    def walk(u: str) -> None:
        state[u] = 1
        for v in out_edges[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif not state.get(v):
                walk(v)
        state[u] = 2
    for n in sorted(nodes, key=lambda n: (incoming[n] > 0, nodes.index(n))):
        if not state.get(n):
            walk(n)
    rank = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for s_, d_, _r in edges:
            if (s_, d_) not in back and rank[d_] < rank[s_] + 1:
                rank[d_] = rank[s_] + 1
                changed = True
        if not changed:
            break
    ranks = sorted(set(rank.values()))
    remap = {r: i for i, r in enumerate(ranks)}
    cols: dict[int, list[str]] = {}
    for n in nodes:
        cols.setdefault(remap[rank[n]], []).append(n)
    nc = len(cols)
    # Order each column by where its neighbours sit (barycentre sweeps), so
    # few connectors cross.
    pos = {n: i for ci in cols for i, n in enumerate(cols[ci])}
    col_of_ = {n: ci for ci in cols for n in cols[ci]}
    for sweep in range(6):
        rng = range(1, nc) if sweep % 2 == 0 else range(nc - 2, -1, -1)
        for ci in rng:
            def bary(n):
                nb = [pos[o] for s_, d_, _r in edges for o, me in ((s_, d_), (d_, s_))
                      if me == n and col_of_[o] == (ci - 1 if sweep % 2 == 0 else ci + 1)]
                return sum(nb) / len(nb) if nb else pos[n]
            cols[ci].sort(key=lambda n: (bary(n), pos[n]))
            for i, n in enumerate(cols[ci]):
                pos[n] = i
    legend_h = 44
    col_of = {n: ci for ci in range(nc) for n in cols[ci]}

    def label_of(r: Record) -> str:
        return ctx.name(r.get("data")) if r.get("data") else r.title
    # Each gap between columns is as wide as the longest label that crosses it.
    gaps = []
    for ci in range(nc - 1):
        crossing = [label_of(r) for s_, d_, r in edges
                    if min(col_of[s_], col_of[d_]) <= ci < max(col_of[s_], col_of[d_])]
        want = max([text_width(c, MIN_FONT) + 24 for c in crossing] or [120]) + 48
        gaps.append(min(max(want, 160), 420))
    bw = min(320, (W - sum(gaps)) / nc) if nc else W
    if bw < 200 and gaps:
        k = (W - 200 * nc) / sum(gaps)
        gaps = [g * k for g in gaps]
        bw = 200
    xs = [0.0]
    for g in gaps:
        xs.append(xs[-1] + bw + g)
    spare = W - (xs[-1] + bw)
    xs = [x + spare * i / max(1, nc - 1) for i, x in enumerate(xs)] if nc > 1 else [(W - bw) / 2]
    boxes: dict[str, Box] = {}
    for ci in range(nc):
        col = cols[ci]
        m = len(col)
        bh = min(120, (H - legend_h - 24 * (m - 1)) / m)
        total = m * bh + 24 * (m - 1)
        y0 = (H - legend_h - total) / 2
        x = xs[ci]
        for k, n in enumerate(col):
            boxes[n] = svg.box(x, y0 + k * (bh + 24), bw, bh, n, [], fill=t.accent_soft, stroke=t.accent, pad=8)
    chips = set()
    labels = []
    pairs: dict[tuple[str, str], list[int]] = {}
    for k, (s, d, r) in enumerate(edges):
        pairs.setdefault(tuple(sorted((s, d))), []).append(k)
    for k, (s, d, r) in enumerate(edges):
        a, b = boxes[s], boxes[d]
        col = t.chip(r.chip)
        chips.add(r.chip)
        group = pairs[tuple(sorted((s, d)))]
        off = 0.0
        if len(group) > 1:
            # Several flows between one pair: parallel lines, labels outside them.
            i = group.index(k)
            off = (i - (len(group) - 1) / 2) * 46
            if (s, d) != tuple(sorted((s, d))):
                off = -off
        svg.arrow(a, b, color=col, dashed=r.chip in ("tbc", "not-started"), offset=off)
        labels.append((svg.last, label_of(r), col))
    for along, text, col in labels:
        svg.last = along
        svg.label_on_last(text, color=col, avoid=list(boxes.values()) + [Box(0, H - legend_h, W, legend_h)],
                          max_w=320)
    _status_legend(svg, chips, 0, H - 34)
    desc = f"{count_phrase('data flow', len(edges))} between {len(nodes)} systems, labelled with the data they carry"
    return Picture("flow", ctx.source, svg.render(desc), desc, svg.texts)


# -------------------------------------------------------------------- bars

def _bars(ctx: Ctx) -> Picture | None:
    t = ctx.theme
    svg = Svg(t, ctx.uid)
    p = ctx.project
    if ctx.source == "registers":
        regs = [(k, r) for k, r in p.registers.items() if len(r)]
        if not regs:
            return None
        n = len(regs)
        per_row = 5 if n > 12 else (4 if n > 4 else n)
        rows = math.ceil(n / per_row)
        gap = 16
        tw = (W - gap * (per_row - 1)) / per_row
        th = min(150, (H - gap * (rows - 1)) / rows)
        num_w = 72
        for i, (k, reg) in enumerate(regs):
            rr, cc = divmod(i, per_row)
            x, y = cc * (tw + gap), rr * (th + gap)
            tile = svg.rect(x, y, tw, th, t.paper, t.rule, r=10)
            svg.text(x + 18, y + th / 2 - 36 * LINE / 2, [str(len(reg))], 36, t.accent, True,
                     font=t.heading_stack, within=tile)
            label = _plural(reg.type.label, len(reg))
            lines = wrap(label[:1].upper() + label[1:], tw - num_w - 30, MIN_FONT,
                         max_lines=max(1, int((th - 16) // (MIN_FONT * LINE))))
            svg.text(x + num_w + 12, y + th / 2 - len(lines) * MIN_FONT * LINE / 2, lines, MIN_FONT, t.ink,
                     within=tile)
        total = sum(len(r) for _, r in regs)
        desc = f"{total} records across {n} registers"
        return Picture("bars", ctx.source, svg.render(desc), desc, svg.texts)
    recs = ctx.records()
    if not recs:
        return None
    rt = ctx.rtype()
    by = ctx.by or "status"
    groups = group_values(ctx, recs, by)
    # Each group is a row: its name and count, then a tile per record (its
    # title, id and status in words), wrapping onto more tile rows.
    legend_h = 48
    label_w = 280
    gap = 12
    avail = W - label_w
    per = max(1, int((avail + gap) // (300 + gap)))
    tw = (avail - gap * (per - 1)) / per
    tile_rows = [max(1, -(-len(g) // per)) for _, g in groups]
    usable = H - legend_h - 16 * (len(groups) - 1)
    th = min(200, (usable - gap * sum(r - 1 for r in tile_rows)) / max(1, sum(tile_rows)))
    max_rows = len(groups)
    if th < 56:
        # Too many to name in full: one tile row per group, the rest counted.
        tile_rows = [1] * len(groups)
        th = min(112, usable / len(groups))
    chips = set()
    total_h = sum(r * th + (r - 1) * gap for r in tile_rows) + 16 * (len(groups) - 1)
    y = max(0.0, (H - legend_h - total_h) / 2)
    for (value, items), nrows in zip(groups, tile_rows):
        block_h = nrows * th + (nrows - 1) * gap
        label = (human(value) if value != "tbc" else "TBC")
        name = wrap(label, label_w - 24, MIN_FONT, True, 1)
        count = wrap(count_phrase(rt.label if rt else "record", len(items)), label_w - 24, MIN_FONT,
                     max_lines=max(1, int(block_h // (MIN_FONT * LINE)) - 1))
        ty = y + (block_h - (1 + len(count)) * MIN_FONT * LINE) / 2
        svg.text(0, ty, name, MIN_FONT, t.ink, True)
        svg.text(0, ty + MIN_FONT * LINE, count, MIN_FONT, t.muted)
        cap = nrows * per
        show = items if len(items) <= cap else items[:cap - 1]
        for k, r in enumerate(show):
            rr, cc = divmod(k, per)
            chips.add(r.chip)
            subs = [f"{r.id} · {status_words(r)}"] if th >= 84 else []
            if th >= 140:
                subs += [x for x in (r.owner and f"Owner: {r.owner}", _first_text(r)) if x]
            svg.status_box(label_w + cc * (tw + gap), y + rr * (th + gap), tw, th, r.title, subs, r.chip,
                           align="start", pad=10)
        if len(show) < len(items):
            k = len(show)
            rr, cc = divmod(k, per)
            _more(svg, label_w + cc * (tw + gap), y + rr * (th + gap), tw, th, len(items) - k, "")
        y += block_h + 16
    _status_legend(svg, chips, 0, H - 34)
    if len(groups) > max_rows:
        svg.text(W, H - 34, [f"+{len(groups) - max_rows} more groups"], MIN_FONT, t.muted, anchor="end")
    desc = f"the {count_phrase(rt.label if rt else 'record', len(recs))} by {by}"
    return Picture("bars", ctx.source, svg.render(desc), desc, svg.texts)


# --------------------------------------------------------------------- map

def _map(ctx: Ctx) -> Picture | None:
    p = ctx.project
    t = ctx.theme
    src = ctx.source
    edges: list[tuple[str, str, str, bool, str]] = []  # (from, to, label, current, chip)
    nodes: list[str] = []
    hub: str | None = None
    inner: list[str] = []
    merged_title: list[str] = []      # a node named for the design, drawn as the container itself
    if src == "application":
        apps = ctx.records("application")
        if not apps:
            return None
        names = [a.title for a in apps]
        for i in ctx.records("integration"):
            s, d = ctx.name(i.get("source")), ctx.name(i.get("target"))
            if s in names and d in names:
                edges.append((s, d, human(i.get("pattern")) or i.title,
                              display(i.get("state")).lower() == "current", i.chip))
        new = [a.title for a in apps if display(a.get("change")).lower() == "new"]
        hub = new[0] if new else p.title
        nodes = [hub] + [n for n in names if n != hub]
        if not edges:
            for a in apps:
                if a.title == hub:
                    continue
                role = display(a.get("role")).lower()
                label = human(a.get("change")) or ""
                cur = display(a.get("state")).lower() == "current"
                if role == "source":
                    edges.append((a.title, hub, label, cur, a.chip))
                elif role == "target":
                    edges.append((hub, a.title, label, cur, a.chip))
                elif role == "both":
                    edges.append((a.title, hub, label, cur, a.chip))
                    edges.append((hub, a.title, label, cur, a.chip))
        noun = "application"
        count = len(apps)
    else:
        ints = ctx.records(src)
        if not ints:
            return None
        rt = ctx.rtype(src)
        if rt is None or "source" not in rt.fields or "target" not in rt.fields:
            return None
        for i in ints:
            s, d = ctx.name(i.get("source")), ctx.name(i.get("target"))
            if not s or not d:
                continue
            for n in (s, d):
                if n not in nodes:
                    nodes.append(n)
            edges.append((s, d, human(i.get("pattern")) or i.title,
                          display(i.get("state")).lower() == "current", i.chip))
        if not edges:
            return None
        degree = {n: 0 for n in nodes}
        for s, d, *_ in edges:
            degree[s] += 1
            degree[d] += 1
        # The system at the centre is this design: a node named for it, or a
        # new application it delivers. A design whose integrations run
        # between its own components (a platform) is drawn as a container of
        # those components instead.
        names = {p.title.lower(), p.short.lower()}
        comps = {c.title.lower() for c in ctx.records("component")}
        ours = [n for n in nodes if n.lower() in comps or n.lower() in names]
        if len(ours) >= 2:
            # The design's own components (and the design itself) form the centre.
            hub = p.title
            inner = [n for n in ours if n.lower() not in names]
            merged_title = [n for n in ours if n.lower() in names]
        elif ours:
            hub = ours[0]
        else:
            new = {a.title.lower() for a in ctx.records("application") if display(a.get("change")).lower() == "new"}
            cands = [n for n in nodes if n.lower() in new] or nodes
            hub = max(cands, key=lambda n: (degree[n], -nodes.index(n)))
        noun = "integration"
        count = len(ints)
    svg = Svg(t, ctx.uid)
    inside = set(inner) | {hub} | set(merged_title)
    others = [n for n in nodes if n not in inside]
    max_nodes = 16
    dropped = others[max_nodes:]
    others = others[:max_nodes]
    legend_h = 44
    cx, cy = W / 2, (H - legend_h) / 2
    boxes: dict[str, Box] = {}
    internal_flows = 0
    if inner:
        shown_in = inner[:8]
        k = len(shown_in)
        cols = k if k <= 2 else -(-k // 2)       # two rows, so each component faces its side
        rows_in = -(-k // cols)
        # Each component box is as wide as its name needs for two lines.
        def need_w(name):
            for w_ in range(180, 341, 10):
                if len(wrap(name, w_ - 16, MIN_FONT, True)) <= 2:
                    return w_
            return 340
        ib_w = max(need_w(nm) for nm in shown_in)
        ib_h = 2 * MIN_FONT * LINE + 20
        cw_ = cols * ib_w + (cols - 1) * 16 + 40
        ch_ = 48 + rows_in * ib_h + (rows_in - 1) * 14 + 20
        hub_box = svg.rect(cx - cw_ / 2, cy - ch_ / 2, cw_, ch_, t.accent, t.accent, r=14)
        svg.text(cx - cw_ / 2 + 20, cy - ch_ / 2 + 12, [ellipsize(hub, cw_ - 40, 28, True)], 28, t.paper, True,
                 within=hub_box)
        cells = [(cx - cw_ / 2 + 20 + c_ * (ib_w + 16), cy - ch_ / 2 + 48 + r_ * (ib_h + 14))
                 for r_ in range(rows_in) for c_ in range(cols)][:k]
        for name in inner[8:]:
            boxes[name] = hub_box
    else:
        hub_box = svg.box(cx - 190, cy - 64, 380, 128, hub, [], fill=t.accent, stroke=t.accent,
                          title_color=t.paper, title_size=28)
    boxes[hub] = hub_box
    for name in merged_title:
        boxes[name] = hub_box
    n = len(others)
    bw, bh = 290, 100          # room for a three-line system name
    rx, ry = W / 2 - bw / 2, (H - legend_h) / 2 - bh / 2
    # Place by angle; sources to the left, targets to the right when they are one-way.
    inbound = {s for s, d, *_ in edges if d in inside and s not in inside}
    outbound = {d for s, d, *_ in edges if s in inside and d not in inside}
    left = [o for o in others if o in inbound and o not in outbound]
    right = [o for o in others if o in outbound and o not in inbound]
    mid = [o for o in others if o not in left and o not in right]
    for o in mid:
        (left if len(left) <= len(right) else right).append(o)

    def place(side: list[str], sign: int):
        m = len(side)
        for k, name in enumerate(side):
            # spread over the half-ellipse from top to bottom
            a = math.pi * (k + 1) / (m + 1)  # 0..pi
            x = cx + sign * rx * math.sin(a) - bw / 2
            y = cy - ry * math.cos(a) - bh / 2
            x = min(max(x, 0), W - bw)
            y = min(max(y, 0), H - legend_h - bh)
            if _hit(Box(x, y, bw, bh), hub_box, 20):
                # Clear of the centre: out to the side it is on.
                x = hub_box.x - bw - 24 if sign < 0 else hub_box.x + hub_box.w + 24
                x = min(max(x, 0), W - bw)
            boxes[name] = svg.box(x, y, bw, bh, name, [], fill=t.paper, stroke=t.rule, pad=8)
    def perimeter(names: list[str]) -> None:
        """Many systems: slots round the edge of the picture (top and bottom
        rows, left and right columns), each system in the free slot nearest
        the side its flows point to."""
        pw, ph_, gap_ = 250, 100, 12
        avail_h = H - legend_h
        n_row = int((W + gap_) // (pw + gap_))
        slots = []
        for i in range(n_row):
            x = i * (W - pw) / (n_row - 1)
            slots.append((x, 0.0))
            slots.append((x, avail_h - ph_))
        n_col = int((avail_h - 2 * ph_ - 2 * gap_ + gap_) // (ph_ + gap_))
        for j in range(n_col):
            y = ph_ + gap_ + j * (ph_ + gap_) + ((avail_h - 2 * ph_ - 2 * gap_) - n_col * (ph_ + gap_) + gap_) / 2
            slots.append((0.0, y))
            slots.append((W - pw, y))
        slots = [sl for sl in slots if not _hit(Box(sl[0], sl[1], pw, ph_), hub_box, 16)]

        def angle(sl):
            return math.atan2(sl[1] + ph_ / 2 - cy, sl[0] + pw / 2 - cx)
        free = list(slots)
        flip = 0
        for name in names:
            if name in inbound and name not in outbound:
                want = math.pi
            elif name in outbound and name not in inbound:
                want = 0.0
            else:
                want = -math.pi / 2 if flip % 2 == 0 else math.pi / 2
                flip += 1
            if not free:
                break
            best = min(free, key=lambda sl: abs(math.atan2(math.sin(angle(sl) - want), math.cos(angle(sl) - want))))
            free.remove(best)
            boxes[name] = svg.box(best[0], best[1], pw, ph_, name, [], fill=t.paper, stroke=t.rule, pad=8)
    if len(others) > 8:
        perimeter(left + right)
    else:
        place(left, -1)
        place(right, 1)
    if inner:
        # Each component sits in the cell nearest the systems it talks to,
        # so few connectors cross the container.
        def partners(name):
            pts = [(boxes[o].cx, boxes[o].cy) for s_, d_, *_ in edges for o in (s_, d_)
                   if name in (s_, d_) and o not in inside and o in boxes]
            if not pts:
                return (cx, cy)
            return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))
        free_cells = list(cells)
        for name in sorted(shown_in, key=lambda nm: -abs(partners(nm)[0] - cx)):
            px_, py_ = partners(name)
            cell = min(free_cells, key=lambda c: math.hypot(c[0] + ib_w / 2 - px_, c[1] + ib_h / 2 - py_))
            free_cells.remove(cell)
            boxes[name] = svg.box(cell[0], cell[1], ib_w, ib_h, name, [], fill=t.paper, stroke=t.paper,
                                  title_size=MIN_FONT, pad=8)
    # Merge edges between the same pair.
    merged: dict[tuple[str, str], dict] = {}
    for s, d, label, cur, chip in edges:
        if s not in boxes or d not in boxes:
            continue
        if s in inside and d in inside:
            internal_flows += 1
            continue
        if boxes[s] is boxes[d]:
            continue
        k = tuple(sorted((s, d)))
        e = merged.setdefault(k, {"dirs": set(), "labels": [], "current": True, "chips": set(), "first": (s, d)})
        e["dirs"].add((s, d))
        if label and label not in e["labels"]:
            e["labels"].append(label)
        e["current"] = e["current"] and cur
        e["chips"].add(chip)
    pills = []
    ring = -1
    any_current = any_target = False
    for (a_, b_), e in merged.items():
        s, d = e["first"]
        both = len(e["dirs"]) == 2
        dashed = e["current"]
        any_current |= dashed
        any_target |= not dashed
        sb, db = boxes[s], boxes[d]
        color = t.ink if not dashed else t.muted
        text = e["labels"][0] if len(e["labels"]) == 1 else f"{len(e['labels'])} flows"
        if s in inside or d in inside:
            if inner and (sb is not hub_box and s in inside or db is not hub_box and d in inside):
                # A component inside the container: the connector stops at the
                # container's border, on the side facing the outer system and
                # in line with the component, so it never crosses the title band.
                comp, ext = (sb, db) if s in inside else (db, sb)
                px, py = hub_box.edge_point((ext.cx, ext.cy))
                if abs(px - hub_box.x) < 1 or abs(px - hub_box.x - hub_box.w) < 1:
                    py = min(max(comp.cy, hub_box.y + 56), hub_box.y + hub_box.h - 8)
                else:
                    px = min(max(comp.cx, hub_box.x + 12), hub_box.x + hub_box.w - 12)
                port = Box(px - 0.5, py - 0.5, 1, 1)
                a_, b_ = (port, db) if s in inside else (sb, port)
                svg.arrow(a_, b_, color=color, dashed=dashed, both=both)
            else:
                svg.arrow(sb, db, color=color, dashed=dashed, both=both)
        elif not _crosses(sb, db, Box(hub_box.x - 16, hub_box.y - 16, hub_box.w + 32, hub_box.h + 32)) and \
                not any(_crosses(sb, db, Box(o.x - 6, o.y - 6, o.w + 12, o.h + 12))
                        for o in boxes.values() if o is not sb and o is not db and o is not hub_box):
            # Two outer systems clear of the container: a straight connector.
            svg.arrow(sb, db, color=color, dashed=dashed, both=both)
        else:
            # Two outer systems on either side of the container: the connector
            # runs round it on a ring road, each one a lane further out.
            ring += 1
            via = _ring_route(sb, db, hub_box, 22 + 12 * ring, Box(0, 0, W, H - legend_h),
                              [o for o in boxes.values() if o is not hub_box])
            svg.arrow(sb, db, color=color, dashed=dashed, both=both, via=via)
        pills.append((svg.last, text))
    dropped_labels = 0
    for along, text in pills:
        svg.last = along
        avoid = list(boxes.values()) + [Box(0, H - legend_h, W, legend_h)]
        if svg.label_on_last(text, color=t.accent, avoid=avoid, max_w=260, strict=True) is None:
            dropped_labels += 1
    entries = []
    if any_target:
        entries.append(("target", False))
    if any_current:
        entries.append(("current only", True))
    lx = svg.line_legend(entries, 0, H - 34) if entries else 0
    notes = []
    if dropped_labels:
        notes.append(f"{count_phrase('connector', dropped_labels)} unlabelled where no clear room")
    if internal_flows:
        notes.append(f"{count_phrase('flow', internal_flows)} inside {hub} not drawn")
    if dropped:
        notes.append(f"+{len(dropped)} more systems")
    if notes:
        svg.text(W, H - 34, [" · ".join(notes)], MIN_FONT, t.muted, anchor="end")
    desc = f"the {count_phrase(noun, count)} around {hub}"
    return Picture("map", src, svg.render(desc), desc, svg.texts)


# ---------------------------------------------------------------- dispatch

DRAWERS: dict[str, Callable[[Ctx], Picture | None]] = {
    "layers": _layers, "timeline": _timeline, "traceability": _traceability, "heatmap": _heatmap,
    "matrix": _matrix, "swimlane": _swimlane, "flow": _flow, "bars": _bars, "map": _map,
}
assert set(DRAWERS) == set(PICTURE_KINDS)


def draw(kind: str, project: "Project", spec: dict | None = None, chapter: "Chapter | None" = None,
         theme: Theme | None = None) -> Picture | None:
    """One picture of ``kind`` (``spec`` may give ``from`` and ``by``), or
    None when the register it needs is empty."""
    if kind not in DRAWERS:
        raise ValueError(f"'{kind}' is not a picture kind ({', '.join(PICTURE_KINDS)})")
    spec = dict(spec or {})
    spec["kind"] = kind
    use_plurals(project)
    ctx = Ctx(project, spec, theme or Theme.from_profile(project.profile), chapter)
    LAST_SVG.clear()
    pic = DRAWERS[kind](ctx)
    if pic is not None and LAST_SVG:
        pic.extent = min(1.0, max(svg.bottom for svg in LAST_SVG) / H)
        pic.rects = [b for svg in LAST_SVG for b in svg.rects]
    return pic


LAST_SVG: list["Svg"] = []    # the writers a drawing used, read once it returns


def chain(spec: dict) -> list[dict]:
    """The pictures to try for a chapter, in order: its own, the fallbacks
    it names (``picture.fallback``, or kinds in a list-valued
    ``picture.by``), then ``layers`` from ``depends_on``."""
    out = [dict(spec)] if spec.get("kind") else []
    if out and isinstance(spec.get("by"), list):
        out[0].pop("by")
    extra = list(spec.get("fallback") or []) if isinstance(spec.get("fallback"), list) else (
        [spec["fallback"]] if spec.get("fallback") else [])
    if isinstance(spec.get("by"), list):
        extra += [b for b in spec["by"] if (isinstance(b, str) and b in DRAWERS) or isinstance(b, dict)]
    for f in extra:
        out.append(dict(f) if isinstance(f, dict) else {"kind": f})
    out.append({"kind": "layers", "from": "depends_on"})
    return out


def generate(project: "Project", chapter: "Chapter", theme: Theme | None = None,
             exclude: set[str] | None = None, registers: Iterable[str] = ()) -> Picture:
    """The chapter's generated picture: the first in its :func:`chain` that
    has something to draw and is not already on another chapter's slide
    (``exclude`` holds the fingerprints used). When the chain is used up,
    the chapter's own registers (``registers``) are drawn: each record's
    status, the status counts, or a timeline. ``layers`` from
    ``depends_on`` is the last resort and always draws."""
    theme = theme or Theme.from_profile(project.profile)
    exclude = exclude or set()
    specs = chain(chapter.picture or {})[:-1]
    for rtype in registers:
        specs += [{"kind": "matrix", "from": rtype}, {"kind": "bars", "from": rtype, "by": "status"},
                  {"kind": "timeline", "from": rtype}, {"kind": "layers", "from": rtype}]
        # the register's records grouped by each of its other choice fields
        reg = project.registers.get(rtype)
        if reg is not None:
            for f, spec_ in reg.type.fields.items():
                if spec_.kind == "enum":
                    specs += [{"kind": "bars", "from": rtype, "by": f}, {"kind": "layers", "from": rtype, "by": f}]
    specs += [{"kind": "layers", "from": "depends_on"}, {"kind": "layers", "from": "component", "by": "layer"},
              {"kind": "layers", "from": "environment"}]
    for spec in specs:
        if spec["kind"] == "timeline" and _date_field(project.registers[spec["from"]].type
                                                       if spec["from"] in project.registers else None) is None:
            continue
        pic = draw(spec["kind"], project, spec, chapter, theme)
        if pic is not None and pic.fingerprint not in exclude and says_something(pic, project, spec, chapter, theme):
            return pic
    # Every picture the chain can draw is already on another slide: draw
    # the chapter itself, its sections as layers of what each holds.
    pic = sections_picture(project, chapter, theme)
    if pic is not None and pic.fingerprint not in exclude and node_count(pic) >= 3:
        return pic
    pic = draw("layers", project, {"from": "depends_on"}, chapter, theme)
    assert pic is not None  # layers from depends_on always draws
    return pic


STATUS_KINDS = ("matrix",)
NODE_KINDS = ("map", "flow", "layers")


def node_count(pic: Picture) -> int:
    """The boxes a picture draws (not legend swatches or chips)."""
    return sum(1 for b in pic.rects if b.w >= 60 and b.h >= 40)


def says_something(pic: Picture, project: "Project", spec: dict, chapter=None, theme=None) -> bool:
    """A status picture needs at least two distinct statuses, and a node
    picture (map, flow, layers) at least three nodes: otherwise it shows
    one fact, which the story slide already says."""
    status_pic = pic.kind in STATUS_KINDS or (pic.kind == "bars" and (spec.get("by") in (None, "status"))
                                               and pic.source != "registers")
    if status_pic:
        ctx = Ctx(project, dict(spec, kind=pic.kind), theme or Theme.from_profile(project.profile), chapter)
        if len({status_words(r) for r in ctx.records()}) < 2:
            return False
    if pic.kind in NODE_KINDS and node_count(pic) < 3:
        return False
    return True


def sections_picture(project: "Project", chapter: "Chapter", theme: Theme | None = None) -> Picture | None:
    """The chapter as layers: a band per section (up to six) holding the
    records the section cites, or its first sentence when it cites none."""
    from . import content as C
    theme = theme or Theme.from_profile(project.profile)
    t = theme
    LAST_SVG.clear()
    svg = Svg(t, f"c{chapter.number}-sections")
    bands = []
    for sec in chapter.sections:
        recs: list[Record] = []
        for b in sec.blocks:
            if isinstance(b, C.RegisterTable):
                recs += [r for r in b.records if r not in recs]
        for a in sec.artefacts:
            reg = project.registers.get(a.type)
            if reg is not None:
                recs += [r for r in reg.filter(a.where) if r not in recs]
        text = ""
        rows: list[tuple[str, str]] = []
        if not recs:
            # A section with a plain table: its rows, first column as the
            # name and the second beneath it.
            for b in sec.blocks:
                if isinstance(b, C.Table) and not isinstance(b, (C.RegisterTable, C.Catalogue)) and b.body:
                    rows = [(C.plain(r[0]), C.plain(r[1]) if len(r) > 1 else "") for r in b.body if r and r[0].strip()]
                    break
            if not rows:
                for b in sec.blocks:
                    if isinstance(b, C.Para) and b.text.strip():
                        text = C.plain(b.text).split(". ")[0].rstrip(".") + "."
                        break
        if recs or rows or text:
            bands.append((f"{sec.number} {sec.title}", recs or rows, text))
    if not bands:
        return None
    bands = bands[:6]
    legend_h = 44
    gap = 16
    bh = min(150, (H - legend_h - gap * (len(bands) - 1)) / len(bands))
    label_w = 380
    y = 0.0
    chips = set()
    for label, recs, text in bands:
        svg.rect(0, y, W, bh, t.panel, t.rule, r=12)
        box = Box(0, y, label_w, bh)
        lines = wrap(label, label_w - 40, MIN_FONT, True, max_lines=max(1, int((bh - 16) // (MIN_FONT * LINE))))
        svg.text(20, y + (bh - len(lines) * MIN_FONT * LINE) / 2, lines, MIN_FONT, t.ink, True, within=box)
        x0, x1 = label_w, W - 12
        if recs:
            per = max(1, min(len(recs), int((x1 - x0 + 12) // (220 + 12))))
            shown = recs if len(recs) <= per else recs[:per - 1]
            bw = (x1 - x0 - 12 * (per - 1)) / per
            for i, r in enumerate(shown):
                if isinstance(r, tuple):             # a plain table's row
                    svg.box(x0 + i * (bw + 12), y + 10, bw, bh - 20, r[0], [r[1]], fill=t.paper, stroke=t.rule,
                            align="start", pad=10)
                    continue
                chips.add(r.chip)
                svg.status_box(x0 + i * (bw + 12), y + 10, bw, bh - 20, r.title, [f"{r.id} · {status_words(r)}"],
                               r.chip, align="start", pad=10)
            if len(shown) < len(recs):
                _more(svg, x0 + len(shown) * (bw + 12), y + 10, bw, bh - 20, len(recs) - len(shown), "")
        else:
            svg.box(x0, y + 10, x1 - x0, bh - 20, "", [text], fill=t.paper, stroke=t.rule, align="start",
                    sub_color=t.ink)
        y += bh + gap
    if chips:
        _status_legend(svg, chips)
    desc = f"chapter {chapter.number} section by section, with what each holds"
    pic = Picture("layers", "sections", svg.render(desc), desc, svg.texts)
    pic.extent = min(1.0, svg.bottom / H)
    pic.rects = list(svg.rects)
    return pic


def overlaps(texts: list[Text], tol: float = 1.0) -> list[tuple[Text, Text]]:
    """Pairs of placed text lines whose boxes overlap."""
    out = []
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if (a.x + tol < b.x + b.w and b.x + tol < a.x + a.w and
                    a.y + tol < b.y + b.h and b.y + tol < a.y + a.h):
                out.append((a, b))
    return out


__all__ = ["Picture", "Theme", "W", "H", "MIN_FONT", "draw", "generate", "chain", "wrap", "ellipsize",
           "text_width", "human", "mix", "overlaps", "DEFAULT_FROM", "CHIP_WORDS"]
