"""EPUB / PDF / KDP artifact validation (gate G3)."""

import re
import zipfile
from pathlib import Path

import pytest
from ebook_engine.formatters.epub_formatter import create_epub
from ebook_engine.formatters.kdp_zip import create_kdp_package
from ebook_engine.formatters.pdf_formatter import create_pdf

# Validators live in the package: the production quality gate needs them
# too, so they cannot sit under tests/.
from ebook_engine.validators import validate_epub, validate_kdp_zip, validate_pdf

CHAPTERS = [
    {
        "number": 1,
        "title": "Calories <Basics> & Myths",
        "content": "Energy balance is the foundation.\n\n"
        "Second paragraph with <angles> & ampersands.",
    },
    {
        "number": 2,
        "title": "Training Volume",
        "content": "## Sub heading\n\nProgressive overload matters.",
    },
]


def make_book(**overrides):
    book = {
        "topic": "Fitness & Nutrition",
        "genre": "Health",
        "author": "Test Author",
        "description": "A guide to <eating> well & training hard",
        "chapters": list(CHAPTERS),
    }
    book.update(overrides)
    return book


@pytest.fixture()
def cover_png(tmp_path):
    """A small real PNG so cover handling is exercised."""
    from PIL import Image

    path = tmp_path / "cover.png"
    Image.new("RGB", (400, 640), (20, 40, 80)).save(path)
    return str(path)


