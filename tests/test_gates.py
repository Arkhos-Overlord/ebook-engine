"""Gate tests: the mechanical checks that define "done" for this project.

G1 static analysis, G4 corpus integrity. The other gates live next to the
code they cover: G3 in test_formatters, G5/G6 in test_cli and test_corpus.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

# Captured in P0 before any file was touched. The corpus must survive
# every migration byte-for-byte.
GOLDEN_CORPUS_SHA256 = "09f5b32a514cbbc309c3ff9ee11b48c0d7fbd1d05a2c2025e0f4f25214ffc4f0"
GOLDEN_NICHES = 15
GOLDEN_CHAPTERS = 75
GOLDEN_PARAGRAPHS = 300
GOLDEN_WORDS = 63719


def _canonical(data: dict) -> str:
    return json.dumps(
        {
            name: {
                "genre": niche["genre"],
                "cover_color": niche["cover_color"],
                "chapters": [
                    {"title": c["title"], "content": c["content"]} for c in niche["chapters"]
                ],
            }
            for name, niche in sorted(data.items())
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _load_corpus() -> dict:
    path = PROJECT / "data" / "content_data.json"
    assert path.is_file(), f"corpus missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


class TestCorpusIntegrity:
    """Gate G4."""

    def test_sha256_matches_the_baseline(self):
        data = _load_corpus()
        digest = hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()
        assert digest == GOLDEN_CORPUS_SHA256, (
            "the corpus changed; if this was intentional, re-baseline "
            f"GOLDEN_CORPUS_SHA256 and the counts below\nwas {digest}"
        )

    def test_shape_matches_the_baseline(self):
        data = _load_corpus()
        assert len(data) == GOLDEN_NICHES
        chapters = sum(len(n["chapters"]) for n in data.values())
        paragraphs = sum(len(c["content"]) for n in data.values() for c in n["chapters"])
        words = sum(
            len(p.split()) for n in data.values() for c in n["chapters"] for p in c["content"]
        )
        assert (chapters, paragraphs, words) == (
            GOLDEN_CHAPTERS,
            GOLDEN_PARAGRAPHS,
            GOLDEN_WORDS,
        )

    def test_file_is_clean_utf8(self):
        raw = (PROJECT / "data" / "content_data.json").read_bytes()
        text = raw.decode("utf-8")  # raises if not valid UTF-8
        assert "\ufffd" not in text, "corpus contains replacement characters"

    def test_every_niche_has_a_genre_and_colour(self):
        for name, niche in _load_corpus().items():
            assert niche["genre"], name
            assert len(niche["cover_color"]) == 3, name
            assert all(0 <= c <= 255 for c in niche["cover_color"]), name

    def test_no_content_data_py_remains(self):
        """The 687 KB .py blob must stay deleted."""
        assert not (PROJECT / "content_data.py").exists()


class TestStaticAnalysis:
    """Gate G1 — `ruff check` must be clean, same as the commit gate."""

    @pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
    def test_ruff_check_is_clean(self):
        result = subprocess.run(
            ["ruff", "check", "."],
            cwd=str(PROJECT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        assert result.returncode == 0, (
            f"ruff check reported problems:\n{result.stdout}{result.stderr}"
        )

    @pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
    def test_ruff_format_is_clean(self):
        """Enforced since P9; formatting must not drift afterwards."""
        result = subprocess.run(
            ["ruff", "format", "--check", "."],
            cwd=str(PROJECT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.returncode == 0:
            return
        pytest.fail(f"ruff format reports unformatted files:\n{result.stdout}{result.stderr}")


class TestProjectLayout:
    """The structural promises the rest of the suite depends on."""

    @pytest.mark.parametrize(
        "path",
        [
            "config.py",
            "catalog.py",
            "main.py",
            "conftest.py",
            "pyproject.toml",
            "requirements.txt",
            "templates/epub.css",
            "templates/reader/index.html",
            "templates/reader/chapter.html",
            "templates/reader/reader.css",
            "data/content_data.json",
            "formatters/__init__.py",
            "formatters/matter.py",
            "formatters/quality.py",
            "formatters/gumroad_zip.py",
            "validators.py",
        ],
    )
    def test_expected_file_exists(self, path):
        assert (PROJECT / path).exists(), f"missing {path}"

    @pytest.mark.parametrize(
        "path",
        [
            "rewrite_ic.py",
            "rewrite_pd.py",
            "gen_all_narrative.py",
            "content_data_test.py",
        ],
    )
    def test_deleted_files_stay_deleted(self, path):
        assert not (PROJECT / path).exists(), f"{path} should not come back"

    def test_package_imports_from_a_neutral_directory(self, tmp_path):
        """Regression: `import ebook_engine.catalog` used to raise
        ImportError because a stray config/ directory shadowed config.py."""
        code = (
            "import ebook_engine, ebook_engine.catalog, ebook_engine.config, "
            "ebook_engine.server, ebook_engine.epub_reader, "
            "ebook_engine.formatters.epub_formatter; print('ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(tmp_path),  # deliberately not the project
            env={**__import__("os").environ, "PYTHONPATH": str(PROJECT.parent)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout
