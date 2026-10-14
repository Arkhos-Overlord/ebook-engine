"""Content generation engine — corpus-backed or LLM-backed ebook content."""

from abc import ABC, abstractmethod

from ebook_engine.config import (
    AUTHOR_NAME,
    LLM_BACKEND,
    OLLAMA_MODEL,
    OLLAMA_URL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

try:
    from ebook_engine.corpus import generate_book as _corpus_generate

    CORPUS_AVAILABLE = True
except (ImportError, OSError) as _corpus_error:  # corpus absent or unreadable
    CORPUS_AVAILABLE = False
    _corpus_generate = None
    _corpus_import_error = _corpus_error
else:
    _corpus_import_error = None

# The research corpus holds exactly 5 chapters per niche. Asking for more
# than the corpus has is an error rather than a silent truncation.
DEFAULT_CHAPTERS = 5


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Return the model's completion for the given prompt."""


class OllamaProvider(LLMProvider):
    """Local Ollama provider — zero API cost."""

    def generate(self, prompt: str, **kwargs) -> str:
        import requests

        model = kwargs.get("model", OLLAMA_MODEL)
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 4000},
                },
                timeout=kwargs.get("timeout", 120),
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 400):
                # Ollama answers 404 for an unknown model name, which reads
                # like a broken endpoint. Say what is actually wrong.
                raise RuntimeError(
                    f"Ollama has no model named {model!r} (HTTP {status}). "
                    f"Installed: {_installed_models()}. "
                    "Set OLLAMA_MODEL in .env to one of them."
                ) from e
            raise
        return response.json()["response"]


class OpenAIProvider(LLMProvider):
    """OpenAI provider — used when Ollama is unavailable."""

    def generate(self, prompt: str, **kwargs) -> str:
        from openai import OpenAI

        if not OPENAI_API_KEY:
            raise RuntimeError(
                "LLM_BACKEND=openai but OPENAI_API_KEY is not set. "
                "Export it, or set LLM_BACKEND=ollama."
            )
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=kwargs.get("model", OPENAI_MODEL),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000,
        )
        return response.choices[0].message.content or ""


def get_provider() -> LLMProvider:
    """Get the configured LLM provider."""
    if LLM_BACKEND == "ollama":
        return OllamaProvider()
    return OpenAIProvider()


def _installed_models() -> str:
    """Model names the local Ollama reports, for a useful error message."""
    try:
        import requests as _requests

        listing = _requests.get(OLLAMA_URL.rsplit("/", 1)[0] + "/tags", timeout=5)
        listing.raise_for_status()
        names = [m.get("name", "") for m in listing.json().get("models", [])]
        return ", ".join(n for n in names if n) or "none"
    except Exception:
        return "unknown (could not query /api/tags)"


def generate_outline(topic: str, genre: str, num_chapters: int = DEFAULT_CHAPTERS) -> str:
    """Generate a book outline with chapter summaries."""
    provider = get_provider()
    prompt = f"""Create a detailed outline for a {genre} book titled "{topic}".

Generate exactly {num_chapters} chapters. For each chapter, provide:
- Chapter number and title
- A 2-3 sentence summary of what happens/covers
- Key points or subtopics

Format as markdown with ## Chapter N: Title headers.

Topic: {topic}
Genre: {genre}
Chapters: {num_chapters}

Return ONLY the outline, no intro or outro text."""
    return provider.generate(prompt)


def generate_chapter(topic: str, genre: str, chapter_num: int, chapter_title: str) -> str:
    """Generate a single chapter's content."""
    provider = get_provider()
    prompt = f"""Write chapter {chapter_num} of a {genre} book titled "{topic}".

Chapter Title: {chapter_title}

Write approximately 2000-3000 words. The chapter should:
- Open with a compelling hook or introduction
- Cover the main points thoroughly with examples
- Close with a transition to the next chapter
- Use clear, engaging prose
- Match the tone of a {genre} book

Return only the chapter body as markdown. Do not repeat the chapter title
as a heading — the caller renders it separately."""
    return provider.generate(prompt)


def generate_book(
    topic: str, genre: str, num_chapters: int = DEFAULT_CHAPTERS, mode: str = "corpus"
) -> dict:
    """Generate a complete book.

    Args:
        topic: Book title / niche name.
        genre: Genre, used to resolve a niche when the topic is not one.
        num_chapters: How many chapters to produce.
        mode: "corpus" (default) reads the bundled research corpus and needs
            no network; "llm" calls the configured provider.

    Returns dict with 'outline', 'chapters', 'topic', 'genre', and for
    corpus mode also 'niche', 'author' and 'description'.
    """
    if mode == "llm":
        return _generate_with_llm(topic, genre, num_chapters)
    if mode != "corpus":
        raise ValueError(f"Unknown mode {mode!r}; expected 'corpus' or 'llm'")
    if not CORPUS_AVAILABLE or _corpus_generate is None:
        raise RuntimeError(
            "Corpus mode requested but the research corpus could not be "
            f"imported: {_corpus_import_error}"
        )
    return _corpus_generate(topic, genre, num_chapters)


def _generate_with_llm(topic: str, genre: str, num_chapters: int) -> dict:
    """Assemble a book from the configured LLM provider."""
    outline = generate_outline(topic, genre, num_chapters)
    titles = _chapter_titles(outline, num_chapters)
    chapters = []
    for i, title in enumerate(titles, 1):
        body = generate_chapter(topic, genre, i, title)
        chapters.append({"number": i, "title": title, "content": body})
    return {
        "outline": outline,
        "chapters": chapters,
        "topic": topic,
        "genre": genre,
        "author": AUTHOR_NAME,
        "description": f"A {genre} book: {topic}",
    }


def _chapter_titles(outline: str, num_chapters: int) -> list:
    """Pull chapter headings out of a generated outline, filling gaps.

    Level 1 headings are skipped: an outline opens with its own title
    (`# Outline`), and matching it promoted the document heading to
    chapter 1 and shifted every real chapter down by one.
    """
    import re

    titles = []
    for match in re.finditer(r"(?m)^#{2,4}\s*(?:Chapter\s*\d+[:.\-]?\s*)?(.+?)\s*$", outline):
        titles.append(match.group(1).strip())
    while len(titles) < num_chapters:
        titles.append(f"Chapter {len(titles) + 1}")
    return titles[:num_chapters]


def plan_expansion(chapters: list, target_words: int) -> list:
    """Indices of chapters that fall short of their share of the target.

    The gate wants 15,000 words across a book; each chapter is measured
    against its equal share so short chapters get the work and a single
    long one is left alone.
    """
    if not chapters or target_words <= 0:
        return []
    share = max(1, target_words // len(chapters))
    return [i for i, chapter in enumerate(chapters) if _words(chapter) < share]


def _words(chapter: dict) -> int:
    from ebook_engine.formatters.quality import count_words

    return count_words({"chapters": [chapter]})


def expand_chapter(book: dict, chapter: dict, target_words: int) -> str:
    """Ask the configured provider to lengthen one chapter.

    The instruction to preserve every existing claim while not inventing
    statistics is the important part: a model left free to add detail will
    happily fabricate a study, and a fabricated citation is a far worse
    publishing problem than a short chapter.
    """
    provider = get_provider()
    current = _words(chapter)
    length_note = f"roughly {target_words} words (currently {current})"
    prompt = f"""Expand this chapter of a non-fiction book to {length_note}.

Book: "{book.get("topic")}" ({book.get("genre")})
Chapter: "{chapter.get("title")}"

Rules:
- keep every claim, number, example and argument already in the text,
  unchanged and with the same magnitude
- do NOT invent statistics, studies, surveys, quotes or sources. If a
  figure is not in the text above, do not write one.
- do NOT name a new study, survey, journal, author, institution, year or
  research paper. Never cite work that is not quoted in the text above.
- do NOT use attribution phrases unless that exact attribution already
  appears above: "according to", "studies show", "researchers found",
  "a study published in", "peer-reviewed", journal names.
- add depth by reasoning from the material you were given, by expanding
  examples already present, and by drawing out implications — not by
  adding new evidence
- keep the existing voice and structure; add ## subheadings only where
  the subject supports them
- do not repeat the chapter title as a heading; the caller renders it
- return only the chapter body as markdown

Current chapter:
---
{chapter.get("content")}
---"""
    return provider.generate(prompt)


def scrub_chapter(book: dict, chapter: dict, reference: str = "") -> str:
    """Remove citations that are not backed by the reference material.

    `expand_chapter` cannot do this job: it is told to keep every existing
    claim, so a fabricated citation survives expansion. This is the inverse
    operation ? the reference text is the authoritative source (the corpus
    chapter this book was expanded from), and anything attributed to a
    study, journal, author, institution or year that is absent from it has
    to go.

    Returns markdown; the result is normally shorter than the input, which
    is the point.
    """
    provider = get_provider()
    source = reference or str(chapter.get("content") or "")
    prompt = f"""Remove unsourced claims from this chapter of a non-fiction book.

Book: "{book.get("topic")}" ({book.get("genre")})
Chapter: "{chapter.get("title")}"

Reference material ? the only source that may be cited:
---
{source}
---

Rules:
- Find every sentence that attributes a finding to a named source: a
  study, survey, journal, author, institution, research paper or year.
- If that exact attribution does NOT appear in the reference material
  above, either DELETE the sentence or RESTATE its point as plain
  reasoning with no source attached.
- Do not swap in a different citation, and do not invent a figure to
  fill the gap left behind.
- Keep every other sentence, argument, number and example exactly as it
  is, in the same order.
- Keep the existing voice, structure and ## subheadings.
- Do not repeat the chapter title as a heading.
- Return only the chapter body as markdown. It will be shorter than the
  input, and that is intended.

Chapter to clean:
---
{chapter.get("content")}
---"""
    return provider.generate(prompt)
