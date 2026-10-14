"""Local EPUB reader — an HTTP server bound to loopback only.

Design notes:
  * Bound to 127.0.0.1 and never a public interface: this serves a
    user's library and has no authentication.
  * Assets are read straight out of the EPUB ZIP by name. The name is
    first normalised and must appear in the archive's own listing, so a
    path like `../../etc/passwd` can never reach the filesystem — there
    is no filesystem lookup to escape in the first place.
  * Parsed books are cached by path + mtime so flipping pages does not
    re-parse the archive.
"""

import posixpath
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from lxml import html as lxml_html

from ebook_engine.config import TEMPLATES_DIR
from ebook_engine.epub_reader import EpubBook, EpubError, read_epub

_HOST = "127.0.0.1"
_TEMPLATE_DIR = TEMPLATES_DIR / "reader"

_cache: dict = {}
_cache_lock = threading.Lock()


def _load_template(name: str):
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template(name)


def get_book(path) -> EpubBook:
    """Parse and cache an EPUB, re-reading when the file changes."""
    path = Path(str(path))
    key = str(path.resolve())
    stamp = path.stat().st_mtime
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
    book = read_epub(path)
    with _cache_lock:
        _cache[key] = (stamp, book)
    return book


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def library_entries() -> list:
    """Catalog rows whose EPUB file actually exists on disk."""
    from ebook_engine.catalog import list_books

    entries = []
    for row in list_books():
        path = row.get("file_epub") or ""
        if path and Path(path).is_file():
            entries.append(row)
    return entries


def read_asset(source_path, name: str):
    """Read a member of the EPUB archive by name, or None.

    Safe by construction: `ZipFile.read` looks the name up in the central
    directory and never touches the filesystem, and we additionally
    require the exact name to be listed in the archive.
    """
    name = unquote(name)
    if not name or name.startswith("/") or "\\" in name:
        return None
    normalised = posixpath.normpath(name)
    if normalised.startswith(".."):
        return None
    try:
        with zipfile.ZipFile(str(source_path)) as zf:
            if normalised not in zf.namelist():
                return None
            return zf.read(normalised)
    except (zipfile.BadZipFile, OSError):
        return None


def rewrite_urls(body: str, chapter_href: str, book_id) -> str:
    """Point relative src/href values at /asset/<id>/... so images and
    links resolve from the reader page instead of the browser's path."""
    if not body:
        return ""
    try:
        wrapper = lxml_html.fragment_fromstring(body, create_parent="div")
    except Exception:
        return body

    base = posixpath.dirname(chapter_href)
    for element in wrapper.iter():
        for attr in ("src", "href"):
            value = element.get(attr)
            if not value or _is_external(value):
                continue
            resolved = posixpath.normpath(posixpath.join(base, unquote(value)))
            element.set(attr, f"/asset/{book_id}/{quote(resolved)}")

    return lxml_html.tostring(wrapper, encoding="unicode", method="html")


def _is_external(value: str) -> bool:
    return value.startswith(
        ("http://", "https://", "//", "#", "mailto:", "data:", "javascript:")
    ) or value.startswith("/")


def read_asset_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".css"):
        return "text/css; charset=utf-8"
    if lowered.endswith((".png",)):
        return "image/png"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".gif"):
        return "image/gif"
    if lowered.endswith(".svg"):
        return "image/svg+xml"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith((".woff",)):
        return "font/woff"
    if lowered.endswith(".woff2"):
        return "font/woff2"
    return "application/octet-stream"


