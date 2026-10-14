"""Front and back matter shared by the EPUB and PDF formatters.

A book that opens cold on Chapter 1 reads as a draft. KDP expects at
minimum a title page, a copyright page and a visible table of contents;
books in the finance, health and income niches also need a disclaimer.

Both formatters consume the same markdown here, so a book never ends up
with front matter in one format and none in the other.

Each entry is a dict shaped like a chapter:
    key       stable identifier (used for the XHTML file name)
    title     heading shown in the reader
    content   markdown body
    toc       whether it belongs in the table of contents
    file      stem for the generated file name
"""

import datetime
import re

# Genres whose claims need an explicit "this is not professional advice"
# paragraph. Amazon is strict about health and financial content.
_DISCLAIMERS = {
    "finance": (
        "**Important:** Nothing in this book is financial, investment, tax or "
        "legal advice. Markets carry the risk of loss, including the loss of "
        "principal. Past performance is not indicative of future results, and "
        "no outcome described here is guaranteed. Speak to a licensed "
        "professional before making any financial decision."
    ),
    "health": (
        "**Important:** This book is for general information only and is not "
        "medical, nutritional or psychological advice. Do not change your "
        "diet, medication or training routine on the basis of this book "
        "without consulting a qualified professional, particularly if you are "
        "pregnant, managing a condition, or taking medication."
    ),
    "wellness": (
        "**Important:** This book is for general information only and is not "
        "medical or mental-health advice. If you are experiencing distress, "
        "injury or symptoms of any condition, consult a qualified "
        "professional before acting on anything you read here."
    ),
    "business": (
        "**Important:** Results vary. Nothing here is a promise of income, "
        "and no earnings figure in this book is typical or guaranteed. Any "
        "examples are illustrative. Your results will depend on your own "
        "effort, market and circumstances."
    ),
    "self-help": (
        "**Important:** This book is not therapy, counselling or medical "
        "treatment. No outcome is guaranteed, and if you are struggling with "
        "your mental health please speak to a qualified professional."
    ),
}

# Niche names that need a disclaimer even when their genre label does not
# obviously call for one.
_NICHE_OVERRIDE = {
    "Stock Trading": "finance",
    "Cryptocurrency": "finance",
    "Term Insurance": "finance",
    "Real Estate Investing": "finance",
    "Fitness & Nutrition": "health",
    "Meditation & Mindfulness": "wellness",
    "Indian Cooking": "",  # food safety is handled in-text
}

_GENERAL = (
    "**Disclaimer:** This book is provided for general information and "
    "education only. Every effort has been made to ensure accuracy, but "
    "no warranty is given, and the author accepts no liability for loss "
    "arising from reliance on it. Examples are illustrative; your results "
    "may differ."
)


def disclaimer_for(genre: str = "", topic: str = "") -> str:
    """Return the disclaimer for this book, or '' for an opted-out niche.

    The niche override is consulted first and its value is used even when it
    is empty — `"" or genre` would silently discard an explicit opt-out and
    hand a sensitive-content disclaimer to a harmless cookbook.
    """
    if topic in _NICHE_OVERRIDE:
        override = _NICHE_OVERRIDE[topic]
        return _DISCLAIMERS.get(override, "") if override else ""
    key = (genre or "").lower()
    if not key:
        return _GENERAL
    return _DISCLAIMERS.get(key, _GENERAL)


def needs_disclaimer(genre: str = "", topic: str = "") -> bool:
    return bool(disclaimer_for(genre, topic))


def _year() -> int:
    return datetime.date.today().year


def front_matter(book_data: dict) -> list:
    """Title page, copyright page and a visible contents page."""
    title = str(book_data.get("topic") or "Untitled")
    subtitle = str(book_data.get("subtitle") or "").strip()
    author = str(book_data.get("author") or "Anonymous")
    publisher = str(book_data.get("publisher") or "").strip()
    isbn = str(book_data.get("isbn") or "").strip()
    edition = str(book_data.get("edition") or "").strip() or "First edition"
    chapters = book_data.get("chapters") or []

    title_page = ["# " + title, ""]
    if subtitle:
        title_page += ["### " + subtitle, ""]
    title_page += ["", "**" + author + "**", ""]
    if publisher:
        title_page += [publisher, ""]

    copyright_lines = [
        f"Copyright © {(_year())} {author}. All rights reserved.",
        "",
        "No part of this publication may be reproduced, stored in or "
        "introduced into a retrieval system, or transmitted in any form or "
        "by any means — electronic, mechanical, photocopying, recording or "
        "otherwise — without prior written permission from the publisher.",
        "",
        f"{edition}.",
    ]
    if publisher:
        copyright_lines.append(f"Published by {publisher}.")
    copyright_lines += [
        f"ISBN: {isbn or 'assigned on publication'}",
        "",
        "The author has made every reasonable effort to ensure the accuracy "
        "of the information in this book. It is offered without warranty of "
        "any kind; the reader remains responsible for their own decisions.",
    ]

    out = [
        {
            "key": "title_page",
            "file": "title_page",
            "title": title,
            "content": "\n".join(title_page),
            "toc": False,
        },
        {
            "key": "copyright",
            "file": "copyright",
            "title": "Copyright",
            "content": "\n".join(copyright_lines),
            "toc": False,
        },
    ]

    if len(chapters) > 1:
        listing = ["# Contents", ""]
        for i, ch in enumerate(chapters, 1):
            listing.append(f"{i}. {ch.get('title') or f'Chapter {i}'}")
        out.append(
            {
                "key": "contents",
                "file": "contents",
                "title": "Contents",
                "content": "\n".join(listing),
                "toc": False,
            }
        )
    return out


