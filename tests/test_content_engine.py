"""LLM content path: outline parsing, chapter assembly, provider selection.

Every test here stubs the provider, so nothing reaches the network and no
API credit is spent — the point is to prove the wiring is correct.
"""

import ebook_engine.content_engine as ce
import pytest


class StubProvider:
    """Returns a canned outline; records the prompts it was given."""

    def __init__(self, outline_text):
        self.outline = outline_text
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.outline


CANNED_OUTLINE = """# Outline

## Chapter 1: Finding the Signal
## Chapter 2: Sizing the Position
## Chapter 3: Reading the Tape
"""


@pytest.fixture()
def stub_provider(monkeypatch):
    provider = StubProvider(CANNED_OUTLINE)
    monkeypatch.setattr(ce, "get_provider", lambda: provider)
    return provider


class TestChapterTitles:
    def test_extracts_headings_from_the_outline(self):
        titles = ce._chapter_titles(CANNED_OUTLINE, 3)
        assert titles == [
            "Finding the Signal",
            "Sizing the Position",
            "Reading the Tape",
        ]

    def test_strips_the_chapter_number_prefix(self):
        outline = "## Chapter 4: Risk Management\n## Chapter 5: Journaling"
        assert ce._chapter_titles(outline, 2) == ["Risk Management", "Journaling"]

    def test_pads_when_the_outline_is_short(self):
        """A model that returns two headings must not produce a 5-chapter book
        with two empty slots."""
        outline = "## Only One Heading\n## And Another"
        titles = ce._chapter_titles(outline, 5)
        assert len(titles) == 5
        assert titles[0] == "Only One Heading"
        assert titles[-1] == "Chapter 5"

    def test_trims_when_the_outline_is_long(self):
        outline = "\n".join(f"## Chapter {i}: Title {i}" for i in range(1, 20))
        assert len(ce._chapter_titles(outline, 4)) == 4

    def test_empty_outline_still_yields_the_requested_count(self):
        titles = ce._chapter_titles("", 3)
        assert len(titles) == 3
        assert all(t.startswith("Chapter ") for t in titles)


class TestLlmGeneration:
    def test_builds_one_chapter_per_outline_heading(self, stub_provider):
        result = ce.generate_book("Trading", "Finance", 3, mode="llm")
        assert result["topic"] == "Trading"
        assert len(result["chapters"]) == 3
        assert [c["number"] for c in result["chapters"]] == [1, 2, 3]
        assert [c["title"] for c in result["chapters"]] == [
            "Finding the Signal",
            "Sizing the Position",
            "Reading the Tape",
        ]
        for chapter in result["chapters"]:
            assert chapter["content"].strip()

    def test_requested_chapter_count_is_respected(self, stub_provider):
        result = ce.generate_book("Trading", "Finance", 5, mode="llm")
        assert len(result["chapters"]) == 5

    def test_outline_is_returned_alongside_the_chapters(self, stub_provider):
        result = ce.generate_book("Trading", "Finance", 3, mode="llm")
        assert result["outline"] == CANNED_OUTLINE
        assert result["genre"] == "Finance"

    def test_calls_the_provider_once_for_the_outline_then_per_chapter(self, stub_provider):
        ce.generate_book("Trading", "Finance", 3, mode="llm")
        assert len(stub_provider.prompts) == 4  # 1 outline + 3 chapters
        assert any("outline" in p.lower() for p in stub_provider.prompts[:1])
        # every prompt names the book and genre
        assert all("Trading" in p for p in stub_provider.prompts)

    def test_chapter_prompt_names_the_chapter_title(self, stub_provider):
        ce.generate_book("Trading", "Finance", 1, mode="llm")
        assert "Finding the Signal" in stub_provider.prompts[-1]

    def test_uses_the_corpus_mode_by_default(self, monkeypatch):
        """mode='corpus' must not touch the provider at all."""
        called = []

        def explode():
            called.append(1)
            raise AssertionError("provider should not be called in corpus mode")

        monkeypatch.setattr(ce, "get_provider", explode)
        result = ce.generate_book("Digital Marketing", "business", 5)
        assert not called
        assert result["niche"] == "Digital Marketing"

    def test_unknown_mode_is_rejected_before_any_provider_call(self, monkeypatch):
        monkeypatch.setattr(ce, "get_provider", lambda: pytest.fail("no call"))
        with pytest.raises(ValueError, match="Unknown mode"):
            ce.generate_book("Trading", "Finance", 3, mode="chatgpt")

    def test_author_comes_from_config_not_a_placeholder(self, stub_provider):
        from ebook_engine.config import AUTHOR_NAME

        result = ce.generate_book("Trading", "Finance", 3, mode="llm")
        assert result["author"] == AUTHOR_NAME
        assert result["author"].lower() not in ("llm author", "demo author")


