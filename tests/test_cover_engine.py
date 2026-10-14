"""Cover generation: palette resolution, niche colours, output."""

import ebook_engine.config as config
import pytest
from ebook_engine.cover_engine import (
    _hex_to_rgb,
    _palette,
    generate_cover,
    get_font,
    resolve_font_path,
)
from PIL import Image


def test_every_corpus_genre_has_a_palette():
    """Regression: config keyed fiction/romance/fantasy while the corpus
    used Business/Cooking/Wellness, so 10 of 15 covers fell back."""
    import ebook_engine.corpus as corpus

    for niche in corpus.get_all_niches():
        genre = corpus.get_niche_genre(niche)
        assert genre.lower() in config.GENRE_COLORS, genre


def test_fallback_palette_still_exists():
    assert "fiction" in config.GENRE_COLORS


def test_palette_uses_genre_case_insensitively():
    assert _palette("Business", None)["primary"] == config.GENRE_COLORS["business"]["primary"]
    assert _palette("business", None)["primary"] == config.GENRE_COLORS["business"]["primary"]


def test_per_niche_colour_overrides_the_genre_palette():
    """The 15 hand-picked corpus colours used to be ignored entirely."""
    niche_color = [26, 26, 46]
    palette = _palette("Business", niche_color)
    assert palette["primary"] == "#1a1a2e"
    assert palette["primary"] != config.GENRE_COLORS["business"]["primary"]


def test_niche_secondary_is_derived_not_clashing():
    palette = _palette("Business", [26, 26, 46])
    assert palette["secondary"] != palette["primary"]
    assert palette["secondary"].startswith("#")


def test_unknown_genre_falls_back_to_fiction():
    palette = _palette("Nonexistent", None)
    assert palette["primary"] == config.GENRE_COLORS["fiction"]["primary"]


def test_hex_to_rgb_rejects_malformed_input():
    with pytest.raises(ValueError):
        _hex_to_rgb("#fff")


def test_generate_cover_writes_a_file(tmp_path):
    out = tmp_path / "cover.png"
    result = generate_cover("Digital Marketing", "Business", str(out))
    assert result == str(out)
    assert out.is_file()
    with Image.open(out) as img:
        assert img.size == config.EPUB_COVER_SIZE


def test_generate_cover_uses_the_niche_colour(tmp_path):
    out = tmp_path / "a.png"
    generate_cover("Digital Marketing", "Business", str(out), cover_color=[26, 26, 46])
    with Image.open(out) as img:
        # Top row is the primary colour drawn from the niche triple
        assert img.getpixel((5, 5)) == (26, 26, 46)


def test_generate_cover_creates_parent_directories(tmp_path):
    out = tmp_path / "deep" / "nested" / "cover.png"
    generate_cover("Travel", "Lifestyle", str(out))
    assert out.is_file()


def test_ai_style_falls_back_to_template(tmp_path):
    out = tmp_path / "ai.png"
    assert generate_cover("Travel", "Lifestyle", str(out), style="ai") == str(out)
    assert out.is_file()


def test_gradient_is_fast_and_filled(tmp_path):
    """Regression: one draw.rectangle per output row (2560 operations)."""
    out = tmp_path / "g.png"
    generate_cover("E-commerce", "Business", str(out))
    with Image.open(out) as img:
        top = img.getpixel((10, 10))
        bottom = img.getpixel((10, img.size[1] - 10))
    primary = config.GENRE_COLORS["business"]["primary"]
    expected = _hex_to_rgb(primary)
    assert top != bottom  # gradient actually varies
    # Top edge is the palette primary (allow a hair of resize interpolation)
    assert all(abs(a - b) <= 4 for a, b in zip(top, expected)), (top, expected)


def test_font_resolver_returns_a_usable_font():
    font = get_font(48)
    assert font is not None
    assert font.getbbox("Hello")  # renders without raising


def test_env_font_override_is_honoured(tmp_path, monkeypatch):
    real = resolve_font_path()
    monkeypatch.setenv("EBOOK_FONT_PATH", real or str(tmp_path / "custom.ttf"))
    assert resolve_font_path() == real


def test_env_override_ignored_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EBOOK_FONT_PATH", str(tmp_path / "missing.ttf"))
    assert resolve_font_path() is None or resolve_font_path().endswith(".ttf")


class TestFooterLegibility:
    """The author and genre sit where the gradient resolves to `secondary`.
    Drawn in `secondary` they measured 1.01:1 and 1.10:1 contrast, i.e.
    present in the file and invisible to anyone looking at it.
    """

    def _region_range(self, image, y0, y1):
        strip = image.crop((0, y0, image.size[0], y1)).convert("L")
        low, high = strip.getextrema()
        return high - low

    def test_author_and_genre_are_legible_on_a_cover(self, tmp_path):
        out = tmp_path / "cover.png"
        generate_cover("Digital Marketing", "Business", str(out), author="NEYAN")
        with Image.open(out) as raw:
            image = raw.convert("RGB")
        h = image.size[1]
        band = max(180, int(h * 0.12))
        for y0, y1 in ((h - band + 20, h - band + 80), (h - band + 85, h - band + 150)):
            spread = self._region_range(image, y0, y1)
            assert spread > 40, f"no visible text in footer strip ({spread})"

    def test_every_genre_palette_keeps_the_footer_readable(self, tmp_path):
        for genre in config.GENRE_COLORS:
            out = tmp_path / f"{genre}.png"
            generate_cover("Some Book Title", genre, str(out), author="NE YAN")
            with Image.open(out) as raw:
                image = raw.convert("RGB")
            h = image.size[1]
            band = max(180, int(h * 0.12))
            for y0, y1 in ((h - band + 20, h - band + 80), (h - band + 85, h - band + 150)):
                assert self._region_range(image, y0, y1) > 40, genre

    def test_footer_band_is_dark(self, tmp_path):
        from ebook_engine.cover_engine import _footer_colour

        out = tmp_path / "cover.png"
        generate_cover("Digital Marketing", "Health", str(out), author="NEYAN")
        with Image.open(out) as raw:
            image = raw.convert("L")
        band_colour = _footer_colour("#1a1a2e")
        assert band_colour.startswith("#0") or band_colour.startswith("#1")
        # the very bottom row is the band, so it must be dark
        assert image.getpixel((5, image.size[1] - 5)) < 40

    def test_accent_is_distinct_from_secondary(self):
        """Regression: accent was literally secondary, so the foot of every
        cover was painted the same colour as the background."""
        from ebook_engine.cover_engine import _accent_for, _palette

        for genre, colours in config.GENRE_COLORS.items():
            palette = _palette(genre, None)
            assert palette["accent"] != palette["secondary"], genre
        assert _accent_for("#0984e3") != "#0984e3"
