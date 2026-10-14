"""End-to-end CLI smoke tests (gate G5) and their negatives (gate G6).

Each run is a real subprocess pointed at a throwaway output/state
directory via the EBOOK_* environment overrides, so the project's own
catalog and books are never touched.
"""

import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
MAIN = PROJECT / "main.py"


@pytest.fixture()
def cli_env(tmp_path):
    """Environment that redirects the CLI's output and catalog."""
    env = dict(os.environ)
    env["EBOOK_OUTPUT_DIR"] = str(tmp_path / "output")
    env["EBOOK_STATE_DIR"] = str(tmp_path / "state")
    env["PYTHONIOENCODING"] = "utf-8"
    return env, tmp_path


def run(args, env, timeout=180, expect=None, cwd=None):
    result = subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd or PROJECT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if expect is not None:
        assert result.returncode == expect, (
            f"{' '.join(args)} -> exit {result.returncode} "
            f"(expected {expect})\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestHelpAndReadOnlyCommands:
    @pytest.mark.parametrize("args", [["--help"], ["list"], ["stats"], ["catalog-export"]])
    def test_exit_zero(self, cli_env, args):
        env, tmp = cli_env
        run([str(MAIN), *args], env, expect=0)

    def test_module_form_works_too(self, cli_env):
        """`python -m ebook_engine.main` needs the parent on sys.path, so
        it is invoked from the workspace root as a package would be."""
        env, _ = cli_env
        run(["-m", "ebook_engine.main", "--help"], env, expect=0, cwd=PROJECT.parent)

    def test_catalog_export_writes_json(self, cli_env):
        env, tmp = cli_env
        run([str(MAIN), "catalog-export", "--format", "json"], env, expect=0)
        exported = tmp / "output" / "catalog.json"
        assert exported.is_file()
        assert exported.read_text(encoding="utf-8").startswith("[")

    def test_read_refuses_when_library_is_empty(self, cli_env):
        env, _ = cli_env
        result = run([str(MAIN), "read"], env, expect=1)
        assert "No published books" in result.stdout


class TestGenerate:
    def test_generates_chapters_and_catalog_row(self, cli_env):
        env, tmp = cli_env
        run(
            [str(MAIN), "generate", "Digital Marketing", "business", "--chapters", "5"],
            env,
            expect=0,
        )
        book_dir = tmp / "output" / "digital-marketing"
        assert (book_dir / "outline.md").is_file()
        chapters = sorted(book_dir.glob("chapter_*.md"))
        assert len(chapters) == 5
        # The heading must be written so publish can recover the real title
        assert chapters[0].read_text(encoding="utf-8").startswith("## ")
        assert (tmp / "state" / "catalog.db").is_file()

    def test_utf8_content_survives_the_round_trip(self, cli_env):
        env, tmp = cli_env
        run(
            [str(MAIN), "generate", "Digital Marketing", "business"],
            env,
            expect=0,
        )
        text = (tmp / "output" / "digital-marketing" / "chapter_01.md").read_text(encoding="utf-8")
        assert text.strip()
        assert "\ufffd" not in text  # no replacement characters

    @pytest.mark.parametrize(
        "topic,genre,extra,phrase",
        [
            ("Python for Beginners", "technical", [], "not a corpus niche"),
            ("Digital Marketing", "business", ["--chapters", "10"], "chapters"),
            ("Nope", "Nope", [], "Unknown topic"),
        ],
    )
    def test_bad_requests_fail_loudly(self, cli_env, topic, genre, extra, phrase):
        """Regression: each of these used to succeed with wrong content."""
        env, _ = cli_env
        result = run([str(MAIN), "generate", topic, genre, *extra], env, expect=1)
        combined = result.stdout + result.stderr
        assert phrase in combined, combined


class TestPublish:
    @pytest.fixture()
    def generated(self, cli_env):
        env, tmp = cli_env
        run(
            [str(MAIN), "generate", "Digital Marketing", "business"],
            env,
            expect=0,
        )
        return env, tmp

    def test_publish_builds_all_three_artifacts(self, generated):
        env, tmp = generated
        result = run([str(MAIN), "publish", "1"], env, expect=0)
        out = tmp / "output"
        # publish now shares one naming convention with batch_generate
        epub = out / "digital-marketing.epub"
        pdf = out / "digital-marketing.pdf"
        kdp = out / "digital-marketing.kdp.zip"
        assert epub.is_file(), result.stdout
        assert pdf.is_file(), result.stdout
        assert kdp.is_file(), result.stdout

        from ebook_engine.validators import validate_epub, validate_kdp_zip, validate_pdf

        assert validate_epub(epub) == []
        assert validate_pdf(pdf) == []
        assert validate_kdp_zip(kdp) == []

    def test_publish_records_real_chapter_titles(self, generated):
        """Regression: titles were re-invented as 'Chapter N'."""
        env, _ = generated
        from ebook_engine.epub_reader import read_epub

        run([str(MAIN), "publish", "1"], env, expect=0)
        book = read_epub(env["EBOOK_OUTPUT_DIR"] + "/digital-marketing.epub")
        assert any("Organic Reach" in c.title or "Chapter" not in c.title for c in book.chapters), [
            c.title for c in book.chapters
        ]

    def test_publish_unknown_id_fails(self, generated):
        env, _ = generated
        result = run([str(MAIN), "publish", "9999"], env, expect=1)
        assert "not found" in result.stdout

    def test_publish_without_chapters_fails(self, cli_env):
        env, tmp = cli_env
        run([str(MAIN), "generate", "Travel", "Lifestyle"], env, expect=0)
        for path in (tmp / "output" / "travel").glob("chapter_*.md"):
            path.unlink()
        result = run([str(MAIN), "publish", "1"], env, expect=1)
        assert "No chapter files" in result.stdout


class TestDedupe:
    def test_dedupe_reports_and_removes_duplicates(self, cli_env):
        env, tmp = cli_env
        run([str(MAIN), "generate", "Travel", "Lifestyle"], env, expect=0)
        run([str(MAIN), "generate", "Travel", "Lifestyle"], env, expect=0)
        run([str(MAIN), "generate", "Travel", "Lifestyle"], env, expect=0)

        dry = run([str(MAIN), "catalog-dedupe", "--dry-run"], env, expect=0)
        assert "duplicate" in dry.stdout

        run([str(MAIN), "catalog-dedupe"], env, expect=0)
        stats = run([str(MAIN), "stats"], env, expect=0)
        assert "Total books: 1" in stats.stdout


class TestReadServer:
    def test_serves_the_library_and_a_chapter(self, cli_env):
        env, tmp = cli_env
        run([str(MAIN), "generate", "Digital Marketing", "business"], env, expect=0)
        run([str(MAIN), "publish", "1"], env, expect=0)

        port = free_port()
        process = subprocess.Popen(
            [sys.executable, str(MAIN), "read", "--port", str(port), "--no-open"],
            cwd=str(PROJECT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            origin = f"http://127.0.0.1:{port}"
            for _ in range(150):
                try:
                    with urllib.request.urlopen(origin + "/", timeout=1):
                        break
                except Exception:
                    time.sleep(0.1)
            else:
                pytest.fail("reader server never became reachable")

            with urllib.request.urlopen(origin + "/", timeout=10) as response:
                index = response.read().decode("utf-8", "replace")
            assert response.status == 200
            assert "/read/1" in index

            with urllib.request.urlopen(origin + "/read/1", timeout=10) as response:
                chapter = response.read().decode("utf-8", "replace")
            assert response.status == 200
            assert "Contents" in chapter

            # Traversal must not reach outside the archive
            for attempt in (
                "/asset/1/../../config.py",
                "/asset/1/%2e%2e/%2e%2e/config.py",
            ):
                with pytest.raises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(origin + attempt, timeout=10)
                assert caught.value.code == 404, attempt
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()


class TestListArtifacts:
    """The catalog now tracks four artifacts per book; list must show them."""

    @pytest.fixture()
    def published(self, cli_env):
        env, tmp = cli_env
        run(
            [str(MAIN), "generate", "Digital Marketing", "business", "--author", "Priya Raman"],
            env,
            expect=0,
        )
        run([str(MAIN), "publish", "1"], env, expect=0)
        return env, tmp

    def test_files_column_counts_present_artifacts(self, published):
        env, _ = published
        out = run([str(MAIN), "list"], env, expect=0).stdout
        assert "Files" in out
        assert "4/4" in out

    def test_partial_books_are_not_reported_as_complete(self, cli_env):
        """A book with only an EPUB must not read as 4/4."""
        env, tmp = cli_env
        run(
            [str(MAIN), "generate", "Digital Marketing", "business", "--author", "Priya Raman"],
            env,
            expect=0,
        )
        out = run([str(MAIN), "list"], env, expect=0).stdout
        assert "4/4" not in out, "no packages built yet, so 4/4 would be a lie"

    def test_paths_flag_prints_every_artifact(self, published):
        env, tmp = published
        out = run([str(MAIN), "list", "--paths"], env, expect=0).stdout
        assert "epub" in out
        assert "kdp" in out
        assert "gumroad" in out
        assert "cover" in out
        # every printed path exists (the label prefixes each line)
        found = 0
        for line in out.splitlines():
            match = re.search(r"([A-Za-z]:\\|/).+$", line.strip())
            if match:
                path = Path(line.strip()[match.start() :])
                assert path.is_file(), path
                found += 1
        assert found >= 4, f"expected at least 4 artifact paths, saw {found}"

    def test_paths_flag_on_an_empty_catalog_is_quiet(self, cli_env):
        env, _ = cli_env
        run([str(MAIN), "list", "--paths"], env, expect=0)


class TestMakeBook:
    """One command for generate -> expand -> publish -> audit.

    Expansion is skipped (--target 0) so the test does not call a model
    and does not take minutes; the wiring is what is under test.
    """

    def test_runs_the_whole_chain(self, cli_env):
        env, tmp = cli_env
        result = run(
            [
                str(MAIN),
                "make-book",
                "Digital Marketing",
                "--author",
                "Priya Raman",
                "--target",
                "0",
            ],
            env,
            expect=0,
            timeout=600,
        )
        out = result.stdout
        assert "generate" in out
        assert "publish" in out
        assert "assessment" in out

    def test_produces_every_artifact(self, cli_env):
        env, tmp = cli_env
        run(
            [str(MAIN), "make-book", "Stock Trading", "--author", "Priya Raman", "--target", "0"],
            env,
            expect=0,
            timeout=600,
        )
        out = tmp / "output"
        for suffix in (".epub", ".pdf", ".kdp.zip", ".gumroad.zip"):
            assert list(out.glob(f"*{suffix}")), suffix

    def test_exits_non_zero_when_the_gate_blocks(self, cli_env):
        """No author supplied, so the placeholder author fails --strict."""
        env, tmp = cli_env
        env = {**env, "EBOOK_AUTHOR": "Anonymous"}
        result = run(
            [str(MAIN), "make-book", "Freelancing", "--target", "0"],
            env,
            expect=1,
            timeout=600,
        )
        assert "placeholder" in (result.stdout + result.stderr)
