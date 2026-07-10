# Scan examples

`repo_scan_example.json` is a real single-repository scan of
`opentelekomcloud-docs/anti-ddos` — one element of the org-wide report's
`repos[]`, produced by the scanner's single-repo mode.

Regenerate (requires `GITHUB_TOKEN` in the environment or `.env`):

    python -m tools.scanner --repo opentelekomcloud-docs/anti-ddos --output docs/examples/repo_scan_example.json
