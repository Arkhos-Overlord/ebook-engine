"""Batch generator: every book gets its full set of artifacts."""

import zipfile
from pathlib import Path

import ebook_engine.batch_generate as batch
import pytest
from ebook_engine.validators import validate_epub, validate_kdp_zip, validate_pdf


@pytest.fixture()
def batch_env(tmp_path, temp_catalog, monkeypatch):
    """Point the batch at a throwaway output directory and catalog."""
    monkeypatch.setattr(batch, "OUTPUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()
    return tmp_path / "out"


@pytest.mark.parametrize("niche", ["Digital Marketing", "Term Insurance"])
def test_builds_every_artifact(batch_env, niche):
    status = batch.generate_single_book(niche)

    assert status["ok"] is True
    assert status["niche"] == niche
    for expected in ("cover", "epub", "pdf", "kdp", "gumroad"):
        assert expected in status["built"], (
            f"{expected} missing; built={status['built']} skipped={status['skipped']}"
        )
    assert not status["skipped"], status["skipped"]

    epub = batch_env / f"{niche.lower().replace(' ', '-')}.epub"
    pdf = batch_env / f"{niche.lower().replace(' ', '-')}.pdf"
    kdp = batch_env / f"{niche.lower().replace(' ', '-')}.kdp.zip"
    gumroad = batch_env / f"{niche.lower().replace(' ', '-')}.gumroad.zip"
    cover = batch_env / niche.lower().replace(" ", "-") / "cover.png"

    for path in (epub, pdf, kdp, gumroad, cover):
        assert path.is_file(), path


def test_built_artifacts_all_validate(batch_env):
    """Gate G3 on a real batch output, not a fixture."""
    status = batch.generate_single_book("Stock Trading")
    assert status["ok"]
    slug = "stock-trading"

    assert validate_epub(batch_env / f"{slug}.epub") == []
    assert validate_pdf(batch_env / f"{slug}.pdf") == []
    assert validate_kdp_zip(batch_env / f"{slug}.kdp.zip") == []


def test_epub_carries_front_and_back_matter(batch_env):
    from ebook_engine.epub_reader import read_epub

    batch.generate_single_book("Digital Marketing")
    book = read_epub(batch_env / "digital-marketing.epub")
    hrefs = {c.href.rsplit("/", 1)[-1] for c in book.chapters}
    assert "title_page.xhtml" in hrefs
    assert "copyright.xhtml" in hrefs
    assert "about_author.xhtml" in hrefs


def test_gumroad_bundle_holds_both_formats(batch_env):
    batch.generate_single_book("Travel")
    path = batch_env / "travel.gumroad.zip"
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        product = zf.read("product.json").decode("utf-8")
    assert any(n.endswith(".epub") for n in names)
    assert any(n.endswith(".pdf") for n in names)
    assert any(n.endswith(".png") for n in names)
    assert '"title": "Travel"' in product


def test_catalog_row_records_only_existing_files(batch_env, temp_catalog):
    """Regression: a failed build used to leave a phantom file_epub path."""
    from ebook_engine.catalog import list_books

    status = batch.generate_single_book("Photography")
    assert status["ok"]
    rows = list_books()
    assert len(rows) == 1
    row = rows[0]
    for key in ("file_epub", "file_pdf", "cover_path"):
        assert row[key] and Path(row[key]).is_file(), (key, row[key])
    assert row["description"] and len(row["description"]) >= 100


def test_rerunning_does_not_duplicate_rows(batch_env, temp_catalog):
    """The batch is re-runnable: upsert matches on title case-insensitively."""
    from ebook_engine.catalog import list_books, upsert_book

    batch.generate_single_book("Travel")
    batch.generate_single_book("Travel")
    assert len(list_books()) == 1

    # ...and the case-insensitive match holds for an equivalent spelling
    upsert_book(
        title="travel",
        author="A",
        genre="Lifestyle",
        isbn="9780000000001",
        price_tier="standard",
        price_inr=799.0,
    )
    assert len(list_books()) == 1


def test_isbn_is_stable_across_runs(batch_env, temp_catalog):
    first = batch.generate_single_book("Cryptocurrency")
    assert first["ok"]
    from ebook_engine.catalog import list_books

    isbn_first = list_books()[0]["isbn"]
    batch.generate_single_book("Cryptocurrency")
    assert list_books()[0]["isbn"] == isbn_first


def test_assessment_is_returned_for_the_gate(batch_env, monkeypatch):
    """The batch must hand back the gate's verdict, not just a word count.

    The author is forced to a placeholder so the assertion holds whatever
    EBOOK_AUTHOR is set to on this machine — the test previously read the
    ambient .env and started failing as soon as a real name was configured.
    """
    import ebook_engine.corpus as corpus

    monkeypatch.setattr(corpus, "_AUTHOR", "Anonymous")

    status = batch.generate_single_book("Web Development")
    assessment = status["assessment"]
    assert assessment is not None
    assert assessment.channel == "kdp"
    assert status["words"] > 3000
    assert assessment.errors
    assert any("author" in e for e in assessment.errors)


def test_a_configured_author_clears_the_gate(batch_env, monkeypatch):
    """The mirror image: a real name must not be reported as a placeholder."""
    import ebook_engine.corpus as corpus

    monkeypatch.setattr(corpus, "_AUTHOR", "NEYAN")

    status = batch.generate_single_book("Web Development")
    assessment = status["assessment"]
    assert not any("placeholder" in e for e in assessment.errors), assessment.errors
    assert status["ok"] is True


def test_failed_builder_is_recorded_not_silently_dropped(batch_env, monkeypatch):
    """A broken formatter must show up as skipped, not as a built artifact."""

    def explode(book_data, output_path):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(batch, "create_pdf", explode)
    status = batch.generate_single_book("Travel")
    assert "pdf" in status["skipped"]
    assert "pdf" not in status["built"]
    # EPUB still built, and the batch still reports success overall
    assert "epub" in status["built"]
    assert status["ok"] is True
