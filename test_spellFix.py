"""Unit tests for spellFix.py.

Run with:
    python -m unittest test_spellFix.py
"""
import io
import sys
import tempfile
import tkinter as tk
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spellFix

ROOT = None


def setUpModule():
    global ROOT
    ROOT = tk.Tk()
    ROOT.withdraw()


def tearDownModule():
    ROOT.destroy()


def write_report(path, lines, encoding="utf-16"):
    with io.open(path, "w", encoding=encoding) as f:
        f.write("\n".join(lines) + "\n")


def read_report(path, encoding="utf-16"):
    with io.open(path, "r", encoding=encoding) as f:
        return f.readlines()


def build_app(report_path, repo_path=".", max_issues=5000, context_lines=15,
              sort_option="alphabetical", ignored_patterns=None, project_dictionary=None):
    """Construct a SpellFixerApp without running __init__ (which reads the
    user's real ~/.spellfix_config.json and would touch their real repo)."""
    app = spellFix.SpellFixerApp.__new__(spellFix.SpellFixerApp)
    app.root = ROOT
    app.typos = defaultdict(list)
    app.fixed_items = {}
    app.project_dictionary = set() if project_dictionary is None else project_dictionary
    app.report_path = tk.StringVar(master=ROOT, value=str(report_path))
    app.repo_path = tk.StringVar(master=ROOT, value=str(repo_path))
    app.max_issues = tk.IntVar(master=ROOT, value=max_issues)
    app.context_lines = tk.IntVar(master=ROOT, value=context_lines)
    app.sort_option = tk.StringVar(master=ROOT, value=sort_option)
    app.status_text = tk.StringVar(master=ROOT, value="Ready")
    app.ignored_patterns = [] if ignored_patterns is None else ignored_patterns
    app.filter_text = tk.StringVar(master=ROOT, value="")
    app.selected_typo = None
    app.selected_occurrence = None
    app.typo_listbox = tk.Listbox(ROOT)
    return app


class TestReportLinePattern(unittest.TestCase):
    """Regression tests for the report-line regex (previously only matched .\\ paths)."""

    def test_relative_windows_path(self):
        m = spellFix.REPORT_LINE_PATTERN.match(r".\src\Form.cs:8: coefficents ==> coefficients")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), r".\src\Form.cs")
        self.assertEqual(m.group(2), "8")
        self.assertEqual(m.group(3), "coefficents")
        self.assertEqual(m.group(4), "coefficients")

    def test_relative_posix_path(self):
        m = spellFix.REPORT_LINE_PATTERN.match("./src/form.py:42: teh ==> the")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "./src/form.py")

    def test_absolute_windows_path(self):
        m = spellFix.REPORT_LINE_PATTERN.match(
            r"C:\SourceDB\AeroConfigurationEditor.Net\AeroCoefficientForm.cs:8: coefficents ==> coefficients"
        )
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), r"C:\SourceDB\AeroConfigurationEditor.Net\AeroCoefficientForm.cs")
        self.assertEqual(m.group(2), "8")

    def test_absolute_posix_path(self):
        m = spellFix.REPORT_LINE_PATTERN.match("/home/user/repo/form.py:42: recieve ==> receive")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "/home/user/repo/form.py")

    def test_multiple_corrections_captured_as_single_group(self):
        m = spellFix.REPORT_LINE_PATTERN.match(r".\x.py:1: wether ==> weather, whether")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(4), "weather, whether")

    def test_no_match_for_malformed_line(self):
        self.assertIsNone(spellFix.REPORT_LINE_PATTERN.match("not a report line"))
        self.assertIsNone(spellFix.REPORT_LINE_PATTERN.match(""))


class TestApplyCasePattern(unittest.TestCase):
    def test_all_upper(self):
        self.assertEqual(spellFix.SpellFixerApp.apply_case_pattern(None, "TEH", "the"), "THE")

    def test_all_lower(self):
        self.assertEqual(spellFix.SpellFixerApp.apply_case_pattern(None, "teh", "THE"), "the")

    def test_title_case(self):
        self.assertEqual(spellFix.SpellFixerApp.apply_case_pattern(None, "Teh", "the"), "The")

    def test_mixed_case_returned_as_is(self):
        self.assertEqual(spellFix.SpellFixerApp.apply_case_pattern(None, "TeH", "the"), "the")

    def test_empty_original_returns_replacement(self):
        self.assertEqual(spellFix.SpellFixerApp.apply_case_pattern(None, "", "the"), "the")

    def test_empty_replacement_returned_as_is(self):
        self.assertEqual(spellFix.SpellFixerApp.apply_case_pattern(None, "teh", ""), "")


