# gen_sdk_tooling

Automated Python SDK generation from OTC API documentation.

## Setup

```bash
# Clone
git clone git@github.com:opentelekomcloud/gen-sdk-toolset.git
cd gen-sdk-toolset

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## Configuration

1. Create GitHub personal access token:
   - Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
   - Generate new token with "Public repositories (read-only)" access

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Add your token to `.env`:
```
GITHUB_TOKEN=ghp_your_token_here
```

## Usage

Scan a repository to classify RST files (endpoint vs non-endpoint):

```bash
python -m tools.main
```

## Development

```bash
# Run tests
pytest

# Lint
ruff check src/
ruff format src/
```
