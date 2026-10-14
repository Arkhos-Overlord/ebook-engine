"""Publication quality gate, front/back matter and store packages."""

import zipfile

import pytest
from ebook_engine.config import KDP_MIN_WORDS, KDP_RECOMMENDED_WORDS
from ebook_engine.formatters.epub_formatter import create_epub
from ebook_engine.formatters.gumroad_zip import create_gumroad_package
from ebook_engine.formatters.kdp_zip import create_kdp_package
from ebook_engine.formatters.matter import (
    back_matter,
    collapse_escapes,
    describe_book,
    disclaimer_for,
    first_sentence,
    front_matter,
    needs_disclaimer,
)
from ebook_engine.formatters.quality import (
    assess,
    count_words,
    find_attributed_claims,
    find_repeated_passages,
)
from ebook_engine.validators import validate_epub, validate_kdp_zip, validate_pdf

# Enough body copy to clear KDP's word floor, so the happy-path fixture is
# genuinely publishable rather than failing on the very check it exists to pass.
_FLOOR_FILLER = " ".join(f"insight{i}" for i in range(1400))

GOOD_BOOK = {
    "topic": "Digital Marketing",
    "genre": "Business",
    "author": "Priya Raman",
    "language": "English",
    "publisher": "Raman Press",
    "subtitle": "A Practical Playbook",
    "author_bio": "Priya Raman has run growth for three venture-backed startups.",
    "description": (
        "Organic reach collapsed below five percent. This book shows what "
        "replaces it: owned channels, email, and content that survives an "
        "algorithm change, with numbers from 2024 and 2025."
    ),
    "chapters": [
        {
            "number": 1,
            "title": "Organic Reach Is Dead",
            "content": "Paragraph one.\n\n" + _FLOOR_FILLER,
        },
        {
            "number": 2,
            "title": "SEO After the AI Overviews",
            "content": "Paragraph two.\n\n" + _FLOOR_FILLER,
        },
    ],
}


def make_book(**overrides):
    book = dict(GOOD_BOOK)
    book["chapters"] = list(GOOD_BOOK["chapters"])
    book.update(overrides)
    return book


@pytest.fixture()
def artifacts(tmp_path, cover_png):
    """A built EPUB and cover, so the gate can be exercised as publish()"""
    epub = tmp_path / "built.epub"
    create_epub(GOOD_BOOK, str(epub))
    return {"epub_path": str(epub), "cover_path": cover_png}


@pytest.fixture()
def cover_png(tmp_path):
    from PIL import Image

    path = tmp_path / "cover.png"
    Image.new("RGB", (1600, 2560), (20, 40, 80)).save(path)
    return str(path)


class TestFrontMatter:
    def test_contains_title_page_and_copyright(self):
        keys = [entry["key"] for entry in front_matter(GOOD_BOOK)]
        assert keys[:2] == ["title_page", "copyright"]
        assert "contents" in keys

    def test_title_page_carries_title_author_and_publisher(self):
        page = front_matter(GOOD_BOOK)[0]
        assert "# Digital Marketing" in page["content"]
        assert "Priya Raman" in page["content"]
        assert "Raman Press" in page["content"]
        assert "A Practical Playbook" in page["content"]

    def test_copyright_page_is_not_in_the_toc(self):
        for entry in front_matter(GOOD_BOOK):
            if entry["key"] in ("title_page", "copyright", "contents"):
                assert entry["toc"] is False, entry["key"]

    def test_single_chapter_book_omits_the_contents_page(self):
        keys = [entry["key"] for entry in front_matter(GOOD_BOOK)]
        assert "contents" in keys
        short = make_book(chapters=[GOOD_BOOK["chapters"][0]])
        assert "contents" not in [e["key"] for e in front_matter(short)]

    def test_contents_lists_every_chapter(self):
        page = next(e for e in front_matter(GOOD_BOOK) if e["key"] == "contents")
        assert "Organic Reach Is Dead" in page["content"]
        assert "SEO After the AI Overviews" in page["content"]


