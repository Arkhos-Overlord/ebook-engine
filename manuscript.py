"""Reading and writing chapter_NN.md files.

Shared by the CLI, the batch generator and the expander so that three
callers cannot disagree about the file layout — they previously did, and
`batch_generate` regenerating from the corpus wiped expanded chapters.
"""

import os
import re
from pathlib import Path

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
_FILENAME = re.compile(r"^chapter_(\d+)\.md$")


def read_chapters(book_dir) -> list:
    """Load chapter_NN.md files from a directory, recovering titles.

    Returns [] when the directory does not exist. Unrecognised filenames
    are skipped rather than raising, so a stray file cannot break a
    rebuild.
    """
    directory = Path(str(book_dir))
    if not directory.is_dir():
        return []

    chapters = []
    for filename in sorted(os.listdir(directory)):
        match = _FILENAME.match(filename)
        if not match:
            continue
        number = int(match.group(1))
        text = (directory / filename).read_text(encoding="utf-8")
        heading = _HEADING.search(text)
        if heading:
            title = heading.group(1).strip()
            body = text[heading.end() :].lstrip()
        else:
            title = f"Chapter {number}"
            body = text
        chapters.append({"number": number, "title": title, "content": body})
    return chapters


def write_chapter(book_dir, number: int, title: str, content: str) -> Path:
    """Write one chapter, keeping the previous version as chapter_NN.md.bak.

    The backup is what makes expansion recoverable when something
    regenerates the book underneath it.
    """
    directory = Path(str(book_dir))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"chapter_{number:02d}.md"
    if path.is_file():
        path.replace(path.with_suffix(".md.bak"))
    path.write_text(f"## {title}\n\n{content.strip()}", encoding="utf-8")
    return path


def backup_chapters(book_dir) -> list:
    """Copy every chapter_NN.md to .bak without touching the original."""
    directory = Path(str(book_dir))
    saved = []
    for chapter in read_chapters(directory):
        path = directory / f"chapter_{chapter['number']:02d}.md"
        backup = path.with_suffix(".md.bak")
        backup.write_bytes(path.read_bytes())
        saved.append(backup)
    return saved
