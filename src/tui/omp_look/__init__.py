"""The OMP look: an opt-in composer chrome and status line modelled on oh-my-pi's `pi` composer shape.

Fork-only package (foxion37/oh-my-hermes, branch q-design). The default look is
upstream's and nothing here changes it; `OMH_TUI_LOOK=omp`, or
`$OMH_HOME/tui/look.json` holding {"look": "omp"}, opts in.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

LOOK_DEFAULT = "default"
LOOK_OMP = "omp"
_LOOKS = frozenset({LOOK_DEFAULT, LOOK_OMP})


def omh_home(environ: Mapping[str, str]) -> Path | None:
    """Where OMH keeps its state, from the environment the TUI was given: `OMH_HOME`, else `$HOME/.omh`, else None.

    Only the given environment is read (never `Path.home()`), so an `App` built
    with a bare environment, as the test suite builds it, never sees this
    machine's look file.
    """
    value = environ.get("OMH_HOME", "").strip()
    if value:
        return Path(value).expanduser()
    home = environ.get("HOME", "").strip()
    return Path(home) / ".omh" if home else None


def resolve_look(environ: Mapping[str, str], home: Path | None = None) -> str:
    """The look to draw: the env var, else the look file, else the default; anything unknown is the default."""
    value = environ.get("OMH_TUI_LOOK", "").strip().lower()
    root = home or omh_home(environ)
    if not value and root is not None:
        try:
            payload = json.loads((root / "tui" / "look.json").read_text(encoding="utf-8"))
            value = str(payload.get("look", "")).strip().lower()
        except (OSError, ValueError, AttributeError):
            value = ""
    return value if value in _LOOKS else LOOK_DEFAULT
