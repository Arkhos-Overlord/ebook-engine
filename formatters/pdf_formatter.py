"""PDF formatter — generate print-ready PDF files with reportlab.

Replaces the earlier weasyprint implementation, which could not be
installed on Windows and had never run: `create_pdf` had zero callers.
reportlab is the backend already proven by books/ai-small-business.
"""

import html
import logging
from pathlib import Path

import markdown
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents

from ebook_engine.config import PDF_PAGE_SIZE
from ebook_engine.formatters.matter import (
    back_matter,
    collapse_escapes,
    front_matter,
)

log = logging.getLogger(__name__)

_PAGE_SIZES = {"A5": A5}
_MARGIN = 18 * mm


def create_pdf(book_data: dict, output_path: str) -> str:
    """Create a print-ready PDF from book data. Returns the output path.

    Args:
        book_data: dict with 'topic', 'genre', 'chapters', 'author' and
            optionally 'description' and 'cover_path'.
        output_path: where the .pdf file will be written.
    """
    chapters = book_data.get("chapters") or []
    if not chapters:
        raise ValueError(f"Cannot build a PDF for '{book_data.get('topic')}': no chapters")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    styles = _build_styles()
    story = _build_story(book_data, chapters, styles)

    doc = _PDFDoc(
        str(output),
        pagesize=_PAGE_SIZES.get(PDF_PAGE_SIZE, A5),
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN + 6 * mm,
        title=str(book_data.get("topic") or ""),
        author=str(book_data.get("author") or ""),
        subject=str(book_data.get("description") or ""),
    )
    doc.multiBuild(story)
    return str(output)


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BookTitle",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=24,
            leading=28,
            spaceAfter=10,
            alignment=1,
        ),
        "subtitle": ParagraphStyle(
            "BookSubtitle",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=13,
            leading=17,
            alignment=1,
            textColor="#444444",
        ),
        "author": ParagraphStyle(
            "BookAuthor",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=16,
            alignment=1,
            spaceBefore=18,
        ),
        "genre": ParagraphStyle(
            "BookGenre",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=10,
            alignment=1,
            textColor="#666666",
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=17,
            leading=21,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Times-Bold",
            fontSize=14,
            leading=18,
            spaceBefore=12,
            spaceAfter=7,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Times-Bold",
            fontSize=12,
            leading=16,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=10.5,
            leading=15,
            alignment=4,
            spaceAfter=7,
            firstLineIndent=0,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName="Times-Italic",
            fontSize=10,
            leading=14,
            leftIndent=14,
            rightIndent=10,
            textColor="#333333",
            spaceBefore=5,
            spaceAfter=8,
        ),
        "toc_title": ParagraphStyle(
            "TOCTitle",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=16,
            leading=20,
            spaceAfter=12,
        ),
        "toc": ParagraphStyle(
            "TOCBody",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=11,
            leading=17,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=9,
            leading=12,
            backColor="#f4f4f4",
            leftIndent=8,
            rightIndent=8,
            spaceBefore=4,
            spaceAfter=8,
        ),
    }


def _build_story(book_data: dict, chapters: list, styles: dict) -> list:
    """Front matter, a page-numbered TOC, chapters, then back matter.

    The PDF keeps its designed title page and reportlab's TableOfContents
    (which carries real page numbers) in place of the markdown contents
    page the EPUB uses, but the copyright page and the back matter come
    from formatters.matter so both formats stay in step.
    """
    story = []
    cover = _cover_flowable(book_data.get("cover_path"))
    if cover is not None:
        story.append(cover)
        story.append(PageBreak())

    # Designed title page.
    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph(html.escape(str(book_data.get("topic") or "")), styles["title"]))
    if book_data.get("subtitle"):
        story.append(Paragraph(html.escape(str(book_data["subtitle"])), styles["subtitle"]))
    elif book_data.get("description"):
        story.append(Paragraph(html.escape(str(book_data["description"])), styles["subtitle"]))
    story.append(Paragraph(html.escape(str(book_data.get("author") or "")), styles["author"]))
    if book_data.get("genre"):
        story.append(Paragraph(html.escape(str(book_data["genre"]).upper()), styles["genre"]))
    story.append(PageBreak())

    # Copyright page and any other shared front matter that is not the
    # title page (which is already designed above) or the contents page
    # (replaced below by a TOC with page numbers).
    for entry in front_matter(book_data):
        if entry["key"] in ("title_page", "contents"):
            continue
        _emit_sections(story, entry["content"], styles)
        story.append(PageBreak())

    toc = TableOfContents()
    toc.levelStyles = [styles["toc"], styles["toc"]]
    story.append(Paragraph("Table of Contents", styles["toc_title"]))
    story.append(toc)
    story.append(PageBreak())

    for i, ch in enumerate(chapters):
        title = str(ch.get("title") or f"Chapter {i + 1}")
        heading = Paragraph(html.escape(title), styles["h1"])
        heading.toc_level = 0
        story.append(heading)
        _emit_sections(story, str(ch.get("content") or ""), styles, toc_headings=True)
        if i < len(chapters) - 1:
            story.append(PageBreak())

    for entry in back_matter(book_data):
        heading = Paragraph(html.escape(entry["title"]), styles["h1"])
        if entry.get("toc"):
            heading.toc_level = 0
        story.append(heading)
        _emit_sections(story, entry["content"], styles, toc_headings=True)
        story.append(PageBreak())
    return story