class TestProviderSelection:
    def test_ollama_backend_returns_ollama_provider(self, monkeypatch):
        monkeypatch.setattr(ce, "LLM_BACKEND", "ollama")
        assert isinstance(ce.get_provider(), ce.OllamaProvider)

    def test_openai_backend_returns_openai_provider(self, monkeypatch):
        monkeypatch.setattr(ce, "LLM_BACKEND", "openai")
        assert isinstance(ce.get_provider(), ce.OpenAIProvider)

    def test_openai_without_a_key_fails_clearly(self, monkeypatch):
        monkeypatch.setattr(ce, "OPENAI_API_KEY", "")
        provider = ce.OpenAIProvider()
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            provider.generate("hello")

    def test_ollama_url_comes_from_config(self, monkeypatch):
        from ebook_engine.config import OLLAMA_URL

        assert ce.OLLAMA_URL == OLLAMA_URL
        assert OLLAMA_URL.startswith("http")


class TestPromptQuality:
    def test_outline_prompt_asks_for_the_requested_count(self, monkeypatch):
        provider = StubProvider("")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        ce.generate_outline("Topic", "Genre", 7)
        assert "exactly 7 chapters" in provider.prompts[0]

    def test_chapter_prompt_does_not_ask_for_a_duplicate_title_header(self, monkeypatch):
        """Regression: the prompt used to say 'No title header needed —
        include it in format', which asked for two contradictory things."""
        provider = StubProvider("")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        ce.generate_chapter("Topic", "Genre", 1, "A Title")
        prompt = provider.prompts[0]
        assert "Do not repeat the chapter title" in prompt
        assert "include it in format" not in prompt

    def test_outline_prompt_rejects_intro_and_outro(self, monkeypatch):
        provider = StubProvider("")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        ce.generate_outline("T", "G", 3)
        assert "Return ONLY the outline" in provider.prompts[0]


def _chapters(count, words_each):
    body = " ".join(f"word{i}" for i in range(words_each))
    return [{"number": i, "title": f"Chapter {i}", "content": body} for i in range(1, count + 1)]


class TestPlanExpansion:
    def test_selects_every_short_chapter(self):
        assert ce.plan_expansion(_chapters(5, 850), 15000) == [0, 1, 2, 3, 4]

    def test_leaves_chapters_that_already_meet_their_share(self):
        assert ce.plan_expansion(_chapters(5, 3500), 15000) == []

    def test_only_short_chapters_are_selected(self):
        # share = 12000 / 4 = 3000; chapters 2-4 are under it, chapter 1 is not
        chapters = _chapters(4, 2000)
        chapters[0]["content"] = " ".join("w" for _ in range(5000))
        assert ce.plan_expansion(chapters, 12000) == [1, 2, 3]

    def test_nothing_to_do_for_an_empty_book(self):
        assert ce.plan_expansion([], 15000) == []

    def test_nothing_to_do_when_the_target_is_zero(self):
        assert ce.plan_expansion(_chapters(5, 10), 0) == []

    def test_share_is_the_target_divided_evenly(self):
        # 10,000 across 4 -> share 2,500; 2,600 words is enough
        assert ce.plan_expansion(_chapters(4, 2600), 10000) == []
        assert ce.plan_expansion(_chapters(4, 2400), 10000) == [0, 1, 2, 3]


