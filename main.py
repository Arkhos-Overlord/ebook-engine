"""Ebook Creation Engine — CLI entry point."""

import os
import re
import sys

# Support `python main.py` (and launch.cmd) as well as `python -m
# ebook_engine.main`: when this file runs as a script the package lives one
# directory above it, so that directory has to be on sys.path first.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
from rich.table import Table

from ebook_engine.catalog import (
    add_book,
    dedupe_books,
    export_catalog,
    get_stats,
    list_books,
)
from ebook_engine.config import (
    AUTHOR_BIO,
    AUTHOR_NAME,
    KDP_RECOMMENDED_WORDS,
    OUTPUT_DIR,
    PLACEHOLDER_AUTHORS,
    PRICING,
    PUBLISHER_NAME,
    ensure_dirs,
)
from ebook_engine.content_engine import generate_book, generate_outline
from ebook_engine.formatters.matter import describe_book
from ebook_engine.formatters.quality import count_words
from ebook_engine.manuscript import read_chapters, write_chapter
from ebook_engine.paths import artifact_path, slug
from ebook_engine.ui import console


@click.group()
def cli():
    """Ebook Creation Engine — generate, format, publish sellable ebooks."""
    ensure_dirs()


@cli.command()
@click.argument("topic")
@click.argument("genre")
@click.option("--chapters", default=5, help="Number of chapters (corpus holds 5)")
@click.option(
    "--author",
    default=None,
    help="Author name (defaults to EBOOK_AUTHOR from .env)",
)
@click.option(
    "--llm",
    "use_llm",
    is_flag=True,
    help="Write content with the configured LLM instead of the research corpus",
)
def generate(topic, genre, chapters, author, use_llm):
    """Generate a complete book: outline + chapters + cover."""
    from ebook_engine.corpus import NICHE_CONTENT, get_niche_cover_color
    from ebook_engine.cover_engine import generate_cover

    author = (author or AUTHOR_NAME).strip() or AUTHOR_NAME

    console.print("\n[bold blue]📚 Ebook Engine[/bold blue]")
    console.print(f"Topic: {topic} | Genre: {genre} | Chapters: {chapters}\n")

    mode = "llm" if use_llm else "corpus"
    try:
        result = generate_book(topic, genre, chapters, mode=mode)
    except (KeyError, ValueError, RuntimeError, OSError) as e:
        console.print(f"[red]✗ Generation failed: {e}[/red]")
        raise SystemExit(1)

    if not result.get("chapters"):
        console.print(f"[red]✗ No content generated for '{topic}'.[/red]")
        raise SystemExit(1)

    # Generate cover — pass the niche's own colour when this is a niche
    cover_path = str(OUTPUT_DIR / f"{slug(topic)}-cover.png")
    cover_color = None
    niche = result.get("niche") or topic
    if niche in NICHE_CONTENT:
        cover_color = get_niche_cover_color(niche)
    try:
        generate_cover(
            topic,
            result.get("genre") or genre,
            cover_path,
            cover_color=cover_color,
            author=author,
        )
        console.print("[green]✓ Cover generated[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Cover skipped: {e}[/yellow]")
        cover_path = ""

    # Save content to files
    book_dir = OUTPUT_DIR / slug(topic)
    book_dir.mkdir(parents=True, exist_ok=True)

    (book_dir / "outline.md").write_text(result["outline"], encoding="utf-8")

    for ch in result["chapters"]:
        # Write the heading too, so `publish` can recover the real chapter
        # title instead of inventing "Chapter N" (batch_generate already does
        # this; the two writers disagreed).
        (book_dir / f"chapter_{ch['number']:02d}.md").write_text(
            f"## {ch['title']}\n\n{ch['content']}", encoding="utf-8"
        )

    # Register in catalog. The description is composed from the book's own
    # opening line and chapter titles rather than boilerplate, because it
    # is what the store listing shows.
    description = describe_book(
        {
            "topic": topic,
            "genre": result.get("genre") or genre,
            "chapters": result["chapters"],
        }
    )
    book_id = add_book(
        title=topic,
        author=author,
        genre=genre,
        isbn="",
        price_tier="basic",
        price_inr=PRICING["basic"]["price_inr"],
        description=description,
        cover_path=cover_path,
    )

    console.print(f"\n[green]✅ Book '{topic}' generated![/green]")
    console.print(f"   Book ID: {book_id}")
    console.print(f"   Output: {book_dir}")
    console.print("   Status: draft")
    if author.lower() in PLACEHOLDER_AUTHORS:
        console.print(
            f"\n[yellow]⚠ Author is {author!r}, which the publication gate "
            "rejects.[/yellow]\n"
            "   Set [cyan]EBOOK_AUTHOR[/cyan] in .env or re-run with "
            '[cyan]--author "Your Name"[/cyan] before publishing.'
        )
    console.print()