class TestIsIgnored(unittest.TestCase):
    def test_substring_pattern_matches(self):
        app = build_app("report.txt", ignored_patterns=["node_modules"])
        self.assertTrue(app.is_ignored("node_modules/foo.js"))

    def test_glob_pattern_matches(self):
        app = build_app("report.txt", ignored_patterns=["*.pyc"])
        self.assertTrue(app.is_ignored("src/app.pyc"))

    def test_no_matching_pattern(self):
        app = build_app("report.txt", ignored_patterns=["node_modules", "*.pyc"])
        self.assertFalse(app.is_ignored("src/app.py"))

    def test_backslashes_normalized_before_matching(self):
        app = build_app("report.txt", ignored_patterns=["build/output"])
        self.assertTrue(app.is_ignored(r"build\output\file.txt"))


class TestLoadReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.report_path = Path(self.tmpdir.name) / "report.txt"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_loads_relative_and_absolute_paths(self):
        write_report(self.report_path, [
            r".\src\form.py:1: teh ==> the",
            r"C:\SourceDB\bar.py:2: recieve ==> receive",
            "/home/user/repo/baz.py:3: adress ==> address",
        ])
        app = build_app(self.report_path)
        app.load_report()

        self.assertEqual(set(app.typos.keys()), {"teh", "recieve", "adress"})
        self.assertEqual(app.typos["recieve"][0]["file"], "C:/SourceDB/bar.py")
        self.assertEqual(app.typos["adress"][0]["file"], "/home/user/repo/baz.py")

    def test_multiple_corrections_are_split(self):
        write_report(self.report_path, [r".\x.py:1: wether ==> weather, whether"])
        app = build_app(self.report_path)
        app.load_report()

        self.assertEqual(app.typos["wether"][0]["corrections"], ["weather", "whether"])

    def test_marked_lines_are_tracked_and_excluded_from_pending(self):
        write_report(self.report_path, [
            r"[FIXED] .\a.py:1: teh ==> the",
            r"[SKIPPED] .\b.py:2: recieve ==> receive",
            r".\c.py:3: adress ==> address",
        ])
        app = build_app(self.report_path)
        app.load_report()

        self.assertEqual(app.fixed_items[("teh", "./a.py", 1)], "fixed")
        self.assertEqual(app.fixed_items[("recieve", "./b.py", 2)], "skipped")
        self.assertEqual(list(app.typos.keys()), ["adress"])

    def test_max_issues_limits_pending_count(self):
        write_report(self.report_path, [
            fr".\f{i}.py:1: typo{i} ==> fix{i}" for i in range(5)
        ])
        app = build_app(self.report_path, max_issues=3)
        app.load_report()

        self.assertEqual(len(app.typos), 3)

    def test_project_dictionary_filters_typos(self):
        write_report(self.report_path, [
            r".\a.py:1: teh ==> the",
            r".\b.py:2: adress ==> address",
        ])
        app = build_app(self.report_path, project_dictionary={"teh"})
        app.load_report()

        self.assertNotIn("teh", app.typos)
        self.assertIn("adress", app.typos)

    def test_ignored_files_are_skipped(self):
        write_report(self.report_path, [
            r".\node_modules\dep.js:1: teh ==> the",
            r".\src\app.py:2: adress ==> address",
        ])
        app = build_app(self.report_path, ignored_patterns=["node_modules"])
        app.load_report()

        self.assertNotIn("teh", app.typos)
        self.assertIn("adress", app.typos)

    @patch("spellFix.messagebox.showerror")
    def test_missing_report_file_shows_error(self, mock_showerror):
        app = build_app(Path(self.tmpdir.name) / "does_not_exist.txt")
        app.load_report()

        mock_showerror.assert_called_once()
        self.assertEqual(len(app.typos), 0)


class TestMarkInReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.report_path = Path(self.tmpdir.name) / "report.txt"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_marks_matching_line_as_fixed(self):
        write_report(self.report_path, [
            r".\a.py:1: teh ==> the",
            r".\b.py:2: adress ==> address",
        ])
        app = build_app(self.report_path)
        app.mark_in_report("teh", "./a.py", 1, "fixed")

        lines = read_report(self.report_path)
        self.assertTrue(lines[0].startswith("[FIXED]"))
        self.assertFalse(lines[1].startswith("[FIXED]"))
        self.assertFalse(lines[1].startswith("[SKIPPED]"))

    def test_marks_absolute_path_line_as_skipped(self):
        write_report(self.report_path, [r"C:\SourceDB\bar.py:2: recieve ==> receive"])
        app = build_app(self.report_path)
        app.mark_in_report("recieve", "C:/SourceDB/bar.py", 2, "skipped")

        lines = read_report(self.report_path)
        self.assertTrue(lines[0].startswith("[SKIPPED]"))

    def test_already_marked_lines_are_left_untouched(self):
        write_report(self.report_path, [r"[FIXED] .\a.py:1: teh ==> the"])
        app = build_app(self.report_path)
        app.mark_in_report("teh", "a.py", 1, "skipped")

        lines = read_report(self.report_path)
        self.assertTrue(lines[0].startswith("[FIXED]"))
        self.assertNotIn("[SKIPPED]", lines[0])


if __name__ == "__main__":
    unittest.main()
