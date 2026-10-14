"""Corpus resolution and the negative behaviours that must now raise (G6)."""

import ebook_engine.corpus as corpus
import pytest
from ebook_engine.content_engine import DEFAULT_CHAPTERS, generate_book


def test_known_niche_resolves_directly():
    result = generate_book("Digital Marketing", "business", 5)
    assert result["niche"] == "Digital Marketing"
    assert len(result["chapters"]) == 5


def test_all_niches_generate():
    for niche in corpus.get_all_niches():
        genre = corpus.get_niche_genre(niche)
        result = corpus.generate_book(niche, genre, 5)
        assert len(result["chapters"]) == 5, niche
        assert result["chapters"][0]["content"]


class TestNegativePaths:
    def test_unknown_topic_and_genre_raises(self):
        """Regression: an unknown genre used to silently return the
        Digital Marketing book."""
        with pytest.raises(ValueError, match="Unknown topic"):
            corpus.generate_book("Totally Made Up Topic", "Fashion", 5)

    def test_topic_that_is_not_a_niche_raises(self):
        """Regression: 'Python for Beginners' + technical silently returned
        a Web Development book under the wrong title."""
        with pytest.raises(ValueError, match="not a corpus niche"):
            corpus.generate_book("Python for Beginners", "technical", 5)

    def test_over_request_raises_instead_of_truncating(self):
        """Regression: --chapters 10 silently delivered 5."""
        with pytest.raises(ValueError, match="chapters"):
            corpus.generate_book("Digital Marketing", "business", 10)

    def test_zero_chapters_raises(self):
        with pytest.raises(ValueError, match=">= 1"):
            corpus.generate_book("Digital Marketing", "business", 0)

    def test_message_lists_available_niches(self):
        with pytest.raises(ValueError) as exc:
            corpus.generate_book("Nope", "Nope", 5)
        assert "Digital Marketing" in str(exc.value)


class TestContentShape:
    def test_every_niche_is_complete(self):
        for niche in corpus.get_all_niches():
            data = corpus.NICHE_CONTENT[niche]
            assert len(data["chapters"]) == 5, niche
            for chapter in data["chapters"]:
                assert len(chapter["content"]) == 4, (niche, chapter["title"])
                assert chapter["title"]

    def test_word_count_is_preserved(self):
        """Gate G4: the corpus must survive migrations byte-for-byte."""
        words = 0
        for data in corpus.NICHE_CONTENT.values():
            for chapter in data["chapters"]:
                for para in chapter["content"]:
                    words += len(para.split())
        assert words == 63719
        assert len(corpus.NICHE_CONTENT) == 15

    def test_outline_references_every_chapter(self):
        result = corpus.generate_book("Travel", "Lifestyle", 5)
        outline = result["outline"]
        assert outline.startswith("# Travel")
        for i, chapter in enumerate(result["chapters"], 1):
            assert f"## Chapter {i}: {chapter['title']}" in outline

    def test_chapters_carry_numbers_and_titles(self):
        result = corpus.generate_book("Travel", "Lifestyle", 5)
        assert [c["number"] for c in result["chapters"]] == [1, 2, 3, 4, 5]
        for chapter in result["chapters"]:
            assert chapter["title"].strip()

    def test_paragraphs_are_joined(self):
        result = corpus.generate_book("Travel", "Lifestyle", 5)
        assert "\n\n" in result["chapters"][0]["content"]


class TestCorpusHelpers:
    def test_genre_lookup(self):
        assert corpus.get_niche_genre("Digital Marketing") == "Business"
        assert corpus.get_niche_genre("Nope") == "General"

    def test_cover_color_lookup(self):
        color = corpus.get_niche_cover_color("Stock Trading")
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)
        assert corpus.get_niche_cover_color("Nope") == [0x1A, 0x1A, 0x2E]


class TestContentEngineModes:
    def test_corpus_is_the_default(self):
        result = generate_book("Photography", "Creative", 5)
        assert result["niche"] == "Photography"

    def test_explicit_corpus_mode(self):
        result = generate_book("Photography", "Creative", 5, mode="corpus")
        assert len(result["chapters"]) == 5

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            generate_book("Photography", "Creative", 5, mode="banana")

    def test_default_chapter_count_matches_the_corpus(self):
        """The CLI default must not exceed what the corpus can supply."""
        assert DEFAULT_CHAPTERS == 5
        result = generate_book("Photography", "Creative")
        assert len(result["chapters"]) == DEFAULT_CHAPTERS
