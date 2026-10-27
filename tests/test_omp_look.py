"""Fork-only (q-design): the OMP look — look switch, segments, `pi` chrome, frame seam and app wiring."""

import inspect
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from omh.tui.composer import Composer
from omh.tui.frame import build_frame
from omh.tui.style import Span, Style
from omh.tui.omp_look import LOOK_DEFAULT, LOOK_OMP, resolve_look
from omh.tui.omp_look.chrome import SIDE_CELLS, PiChrome
from omh.tui.omp_look.segments import Segment, StatusInputs, build_segments, join_segments
from omh.tui.omp_look.wire import _status_cache, band_wanted, chrome_for, git_branch, git_status, status_inputs
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

    def test_only_the_given_environment_names_the_home(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / ".omh" / "tui" / "look.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"look": "omp"}))
            self.assertEqual(resolve_look({"HOME": home}), LOOK_OMP)
        self.assertEqual(resolve_look({}), LOOK_DEFAULT)  # a bare environment never reads this machine's file

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
        self.assertEqual([s.text for s in right], ["▤ 42%", "⚍ 71%"])

    def test_missing_values_and_unknown_ids_are_dropped(self):
        left, _ = build_segments(inputs(branch="", subagents=0), ["git", "subagents", "cost", "pr", "model"], [])
        self.assertEqual([s.id for s in left], ["model"])

    def test_formats(self):
        _, right = build_segments(inputs(), [], ["token_total", "token_rate", "time_spent"])
        self.assertEqual([s.text for s in right], ["∑ 12.3k tok", "⚡ 38 tok/s", "◷ 2m05s"])
        _, right = build_segments(inputs(total_tokens=900, elapsed_s=3725), [], ["token_total", "time_spent"])
        self.assertEqual([s.text for s in right], ["∑ 900 tok", "◷ 1h02m"])

    def test_every_segment_carries_its_glyph(self):
        left, right = build_segments(inputs(), ["model", "mode", "session_name", "git"], ["context_pct", "cache_hit"])
        self.assertEqual([s.text.split(" ")[0] for s in (*left, *right)], ["◆", "◇", "❐", "⎇", "▤", "⚍"])

    def test_context_shows_the_window_it_sits_in(self):
        _, right = build_segments(inputs(), [], ["context_pct"])
        self.assertEqual(right[0].text, "▤ 42%")
        _, right = build_segments(inputs(context_used=91_600, context_max=200_000), [], ["context_pct"])
        self.assertEqual(right[0].text, "▤ 42% · 91.6k/200.0k")

    def test_usage_shows_input_output_and_total(self):
        _, right = build_segments(inputs(input_tokens=91_564, output_tokens=18_650), [], ["usage"])
        self.assertEqual(right[0].text, "⇅ ↑91.6k ↓18.6k · 110.2k")
        _, right = build_segments(inputs(total_tokens=1_500), [], ["usage"])
        self.assertEqual(right[0].text, "⇅ 1.5k")
        _, right = build_segments(inputs(total_tokens=None), [], ["usage"])
        self.assertEqual(right, [])

    def test_git_state_follows_the_branch(self):
        _, right = build_segments(inputs(git_state="●3 ↑1"), ["git"], [])
        self.assertEqual(right, [])
        left, _ = build_segments(inputs(git_state="●3 ↑1"), ["git"], [])
        self.assertEqual(left[0].text, "⎇ q-design ●3 ↑1")
        left, _ = build_segments(inputs(git_state=""), ["git"], [])
        self.assertEqual(left[0].text, "⎇ q-design")

    def test_context_turns_warn_then_error(self):
        roles = [build_segments(inputs(context_pct=p), [], ["context_pct"])[1][0].role for p in (10, 70, 90)]
        self.assertEqual(roles, ["ok", "warn", "error"])

    def test_join_uses_pipe(self):
        left, _ = build_segments(inputs(), ["model", "mode"], [])
        self.assertEqual(join_segments(left), "◆ opus │ ◇ normal")


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

    def test_segments_drop_one_at_a_time(self):
        chrome = PiChrome(
            left=(Segment("model", "opus", "brand"), Segment("mode", "normal", "muted")),
            right=(Segment("ctx", "ctx 42%", "ok"), Segment("tok", "12.3k tok", "muted")),
        )
        top = chrome.top(40, DEFAULT_THEME)
        self.assertEqual(line_width(top), 40)
        self.assertTrue(text(top).startswith("╭─ opus │ normal ─"))
        self.assertTrue(text(top).endswith("─ ctx 42% ─╮"))
        self.assertNotIn("12.3k", text(top))
        self.assertEqual(text(chrome.top(20, DEFAULT_THEME)), "╭─ opus │ normal ──╮")
        self.assertEqual(text(chrome.top(12, DEFAULT_THEME)), "╭─ opus ───╮")

    def test_bottom_and_sides(self):
        self.assertEqual(text(self.chrome.bottom(6, DEFAULT_THEME)), "╰────╯")
        row = self.chrome.wrap([()], 10, DEFAULT_THEME)[0]
        self.assertEqual(line_width(row), 10)
        self.assertTrue(text(row).startswith("│ ") and text(row).endswith(" │"))
        self.assertEqual(SIDE_CELLS, 2)

    def test_band_fills_the_row_and_inks_its_text(self):
        band = DEFAULT_THEME.input_band
        self.assertTrue(band.bg)
        row = self.chrome.wrap([(Span("typed", Style()),)], 12, DEFAULT_THEME, band)[0]
        self.assertEqual(line_width(row), 12)
        typed = next(span for span in row if span.text == "typed")
        self.assertEqual(typed.style.bg, band.bg)
        self.assertEqual(typed.style.fg, band.fg)  # the terminal's own foreground would vanish on the band
        self.assertEqual(row[0].style.bg, None)  # the sides and the rules keep the terminal's background
        self.assertEqual(row[-1].style.bg, None)
        self.assertEqual(row[-3].style.bg if row[-3].text.strip() == "" else row[-2].style.bg, band.bg)  # the padding


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
        self.assertEqual([s.text for s in chrome.right], ["▤ 12%", "⇅ 1.5k", "⚡ 40 tok/s", "⚍ 70%"])
        self.assertTrue(chrome.band)  # no environment at all still gets the look's band

    def test_band_switches_off_from_the_environment(self):
        self.assertFalse(band_wanted({"OMH_TUI_BAND": "0"}))
        self.assertFalse(band_wanted({"OMH_TUI_BAND": "off"}))
        self.assertTrue(band_wanted({}))
        self.assertTrue(band_wanted({"OMH_TUI_BAND": "1"}))

    def test_title_falls_back_to_the_first_prompt(self):
        from omh.tui.transcript import Transcript, UserBlock

        transcript = Transcript()
        transcript.blocks.append(UserBlock(text="첫 프롬프트입니다\n둘째 줄"))
        inputs_ = status_inputs(SimpleNamespace(session_title="", transcript=transcript, omp_started_at=None))
        self.assertEqual(inputs_.title, "첫 프롬프트입니다")

    def test_usage_feeds_the_context_window_and_the_token_split(self):
        app = SimpleNamespace(
            model="opus", session_title="t", context_percent=42.0, _display_mode=lambda: "normal",
            transcript=SimpleNamespace(cwd=""),
            omp_usage={"input": 91_564, "output": 18_650, "total": 110_214, "context_used": 91_600,
                       "context_max": 200_000},
            omp_started_at=None,
        )
        inputs_ = status_inputs(app)
        self.assertEqual((inputs_.input_tokens, inputs_.output_tokens), (91_564, 18_650))
        self.assertEqual((inputs_.context_used, inputs_.context_max), (91_600, 200_000))

    def test_git_status_reads_branch_changes_and_tracking(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)

            def git(*args):
                return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True)

            git("init", "-q", "-b", "q-design")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            (path / "tracked.txt").write_text("one\n")
            git("add", "tracked.txt")
            git("commit", "-q", "-m", "one")
            _status_cache.clear()
            self.assertEqual(git_status(str(path)), ("q-design", ""))
            (path / "tracked.txt").write_text("one\ntwo\n")
            (path / "new.txt").write_text("x\n")
            _status_cache.clear()
            self.assertEqual(git_status(str(path)), ("q-design", "●2"))
            _status_cache.clear()
            self.assertEqual(git_status(str(Path(root) / "missing")), ("", ""))

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


