"""Synthetic fixtures only; these tests do not label validation criteria."""
import tempfile
import unittest
from pathlib import Path

from trialcriteria.score import read_marks


class TestReadMarks(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.txt"
            path.write_text(text, encoding="utf-8")
            return read_marks(path)

    def test_sheet_preserves_item_numbers_and_question_marks(self):
        text = ("1. [demo] NCT00000001\n    you: W\n"
                "2. [demo] NCT00000002\n    you: ?\n"
                "3. [demo] NCT00000003\n    you: ___\n"
                "4. [demo] NCT00000004\n    you: C\n")
        self.assertEqual(self.read(text), {1: "W", 2: "?", 4: "C"})

    def test_bare_and_numbered_you_formats(self):
        self.assertEqual(self.read("1 W\n2 ?\n3. you: n\n"),
                         {1: "W", 2: "?", 3: "N"})

    def test_numberless_sheet_keeps_blank_positions(self):
        self.assertEqual(self.read("you: W\nyou: ___\nyou: ?\nyou: C\n"),
                         {1: "W", 3: "?", 4: "C"})

    def test_unmarked_sheet_has_no_answers(self):
        self.assertEqual(self.read("1. [demo] NCT00000001\nyou: ___\n"), {})

    def test_duplicate_marks_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.read("1 W\n1 C\n")
