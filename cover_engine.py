"""Cover design engine — template-based and AI-generated covers."""

import os
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ebook_engine.config import EPUB_COVER_SIZE, GENRE_COLORS

# Candidate system fonts, checked in order. EBOOK_FONT_PATH overrides all.
FONT_PATHS = [
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]

_GRADIENT_STEPS = 256


def resolve_font_path() -> str | None:
    """Return a usable font file, or None to fall back to the default."""
    override = os.getenv("EBOOK_FONT_PATH")
    if override and Path(override).is_file():
        return override
    for candidate in FONT_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def get_font(size: int = 60) -> ImageFont.ImageFont:
    """Load a font, falling back to PIL's bundled default."""
    path = resolve_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow
        return ImageFont.load_default()


def generate_cover(
    topic: str,
    genre: str,
    output_path: str,
    style: str = "template",
    cover_color: Sequence[int] | None = None,
    author: str = "",
) -> str:
    """Generate an ebook cover.

    Args:
        topic: Book title.
        genre: Genre, used to pick a colour scheme when none is supplied.
        output_path: Where to save the cover image.
        style: "template" or "ai" (ai currently falls back to template).
        cover_color: Optional per-niche RGB triple from the corpus. When
            given it wins over the genre palette, which is how the 15
            hand-picked niche colours finally reach the artwork.
        author: Author name. Amazon's own guidance is that the cover
            should carry both the title and the author, so this is
            rendered along the foot when supplied.

    Returns the path written.
    """
    if style == "ai":
        return _generate_ai_cover(topic, genre, output_path, cover_color, author)
    return _generate_template_cover(topic, genre, output_path, cover_color, author)


def _generate_template_cover(
    topic: str,
    genre: str,
    output_path: str,
    cover_color: Sequence[int] | None = None,
    author: str = "",
) -> str:
    """Render a title-on-gradient cover with the author along the foot."""
    colors = _palette(genre, cover_color)
    width, height = EPUB_COVER_SIZE

    img = _gradient(colors["primary"], colors["secondary"], width, height)
    draw = ImageDraw.Draw(img)

    font_large = get_font(96)
    font_small = get_font(34)

    title_lines = _wrap_text(topic, font_large, width - 160)

    y_offset = height // 3
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_large)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        draw.text((x, y_offset), line, fill="white", font=font_large)
        y_offset += 118

    # A dark band across the foot, as on the hand-authored reference cover.
    # Without it the author and genre are drawn in colours the gradient
    # resolves to underneath, which measured 1.01:1 and 1.10:1 contrast -
    # literally invisible. A band makes them legible on every palette.
    band = max(180, int(height * 0.12))
    draw.rectangle([0, height - band, width, height], fill=_footer_colour(colors["primary"]))

    # Author above the genre label: Amazon expects the cover to carry both.
    if author:
        author_label = author.strip().upper()
        bbox = draw.textbbox((0, 0), author_label, font=font_small)
        draw.text(
            ((width - (bbox[2] - bbox[0])) // 2, height - band + 34),
            author_label,
            fill="white",
            font=font_small,
        )

    label = genre.upper()
    genre_bbox = draw.textbbox((0, 0), label, font=font_small)
    genre_width = genre_bbox[2] - genre_bbox[0]
    genre_y = height - band + (104 if author else 60)
    draw.text(
        ((width - genre_width) // 2, genre_y),
        label,
        fill=colors["accent"],
        font=font_small,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output)
    return str(output)


def _palette(genre: str, cover_color: Sequence[int] | None) -> dict:
    """Resolve {primary, secondary, accent} as hex strings."""
    fallback = GENRE_COLORS.get("fiction")
    colors = GENRE_COLORS.get(str(genre).lower(), fallback)
    primary, secondary = colors["primary"], colors["secondary"]

    if cover_color and len(cover_color) >= 3:
        rgb = tuple(max(0, min(255, int(c))) for c in cover_color[:3])
        primary = "#{:02x}{:02x}{:02x}".format(*rgb)
        # Pair the niche colour with a lightened version of itself so the
        # gradient reads as one considered palette rather than a clash.
        secondary = "#{:02x}{:02x}{:02x}".format(
            *(min(255, int(c + (255 - c) * 0.55)) for c in rgb)
        )

    return {"primary": primary, "secondary": secondary, "accent": _accent_for(secondary)}


def _footer_colour(primary: str) -> str:
    """A near-black drawn from the palette's primary, for the footer band.

    Darkening the primary keeps the band on-palette while guaranteeing the
    white and accent labels above it clear 4.5:1 whatever the genre.
    """
    r, g, b = _hex_to_rgb(primary)
    return f"#{r // 8:02x}{g // 8:02x}{b // 8:02x}"


def _accent_for(secondary: str) -> str:
    """A tint light enough to read against the gradient's lower half.

    The gradient ends on `secondary`, so labelling the author and genre in
    `secondary` itself renders them invisible - measured at 1.01:1 contrast
    on a real cover. Lifting it well clear of the background is what makes
    the foot of the design legible.
    """
    lifted = (int(c + (255 - c) * 0.72) for c in _hex_to_rgb(secondary))
    r, g, b = lifted
    return f"#{r:02x}{g:02x}{b:02x}"


def _gradient(primary: str, secondary: str, width: int, height: int) -> Image.Image:
    """Vertical gradient built from a 1px-wide strip, then scaled up.

    The previous version issued one draw.rectangle per output row — 2560
    canvas operations per cover. A 1px strip plus a single resize does the
    same job with one resample.
    """
    p = _hex_to_rgb(primary)
    s = _hex_to_rgb(secondary)
    strip = Image.new("RGB", (1, _GRADIENT_STEPS))
    strip.putdata(
        [
            tuple(round(p[i] + (s[i] - p[i]) * (step / (_GRADIENT_STEPS - 1))) for i in range(3))
            for step in range(_GRADIENT_STEPS)
        ]
    )
    return strip.resize((width, height), Image.BILINEAR)


def _hex_to_rgb(value: str) -> tuple:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected a 6-digit hex colour, got {value!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _generate_ai_cover(
    topic: str,
    genre: str,
    output_path: str,
    cover_color: Sequence[int] | None = None,
    author: str = "",
) -> str:
    """Placeholder for AI cover generation (DALL-E/Stability)."""
    # TODO: Integrate DALL-E or Stable Diffusion API
    return _generate_template_cover(topic, genre, output_path, cover_color, author)


def _wrap_text(text: str, font, max_width: int) -> list:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = current + " " + word if current else word
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [text]
