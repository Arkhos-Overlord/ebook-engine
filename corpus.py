"""Corpus-backed content generation from the bundled research data."""

import json

from ebook_engine.config import AUTHOR_NAME, BASE_DIR
from ebook_engine.formatters.matter import describe_book

_CORPUS_PATH = BASE_DIR / "data" / "content_data.json"


def _load() -> dict:
    """Load the research corpus from the JSON data file."""
    if not _CORPUS_PATH.is_file():
        raise FileNotFoundError(
            f"Research corpus not found: {_CORPUS_PATH}. "
            "It ships as data/content_data.json and must not be missing."
        )
    with open(_CORPUS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


NICHE_CONTENT = _load()
RESEARCH_AVAILABLE = True

_AUTHOR = AUTHOR_NAME


def get_all_niches() -> list:
    """Return the list of all available niche names."""
    return list(NICHE_CONTENT.keys())


def get_niche_genre(niche: str) -> str:
    """Return the genre for a niche, or 'General' when unknown."""
    return NICHE_CONTENT.get(niche, {}).get("genre", "General")


def get_niche_cover_color(niche: str) -> list:
    """Return the corpus cover colour (RGB) for a niche."""
    return NICHE_CONTENT.get(niche, {}).get("cover_color", [0x1A, 0x1A, 0x2E])


def _resolve_niche(topic: str, genre: str) -> str:
    """Resolve a topic to a corpus niche, or raise.

    Returning a different niche's content under the caller's title was the
    old behaviour: `generate "Python for Beginners" technical` produced a
    Web Development book titled "Python for Beginners". Silently wrong
    content is worse than an error.
    """
    if topic in NICHE_CONTENT:
        return topic

    matches = [
        name
        for name, data in NICHE_CONTENT.items()
        if str(data.get("genre", "")).lower() == str(genre).lower()
    ]
    if len(matches) == 1:
        available = ", ".join(sorted(NICHE_CONTENT))
        raise ValueError(
            f"Topic {topic!r} is not a corpus niche (closest genre {genre!r} "
            f"would give {matches[0]!r}, which is not the requested book). "
            f"Pick a corpus niche: {available}. "
            "Or generate an arbitrary topic with mode='llm'."
        )

    available = ", ".join(sorted(NICHE_CONTENT))
    raise ValueError(
        f"Unknown topic {topic!r} and genre {genre!r} matches {len(matches)} "
        f"niches. Pick a corpus niche: {available}. "
        "Or generate an arbitrary topic with mode='llm'."
    )


def _build_outline(topic: str, data: dict, chapters: list) -> str:
    lines = [
        f"# {topic}",
        "",
        f"**Genre:** {data['genre']}",
        f"**Total Chapters:** {len(chapters)}",
        f"**Author:** {_AUTHOR}",
        "",
        "---",
        "",
        "# Table of Contents",
        "",
    ]
    for i, ch in enumerate(chapters, 1):
        lines.append(f"## Chapter {i}: {ch['title']}")
        lines.append("")
        lines.append(f"*{ch['content'][0][:100]}...*")
        lines.append("")
    return "\n".join(lines)


def generate_book(topic: str, genre: str, num_chapters: int = 5) -> dict:
    """Generate a complete book from the research corpus.

    Raises ValueError when the topic is not a corpus niche or when more
    chapters are requested than the niche contains.
    """
    niche = _resolve_niche(topic, genre)
    data = NICHE_CONTENT[niche]
    available = data["chapters"]

    if num_chapters < 1:
        raise ValueError(f"num_chapters must be >= 1, got {num_chapters}")
    if num_chapters > len(available):
        raise ValueError(
            f"{niche!r} has {len(available)} chapters; {num_chapters} requested. "
            f"Ask for {len(available)} or fewer."
        )

    chapters_data = available[:num_chapters]

    chapters = [
        {
            "number": i,
            "title": ch["title"],
            "content": (
                ch["content"] if isinstance(ch["content"], str) else "\n\n".join(ch["content"])
            ),
        }
        for i, ch in enumerate(chapters_data, start=1)
    ]

    return {
        "outline": _build_outline(topic, data, chapters_data),
        "chapters": chapters,
        "topic": topic,
        "genre": data["genre"],
        "niche": niche,
        "author": _AUTHOR,
        "description": describe_book(
            {"topic": topic, "genre": data["genre"], "chapters": chapters}
        ),
    }
