"""Reading and writing chapter_NN.md files.

These helpers exist because three callers used to disagree about the
layout, and batch_generate regenerating from the corpus wiped expanded
chapters.
"""

from ebook_engine.manuscript import read_chapters, write_chapter


def test_missing_directory_returns_no_chapters(tmp_path):
    assert read_chapters(tmp_path / "nowhere") == []


def test_writes_heading_then_body(tmp_path):
    path = write_chapter(tmp_path, 1, "Real Title", "Body text.")
    assert path.name == "chapter_01.md"
    assert path.read_text(encoding="utf-8") == "## Real Title\n\nBody text."


def test_round_trips_title_and_body(tmp_path):
    write_chapter(tmp_path, 3, "A Title Worth Keeping", "First para.\n\nSecond.")
    chapters = read_chapters(tmp_path)
    assert len(chapters) == 1
    assert chapters[0]["number"] == 3
    assert chapters[0]["title"] == "A Title Worth Keeping"
    assert "Second." in chapters[0]["content"]
    # the heading is not part of the body, or it would double up next write
    assert not chapters[0]["content"].startswith("#")


def test_unheaded_file_falls_back_to_chapter_number(tmp_path):
    (tmp_path / "chapter_02.md").write_text("Plain body with no heading.", encoding="utf-8")
    chapters = read_chapters(tmp_path)
    assert chapters[0]["title"] == "Chapter 2"
    assert chapters[0]["content"] == "Plain body with no heading."


def test_overwrite_keeps_the_previous_version(tmp_path):
    """The .bak is what makes expansion recoverable."""
    write_chapter(tmp_path, 1, "Title", "original words")
    write_chapter(tmp_path, 1, "Title", "much longer expanded content here")
    assert "original words" in (tmp_path / "chapter_01.md.bak").read_text(encoding="utf-8")
    assert "much longer" in (tmp_path / "chapter_01.md").read_text(encoding="utf-8")


def test_read_ignores_unrecognised_filenames(tmp_path):
    write_chapter(tmp_path, 1, "Title", "Body.")
    (tmp_path / "outline.md").write_text("# Outline", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a chapter", encoding="utf-8")
    (tmp_path / "chapter_x.md").write_text("bad number", encoding="utf-8")
    chapters = read_chapters(tmp_path)
    assert [c["number"] for c in chapters] == [1]


def test_reads_chapters_in_numeric_not_lexicographic_order(tmp_path):
    for n in (1, 2, 10, 11):
        write_chapter(tmp_path, n, f"C{n}", "Body.")
    assert [c["number"] for c in read_chapters(tmp_path)] == [1, 2, 10, 11]


def test_empty_file_yields_empty_string_body(tmp_path):
    (tmp_path / "chapter_01.md").write_text("", encoding="utf-8")
    chapters = read_chapters(tmp_path)
    assert chapters[0]["content"] == ""
    assert chapters[0]["title"] == "Chapter 1"


class TestPreservation:
    """The bug this module was written for."""

    def test_longer_on_disk_content_wins_over_the_corpus(self, tmp_path, temp_catalog, monkeypatch):
        import ebook_engine.batch_generate as batch
        from ebook_engine.corpus import generate_book

        monkeypatch.setattr(batch, "OUTPUT_DIR", tmp_path)
        tmp_path.mkdir(exist_ok=True)

        # Seed every chapter at expanded length, as `expand` would leave it:
        # longer in total than the ~4,200-word corpus chapter set.
        corpus_words = sum(
            len(c["content"].split()) for c in generate_book("Travel", "Lifestyle", 5)["chapters"]
        )
        target = corpus_words // 5 + 50
        for n in range(1, 6):
            write_chapter(tmp_path / "travel", n, f"Expanded Chapter {n}", "word " * target)

        status = batch.generate_single_book("Travel")
        assert status["ok"]
        assert status.get("content_preserved") is True, status["content"]
        assert status["content"].startswith("kept")

        chapters = read_chapters(tmp_path / "travel")
        assert len(chapters) == 5
        # preserved, not replaced by the shorter corpus chapters
        assert words(chapters[0]["content"]) >= target
        assert chapters[0]["title"] == "Expanded Chapter 1"

    def test_corpus_content_is_written_when_disk_is_empty(
        self, tmp_path, temp_catalog, monkeypatch
    ):
        import ebook_engine.batch_generate as batch

        monkeypatch.setattr(batch, "OUTPUT_DIR", tmp_path)
        tmp_path.mkdir(exist_ok=True)

        status = batch.generate_single_book("Travel")
        assert status["ok"]
        assert status["content"] == "corpus"
        assert "content_preserved" not in status
        assert len(read_chapters(tmp_path / "travel")) == 5


def words(text: str) -> int:
    return len(text.split())
