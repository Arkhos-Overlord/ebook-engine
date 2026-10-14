# Ebook Creation Engine

A Python engine that generates, formats, packages and reads sellable ebooks:
research-backed content, cover art, KDP-ready EPUB and PDF, and a built-in
reader that opens your library in the browser.

## What it actually does

- **Research-backed content** — 15 niches / 75 chapters / 63,727 words ship
  in `data/content_data.json`. Generation works offline with no LLM.
- **Optional LLM writing** — `--llm` routes to Ollama (local, free) or
  OpenAI when you want fresh prose instead of the corpus.
- **Covers** — template covers using genre palettes *and* each niche's own
  colour from the corpus.
- **Multi-format export** — EPUB3 and PDF, plus a KDP upload zip holding the
  EPUB, cover, metadata and listing.
- **Catalog** — SQLite book library with pricing tiers and stats.
- **Built-in reader** — `python main.py read` serves your library on
  `127.0.0.1` and opens it in your browser, with a table of contents,
  page navigation and the book's own stylesheet.

MOBI is **not** implemented: the `--mobi` flag only records a path you supply.

## What we are working for

Publish books that earn money on Amazon KDP and Gumroad, and the engine
exists to remove the mechanical work around writing them.

Concretely, a book is done when:

1. it clears `main.py quality <id> --strict` (no errors, only warnings)
2. every sourced claim has been checked against a real source
3. `output/` holds a valid EPUB3, a PDF, a KDP zip and a Gumroad bundle
4. a person has read it end to end and would put their name on it

Step 4 is the one the engine cannot help with, and it is the one that
decides whether any of this works.

## The library

15 books, 235,235 words, ~15,700 each. Two real clusters and six
singletons:

| Genre | Books | |
|---|---|---|
| Business | 4 | Digital Marketing, E-commerce, Freelancing, Real Estate Investing |
| Finance | 3 | Cryptocurrency, Stock Trading, Term Insurance |
| Lifestyle | 2 | Travel, YouTube Content Creation |
| Technical | 1 | Web Development |
| Health / Wellness / Self-Help / Cooking / Creative | 1 each | |

### The honest constraint

Topic mix is the *second* problem, not the first.

Adding a fourth book to a saturated niche will not outrank books by
authors who have been ranking there for a decade. Stock trading, crypto,
meditation and web development are all owned by credentialed authors.
Category strategy only decides where you are visible once a reader
arrives.

What tends to matter more, roughly in order:

1. **Something a real author has** — credentials, first-hand data, a
   story, a point of view the corpus does not contain
2. **Concentration** — 8-10 books in two adjacent niches beats 30 spread
   thin. Right now six books are alone in their category
3. **Cover and blurb** — the first thing a browser sees
4. **Reviews** — the multiplier on all of the above

So if the direction is more tech and finance: finance is the stronger
position (3 books, one audience, adjacent sub-topics) and is the right
place to go deeper. Tech is the weakest cluster at one book, so growing
it is building a new audience from zero rather than extending one.

If either is a field you actually know something about, that changes the
calculation entirely — the engine handles the mechanical half, and your
subject knowledge would be the half that actually differentiates the
books. Worth deciding before generating more.

## Quick start

```bash
cd ebook_engine
pip install -r requirements.txt

python main.py --help
```

Double-click `launch.cmd` to open the CLI in a terminal.

## Usage

```bash
# One command: generate -> lengthen -> package -> audit
python main.py make-book "Digital Marketing" --author "Your Name"
python main.py make-book "Digital Marketing" --target 0   # skip expansion
```

or step by step:

```bash
# Generate a book from the research corpus (5 chapters, offline)
python main.py generate "Digital Marketing" business --author "Priya Raman"

# Generate with an LLM instead of the corpus (needs Ollama or an OpenAI key)
python main.py generate "Python for Beginners" technical --llm

# Package it: EPUB + PDF + KDP zip + Gumroad bundle, then audit it
python main.py publish 1
python main.py publish 1 --strict     # exit 1 if the gate blocks publication

# Lengthen a thin book with the configured LLM (corpus books are ~4,200 words)
python main.py expand 1 --dry-run     # show the plan, no model calls
python main.py expand 1               # rewrite the short chapters
python main.py expand 1 --target 18000
python main.py expand 1 --force       # rewrite every chapter

# Audit a stored book without rebuilding it
python main.py quality 1                        # against KDP rules
python main.py quality 1 --channel gumroad      # against Gumroad rules
python main.py quality 1 --strict               # exit 1 if blocked
python main.py quality 1 --claims               # list every sourced claim for fact-checking
python main.py quality 1 --repeats              # list near-duplicate passages

# Remove citations the source corpus does not back (see Length below)
python main.py scrub 1 --dry-run                # show what would change, no model calls
python main.py scrub 1

# Read it
python main.py read          # library index in the browser
python main.py read 1        # open book 1 directly

# Catalog
python main.py list             # includes a Files column (4/4 when everything exists)
python main.py list --paths     # print every artifact path, colour-coded by existence
python main.py stats
python main.py catalog-export --format json
python main.py catalog-dedupe          # collapse duplicate rows
python main.py catalog-dedupe --dry-run

# Outline only (requires a reachable LLM backend)
python main.py outline "AI Trading" finance
```

