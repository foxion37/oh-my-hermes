"""oh-my-pi's `pi` composer shape for the OMH frame: a rounded box whose top edge carries the status line.

    ╭─ model │ mode │ path ─────────── ctx 42% │ cache 71% ─╮
    │ ❯ the prompt                                          │
    ╰───────────────────────────────────────────────────────╯

Pure rendering over `Line`/`Span`; widths are terminal cells. When the top
edge is too narrow the right group goes first, then the left. The composer's
rows are rendered `2 * SIDE_CELLS` narrower and wrapped between `│ ` and ` │`,
so the caret moves `SIDE_CELLS` to the right.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..style import Line, Span
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

    def top(self, width: int, theme: Theme) -> Line:
        if width < 2:
            return (Span("─" * max(width, 0), theme.rule),)
        inner = width - 2  # between ╭ and ╮
        left, right = _group(self.left, theme), _group(self.right, theme)
        lhs: tuple[Span, ...] = ()
        rhs: tuple[Span, ...] = ()
        for lhs, rhs in ((left, right), (left, ()), ((), ())):
            if _cost(lhs) + _cost(rhs) <= inner:
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

    def wrap(self, rows: Sequence[Line], width: int, theme: Theme) -> list[Line]:
        """Each row between `│ ` and ` │`, padded to `width`; the rows were rendered at `inner_width(width)`."""
        inner = inner_width(width)
        wrapped: list[Line] = []
        for row in rows:
            body = truncate_line(tuple(row), inner)
            pad = inner - line_width(body)
            wrapped.append((Span("│ ", theme.rule), *body, Span(" " * pad), Span(" │", theme.rule)))
        return wrapped


def _cost(group: tuple[Span, ...]) -> int:
    """Cells a group takes on the top edge with its padding (`─ … ` on the left, ` … ─` on the right)."""
    return line_width(group) + 3 if group else 0


def inner_width(width: int) -> int:
    return max(width - 2 * SIDE_CELLS, 0)