class TestEpub:
    def test_output_is_structurally_valid(self, tmp_path):
        out = tmp_path / "book.epub"
        create_epub(make_book(), str(out))
        assert validate_epub(out) == []

    def test_chapters_are_present(self, tmp_path):
        out = tmp_path / "book.epub"
        create_epub(make_book(), str(out))
        with zipfile.ZipFile(out) as zf:
            chapters = [n for n in zf.namelist() if Path(n).name.startswith("chapter_")]
        assert len(chapters) == 2

    def test_ampersand_and_brackets_do_not_break_xml(self, tmp_path):
        """Regression: raw & and < went straight into the XHTML."""
        out = tmp_path / "book.epub"
        create_epub(make_book(topic="A & B <Guide>"), str(out))
        assert validate_epub(out) == []

    def test_markdown_headings_become_html(self, tmp_path):
        out = tmp_path / "book.epub"
        create_epub(make_book(), str(out))
        with zipfile.ZipFile(out) as zf:
            body = zf.read("EPUB/chapter_02.xhtml").decode("utf-8")
        assert "<h2>Sub heading</h2>" in body
        assert "## Sub heading" not in body

    def test_identifier_is_stable_across_rebuilds(self, tmp_path):
        """Rebuilding the same title must not mint a new book identity."""
        first, second = tmp_path / "a.epub", tmp_path / "b.epub"
        create_epub(make_book(), str(first))
        create_epub(make_book(), str(second))
        ids = []
        for path in (first, second):
            with zipfile.ZipFile(path) as zf:
                opf = next(n for n in zf.namelist() if n.endswith(".opf"))
                text = zf.read(opf).decode("utf-8")
            start = text.index("<dc:identifier") + 1
            ids.append(text[start : text.index("</dc:identifier>")])
        assert ids[0] == ids[1]

    def test_cover_is_embedded(self, tmp_path, cover_png):
        out = tmp_path / "book.epub"
        create_epub(make_book(cover_path=cover_png), str(out))
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert any(n.endswith(".png") for n in names)
        assert validate_epub(out) == []

    def test_missing_cover_does_not_abort(self, tmp_path):
        out = tmp_path / "book.epub"
        create_epub(make_book(cover_path=str(tmp_path / "nope.png")), str(out))
        assert validate_epub(out) == []

    def test_without_cover_is_valid(self, tmp_path):
        out = tmp_path / "book.epub"
        create_epub(make_book(cover_path=""), str(out))
        assert validate_epub(out) == []

    def test_no_chapters_raises(self, tmp_path):
        with pytest.raises(ValueError, match="no chapters"):
            create_epub(make_book(chapters=[]), str(tmp_path / "x.epub"))

    def test_creates_parent_directory(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "book.epub"
        create_epub(make_book(), str(out))
        assert out.is_file()


class TestPdf:
    def test_output_is_usable(self, tmp_path):
        out = tmp_path / "book.pdf"
        create_pdf(make_book(), str(out))
        assert validate_pdf(out) == []

    def test_text_survives_escaping(self, tmp_path):
        out = tmp_path / "book.pdf"
        create_pdf(make_book(), str(out))
        from pypdf import PdfReader

        text = "\n".join(p.extract_text() or "" for p in PdfReader(str(out)).pages)
        assert "ampersands" in text
        assert "Sub heading" in text

    def test_cover_does_not_overflow_the_frame(self, tmp_path, cover_png):
        """Regression: the cover was sized against the page, not the frame,
        which raised LayoutError for every book that had a cover."""
        out = tmp_path / "book.pdf"
        create_pdf(make_book(cover_path=cover_png), str(out))
        assert validate_pdf(out) == []

    def test_missing_cover_is_skipped(self, tmp_path):
        out = tmp_path / "book.pdf"
        create_pdf(make_book(cover_path=str(tmp_path / "none.png")), str(out))
        assert validate_pdf(out) == []

    def test_no_chapters_raises(self, tmp_path):
        with pytest.raises(ValueError, match="no chapters"):
            create_pdf(make_book(chapters=[]), str(tmp_path / "x.pdf"))


class TestKdpZip:
    def test_package_is_valid(self, tmp_path, cover_png):
        epub = tmp_path / "book.epub"
        create_epub(make_book(cover_path=cover_png), str(epub))
        zipped = create_kdp_package(
            str(epub),
            output_path=str(tmp_path / "book.kdp.zip"),
            cover_path=cover_png,
            metadata={"title": "Fitness & Nutrition", "author": "Test Author"},
        )
        assert validate_kdp_zip(zipped) == []

    def test_bundles_required_members(self, tmp_path, cover_png):
        epub = tmp_path / "book.epub"
        create_epub(make_book(cover_path=cover_png), str(epub))
        zipped = create_kdp_package(
            str(epub),
            output_path=str(tmp_path / "b.zip"),
            cover_path=cover_png,
            metadata={"title": "T"},
        )
        with zipfile.ZipFile(zipped) as zf:
            names = zf.namelist()
        assert any(n.endswith(".epub") for n in names)
        assert any(n.endswith(".json") for n in names)
        assert any(n.endswith(".png") for n in names)
        assert "README.txt" in names

    def test_missing_epub_raises_rather_than_writing_an_empty_package(self, tmp_path):
        """A failed EPUB build must never be recorded as a finished package."""
        with pytest.raises(FileNotFoundError):
            create_kdp_package(str(tmp_path / "absent.epub"), output_path=str(tmp_path / "b.zip"))


class TestEpub3Compliance:
    """Amazon rejects an upload whose package metadata is incomplete, so
    these are checked rather than assumed."""

    def _build(self, tmp_path, **overrides):
        book = make_book(**overrides)
        out = tmp_path / "c.epub"
        create_epub(book, str(out))
        return out

    def test_a_generated_book_is_compliant(self, tmp_path):
        assert validate_epub(self._build(tmp_path)) == []

    def _rewrite_opf(self, path, transform):
        """Rebuild an EPUB with its OPF passed through `transform`."""
        with zipfile.ZipFile(path) as zf:
            members = {n: zf.read(n) for n in zf.namelist()}
        opf_name = next(n for n in members if n.endswith(".opf"))
        members[opf_name] = transform(members[opf_name].decode("utf-8")).encode("utf-8")
        out = path.with_name("mutated.epub")
        with zipfile.ZipFile(out, "w") as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return out

    def test_missing_language_is_caught(self, tmp_path):
        path = self._build(tmp_path)

        def drop(text):
            return re.sub(r"<dc:language>.*?</dc:language>", "", text, flags=re.S)

        errs = validate_epub(self._rewrite_opf(path, drop))
        assert any("dc:language" in e for e in errs), errs

    def test_missing_identifier_is_caught(self, tmp_path):
        path = self._build(tmp_path)

        def drop(text):
            return re.sub(r"<dc:identifier[^>]*>.*?</dc:identifier>", "", text, flags=re.S)

        errs = validate_epub(self._rewrite_opf(path, drop))
        assert any("dc:identifier" in e for e in errs), errs

    def test_missing_modified_date_is_caught(self, tmp_path):
        path = self._build(tmp_path)

        def drop(text):
            return re.sub(r'<meta property="dcterms:modified">.*?</meta>', "", text, flags=re.S)

        errs = validate_epub(self._rewrite_opf(path, drop))
        assert any("dcterms:modified" in e for e in errs), errs

    def test_missing_unique_identifier_attribute_is_caught(self, tmp_path):
        path = self._build(tmp_path)

        def drop(text):
            return text.replace('unique-identifier="id"', "")

        errs = validate_epub(self._rewrite_opf(path, drop))
        assert any("unique-identifier" in e for e in errs), errs

    def test_downgraded_version_is_caught(self, tmp_path):
        path = self._build(tmp_path)

        def downgrade(text):
            return text.replace('version="3.0"', 'version="2.0"')

        errs = validate_epub(self._rewrite_opf(path, downgrade))
        assert any("not EPUB 3" in e for e in errs), errs

    def test_publisher_appears_when_supplied(self, tmp_path):
        path = self._build(tmp_path, publisher="Vale Press", publication_date="2026-01-02")
        import zipfile as zf_mod

        with zf_mod.ZipFile(path) as z:
            opf = z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8")
        assert "Vale Press" in opf
        assert "2026-01-02" in opf


class TestEpubCover:
    """Readers and KDP both need a declared cover that opens the book."""

    def _build(self, tmp_path, **overrides):
        out = tmp_path / "c.epub"
        create_epub(make_book(**overrides), str(out))
        return out

    def test_a_built_epub_declares_its_cover(self, tmp_path, cover_png):
        path = self._build(tmp_path, cover_path=cover_png)
        with zipfile.ZipFile(path) as z:
            opf = z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8")
        assert 'name="cover"' in opf or "cover-image" in opf

    def test_the_cover_opens_the_spine(self, tmp_path, cover_png):
        path = self._build(tmp_path, cover_path=cover_png)
        with zipfile.ZipFile(path) as z:
            opf = z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8")
        assert re.search(r'idref="cover"', opf), "cover must lead the spine"

    def test_the_cover_image_is_embedded(self, tmp_path, cover_png):
        path = self._build(tmp_path, cover_path=cover_png)
        with zipfile.ZipFile(path) as z:
            images = [n for n in z.namelist() if n.lower().endswith((".png", ".jpg"))]
        assert images, "cover image not embedded"

    def test_a_cover_outside_the_spine_is_caught(self, tmp_path, cover_png):
        from lxml import etree

        path = self._build(tmp_path, cover_path=cover_png)
        with zipfile.ZipFile(path) as z:
            members = {n: z.read(n) for n in z.namelist()}
        opf_name = next(n for n in members if n.endswith(".opf"))

        # Move the cover to the end of the spine structurally; string
        # surgery is at the mercy of ebooklib's own formatting.
        root = etree.fromstring(members[opf_name])
        spine_el = next(e for e in root.iter() if e.tag.endswith("spine"))
        cover = next(e for e in spine_el if e.get("idref") == "cover")
        spine_el.remove(cover)
        spine_el.append(cover)
        members[opf_name] = etree.tostring(root, xml_declaration=True, encoding="utf-8")

        out = tmp_path / "outoforder.epub"
        with zipfile.ZipFile(out, "w") as z:
            for name, data in members.items():
                z.writestr(name, data)
        errs = validate_epub(out)
        assert any("lead the spine" in e for e in errs), errs
