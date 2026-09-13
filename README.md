# CSV tag splitter

Split a contact export into tag groups without turning `001` into `1`, dropping multiline notes, or silently discarding unassigned records.

This is an independent Python work sample by Sam Doane. It demonstrates a small, auditable data-transformation workflow with explicit rules and a reconciliation report. The included data is synthetic; this is not a commissioned project or a certified CRM importer.

## Need an export prepared for import?

I offer fixed-price CSV preparation starting at **$75 USD**, with the final scope and price confirmed before a contract starts. A typical small task is one UTF-8 CSV of up to 12,000 rows and 25 MB, split into up to ten groups using one tag column, with columns mapped to your supplied template.

You receive the output CSVs, a row-count and file-hash reconciliation report, the agreed transformation rules, and one correction round for those rules. The original export stays unchanged. This scope excludes finding contact details, merging conflicting records, inventing missing values, logging into your CRM, or guaranteeing that a destination system will accept the files.

[Contact Sam on Upwork](https://www.upwork.com/freelancers/~0178ba22c34ac67dda) with the destination headers, your grouping rules, and a small redacted or synthetic example. We agree on feasibility, acceptance checks, turnaround, data handling and funding before work starts. Please do not send a full customer export with your first message or put private data in a GitHub issue. I use automation and AI coding assistance; the delivered files are checked against the agreed rules.

## Try the example

Python 3 and the standard library are sufficient; no packages or accounts are needed. Run from the repository directory:

```sh
python3 preflight.py examples/contacts.csv --tag-column tags --tag-separator ';' --id-column id --allowed-tag North --allowed-tag Wholesale
python3 split.py examples/contacts.csv examples/rules.json example-output
python3 -m unittest discover -s . -v
```

The example has four source records. One belongs to both groups, so the outputs contain five records in total:

| Output | Group | Records |
| --- | --- | ---: |
| `group-001.csv` | North | 2 |
| `group-002.csv` | Wholesale | 2 |
| `group-003.csv` | Untagged | 1 |

`reconciliation.json` records the input/output counts and SHA-256 hashes. `COMPLETE` is written last. If that marker is absent, treat the output as an incomplete run. It is an application marker, not a power-loss durability guarantee. Each run requires a new output directory; existing files are never overwritten.

## What the rules control

`examples/rules.json` names the tag column, separator, allowed tags, and destination headers. Each column pair is `[destination header, source header]`. Every source column must appear exactly once.

- Values stay strings. Source row order is preserved within each group.
- Tag matching is case-sensitive and trims surrounding whitespace. Repeated tags route a record only once to each group; the original cell is unchanged.
- Multi-tag records can be replicated or rejected. Untagged records can go to a separate group or be rejected.
- Exact duplicate rows can be retained or rejected. The splitter does not merge records by ID or guess which record is correct.
- Unknown tags and malformed records stop the run before the output directory is created.
- Formula-like cells can be rejected or preserved explicitly. Preservation does not make an untrusted CSV safe to open in a spreadsheet; plus-prefixed phone numbers may also trigger this check.

## Boundaries and verification

Input is comma-delimited UTF-8, with an optional BOM, limited to 25 MB. Outputs are UTF-8 without a BOM with CRLF record separators. Processing is in memory. Files remain local: neither script makes network requests, uploads data, or modifies the source file. New output files request owner-only permissions; the operating system determines the effective protection.

Preflight reports structural issues and aggregate counts. An exit code of zero means the structure was readable, not that duplicate, tag, or destination requirements have been accepted. Reconciliation reports omit contact values, but reports and rules should still be treated as private when used with real data.

The test suite covers leading zeros, quoted and multiline fields, duplicate/tag policies, malformed input, source preservation, output hashes, non-overwrite, failed writes, and deterministic 12,000-row examples. These are synthetic checks, not evidence of compatibility with a particular CRM.

For a scoped export-cleanup task, the starting point is a redacted sample, the destination template, and agreed rules for ambiguous records. Share those privately through the platform where we connected; do not post customer data in GitHub issues. Real-data processing, acceptance checks, and retention need to be agreed before work begins.
