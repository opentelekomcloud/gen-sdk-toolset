# Scan examples

`repo_scan_example.json` is a real single-repository scan of
`opentelekomcloud-docs/anti-ddos` — one element of the org-wide report's
`repos[]`, produced by the scanner's single-repo mode.

Regenerate (requires `GITHUB_TOKEN` in the environment or `.env`):

```bash
uv run gen-sdk-scan \
  --repo opentelekomcloud-docs/anti-ddos \
  --branch 8ff5254f6b7d669170bdacbdf5058e9adcfbe75f \
  --output docs/examples/repo_scan_example.json
```

This committed example intentionally passes a full commit SHA through
`--branch` to make regeneration reproducible. `RepositoryScanResult.branch`
may contain a normal branch name in regular scans.