class TestBackMatter:
    def test_always_includes_about_the_author(self):
        entries = back_matter(GOOD_BOOK)
        assert entries[0]["key"] == "about_author"
        assert "Priya Raman" in entries[0]["content"]
        assert entries[0]["toc"] is True

    def test_author_bio_is_used_when_supplied(self):
        page = back_matter(GOOD_BOOK)[0]
        assert "venture-backed startups" in page["content"]

    def test_generic_bio_falls_back_when_missing(self):
        book = make_book(author_bio="")
        page = back_matter(book)[0]
        assert "Priya Raman" in page["content"]

    @pytest.mark.parametrize(
        "genre",
        [
            "Finance",
            "Health",
            "Wellness",
            "Business",
            "Self-Help",
            "Technical",
            "Creative",
            "Lifestyle",
            "Cooking",
        ],
    )
    def test_every_book_carries_a_disclaimer(self, genre):
        """Every published book gets at least a general disclaimer; the
        sensitive genres get a specific one on top."""
        assert needs_disclaimer(genre, "Anything") is True

    @pytest.mark.parametrize(
        "genre,phrase",
        [
            ("Finance", "financial"),
            ("Health", "medical"),
            ("Wellness", "medical"),
            ("Business", "income"),
            ("Self-Help", "therapy"),
        ],
    )
    def test_sensitive_genres_get_a_specific_disclaimer(self, genre, phrase):
        assert phrase in disclaimer_for(genre, "Anything").lower()

    def test_other_genres_get_the_general_disclaimer(self):
        assert "no warranty" in disclaimer_for("Technical", "Anything")

    def test_disclaimer_text_is_specific_to_the_genre(self):
        assert "financial" in disclaimer_for("Finance", "Stock Trading")
        assert "medical" in disclaimer_for("Health", "Fitness")
        assert "income" in disclaimer_for("Business", "Digital Marketing")

    def test_niche_override_wins(self):
        assert needs_disclaimer("Technical", "Stock Trading") is True

    def test_indian_cooking_opts_out(self):
        assert needs_disclaimer("Cooking", "Indian Cooking") is False

    def test_about_author_is_in_toc_but_disclaimer_is_not(self):
        entries = back_matter(GOOD_BOOK)
        flags = {e["key"]: e["toc"] for e in entries}
        assert flags["about_author"] is True
        assert flags.get("disclaimer") in (False, None)


