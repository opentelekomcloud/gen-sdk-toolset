# Scan examples

No example scan is committed — `repo_scan_example.json` was removed in #79 and
the JSON is generated on demand instead, so it cannot drift from the current
`RepositoryScanResult` shape.

Generate one (requires `GITHUB_TOKEN` in the environment or `.env`):

```bash
uv run gen-sdk-scan \
  --repo opentelekomcloud-docs/anti-ddos \
  --branch 8ff5254f6b7d669170bdacbdf5058e9adcfbe75f \
  --output docs/examples/repo_scan_example.json
```

Passing a full commit SHA through `--branch` makes the output reproducible;
`RepositoryScanResult.branch` carries a normal branch name in regular scans.
