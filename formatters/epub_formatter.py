"""EPUB formatter — generate KDP-compliant EPUB3 files."""

import datetime
import html
import logging
import mimetypes
import re
import uuid
from pathlib import Path

import markdown
from ebooklib import epub

from ebook_engine.config import TEMPLATES_DIR
from ebook_engine.formatters.matter import (
    back_matter,
    collapse_escapes,
    front_matter,
)

log = logging.getLogger(__name__)

_NS = uuid.NAMESPACE_URL
_CSS_PATH = TEMPLATES_DIR / "epub.css"
_DEFAULT_CSS = (
    "body { font-family: Georgia, serif; font-size: 1.15em; "
    "line-height: 1.6; text-align: justify; }\n"
    "h1 { color: #101828; font-size: 1.7em; }\n"
    "h2 { color: #101828; font-size: 1.3em; }\n"
)


def slugify(text: str) -> str:
    """Stable slug used for the book identifier."""
    slug = text.lower().replace(" ", "-").replace("/", "-").replace("\\", "-")
    return slug or "untitled"


_IMAGE_MD = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_PLACEHOLDER = "%%IMG:{key}%%"


def _register_images(book: epub.EpubBook, chapters, images_base) -> dict:
    """Find every markdown image reference and attach it to the EPUB.

    Returns {original_reference: (epub_filename, alt_text)}. A reference whose
    file is missing is left out of the map, so the markdown that used it is
    stripped rather than rendering a broken image tag.
    """
    if not images_base:
        return {}
    base = Path(str(images_base))
    found: dict = {}
    for ch in chapters:
        for alt, ref in _IMAGE_MD.findall(str(ch.get("content") or "")):
            if ref not in found or (alt and not found[ref]):
                found[ref] = alt
    if not found:
        return {}

    out: dict = {}
    for ref, alt in found.items():
        path = (base / ref).resolve()
        if not path.is_file():
            log.warning("Chapter image not found: %s (referenced as %s)", path, ref)
            continue
        ext = (path.suffix.lstrip(".").lower()) or "png"
        uid = "img_" + re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
        name = f"{uid}.{ext}"
        mime = mimetypes.guess_type(path.name)[0] or f"image/{ext}"
        book.add_item(
            epub.EpubImage(uid=uid, file_name=name, media_type=mime, content=path.read_bytes())
        )
        out[ref] = (name, alt)
    if out:
        log.debug("attached %d chapter image(s)", len(out))
    return out


def _expand_images(text: str, images: dict) -> str:
    """Swap markdown image syntax for placeholders markdown will pass through."""
    if not images:
        return _IMAGE_MD.sub("", text)
    key = {ref: ref for ref in images}
    return _IMAGE_MD.sub(
        lambda m: _PLACEHOLDER.format(key=key.get(m.group(2), "")) if m.group(2) in key else "",
        text,
    )


def _inject_images(converted: str, images: dict) -> str:
    """Replace placeholders with real figure markup after markdown conversion.

    Runs on the converted HTML rather than before, because `_to_html` escapes
    the source: raw <figure> in the markdown would arrive as literal text.
    """
    for ref, (name, alt) in images.items():
        caption = f"<figcaption>{html.escape(alt)}</figcaption>" if alt else ""
        alt_attr = html.escape(alt, quote=True) if alt else name
        # Chapter documents and EpubImage items are siblings under EPUB/,
        # so the reference is a bare filename. Prefixing "../" resolves one
        # level above the archive and every reader renders a broken image.
        figure = f'<figure class="chart"><img src="{name}" alt="{alt_attr}"/>{caption}</figure>'
        converted = converted.replace(f"<p>{_PLACEHOLDER.format(key=ref)}</p>", figure)
        converted = converted.replace(_PLACEHOLDER.format(key=ref), figure)
    return converted


def _valid_isbn(value) -> str:
    """Return the ISBN only if it is a real, correctly-checksummed ISBN-13.

    KDP rejects an EPUB whose identifier claims to be an ISBN but is not one:
    a short number, a mistyped digit, or an unassigned GS1 prefix all fail at
    ingest. An unassigned prefix is impossible to detect from the digits
    alone, so the real remedy is to not supply one -- KDP assigns a free ISBN
    at upload. Until then the book carries a deterministic UUID, which is a
    legitimate EPUB unique identifier.
    """
    digits = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    if not re.fullmatch(r"97[89][0-9]{10}", digits):
        return ""
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits))
    return digits if total % 10 == 0 else ""


def _to_html(text: str, images: dict | None = None) -> str:
    """Escape source prose, then markdown-convert it.

    The source is untrusted plain text, so `<` and `&` must never reach the
    XHTML as raw markup. Escaping before conversion means markdown's own
    tags are added afterwards and stay intact, while any literal ampersand
    or angle bracket in the prose becomes an entity that survives the
    strict XML parse an EPUB requires.

    markdown escapes a second time inside spans it treats verbatim (an
    inline code span turns our `&amp;` into `&amp;amp;`), so the result is
    collapsed back to a single level of escaping.
    """
    source = _expand_images(text, images or {})
    converted = markdown.markdown(html.escape(source, quote=False), extensions=["extra"])
    converted = collapse_escapes(converted)
    return _inject_images(converted, images or {})


def _document(title: str, body: str) -> str:
    """Wrap body in the minimal document ebooklib expects.

    Deliberately namespace-free and without an XML declaration: ebooklib
    extracts the body with `tree.find("body")`, which only matches an
    un-namespaced tag. Declaring the XHTML namespace made that lookup miss,
    raising TypeError inside ebooklib's error handler and yielding an
    empty document for every chapter.
    """
    safe_title = html.escape(title, quote=True)
    # The stylesheet link is not written here: EpubHtml.add_item() injects
    # it into the head, and adding both would emit a duplicate <link>.
    return (
        f"<html><head><title>{safe_title}</title></head>"
        f"<body><h1>{safe_title}</h1>\n{body}\n</body></html>"
    )


def create_epub(book_data: dict, output_path: str) -> str:
    """Create an EPUB3 file from book data. Returns the output path.

    The spine is built from the chapter objects themselves rather than from
    file-name stems: ebooklib assigns its own item ids, so hardcoding names
    like `chapter_01` produced idrefs that pointed at nothing (every one of
    the 15 pre-existing books had an unresolvable spine).
    """
    topic = book_data["topic"]
    chapters = book_data.get("chapters") or []
    if not chapters:
        raise ValueError(f"Cannot build an EPUB for '{topic}': no chapters")

    book = epub.EpubBook()

    # Deterministic identity: rebuilding the same title must not mint a new
    # identifier, but the id must not be the raw title either.
    identifier = _valid_isbn(book_data.get("isbn")) or str(
        uuid.uuid5(_NS, "ebook:" + slugify(topic))
    )
    book.set_identifier(identifier)
    book.set_title(topic)
    book.set_language("en-IN")
    book.add_author(book_data.get("author") or "Anonymous")
    if book_data.get("description"):
        book.add_metadata("DC", "description", book_data["description"])
    if book_data.get("publisher"):
        book.add_metadata("DC", "publisher", book_data["publisher"])
    if book_data.get("subtitle"):
        book.add_metadata("DC", "subtitle", book_data["subtitle"])
    if book_data.get("keywords"):
        book.add_metadata("DC", "subject", book_data["keywords"])
    # KDP wants a publication date; fall back to today when not supplied.
    book.add_metadata("DC", "date", str(book_data.get("publication_date") or datetime.date.today()))
    book.add_metadata(
        "DC",
        "rights",
        f"Copyright (c) {datetime.date.today().year} "
        f"{book_data.get('author') or 'Anonymous'}. All rights reserved.",
    )

    # The cover MUST be attached before any other document is added.
    # EpubCoverHtml builds its page lazily from the book state at this
    # point in the sequence; adding it afterwards leaves cover.xhtml with
    # an empty body, and ebooklib's nav generator then raises
    # "Document is empty" while parsing it.
    has_cover = _add_cover(book, book_data.get("cover_path"))

    style = epub.EpubItem(
        uid="style_css",
        file_name="style.css",
        media_type="text/css",
        content=_load_css(),
    )
    book.add_item(style)

    images = _register_images(book, chapters, book_data.get("images_base"))

    def add_document(title, body_markdown, file_stem, in_toc):
        """Add one XHTML document to the spine; record it for the TOC."""
        page = epub.EpubHtml(title=title, file_name=f"{file_stem}.xhtml", lang="en")
        page.content = _document(title, _to_html(body_markdown, images))
        page.add_item(style)
        book.add_item(page)
        spine_items.append(page)
        if in_toc:
            toc_items.append(page)
        return page

    spine_items: list = []
    toc_items: list = []

    # Front matter first: title page, copyright, contents.
    for entry in front_matter(book_data):
        add_document(entry["title"], entry["content"], entry["file"], entry["toc"])

    # Chapters
    for i, ch in enumerate(chapters, 1):
        title = str(ch.get("title") or f"Chapter {ch.get('number', i)}")
        number = int(ch.get("number", i))
        add_document(title, str(ch.get("content") or ""), f"chapter_{number:02d}", True)

    # Back matter last: about the author, disclaimer.
    for entry in back_matter(book_data):
        add_document(entry["title"], entry["content"], entry["file"], entry["toc"])

    # Only content entries appear in the navigation document; the title page
    # and copyright page stay reachable through the spine but would clutter a
    # reader's table of contents.
    book.toc = tuple(toc_items)

    # EPUB3 navigation document plus EPUB2 NCX for older readers. Omitting
    # these is what made the existing books unacceptable to KDP.
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    spine = []
    if has_cover:
        spine.append("cover")
    spine.append("nav")
    spine.extend(spine_items)
    book.spine = spine

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(output_path, book, {})
    return output_path


def _load_css() -> bytes:
    if _CSS_PATH.is_file():
        return _CSS_PATH.read_bytes()
    return _DEFAULT_CSS.encode("utf-8")


def _add_cover(book: epub.EpubBook, cover_path) -> bool:
    """Attach the cover image if a readable file exists.

    Failure never aborts the build: a missing cover is logged, not silently
    swallowed and not fatal.
    """
    if not cover_path:
        return False
    path = Path(str(cover_path))
    if not path.is_file():
        log.warning("Cover not found: %s", path)
        return False
    try:
        data = path.read_bytes()
    except OSError as e:
        log.warning("Cover unreadable (%s): %s", e, path)
        return False
    ext = (path.suffix.lstrip(".").lower()) or "png"
    mime = mimetypes.guess_type(path.name)[0] or f"image/{ext}"
    book.set_cover(f"cover.{ext}", data, create_page=True)
    log.debug("cover attached as cover.%s (%s)", ext, mime)
    return True