class TestQualityGate:
    def test_a_good_book_passes(self, artifacts):
        result = assess(GOOD_BOOK, channel="kdp", **artifacts)
        assert result.ok, result.errors
        assert result.metrics["words"] == count_words(GOOD_BOOK)
        assert result.metrics["words"] > KDP_MIN_WORDS

    def test_placeholder_author_blocks_publication(self):
        """Regression: every book defaulted to 'Demo Author'."""
        for placeholder in ("Demo Author", "Anonymous", "Your Name", ""):
            result = assess(make_book(author=placeholder), channel="kdp")
            assert not result.ok, placeholder
            assert any("placeholder" in e or "author is empty" in e for e in result.errors)

    def test_generic_chapter_titles_block_publication(self):
        book = make_book(
            chapters=[
                {"number": 1, "title": "Chapter 1", "content": "Text."},
                {"number": 2, "title": "Chapter 2", "content": "Text."},
            ]
        )
        result = assess(book, channel="kdp")
        assert not result.ok
        assert any("generic titles" in e for e in result.errors)

    def test_short_book_blocks_kdp_but_not_gumroad(self, artifacts):
        book = make_book(chapters=[{"number": 1, "title": "Real Title", "content": "Too short."}])
        kdp = assess(book, channel="kdp", **artifacts)
        gumroad = assess(book, channel="gumroad", **artifacts)
        floor = f"{KDP_MIN_WORDS:,}"
        # Same finding, different severity: fatal for KDP, advisory for Gumroad.
        assert any(floor in e for e in kdp.errors)
        assert not kdp.ok
        assert any(floor in w for w in gumroad.warnings)
        assert gumroad.ok, "Gumroad has no word-count floor"

    def test_mid_length_book_warns_but_passes(self, artifacts):
        """Between the KDP floor and the competitive length."""
        filler = " ".join(f"word{i}" for i in range(KDP_MIN_WORDS + 100))
        book = make_book(
            chapters=[
                {"number": 1, "title": "Real Title", "content": filler},
                {"number": 2, "title": "Second Title", "content": filler},
            ]
        )
        result = assess(book, channel="kdp", **artifacts)
        assert result.ok, result.errors
        target = f"{KDP_RECOMMENDED_WORDS:,}"
        assert any(target in w for w in result.warnings)

    def test_placeholder_text_blocks(self):
        book = make_book(
            chapters=[
                {"number": 1, "title": "Real Title", "content": "Lorem ipsum dolor."},
                {"number": 2, "title": "Second", "content": "Fine."},
            ]
        )
        result = assess(book, channel="kdp")
        assert any("placeholder text" in e for e in result.errors)

    @pytest.mark.parametrize(
        "content",
        [
            # Real corpus prose from Term Insurance chapter 3 — this word is
            # ordinary English and blocking it stopped a finished book.
            "The answer is somewhere between ten and fifteen times your "
            "annual income, and it is a reasonable placeholder but a poor plan.",
            "The term 'placeholder' appears in most style guides.",
            "Values between 1 and 3 are placeholders in the sense of defaults.",
        ],
    )
    def test_prose_containing_the_word_placeholder_is_not_blocked(self, content, artifacts):
        book = make_book(
            chapters=[
                {"number": 1, "title": "Real Title", "content": content},
                {"number": 2, "title": "Second", "content": "Fine."},
            ]
        )
        result = assess(book, channel="kdp", **artifacts)
        assert not any("placeholder text" in e for e in result.errors), result.errors

    @pytest.mark.parametrize(
        "content",
        [
            "TODO: write this chapter",
            "FIXME - needs review",
            "Coming soon, TBD",
            "Insert your introduction here",
            "[placeholder]",
            "<placeholder>",
            "placeholder text goes here",
            "chapter content here",
        ],
    )
    def test_actual_template_markers_still_block(self, content, artifacts):
        book = make_book(
            chapters=[
                {"number": 1, "title": "Real Title", "content": content},
                {"number": 2, "title": "Second", "content": "Fine."},
            ]
        )
        result = assess(book, channel="kdp", **artifacts)
        assert any("placeholder text" in e for e in result.errors), content

    def test_empty_chapter_blocks(self):
        book = make_book(
            chapters=[
                {"number": 1, "title": "Real Title", "content": ""},
                {"number": 2, "title": "Second", "content": "Fine."},
            ]
        )
        result = assess(book, channel="kdp")
        assert any("is empty" in e for e in result.errors)

    def test_short_description_warns(self):
        book = make_book(description="Too short.")
        result = assess(book, channel="kdp")
        assert any("description" in w for w in result.warnings)

    def test_missing_cover_blocks_kdp(self):
        result = assess(GOOD_BOOK, channel="kdp")
        assert any("cover" in e for e in result.errors)

    def test_tiny_cover_is_rejected(self, tmp_path):
        from PIL import Image

        path = tmp_path / "small.png"
        Image.new("RGB", (600, 900), (0, 0, 0)).save(path)
        result = assess(GOOD_BOOK, cover_path=str(path), channel="kdp")
        assert any("1000x1600" in e for e in result.errors)

    def test_non_standard_cover_warns(self, tmp_path, artifacts):
        from PIL import Image

        path = tmp_path / "odd.png"
        Image.new("RGB", (1200, 2000), (0, 0, 0)).save(path)
        result = assess(
            GOOD_BOOK, channel="kdp", epub_path=artifacts["epub_path"], cover_path=str(path)
        )
        assert result.ok, result.errors
        assert any("1600x2560" in w for w in result.warnings)

    def test_health_content_without_disclaimer_blocks(self, artifacts):
        """A health book must ship a disclaimer; back_matter() supplies it."""
        book = make_book(genre="Health")
        result = assess(book, channel="kdp", **artifacts)
        # back_matter() supplies the disclaimer, so this should pass
        assert result.ok, result.errors

    def test_unknown_channel_raises(self):
        with pytest.raises(ValueError, match="Unknown channel"):
            assess(GOOD_BOOK, channel="amazon")

    def test_broken_epub_blocks(self, tmp_path, cover_png):
        junk = tmp_path / "bad.epub"
        junk.write_bytes(b"not a zip")
        result = assess(GOOD_BOOK, epub_path=str(junk), cover_path=cover_png, channel="kdp")
        assert any("EPUB" in e for e in result.errors)

    def test_no_epub_at_all_blocks(self, cover_png):
        result = assess(GOOD_BOOK, cover_path=cover_png, channel="kdp")
        assert any("no EPUB" in e for e in result.errors)

    def test_assessment_reports_pass_and_block(self, artifacts):
        good = assess(GOOD_BOOK, channel="gumroad", **artifacts)
        text = "\n".join(good.lines())
        assert "PASS" in text
        bad = assess(make_book(author="Demo Author"), channel="gumroad", **artifacts)
        assert "BLOCKED" in "\n".join(bad.lines())


