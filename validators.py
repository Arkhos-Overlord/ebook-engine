"""Structural validators for generated EPUB / PDF / KDP artifacts.

These implement gate G3: an artifact is only "done" if it would be accepted
by a conforming reader (and therefore by Amazon KDP).
"""

import posixpath
import zipfile
from pathlib import Path

from lxml import etree

_CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"


def validate_epub(path) -> list:
    """Return a list of structural problems with an EPUB. Empty means valid."""
    errors = []
    path = Path(str(path))
    if not path.is_file():
        return [f"file does not exist: {path}"]

    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                errors.append(f"corrupt zip entry: {bad}")
            errors += _validate_zip_epub(zf)
    except zipfile.BadZipFile as e:
        errors.append(f"not a zip: {e}")
    return errors


def _validate_zip_epub(zf: zipfile.ZipFile) -> list:
    errors = []
    names = set(zf.namelist())

    if "mimetype" not in names:
        errors.append("missing mimetype entry")
    else:
        if zf.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            errors.append("mimetype must be stored uncompressed")
        if zf.read("mimetype").strip() != b"application/epub+zip":
            errors.append("mimetype content is wrong")

    if "META-INF/container.xml" not in names:
        return errors + ["missing META-INF/container.xml"]

    try:
        container = etree.fromstring(zf.read("META-INF/container.xml"))
    except etree.XMLSyntaxError as e:
        return errors + [f"container.xml unparseable: {e}"]

    rootfile = container.find(f".//{_CONTAINER_NS}rootfile")
    if rootfile is None:
        return errors + ["container.xml has no rootfile"]
    opf_path = rootfile.get("full-path")
    if opf_path not in names:
        return errors + [f"OPF not in zip: {opf_path}"]

    try:
        opf = etree.fromstring(zf.read(opf_path))
    except etree.XMLSyntaxError as e:
        return errors + [f"OPF unparseable: {e}"]

    base = posixpath.dirname(opf_path)

    # Manifest keyed by item ID: spine references ids, not hrefs.
    manifest = {}
    has_nav = False
    for item in opf.iter():
        if not item.tag.endswith("item"):
            continue
        item_id = item.get("id")
        href = item.get("href")
        if not item_id or not href:
            errors.append("manifest item missing id or href")
            continue
        manifest[item_id] = href
        if "nav" in (item.get("properties") or ""):
            has_nav = True
        resolved = posixpath.normpath(posixpath.join(base, href))
        if resolved not in names and href not in names:
            errors.append(f"manifest href not in zip: {href}")

    spine = [ref.get("idref") for ref in opf.iter() if ref.tag.endswith("itemref")]
    if not spine:
        errors.append("spine is empty")
    for ref in spine:
        if ref not in manifest:
            errors.append(f"spine idref not in manifest: {ref}")

    # EPUB3 requires a navigation document; KDP rejects without it.
    if not has_nav:
        errors.append("no EPUB3 navigation document (properties='nav')")

    # Cover. Absence is a publication gap, not a structural defect, so the
    # quality gate is what blocks on it (`_check_cover`). What this file
    # owns is internal consistency: if a cover IS declared it must lead the
    # spine, or readers open on the wrong page.
    cover_declared = any(
        "cover-image" in (item.get("properties") or "")
        for item in opf.iter()
        if item.tag.endswith("item")
    ) or any(el.get("name") == "cover" for el in opf.iter() if el.tag.endswith("meta"))
    if cover_declared and (not spine or spine[0] != "cover"):
        errors.append("cover image is declared but does not lead the spine")

    # EPUB3 / KDP mandatory package metadata. Without these Amazon rejects
    # the upload, so they belong in the gate rather than in a manual list.
    if not opf.get("unique-identifier"):
        errors.append("package has no unique-identifier attribute")
    version = (opf.get("version") or "").strip()
    if not version:
        errors.append("package has no version attribute")
    elif not version.startswith("3"):
        # Not fatal on its own, but the nav check above only makes sense
        # in EPUB3; a 2.0 package is a downgrade from what we generate.
        errors.append(f"package version is {version}, not EPUB 3")
    for required in ("identifier", "language"):
        if opf.find(f".//{_DC_NS}{required}") is None:
            errors.append(f"package metadata is missing dc:{required}")
    if not any(
        "dcterms:modified" in (el.get("property") or "")
        for el in opf.iter()
        if el.tag.endswith("meta")
    ):
        errors.append("package metadata is missing dcterms:modified")
    if opf.find(f".//{_DC_NS}date") is None:
        errors.append("package metadata is missing dc:date")

    # Every spine document must be strict XML — raw &, < break readers.
    for ref in spine:
        href = manifest.get(ref)
        if not href:
            continue
        full = posixpath.normpath(posixpath.join(base, href))
        if full not in names:
            continue
        try:
            etree.fromstring(zf.read(full))
        except etree.XMLSyntaxError as e:
            errors.append(f"{href} is not well-formed XML: {e}")

    title = opf.find(f".//{_DC_NS}title")
    if title is None or not (title.text or "").strip():
        errors.append("OPF has no dc:title")

    return errors


def validate_pdf(path) -> list:
    """Return problems with a generated PDF. Empty means usable."""
    errors = []
    path = Path(str(path))
    if not path.is_file():
        return [f"file does not exist: {path}"]
    try:
        from pypdf import PdfReader
    except ImportError:
        return errors  # pypdf is a dev/test dependency

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        return [f"cannot open PDF: {e}"]

    if not reader.pages:
        errors.append("PDF has no pages")
    else:
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if not text.strip():
            errors.append("PDF has no extractable text")
        # Escaping applied twice leaves the entity itself visible in the
        # rendered output. Raw `<`/`>` in extracted text is NOT an error:
        # source prose such as "less than <limit>" legitimately renders as
        # literal angle brackets once escaping has been undone correctly.
        for artifact in ("&amp;", "&lt;", "&gt;"):
            if artifact in text:
                errors.append(f"PDF text shows a double-escaped entity: {artifact}")
                break
    if not reader.metadata or not reader.metadata.title:
        errors.append("PDF has no title metadata")
    return errors


def validate_kdp_zip(path) -> list:
    """Return problems with a KDP upload package."""
    errors = []
    path = Path(str(path))
    if not path.is_file():
        return [f"file does not exist: {path}"]
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                errors.append(f"corrupt zip entry: {bad}")
            names = zf.namelist()
            if not any(n.lower().endswith(".epub") for n in names):
                errors.append("package contains no EPUB")
            if not any(n.lower().endswith(".json") for n in names):
                errors.append("package contains no metadata json")
            if not any(n.lower().endswith((".png", ".jpg", ".jpeg")) for n in names):
                errors.append("package contains no cover image")
            for epub_name in (n for n in names if n.lower().endswith(".epub")):
                member_errors = _validate_epub_bytes(zf.read(epub_name))
                errors += [f"{epub_name}: {e}" for e in member_errors]
    except zipfile.BadZipFile as e:
        errors.append(f"not a zip: {e}")
    return errors


def _validate_epub_bytes(data: bytes) -> list:
    """Run validate_epub against EPUB bytes held inside another archive."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return validate_epub(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
