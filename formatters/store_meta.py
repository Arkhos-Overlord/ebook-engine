"""Store metadata: the listing fields each sales channel asks for.

Amazon's KDP upload form and a Gumroad product page want different, and
much fuller, sets of fields than the four the engine used to emit. This
builds complete records for both.

Deliberate omission: BISAC codes. KDP requires them, but the catalogue
changes and a wrong code puts the book in the wrong store shelf, which is
worse than a blank field. The suggested category *names* are produced and
the selection is left to the publisher in KDP's own UI.
"""

import datetime
import re

# Human-readable shelf suggestions per genre. Names, not codes.
_CATEGORIES = {
    "business": [
        "Business & Money",
        "Entrepreneurship",
        "Marketing",
        "Small Business",
    ],
    "finance": ["Personal Finance", "Investing", "Business & Money"],
    "health": ["Health & Fitness", "Exercise & Fitness", "Nutrition"],
    "wellness": ["Health & Fitness", "Mindfulness & Meditation"],
    "self-help": ["Self-Help", "Personal Growth", "Motivational"],
    "cooking": ["Cooking", "Food & Wine", "Regional & International"],
    "lifestyle": ["Lifestyle", "Travel", "Personal Growth"],
    "creative": ["Arts & Photography", "Photography", "Crafts & Hobbies"],
    "technical": ["Computers & Technology", "Programming", "Web Development"],
}

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "your",
    "you",
    "are",
    "how",
    "why",
    "what",
    "when",
    "who",
    "which",
    "into",
    "about",
    "have",
    "more",
    "most",
    "been",
    "than",
    "then",
    "also",
    "just",
    "like",
    "well",
}

# KDP allows seven keyword slots; more get truncated anyway.
_MAX_KEYWORDS = 7


def categories_for(genre: str = "") -> list:
    """Suggested KDP category names for a genre. Select codes in KDP's UI."""
    return list(_CATEGORIES.get((genre or "").lower(), ["Business & Money"]))


def keywords_for(book_data: dict) -> list:
    """Derive listing keywords from the book's own subject matter.

    Built from the genre, the niche name and the chapter titles, so the
    words are ones the book is actually about. Deduplicated on a
    lowercased stem, capped at KDP's seven slots.
    """
    genre = str(book_data.get("genre") or "").lower()
    topic = str(book_data.get("topic") or "")

    words: list = []
    for phrase in [topic, *(c.get("title") or "" for c in book_data.get("chapters") or [])]:
        for token in re.findall(r"[A-Za-z][A-Za-z']{2,}", phrase or ""):
            lowered = token.lower()
            if lowered in _STOPWORDS:
                continue
            if not any(lowered.startswith(w[: max(3, len(w) - 2)]) for w in words):
                words.append(token)

    out = [genre.title()] if genre else []
    out += list(words)
    seen = set()
    unique = []
    for word in out:
        key = word.lower().rstrip("s")
        if key in seen:
            continue
        seen.add(key)
        unique.append(word)
        if len(unique) == _MAX_KEYWORDS:
            break
    return unique


def _today() -> str:
    return datetime.date.today().isoformat()


def build_kdp_metadata(book_data: dict, price: dict, publisher: str = "") -> dict:
    """The record Amazon's KDP upload form needs, as far as we can fill it."""
    description = str(book_data.get("description") or "").strip()
    record = {
        "title": book_data.get("topic"),
        "subtitle": book_data.get("subtitle") or "",
        "author": book_data.get("author"),
        "author_bio": book_data.get("author_bio") or "",
        "publisher": publisher or book_data.get("publisher") or "",
        "language": book_data.get("language") or "English",
        "description": description,
        "keywords": keywords_for(book_data),
        "categories": categories_for(book_data.get("genre") or ""),
        "isbn": book_data.get("isbn") or "",
        "publication_date": book_data.get("publication_date") or _today(),
        "price_ebook_usd": price.get("price_usd"),
        "price_ebook_inr": price.get("price_inr"),
        "royalty": "70%",
        "kindle_unlimited": bool(book_data.get("kindle_unlimited", False)),
        "rights": (
            f"Copyright (c) {_today()[:4]} {book_data.get('author') or 'the author'}. "
            "All rights reserved."
        ),
        "_notes": [
            "Select BISAC codes in KDP's own category picker; the 'categories' "
            "field holds suggested shelf names, not codes.",
            "Set 'author_bio' (EBOOK_AUTHOR_BIO) and 'publisher' "
            "(EBOOK_PUBLISHER) before upload — both are required on the form.",
        ],
    }
    return record


def build_gumroad_product(book_data: dict, price: dict, files: dict) -> dict:
    """A Gumroad product record: what the buyer page and the bundle need."""
    description = str(book_data.get("description") or "").strip()
    return {
        "title": book_data.get("topic"),
        "subtitle": book_data.get("subtitle") or "",
        "author": book_data.get("author"),
        "description": description,
        "tags": keywords_for(book_data)[:5],
        "price": price.get("price_usd"),
        "price_inr": price.get("price_inr"),
        "currency": "USD",
        "language": "English",
        "formats": [name for name, path in files.items() if path],
        "chapters": len(book_data.get("chapters") or []),
    }