@cli.command()
@click.argument("book_id", type=int)
@click.option("--epub", default="", help="EPUB path (auto-generated if omitted)")
@click.option("--pdf", default="", help="PDF path (auto-generated if omitted)")
@click.option(
    "--mobi",
    default="",
    help="MOBI path to record (there is no MOBI writer in this project)",
)
@click.option("--cover", default="", help="Cover image path")
@click.option("--no-kdp", is_flag=True, help="Skip building the KDP zip")
@click.option("--no-gumroad", is_flag=True, help="Skip building the Gumroad bundle")
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero if the quality gate reports errors (for CI/automation)",
)
def publish(book_id, epub, pdf, mobi, cover, no_kdp, no_gumroad, strict):
    """Package a book for publishing: EPUB, PDF, KDP zip and Gumroad bundle."""
    from ebook_engine.catalog import get_book, update_files, update_status
    from ebook_engine.formatters.epub_formatter import create_epub
    from ebook_engine.formatters.gumroad_zip import create_gumroad_package
    from ebook_engine.formatters.kdp_zip import create_kdp_package
    from ebook_engine.formatters.pdf_formatter import create_pdf
    from ebook_engine.formatters.quality import assess

    book = get_book(book_id)
    if not book:
        console.print(f"[red]Book ID {book_id} not found.[/red]")
        raise SystemExit(1)

    title = book["title"]
    book_dir = OUTPUT_DIR / slug(title)
    book_dir.mkdir(parents=True, exist_ok=True)

    chapters = read_chapters(book_dir)
    if not chapters:
        console.print(f"[red]No chapter files found in {book_dir}.[/red]")
        raise SystemExit(1)

    book_data = {
        "topic": title,
        "genre": book["genre"] or "",
        "author": book["author"] or "",
        "language": book.get("language") or "English",
        "publisher": book.get("publisher") or PUBLISHER_NAME,
        "subtitle": book.get("subtitle") or "",
        "author_bio": book.get("author_bio") or AUTHOR_BIO,
        "chapters": chapters,
        "description": book.get("description", ""),
        "cover_path": cover or book.get("cover_path", ""),
    }

    if not epub:
        epub = artifact_path(OUTPUT_DIR, title, ".epub")
        try:
            create_epub(book_data, epub)
            console.print(f"[green]✓ EPUB: {os.path.basename(epub)}[/green]")
        except Exception as e:
            console.print(f"[red]✗ EPUB failed: {e}[/red]")
            raise SystemExit(1)

    if not pdf:
        pdf = artifact_path(OUTPUT_DIR, title, ".pdf")
        try:
            create_pdf(book_data, pdf)
            console.print(f"[green]✓ PDF: {os.path.basename(pdf)}[/green]")
        except Exception as e:
            # A missing PDF must not lose the EPUB that already succeeded.
            console.print(f"[yellow]⚠ PDF skipped: {e}[/yellow]")
            pdf = ""

    kdp = ""
    if not no_kdp and epub:
        try:
            kdp = create_kdp_package(
                epub,
                output_path=artifact_path(OUTPUT_DIR, title, ".kdp.zip"),
                cover_path=book_data.get("cover_path"),
                metadata=_kdp_metadata(book, kdp_price=PRICING, chapters=chapters),
            )
            console.print(f"[green]✓ KDP: {os.path.basename(kdp)}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ KDP package skipped: {e}[/yellow]")

    gumroad = ""
    if not no_gumroad and epub:
        try:
            listing = book_dir / "kdp_listing.md"
            gumroad = create_gumroad_package(
                epub,
                output_path=artifact_path(OUTPUT_DIR, title, ".gumroad.zip"),
                pdf_path=pdf or None,
                cover_path=book_data.get("cover_path"),
                product=_gumroad_product(book, chapters),
                listing_path=listing if listing.is_file() else None,
                preview_chapter=chapters[0].get("content", "") if chapters else None,
            )
            console.print(f"[green]✓ Gumroad: {os.path.basename(gumroad)}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Gumroad package skipped: {e}[/yellow]")

    update_status(book_id, "published")
    update_files(
        book_id,
        file_epub=epub,
        file_pdf=pdf,
        file_mobi=mobi,
        file_kdp=kdp,
        file_gumroad=gumroad,
        cover_path=book_data.get("cover_path") or cover,
    )

    console.print(f"\n[green]Published '{title}'![/green]")
    console.print(f"   EPUB:    {epub or 'pending'}")
    console.print(f"   PDF:     {pdf or 'pending'}")
    console.print(f"   KDP:     {kdp or 'skipped'}")
    console.print(f"   Gumroad: {gumroad or 'skipped'}")
    if mobi:
        console.print(f"   MOBI:    {mobi} (recorded only — no MOBI writer exists)")
    console.print("   Status:  published\n")

    assessment = assess(
        book_data,
        epub_path=epub,
        pdf_path=pdf or None,
        cover_path=book_data.get("cover_path"),
        channel="kdp",
    )
    _print_assessment(assessment)
    if strict and not assessment.ok:
        raise SystemExit(1)


