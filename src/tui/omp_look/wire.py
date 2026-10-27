"""Gathers the OMP look's inputs from the running app: the only module that knows the app's attribute names.

Everything is read with `getattr` defaults, so an upstream rename degrades a
segment to empty instead of breaking the frame; `tests/test_omp_look_wire.py`
pins the names against the real `App` so a rename is caught by the sync check.

The branch and its state come from one `git status`, whose answer is kept for
`GIT_STATUS_TTL_S`: a frame is redrawn many times a second, and a status call
per frame would cost more than the look is worth.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .chrome import PiChrome
from .segments import StatusInputs, build_segments

# oh-my-pi's status line as configured on this machine, without `hostname` (kept out of a public fork's defaults),
# `cost` and `pr` (no data from Hermes). `usage` is the session's own input/output tokens.
LEFT: Sequence[str] = ("model", "mode", "session_name", "path", "git", "subagents")
RIGHT: Sequence[str] = ("context_pct", "usage", "token_rate", "cache_hit", "time_spent")

GIT_STATUS_TTL_S = 2.0  # how long one `git status` answer is reused, per directory
_GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
_status_cache: dict[str, tuple[float, tuple[str, str]]] = {}


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


def git_status(cwd: str, now: float | None = None) -> tuple[str, str]:
    """The branch and its state at `cwd` from one `git status`: `("q-design", "●3 ↑1")`.

    The state counts the changed files (`●N`, untracked included) and the commits the branch is ahead of and behind
    its upstream (`↑N`, `↓N`), each only when it is not zero. `("", "")` where there is no repository, no `git`, or
    the call failed; the last answer is reused for `GIT_STATUS_TTL_S`.
    """
    if not cwd:
        return "", ""
    stamp = time.monotonic() if now is None else now
    held = _status_cache.get(cwd)
    if held is not None and stamp - held[0] < GIT_STATUS_TTL_S:
        return held[1]
    answer = _git_status_uncached(cwd)
    _status_cache[cwd] = (stamp, answer)
    return answer


def _git_status_uncached(cwd: str) -> tuple[str, str]:
    try:
        done = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v1", "--branch", "--untracked-files=normal"],
            capture_output=True,
            text=True,
            timeout=2.0,
            stdin=subprocess.DEVNULL,
            env=_GIT_ENV,
        )
    except (OSError, subprocess.SubprocessError):
        return "", ""
    if done.returncode != 0:
        return "", ""
    branch = ""
    ahead = behind = changed = 0
    for index, line in enumerate(done.stdout.splitlines()):
        if index == 0 and line.startswith("## "):
            header = line[3:]
            head, _, rest = header.partition(" [")
            branch = head.split("...")[0].strip()
            if branch.startswith("No commits"):
                branch = ""
            for part in rest.rstrip("]").split(", "):
                name, _, count = part.partition(" ")
                if not count.isdigit():
                    continue
                if name == "ahead":
                    ahead = int(count)
                elif name == "behind":
                    behind = int(count)
            continue
        if line.strip():
            changed += 1
    pieces = []
    if changed:
        pieces.append(f"●{changed}")
    if ahead:
        pieces.append(f"↑{ahead}")
    if behind:
        pieces.append(f"↓{behind}")
    return branch, " ".join(pieces)


def _number(usage: Mapping[str, object], key: str) -> float | None:
    value = usage.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _int(usage: Mapping[str, object], key: str) -> int | None:
    value = _number(usage, key)
    return int(value) if value is not None else None


def _text(value: object) -> str:
    return str(value) if isinstance(value, str) else ""


def _title(app: object, transcript: object) -> str:
    """Hermes' auto-title, else the first line of the session's first prompt: the look always names the session."""
    title = _text(getattr(app, "session_title", ""))
    if title:
        return title
    blocks = getattr(transcript, "blocks", None)
    if not isinstance(blocks, list):
        return ""
    for block in blocks:
        text = _text(getattr(block, "text", ""))
        if type(block).__name__ == "UserBlock" and text.strip():
            return text.strip().split("\n", 1)[0][:40]
    return ""


def status_inputs(app: object, now: float | None = None) -> StatusInputs:
    usage = getattr(app, "omp_usage", None)
    usage = usage if isinstance(usage, Mapping) else {}
    transcript = getattr(app, "transcript", None)
    cwd = _text(getattr(transcript, "cwd", "")) or _text(getattr(app, "cwd", ""))
    branch, git_state = git_status(cwd)
    if not branch:  # a directory the look cannot read: the session's own record
        branch, git_state = git_branch(cwd), ""
    roster = getattr(app, "roster", None)
    mode = getattr(app, "_display_mode", None)
    started = getattr(app, "omp_started_at", None)
    total = _int(usage, "total")
    return StatusInputs(
        model=_text(getattr(app, "model", "")) or _text(usage.get("model")),
        mode=_text(mode() if callable(mode) else ""),
        title=_title(app, transcript),
        cwd=_home_short(cwd),
        branch=branch,
        git_state=git_state,
        subagents=int(roster.running_count()) if roster is not None and hasattr(roster, "running_count") else 0,
        context_pct=getattr(app, "context_percent", None),
        context_used=_int(usage, "context_used"),
        context_max=_int(usage, "context_max"),
        total_tokens=total,
        input_tokens=_int(usage, "input"),
        output_tokens=_int(usage, "output"),
        tps=_number(usage, "avg_tps"),
        cache_hit_pct=_number(usage, "cache_hit_pct"),
        elapsed_s=int((time.monotonic() if now is None else now) - started) if isinstance(started, float) else None,
    )


def _home_short(cwd: str) -> str:
    home = str(Path.home())
    return "~" + cwd[len(home):] if cwd == home or cwd.startswith(home + "/") else cwd


def band_wanted(environ: Mapping[str, str]) -> bool:
    """Whether the composer's text sits on the look's bright band: on for the OMP look, `OMH_TUI_BAND=0` turns it off."""
    return _text(environ.get("OMH_TUI_BAND")).strip().lower() not in {"0", "off", "no", "false"}


def chrome_for(app: object) -> PiChrome:
    left, right = build_segments(status_inputs(app), LEFT, RIGHT)
    environ = getattr(app, "environ", None)
    band = band_wanted(environ) if isinstance(environ, Mapping) else True
    return PiChrome(left=tuple(left), right=tuple(right), band=band)
