"""Built-in EPUB reader: parser, asset safety, and HTTP routes (gate G6)."""

import io
import re
import threading
import time
import urllib.error
import urllib.request
import zipfile

import ebook_engine.server as server
import pytest
from ebook_engine.epub_reader import EpubError, read_epub, read_epub_bytes
from ebook_engine.formatters.epub_formatter import create_epub
from ebook_engine.server import read_asset, rewrite_urls

CHAPTERS = [
    {"number": 1, "title": "First Chapter", "content": "Opening text."},
    {"number": 2, "title": "Second Chapter", "content": "More text."},
]


def build_epub(tmp_path, name="book.epub", cover=None, chapters=None):
    out = tmp_path / name
    create_epub(
        {
            "topic": "Fitness & Nutrition",
            "genre": "Health",
            "author": "Test Author",
            "description": "desc",
            "cover_path": cover or "",
            "chapters": chapters or list(CHAPTERS),
        },
        str(out),
    )
    return out


@pytest.fixture()
def cover_png(tmp_path):
    from PIL import Image

    path = tmp_path / "cover.png"
    Image.new("RGB", (400, 640), (20, 40, 80)).save(path)
    return path


@pytest.fixture()
def valid_epub(tmp_path, cover_png):
    return build_epub(tmp_path, cover=str(cover_png))


@pytest.fixture()
def broken_epub(tmp_path):
    """An EPUB whose spine idrefs point at nothing, like all 15 originals."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'version="1.0"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )
        zf.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Broken Book</dc:title>"
            "<dc:identifier id='id'>x</dc:identifier>"
            "<dc:language>en</dc:language></metadata>"
            "<manifest>"
            '<item id="chapter_0" href="chapter_01.xhtml" '
            'media-type="application/xhtml+xml"/>'
            "</manifest>"
            '<spine><itemref idref="chapter_01"/></spine>'  # dangling
            "</package>",
        )
        zf.writestr(
            "OEBPS/chapter_01.xhtml",
            '<?xml version="1.0"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            "<title>One</title></head><body><p>Recovered body</p></body></html>",
        )
    data = buf.getvalue()
    path = tmp_path / "broken.epub"
    path.write_bytes(data)
    return path


def by_href(book) -> dict:
    """Map a chapter's file name to its parsed entry."""
    return {c.href.rsplit("/", 1)[-1]: c for c in book.chapters}


class TestParser:
    def test_reads_valid_epub(self, valid_epub):
        book = read_epub(valid_epub)
        assert book.title == "Fitness & Nutrition"
        assert book.author == "Test Author"

        chapters = by_href(book)
        # Titles resolve by href, not by position in the spine.
        assert chapters["chapter_01.xhtml"].title == "First Chapter"
        assert chapters["chapter_02.xhtml"].title == "Second Chapter"
        assert chapters["chapter_01.xhtml"].body
        assert chapters["chapter_02.xhtml"].body

    def test_front_and_back_matter_are_present(self, valid_epub):
        """A publishable book needs a title page, copyright page,
        contents page and about-the-author page, not just bare chapters.

        Checked against the archive, because the reader intentionally
        hides contents.xhtml (it draws its own TOC sidebar).
        """
        with zipfile.ZipFile(valid_epub) as zf:
            names = {n.rsplit("/", 1)[-1] for n in zf.namelist()}
        for expected in (
            "title_page.xhtml",
            "copyright.xhtml",
            "contents.xhtml",
            "about_author.xhtml",
        ):
            assert expected in names, expected

        chapters = by_href(read_epub(valid_epub))
        assert "title_page.xhtml" in chapters
        assert "copyright.xhtml" in chapters
        assert "about_author.xhtml" in chapters

    def test_cover_and_assets_are_collected(self, valid_epub, cover_png):
        book = read_epub(valid_epub)
        assert book.cover_name
        assert book.stylesheets, "the book's own CSS must be available"
        assert any(p.endswith(".png") for p in book.images)

    def test_cover_page_is_not_treated_as_a_chapter(self, valid_epub, cover_png):
        """Regression: cover.xhtml was served as chapter 1 ('Cover')."""
        book = read_epub(valid_epub)
        assert "cover.xhtml" not in by_href(book)
        assert "Cover" not in [c.title for c in book.chapters]

    def test_contents_page_is_suppressed_in_the_reader(self, valid_epub):
        """The reader draws its own TOC sidebar; a contents.xhtml in the
        reading order would duplicate it."""
        assert "contents.xhtml" not in by_href(read_epub(valid_epub))

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(EpubError, match="file not found"):
            read_epub(tmp_path / "absent.epub")

    def test_not_a_zip_raises(self, tmp_path):
        junk = tmp_path / "junk.epub"
        junk.write_bytes(b"this is not a zip at all")
        with pytest.raises(EpubError, match="not a ZIP"):
            read_epub(junk)

    def test_broken_spine_falls_back_to_manifest(self, broken_epub):
        """Regression: a dangling spine used to raise instead of reading."""
        book = read_epub(broken_epub)
        assert book.title == "Broken Book"
        assert len(book.chapters) == 1
        assert "Recovered body" in book.chapters[0].body

    def test_read_epub_bytes(self, valid_epub):
        book = read_epub_bytes(valid_epub.read_bytes())
        chapters = by_href(book)
        assert chapters["chapter_01.xhtml"].title == "First Chapter"
        assert chapters["chapter_02.xhtml"].title == "Second Chapter"


class TestAssetSafety:
    def test_reads_a_real_member(self, valid_epub):
        book = read_epub(valid_epub)
        css = read_asset(book.source_path, "EPUB/style.css")
        assert css and b"font-family" in css

    @pytest.mark.parametrize(
        "attempt",
        [
            "../../config.py",
            "../../../Windows/win.ini",
            "/etc/passwd",
            "..\\..\\secret",
            "",
            "EPUB/../content.opf",
        ],
    )
    def test_traversal_and_absolute_paths_are_rejected(self, valid_epub, attempt):
        """Assets come from the ZIP namelist only — never the filesystem."""
        book = read_epub(valid_epub)
        assert read_asset(book.source_path, attempt) is None

    def test_unknown_member_is_none(self, valid_epub):
        book = read_epub(valid_epub)
        assert read_asset(book.source_path, "EPUB/nope.css") is None


class TestRewriteUrls:
    def test_relative_src_is_pointed_at_the_asset_route(self):
        out = rewrite_urls('<img src="images/f.png">', "EPUB/ch.xhtml", 3)
        assert 'src="/asset/3/EPUB/images/f.png"' in out

    def test_parent_relative_path_is_resolved(self):
        out = rewrite_urls('<img src="../img/f.png">', "EPUB/ch.xhtml", 3)
        assert 'src="/asset/3/img/f.png"' in out

    def test_anchors_and_external_links_are_untouched(self):
        body = '<a href="#x">a</a><a href="https://e.com">b</a><a href="mailto:x@y.z">c</a>'
        out = rewrite_urls(body, "EPUB/ch.xhtml", 3)
        assert 'href="#x"' in out
        assert 'href="https://e.com"' in out
        assert 'href="mailto:x@y.z"' in out

    def test_empty_body_is_safe(self):
        assert rewrite_urls("", "EPUB/ch.xhtml", 1) == ""


@pytest.fixture()
def reader_server(tmp_path, monkeypatch, valid_epub):
    """A live reader server bound to a free loopback port."""
    import ebook_engine.catalog as catalog
    import ebook_engine.config as config

    monkeypatch.setattr(catalog, "DB_PATH", tmp_path / "catalog.db")
    monkeypatch.setattr(catalog, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "catalog.db")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    server.clear_cache()

    book_id = catalog.add_book(
        title="Fitness & Nutrition",
        author="Test Author",
        genre="Health",
        isbn="9780000000001",
        price_tier="basic",
        price_inr=349.0,
        file_epub=str(valid_epub),
        description="desc",
    )

    ready = {}
    thread = threading.Thread(
        target=server.serve,
        kwargs={
            "port": 0,
            "open_browser": False,
            "ready": lambda srv, url: ready.update(srv=srv, url=url),
        },
        daemon=True,
    )
    thread.start()
    for _ in range(200):
        if ready:
            break
        time.sleep(0.02)
    assert ready, "server did not start"

    from urllib.parse import urlparse

    origin = "{}://{}".format(
        urlparse(ready["url"]).scheme,
        urlparse(ready["url"]).netloc,
    )
    yield origin, book_id
    ready["srv"].shutdown()
    ready["srv"].server_close()
    server.clear_cache()


