"""Catalog manager — SQLite-backed book metadata storage."""

import csv
import hashlib
import io
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from ebook_engine.config import CONFIG_DIR, DB_PATH

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT DEFAULT 'Anonymous',
        genre TEXT,
        isbn TEXT,
        description TEXT,
        price_tier TEXT,
        price_inr REAL,
        file_epub TEXT,
        file_mobi TEXT,
        file_pdf TEXT,
        file_kdp TEXT,
        file_gumroad TEXT,
        cover_path TEXT,
        status TEXT DEFAULT 'draft',
        created_at TEXT,
        updated_at TEXT
    )
"""

# Columns added after the first schema shipped. SQLite cannot alter a
# table's column list, so existing catalogs are migrated in place the
# first time they are opened.
_EXTRA_COLUMNS = (
    ("file_kdp", "TEXT DEFAULT ''"),
    ("file_gumroad", "TEXT DEFAULT ''"),
)

_COLUMNS = (
    "title",
    "author",
    "genre",
    "isbn",
    "description",
    "price_tier",
    "price_inr",
    "file_epub",
    "file_mobi",
    "file_pdf",
    "file_kdp",
    "file_gumroad",
    "cover_path",
)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any column the running code expects but the table lacks."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
    for name, declaration in _EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE books ADD COLUMN {name} {declaration}")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a catalog connection; creates the table and closes on exit."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_SCHEMA)
        _migrate(conn)
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _insert(conn: sqlite3.Connection, values: dict) -> int:
    """Insert one row from the shared column list. Returns the new row id."""
    cols = ", ".join(_COLUMNS)
    marks = ", ".join("?" for _ in _COLUMNS)
    now = datetime.now().isoformat()
    params = [values.get(c, "") for c in _COLUMNS]
    cursor = conn.execute(
        f"INSERT INTO books ({cols}, status, created_at, updated_at) "
        f"VALUES ({marks}, 'draft', ?, ?)",
        (*params, now, now),
    )
    return int(cursor.lastrowid or 0)


def make_isbn(slug: str) -> str:
    """Return a deterministic ISBN-13 for a placeholder slug.

    Uses blake2b (process-stable, unlike hash() which is salted by
    PYTHONHASHSEED) so re-running batch generation never mints new ISBNs for
    the same book. These are syntactically valid ISBN-13s with a correct
    ISO 7064 MOD 10-2 check digit, but they are PLACEHOLDERS: they are not
    assigned to or owned by anyone and must not be used to publish on KDP.
    """
    digest = hashlib.blake2b(slug.encode("utf-8"), digest_size=8).hexdigest()
    body = "978" + f"{int(digest, 16) % 1_000_000_000:09d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def add_book(
    title: str,
    author: str,
    genre: str,
    isbn: str,
    price_tier: str,
    price_inr: float,
    file_epub: str = "",
    file_mobi: str = "",
    file_pdf: str = "",
    file_kdp: str = "",
    file_gumroad: str = "",
    cover_path: str = "",
    description: str = "",
) -> int:
    """Add a new book to the catalog. Returns the book ID."""
    values = {
        "title": title,
        "author": author,
        "genre": genre,
        "isbn": isbn,
        "description": description,
        "price_tier": price_tier,
        "price_inr": price_inr,
        "file_epub": file_epub,
        "file_mobi": file_mobi,
        "file_pdf": file_pdf,
        "file_kdp": file_kdp,
        "file_gumroad": file_gumroad,
        "cover_path": cover_path,
    }
    with connect() as conn:
        return _insert(conn, values)


def upsert_book(
    title: str,
    author: str,
    genre: str,
    isbn: str,
    price_tier: str,
    price_inr: float,
    file_epub: str = "",
    file_mobi: str = "",
    file_pdf: str = "",
    file_kdp: str = "",
    file_gumroad: str = "",
    cover_path: str = "",
    description: str = "",
) -> int:
    """Insert a book, or refresh the existing row with the same title.

    Batch generation is re-runnable, so re-running it must not stack duplicate
    catalog rows. Matches on title (case-insensitive) and refreshes the file
    paths, price and metadata, preserving the row's id and created_at.
    Returns the book ID either way.
    """
    now = datetime.now().isoformat()
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM books WHERE LOWER(title) = LOWER(?) ORDER BY id LIMIT 1",
            (title,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE books SET author = ?, genre = ?, isbn = ?,
                                 description = ?, price_tier = ?, price_inr = ?,
                                 file_epub = COALESCE(NULLIF(?, ''), file_epub),
                                 file_mobi = COALESCE(NULLIF(?, ''), file_mobi),
                                 file_pdf  = COALESCE(NULLIF(?, ''), file_pdf),
                                 file_kdp  = COALESCE(NULLIF(?, ''), file_kdp),
                                 file_gumroad = COALESCE(NULLIF(?, ''), file_gumroad),
                                 cover_path = COALESCE(NULLIF(?, ''), cover_path),
                                 updated_at = ?
                WHERE id = ?
                """,
                (
                    author,
                    genre,
                    isbn,
                    description,
                    price_tier,
                    price_inr,
                    file_epub,
                    file_mobi,
                    file_pdf,
                    file_kdp,
                    file_gumroad,
                    cover_path,
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"])
        return _insert(
            conn,
            {
                "title": title,
                "author": author,
                "genre": genre,
                "isbn": isbn,
                "description": description,
                "price_tier": price_tier,
                "price_inr": price_inr,
                "file_epub": file_epub,
                "file_mobi": file_mobi,
                "file_pdf": file_pdf,
                "file_kdp": file_kdp,
                "file_gumroad": file_gumroad,
                "cover_path": cover_path,
            },
        )


def dedupe_books() -> int:
    """Remove duplicate title rows, keeping the most recent of each.

    Returns the number of rows deleted. Use this after several batch runs
    accumulated copies of the same book.
    """
    with connect() as conn:
        dupes = conn.execute(
            """
            SELECT id FROM books
            WHERE id NOT IN (SELECT MAX(id) FROM books GROUP BY LOWER(title))
            """
        ).fetchall()
        conn.executemany("DELETE FROM books WHERE id = ?", [(r["id"],) for r in dupes])
        return len(dupes)


def list_books(status: str | None = None) -> list[dict]:
    """List all books, optionally filtered by status."""
    query = "SELECT * FROM books"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY created_at DESC, id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_book(book_id: int) -> dict | None:
    """Get a single book by ID, or None if it does not exist."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None


def update_status(book_id: int, status: str) -> None:
    """Update book status (draft/published/sold)."""
    with connect() as conn:
        conn.execute(
            "UPDATE books SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), book_id),
        )


def update_files(
    book_id: int,
    file_epub: str = "",
    file_mobi: str = "",
    file_pdf: str = "",
    file_kdp: str = "",
    file_gumroad: str = "",
    cover_path: str = "",
) -> None:
    """Update file paths for a book. Only non-empty values are written."""
    updates = []
    params = []
    for column, value in (
        ("file_epub", file_epub),
        ("file_mobi", file_mobi),
        ("file_pdf", file_pdf),
        ("file_kdp", file_kdp),
        ("file_gumroad", file_gumroad),
        ("cover_path", cover_path),
    ):
        if value:
            updates.append(f"{column} = ?")
            params.append(value)
    if not updates:
        return
    updates.append("updated_at = ?")
    params.extend([datetime.now().isoformat(), book_id])
    with connect() as conn:
        conn.execute(f"UPDATE books SET {', '.join(updates)} WHERE id = ?", params)


def export_catalog(format: str = "json") -> str:
    """Export catalog as JSON or CSV string."""
    books = list_books()
    if format == "json":
        return json.dumps(books, indent=2, default=str)
    output = io.StringIO()
    if books:
        writer = csv.DictWriter(output, fieldnames=list(books[0].keys()))
        writer.writeheader()
        writer.writerows(books)
    return output.getvalue()


def get_stats() -> dict:
    """Get catalog statistics in a single query."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) AS published,
                   SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) AS draft
            FROM books
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "published": int(row["published"] or 0),
        "draft": int(row["draft"] or 0),
    }
