import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from split import SplitError, split_file


class SplitAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.output = self.root/'input.csv', self.root/'output'
        self.rules = dict(tags=['A', 'B'], tag_column='tags', tag_separator=';',
                          columns=[['Phone', 'phone'], ['ID', 'id'], ['Notes', 'note'], ['Tags', 'tags']],
                          duplicates='retain', multi_tag='replicate', untagged='separate',
                          unknown_tags='reject', formula_like='preserve')

    def put(self, rows):
        with self.source.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f); w.writerow(['id', 'phone', 'tags', 'note']); w.writerows(rows)

    def read(self, number):
        with (self.output/f'group-{number:03d}.csv').open(newline='') as f:
            return list(csv.reader(f))

    def test_exact_handoff_values_routes_and_private_summary(self):
        a = ['001', '+15550000000', 'A;B;A', 'comma, quote " and\nnew line café']
        b = ['000', '000123', '', 'private@example.test']
        self.put([a, a, b])
        before = self.source.read_bytes()
        r = split_file(self.source, self.output, self.rules)
        header = ['Phone', 'ID', 'Notes', 'Tags']
        projected_a = [a[1], a[0], a[3], a[2]]
        self.assertEqual(self.read(1), [header, projected_a, projected_a])
        self.assertEqual(self.read(2), [header, projected_a, projected_a])
        self.assertEqual(self.read(3), [header, [b[1], b[0], b[3], b[2]]])
        self.assertEqual((r['input_rows'], r['output_rows'], r['duplicate_rows_retained']), (3, 5, 1))
        self.assertEqual(r['formula_like_cells_preserved'], 2)
        self.assertNotIn('private@example.test', json.dumps(r))
        self.assertEqual(before, self.source.read_bytes())
        self.assertTrue((self.output/'COMPLETE').exists())
        for file in r['files']:
            self.assertEqual(file['sha256'], hashlib.sha256((self.output/file['file']).read_bytes()).hexdigest())

    def test_unresolved_cases_leave_no_output(self):
        cases = [([['1','0','Z','']], {}, 'unknown_tag'),
                 ([['1','0','A;B','']], {'multi_tag':'reject'}, 'multi_tag'),
                 ([['1','0','','']], {'untagged':'reject'}, 'untagged'),
                 ([['1','0','A','=1+1']], {'formula_like':'reject'}, 'formula_like'),
                 ([['1','0','A','']]*2, {'duplicates':'reject'}, 'duplicate_row')]
        for rows, overrides, code in cases:
            self.put(rows)
            with self.assertRaisesRegex(SplitError, code):
                split_file(self.source, self.output, dict(self.rules, **overrides))
            self.assertFalse(self.output.exists())

    def test_invalid_structure_or_lossy_mapping_rejected(self):
        self.put([['1','0','A','']])
        with self.assertRaisesRegex(SplitError, 'rules_object_required'):
            split_file(self.source, self.output, [])
        bad = dict(self.rules, columns=self.rules['columns'][:-1])
        with self.assertRaisesRegex(SplitError, 'preserve_all'):
            split_file(self.source, self.output, bad)
        self.source.write_text('id,phone,tags,note\n1,0,A\n')
        with self.assertRaisesRegex(SplitError, 'row_width'):
            split_file(self.source, self.output, self.rules)
        self.assertFalse(self.output.exists())

    def test_no_overwrite_and_no_complete_on_write_failure(self):
        self.put([['1','0','A','']])
        self.output.mkdir(); marker = self.output/'existing'; marker.write_text('preserve')
        with self.assertRaises(FileExistsError):
            split_file(self.source, self.output, self.rules)
        self.assertEqual(marker.read_text(), 'preserve')
        other = self.root/'partial'
        with patch('split.os.open', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                split_file(self.source, other, self.rules)
        self.assertFalse((other/'COMPLETE').exists())

    def test_12000_rows_counts_order_and_determinism(self):
        self.put([[f'{i:08d}', '000123', 'A;B' if i%2 else 'A', ''] for i in range(12000)])
        first = split_file(self.source, self.output, self.rules)
        second = split_file(self.source, self.root/'replay', self.rules)
        self.assertEqual(first, second)
        self.assertEqual((first['input_rows'], first['output_rows']), (12000, 18000))
        self.assertEqual([row[1] for row in self.read(2)[1:]], [f'{i:08d}' for i in range(1,12000,2)])
        self.assertEqual(len(self.read(1))-1, 12000)


if __name__ == '__main__':
    unittest.main()