class TestExpandChapter:
    def test_prompt_carries_the_target_and_the_current_length(self, monkeypatch):
        provider = StubProvider("Expanded body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        book = {"topic": "Digital Marketing", "genre": "Business"}
        chapter = {"number": 1, "title": "Organic Reach", "content": "Original words."}
        ce.expand_chapter(book, chapter, 3000)
        prompt = provider.prompts[0]
        assert "roughly 3000 words" in prompt
        assert "currently" in prompt
        assert "Digital Marketing" in prompt
        assert "Organic Reach" in prompt
        assert "Original words." in prompt

    def test_prompt_forbids_inventing_statistics(self, monkeypatch):
        """A fabricated citation is a worse publishing problem than a short
        chapter, so the instruction has to be explicit."""
        provider = StubProvider("Body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        ce.expand_chapter({"topic": "T", "genre": "Finance"}, _chapters(1, 10)[0], 3000)
        prompt = provider.prompts[0]
        assert "do NOT invent statistics" in prompt
        assert "keep every claim, number" in prompt

    @pytest.mark.parametrize(
        "phrase",
        [
            # Hardened after an expansion pass invented 5 of 6 checked
            # claims: a named study, a wrong year, a conflated statistic.
            "do NOT name a new study",
            "journal, author, institution, year",
            "according to",
            "attribution phrases",
            "reasoning from the material you were given",
        ],
    )
    def test_hardened_prompt_blocks_the_specific_failure_modes(self, monkeypatch, phrase):
        provider = StubProvider("Body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        ce.expand_chapter({"topic": "T", "genre": "Health"}, _chapters(1, 10)[0], 3000)
        assert phrase in provider.prompts[0], phrase

    def test_prompt_keeps_the_original_text_in_scope(self, monkeypatch):
        """The chapter body must be passed through so claims can be kept."""
        provider = StubProvider("Body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        chapter = {"number": 1, "title": "T", "content": "The original wording."}
        ce.expand_chapter({"topic": "T", "genre": "G"}, chapter, 3000)
        assert "The original wording." in provider.prompts[0]

    def test_prompt_does_not_ask_for_a_repeated_title_heading(self, monkeypatch):
        provider = StubProvider("Body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        ce.expand_chapter({"topic": "T", "genre": "G"}, _chapters(1, 10)[0], 3000)
        assert "do not repeat the chapter title" in provider.prompts[0].lower()

    def test_returns_what_the_provider_gave(self, monkeypatch):
        provider = StubProvider("## A subheading\n\nMuch longer body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        out = ce.expand_chapter({"topic": "T", "genre": "G"}, _chapters(1, 10)[0], 3000)
        assert out == "## A subheading\n\nMuch longer body."

    def test_provider_failure_propagates(self, monkeypatch):
        class Broken:
            def generate(self, prompt, **kwargs):
                raise ConnectionError("backend down")

        monkeypatch.setattr(ce, "get_provider", lambda: Broken())
        with pytest.raises(ConnectionError, match="backend down"):
            ce.expand_chapter({"topic": "T", "genre": "G"}, _chapters(1, 10)[0], 3000)


class TestScrubChapter:
    """Expansion is told to keep every claim, so it structurally cannot
    remove a citation the corpus already contained. scrub_chapter is the
    inverse operation: the corpus chapter is the only citable source."""

    def _scrub(self, monkeypatch, chapter, reference=""):
        provider = StubProvider("Cleaned body.")
        monkeypatch.setattr(ce, "get_provider", lambda: provider)
        out = ce.scrub_chapter({"topic": "T", "genre": "G"}, chapter, reference=reference)
        return out, provider.prompts[0]

    def test_reference_material_is_supplied(self, monkeypatch):
        chapter = {"number": 1, "title": "T", "content": "Chapter text here."}
        _, prompt = self._scrub(monkeypatch, chapter, reference="Authoritative text.")
        assert "Authoritative text." in prompt

    def test_falls_back_to_the_chapter_itself(self, monkeypatch):
        chapter = {"number": 1, "title": "T", "content": "Only source available."}
        _, prompt = self._scrub(monkeypatch, chapter)
        assert "Only source available." in prompt

    def test_prompt_forbids_replacement_citations(self, monkeypatch):
        chapter = {"number": 1, "title": "T", "content": "Body."}
        _, prompt = self._scrub(monkeypatch, chapter, reference="Ref.")
        assert "Do not swap in a different citation" in prompt
        assert "do not invent a figure" in prompt

    def test_prompt_asks_for_deletion_or_plain_restatement(self, monkeypatch):
        chapter = {"number": 1, "title": "T", "content": "Body."}
        _, prompt = self._scrub(monkeypatch, chapter, reference="Ref.")
        assert "DELETE the sentence or RESTATE" in prompt
        assert "no source attached" in prompt

    def test_prompt_tells_the_model_a_shorter_result_is_intended(self, monkeypatch):
        """Otherwise the model pads back to the original length."""
        chapter = {"number": 1, "title": "T", "content": "Body."}
        _, prompt = self._scrub(monkeypatch, chapter, reference="Ref.")
        flat = " ".join(prompt.split())
        assert "shorter than the input" in flat
        assert "that is intended" in flat

    def test_chapter_body_is_included(self, monkeypatch):
        chapter = {"number": 1, "title": "T", "content": "The text to clean."}
        _, prompt = self._scrub(monkeypatch, chapter, reference="Ref.")
        assert "The text to clean." in prompt

    def test_returns_what_the_provider_gave(self, monkeypatch):
        chapter = {"number": 1, "title": "T", "content": "Body."}
        out, _ = self._scrub(monkeypatch, chapter, reference="Ref.")
        assert out == "Cleaned body."

    def test_provider_failure_propagates(self, monkeypatch):
        class Broken:
            def generate(self, prompt, **kwargs):
                raise ConnectionError("backend down")

        monkeypatch.setattr(ce, "get_provider", lambda: Broken())
        with pytest.raises(ConnectionError):
            ce.scrub_chapter({"topic": "T", "genre": "G"}, {"content": "x"}, reference="r")
