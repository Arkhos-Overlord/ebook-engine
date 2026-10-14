"""Batch generate every niche in the research corpus as an ebook.

Produces the complete set of artifacts per book — cover, chapters, EPUB,
PDF, KDP zip and Gumroad bundle — and finishes with a quality summary so
a batch run tells you what is publishable rather than just what exists.
"""

import os
import sys

# Allow `python batch_generate.py` from inside the package directory.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.table import Table

from ebook_engine.catalog import make_isbn, upsert_book
from ebook_engine.config import (
    AUTHOR_BIO,
    AUTHOR_NAME,
    OUTPUT_DIR,
    PRICING,
    PUBLISHER_NAME,
    ensure_dirs,
)
from ebook_engine.corpus import (
    generate_book,
    get_all_niches,
    get_niche_cover_color,
    get_niche_genre,
)
from ebook_engine.cover_engine import generate_cover
from ebook_engine.formatters.epub_formatter import create_epub
from ebook_engine.formatters.gumroad_zip import create_gumroad_package
from ebook_engine.formatters.kdp_zip import create_kdp_package
from ebook_engine.formatters.pdf_formatter import create_pdf
from ebook_engine.formatters.quality import assess, count_words
from ebook_engine.formatters.store_meta import build_gumroad_product, build_kdp_metadata
from ebook_engine.manuscript import read_chapters, write_chapter
from ebook_engine.paths import artifact_path, slug
from ebook_engine.ui import console


def generate_single_book(niche: str) -> dict:
    """Generate one complete book from research data.

    Returns a status dict rather than a bool so the caller can report
    which artifacts were built and how the gate scored the book.
    """
    genre = get_niche_genre(niche)
    result = generate_book(niche, genre, num_chapters=5)

    status = {"niche": niche, "built": [], "skipped": [], "assessment": None}
    if not result["chapters"]:
        console.print(f"[red]✗ No content for {niche}[/red]")
        status["ok"] = False
        return status

    book_dir_name = slug(niche)
    book_dir = OUTPUT_DIR / book_dir_name
    book_dir.mkdir(parents=True, exist_ok=True)

    # A batch re-run must not destroy expanded chapters. If what is on disk
    # already says more than the corpus does, the on-disk copy is the later
    # work and wins; otherwise this run regenerates it.
    on_disk = read_chapters(book_dir)
    corpus_words = count_words({"chapters": result["chapters"]})
    disk_words = count_words({"chapters": on_disk}) if on_disk else 0
    content_source = "corpus"
    if on_disk and disk_words > corpus_words:
        result = {**result, "chapters": on_disk}
        content_source = f"kept ({disk_words:,}w on disk)"
        status["content_preserved"] = True

    # Cover, using the niche's own colour from the corpus.
    cover_path = str(book_dir / "cover.png")
    try:
        generate_cover(
            niche,
            genre,
            cover_path,
            cover_color=get_niche_cover_color(niche),
            author=result.get("author") or AUTHOR_NAME,
        )
        status["built"].append("cover")
    except Exception as e:
        console.print(f"[yellow]⚠ Cover skipped for {niche}: {e}[/yellow]")
        cover_path = ""
        status["skipped"].append("cover")

    # Write chapters only when they came from the corpus — writing back a
    # preserved chapter would needlessly replace the .bak with itself.
    if content_source == "corpus":
        for ch in result["chapters"]:
            write_chapter(book_dir, ch["number"], ch["title"], ch["content"])
    status["content"] = content_source
    (book_dir / "outline.md").write_text(result["outline"], encoding="utf-8")

    book_data = {
        "topic": niche,
        "genre": genre,
        "author": result["author"],
        "language": "English",
        "publisher": PUBLISHER_NAME,
        "author_bio": AUTHOR_BIO,
        "chapters": result["chapters"],
        "description": result.get("description", ""),
        "cover_path": cover_path,
    }

    # Every artifact is built independently and its path is only recorded
    # when the file actually exists — a failed build must never leave a
    # phantom path in the catalog.
    paths = {}
    artifacts = [
        ("epub", artifact_path(OUTPUT_DIR, niche, ".epub"), create_epub),
        ("pdf", artifact_path(OUTPUT_DIR, niche, ".pdf"), create_pdf),
    ]
    for name, path, builder in artifacts:
        try:
            builder(book_data, path)
            if os.path.exists(path):
                paths[f"file_{name}"] = path
                status["built"].append(name)
            else:
                console.print(f"[yellow]⚠ {name.upper()} not written for {niche}[/yellow]")
                status["skipped"].append(name)
        except Exception as e:
            console.print(f"[yellow]⚠ {name.upper()} skipped for {niche}: {e}[/yellow]")
            status["skipped"].append(name)

    epub = paths.get("file_epub", "")
    price = PRICING["standard"]
    if epub:
        try:
            kdp = create_kdp_package(
                epub,
                output_path=artifact_path(OUTPUT_DIR, niche, ".kdp.zip"),
                cover_path=cover_path or None,
                metadata=build_kdp_metadata(book_data, price, publisher=PUBLISHER_NAME),
            )
            status["built"].append("kdp")
            status["kdp"] = kdp
        except Exception as e:
            console.print(f"[yellow]⚠ KDP package skipped for {niche}: {e}[/yellow]")
            status["skipped"].append("kdp")

        try:
            gumroad = create_gumroad_package(
                epub,
                output_path=artifact_path(OUTPUT_DIR, niche, ".gumroad.zip"),
                pdf_path=paths.get("file_pdf") or None,
                cover_path=cover_path or None,
                product=build_gumroad_product(
                    book_data, price, files={"epub": True, "pdf": True, "cover": True}
                ),
                preview_chapter=result["chapters"][0].get("content", ""),
            )
            status["built"].append("gumroad")
            status["gumroad"] = gumroad
        except Exception as e:
            console.print(f"[yellow]⚠ Gumroad bundle skipped for {niche}: {e}[/yellow]")
            status["skipped"].append("gumroad")

    try:
        upsert_book(
            title=niche,
            author=book_data["author"],
            genre=genre,
            isbn=make_isbn(niche),
            price_tier="standard",
            price_inr=PRICING["standard"]["price_inr"],
            file_epub=epub,
            file_pdf=paths.get("file_pdf", ""),
            file_kdp=status.get("kdp", ""),
            file_gumroad=status.get("gumroad", ""),
            cover_path=cover_path,
            description=book_data["description"],
        )
    except Exception as e:
        console.print(f"[yellow]⚠ Catalog add skipped for {niche}: {e}[/yellow]")

    status["assessment"] = assess(
        book_data,
        epub_path=epub or None,
        pdf_path=paths.get("file_pdf") or None,
        cover_path=cover_path or None,
        channel="kdp",
    )
    status["words"] = count_words(book_data)
    status["ok"] = True
    return status


