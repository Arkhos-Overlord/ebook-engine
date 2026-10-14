"""Filesystem naming helpers shared by the CLI and the batch generator.

The two callers used to name artifacts differently — `publish` produced
`Digital Marketing.epub` from the raw title while `batch_generate` produced
`digital-marketing.epub` — so running both left two copies of every book
and a catalog that pointed at whichever ran last. `batch_generate` also
carried its own inline slug that never stripped path separators.

Both now go through these two functions.
"""

import re
from pathlib import Path

_RESERVED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slug(text: str) -> str:
    """Directory- and file-safe slug.

    Keeps the names earlier runs already produced (spaces to dashes, case
    preserved) while neutralising separators, so a title containing `/`
    can never escape the output directory.
    """
    result = text.lower().replace(" ", "-").replace("/", "-").replace("\\", "-")
    return result or "untitled"


def safe_filename(name: str, suffix: str = "") -> str:
    """Strip characters Windows and POSIX refuse in file names."""
    cleaned = _RESERVED.sub("-", name).strip(" .")
    return f"{cleaned or 'untitled'}{suffix}"


def artifact_path(output_dir, title: str, extension: str) -> str:
    """Path for a generated artifact: `<slug>.<extension>`.

    The single call site both the CLI and the batch use, so an extension
    passed as `.epub` or `epub` lands in the same place either way.
    """
    ext = extension if extension.startswith(".") else f".{extension}"
    return str(Path(output_dir) / f"{slug(title)}{ext}")
