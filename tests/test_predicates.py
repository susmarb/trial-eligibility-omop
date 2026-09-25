"""Numeric thresholds must survive parsing as predicates, not as prose.

'Platelet count >= 100,000/mm3' is only executable if the comparator, the value
and the unit all come through.
"""
import unittest

from trialcriteria.omop import COMP, OPMAP, generic_phrase


def parse(text):
    m = COMP.search(text)
    if not m:
        return None
    return (OPMAP.get(m.group("op").lower(), m.group("op")),
            float(m.group("val").replace(",", "")),
            (m.group("unit") or "").strip() or None)


class TestComparators(unittest.TestCase):

    def test_symbolic_greater_or_equal(self):
        self.assertEqual(parse("Platelet count >= 100,000/mm3")[:2], (">=", 100000.0))

    def test_unicode_greater_or_equal(self):
        self.assertEqual(parse("ANC ≥ 1.5 10^9/L")[:2], (">=", 1.5))

    def test_worded_at_least(self):
        self.assertEqual(parse("Life expectancy of at least 3 months")[0], ">=")

    def test_times_upper_limit_of_normal(self):
        op, val, unit = parse("Bilirubin <= 1.5 x ULN")
        self.assertEqual((op, val), ("<=", 1.5))
        self.assertIn("ULN", unit)

    def test_thousands_separator_is_stripped(self):
        self.assertEqual(parse("Platelets > 75,000/mm3")[1], 75000.0)

    def test_prose_without_a_threshold_yields_nothing(self):
        self.assertIsNone(parse("Patient must have adequate organ function"))


class TestGenericPhrase(unittest.TestCase):

    def test_stopwords_are_dropped(self):
        p = generic_phrase(
            "Patients must have a documented history of chronic asthma")
        self.assertIsNotNone(p)
        for w in ("patients", "must", "have", "documented", "history"):
            self.assertNotIn(w, p.split())
        self.assertIn("asthma", p.split())

    def test_fewer_than_two_content_words_returns_none(self):
        """Deliberate: a one-word query retrieves a menu too broad to choose from,
        and a bad menu is worse than no mapping at all."""
        self.assertIsNone(generic_phrase("Pregnant"))
        self.assertIsNone(generic_phrase("Patients must have a history of asthma"))


if __name__ == "__main__":
    unittest.main()
