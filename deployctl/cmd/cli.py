"""deployctl CLI entry point."""

from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> int:
    """Deployctl CLI."""
    parser = argparse.ArgumentParser(prog="deployctl")
    subparsers = parser.add_subparsers(dest="command")

    server_parser = subparsers.add_parser("server", help="run the control plane server")
    server_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface to bind (default: 127.0.0.1)",
    )
    server_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port to bind (default: 8000)",
    )
    subparsers.add_parser("worker", help="run a background worker")
    subparsers.add_parser("migrate", help="run database migrations")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "server":
        uvicorn.run(
            "deployctl.app.server:create_app",
            factory=True,
            host=args.host,
            port=args.port,
        )
        return 0

    # worker / migrate are placeholders for now
    print(f"deployctl {args.command}: not implemented yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