class TestStorePackages:
    def test_gumroad_bundle_holds_both_formats(self, tmp_path, cover_png):
        epub = tmp_path / "book.epub"
        pdf = tmp_path / "book.pdf"
        from ebook_engine.formatters.pdf_formatter import create_pdf

        create_epub(GOOD_BOOK, str(epub))
        create_pdf(GOOD_BOOK, str(pdf))
        bundle = create_gumroad_package(
            str(epub),
            output_path=str(tmp_path / "b.zip"),
            pdf_path=str(pdf),
            cover_path=cover_png,
            product={"title": "Digital Marketing", "price": 9.99},
            preview_chapter="## Organic Reach Is Dead\n\nPreview text.",
        )
        with zipfile.ZipFile(bundle) as zf:
            names = zf.namelist()
            product = zf.read("product.json").decode("utf-8")
        assert any(n.endswith(".epub") for n in names)
        assert any(n.endswith(".pdf") for n in names)
        assert any(n.endswith(".png") for n in names)
        assert "product.json" in names
        assert "README.txt" in names
        assert "preview.txt" in names
        assert '"price": 9.99' in product

    def test_gumroad_missing_epub_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            create_gumroad_package(str(tmp_path / "absent.epub"))

    def test_kdp_bundle_still_valid(self, tmp_path, cover_png):
        epub = tmp_path / "book.epub"
        create_epub(GOOD_BOOK, str(epub))
        bundle = create_kdp_package(
            str(epub),
            output_path=str(tmp_path / "k.zip"),
            cover_path=cover_png,
            metadata={"title": "Digital Marketing"},
        )
        assert validate_kdp_zip(bundle) == []

    def test_epub_with_matter_still_valid(self, tmp_path, cover_png):
        path = tmp_path / "book.epub"
        create_epub(make_book(cover_path=cover_png), str(path))
        assert validate_epub(path) == []


class TestCoverCarriesTheAuthor:
    def test_author_is_drawn_on_the_cover(self, tmp_path):
        from ebook_engine.cover_engine import generate_cover
        from PIL import Image

        out = tmp_path / "cover.png"
        generate_cover("Digital Marketing", "Business", str(out), author="Priya Raman")
        assert out.is_file()
        with Image.open(out) as img:
            assert img.size == (1600, 2560)

    def test_cover_without_author_still_builds(self, tmp_path):
        from ebook_engine.cover_engine import generate_cover

        out = tmp_path / "cover.png"
        generate_cover("Travel", "Lifestyle", str(out))
        assert out.is_file()


