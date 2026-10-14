"""Shared rich console with Windows-safe output encoding.

Windows consoles default to cp1252, which cannot encode astral-plane glyphs
(the book/chart emoji) or the rupee sign used in price output. rich raises
UnicodeEncodeError on those, which crashed `generate`, `stats` and any `list`
that showed a price. Force UTF-8 with replacement so unsupported characters
degrade instead of aborting the command.
"""

import sys

from rich.console import Console


def _force_utf8(stream) -> None:
    try:
        if stream is None or not hasattr(stream, "reconfigure"):
            return
        encoding = (stream.encoding or "").lower().replace("_", "-")
        if encoding not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


_force_utf8(sys.stdout)
_force_utf8(sys.stderr)

console = Console()
