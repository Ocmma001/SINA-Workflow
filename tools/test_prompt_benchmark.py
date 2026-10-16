import unittest
from prompt_benchmark import score_draft


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.truth = [{'id': 'Resistor_1', 'kind': 'R', 'ref': 'R1', 'nodes': ['1', '0'], 'value': 1000},
                      {'id': 'Resistor_2', 'kind': 'R', 'ref': 'R2', 'nodes': ['2', '0'], 'value': 47}]

    def test_swapped_labels_fail_even_when_node_tuples_preserved(self):
        s = score_draft('R2 1 0 1k\nR1 2 0 47\n.end', self.truth)
        self.assertEqual(s['labels_correct'], 0)
        self.assertTrue(s['node_tuples_preserved'])
        self.assertFalse(s['all_tasks_correct'])

    def test_known_values_and_duplicate_labels(self):
        s = score_draft('R1 1 0 1k\nR2 2 0 47\n.end', self.truth)
        self.assertEqual(s['labels_correct'], 2)
        self.assertEqual(s['values_correct'], 2)
        self.assertTrue(s['all_tasks_correct'])
        s = score_draft('R1 1 0 1k\nR1 2 0 47\n.end', self.truth)
        self.assertEqual(s['labels_correct'], 0)
        self.assertFalse(s['unique_refs'])

    def test_unknown_parameters_are_not_included_in_numeric_accuracy(self):
        truth = [{'id': 'Resistor_1', 'kind': 'R', 'ref': 'RC', 'nodes': ['1', '0'], 'value': None}]
        s = score_draft('R_C 1 0\n.end', truth)
        self.assertEqual(s['labels_correct'], 1)
        self.assertEqual(s['values_total'], 0)
        self.assertTrue(s['unknown_passives_not_invented'])
        self.assertFalse(score_draft('RC 1 0 1k\n.end', truth)['unknown_passives_not_invented'])


if __name__ == '__main__':
    unittest.main()
