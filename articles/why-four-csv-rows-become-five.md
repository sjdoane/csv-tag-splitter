# Why four CSV rows can become five

*Sam Doane · September 14, 2026*

I want a CSV split to answer a simple question: did every record go where the rules said it should? Comparing the input and output row counts seems like a reasonable check. It breaks as soon as a record belongs to two groups.

The synthetic example in this repository has four contacts:

| ID | Tags | Intended destination |
| --- | --- | --- |
| `001` | `North;Wholesale` | North and Wholesale |
| `002` | `North` | North |
| `003` | No tag | Untagged |
| `004` | `Wholesale` | Wholesale |

The correct result is two North rows, two Wholesale rows and one Untagged row. Five output rows from four inputs. Deduplicating those outputs by ID would remove an intended copy; insisting that the totals match would reject a correct run.

## Count destinations, not just records

For each input record, let `d` be the number of destinations assigned by the rules. The expected output count is the sum of those destination counts. Here it is `2 + 1 + 1 + 1 = 5`.

That equation makes the untagged policy part of the calculation. In this example, an untagged record has one destination: a separate file. If untagged records were silently skipped, the output count would fall to four. A naive input-versus-output check would pass precisely because one omission canceled one intended extra copy.

Even the correct expected total is insufficient. A missing North row and an extra Wholesale row could cancel each other. I would check the expected records in each destination, including multiplicity, rather than treat a matching grand total as proof. IDs alone are a poor substitute for that comparison if the input allows duplicate IDs.

The splitter's reconciliation report records counts and file hashes. Those are useful evidence about the files produced. A hash does not establish that the routing rule was the right rule. The worked fixture supplies a separate, inspectable expectation for that.

## Preserve the values while moving them

Routing is only half the job. ID `001` and phone number `000123` must stay text. Record `004` has a note containing a newline. Splitting the source into physical lines would turn that one logical record into two pieces.

This implementation uses Python's CSV parser and writer and keeps cell values as strings. Repeated copies preserve the source fields, including the original tag cell. The transformation changes which file contains a record; it does not infer types or repair the customer's data.

I prefer making ambiguous cases explicit. The rules can reject multi-tag or untagged records instead of distributing them. Unknown tags stop the run before an output directory is created. Otherwise a newly introduced tag could quietly disappear from a routine export.

## Distinguish a complete run from a partly written directory

The script requires a new output directory and writes a `COMPLETE` marker last, after the CSVs and reconciliation report. A downstream process should not consume a directory without that marker. This is an application-level completion signal, not a guarantee that every write survives a power failure.

Keeping those claims separate matters. The program can show what it wrote and whether it reached its final step. It cannot establish that a destination CRM will accept the files, or that a customer's intended business rule matches the supplied configuration.

You can reproduce the four-record example from the repository root:

```sh
python3 split.py examples/contacts.csv examples/rules.json example-output
python3 -m unittest discover -s . -v
```

Use a fresh output path on subsequent runs. The example is deliberately small enough to inspect each result. Before scaling a transformation to thousands of rows, I want that small example to demonstrate which extra copies are intentional, where unassigned records go, and which inputs should stop the run.