def _kdp_metadata(book: dict, kdp_price: dict, chapters: list) -> dict:
    """Complete KDP upload record.

    Amazon's form asks for far more than title/author/price: subtitle,
    description, keywords, categories, author bio, publisher, language,
    rights and royalty all have fields. Missing ones either block the
    upload or land the book in the wrong place.
    """
    from ebook_engine.formatters.store_meta import build_kdp_metadata

    tier = book.get("price_tier") or "basic"
    price = kdp_price.get(tier, kdp_price["basic"])
    record = build_kdp_metadata(
        {
            "topic": book["title"],
            "author": book.get("author"),
            "genre": book.get("genre"),
            "description": book.get("description"),
            "isbn": book.get("isbn"),
            "author_bio": AUTHOR_BIO,
            "publisher": PUBLISHER_NAME,
            "chapters": chapters,
        },
        price,
        publisher=PUBLISHER_NAME,
    )
    record["genre"] = book.get("genre")
    record["price_tier"] = tier
    record["status"] = "published"
    return record


def _gumroad_product(book: dict, chapters: list) -> dict:
    """Listing record shipped inside the Gumroad bundle."""
    from ebook_engine.formatters.store_meta import build_gumroad_product

    tier = book.get("price_tier") or "basic"
    price = PRICING.get(tier, PRICING["basic"])
    return build_gumroad_product(
        {
            "topic": book["title"],
            "author": book.get("author"),
            "genre": book.get("genre"),
            "description": re.sub(r"\s+", " ", book.get("description") or "").strip(),
            "chapters": chapters,
        },
        price,
        files={"epub": True, "pdf": True, "cover": True},
    )


def _print_assessment(assessment) -> None:
    """Render a quality report in the terminal."""
    colour = "green" if assessment.ok else "red"
    verdict = "PASS" if assessment.ok else "BLOCKED"
    console.print(f"\n[{colour}]{assessment.channel.upper()} assessment: {verdict}[/{colour}]")
    for message in assessment.errors:
        console.print(f"   [red]✗ {message}[/red]")
    for message in assessment.warnings:
        console.print(f"   [yellow]⚠ {message}[/yellow]")
    if assessment.metrics:
        summary = "  ".join(f"{k}={v}" for k, v in assessment.metrics.items())
        console.print(f"   [dim]{summary}[/dim]")
    console.print()


