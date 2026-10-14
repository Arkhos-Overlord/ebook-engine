"""Gumroad packaging — bundle a book for direct sale.

Gumroad and KDP need different things:

  KDP      one reflowable EPUB, cover embedded, plus a metadata sheet for
           Amazon's upload form. One file to upload.
  Gumroad  a downloadable bundle. Buyers expect both formats, the cover
           used as the listing image, and a plain-text description they
           can paste into the product page — plus a preview file so they
           can read a sample before buying.
"""

import json
import logging
import re
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

PRODUCT_NAME = "product.json"
README_NAME = "README.txt"
PREVIEW_NAME = "preview"


def create_gumroad_package(
    epub_path,
    output_path=None,
    pdf_path=None,
    cover_path=None,
    product=None,
    listing_path=None,
    preview_chapter=None,
) -> str:
    """Write a ZIP suitable for upload to Gumroad.

    Args:
        epub_path: the EPUB (required — it is the primary file).
        output_path: destination ZIP; defaults to `<epub>.gumroad.zip`.
        pdf_path: optional PDF to include alongside the EPUB.
        cover_path: cover image, used as the Gumroad listing artwork.
        product: dict of listing fields (title, subtitle, description,
            price, price_inr, tags, author, url).
        listing_path: optional existing markdown listing to bundle.
        preview_chapter: optional markdown/text sample to include so
            buyers can read before purchasing.

    Returns the ZIP path. Raises FileNotFoundError if the EPUB is missing
    so a failed build can never be recorded as a finished package.
    """
    epub = Path(str(epub_path))
    if not epub.is_file():
        raise FileNotFoundError(f"EPUB not found: {epub}")

    target = Path(str(output_path)) if output_path else epub.with_suffix(".gumroad.zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = dict(product or {})
    title = str(data.get("title") or epub.stem)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(epub, arcname=epub.name)

        pdf = Path(str(pdf_path)) if pdf_path else None
        if pdf and pdf.is_file():
            zf.write(pdf, arcname=pdf.name)
        elif pdf:
            log.warning("PDF not found, not bundled: %s", pdf)

        cover = Path(str(cover_path)) if cover_path else None
        if cover and cover.is_file():
            zf.write(cover, arcname=cover.name)
            data.setdefault("cover_file", cover.name)
        elif cover:
            log.warning("Cover not found, not bundled: %s", cover)

        if listing_path:
            listing = Path(str(listing_path))
            if listing.is_file():
                zf.write(listing, arcname=listing.name)

        if preview_chapter:
            zf.writestr(
                f"{PREVIEW_NAME}.txt",
                _as_plain_text(str(preview_chapter)),
            )
            data.setdefault("preview_file", f"{PREVIEW_NAME}.txt")

        data.setdefault("title", title)
        if data.get("description"):
            # Gumroad's description box takes text/HTML the seller pastes;
            # ship a plain-text copy next to the structured record.
            zf.writestr("description.txt", str(data["description"]).strip() + "\n")

        zf.writestr(
            PRODUCT_NAME,
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
        )
        zf.writestr(README_NAME, _readme(title, epub.name, pdf and pdf.is_file()))

    log.info("Gumroad package written: %s", target)
    return str(target)


def _as_plain_text(content: str) -> str:
    """Markdown-ish sample stripped down to readable plain text."""
    text = re.sub(r"(?m)^#{1,6}\s*", "", content)
    text = re.sub(r"(?m)^>\s?", "", text)
    text = re.sub(r"[*_`]{1,3}", "", text)
    return text.strip() + "\n"


def _readme(title: str, epub_name: str, has_pdf: bool) -> str:
    lines = [
        f"Thank you for buying {title}.",
        "",
        "Your files:",
        f"  - {epub_name}  (e-reader: Kindle via Send-to-Kindle, Kobo, Apple Books)",
    ]
    if has_pdf:
        lines.append("  - the PDF edition (read anywhere, print if you like)")
    lines += [
        "",
        "The cover image is included for your reference.",
        "",
        "If anything is missing or unreadable, reply to your Gumroad receipt "
        "and it will be sorted out.",
    ]
    return "\n".join(lines) + "\n"