class TestStoreDescription:
    """The description is the product page. It must read as written."""

    def test_clears_the_gate_threshold(self, artifacts):
        """Regression: the default was 'Auto-generated Business book: ...',
        43 characters, which the gate flags as too short to list."""
        result = assess(GOOD_BOOK, channel="kdp", **artifacts)
        assert not any("description" in w for w in result.warnings)

    def test_is_long_enough_to_list(self):
        assert len(describe_book(GOOD_BOOK)) >= 100

    def test_uses_the_books_own_chapter_titles(self):
        text = describe_book(GOOD_BOOK)
        assert "Organic Reach Is Dead" in text
        assert "SEO After the AI Overviews" in text

    def test_contains_no_markdown(self):
        text = describe_book(
            make_book(
                chapters=[
                    {
                        "number": 1,
                        "title": "A **Bold** Chapter",
                        "content": "## A heading\n\n**Emphasis** and `code` here.",
                    },
                    {"number": 2, "title": "Plain", "content": "More text."},
                ]
            )
        )
        for marker in ("##", "**", "`"):
            assert marker not in text, marker

    def test_two_books_do_not_share_boilerplate(self):
        first = describe_book(GOOD_BOOK)
        second = describe_book(make_book(topic="Travel", chapters=[GOOD_BOOK["chapters"][0]]))
        assert first != second

    def test_handles_a_book_with_no_chapters(self):
        text = describe_book(make_book(chapters=[]))
        assert text.strip()
        assert "Digital Marketing" in text

    def test_handles_empty_chapter_content(self):
        text = describe_book(
            make_book(
                chapters=[
                    {"number": 1, "title": "Real Title", "content": ""},
                    {"number": 2, "title": "Also Real", "content": "   "},
                ]
            )
        )
        assert text.strip()
        assert len(text) >= 60

    def test_caps_the_opening_sentence(self):
        long = "word " * 500
        assert len(first_sentence(long)) <= 230

    def test_first_sentence_strips_headings_and_emphasis(self):
        assert first_sentence("# Title\n\nSome **bold** lead.") == "Some bold lead."

    def test_limited_to_the_requested_number_of_titles(self):
        chapters = [{"number": i, "title": f"Title {i}", "content": "Body."} for i in range(1, 10)]
        text = describe_book({"topic": "T", "genre": "G", "chapters": chapters})
        assert "Title 4" in text
        assert "Title 5" not in text

    def test_corpus_generate_book_returns_a_listable_description(self):
        """End to end: what the corpus hands to the catalog must list well."""
        from ebook_engine.corpus import generate_book

        book = generate_book("Digital Marketing", "business", 5)
        assert len(book["description"]) >= 100
        assert "Auto-generated" not in book["description"]
        assert "niche" not in book["description"].lower().split("inside")[0]