def _load_book(book_id):
    """Fetch a catalog row and its chapter files, or exit with a message."""
    from ebook_engine.catalog import get_book

    book = get_book(book_id)
    if not book:
        console.print(f"[red]Book ID {book_id} not found.[/red]")
        raise SystemExit(1)
    book_dir = OUTPUT_DIR / slug(book["title"])
    chapters = read_chapters(book_dir) if book_dir.is_dir() else []
    if not chapters:
        console.print(f"[red]No chapter files found for book {book_id}.[/red]")
        raise SystemExit(1)
    book_data = {
        "topic": book["title"],
        "genre": book.get("genre") or "",
        "author": book.get("author") or "",
        "language": book.get("language") or "en",
        "publisher": book.get("publisher") or "",
        "description": book.get("description") or "",
        "cover_path": book.get("cover_path") or "",
        "chapters": chapters,
    }
    return book, book_data


@cli.command()
@click.argument("book_id", type=int)
@click.option(
    "--channel",
    type=click.Choice(["kdp", "gumroad"]),
    default="kdp",
    show_default=True,
    help="Store to audit against",
)
@click.option("--strict", is_flag=True, help="Exit 1 if the gate reports errors")
@click.option(
    "--claims",
    is_flag=True,
    help="List every sourced/statistical sentence for fact-checking",
)
@click.option(
    "--repeats",
    is_flag=True,
    help="List near-duplicate paragraphs and chapters",
)
def quality(book_id, channel, strict, claims, repeats):
    """Audit a stored book for publication without rebuilding it."""
    from ebook_engine.formatters.quality import (
        assess,
        find_attributed_claims,
        find_repeated_passages,
    )

    book, book_data = _load_book(book_id)
    epub = book.get("file_epub") or ""
    pdf = book.get("file_pdf") or ""
    assessment = assess(
        book_data,
        epub_path=epub if epub and os.path.isfile(epub) else None,
        pdf_path=pdf if pdf and os.path.isfile(pdf) else None,
        cover_path=book_data.get("cover_path") or None,
        channel=channel,
    )
    _print_assessment(assessment)

    if claims:
        found = find_attributed_claims(book_data)
        if found:
            console.print(
                f"\n[bold yellow]{len(found)} claim(s) to fact-check[/bold yellow] "
                "— an LLM asked not to invent statistics will invent them anyway, "
                "so verify each against its source:\n"
            )
            for i, sentence in enumerate(found, 1):
                console.print(f"  [yellow]{i:2d}.[/yellow] {sentence}")
        else:
            console.print("\n[green]No attributed claims to check.[/green]")

    if repeats:
        found_repeats = find_repeated_passages(book_data)
        if found_repeats:
            console.print(
                f"\n[bold magenta]{len(found_repeats)} near-duplicate "
                f"passage(s)[/bold magenta] — restated copy reads as padding:\n"
            )
            for i, item in enumerate(found_repeats, 1):
                console.print(
                    f"  [magenta]{i:2d}.[/magenta] "
                    f"{item['similarity']:.0%} similar · {item['where']}"
                )
        else:
            console.print("[green]No repeated passages detected.[/green]")

    if strict and not assessment.ok:
        raise SystemExit(1)


