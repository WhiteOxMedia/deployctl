"""deployctl CLI package."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deployctl.cmd import cli as cli

__all__ = ["cli"]


def __getattr__(name: str) -> object:
    """Import ``cli`` on first access.

    Importing it eagerly here would put ``deployctl.cmd.cli`` in ``sys.modules``
    before runpy executes ``python -m deployctl.cmd.cli``, which makes Python
    emit a RuntimeWarning about the module already being imported.
    """
    if name == "cli":
        # importlib rather than ``from deployctl.cmd import cli``: a from-import
        # would read this package's attribute and recurse back into here.
        return importlib.import_module(f"{__name__}.cli")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
