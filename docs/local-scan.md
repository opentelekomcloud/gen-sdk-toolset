# Checking API reference docs locally

The scanner lists documentation errors it detects reliably in a local copy of
a docs repository. It does not catch everything, so review your changes too.

## Setup

Requires [uv](https://docs.astral.sh/uv/). No GitHub token is needed.

```bash
git clone git@github.com:opentelekomcloud/gen-sdk-toolset.git
cd gen-sdk-toolset
uv sync
```

## Run

From the `gen-sdk-toolset` folder:

```bash
uv run gen-sdk-scan --path ../identity-access-management-5 > report.md
```

`--path` is a cloned docs repository. Files are read as they are on disk, so
uncommitted edits are scanned too; the report says when there are any. The
markdown report goes to stdout. `scan-output.json` with raw scanner
diagnostics is written as well; it is for the toolset team.

## What it reports

Each row gives the file, the section (`body`, `response`, `example_response`,
…) and the place in it (`row 3`, a parameter name, `example 1`).

| Problem | Example |
| --- | --- |
| Example is not valid JSON (line and column inside the example) | trailing comma, missing comma, comment |
| Type is a table reference | `Table 3` instead of `Object` / `Array of objects` |
| Type contains an internal marker | `REFERENCE`, `ARRAY_REFERENCE` |
| Type column contains a description | `User token from IAM` |
| Type is not a known type | `Interger`, `objects` |
| Parameter does not match the path placeholder | `flavors_id` for `{flavor_id}` |
| Field links to a whole page instead of a table | reference to a page label |
| Empty or broken code-block directive | `.. code-block:: text` with no content |

`--path` cannot be combined with `--repo`, `--branch`, `--stdout` or
`--output -`.