@cli.command()
@click.argument("book_id", type=int)
@click.option(
    "--target",
    default=KDP_RECOMMENDED_WORDS,
    show_default=True,
    help="Total words to aim for across the book",
)
@click.option("--dry-run", is_flag=True, help="Show the plan without calling the model")
@click.option(
    "--force",
    is_flag=True,
    help="Rewrite every chapter unconditionally, accepting shorter results",
)
@click.option(
    "--repeat",
    is_flag=True,
    help="Keep passing until the target is met, no chapter grows, or --max-passes",
)
@click.option(
    "--max-passes",
    default=6,
    show_default=True,
    help="Upper bound on passes when using --repeat",
)
def expand(book_id, target, dry_run, force, repeat, max_passes):
    """Lengthen a book's chapters with the configured LLM backend.

    Each chapter is measured against an equal share of the target, so only
    the short ones are rewritten. Originals are kept beside the new files.
    After expanding, re-run `publish` to rebuild the artifacts.
    """
    from ebook_engine.content_engine import expand_chapter, get_provider, plan_expansion

    book, book_data = _load_book(book_id)
    chapters = book_data["chapters"]
    before = count_words(book_data)

    console.print(f"\n[bold blue]Expand[/bold blue] '{book['title']}'")
    console.print(
        f"   now {before:,} words across {len(chapters)} chapters · "
        f"target {target:,} · share {target // max(1, len(chapters)):,}"
    )

    def plan_for() -> list:
        return list(range(len(chapters))) if force else plan_expansion(chapters, target)

    plan = plan_for()
    if not plan:
        console.print("   [green]✓ every chapter already meets its share.[/green]\n")
        return

    plan_words = [
        f"{chapters[i]['number']} ({count_words({'chapters': [chapters[i]]}):,}w)" for i in plan
    ]
    console.print("   would rewrite: " + ", ".join(plan_words))
    if dry_run:
        console.print("   [yellow]dry run — no model calls made.[/yellow]\n")
        return

    try:
        get_provider()
    except Exception as e:
        console.print(f"[red]✗ No LLM backend available: {e}[/red]")
        raise SystemExit(1)

    book_dir = OUTPUT_DIR / slug(book["title"])
    passes = 0
    while True:
        passes += 1
        plan = plan_for()
        if not plan:
            console.print("   [green]✓ every chapter meets its share.[/green]")
            break
        if passes > 1:
            console.print(
                f"\n   [bold]pass {passes}[/bold] — "
                + ", ".join(str(chapters[i]["number"]) for i in plan)
                + " still short"
            )

        grew = 0
        for i in plan:
            chapter = chapters[i]
            number = int(chapter.get("number") or i + 1)
            old_words = count_words({"chapters": [chapter]})
            share = target // max(1, len(chapters))
            try:
                new_body = expand_chapter(book_data, chapter, share)
            except Exception as e:
                console.print(f"   [red]✗ chapter {number}: {e}[/red]")
                raise SystemExit(1)

            new_words = count_words({"chapters": [{"content": new_body}]})
            # Reject anything that did not grow. An equal count means the
            # model paraphrased without adding, and writing it back would
            # spend the chapter's .md.bak for nothing. --force means
            # "replace this text", so a shorter result is accepted there:
            # removing an invented citation legitimately shortens a chapter.
            if not new_body.strip() or (not force and new_words <= old_words):
                console.print(
                    f"   [yellow]⚠ chapter {number}: model returned "
                    f"{new_words:,}w against {old_words:,}w — kept the original[/yellow]"
                )
                continue

            write_chapter(book_dir, number, str(chapter["title"]), new_body)
            console.print(f"   [green]✓[/green] chapter {number}: {old_words:,}w → {new_words:,}w")
            chapter["content"] = new_body.strip()
            grew += 1

        after = count_words(book_data)
        if after >= target:
            break
        if not repeat:
            break
        if not grew:
            console.print("   [yellow]no chapter grew; stopping[/yellow]")
            break
        if passes >= max_passes:
            console.print(f"   [yellow]reached --max-passes ({max_passes})[/yellow]")
            break

    after = count_words(book_data)
    console.print(f"\n   {before:,} → {after:,} words in {passes} pass(es)")
    if after < target:
        console.print(f"   [yellow]still short of {target:,}; run again or raise --target[/yellow]")
    console.print("   [cyan]re-run 'publish' to rebuild the EPUB, PDF and store zips[/cyan]\n")


