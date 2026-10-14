"""Catalog CRUD, dedupe and deterministic ISBN tests."""

import re

import ebook_engine.catalog as catalog


def _add(temp_catalog, title="Test Book", **kw):
    kwargs = dict(
        title=title,
        author="A. Author",
        genre="Business",
        isbn="9780000000000",
        price_tier="basic",
        price_inr=349.0,
        description="A description that must survive",
    )
    kwargs.update(kw)
    return catalog.add_book(**kwargs)


def test_add_book_persists_description(temp_catalog):
    """Regression: add_book used to accept `description` and silently drop it."""
    book_id = _add(temp_catalog)
    row = catalog.get_book(book_id)
    assert row is not None
    assert row["description"] == "A description that must survive"


def test_add_book_persists_every_column(temp_catalog):
    book_id = _add(
        temp_catalog,
        title="Full Row",
        file_epub="/tmp/a.epub",
        file_mobi="/tmp/a.mobi",
        file_pdf="/tmp/a.pdf",
        cover_path="/tmp/a.png",
    )
    row = catalog.get_book(book_id)
    assert row["file_epub"] == "/tmp/a.epub"
    assert row["file_mobi"] == "/tmp/a.mobi"
    assert row["file_pdf"] == "/tmp/a.pdf"
    assert row["cover_path"] == "/tmp/a.png"
    assert row["status"] == "draft"
    assert row["created_at"] and row["updated_at"]


def test_upsert_persists_description(temp_catalog):
    book_id = catalog.upsert_book(
        title="Upserted",
        author="A",
        genre="Finance",
        isbn="9780000000001",
        price_tier="standard",
        price_inr=799.0,
        description="upsert description",
    )
    assert catalog.get_book(book_id)["description"] == "upsert description"


def test_upsert_does_not_stack_duplicates(temp_catalog):
    for i in range(5):
        catalog.upsert_book(
            title="Same Title",
            author="A",
            genre="Business",
            isbn=f"978000000000{i}",
            price_tier="basic",
            price_inr=349.0,
        )
    assert len(catalog.list_books()) == 1


def test_upsert_refreshes_paths_but_keeps_id(temp_catalog):
    first = catalog.upsert_book(
        title="Refreshable",
        author="A",
        genre="Business",
        isbn="9780000000002",
        price_tier="basic",
        price_inr=349.0,
        file_epub="/old.epub",
    )
    second = catalog.upsert_book(
        title="refreshable",
        author="B",
        genre="Finance",
        isbn="9780000000003",
        price_tier="premium",
        price_inr=1499.0,
        file_epub="/new.epub",
    )
    assert first == second
    row = catalog.get_book(second)
    assert row["file_epub"] == "/new.epub"
    assert row["author"] == "B"
    assert row["price_tier"] == "premium"


def test_dedupe_collapses_duplicate_titles(temp_catalog):
    for i in range(8):
        catalog.add_book(
            title="Repeated",
            author="A",
            genre="Business",
            isbn=f"978000000000{i}",
            price_tier="basic",
            price_inr=349.0,
        )
    catalog.add_book(
        title="Unique",
        author="A",
        genre="Business",
        isbn="9780000000009",
        price_tier="basic",
        price_inr=349.0,
    )
    assert len(catalog.list_books()) == 9
    removed = catalog.dedupe_books()
    assert removed == 7
    assert len(catalog.list_books()) == 2


def test_dedupe_is_case_insensitive(temp_catalog):
    for title in ("Hello", "HELLO", "hello"):
        catalog.add_book(
            title=title,
            author="A",
            genre="Business",
            isbn="9780000000000",
            price_tier="basic",
            price_inr=349.0,
        )
    catalog.dedupe_books()
    assert len(catalog.list_books()) == 1


def test_get_stats_single_query(temp_catalog):
    _add(temp_catalog, title="Draft One")
    published = _add(temp_catalog, title="Published One")
    catalog.update_status(published, "published")
    stats = catalog.get_stats()
    assert stats == {"total": 2, "published": 1, "draft": 1}


def test_get_book_returns_none_for_missing(temp_catalog):
    assert catalog.get_book(99999) is None


def test_update_files_ignores_empty_values(temp_catalog):
    book_id = _add(temp_catalog, title="Paths", file_epub="/keep.epub")
    catalog.update_files(book_id, file_epub="", file_pdf="/actual.pdf")
    row = catalog.get_book(book_id)
    assert row["file_epub"] == "/keep.epub"
    assert row["file_pdf"] == "/actual.pdf"
    assert row["file_mobi"] == ""


