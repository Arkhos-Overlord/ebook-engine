"""KDP packaging — bundle an EPUB and its assets for Amazon upload."""

import json
import logging
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

METADATA_NAME = "kdp_metadata.json"
LISTING_NAME = "kdp_listing.md"
README_NAME = "README.txt"


def create_kdp_package(
    epub_path,
    output_path=None,
    cover_path=None,
    metadata=None,
    listing_path=None,
) -> str:
    """Write a ZIP holding everything needed for a KDP upload.

    Args:
        epub_path: the generated EPUB (required).
        output_path: destination ZIP; defaults to <epub>.kdp.zip.
        cover_path: cover image to include alongside the book.
        metadata: dict serialised as kdp_metadata.json.
        listing_path: optional existing listing file to bundle.

    Returns the ZIP path. Raises FileNotFoundError if the EPUB is missing,
    so a failed EPUB build can never be recorded as a finished package.
    """
    epub = Path(str(epub_path))
    if not epub.is_file():
        raise FileNotFoundError(f"EPUB not found: {epub}")

    target = Path(str(output_path)) if output_path else epub.with_suffix(".kdp.zip")
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(epub, arcname=epub.name)

        cover = Path(str(cover_path)) if cover_path else None
        if cover and cover.is_file():
            zf.write(cover, arcname=cover.name)
        elif cover:
            log.warning("Cover not found, not bundled: %s", cover)

        if metadata:
            zf.writestr(
                METADATA_NAME,
                json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
            )

        listing = Path(str(listing_path)) if listing_path else None
        if listing and listing.is_file():
            zf.write(listing, arcname=listing.name)

        zf.writestr(
            README_NAME,
            _readme(epub.name, cover.name if (cover and cover.is_file()) else None),
        )

    log.info("KDP package written: %s", target)
    return str(target)


def _readme(epub_name: str, cover_name) -> str:
    lines = [
        "KDP upload package",
        "",
        f"1. Upload {epub_name} as the manuscript file.",
    ]
    if cover_name:
        lines.append(f"   The cover is embedded in the EPUB; {cover_name} is also")
        lines.append("   included here for the separate KDP cover upload.")
    lines += [
        "2. Check that title, author and description match the listing.",
        "",
        "The identifier inside the EPUB is deterministic for this title.",
    ]
    return "\n".join(lines) + "\n"
