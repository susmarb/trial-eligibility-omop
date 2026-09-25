"""Three-valued evaluation. The rule that matters: UNKNOWN never excludes.

A record that is silent about a criterion must not be read as failing it. That
single decision is what separates a screening aid a coordinator will use from one
that quietly rejects eligible patients.
"""
import unittest

from trialcriteria import tree as CT
from trialcriteria.tree import FALSE, TRUE, UNKNOWN


def leaf():
    return CT.Node("LEAF", text="x")


def node(op, kids, n=0):
    p = CT.Node(op, n=n)
    p.children = list(kids)
    return p


class TestKleene(unittest.TestCase):

    def test_and_with_one_unknown_is_unknown_not_false(self):
        a, b = leaf(), leaf()
        p = node("AND", [a, b])
        self.assertEqual(CT.evaluate(p, {id(a): TRUE}), UNKNOWN)

    def test_and_with_one_false_is_false(self):
        a, b = leaf(), leaf()
        p = node("AND", [a, b])
        self.assertEqual(CT.evaluate(p, {id(a): FALSE}), FALSE)

    def test_and_all_true_is_true(self):
        a, b = leaf(), leaf()
        p = node("AND", [a, b])
        self.assertEqual(CT.evaluate(p, {id(a): TRUE, id(b): TRUE}), TRUE)

    def test_or_with_one_true_is_true_even_if_the_rest_are_unknown(self):
        a, b = leaf(), leaf()
        p = node("OR", [a, b])
        self.assertEqual(CT.evaluate(p, {id(a): TRUE}), TRUE)

    def test_or_all_false_is_false(self):
        a, b = leaf(), leaf()
        p = node("OR", [a, b])
        self.assertEqual(CT.evaluate(p, {id(a): FALSE, id(b): FALSE}), FALSE)

    def test_n_of_reaches_true_once_the_threshold_is_met(self):
        a, b, c = leaf(), leaf(), leaf()
        p = node("N_OF", [a, b, c], n=2)
        self.assertEqual(CT.evaluate(p, {id(a): TRUE, id(b): TRUE}), TRUE)

    def test_n_of_is_false_only_when_it_can_no_longer_be_reached(self):
        a, b, c = leaf(), leaf(), leaf()
        p = node("N_OF", [a, b, c], n=2)
        self.assertEqual(CT.evaluate(p, {id(a): FALSE, id(b): FALSE, id(c): TRUE}),
                         FALSE)

    def test_n_of_stays_unknown_while_unknowns_could_still_satisfy_it(self):
        a, b, c = leaf(), leaf(), leaf()
        p = node("N_OF", [a, b, c], n=2)
        self.assertEqual(CT.evaluate(p, {id(a): TRUE}), UNKNOWN)

    def test_an_empty_tree_is_unknown_not_true(self):
        self.assertEqual(CT.evaluate(node("AND", []), {}), UNKNOWN)

    def test_explain_names_the_failing_node(self):
        a, b = leaf(), leaf()
        a.text = "Adult patients"
        b.text = "Measurable disease"
        p = node("AND", [a, b])
        out = CT.explain(p, {id(a): TRUE, id(b): FALSE})
        self.assertIn("false", out)
        self.assertIn("Measurable disease", out)


if __name__ == "__main__":
    unittest.main()
