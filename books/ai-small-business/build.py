"""Build the AI for Small Business Owners manuscript into EPUB + PDF + KDP zip.

This is a manifest for one book: it reads `manuscript/*.md`, renders this
book's bespoke cover, and delegates the EPUB and PDF work to the engine's
formatters. Doing that means the known-good output is produced by the same
code path as every other book, instead of a private second implementation.

Fixes over the original:
  * it ran the entire build on import (no `__main__` guard)
  * `esc()` replaced every character with itself and unescaped first, so
    raw markup reached ReportLab's XML-based Paragraph
  * BASE was a hardcoded absolute path
  * fonts were hardcoded to four Windows paths
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

# Allow running as a plain script: find the directory that contains the
# `ebook_engine` package and put it on sys.path.
if __package__ in (None, ""):
    for _ancestor in Path(__file__).resolve().parents:
        if (_ancestor / "ebook_engine" / "__init__.py").is_file():
            sys.path.insert(0, str(_ancestor))
            break

from ebook_engine.cover_engine import FONT_PATHS, get_font
from ebook_engine.formatters.epub_formatter import create_epub
from ebook_engine.formatters.kdp_zip import create_kdp_package
from ebook_engine.formatters.pdf_formatter import create_pdf
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
MANUSCRIPT = BASE / "manuscript"
OUTPUT = BASE / "output"
METADATA = BASE / "kdp_metadata.json"

TITLE = "AI for Small Business Owners"
SUBTITLE = (
    "How to Use ChatGPT and AI Tools to Automate the Work You Hate, "
    "Reclaim Ten Hours a Week, and Grow Without Hiring"
)
AUTHOR = "Jordan Vale"
PUBLISHER = "Vale Press"


def load_chapters() -> list:
    """Read the manuscript into chapter dicts for the formatters.

    The title comes from the document's first `#` heading; the body is the
    rest of the markdown, passed through untouched so the formatters'
    own escaping and conversion applies.
    """
    chapters = []
    for index, path in enumerate(sorted(MANUSCRIPT.glob("*.md")), start=1):
        raw = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^#\s+(.+?)\s*$", raw)
        if match:
            title = match.group(1).strip()
            body = raw[match.end() :].lstrip()
        else:
            title = path.stem.replace("_", " ").title()
            body = raw
        chapters.append({"number": index, "title": title, "content": body})
    if not chapters:
        raise FileNotFoundError(f"No markdown manuscript found in {MANUSCRIPT}")
    return chapters


def book_data(chapters: list, cover_path: Path) -> dict:
    description = ""
    if METADATA.is_file():
        meta = json.loads(METADATA.read_text(encoding="utf-8"))
        # kdp_metadata holds HTML; the PDF wants plain text.
        description = re.sub(r"<[^>]+>", " ", meta.get("description_html", ""))
        description = re.sub(r"\s+", " ", description).strip()
    return {
        "topic": TITLE,
        "genre": "Business",
        "author": AUTHOR,
        "description": description or SUBTITLE,
        "cover_path": str(cover_path),
        "chapters": chapters,
    }


def _system_font(*candidates: str):
    """First readable candidate, else a font the engine already resolves."""
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, 1)
            except OSError:
                continue
    resolved = FONT_PATHS and next((p for p in FONT_PATHS if Path(p).is_file()), None)
    if resolved:
        try:
            return ImageFont.truetype(resolved, 1)
        except OSError:
            pass
    return ImageFont.load_default()


def _font(size: int, *candidates: str):
    for candidate in candidates:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return get_font(size)


def _wrap(draw, font, text: str, max_width: int) -> list:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def build_cover() -> Path:
    """Render this book's bespoke cover. Returns the path written.

    Kept here rather than delegated to the generic engine cover: this is
    the book's own art direction, tied to its KDP listing.
    """
    width, height = 1600, 2560
    background = (16, 24, 40)
    accent = (240, 184, 74)
    white = (243, 243, 240)
    muted = (150, 160, 178)

    img = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(img)
    for x in range(80, width, 160):
        for y in range(80, height, 160):
            if (x // 160 + y // 160) % 3 == 0:
                draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(30, 42, 66))
    draw.rectangle([120, 300, 480, 316], fill=accent)

    f_big = _font(150, r"C:\Windows\Fonts\georgiab.ttf", "C:/Windows/Fonts/arialbd.ttf")
    f_sub = _font(66, r"C:\Windows\Fonts\georgia.ttf", "C:/Windows/Fonts/arial.ttf")
    f_tag = _font(54, r"C:\Windows\Fonts\segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf")
    f_auth = _font(58, r"C:\Windows\Fonts\segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf")
    f_ai = _font(320, r"C:\Windows\Fonts\georgiab.ttf", "C:/Windows/Fonts/arialbd.ttf")

    draw.text((120, 380), "AI", font=f_ai, fill=accent)

    y = 760
    for line in _wrap(draw, f_big, "for Small Business", 1360):
        draw.text((120, y), line, font=f_big, fill=white)
        y += 170
    for line in _wrap(draw, f_big, "Owners", 1360):
        draw.text((120, y), line, font=f_big, fill=white)
        y += 190

    draw.rectangle([120, y + 30, 1480, y + 36], fill=(40, 54, 84))
    y += 90
    for line in _wrap(draw, f_sub, SUBTITLE, 1360):
        draw.text((120, y), line, font=f_sub, fill=muted)
        y += 88

    draw.rectangle([0, height - 330, width, height], fill=(11, 17, 30))
    draw.text((120, height - 250), "TEN HOURS A WEEK. BACK.", font=f_tag, fill=accent)
    draw.text((120, height - 150), AUTHOR.upper(), font=f_auth, fill=white)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    cover_path = OUTPUT / "cover_1600x2560.png"
    img.save(cover_path)
    img.resize((600, 900)).save(OUTPUT / "cover_thumb_600x900.png")
    print(f"cover OK   {cover_path.name}")
    return cover_path


def main() -> None:
    chapters = load_chapters()
    print(f"manuscript OK  {len(chapters)} chapters")

    cover = build_cover()
    data = book_data(chapters, cover)

    epub_path = OUTPUT / f"{TITLE}.epub"
    create_epub(data, str(epub_path))
    print(f"epub OK    {epub_path.name} ({epub_path.stat().st_size} bytes)")

    pdf_path = OUTPUT / f"{TITLE}.pdf"
    create_pdf(data, str(pdf_path))
    print(f"pdf OK     {pdf_path.name} ({pdf_path.stat().st_size} bytes)")

    zip_path = create_kdp_package(
        str(epub_path),
        output_path=str(OUTPUT / f"{TITLE}.kdp.zip"),
        cover_path=str(cover),
        metadata=json.loads(METADATA.read_text(encoding="utf-8")) if METADATA.is_file() else None,
        listing_path=BASE / "kdp_listing.md",
    )
    print(f"kdp OK     {Path(zip_path).name}")
    print(f"rights     {date.today().year} {AUTHOR}")


if __name__ == "__main__":
    main()
