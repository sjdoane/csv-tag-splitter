"""Local, explicit-rule CSV splitter. No network or automatic cleanup."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path


class SplitError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise SplitError(code)


def split_file(source, output, rules):
    # All record validation and serialization happen before creating output.
    require(isinstance(rules, dict), 'rules_object_required')
    with Path(source).open('rb') as handle:
        raw = handle.read(25_000_001)
    require(len(raw) <= 25_000_000, 'input_size_limit')
    require(rules.get('duplicates') in ('retain', 'reject'), 'duplicate_policy_required')
    require(rules.get('multi_tag') in ('replicate', 'reject'), 'multi_tag_policy_required')
    require(rules.get('untagged') in ('separate', 'reject'), 'untagged_policy_required')
    require(rules.get('formula_like') in ('preserve', 'reject'), 'formula_policy_required')
    require(rules.get('unknown_tags') == 'reject', 'unknown_tags_must_reject')
    separator = rules.get('tag_separator')
    require(isinstance(separator, str) and bool(separator), 'tag_separator_required')
    tags = rules.get('tags')
    require(isinstance(tags, list) and bool(tags) and
            all(isinstance(t, str) and t and t == t.strip() and separator not in t for t in tags),
            'invalid_tags')
    require(len(set(tags)) == len(tags), 'duplicate_configured_tags')
    columns = rules.get('columns')
    require(isinstance(columns, list) and bool(columns) and
            all(isinstance(c, list) and len(c) == 2 and
                all(isinstance(v, str) and v.strip() for v in c) for c in columns),
            'explicit_column_mapping_required')
    dest_headers, source_headers = zip(*columns)
    require(len(set(dest_headers)) == len(dest_headers), 'duplicate_destination_header')
    require(len(set(source_headers)) == len(source_headers), 'duplicate_source_mapping')
    try:
        decoded = raw.decode('utf-8-sig', errors='strict')
        require('\x00' not in decoded, 'nul_character')
        table = list(csv.reader(io.StringIO(decoded, newline=''), strict=True))
    except (UnicodeError, csv.Error):
        raise SplitError('invalid_utf8_csv') from None
    require(bool(table), 'empty_input')
    headers, rows = table[0], table[1:]
    require(bool(headers) and all(h.strip() for h in headers), 'blank_header')
    require(len({h.strip() for h in headers}) == len(headers), 'duplicate_header')
    require(set(source_headers) == set(headers), 'mapping_must_preserve_all_source_columns')
    require(rules.get('tag_column') in headers, 'tag_column_missing')
    indexes = [headers.index(h) for h in source_headers]
    tag_index = headers.index(rules['tag_column'])
    groups = [[] for _ in tags]
    tag_indexes = {tag: i for i, tag in enumerate(tags)}
    if rules['untagged'] == 'separate':
        groups.append([])
    seen, duplicates, multi, untagged, formulas = set(), 0, 0, 0, 0
    for row in rows:
        require(len(row) == len(headers), 'row_width_mismatch')
        key = tuple(row)
        duplicate = key in seen
        require(not duplicate or rules['duplicates'] == 'retain', 'duplicate_row_requires_decision')
        duplicates += duplicate
        seen.add(key)
        formula_count = sum(bool(v.lstrip()) and v.lstrip()[0] in '=+-@' for v in row)
        require(not formula_count or rules['formula_like'] == 'preserve', 'formula_like_requires_decision')
        formulas += formula_count
        row_tags = set(t.strip() for t in row[tag_index].split(separator) if t.strip())
        require(not (row_tags - set(tags)), 'unknown_tag_requires_decision')
        require(len(row_tags) <= 1 or rules['multi_tag'] == 'replicate', 'multi_tag_requires_decision')
        require(bool(row_tags) or rules['untagged'] == 'separate', 'untagged_requires_decision')
        multi += len(row_tags) > 1
        untagged += not row_tags
        destinations = sorted(tag_indexes[t] for t in row_tags) if row_tags else [len(tags)]
        for index in destinations:
            groups[index].append([row[i] for i in indexes])
    payloads = {}
    for i, group in enumerate(groups):
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\r\n')
        writer.writerow(dest_headers)
        writer.writerows(group)
        content = stream.getvalue()
        require(list(csv.reader(io.StringIO(content, newline=''))) == [list(dest_headers)] + group,
                'serialization_readback_mismatch')
        payloads[f'group-{i+1:03d}.csv'] = content.encode('utf-8')
    report = {'schema_version': 1, 'source_sha256': hashlib.sha256(raw).hexdigest(),
              'rules_sha256': hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest(),
              'input_rows': len(rows), 'output_rows': sum(map(len, groups)),
              'duplicate_rows_retained': duplicates, 'multi_tag_rows': multi,
              'untagged_rows': untagged, 'formula_like_cells_preserved': formulas,
              'files': [{'file': name, 'rows': len(groups[i]),
                         'sha256': hashlib.sha256(data).hexdigest()}
                        for i, (name, data) in enumerate(payloads.items())]}
    payloads['reconciliation.json'] = (json.dumps(report, indent=2) + '\n').encode()
    out = Path(output)
    out.mkdir(mode=0o700)  # Exclusive: never overwrite a previous delivery directory.
    for name, data in payloads.items():
        fd = os.open(str(out / name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
    # Written last: missing COMPLETE means a failed/partial write, never a deliverable.
    fd = os.open(str(out / 'COMPLETE'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('rules', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        report = split_file(args.input, args.output, json.loads(args.rules.read_text()))
    except (SplitError, OSError, ValueError, TypeError) as error:
        print(json.dumps({'status': 'failed', 'code': str(error) if isinstance(error, SplitError)
                          else type(error).__name__}))
        return 2
    print(json.dumps({'status': 'complete_local_split', 'input_rows': report['input_rows'],
                      'output_rows': report['output_rows']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
