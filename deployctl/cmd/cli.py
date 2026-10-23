"""deployctl CLI entry point."""

from __future__ import annotations

import argparse

from deployctl.app.server import run_dev


def main(argv: list[str] | None = None) -> int:
    """Deployctl CLI."""
    parser = argparse.ArgumentParser(prog="deployctl")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("server", help="run the control plane server")
    subparsers.add_parser("worker", help="run a background worker")
    subparsers.add_parser("migrate", help="run database migrations")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "server":
        run_dev()
        return 0

    # worker / migrate are placeholders for now
    print(f"deployctl {args.command}: not implemented yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