### Publication quality gate

Every book is audited before it ships, because a draft that reaches a
store is worse than one that does not:

- **author** — placeholder names (`Demo Author`, `Anonymous`, your name
  left as the default) block publication outright
- **length** — under 2,500 words Amazon rejects the file; under 15,000
  the gate warns that the book is thin for its niche
- **copy** — generic `Chapter N` titles, empty chapters and leftover
  `Lorem`/`TODO` text all block
- **disclaimers** — finance, health, wellness, business and self-help
  books ship a genre-appropriate disclaimer as back matter
- **cover** — missing, under 1000x1600, over 50 MB or off-ratio
- **artifacts** — the EPUB must validate: nav document, resolvable
  spine, well-formed XHTML, and the package metadata Amazon requires
  (`unique-identifier`, version 3, `dc:identifier`, `dc:language`,
  `dc:date`, `dcterms:modified`); the PDF must open with pages and text
- **repetition** — near-duplicate paragraphs and chapters are reported,
  because a model told to hit a word count can hit it by restating itself

KDP treats all of that as fatal except the advisory items. Gumroad has
no word floor, so length becomes a warning and the rest still applies.

`publish` builds **both** store packages. The KDP zip carries the EPUB,
the cover, and a `kdp_metadata.json` with the fields Amazon's upload form
asks for — title, subtitle, author, author bio, publisher, language,
description, keywords, categories, ISBN, publication date, both prices,
royalty, the Kindle Unlimited flag, and rights. Keywords are derived from
the book's own genre and chapter titles rather than a fixed marketing
list. The Gumroad bundle carries both formats, the cover, a
`product.json` listing record, and a sample chapter.

Two things are deliberately left to you. **BISAC codes** must be picked
in KDP's own category picker — a wrong code files the book on the wrong
shelf, so suggested category *names* ship in the record instead. And
**author bio** and **publisher** come from you: set `EBOOK_AUTHOR_BIO`
and `EBOOK_PUBLISHER` in `.env`.

### Length

The corpus ships ~4,200 words per book. That clears Amazon's 2,500-word
floor but is thin for a competitive niche, so the gate warns at 15,000.

`expand` fixes that with the configured LLM:

```bash
python main.py expand 1 --dry-run   # which chapters are short, no model calls
python main.py expand 1             # rewrite them, originals kept as .md.bak
```

- each chapter is measured against an equal share of `--target`, so only
  the short ones are rewritten
- the prompt forbids inventing statistics, studies or sources — a
  fabricated citation is a worse publishing problem than a short chapter
- a result that comes back shorter or empty is rejected and the original
  kept
- it usually takes two passes to reach 15,000; run it again or raise
  `--target`, then `publish` to rebuild the artifacts

### Claims

Chapters carry sentences that attribute a finding to a source or state a
hard number. The gate counts them and never blocks on them — it cannot
tell a real study from an invented one — but it will not let them pass
unexamined either:

```bash
python main.py quality 1                # shows "N attributed claim(s)"
python main.py quality 1 --claims       # prints each one for review
python main.py scrub 1 --dry-run        # what a scrub would remove
python main.py scrub 1                  # remove them
```

`expand` is told to keep every existing claim, so it cannot remove one
that is already in the text. `scrub` is the inverse: the original corpus
chapter is the only source allowed to be cited, and anything attributed
elsewhere is deleted or restated as plain reasoning with no source
attached. The result is normally shorter, which is intended.

Every claim in the corpus has been checked against primary sources.
The verdicts — what was corrected, what was confirmed, and the two
whose direction the literature contradicts — are recorded in
[`data/SOURCE_AUDIT.md`](data/SOURCE_AUDIT.md).

`batch_generate` preserves expanded chapters over the corpus whenever
they are longer, so re-running it does not lose work — and does not
resurrect a scrub either.

Generate and publish the whole corpus in one pass:

```bash
python batch_generate.py
```

### Reader options

```bash
python main.py read --port 9000   # use a different port (0 = any free port)
python main.py read --no-open     # don't launch a browser
```

The reader binds to `127.0.0.1` only. It never extracts archives to disk:
assets are read straight out of the EPUB by name, so a path like
`../../etc/passwd` has nothing to reach.

## Configuration

Set in `.env` or the environment:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BACKEND` | `ollama` | `ollama` or `openai` |
| `OLLAMA_MODEL` | `llama3` | model for local generation |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | model when using OpenAI |
| `OPENAI_API_KEY` | – | required if `LLM_BACKEND=openai` |
| `EBOOK_FONT_PATH` | auto | override the font used for covers |
| `EBOOK_OUTPUT_DIR` | `output/` | where books are written |
| `EBOOK_STATE_DIR` | `state/` | where `catalog.db` lives |
| `EBOOK_AUTHOR` | `Anonymous` | default author; must be a real name to publish |
| `EBOOK_AUTHOR_BIO` | – | back-cover bio used for the about page |
| `EBOOK_PUBLISHER` | – | imprint printed on the copyright page |
| `KDP_MIN_WORDS` | `2500` | below this KDP rejects the file |
| `KDP_RECOMMENDED_WORDS` | `15000` | below this the gate warns the book is thin |
| `KDP_MIN_CHAPTERS` | `5` | below this the gate warns |

## Project structure

```
ebook_engine/
├── main.py               CLI entry point
├── batch_generate.py     build every niche in one pass
├── config.py             paths, pricing, palettes, LLM settings
├── catalog.py            SQLite catalog + deterministic ISBNs
├── corpus.py            research corpus (15 niches, offline generation)
├── content_engine.py     corpus/LLM switch, providers
├── manuscript.py         read/write chapter_NN.md (shared by CLI + batch)
├── paths.py              slug and artifact naming (shared by CLI + batch)
├── cover_engine.py       cover rendering
├── epub_reader.py        stdlib + lxml EPUB parser
├── server.py             loopback HTTP reader
├── validators.py         EPUB / PDF / store-package checks
├── ui.py                 shared console (Windows-safe encoding)
├── data/
│   └── content_data.json the research corpus (source of truth)
├── formatters/
│   ├── epub_formatter.py EPUB3 (nav, NCX, escaped XHTML)
│   ├── pdf_formatter.py  reportlab PDF with TOC and bookmarks
│   ├── matter.py         front/back matter, genre disclaimers
│   ├── quality.py        KDP/Gumroad publication gate
│   ├── kdp_zip.py        KDP upload package
│   └── gumroad_zip.py    Gumroad bundle
├── templates/
│   ├── epub.css          stylesheet embedded in every book
│   └── reader/           reader HTML and CSS
├── tests/                312 tests + artifact validators
├── books/ai-small-business/   a finished book and its builder
├── state/catalog.db      runtime catalog (gitignored)
├── output/               generated books (gitignored)
└── launch.cmd            terminal launcher
```

## Development

```bash
pip install -e ".[dev]"   # or: pip install -r requirements.txt

pytest                    # 312 tests; also runs the lint + corpus gates
ruff check .              # lint
ruff format .             # formatting
```

The suite defines the project's acceptance gates:

- **G1 static** — `ruff check` and `ruff format --check` must be clean
- **G3 artifacts** — every generated EPUB/PDF/KDP zip is structurally
  validated (nav present, spine resolves, XHTML is well-formed, cover
  embedded, PDF has pages and bookmarks)
- **G4 data** — the corpus SHA256 must match the recorded baseline, so a
  migration cannot silently lose words
- **G5/G6** — the CLI is exercised as real subprocesses, including the
  failure paths (wrong topic, chapter over-request, missing book, traversal)

## Requirements

- Python 3.10+
- Optional: Ollama for local LLM generation

## Revenue model

1. Publish on Amazon KDP (free to upload)
2. Direct sales via Gumroad
3. Price tiers: ₹349 / ₹799 / ₹1,499 ($4.99 / $9.99 / $14.99)
4. Target: 50 books → ₹50K/mo by Month 3