def _emit_sections(story: list, source: str, styles: dict, toc_headings: bool = False) -> None:
    """Append markdown-derived blocks to the story."""
    for tag, text in _blocks(source):
        style = {"h2": "h2", "h3": "h3", "blockquote": "quote", "pre": "code"}.get(tag, "body")
        if not text.strip():
            continue
        flowable = Paragraph(text, styles[style])
        if toc_headings and tag in ("h2", "h3"):
            flowable.toc_level = 1
        story.append(flowable)


def _blocks(source: str) -> list:
    """Convert prose to (tag, text) blocks, XML-safe for reportlab.

    Source is escaped BEFORE markdown runs, so the text we hand to
    ReportLab's XML-based Paragraph already contains entities rather than
    raw `<`, `&`. This is the fix for the old builder, whose esc() replaced
    every character with itself and unescaped first.
    """
    body = markdown.markdown(html.escape(source, quote=False), extensions=["extra"])
    import re

    blocks = []
    pattern = re.compile(r"(?is)<(h1|h2|h3|p|blockquote|pre|li)>(.*?)</\1>")
    for match in pattern.finditer(body):
        tag, inner = match.group(1).lower(), match.group(2)
        text = re.sub(r"(?is)<[^>]+>", "", inner).strip()
        if not text:
            continue
        blocks.append(("h1" if tag == "h1" else tag, collapse_escapes(text)))
    if blocks:
        return blocks
    return [("p", collapse_escapes(html.escape(source, quote=False)).strip())]


def _frame_size():
    """Usable content box of the body frame.

    Matches _PDFDoc's construction exactly, including reportlab's default
    Frame padding of 6pt on each side — ignoring that padding made the
    cover overflow and raised LayoutError.
    """
    size = _PAGE_SIZES.get(PDF_PAGE_SIZE, A5)
    return (
        size[0] - 2 * _MARGIN - 12,
        size[1] - 2 * _MARGIN - 6 * mm - 12,
    )


def _cover_flowable(cover_path):
    """Build a cover image fitted to the body frame, or None when unavailable.

    The previous implementation referenced the cover with a `file://C:\\...`
    URI, which is malformed on Windows; here the image is read directly.
    Sized against the frame (not the page) or reportlab raises LayoutError
    for anything taller than the printable area.
    """
    if not cover_path:
        return None
    path = Path(str(cover_path))
    if not path.is_file():
        log.warning("Cover not found, skipping: %s", path)
        return None
    try:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(str(path))
        iw, ih = reader.getSize()
    except Exception as e:
        log.warning("Cover unreadable (%s): %s", e, path)
        return None
    frame_w, frame_h = _frame_size()
    scale = min(frame_w / iw, frame_h / ih)
    return Image(str(path), width=iw * scale, height=ih * scale)


class _PDFDoc(BaseDocTemplate):
    """Document with a page-number footer and TOC entry collection."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        size = _PAGE_SIZES.get(PDF_PAGE_SIZE, A5)
        frame = Frame(
            _MARGIN,
            _MARGIN + 6 * mm,
            size[0] - 2 * _MARGIN,
            size[1] - 2 * _MARGIN - 6 * mm,
            id="body",
        )
        self.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_page_footer)])

    def afterFlowable(self, flowable):
        level = getattr(flowable, "toc_level", None)
        if level is None:
            return
        text = flowable.getPlainText()
        key = f"toc-{id(flowable)}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=(level > 0))
        self.notify("TOCEntry", (level, text, self.page, key))


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColorRGB(0.4, 0.4, 0.4)
    canvas.drawCentredString(_PAGE_SIZES.get(PDF_PAGE_SIZE, A5)[0] / 2, 10 * mm, str(doc.page))
    canvas.restoreState()
