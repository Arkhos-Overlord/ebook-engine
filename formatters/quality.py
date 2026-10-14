"""Publication quality gate for KDP and Gumroad.

Audits a book before it is uploaded, so a thin draft or an unfilled
placeholder never reaches a store. Every finding is either an `error`
(block publication) or a `warning` (publishable, but flag it), and the
metrics are reported alongside so a pass is explainable rather than a
bare ok.

Amazon rejects reflowable ebooks under roughly 2,500 words outright and
is strict about health and financial claims; Gumroad imposes no floor,
so the channel only changes which checks are fatal.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from ebook_engine.config import (
    KDP_MIN_CHAPTERS,
    KDP_MIN_WORDS,
    KDP_RECOMMENDED_WORDS,
    PLACEHOLDER_AUTHORS,
)
from ebook_engine.formatters.matter import needs_disclaimer

# Phrases that mean nobody filled the template in.
#
# Deliberately NOT a bare `placeholder`: that word is ordinary prose. The
# Term Insurance chapter says "it is a reasonable placeholder but a poor
# plan", and matching it blocked a finished book for using English. Only
# template-shaped forms are matched.
#
# Two alternatives, because \b cannot follow a bracket — `]` is a non-word
# character, so `\b(...)\b` never matches `[placeholder]`.
_PLACEHOLDER_TEXT = re.compile(
    r"(?ix)"
    r"\b(?:lorem\s+ipsum|todo|fixme|tbd"
    r"|insert\s+.{0,40}?\s+here"
    r"|chapter\s+content\s+here"
    r"|your\s+text\s+here"
    r"|placeholder\s+(?:text|content|copy|here|string))\b"
    r"|\[\s*placeholder\s*\]"
    r"|<\s*placeholder\s*>"
    r"|\(\s*placeholder\s*\)"
)
_SQUASH = re.compile(r"\s+")
_GENERIC_TITLE = re.compile(r"^chapter\s+\d+$", re.IGNORECASE)
_MARKUP = re.compile(r"[*_`#>|]+")

CHANNELS = ("kdp", "gumroad")


@dataclass
class Assessment:
    """Outcome of one quality audit."""

    channel: str
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def lines(self) -> list:
        out = [f"{self.channel.upper()} assessment: {'PASS' if self.ok else 'BLOCKED'}"]
        for message in self.errors:
            out.append(f"  ERROR   {message}")
        for message in self.warnings:
            out.append(f"  warning {message}")
        for key, value in self.metrics.items():
            out.append(f"  {key:18s} {value}")
        return out


def count_words(book_data: dict) -> int:
    """Words of body copy, ignoring markdown punctuation."""
    total = 0
    for chapter in book_data.get("chapters") or []:
        text = _MARKUP.sub(" ", str(chapter.get("content") or ""))
        text = re.sub(r"\s+", " ", text)
        total += len(text.split())
    return total


# Sentences that hang a claim on a source or a hard number. An LLM told not
# to invent statistics will invent them anyway — of 17 such sentences in one
# expanded library, 14 did not exist in the source corpus — so they are
# surfaced for a human rather than silently trusted.
_ATTRIBUTION = re.compile(
    r"(?i)\b("
    r"according to|study|studies|research(?:ers)?|survey|reported that|"
    r"found that|analysed|analyzed|meta-analysis|published in|journal of|"
    r"landmark|pooled|estimated|gartner|nielsen|forrester|pew"
    r")\b"
)
_HARD_NUMBER = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:percent|%|x)\b"
    r"|\b\d{1,3}(?:,\d{3})+\b"
    r"|\b(?:19|20)\d{2}\b"
)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]")
_MIN_CLAIM = 40


def find_attributed_claims(book_data: dict) -> list:
    """Sentences stating a sourced finding or a hard number.

    Returned verbatim and in reading order so `quality --claims` can print
    them for review against the sources they name.
    """
    claims = []
    for chapter in book_data.get("chapters") or []:
        body = str(chapter.get("content") or "")
        for sentence in _SENTENCE.findall(body):
            cleaned = _SQUASH.sub(" ", sentence).strip()
            if len(cleaned) < _MIN_CLAIM:
                continue
            if _ATTRIBUTION.search(cleaned) and _HARD_NUMBER.search(cleaned):
                claims.append(cleaned)
    return claims


def assess(
    book_data: dict,
    epub_path=None,
    pdf_path=None,
    cover_path=None,
    channel: str = "kdp",
) -> Assessment:
    """Audit one book for publication.

    Args:
        book_data: the dict handed to the formatters.
        epub_path: built EPUB, validated if given.
        pdf_path: built PDF, validated if given.
        cover_path: cover image, checked for KDP's size rules.
        channel: "kdp" or "gumroad".
    """
    if channel not in CHANNELS:
        raise ValueError(f"Unknown channel {channel!r}; expected one of {CHANNELS}")

    result = Assessment(channel=channel)
    chapters = book_data.get("chapters") or []
    words = count_words(book_data)
    result.metrics["chapters"] = len(chapters)
    result.metrics["words"] = words
    result.metrics["words/chapter"] = round(words / len(chapters)) if chapters else 0

    _check_identity(book_data, result)
    _check_length(words, len(chapters), result, fatal_floor=(channel == "kdp"))
    _check_copy(book_data, result)
    claims = find_attributed_claims(book_data)
    result.metrics["claims"] = len(claims)
    if claims:
        # Not an error: the gate cannot tell a real study from an invented
        # one, but a fabricated citation is a serious publishing problem, so
        # they are counted and listed by `main.py quality --claims` for a
        # human to check.
        result.warn(
            f"{len(claims)} attributed claim(s) need fact-checking — see "
            "'quality <id> --claims' for the sentences"
        )
    _check_disclaimer(book_data, result, fatal=(channel == "kdp"))
    _check_cover(cover_path, result, fatal=(channel == "kdp"))
    _check_artifacts(epub_path, pdf_path, result, fatal_epub=True)
    repeats = find_repeated_passages(book_data)
    result.metrics["repeats"] = len(repeats)
    if repeats:
        # A model told to reach a word count can pad by restating itself.
        # Near-duplicate passages are the clearest tell of thin, padded
        # copy, and no other gate looks for them.
        result.warn(
            f"{len(repeats)} near-duplicate passage pair(s) detected; "
            "repeated copy reads as padding — see 'quality <id> --claims' "
            "or re-run expand on the affected chapters"
        )
    return result


def _shingles(text: str, size: int = 8) -> set:
    """Word n-gram fingerprints, used to spot restated passages.

    Digits are kept: a paragraph that differs only in its numbers is not a
    repetition, and dropping digits would make every numbered sentence
    collapse onto the same tokens.
    """
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Below this, a book is too short for similarity to mean anything.
_REPEAT_MIN_WORDS = 3000
_REPEAT_MIN_PARAGRAPH = 40


def find_repeated_passages(book_data: dict) -> list:
    """Paragraph and chapter pairs that are near-duplicates of each other.

    Returns [{"similarity": 0.0-1.0, "where": "chapter 2"}]. Two
    thresholds: paragraphs that restate each other, and whole chapters
    that cover the same ground twice.
    """
    chapters = book_data.get("chapters") or []
    if count_words(book_data) < _REPEAT_MIN_WORDS:
        return []

    found = []
    for chapter in chapters:
        number = chapter.get("number", "?")
        paragraphs = [
            p
            for p in str(chapter.get("content") or "").split("\n\n")
            if len(p.split()) > _REPEAT_MIN_PARAGRAPH
        ]
        prints = [_shingles(p) for p in paragraphs]
        for i in range(len(paragraphs)):
            for j in range(i + 1, len(paragraphs)):
                similarity = _jaccard(prints[i], prints[j])
                if similarity > 0.5:
                    found.append(
                        {
                            "similarity": round(similarity, 2),
                            "where": f"chapter {number}, paragraphs {i + 1} and {j + 1}",
                        }
                    )

    chapter_prints = [_shingles(c.get("content") or "") for c in chapters]
    for i in range(len(chapters)):
        for j in range(i + 1, len(chapters)):
            similarity = _jaccard(chapter_prints[i], chapter_prints[j])
            if similarity > 0.35:
                found.append(
                    {
                        "similarity": round(similarity, 2),
                        "where": f"chapters {chapters[i].get('number', '?')} "
                        f"and {chapters[j].get('number', '?')}",
                    }
                )
    found.sort(key=lambda item: item["similarity"], reverse=True)
    return found


def _check_identity(book_data: dict, result: Assessment) -> None:
    title = str(book_data.get("topic") or "").strip()
    author = str(book_data.get("author") or "").strip()
    description = str(book_data.get("description") or "").strip()

    if not title:
        result.error("title is empty")
    if not author:
        result.error("author is empty")
    elif author.lower() in PLACEHOLDER_AUTHORS:
        # Unfilled author names must never reach a store listing.
        result.error(f"author is a placeholder ({author!r}) — pass --author")
    if not str(book_data.get("language") or "").strip() and not book_data.get("lang"):
        result.warn("no language set (the formatters default to English)")
    if len(description) < 80:
        result.warn(
            f"description is only {len(description)} characters; store listings "
            "read best at 100-400"
        )
    if not book_data.get("publisher"):
        result.warn(
            "no publisher set (EBOOK_PUBLISHER in .env); it is omitted "
            "from the copyright page and the listing until you do"
        )


def _check_length(words: int, chapters: int, result: Assessment, fatal_floor: bool) -> None:
    if words < KDP_MIN_WORDS and fatal_floor:
        result.error(
            f"{words:,} words is below the {KDP_MIN_WORDS:,} floor — Amazon "
            "will reject this as a reflowable ebook"
        )
    elif words < KDP_MIN_WORDS:
        result.warn(f"{words:,} words is below {KDP_MIN_WORDS:,}")
    elif words < KDP_RECOMMENDED_WORDS:
        result.warn(
            f"{words:,} words clears the floor but is short of the "
            f"{KDP_RECOMMENDED_WORDS:,} that a competitive book in this "
            "niche usually runs to"
        )

    if chapters < KDP_MIN_CHAPTERS:
        result.warn(f"only {chapters} chapters; {KDP_MIN_CHAPTERS} is the usual minimum")


def _check_copy(book_data: dict, result: Assessment) -> None:
    titles = []
    for i, chapter in enumerate(book_data.get("chapters") or [], 1):
        title = str(chapter.get("title") or "").strip()
        titles.append(title.lower())
        if not title:
            result.error(f"chapter {i} has no title")
        elif _GENERIC_TITLE.match(title):
            result.error(
                f"chapter {i} is titled {title!r} — generic titles read as unpublished drafts"
            )

        body = str(chapter.get("content") or "")
        if not body.strip():
            result.error(f"chapter {i} ({title or 'untitled'}) is empty")
        hit = _PLACEHOLDER_TEXT.search(body)
        if hit:
            result.error(f"chapter {i} contains placeholder text: {hit.group(0)!r}")

    duplicates = {t for t in titles if t and titles.count(t) > 1}
    for duplicate in sorted(duplicates):
        result.warn(f"duplicate chapter title {duplicate!r}")


def _check_disclaimer(book_data: dict, result: Assessment, fatal: bool) -> None:
    """Amazon is strict about health and financial claims.

    Checked against the assembled book — chapters *plus* the back matter the
    formatters append — not the chapters alone, otherwise a book that ships
    a correct disclaimer page would still be reported as missing one.
    """
    genre = str(book_data.get("genre") or "")
    topic = str(book_data.get("topic") or "")
    if not needs_disclaimer(genre, topic):
        return

    from ebook_engine.formatters.matter import back_matter

    sections = [str(ch.get("content") or "") for ch in book_data.get("chapters") or []]
    sections += [entry["content"] for entry in back_matter(book_data)]
    assembled = "\n".join(sections)

    present = any(
        phrase in assembled
        for phrase in (
            "not financial",
            "not medical",
            "not therapy",
            "Results vary",
            "no warranty",
            "Disclaimer",
        )
    )
    if not present:
        message = f"{genre or topic or 'this'} content needs an explicit advice/earnings disclaimer"
        result.error(message) if fatal else result.warn(message)


def _check_cover(cover_path, result: Assessment, fatal: bool) -> None:
    if not cover_path:
        message = "no cover image"
        result.error(message) if fatal else result.warn(message)
        return
    path = Path(str(cover_path))
    if not path.is_file():
        result.error(f"cover file missing: {path.name}")
        return
    try:
        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size
    except Exception as e:  # unreadable or PIL unavailable
        result.warn(f"could not read the cover: {e}")
        return

    result.metrics["cover"] = f"{width}x{height}"
    if width < 1000 or height < 1600:
        result.error(
            f"cover is {width}x{height}; Amazon wants at least 1000x1600 (ideally 1600x2560)"
        )
    elif (width, height) != (1600, 2560):
        result.warn(f"cover is {width}x{height}; 1600x2560 is the recommended ebook cover size")
    ratio = width / height
    if not 0.62 <= ratio <= 0.64:
        result.warn(f"cover ratio {ratio:.3f} is outside the 0.62-0.64 band Amazon recommends")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        result.error(f"cover is {size_mb:.1f} MB; the limit is 50 MB")


def _check_artifacts(epub_path, pdf_path, result: Assessment, fatal_epub: bool) -> None:
    if epub_path:
        from ebook_engine.validators import validate_epub

        problems = validate_epub(epub_path)
        if problems:
            for problem in problems[:8]:
                result.error(f"EPUB: {problem}")
        else:
            result.metrics["epub"] = "valid"
    elif fatal_epub:
        result.error("no EPUB was built")

    if pdf_path:
        from ebook_engine.validators import validate_pdf

        problems = validate_pdf(pdf_path)
        if problems:
            for problem in problems[:5]:
                result.warn(f"PDF: {problem}")
        else:
            result.metrics["pdf"] = "valid"