def test_list_books_status_filter(temp_catalog):
    a = _add(temp_catalog, title="A")
    b = _add(temp_catalog, title="B")
    catalog.update_status(b, "published")
    assert [x["id"] for x in catalog.list_books("published")] == [b]
    assert len(catalog.list_books("draft")) == 1
    assert len(catalog.list_books()) == 2
    assert a != b


def test_export_json_and_csv(temp_catalog):
    _add(temp_catalog, title="Exported")
    as_json = catalog.export_catalog("json")
    as_csv = catalog.export_catalog("csv")
    assert '"Exported"' in as_json
    assert "Exported" in as_csv
    assert as_csv.splitlines()[0].startswith("id,title,author,genre")


class TestMakeIsbn:
    def test_deterministic_across_calls(self):
        assert catalog.make_isbn("digital marketing") == catalog.make_isbn("digital marketing")

    def test_differs_per_slug(self):
        assert catalog.make_isbn("travel") != catalog.make_isbn("cooking")

    def test_shape_is_isbn13(self):
        isbn = catalog.make_isbn("photography")
        assert isbn.startswith("978")
        assert re.fullmatch(r"\d{13}", isbn), isbn

    def test_check_digit_is_valid(self):
        body = catalog.make_isbn("e-commerce")[:12]
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
        expected = str((10 - total % 10) % 10)
        assert catalog.make_isbn("e-commerce")[12] == expected

    def test_not_broken_by_hash_seed(self):
        """hash() is salted per process; blake2b is not. Stable across runs."""
        assert catalog.make_isbn("web development") == catalog.make_isbn("web development")


class TestStorePackageColumns:
    """The KDP and Gumroad bundles are built but were not recorded anywhere,
    so nothing could tell you where they went."""

    def test_fresh_schema_has_both_columns(self, temp_catalog):
        row = catalog.get_book(
            catalog.add_book(
                title="T",
                author="A",
                genre="G",
                isbn="",
                price_tier="basic",
                price_inr=349.0,
            )
        )
        assert "file_kdp" in row
        assert "file_gumroad" in row

    def test_existing_database_is_migrated_in_place(self, tmp_path, monkeypatch):
        """An older catalog lacks the columns; opening it must add them
        without losing the rows already there."""
        import sqlite3

        import ebook_engine.config as config

        legacy = tmp_path / "legacy.db"
        conn = sqlite3.connect(legacy)
        conn.execute(
            """CREATE TABLE books (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   title TEXT NOT NULL, author TEXT, genre TEXT, isbn TEXT,
                   description TEXT, price_tier TEXT, price_inr REAL,
                   file_epub TEXT, file_mobi TEXT, file_pdf TEXT,
                   cover_path TEXT, status TEXT, created_at TEXT, updated_at TEXT
               )"""
        )
        conn.execute("INSERT INTO books (title, author) VALUES ('Legacy Book', 'A. Writer')")
        conn.commit()
        conn.close()

        monkeypatch.setattr(catalog, "DB_PATH", legacy)
        monkeypatch.setattr(catalog, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(config, "DB_PATH", legacy)

        row = catalog.get_book(1)
        assert row["title"] == "Legacy Book", "migration must not lose rows"
        assert row["file_kdp"] == ""
        assert row["file_gumroad"] == ""

    def test_upsert_records_package_paths(self, temp_catalog):
        book_id = catalog.upsert_book(
            title="Packaged",
            author="A",
            genre="G",
            isbn="",
            price_tier="standard",
            price_inr=799.0,
            file_epub="/out/book.epub",
            file_kdp="/out/book.kdp.zip",
            file_gumroad="/out/book.gumroad.zip",
        )
        row = catalog.get_book(book_id)
        assert row["file_kdp"] == "/out/book.kdp.zip"
        assert row["file_gumroad"] == "/out/book.gumroad.zip"

    def test_update_files_records_package_paths(self, temp_catalog):
        book_id = _add(temp_catalog, title="Paths")
        catalog.update_files(book_id, file_kdp="/a.kdp.zip", file_gumroad="/a.gumroad.zip")
        row = catalog.get_book(book_id)
        assert row["file_kdp"] == "/a.kdp.zip"
        assert row["file_gumroad"] == "/a.gumroad.zip"

    def test_update_files_ignores_empty_package_paths(self, temp_catalog):
        book_id = _add(temp_catalog, title="Kept")
        catalog.update_files(book_id, file_kdp="/real.kdp.zip")
        catalog.update_files(book_id, file_kdp="", file_gumroad="")
        row = catalog.get_book(book_id)
        assert row["file_kdp"] == "/real.kdp.zip"
        assert row["file_gumroad"] == ""