class _Handler(BaseHTTPRequestHandler):
    """Routes: /, /read/<id>, /asset/<id>/<path>, /cover/<id>."""

    server_version = "EbookReader/1.0"

    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        try:
            self._route(parsed.path, parse_qs(parsed.query))
        except BrokenPipeError:
            pass
        except Exception as e:  # never let one bad request kill the server
            self._send(500, "text/plain; charset=utf-8", f"Error: {e}".encode())

    def _route(self, path: str, query: dict) -> None:
        parts = [p for p in path.split("/") if p]

        if not parts:
            return self._index()
        if parts[0] == "read" and len(parts) >= 2:
            page = int((query.get("p") or ["1"])[0] or 1)
            return self._chapter(parts[1], page)
        if parts[0] == "asset" and len(parts) >= 3:
            return self._asset(parts[1], "/".join(parts[2:]))
        if parts[0] == "cover" and len(parts) >= 2:
            return self._cover(parts[1])
        self._send(404, "text/plain; charset=utf-8", b"Not found")

    def _index(self) -> None:
        template = _load_template("index.html")
        body = template.render(books=library_entries())
        self._send(200, "text/html; charset=utf-8", body.encode("utf-8"))

    def _chapter(self, book_id: str, page: int) -> None:
        _, book = self._resolve(book_id)
        if book is None:
            return
        if not book.chapters:
            return self._send(404, "text/plain; charset=utf-8", b"Book has no chapters")
        page = max(1, min(page, len(book.chapters)))
        chapter = book.chapters[page - 1]

        css = "\n".join(book.stylesheets.values())
        body_html = rewrite_urls(chapter.body, chapter.href, book_id)

        template = _load_template("chapter.html")
        rendered = template.render(
            book=book,
            book_id=book_id,
            chapter=chapter,
            chapters=book.chapters,
            page=page,
            total=len(book.chapters),
            body_html=body_html,
            book_css=css,
            has_cover=bool(book.cover_name),
            cover_url=f"/cover/{book_id}" if book.cover_name else "",
            title=book.title,
        )
        self._send(200, "text/html; charset=utf-8", rendered.encode("utf-8"))

    def _asset(self, book_id: str, name: str) -> None:
        _, book = self._resolve(book_id)
        if book is None:
            return
        data = read_asset(book.source_path, name)
        if data is None:
            return self._send(404, "text/plain; charset=utf-8", b"Asset not found")
        self._send(200, read_asset_type(name), data)

    def _cover(self, book_id: str) -> None:
        _, book = self._resolve(book_id)
        if book is None:
            return
        if not book.cover_name:
            return self._send(404, "text/plain; charset=utf-8", b"No cover")
        data = read_asset(book.source_path, book.cover_name)
        if data is None:
            return self._send(404, "text/plain; charset=utf-8", b"Cover not found")
        self._send(200, read_asset_type(book.cover_name), data)

    def _resolve(self, book_id: str):
        """Look up a catalog row and its parsed book, or send an error."""
        if not book_id.isdigit():
            self._send(400, "text/plain; charset=utf-8", b"Bad book id")
            return None, None
        from ebook_engine.catalog import get_book

        row = get_book(int(book_id))
        if not row:
            self._send(404, "text/plain; charset=utf-8", b"Book not found")
            return None, None
        path = row.get("file_epub") or ""
        if not path or not Path(path).is_file():
            self._send(404, "text/plain; charset=utf-8", b"EPUB file missing")
            return None, None
        try:
            return row, get_book_file(path)
        except EpubError as e:
            self._send(422, "text/plain; charset=utf-8", f"Unreadable EPUB: {e}".encode())
            return None, None

    def _send(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        """Keep the console quiet; the CLI prints its own status."""


def get_book_file(path) -> EpubBook:
    """Thin alias so the handler reads clearly."""
    return get_book(path)


def make_server(host: str = _HOST, port: int = 0) -> ThreadingHTTPServer:
    """Build a server bound to loopback. port=0 picks a free port."""
    return ThreadingHTTPServer((host, port), _Handler)


def serve(
    port: int = 8765,
    book_id=None,
    open_browser: bool = True,
    ready=None,
) -> None:
    """Run the reader until interrupted.

    Args:
        port: TCP port; 0 asks the OS for a free one.
        book_id: open this book directly instead of the library index.
        open_browser: launch the default browser at the right URL.
        ready: optional callback(server, url) invoked once listening —
            used by tests to make requests before blocking.
    """
    server = make_server(port=port)
    host, actual = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{actual}/" + (f"read/{book_id}" if book_id else "")

    print(f"EPUB reader running at http://{host}:{actual}/  (Ctrl+C to stop)")
    if book_id:
        print(f"  Reading book {book_id}")

    if ready is not None:
        ready(server, url)

    if open_browser:
        threading.Thread(target=_open, args=(url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReader stopped.")
    finally:
        server.server_close()


def _open(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass
