"""oh-my-pi's `pi` composer shape for the OMH frame: a rounded box whose top edge carries the status line.

    ╭─ model │ mode │ path ─────────── ctx 42% │ cache 71% ─╮
    │ ❯ the prompt                                          │
    ╰───────────────────────────────────────────────────────╯

Pure rendering over `Line`/`Span`; widths are terminal cells. When the top
edge is too narrow, segments go one at a time from the right group's end, then from the left's. The composer's
rows are rendered `2 * SIDE_CELLS` narrower and wrapped between `│ ` and ` │`,
so the caret moves `SIDE_CELLS` to the right.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..style import Line, Span, Style
from ..theme import Theme
from ..width import line_width, truncate_line
from .segments import SEPARATOR, Segment

SIDE_CELLS = 2  # "│ " on the left, " │" on the right


def _group(segments: Sequence[Segment], theme: Theme) -> tuple[Span, ...]:
    spans: list[Span] = []
    for index, seg in enumerate(segments):
        if index:
            spans.append(Span(SEPARATOR, theme.dim))
        spans.append(Span(seg.text, getattr(theme, seg.role, theme.muted)))
    return tuple(spans)


@dataclass(frozen=True)
class PiChrome:
    left: tuple[Segment, ...] = ()
    right: tuple[Segment, ...] = ()
    band: bool = False  # the composer's text sits on `Theme.input_band`, the look's bright band

    def top(self, width: int, theme: Theme) -> Line:
        if width < 2:
            return (Span("─" * max(width, 0), theme.rule),)
        inner = width - 2  # between ╭ and ╮
        # Segments go one at a time from the right group's end, then from the left group's end, until both fit.
        tries = [(len(self.left), k) for k in range(len(self.right), -1, -1)]
        tries += [(j, 0) for j in range(len(self.left) - 1, -1, -1)]
        lhs: tuple[Span, ...] = ()
        rhs: tuple[Span, ...] = ()
        for keep_left, keep_right in tries:
            lhs, rhs = _group(self.left[:keep_left], theme), _group(self.right[:keep_right], theme)
            if _cost(lhs) + _cost(rhs) + (1 if lhs and rhs else 0) <= inner:  # a `─` keeps the groups apart
                break
        out: list[Span] = [Span("╭", theme.rule)]
        if lhs:
            out += [Span("─ ", theme.rule), *lhs, Span(" ", theme.rule)]
        out.append(Span("─" * (inner - _cost(lhs) - _cost(rhs)), theme.rule))
        if rhs:
            out += [Span(" ", theme.rule), *rhs, Span(" ─", theme.rule)]
        out.append(Span("╮", theme.rule))
        return tuple(out)

    def bottom(self, width: int, theme: Theme) -> Line:
        if width < 2:
            return (Span("─" * max(width, 0), theme.rule),)
        return (Span("╰" + "─" * (width - 2) + "╯", theme.rule),)

    def wrap(self, rows: Sequence[Line], width: int, theme: Theme, band: Style | None = None) -> list[Line]:
        """Each row between `│ ` and ` │`, padded to `width`; the rows were rendered at `inner_width(width)`.

        `band` fills the row's background: each span keeps its colour and takes the band's behind it, and the padding
        past the text is band too, so the band reaches both side cells.
        """
        inner = inner_width(width)
        wrapped: list[Line] = []
        for row in rows:
            body = truncate_line(tuple(row), inner)
            pad = inner - line_width(body)
            if band is None or band.bg is None:
                wrapped.append((Span("│ ", theme.rule), *body, Span(" " * pad), Span(" │", theme.rule)))
            else:
                inked = tuple(
                    Span(span.text, replace(span.style, bg=band.bg, fg=span.style.fg or band.fg)) for span in body
                )
                wrapped.append((Span("│ ", theme.rule), *inked, Span(" " * pad, band), Span(" │", theme.rule)))
        return wrapped


def _cost(group: tuple[Span, ...]) -> int:
    """Cells a group takes on the top edge with its padding (`─ … ` on the left, ` … ─` on the right)."""
    return line_width(group) + 3 if group else 0


def inner_width(width: int) -> int:
    return max(width - 2 * SIDE_CELLS, 0)