@cli.command()
@click.argument("book_id", type=int)
@click.option("--dry-run", is_flag=True, help="Report what would change, no model calls")
def scrub(book_id, dry_run):
    """Remove citations that are not backed by the source corpus.

    Expansion cannot do this: it is instructed to keep every existing
    claim, so a citation the model invented survives it. This is the
    inverse — the original corpus chapter is the only source allowed to
    be cited, and anything attributed elsewhere is deleted or restated as
    plain reasoning.
    """
    from ebook_engine.content_engine import get_provider, scrub_chapter
    from ebook_engine.formatters.quality import find_attributed_claims
    from ebook_engine.manuscript import write_chapter

    book, book_data = _load_book(book_id)
    chapters = book_data["chapters"]
    before_words = count_words(book_data)
    before_claims = find_attributed_claims(book_data)

    console.print(f"\n[bold blue]Scrub[/bold blue] '{book['title']}'")
    console.print(f"   {before_words:,} words · {len(before_claims)} attributed claim(s)")
    if not before_claims:
        console.print("   [green]✓ nothing to remove.[/green]\n")
        return

    reference = _corpus_reference(book["title"])
    if not reference:
        console.print(
            "[yellow]No corpus chapter found for this title — cannot tell "
            "an original claim from an invented one. Aborting.[/yellow]\n"
        )
        raise SystemExit(1)

    if dry_run:
        for i, claim in enumerate(before_claims, 1):
            console.print(f"   [yellow]{i:2d}.[/yellow] {claim[:140]}")
        console.print("\n   [yellow]dry run — no model calls made.[/yellow]\n")
        return

    try:
        get_provider()
    except Exception as e:
        console.print(f"[red]✗ No LLM backend available: {e}[/red]")
        raise SystemExit(1)

    # The reference is indexed by chapter position: one corpus chapter per
    # book chapter, in order.
    reference_by_index = reference.split("\n\n===CHAPTER===\n\n")
    book_dir = OUTPUT_DIR / slug(book["title"])

    for chapter in chapters:
        number = int(chapter.get("number") or chapters.index(chapter) + 1)
        index = number - 1
        ref = reference_by_index[index] if 0 <= index < len(reference_by_index) else ""
        old_words = count_words({"chapters": [chapter]})
        try:
            new_body = scrub_chapter(book_data, chapter, reference=ref)
        except Exception as e:
            console.print(f"   [red]✗ chapter {number}: {e}[/red]")
            raise SystemExit(1)
        new_words = count_words({"chapters": [{"content": new_body}]})
        if not new_body.strip() or new_words >= old_words:
            console.print(
                f"   [yellow]⚠[/yellow] chapter {number}: nothing removed "
                f"({old_words:,}w → {new_words:,}w) — kept the original"
            )
            continue
        write_chapter(book_dir, number, str(chapter["title"]), new_body)
        console.print(f"   [green]✓[/green] chapter {number}: {old_words:,}w → {new_words:,}w")
        chapter["content"] = new_body.strip()

    after_words = count_words(book_data)
    after_claims = find_attributed_claims(book_data)
    console.print(
        f"\n   {before_words:,} → {after_words:,} words · "
        f"{len(before_claims)} → {len(after_claims)} claim(s)"
    )
    if after_claims:
        console.print(
            "   [yellow]some claims remain; run again or review "
            "with 'quality <id> --claims'[/yellow]"
        )
    console.print("   [cyan]re-run 'publish' to rebuild the EPUB, PDF and store zips[/cyan]\n")


def _corpus_reference(title: str) -> str:
    """The original corpus chapters for a book, joined as one reference.

    This is what makes the scrub able to tell an original claim from an
    invented one: the corpus never contained the fabricated citations.
    """
    from ebook_engine.corpus import NICHE_CONTENT

    niche = NICHE_CONTENT.get(title)
    if not niche:
        return ""
    return "\n\n===CHAPTER===\n\n".join("\n\n".join(ch["content"]) for ch in niche["chapters"])


