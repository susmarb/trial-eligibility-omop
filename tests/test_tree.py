"""The parser's contract, expressed as the failures that actually happened.

Every test here is a bug that was shipped once. Indentation carries the only
nesting signal in ClinicalTrials.gov criteria text, and the first version of this
parser called `line.strip()` on every line.
"""
import unittest

from trialcriteria import tree as CT


class TestNesting(unittest.TestCase):

    def test_indentation_creates_a_child_group(self):
        """The regression that motivated the whole rewrite.

        Six indented risk factors under 'at least 2 of the following' must not
        become six independent mandatory criteria.
        """
        text = """Inclusion Criteria:
  - Histologically confirmed carcinoma
  - At least 2 of the following risk factors:
    - Age over 60 years
    - Tumor size greater than 5 cm
    - Node positive disease
Exclusion Criteria:
  - Pregnancy"""
        t = CT.parse(text)
        inc = t["inclusion"]
        groups = [c for c in inc.children if c.op == "N_OF"]
        self.assertEqual(len(groups), 1, "the n-of-m group was flattened away")
        self.assertEqual(groups[0].n, 2)
        self.assertEqual(len(groups[0].children), 3,
                         "the risk factors did not nest under the group")
        # and they are NOT top-level requirements
        self.assertEqual(len([c for c in inc.children if c.op == "LEAF"]), 1)

    def test_sections_are_separated(self):
        text = """Inclusion Criteria:
  - Adult patients
Exclusion Criteria:
  - Active infection
  - Pregnancy"""
        t = CT.parse(text)
        self.assertEqual(len(list(t["inclusion"].leaves())), 1)
        self.assertEqual(len(list(t["exclusion"].leaves())), 2)

    def test_turkish_dotted_capital_i_still_finds_the_section(self):
        """'İNCLUSION' lowercases to 'i̇nclusion' (i + combining dot), which broke
        an exact dictionary lookup. Real protocols contain it."""
        text = "İNCLUSION CRITERIA:\n  - Adult patients\nEXCLUSION CRITERIA:\n  - Pregnancy"
        t = CT.parse(text)
        self.assertEqual(len(list(t["exclusion"].leaves())), 1)

    def test_any_of_the_following_is_a_disjunction(self):
        text = """Inclusion Criteria:
  - Any of the following:
    - Measurable disease by RECIST
    - Evaluable bone disease"""
        t = CT.parse(text)
        ors = [c for c in t["inclusion"].children if c.op == "OR"]
        self.assertEqual(len(ors), 1)
        self.assertEqual(len(ors[0].children), 2)

    def test_all_of_the_following_is_a_conjunction(self):
        text = """Inclusion Criteria:
  - All of the following:
    - ECOG 0 or 1
    - Life expectancy over 3 months"""
        t = CT.parse(text)
        self.assertTrue(any(c.op == "AND" and len(c.children) == 2
                            for c in t["inclusion"].children))

    def test_numbered_and_lettered_bullets_are_recognised(self):
        text = """Inclusion Criteria:
  1. Adult patients
  2. Signed informed consent"""
        self.assertEqual(len(list(CT.parse(text)["inclusion"].leaves())), 2)


class TestGroupOperator(unittest.TestCase):

    def test_word_numbers(self):
        self.assertEqual(CT._group_op("at least two of the following"), ("N_OF", 2))

    def test_digits(self):
        self.assertEqual(CT._group_op("At least 3 of the following:"), ("N_OF", 3))

    def test_one_of_the_following_is_a_disjunction_not_a_1_of_n(self):
        self.assertEqual(CT._group_op("one of the following"), ("OR", 0))

    def test_at_least_one_stays_an_n_of(self):
        self.assertEqual(CT._group_op("at least one of the following")[0], "N_OF")

    def test_plain_prose_is_not_a_group(self):
        self.assertIsNone(CT._group_op("Patients must have measurable disease"))


if __name__ == "__main__":
    unittest.main()