class AppLookTest(unittest.TestCase):
    """The real `App`, drawn through the TUI test harness: the box only when the look is opted in."""

    def _screen(self, environ):
        from test_tui_modes import drawn, make_app, type_text

        app, _ = make_app(environ=environ)
        app.model = "opus-test"
        app._take_usage({"total": 2048, "avg_tps": 33.0, "cache_hit_pct": 50.0, "context_used": 10, "context_max": 100})
        type_text(app, "안녕")
        return drawn(app)

    def test_default_look_draws_no_box(self):
        with tempfile.TemporaryDirectory() as home:
            screen = self._screen({"OMH_HOME": home})
        self.assertFalse(any(row.lstrip().startswith("╭") for row in screen), screen)

    def test_omp_look_draws_the_status_box(self):
        with tempfile.TemporaryDirectory() as home:
            screen = self._screen({"OMH_HOME": home, "OMH_TUI_LOOK": "omp"})
        top = next((row for row in screen if row.startswith("╭─ ◆ opus-test")), None)
        self.assertIsNotNone(top, screen)
        self.assertIn("▤ 10%", top or "")
        self.assertIn("10/100", top or "")  # the context window's own size
        self.assertIn("⇅ 2.0k", top or "")
        self.assertIn("⚍ 50%", top or "")
        self.assertTrue(any(row.startswith("│ ") and "안녕" in row for row in screen), screen)
        self.assertTrue(any(row.startswith("╰") for row in screen), screen)

    def test_frame_paints_the_composer_band(self):
        composer = Composer(text="안녕")
        frame = build_frame(
            cols=60, rows=12, composer=composer, info=(), theme=DEFAULT_THEME,
            chrome=PiChrome(left=(Segment("model", "opus", "brand"),), band=True),
        )
        row = next((line for line in frame.lines if any("안녕" in span.text for span in line)), None)
        self.assertIsNotNone(row)
        band = DEFAULT_THEME.input_band
        typed = [span for span in row if "안녕" in span.text]
        self.assertTrue(all(span.style.bg == band.bg for span in typed), row)  # on the bright band
        self.assertTrue(all(span.style.fg == band.fg for span in typed), row)  # in its own ink
        # Without the band the same frame keeps the terminal's background.
        plain = build_frame(
            cols=60, rows=12, composer=composer, info=(), theme=DEFAULT_THEME,
            chrome=PiChrome(left=(Segment("model", "opus", "brand"),), band=False),
        )
        plain_row = next((line for line in plain.lines if any("안녕" in span.text for span in line)), None)
        self.assertTrue(all(span.style.bg is None for span in plain_row if "안녕" in span.text))


if __name__ == "__main__":
    unittest.main()