class TestCollapseEscapes:
    """Regression: escaping before markdown plus markdown escaping again
    inside verbatim spans stacked, so `?limit=20&offset=100` printed as
    `?limit=20&amp;offset=100` in the PDF and the EPUB."""

    def test_collapses_a_double_escaped_ampersand(self):
        assert collapse_escapes("a &amp;amp; b") == "a &amp; b"

    def test_leaves_a_single_escape_alone(self):
        assert collapse_escapes("a &amp; b") == "a &amp; b"

    def test_collapses_angle_bracket_entities(self):
        assert collapse_escapes("&amp;lt;tag&amp;gt;") == "&lt;tag&gt;"

    def test_collapses_repeatedly_to_one_level(self):
        assert collapse_escapes("&amp;amp;amp;x") == "&amp;x"

    def test_leaves_bare_ampersands_alone(self):
        """Only stacked entities are touched; a raw & is the caller's job."""
        assert collapse_escapes("a & b") == "a & b"

    def test_ignores_text_without_entities(self):
        assert collapse_escapes("plain prose") == "plain prose"
        assert collapse_escapes("") == ""

    def test_numeric_entities_collapse(self):
        assert collapse_escapes("&amp;#38;") == "&#38;"

    @pytest.mark.parametrize(
        "source",
        [
            # The exact paragraph that failed validation on web-development.
            "- **Offset Pagination:** (e.g., `?limit=20&offset=100`). "
            "Acceptable for small, stable, human-browsed lists.",
            "- **Cursor Pagination:** (e.g., `?limit=20&after=cursor_abc`).",
            "Inline `a & b` and <angle> brackets together.",
        ],
    )
    def test_formatters_never_emit_a_double_escape(self, source):
        from ebook_engine.formatters.epub_formatter import _to_html
        from ebook_engine.formatters.pdf_formatter import _blocks

        html = _to_html(source)
        assert "&amp;amp;" not in html, html
        for _tag, text in _blocks(source):
            assert "&amp;amp;" not in text, text

    def test_entities_render_correctly_in_a_built_pdf(self, tmp_path, cover_png):
        """End to end: the built PDF must not contain a literal &amp;."""
        from ebook_engine.formatters.pdf_formatter import create_pdf

        book = make_book(
            chapters=[
                {
                    "number": 1,
                    "title": "Pagination",
                    "content": "Use `?limit=20&offset=100` for offset "
                    "pagination, or `a & b` inline.",
                },
                {"number": 2, "title": "Second", "content": "Fine."},
            ]
        )
        out = tmp_path / "entities.pdf"
        create_pdf(book, str(out))
        assert validate_pdf(out) == []

    def test_entities_render_correctly_in_a_built_epub(self, tmp_path, cover_png):
        from ebook_engine.formatters.epub_formatter import create_epub

        book = make_book(
            chapters=[
                {
                    "number": 1,
                    "title": "Pagination",
                    "content": "Use `?limit=20&offset=100` for offset "
                    "pagination, or `a & b` inline.",
                },
                {"number": 2, "title": "Second", "content": "Fine."},
            ]
        )
        out = tmp_path / "entities.epub"
        create_epub(book, str(out))
        assert validate_epub(out) == []
        with zipfile.ZipFile(out) as zf:
            doc = zf.read("EPUB/chapter_01.xhtml").decode("utf-8")
        assert "&amp;amp;" not in doc, doc
        assert "&amp;offset=100" in doc