def fetch(origin, path):
    try:
        with urllib.request.urlopen(origin + path, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


class TestRoutes:
    def test_library_index_lists_the_book(self, reader_server):
        origin, book_id = reader_server
        status, ctype, body = fetch(origin, "/")
        assert status == 200
        assert b"Fitness &amp; Nutrition" in body or b"Fitness & Nutrition" in body
        assert f"/read/{book_id}".encode() in body

    def test_chapter_page_renders(self, reader_server):
        origin, book_id = reader_server
        status, ctype, body = fetch(origin, f"/read/{book_id}")
        assert status == 200
        html = body.decode("utf-8")
        assert "Contents" in html
        assert "?p=2" in html  # next-page navigation

    def test_page_is_clamped_not_rejected(self, reader_server):
        origin, book_id = reader_server
        for page in ("0", "-3", "999"):
            status, _, _ = fetch(origin, f"/read/{book_id}?p={page}")
            assert status == 200, page

    def test_unknown_book_is_404(self, reader_server):
        origin, _ = reader_server
        assert fetch(origin, "/read/9999")[0] == 404

    def test_non_numeric_id_is_400(self, reader_server):
        origin, _ = reader_server
        assert fetch(origin, "/read/abc")[0] == 400

    def test_unknown_route_is_404(self, reader_server):
        origin, _ = reader_server
        assert fetch(origin, "/nope")[0] == 404

    def test_css_asset_is_served_with_its_type(self, reader_server):
        origin, book_id = reader_server
        status, ctype, body = fetch(origin, f"/asset/{book_id}/EPUB/style.css")
        assert status == 200
        assert ctype.startswith("text/css")

    def test_cover_is_served_as_an_image(self, reader_server):
        origin, book_id = reader_server
        status, ctype, body = fetch(origin, f"/cover/{book_id}")
        assert status == 200
        assert ctype == "image/png"
        assert body[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.parametrize(
        "attempt",
        [
            "/asset/{id}/../../config.py",
            "/asset/{id}/%2e%2e/%2e%2e/config.py",
            "/asset/{id}//etc/passwd",
            "/asset/{id}/EPUB/../../../win.ini",
        ],
    )
    def test_traversal_requests_are_rejected(self, reader_server, attempt):
        origin, book_id = reader_server
        status, _, _ = fetch(origin, attempt.format(id=book_id))
        assert status == 404, attempt

    def test_missing_asset_is_404(self, reader_server):
        origin, book_id = reader_server
        assert fetch(origin, f"/asset/{book_id}/EPUB/nope.css")[0] == 404


class TestRendering:
    def test_book_css_cannot_override_the_reader_foreground(self, reader_server):
        """Regression: the book's stylesheet was injected AFTER the reader
        chrome, so on equal specificity it won the cascade. Every generated
        book ships `body { color: #1a1a1a }`, which on the reader's
        #12141a background is a 1.06:1 contrast ratio — the text was
        present in the page but invisible. Chrome must come last.
        """
        origin, book_id = reader_server
        status, _, body = fetch(origin, f"/read/{book_id}")
        assert status == 200
        blocks = re.findall(r"<style>(.*?)</style>", body.decode("utf-8"), re.S)
        assert len(blocks) == 2, "expected book CSS + reader chrome CSS"
        book_css, chrome = blocks[0], blocks[1]

        # book typography first, chrome last
        assert "EPUB stylesheet" in book_css, "block 0 should be the book's"
        assert "topbar" in chrome, "block 1 should be the reader chrome"

        # the winning body colour must be ours, not the book's literal hex
        winner = re.findall(r"(?m)^\s*body\s*\{[^}]*?color:\s*([^;]+);", chrome)
        assert winner and winner[0] == "var(--ink)", winner

        # article text is forced onto the reader's foreground so a book's
        # dark-on-light heading colours cannot survive either
        assert "article :is(" in chrome
        assert "--bg:" in chrome and "--ink:" in chrome

    def test_article_typography_is_left_to_the_book(self, reader_server):
        """The reader owns contrast; the book owns size, spacing and font."""
        origin, book_id = reader_server
        _, _, body = fetch(origin, f"/read/{book_id}")
        chrome = re.findall(r"<style>(.*?)</style>", body.decode("utf-8"), re.S)[-1]
        assert "article > h1" not in chrome
        assert "article p, article li" not in chrome