@cli.command()
@click.argument("book_id", type=int, required=False)
@click.option("--port", default=8765, show_default=True, help="Port (0 picks a free one)")
@click.option("--no-open", is_flag=True, help="Do not launch a browser")
def read(book_id, port, no_open):
    """Read your library in the browser.

    With no argument the library index is served; with a book id that
    book opens directly. The server listens on 127.0.0.1 only.
    """
    from ebook_engine.server import library_entries, serve

    entries = library_entries()
    if not entries:
        console.print("[yellow]No published books with an EPUB yet.[/yellow]")
        console.print(
            "[dim]Generate and publish one first:[/dim]\n"
            '  [cyan]python main.py generate "Digital Marketing" business[/cyan]\n'
            "  [cyan]python main.py publish 1[/cyan]"
        )
        raise SystemExit(1)

    if book_id is not None:
        wanted = next((e for e in entries if e["id"] == book_id), None)
        if not wanted:
            console.print(
                f"[red]Book {book_id} has no readable EPUB.[/red] "
                f"Readable ids: {', '.join(str(e['id']) for e in entries)}"
            )
            raise SystemExit(1)

    console.print(f"[green]Opening {len(entries)} book{'s' if len(entries) != 1 else ''}[/green]")
    serve(port=port, book_id=book_id, open_browser=not no_open)


_ARTIFACT_KEYS = ("file_epub", "file_pdf", "file_kdp", "file_gumroad")


def _artifact_count(book: dict) -> tuple[int, int]:
    """(present, expected) for the four files a published book needs."""
    present = sum(1 for key in _ARTIFACT_KEYS if book.get(key) and os.path.isfile(book[key]))
    return present, len(_ARTIFACT_KEYS)


@cli.command("list")
@click.option(
    "--paths",
    is_flag=True,
    help="Print every artifact path instead of the table",
)
def list_cmd(paths):
    """List all books in catalog."""
    books = list_books()
    if not books:
        console.print("[yellow]No books in catalog yet.[/yellow]")
        return

    if paths:
        for book in books:
            console.print(f"\n[bold cyan]{book['id']}[/bold cyan] {book['title']}")
            for key in (*_ARTIFACT_KEYS, "cover_path"):
                value = book.get(key) or ""
                exists = bool(value) and os.path.isfile(value)
                state = "green" if exists else "red"
                label = key[5:] if key.startswith("file_") else key
                shown = value if value else "(not built)"
                # soft_wrap keeps a path on one line: rich's own wrapping
                # would break it across lines and make it uncopyable.
                console.print(f"   [{state}]{label:<8}[/{state}] {shown}", soft_wrap=True)
        console.print()
        return

    table = Table(show_header=True)
    table.add_column("ID", style="cyan", min_width=4)
    table.add_column("Title", min_width=20)
    table.add_column("Genre", min_width=12)
    table.add_column("Status", min_width=10)
    table.add_column("Price", min_width=8)
    table.add_column("Files", min_width=6)

    for book in books:
        tier = book.get("price_tier", "basic")
        price = PRICING.get(tier, PRICING["basic"])["price_inr"]
        have, want = _artifact_count(book)
        files = f"{have}/{want}"
        if have == want:
            files = f"[green]{files}[/green]"
        elif have:
            files = f"[yellow]{files}[/yellow]"
        else:
            files = f"[red]{files}[/red]"
        table.add_row(
            str(book["id"]),
            book["title"][:20],
            (book.get("genre") or "-")[:12],
            book["status"],
            f"₹{price}",
            files,
        )

    console.print(table)
    stats = get_stats()
    console.print(
        f"\nStats: {stats['total']} books, {stats['published']} published, {stats['draft']} draft\n"
    )


@cli.command()
def stats():
    """Show catalog statistics."""
    s = get_stats()
    console.print("\n📊 Catalog Stats:")
    console.print(f"   Total books: {s['total']}")
    console.print(f"   Published:   {s['published']}")
    console.print(f"   Draft:       {s['draft']}")
    console.print()


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
def catalog_export(fmt):
    """Export catalog."""
    data = export_catalog(fmt)
    output_path = OUTPUT_DIR / f"catalog.{fmt}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(data, encoding="utf-8")
    console.print(f"[green]✅ Catalog exported to {output_path}[/green]\n")