class TestAttributedClaims:
    """An LLM told not to invent statistics invents them anyway.

    Of 17 sourced/statistical sentences across one expanded library, 14 did
    not exist in the source corpus, so the gate counts and lists them for a
    human rather than trusting them silently.
    """

    CLAIM = (
        "A landmark 2018 meta-analysis in the British Journal of Sports "
        "Medicine, pooling 49 studies and 1,860 participants, found the ceiling."
    )
    PLAIN = "Habit formation depends on cue, routine and reward, as covered earlier."

    def _book(self, content):
        return {"chapters": [{"number": 1, "title": "T", "content": content}]}

    def test_a_sourced_statistic_is_flagged(self):
        claims = find_attributed_claims(self._book(self.CLAIM))
        assert len(claims) == 1
        assert "British Journal" in claims[0]

    def test_ordinary_prose_is_not_flagged(self):
        assert find_attributed_claims(self._book(self.PLAIN)) == []

    def test_a_bare_number_is_not_enough(self):
        """A year alone is not a claim needing a source."""
        assert (
            find_attributed_claims(
                self._book("The plan runs from January to December and repeats.")
            )
            == []
        )

    def test_a_bare_attribution_is_not_enough(self):
        """'Studies show' with no number carries nothing checkable."""
        assert (
            find_attributed_claims(
                self._book("Studies show that habits compound over long horizons for readers.")
            )
            == []
        )

    def test_short_fragments_are_skipped(self):
        """Sentence fragments under the length floor are noise."""
        assert find_attributed_claims(self._book("Study found 90%.")) == []

    def test_returns_claims_in_reading_order(self):
        content = (
            "First, a 2019 survey of 1,200 developers found that 62 percent "
            "ship weekly. Second, unrelated. Third, a 2021 study of 400 "
            "teams reported 30 percent fewer defects across the group."
        )
        claims = find_attributed_claims(self._book(content))
        assert len(claims) == 2
        assert claims[0].startswith("First")
        assert claims[1].startswith("Third")

    def test_the_gate_warns_and_counts_them(self, artifacts):
        book = make_book(
            chapters=[
                {"number": 1, "title": "T", "content": self.CLAIM},
                {"number": 2, "title": "U", "content": self.PLAIN},
            ]
        )
        result = assess(book, channel="kdp", **artifacts)
        assert result.metrics["claims"] == 1
        assert any("fact-check" in w for w in result.warnings)
        # Advisory only: an unverifiable claim must never block publication.
        assert not any("claim" in e for e in result.errors), result.errors

    def test_a_clean_book_reports_zero_claims(self, artifacts):
        book = make_book(
            chapters=[
                {"number": 1, "title": "T", "content": self.PLAIN},
                {"number": 2, "title": "U", "content": self.PLAIN},
            ]
        )
        result = assess(book, channel="kdp", **artifacts)
        assert result.metrics["claims"] == 0
        assert not any("fact-check" in w for w in result.warnings)


class TestRepeatedPassages:
    """A model told to hit a word count can pad by restating itself."""

    PARA = (
        "The espresso grinder matters more than most buyers expect, and the "
        "reason is mechanical rather than romantic: burr geometry decides how "
        "evenly coffee is crushed, and uneven crushing means some grounds "
        "over-extract while the rest under-extract, which tastes thin and "
        "bitter at the same time."
    )

    def _long(self, n=900):
        return " ".join(f"subject{i} differs{i * 7}" for i in range(n))

    def test_a_clean_book_reports_nothing(self, artifacts):
        book = make_book(
            chapters=[
                {"number": 1, "title": "One", "content": self._long(900)},
                {"number": 2, "title": "Two", "content": self._long(400) + " extra"},
            ]
        )
        assert find_repeated_passages(book) == []

    def test_a_repeated_paragraph_is_caught(self):
        body = "\n\n".join([self.PARA] * 4 + [self._long(900)])
        book = {"chapters": [{"number": i, "title": f"C{i}", "content": body} for i in range(1, 6)]}
        repeats = find_repeated_passages(book)
        assert repeats, "identical paragraphs must be detected"
        assert repeats[0]["similarity"] > 0.9
        assert "paragraph" in repeats[0]["where"]

    def test_identical_chapters_are_caught(self):
        body = self._long(900)
        book = {"chapters": [{"number": i, "title": f"C{i}", "content": body} for i in range(1, 6)]}
        repeats = find_repeated_passages(book)
        assert any("chapters" in r["where"] for r in repeats)

    def test_short_books_are_skipped(self):
        """Similarity on a handful of words is noise, not a finding."""
        book = {"chapters": [{"number": 1, "title": "T", "content": "a b c"}]}
        assert find_repeated_passages(book) == []

    def test_the_gate_warns_without_blocking(self, artifacts):
        body = "\n\n".join([self.PARA] * 4 + [self._long(1000)])
        book = make_book(
            chapters=[
                {"number": 1, "title": "One", "content": body},
                {"number": 2, "title": "Two", "content": self._long(900) + " tail"},
            ]
        )
        result = assess(book, channel="kdp", **artifacts)
        assert result.metrics["repeats"] > 0
        assert any("near-duplicate" in w for w in result.warnings)
        # Padded copy is a quality problem, not a reason to refuse to publish.
        assert not any("duplicate" in e for e in result.errors), result.errors
