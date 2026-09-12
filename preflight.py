"""Read-only CSV intake audit. Reports counts, never field values or contact details."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


def audit(path, *, encoding="utf-8-sig", delimiter=",", tag_column=None,
          tag_separator=None, allowed_tags=None, id_column=None, max_bytes=25_000_000):
    result = {"schema_version": 1, "status": "needs_review", "errors": [],
              "data_rows": 0, "valid_width_rows": 0, "malformed_width_rows": 0,
              "blank_rows": 0, "exact_duplicate_rows": 0, "blank_id_rows": 0,
              "duplicate_id_rows": 0, "untagged_rows": 0, "multi_tag_rows": 0,
              "unknown_tag_rows": 0, "repeated_tag_rows": 0,
              "formula_like_cells": 0}
    def fail(code):
        result["errors"].append(code)
        result["status"] = "invalid"
        return result
    if len(delimiter) != 1 or (tag_column is not None and not tag_separator):
        return fail("explicit_valid_delimiters_required")
    try:
        with Path(path).open("rb") as f:
            raw = f.read(max_bytes + 1)
    except OSError:
        return fail("input_unreadable")
    if len(raw) > max_bytes:
        return fail("input_size_limit")
    result.update(source_sha256=hashlib.sha256(raw).hexdigest(), source_bytes=len(raw))
    try:
        decoded = raw.decode(encoding, errors="strict")
    except (UnicodeError, LookupError):
        return fail("encoding_error")
    if "\x00" in decoded:
        return fail("nul_character")
    reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=delimiter, strict=True)
    try:
        headers = next(reader)
    except StopIteration:
        return fail("empty_file")
    except csv.Error:
        return fail("csv_parse_error")
    result["column_count"] = len(headers)
    if not headers or any(not h.strip() for h in headers):
        return fail("blank_header")
    if len(set(headers)) != len(headers) or len({h.strip() for h in headers}) != len(headers):
        return fail("duplicate_header")
    for field in (tag_column, id_column):
        if field is not None and field not in headers:
            return fail("configured_column_missing")
    ti = headers.index(tag_column) if tag_column is not None else None
    ii = headers.index(id_column) if id_column is not None else None
    known = set(allowed_tags) if allowed_tags is not None else None
    seen_rows, seen_ids = set(), set()
    try:
        for row in reader:
            result["data_rows"] += 1
            if not row:
                result["blank_rows"] += 1
            if len(row) != len(headers):
                result["malformed_width_rows"] += 1
                continue
            result["valid_width_rows"] += 1
            # Hashes stay in memory only; no record-level hashes leave the process.
            key = hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).digest()
            result["exact_duplicate_rows"] += int(key in seen_rows)
            seen_rows.add(key)
            result["formula_like_cells"] += sum(
                bool(v.lstrip()) and v.lstrip()[0] in "=+-@" for v in row)
            if ii is not None:
                identifier = row[ii]
                if not identifier.strip():
                    result["blank_id_rows"] += 1
                else:
                    key = hashlib.sha256(identifier.encode()).digest()
                    result["duplicate_id_rows"] += int(key in seen_ids)
                    seen_ids.add(key)
            if ti is not None:
                tags = [t.strip() for t in row[ti].split(tag_separator) if t.strip()]
                unique = set(tags)
                result["untagged_rows"] += int(not unique)
                result["multi_tag_rows"] += int(len(unique) > 1)
                result["repeated_tag_rows"] += int(len(tags) != len(unique))
                result["unknown_tag_rows"] += int(known is not None and bool(unique - known))
    except csv.Error:
        return fail("csv_parse_error")
    if result["malformed_width_rows"]:
        return fail("row_width_mismatch")
    result["status"] = "structurally_valid"
    result["acceptance_note"] = "Structural check only. Buyer mapping, duplicate, tag and retention rules still require agreement."
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("--encoding", default="utf-8-sig")
    ap.add_argument("--delimiter", default=",")
    ap.add_argument("--tag-column")
    ap.add_argument("--tag-separator")
    ap.add_argument("--id-column")
    ap.add_argument("--allowed-tag", action="append")
    args = ap.parse_args()
    report = audit(args.input, encoding=args.encoding, delimiter=args.delimiter,
                   tag_column=args.tag_column, tag_separator=args.tag_separator,
                   id_column=args.id_column, allowed_tags=args.allowed_tag)
    print(json.dumps(report, indent=2))
    return 2 if report["status"] == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