@cli.command("catalog-dedupe")
@click.option("--dry-run", is_flag=True, help="Report duplicates without deleting")
def catalog_dedupe(dry_run):
    """Collapse duplicate catalog rows (keeps the newest of each title)."""
    if dry_run:
        titles: dict[str, int] = {}
        for book in list_books():
            key = book["title"].lower()
            titles[key] = titles.get(key, 0) + 1
        dupes = {k: v for k, v in titles.items() if v > 1}
        console.print(
            f"[yellow]{sum(dupes.values()) - len(dupes)} duplicate rows "
            f"across {len(dupes)} titles[/yellow]"
        )
        return
    removed = dedupe_books()
    console.print(f"[green]✅ Removed {removed} duplicate rows.[/green]")
    stats = get_stats()
    console.print(f"   Catalog now holds {stats['total']} books.\n")


@cli.command()
@click.argument("topic")
@click.argument("genre")
def outline(topic, genre):
    """Generate just an outline (requires a reachable LLM backend)."""
    try:
        result = generate_outline(topic, genre)
    except Exception as e:
        console.print(f"[red]✗ Outline generation failed: {e}[/red]")
        console.print(
            "[yellow]Hint: `outline` needs a running backend "
            "(set LLM_BACKEND / OLLAMA_URL, or start Ollama). "
            "Use `generate` for corpus-backed content.[/yellow]"
        )
        raise SystemExit(1)
    console.print(result)
    output = OUTPUT_DIR / f"{slug(topic)}-outline.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")


def _lookup_book_id(title: str):
    """Find a catalog row by title, case-insensitively."""
    from ebook_engine.catalog import list_books

    for row in list_books():
        if (row.get("title") or "").lower() == title.strip().lower():
            return row.get("id")
    return None


@cli.command()
@click.argument("topic")
@click.argument("genre", default="")
@click.option("--author", default=None, help="Author name (defaults to EBOOK_AUTHOR)")
@click.option("--chapters", default=5, show_default=True, help="Chapters to generate")
@click.option(
    "--target",
    default=KDP_RECOMMENDED_WORDS,
    show_default=True,
    help="Words to aim for; 0 skips expansion entirely",
)
@click.option("--llm", "use_llm", is_flag=True, help="Write with an LLM, not the corpus")
def make_book(topic, genre, author, chapters, target, use_llm):
    """Generate, lengthen, package and audit a book in one command.

    Expansion calls a language model and takes minutes, so the cost is
    stated before it starts. Pass --target 0 to skip it.
    """
    import subprocess
    import sys
    import time

    from ebook_engine.corpus import get_niche_genre

    genre = genre or get_niche_genre(topic)
    author = author or AUTHOR_NAME

    generate = ["generate", topic, genre, "--author", author, "--chapters", str(chapters)]
    if use_llm:
        generate.append("--llm")

    steps = [generate]
    if target:
        steps.append(["expand", "--target", str(target), "--repeat"])
    steps.append(["publish"])
    steps.append(["quality", "--strict"])

    console.print(f"\n[bold blue]Make book[/bold blue] {topic!r} — {genre}")
    if target:
        console.print(
            f"   will call the LLM to reach {target:,} words. This takes minutes, "
            "not seconds. Use --target 0 to skip expansion.\n"
        )

    book_id = None
    for index, step in enumerate(steps):
        command = step[0]
        args = [sys.executable, "main.py", command]
        if command != "generate" and book_id is not None:
            args.append(str(book_id))
        args.extend(step[1:])

        last = index == len(steps) - 1
        started = time.time()
        if last:
            # The audit is the point of the command: let it print itself.
            result = subprocess.run(args, text=True, encoding="utf-8", errors="replace")
        else:
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
        elapsed = time.time() - started

        if result.returncode != 0:
            if not last:
                console.print(f"   [red]✗ {command} failed[/red]")
                console.print((result.stdout or "") + (result.stderr or ""))
            raise SystemExit(1)
        if not last:
            console.print(f"   [green]✓[/green] {command} ({elapsed:.0f}s)")

        if index == 0:
            book_id = _lookup_book_id(topic)
            if book_id is None:
                console.print(f"   [red]✗ {topic!r} was not added to the catalog[/red]")
                raise SystemExit(1)


if __name__ == "__main__":
    cli()
