"""Gathers the OMP look's inputs from the running app: the only module that knows the app's attribute names.

Everything is read with `getattr` defaults, so an upstream rename degrades a
segment to empty instead of breaking the frame; `tests/test_omp_look_wire.py`
pins the names against the real `App` so a rename is caught by the sync check.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .chrome import PiChrome
from .segments import StatusInputs, build_segments

# oh-my-pi's status line as configured on this machine, without `hostname` (kept out of a public fork's defaults),
# `usage`, `cost` and `pr` (no data from Hermes).
LEFT: Sequence[str] = ("model", "mode", "session_name", "path", "git", "subagents")
RIGHT: Sequence[str] = ("context_pct", "token_total", "token_rate", "cache_hit", "time_spent")


def git_branch(cwd: str) -> str:
    """The branch checked out at `cwd` or above, read from `.git/HEAD` (no subprocess); "" when there is none."""
    if not cwd:
        return ""
    path = Path(cwd).expanduser()
    for folder in (path, *path.parents):
        head = folder / ".git"
        if head.is_file():  # a worktree: `.git` names the real git dir
            try:
                target = head.read_text(encoding="utf-8").strip().removeprefix("gitdir:").strip()
            except OSError:
                return ""
            head = (folder / target) if not Path(target).is_absolute() else Path(target)
        try:
            ref = (head / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return ref.removeprefix("ref: refs/heads/") if ref.startswith("ref: ") else ref[:7]
    return ""


def _number(usage: Mapping[str, object], key: str) -> float | None:
    value = usage.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def status_inputs(app: object, now: float | None = None) -> StatusInputs:
    usage = getattr(app, "omp_usage", None)
    usage = usage if isinstance(usage, Mapping) else {}
    transcript = getattr(app, "transcript", None)
    cwd = str(getattr(transcript, "cwd", "") or "")
    roster = getattr(app, "roster", None)
    mode = getattr(app, "_display_mode", None)
    started = getattr(app, "omp_started_at", None)
    total = _number(usage, "total")
    return StatusInputs(
        model=str(getattr(app, "model", "") or ""),
        mode=str(mode() if callable(mode) else ""),
        title=str(getattr(app, "session_title", "") or ""),
        cwd=_home_short(cwd),
        branch=git_branch(cwd),
        subagents=int(roster.running_count()) if roster is not None and hasattr(roster, "running_count") else 0,
        context_pct=getattr(app, "context_percent", None),
        total_tokens=int(total) if total is not None else None,
        tps=_number(usage, "avg_tps"),
        cache_hit_pct=_number(usage, "cache_hit_pct"),
        elapsed_s=int((time.monotonic() if now is None else now) - started) if isinstance(started, float) else None,
    )


def _home_short(cwd: str) -> str:
    home = str(Path.home())
    return "~" + cwd[len(home):] if cwd == home or cwd.startswith(home + "/") else cwd


def chrome_for(app: object) -> PiChrome:
    left, right = build_segments(status_inputs(app), LEFT, RIGHT)
    return PiChrome(left=tuple(left), right=tuple(right))
