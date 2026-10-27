"""Status-line segments for the OMP look, from what Hermes' gateway already sends (session.info, session.usage).

Pure: no IO and no clock; `wire.status_inputs` gathers the values. A segment
with no value is dropped, and ids Hermes has no data for (`cost`, `pr`) are
ignored, so a config copied from oh-my-pi still renders.

Every segment carries a glyph, as oh-my-pi's do, and the figures that have a
denominator show it (`▤ 42% · 91k/200k`): the context window's own size, the
session's input and output tokens (`⇅ ↑91k ↓18k`), and the cache hit share.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

SEPARATOR = " │ "  # oh-my-pi's `pipe` separator

# The glyph a segment starts with, drawn in the segment's own colour. `path` and `hostname` carry none: a path
# reads as a path, and oh-my-pi keeps the host out of its defaults.
GLYPHS = {
    "model": "◆",
    "mode": "◇",
    "session_name": "❐",
    "path": "",
    "git": "⎇",
    "subagents": "⛓",
    "hostname": "",
    "context_pct": "▤",
    "usage": "⇅",
    "token_total": "∑",
    "token_rate": "⚡",
    "cache_hit": "⚍",
    "time_spent": "◷",
}


@dataclass(frozen=True)
class StatusInputs:
    model: str = ""
    mode: str = ""
    title: str = ""
    cwd: str = ""
    branch: str = ""
    git_state: str = ""  # `●3` changed files, `↑1↓2` ahead/behind, both: `●3 ↑1`
    subagents: int = 0
    context_pct: float | None = None
    context_used: int | None = None
    context_max: int | None = None
    total_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tps: float | None = None
    cache_hit_pct: float | None = None
    elapsed_s: int | None = None
    hostname: str = ""


@dataclass(frozen=True)
class Segment:
    id: str
    text: str
    role: str  # a `Theme` attribute: "brand", "muted", "running", "ok", "warn", "error"


def _tokens(count: int) -> str:
    """`91.6k`, `900`: a count as the status line says it, without a unit of its own."""
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def _elapsed(seconds: int) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _context_role(percent: float) -> str:
    return "error" if percent >= 85 else "warn" if percent >= 60 else "ok"


def _icon(seg_id: str) -> str:
    glyph = GLYPHS.get(seg_id, "")
    return f"{glyph} " if glyph else ""


def _context(v: StatusInputs) -> str:
    """`42% · 91.6k/200.0k`: the share, and the window's own size when the gateway sends it."""
    percent = f"{v.context_pct:.0f}%"
    if v.context_used is not None and v.context_max:
        return f"{percent} · {_tokens(int(v.context_used))}/{_tokens(int(v.context_max))}"
    return percent


def _usage(v: StatusInputs) -> str:
    """`↑91.6k ↓18.7k · 110.3k`: this session's input, its output, and their sum."""
    if v.input_tokens is not None and v.output_tokens is not None:
        return f"↑{_tokens(v.input_tokens)} ↓{_tokens(v.output_tokens)} · {_tokens(v.input_tokens + v.output_tokens)}"
    if v.total_tokens:
        return _tokens(int(v.total_tokens))
    return ""


def _segment(seg_id: str, v: StatusInputs) -> Segment | None:
    if seg_id == "model" and v.model:
        return Segment(seg_id, f"{_icon(seg_id)}{v.model}", "brand")
    if seg_id == "mode" and v.mode:
        return Segment(seg_id, f"{_icon(seg_id)}{v.mode}", "muted")
    if seg_id == "session_name" and v.title:
        return Segment(seg_id, f"{_icon(seg_id)}{v.title}", "muted")
    if seg_id == "path" and v.cwd:
        return Segment(seg_id, f"{_icon(seg_id)}{v.cwd}", "muted")
    if seg_id == "git" and v.branch:
        state = f" {v.git_state}" if v.git_state else ""
        return Segment(seg_id, f"{_icon(seg_id)}{v.branch}{state}", "muted")
    if seg_id == "subagents" and v.subagents > 0:
        return Segment(seg_id, f"{_icon(seg_id)}{v.subagents}", "running")
    if seg_id == "hostname" and v.hostname:
        return Segment(seg_id, f"{_icon(seg_id)}{v.hostname}", "muted")
    if seg_id == "context_pct" and v.context_pct is not None:
        return Segment(seg_id, f"{_icon(seg_id)}{_context(v)}", _context_role(v.context_pct))
    if seg_id == "usage":
        usage = _usage(v)
        return Segment(seg_id, f"{_icon(seg_id)}{usage}", "muted") if usage else None
    if seg_id == "token_total" and v.total_tokens:
        return Segment(seg_id, f"{_icon(seg_id)}{_tokens(int(v.total_tokens))} tok", "muted")
    if seg_id == "token_rate" and v.tps:
        return Segment(seg_id, f"{_icon(seg_id)}{v.tps:.0f} tok/s", "muted")
    if seg_id == "cache_hit" and v.cache_hit_pct is not None:
        return Segment(seg_id, f"{_icon(seg_id)}{v.cache_hit_pct:.0f}%", "muted")
    if seg_id == "time_spent" and v.elapsed_s is not None:
        return Segment(seg_id, f"{_icon(seg_id)}{_elapsed(int(v.elapsed_s))}", "muted")
    return None


def _pick(v: StatusInputs, ids: Sequence[str]) -> list[Segment]:
    return [seg for seg in (_segment(seg_id, v) for seg_id in ids) if seg is not None]


def build_segments(v: StatusInputs, left: Sequence[str], right: Sequence[str]) -> tuple[list[Segment], list[Segment]]:
    """The left and right groups, in the order the ids are given, without the segments that have no value."""
    return _pick(v, left), _pick(v, right)


def join_segments(segments: Sequence[Segment]) -> str:
    return SEPARATOR.join(seg.text for seg in segments)