def main() -> None:
    ensure_dirs()
    niches = get_all_niches()

    console.print("\n[bold blue]📚 Ebook Engine - Batch Generator[/bold blue]")
    console.print(f"[bold]Building {len(niches)} books from research data[/bold]\n")

    table = Table()
    table.add_column("#", style="cyan")
    table.add_column("Niche", style="green")
    table.add_column("Genre", style="yellow")
    table.add_column("Words", justify="right", style="white")
    table.add_column("Artifacts", style="white")
    table.add_column("KDP gate", style="white")

    ok_count = fail_count = blocked_count = 0

    for i, niche in enumerate(niches, 1):
        genre = get_niche_genre(niche)
        try:
            status = generate_single_book(niche)
        except Exception as e:
            fail_count += 1
            table.add_row(str(i), niche, genre, "-", "-", f"[red]✗ {str(e)[:40]}[/red]")
            continue

        if not status.get("ok"):
            fail_count += 1
            table.add_row(str(i), niche, genre, "-", "-", "[red]✗ no content[/red]")
            continue

        ok_count += 1
        assessment = status["assessment"]
        if assessment and assessment.ok:
            gate = "[green]✓ pass[/green]"
        else:
            blocked_count += 1
            gate = "[red]✗ blocked[/red]"
        table.add_row(
            str(i),
            niche,
            genre,
            f"{status['words']:,}",
            " ".join(status["built"]) or "-",
            gate,
        )

    console.print()
    console.print(table)
    console.print(
        f"\n[bold green]{ok_count} built, {fail_count} failed[/bold green] · "
        f"{blocked_count} blocked by the KDP gate"
    )
    console.print(f"[cyan]Output directory: {OUTPUT_DIR}[/cyan]")
    if blocked_count:
        console.print(
            "[yellow]Run 'python main.py quality <id>' to see what each "
            "blocked book needs (usually a real author name).[/yellow]"
        )


if __name__ == "__main__":
    main()
