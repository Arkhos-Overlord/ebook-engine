"""EPUB reader — parse EPUB archives with the standard library and lxml.

A reader needs no third-party EPUB library: an EPUB is a ZIP holding
`META-INF/container.xml`, which points at an OPF manifest describing the
spine and navigation. Everything here reads from the archive, so nothing
is ever extracted to disk and no path can escape the file it came from.
"""

import posixpath
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from lxml import html as lxml_html

_CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_EPUB_NS = "{http://www.idpf.org/2007/ops}"
_XHTML = "application/xhtml+xml"
_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp")


def _iter_local(root, local: str):
    """Yield elements matching a local name, ignoring their namespace.

    XHTML and NCX documents are namespaced, so `root.iter("a")` matches
    nothing — it only ever selects un-namespaced tags. Matching on the
    local name works for both forms.
    """
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == local:
            yield element


class EpubError(Exception):
    """Raised when an archive is not a readable EPUB."""


@dataclass
class Chapter:
    """One readable chapter of the book."""

    number: int
    title: str
    href: str  # path inside the archive, used to resolve relative assets
    body: str  # inner HTML of the document body


@dataclass
class EpubBook:
    """The parts of an EPUB a reader needs."""

    title: str
    author: str
    language: str
    identifier: str
    chapters: list = field(default_factory=list)
    stylesheets: dict = field(default_factory=dict)  # archive path -> css text
    images: dict = field(default_factory=dict)  # archive path -> bytes
    cover_name: str = ""
    source_path: str = ""

    @property
    def author_or_unknown(self) -> str:
        return self.author or "Unknown author"


def read_epub(path) -> EpubBook:
    """Read an EPUB from disk into an EpubBook. Raises EpubError on bad input."""
    path = Path(str(path))
    if not path.is_file():
        raise EpubError(f"file not found: {path}")
    try:
        with zipfile.ZipFile(path) as zf:
            return _parse(zf, str(path))
    except zipfile.BadZipFile as e:
        raise EpubError(f"not a ZIP archive: {e}") from e


def read_epub_bytes(data: bytes) -> EpubBook:
    """Read an EPUB held in memory (e.g. an archive nested in a package)."""
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return _parse(zf, "<memory>")
    except zipfile.BadZipFile as e:
        raise EpubError(f"not a ZIP archive: {e}") from e


def _parse(zf: zipfile.ZipFile, source: str) -> EpubBook:
    names = set(zf.namelist())

    if "META-INF/container.xml" not in names:
        raise EpubError("missing META-INF/container.xml")
    try:
        container = etree.fromstring(zf.read("META-INF/container.xml"))
    except etree.XMLSyntaxError as e:
        raise EpubError(f"container.xml is not XML: {e}") from e

    rootfile = container.find(f".//{_CONTAINER_NS}rootfile")
    if rootfile is None:
        raise EpubError("container.xml names no OPF file")
    opf_path = rootfile.get("full-path")
    if opf_path not in names:
        raise EpubError(f"OPF missing from archive: {opf_path}")
    try:
        opf = etree.fromstring(zf.read(opf_path))
    except etree.XMLSyntaxError as e:
        raise EpubError(f"OPF is not XML: {e}") from e

    base = posixpath.dirname(opf_path)

    book = EpubBook(
        title=_meta(opf, "title") or Path(source).stem,
        author=_meta(opf, "creator"),
        language=_meta(opf, "language"),
        identifier=_meta(opf, "identifier"),
        source_path=source,
    )

    # id -> (href, media-type, properties)
    manifest = {}
    for item in opf.iter():
        if item.tag.endswith("item"):
            manifest[item.get("id")] = (
                item.get("href") or "",
                item.get("media-type") or "",
                item.get("properties") or "",
            )

    nav_item = next((i for i in manifest.values() if "nav" in i[2]), None)
    spine = [
        ref.get("idref") for ref in opf.iter() if ref.tag.endswith("itemref") and ref.get("idref")
    ]

    # Titles are keyed by href, not by position: the navigation document
    # deliberately omits the title page, copyright page and contents page,
    # so an index-based match would hand chapter titles to the wrong
    # documents.
    title_by_href = {}
    if nav_item:
        title_by_href = _nav_titles(zf, _join(base, nav_item[0]), names)
    if not title_by_href:
        title_by_href = _ncx_titles(zf, opf_path, opf, names)

    chapter_specs = []
    for ref in spine:
        entry = manifest.get(ref)
        if not entry:
            continue  # dangling idref — skip rather than crash the reader
        href, media_type, _ = entry
        if not href:
            continue
        full = _join(base, href)
        if full not in names:
            continue
        if media_type and media_type != _XHTML and not href.endswith((".xhtml", ".html", ".htm")):
            continue
        chapter_specs.append((full, href))

    # Drop leading cover/nav/toc documents: the cover is rendered
    # separately and the navigation duplicates the sidebar.
    readable = [c for c in chapter_specs if not _is_front_matter(c[1])]

    if not readable:
        # Spine idrefs could not be resolved (the 15 pre-existing books all
        # carry idrefs that point at nothing). Fall back to every XHTML
        # document in the manifest so a damaged EPUB is still readable
        # here even though it is unacceptable to KDP.
        readable = [
            (_join(base, href), href)
            for href, media_type, _ in manifest.values()
            if href
            and _join(base, href) in names
            and (media_type == _XHTML or href.lower().endswith((".xhtml", ".html", ".htm")))
            and not _is_front_matter(href)
        ]
        if not readable:
            raise EpubError("no readable chapter documents in the spine")

    book.chapters = [
        Chapter(
            number=i,
            title=_title_for(title_by_href, href, i),
            href=href,
            body=_body(zf.read(full)),
        )
        for i, (full, href) in enumerate(readable, start=1)
    ]

    if not book.chapters:
        raise EpubError("no readable chapter documents in the spine")

    _collect_assets(zf, base, names, manifest, book)
    return book


