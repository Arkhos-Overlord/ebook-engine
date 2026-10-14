"""Configuration manager for ebook_engine."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

# Runtime locations. Both can be redirected with an environment variable,
# which is how the test suite runs the CLI against a throwaway tree instead
# of writing into the project's real state/ and output/.
OUTPUT_DIR = Path(os.getenv("EBOOK_OUTPUT_DIR") or BASE_DIR / "output")
CONFIG_DIR = Path(os.getenv("EBOOK_STATE_DIR") or (BASE_DIR / "state"))
TEMPLATES_DIR = BASE_DIR / "templates"

DB_PATH = CONFIG_DIR / "catalog.db"

# LLM Configuration
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")  # "ollama" or "openai"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Publishing identity. Overridden by --author on the CLI.
AUTHOR_NAME = os.getenv("EBOOK_AUTHOR", "Anonymous")
AUTHOR_BIO = os.getenv("EBOOK_AUTHOR_BIO", "")
PUBLISHER_NAME = os.getenv("EBOOK_PUBLISHER", "")

# KDP quality thresholds.
# Amazon rejects reflowable ebooks under ~2,500 words outright; a book that
# merely clears that floor is still a pamphlet, so warn much higher up.
KDP_MIN_WORDS = int(os.getenv("KDP_MIN_WORDS", "2500"))
KDP_RECOMMENDED_WORDS = int(os.getenv("KDP_RECOMMENDED_WORDS", "15000"))
KDP_MIN_CHAPTERS = int(os.getenv("KDP_MIN_CHAPTERS", "5"))
# Values the suite treats as "nobody filled this in".
PLACEHOLDER_AUTHORS = frozenset(
    {"demo author", "anonymous", "author", "test author", "your name", ""}
)

# Output Configuration
EPUB_COVER_SIZE = (1600, 2560)
PDF_PAGE_SIZE = "A5"

# Pricing (INR)
PRICING = {
    "basic": {"price_inr": 349, "price_usd": 4.99},
    "standard": {"price_inr": 799, "price_usd": 9.99},
    "premium": {"price_inr": 1499, "price_usd": 14.99},
}

# Genres with cover color schemes. Keys are lowercase genre names as they
# appear in the content corpus (config.py -> data/content_data.json).
GENRE_COLORS = {
    "business": {"primary": "#1f3a5f", "secondary": "#4a90d9"},
    "cooking": {"primary": "#5c3317", "secondary": "#e8a33d"},
    "creative": {"primary": "#3a2f4f", "secondary": "#9b72cf"},
    "finance": {"primary": "#00b894", "secondary": "#0984e3"},
    "health": {"primary": "#14532d", "secondary": "#43a047"},
    "lifestyle": {"primary": "#4a1942", "secondary": "#e05299"},
    "self-help": {"primary": "#fd79a8", "secondary": "#e17055"},
    "technical": {"primary": "#0984e3", "secondary": "#6c5ce7"},
    "wellness": {"primary": "#1a5276", "secondary": "#52be80"},
    # Fallback used when a genre is not listed above.
    "fiction": {"primary": "#2c3e50", "secondary": "#8e44ad"},
}


def ensure_dirs() -> None:
    """Create runtime directories. Call explicitly, not at import time."""
    for d in (OUTPUT_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)
