import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from preflight import audit


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "synthetic.csv"

    def put(self, text):
        self.source.write_bytes(text.encode("utf-8"))
        return self.source

    def test_multiline_bom_preserves_source_and_counts(self):
        self.put('\ufeffid,phone,tags,note\r\n001,000012,A;B,"line one\nline two"\r\n001,000012,A;B,"line one\nline two"\r\n002,+15550000000,,"comma, quoted"\r\n003,0000,A;A;Z,secret@example.test\r\n')
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        r = audit(self.source, tag_column="tags", tag_separator=";", allowed_tags=["A", "B"], id_column="id")
        for k, expected in dict(data_rows=4, exact_duplicate_rows=1, duplicate_id_rows=1,
                                untagged_rows=1, multi_tag_rows=3, unknown_tag_rows=1,
                                repeated_tag_rows=1, formula_like_cells=1).items():
            self.assertEqual(r[k], expected, k)
        self.assertEqual(before, r["source_sha256"])
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertNotIn("secret@example.test", json.dumps(r))
        self.assertNotIn("000012", json.dumps(r))

    def test_row_width_and_blank_record(self):
        r = audit(self.put('a,b\n1,2,3\n\n4\n'))
        self.assertEqual(r["malformed_width_rows"], 3)
        self.assertEqual(r["blank_rows"], 1)
        self.assertEqual(r["status"], "invalid")

    def test_bad_headers_rejected(self):
        for text in ['a,a\n1,2\n', 'a, a\n1,2\n', ',b\n1,2\n', '']:
            self.assertEqual(audit(self.put(text))["status"], "invalid")

    def test_bad_quotes_rejected(self):
        r = audit(self.put('a,b\n1,"unterminated\n'))
        self.assertIn("csv_parse_error", r["errors"])

    def test_encoding_size_and_nul(self):
        self.source.write_bytes(b'a\n\xff')
        self.assertIn("encoding_error", audit(self.source)["errors"])
        self.assertIn("input_size_limit", audit(self.put('a\n123'), max_bytes=2)["errors"])
        self.assertIn("nul_character", audit(self.put('a\n\x00'))["errors"])

    def test_configuration_is_explicit(self):
        self.put('id,tags\n0001,A;B\n')
        self.assertEqual(audit(self.source, tag_column="tags")["status"], "invalid")
        self.assertEqual(audit(self.source, id_column="missing")["status"], "invalid")

    def test_12000_rows_with_string_ids(self):
        with self.source.open('w', newline='') as f:
            w = csv.writer(f); w.writerow(['id', 'tags'])
            for i in range(12000):
                w.writerow([f'{i:08d}', 'A;B' if i % 2 else 'A'])
        r = audit(self.source, tag_column='tags', tag_separator=';', id_column='id')
        self.assertEqual(r['data_rows'], 12000)
        self.assertEqual(r['multi_tag_rows'], 6000)
        self.assertEqual(r['duplicate_id_rows'], 0)
        self.assertEqual(r['status'], 'structurally_valid')


if __name__ == '__main__':
    unittest.main()
