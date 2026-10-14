"""Store listing metadata for KDP and Gumroad."""

from ebook_engine.formatters.store_meta import (
    build_gumroad_product,
    build_kdp_metadata,
    categories_for,
    keywords_for,
)

PRICE = {"price_usd": 9.99, "price_inr": 799}


def make_book(**overrides):
    book = {
        "topic": "Cryptocurrency",
        "genre": "Finance",
        "author": "NEYAN",
        "description": "A practical guide to digital assets. " * 8,
        "chapters": [
            {"title": "What Bitcoin Halvings Actually Do"},
            {"title": "Scarcity, Supply and Demand"},
            {"title": "Custody and Security Basics"},
        ],
    }
    book.update(overrides)
    return book


class TestKeywords:
    def test_derived_from_the_books_own_subject(self):
        words = keywords_for(make_book())
        lowered = [w.lower() for w in words]
        assert "bitcoin" in lowered
        assert "scarcity" in lowered
        assert "finance" in lowered

    def test_capped_at_kdps_seven_slots(self):
        book = make_book(chapters=[{"title": f"Distinct Topic Number {i}"} for i in range(20)])
        assert len(keywords_for(book)) <= 7

    def test_no_case_duplicates(self):
        """The genre led the list, so 'finance' and 'Finance' could both
        appear; the dedup is on a lowercased stem."""
        words = [w.lower() for w in keywords_for(make_book())]
        assert len(words) == len(set(words))

    def test_stopwords_are_dropped(self):
        words = [w.lower() for w in keywords_for(make_book())]
        assert "the" not in words
        assert "with" not in words

    def test_stem_variants_are_collapsed(self):
        book = make_book(
            topic="Investing",
            chapters=[{"title": "Investment and Investor Basics"}],
        )
        words = [w.lower() for w in keywords_for(book)]
        assert words.count("investing") <= 1
        assert words.count("investment") <= 1

    def test_a_book_with_no_chapters_still_yields_keywords(self):
        words = keywords_for(make_book(topic="Travel", genre="Lifestyle", chapters=[]))
        assert words
        assert "travel" in [w.lower() for w in words]

    def test_is_deterministic(self):
        assert keywords_for(make_book()) == keywords_for(make_book())


class TestCategories:
    def test_known_genre_returns_shelves(self):
        assert "Personal Finance" in categories_for("Finance")

    def test_case_insensitive(self):
        assert categories_for("finance") == categories_for("FINANCE")

    def test_unknown_genre_falls_back_rather_than_empty(self):
        assert categories_for("Underwater Basket Weaving")

    def test_are_names_not_codes(self):
        """BISAC codes are chosen in KDP's own picker; a wrong code would
        file the book on the wrong shelf."""
        for name in categories_for("Finance"):
            assert not name.split()[0].isdigit()
            assert len(name) > 3


class TestKdpMetadata:
    def test_carries_every_field_the_upload_form_asks_for(self):
        record = build_kdp_metadata(make_book(), PRICE, publisher="Raman Press")
        for field in (
            "title",
            "subtitle",
            "author",
            "author_bio",
            "publisher",
            "language",
            "description",
            "keywords",
            "categories",
            "isbn",
            "publication_date",
            "price_ebook_usd",
            "royalty",
            "rights",
        ):
            assert field in record, field

    def test_publisher_argument_wins(self):
        record = build_kdp_metadata(make_book(), PRICE, publisher="Vale Press")
        assert record["publisher"] == "Vale Press"

    def test_publisher_falls_back_to_the_book(self):
        record = build_kdp_metadata(make_book(publisher="From Book"), PRICE, publisher="")
        assert record["publisher"] == "From Book"

    def test_rights_names_the_author_and_year(self):
        record = build_kdp_metadata(make_book(), PRICE)
        assert "NEYAN" in record["rights"]
        assert str(__import__("datetime").date.today().year) in record["rights"]

    def test_explains_the_bisac_omission(self):
        record = build_kdp_metadata(make_book(), PRICE)
        notes = " ".join(record["_notes"])
        assert "BISAC" in notes

    def test_prices_come_from_the_tier(self):
        record = build_kdp_metadata(make_book(), PRICE)
        assert record["price_ebook_usd"] == 9.99
        assert record["price_ebook_inr"] == 799

    def test_keywords_are_present_and_derived(self):
        record = build_kdp_metadata(make_book(), PRICE)
        assert record["keywords"]
        assert "bitcoin" in [w.lower() for w in record["keywords"]]


class TestGumroadProduct:
    def test_carries_the_listing_fields(self):
        product = build_gumroad_product(
            make_book(), PRICE, files={"epub": True, "pdf": True, "cover": False}
        )
        for field in ("title", "author", "description", "tags", "price", "currency", "formats"):
            assert field in product, field

    def test_formats_reflect_what_exists(self):
        product = build_gumroad_product(
            make_book(), PRICE, files={"epub": True, "pdf": False, "cover": True}
        )
        assert "epub" in product["formats"]
        assert "pdf" not in product["formats"]

    def test_tags_have_no_case_duplicates(self):
        product = build_gumroad_product(make_book(), PRICE, files={"epub": True})
        tags = [t.lower() for t in product["tags"]]
        assert len(tags) == len(set(tags))

    def test_counts_chapters(self):
        product = build_gumroad_product(make_book(), PRICE, files={"epub": True})
        assert product["chapters"] == 3