def _meta(opf, name) -> str:
    node = opf.find(f".//{_DC_NS}{name}")
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _join(base: str, href: str) -> str:
    return posixpath.normpath(posixpath.join(base, href)) if base else href


def _is_front_matter(href: str) -> bool:
    """Documents that are not chapters: the cover image page and the TOC."""
    leaf = href.rsplit("/", 1)[-1].lower()
    return leaf in (
        "cover.xhtml",
        "nav.xhtml",
        "toc.xhtml",
        "contents.xhtml",
    )


def _nav_titles(zf, nav_path: str, names: set) -> dict:
    """href -> title from an EPUB3 navigation document."""
    if nav_path not in names:
        return {}
    try:
        doc = etree.fromstring(zf.read(nav_path))
    except etree.XMLSyntaxError:
        return {}

    def anchors(root) -> dict:
        out = {}
        for link in _iter_local(root, "a"):
            href = link.get("href")
            text = "".join(link.itertext()).strip()
            if href and text:
                out[_leaf(href)] = text
        return out

    for nav in _iter_local(doc, "nav"):
        if nav.get(f"{_EPUB_NS}type") not in (None, "toc"):
            continue
        titles = anchors(nav)
        if titles:
            return titles
    return anchors(doc)


def _ncx_titles(zf, opf_path: str, opf, names: set) -> dict:
    """href -> title from an EPUB2 toc.ncx."""
    base = posixpath.dirname(opf_path)
    toc = opf.get("toc")
    ncx_href = None
    for item in opf.iter():
        if item.tag.endswith("item") and (
            (toc and item.get("id") == toc)
            or (item.get("media-type") or "").endswith("x-dtbncx+xml")
        ):
            ncx_href = item.get("href")
            break
    if not ncx_href:
        return {}
    ncx_path = _join(base, ncx_href)
    if ncx_path not in names:
        return {}
    try:
        doc = etree.fromstring(zf.read(ncx_path))
    except etree.XMLSyntaxError:
        return {}

    titles = {}
    for point in _iter_local(doc, "navPoint"):
        label, src = "", ""
        for child in point:
            if not isinstance(child.tag, str):
                continue
            local = child.tag.rsplit("}", 1)[-1]
            if local == "navLabel":
                text = next(_iter_local(child, "text"), None)
                label = "".join(text.itertext()).strip() if text is not None else ""
            elif local == "content":
                src = child.get("src") or ""
        if src and label:
            titles[_leaf(src)] = label
    return titles


def _leaf(href: str) -> str:
    """File name of an href, without any fragment or query."""
    return posixpath.basename(href.split("#")[0].split("?")[0])


def _title_for(title_by_href: dict, href: str, index: int) -> str:
    """Resolve one document's display title.

    Looks the document up by its own href; documents absent from the
    navigation document (the title page, the copyright page) fall back to
    a title derived from the file name.
    """
    found = title_by_href.get(_leaf(href))
    if found:
        return found
    stem = posixpath.splitext(_leaf(href))[0]
    pretty = stem.replace("_", " ").replace("-", " ").strip().title()
    return pretty or f"Chapter {index}"


def _body(raw: bytes) -> str:
    """Extract the body's inner HTML, leaving markup intact for the browser."""
    try:
        doc = lxml_html.fromstring(raw)
    except Exception:
        return ""
    body = doc.find("body")
    if body is None:
        return _inner(doc)
    return _inner(body)


def _inner(node) -> str:
    parts = []
    if node.text:
        parts.append(node.text)
    for child in node:
        parts.append(etree.tostring(child, encoding="unicode", method="html"))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _collect_assets(zf, base: str, names: set, manifest: dict, book: EpubBook) -> None:
    """Load every stylesheet and image the manifest declares."""
    for href, media_type, _ in manifest.values():
        if not href:
            continue
        full = _join(base, href)
        if full not in names:
            continue
        if media_type == "text/css" or href.lower().endswith(".css"):
            book.stylesheets[full] = zf.read(full).decode("utf-8", "replace")
        elif media_type in _IMAGE_TYPES or media_type.startswith("image/"):
            book.images[full] = zf.read(full)

    # Prefer the actual cover image over any other picture.
    for path in book.images:
        if "cover" in posixpath.basename(path).lower():
            book.cover_name = path
            break
    if not book.cover_name and book.images:
        book.cover_name = next(iter(book.images))