def back_matter(book_data: dict) -> list:
    """About-the-author page and, where the niche needs one, a disclaimer."""
    out = []
    author = str(book_data.get("author") or "Anonymous")
    bio = str(book_data.get("author_bio") or "").strip()

    if not bio:
        bio = (
            f"{author} writes practical, research-backed non-fiction for "
            "readers who want the useful part without the padding."
        )
    out.append(
        {
            "key": "about_author",
            "file": "about_author",
            "title": f"About {author}",
            "content": f"# About {author}\n\n{bio}",
            "toc": True,
        }
    )

    text = disclaimer_for(str(book_data.get("genre") or ""), str(book_data.get("topic") or ""))
    if text:
        out.append(
            {
                "key": "disclaimer",
                "file": "disclaimer",
                "title": "Disclaimer",
                "content": f"# Disclaimer\n\n{text}",
                "toc": False,
            }
        )
    return out


def strip_markdown_heading(text: str) -> str:
    """First `# heading` in a markdown document, without its markup."""
    match = re.search(r"(?m)^#{1,6}\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


_SQUASH = re.compile(r"\s+")
# Emphasis markers safe to strip wholesale. Single underscores are left
# alone so identifiers like core_web_vitals survive intact.
_BOLDISH = re.compile(r"\*\*|__|~~|`+")
_HEADING_LINE = re.compile(r"(?m)^#{1,6}.*$")


def _clean(text: str) -> str:
    """Reduce markdown-ish source to plain, single-spaced prose."""
    cleaned = _HEADING_LINE.sub("", text or "")
    cleaned = _BOLDISH.sub("", cleaned)
    return _SQUASH.sub(" ", cleaned).strip()


# `&amp;` followed by a reference that itself looks like an entity. This is
# what markdown produces when it escapes a source we already escaped.
_DOUBLE_ENTITY = re.compile(r"&amp;(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);", re.I)


def collapse_escapes(text: str) -> str:
    """Collapse stacked entities back to a single level.

    Source is escaped before markdown runs so that a bare `<` in prose
    cannot reach the XML. Markdown then escapes *again* inside spans it
    treats verbatim — an inline code span turns `&` into `&amp;`, turning
    our `&amp;` into `&amp;amp;`. The renderer emits that literally, so a
    URL like `?limit=20&offset=100` printed as `?limit=20&amp;offset=100`.

    Decoding until stable and re-collapsing once leaves every entity at
    exactly one level, which is what a renderer expects.
    """
    if not text or "&amp;" not in text:
        return text
    while True:
        collapsed = _DOUBLE_ENTITY.sub(r"&\1;", text)
        if collapsed == text:
            return text
        text = collapsed


def first_sentence(text: str, limit: int = 220) -> str:
    """The opening sentence of a chapter, stripped to plain text.

    Store listings take text, not markdown. Whole heading lines are
    dropped — removing only the `#` marker would leave the heading's own
    words merged into the first sentence — and emphasis is stripped, so
    the blurb never shows `**` to a reader.
    """
    cleaned = _clean(text)
    if not cleaned:
        return ""
    end = re.search(r"[.!?](\s|$)", cleaned)
    sentence = cleaned[: end.end()].strip() if end else cleaned
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
    return sentence


def describe_book(book_data: dict, max_titles: int = 4) -> str:
    """Compose a store-ready description from the book's own content.

    The previous default was `Auto-generated {genre} book: {topic}` — 43
    characters of placeholder text that reads as unfinished on a product
    page. This builds a blurb out of what the book actually contains: its
    opening line and its chapter titles, so no two books share boilerplate
    and the listing cannot drift from the contents.
    """
    topic = str(book_data.get("topic") or "").strip()
    genre = str(book_data.get("genre") or "").strip()
    chapters = book_data.get("chapters") or []

    parts = []
    hook = first_sentence(str(chapters[0].get("content") or "")) if chapters else ""
    if hook:
        parts.append(hook)
    elif topic:
        parts.append(f"{topic}: a practical {genre.lower() or 'non-fiction'} guide.")

    titles = [_clean(str(c.get("title") or "")) for c in chapters]
    titles = [t for t in titles if t][:max_titles]
    if titles:
        if len(titles) == 1:
            listing = titles[0]
        else:
            listing = ", ".join(titles[:-1]) + " and " + titles[-1]
        parts.append(f"Inside: {listing}.")

    if genre and topic:
        parts.append(f"A {genre.lower()} book for readers who want the working part.")

    text = _SQUASH.sub(" ", " ".join(parts)).strip()
    if len(text) < 120:
        text = _SQUASH.sub(
            " ",
            f"{topic or 'This book'} covers the ground step by step, with "
            f"research, numbers and worked examples. {text}",
        ).strip()
    return text
