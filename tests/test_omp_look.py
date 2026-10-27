"""Fork-only (q-design): the OMP look — look switch, segments, `pi` chrome, frame seam and app wiring."""

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from omh.tui.composer import Composer
from omh.tui.frame import build_frame
from omh.tui.omp_look import LOOK_DEFAULT, LOOK_OMP, resolve_look
from omh.tui.omp_look.chrome import SIDE_CELLS, PiChrome
from omh.tui.omp_look.segments import Segment, StatusInputs, build_segments, join_segments
from omh.tui.omp_look.wire import chrome_for, git_branch
from omh.tui.theme import DEFAULT_THEME
from omh.tui.width import line_width


def text(line):
    return "".join(span.text for span in line)


class ResolveLookTest(unittest.TestCase):
    def test_default_when_nothing_set(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(resolve_look({}, Path(home)), LOOK_DEFAULT)

    def test_env_wins(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(resolve_look({"OMH_TUI_LOOK": "OMP"}, Path(home)), LOOK_OMP)

    def test_file_is_read(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "tui" / "look.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"look": "omp"}))
            self.assertEqual(resolve_look({}, Path(home)), LOOK_OMP)

    def test_unknown_or_broken_falls_back(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(resolve_look({"OMH_TUI_LOOK": "neon"}, Path(home)), LOOK_DEFAULT)
            path = Path(home) / "tui" / "look.json"
            path.parent.mkdir()
            path.write_text("[not json")
            self.assertEqual(resolve_look({}, Path(home)), LOOK_DEFAULT)


def inputs(**overrides):
    base = dict(
        model="opus", mode="normal", title="plan", cwd="~/dev/x", branch="q-design", subagents=2,
        context_pct=42.4, total_tokens=12_345, tps=38.2, cache_hit_pct=71.0, elapsed_s=125,
    )
    base.update(overrides)
    return StatusInputs(**base)


class SegmentsTest(unittest.TestCase):
    def test_order_follows_config(self):
        left, right = build_segments(inputs(), ["model", "mode", "path", "git"], ["context_pct", "cache_hit"])
        self.assertEqual([s.id for s in left], ["model", "mode", "path", "git"])
        self.assertEqual([s.text for s in right], ["ctx 42%", "cache 71%"])

    def test_missing_values_and_unknown_ids_are_dropped(self):
        left, _ = build_segments(inputs(branch="", subagents=0), ["git", "subagents", "cost", "pr", "model"], [])
        self.assertEqual([s.id for s in left], ["model"])

    def test_formats(self):
        _, right = build_segments(inputs(), [], ["token_total", "token_rate", "time_spent"])
        self.assertEqual([s.text for s in right], ["12.3k tok", "38 tok/s", "2m05s"])
        _, right = build_segments(inputs(total_tokens=900, elapsed_s=3725), [], ["token_total", "time_spent"])
        self.assertEqual([s.text for s in right], ["900 tok", "1h02m"])

    def test_context_turns_warn_then_error(self):
        roles = [build_segments(inputs(context_pct=p), [], ["context_pct"])[1][0].role for p in (10, 70, 90)]
        self.assertEqual(roles, ["ok", "warn", "error"])

    def test_join_uses_pipe(self):
        left, _ = build_segments(inputs(), ["model", "mode"], [])
        self.assertEqual(join_segments(left), "opus │ normal")


class PiChromeTest(unittest.TestCase):
    def setUp(self):
        self.chrome = PiChrome(left=(Segment("model", "opus", "brand"),), right=(Segment("ctx", "ctx 42%", "ok"),))

    def test_top_border_embeds_segments_and_fills_width(self):
        top = self.chrome.top(40, DEFAULT_THEME)
        self.assertEqual(line_width(top), 40)
        self.assertTrue(text(top).startswith("╭─ opus "))
        self.assertTrue(text(top).endswith(" ctx 42% ─╮"))

    def test_top_border_drops_right_then_left_when_narrow(self):
        self.assertEqual(text(self.chrome.top(12, DEFAULT_THEME)), "╭─ opus ───╮")
        self.assertEqual(text(self.chrome.top(5, DEFAULT_THEME)), "╭───╮")

    def test_bottom_and_sides(self):
        self.assertEqual(text(self.chrome.bottom(6, DEFAULT_THEME)), "╰────╯")
        row = self.chrome.wrap([()], 10, DEFAULT_THEME)[0]
        self.assertEqual(line_width(row), 10)
        self.assertTrue(text(row).startswith("│ ") and text(row).endswith(" │"))
        self.assertEqual(SIDE_CELLS, 2)


class FrameSeamTest(unittest.TestCase):
    def test_default_frame_is_unchanged_without_chrome(self):
        a = build_frame(cols=40, rows=20, composer=Composer(), info=())
        b = build_frame(cols=40, rows=20, composer=Composer(), info=(), chrome=None)
        self.assertEqual(a, b)

    def test_pi_chrome_draws_box_and_shifts_caret(self):
        chrome = PiChrome(left=(Segment("model", "opus", "brand"),))
        composer = Composer(text="안녕하세요", caret=5)
        plain = build_frame(cols=40, rows=20, composer=composer, info=())
        boxed = build_frame(cols=40, rows=20, composer=composer, info=(), chrome=chrome)
        rows = [text(line) for line in boxed.lines]
        self.assertTrue(any(r.startswith("╭─ opus") for r in rows), rows)
        self.assertTrue(any(r.startswith("╰") and r.endswith("╯") for r in rows), rows)
        self.assertTrue(all(line_width(line) <= 40 for line in boxed.lines))
        self.assertEqual(boxed.cursor[1], plain.cursor[1] + SIDE_CELLS)
        self.assertEqual(boxed.cursor[0], plain.cursor[0])


class WireTest(unittest.TestCase):
    def test_reads_app_state(self):
        app = SimpleNamespace(
            model="opus", session_title="t", context_percent=12.0, _display_mode=lambda: "normal",
            transcript=SimpleNamespace(cwd=""), roster=SimpleNamespace(running_count=lambda: 1),
            omp_usage={"total": 1500, "avg_tps": 40.0, "cache_hit_pct": 70.0}, omp_started_at=None,
        )
        chrome = chrome_for(app)
        self.assertEqual([s.id for s in chrome.left], ["model", "mode", "session_name", "subagents"])
        self.assertEqual([s.text for s in chrome.right], ["ctx 12%", "1.5k tok", "40 tok/s", "cache 70%"])

    def test_git_branch_reads_head(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / ".git").mkdir()
            (Path(root) / ".git" / "HEAD").write_text("ref: refs/heads/q-design\n")
            (Path(root) / "sub").mkdir()
            self.assertEqual(git_branch(str(Path(root) / "sub")), "q-design")
            self.assertEqual(git_branch(""), "")

    def test_app_still_has_the_attributes_wire_reads(self):
        from omh.tui import app as app_module

        source = inspect.getsource(app_module)
        for name in ("self.model", "self.session_title", "self.context_percent", "self.roster", "self.transcript",
                     "def _display_mode", "self.omp_usage", "self.omp_started_at", "self.omp_look"):
            self.assertTrue(name in source, f"upstream renamed or dropped {name}: update omp_look/wire.py")


if __name__ == "__main__":
    unittest.main()
