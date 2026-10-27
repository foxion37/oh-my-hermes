"""Status-line segments for the OMP look, from what Hermes' gateway already sends (session.info, session.usage).

Pure: no IO and no clock; `wire.status_inputs` gathers the values. A segment
with no value is dropped, and ids Hermes has no data for (`cost`, `pr`) are
ignored, so a config copied from oh-my-pi still renders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

SEPARATOR = " │ "  # oh-my-pi's `pipe` separator


@dataclass(frozen=True)
class StatusInputs:
    model: str = ""
    mode: str = ""
    title: str = ""
    cwd: str = ""
    branch: str = ""
    subagents: int = 0
    context_pct: float | None = None
    total_tokens: int | None = None
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
    return f"{count / 1000:.1f}k tok" if count >= 1000 else f"{count} tok"


def _elapsed(seconds: int) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _context_role(percent: float) -> str:
    return "error" if percent >= 85 else "warn" if percent >= 60 else "ok"


def _segment(seg_id: str, v: StatusInputs) -> Segment | None:
    if seg_id == "model" and v.model:
        return Segment(seg_id, v.model, "brand")
    if seg_id == "mode" and v.mode:
        return Segment(seg_id, v.mode, "muted")
    if seg_id == "session_name" and v.title:
        return Segment(seg_id, v.title, "muted")
    if seg_id == "path" and v.cwd:
        return Segment(seg_id, v.cwd, "muted")
    if seg_id == "git" and v.branch:
        return Segment(seg_id, f"⎇ {v.branch}", "muted")
    if seg_id == "subagents" and v.subagents > 0:
        return Segment(seg_id, f"⛓ {v.subagents}", "running")
    if seg_id == "hostname" and v.hostname:
        return Segment(seg_id, v.hostname, "muted")
    if seg_id == "context_pct" and v.context_pct is not None:
        return Segment(seg_id, f"ctx {v.context_pct:.0f}%", _context_role(v.context_pct))
    if seg_id == "token_total" and v.total_tokens:
        return Segment(seg_id, _tokens(int(v.total_tokens)), "muted")
    if seg_id == "token_rate" and v.tps:
        return Segment(seg_id, f"{v.tps:.0f} tok/s", "muted")
    if seg_id == "cache_hit" and v.cache_hit_pct is not None:
        return Segment(seg_id, f"cache {v.cache_hit_pct:.0f}%", "muted")
    if seg_id == "time_spent" and v.elapsed_s is not None:
        return Segment(seg_id, _elapsed(int(v.elapsed_s)), "muted")
    return None


def _pick(v: StatusInputs, ids: Sequence[str]) -> list[Segment]:
    return [seg for seg in (_segment(seg_id, v) for seg_id in ids) if seg is not None]


def build_segments(v: StatusInputs, left: Sequence[str], right: Sequence[str]) -> tuple[list[Segment], list[Segment]]:
    """The left and right groups, in the order the ids are given, without the segments that have no value."""
    return _pick(v, left), _pick(v, right)


def join_segments(segments: Sequence[Segment]) -> str:
    return SEPARATOR.join(seg.text for seg in segments)
