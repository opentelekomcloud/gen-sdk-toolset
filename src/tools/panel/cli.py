import argparse
import json

from tools.panel.api.app import create_app


def _openapi_command() -> None:
    app = create_app()
    schema = app.openapi()
    print(json.dumps(schema, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(prog="panel")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("openapi", help="Print the OpenAPI schema to stdout.")

    args = parser.parse_args()
    if args.command == "openapi":
        _openapi_command()


if __name__ == "__main__":
    main()
