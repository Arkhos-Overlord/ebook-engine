"""Path resolution: everything must stay inside the project directory."""

from pathlib import Path

import ebook_engine.config as config

PROJECT = Path(__file__).resolve().parent.parent


def test_base_dir_is_the_project_not_its_parent():
    """Regression: BASE_DIR used to be Path(__file__).parent.parent, which
    pointed one level too high and dumped output/ and catalog.db into the
    workspace root instead of ebook_engine/."""
    assert config.BASE_DIR == PROJECT
    assert config.BASE_DIR.name == "ebook_engine"


def test_all_paths_live_inside_the_project():
    for path in (
        config.OUTPUT_DIR,
        config.CONFIG_DIR,
        config.TEMPLATES_DIR,
        config.DB_PATH,
    ):
        assert PROJECT in path.resolve().parents or path.parent.resolve() == (PROJECT), (
            f"{path} escaped the project"
        )


def test_db_lives_in_state_not_config():
    """Regression: the DB directory is named config/, which collides with the
    module config.py and shadows it as a namespace package."""
    assert config.CONFIG_DIR.name == "state"
    assert config.DB_PATH == config.CONFIG_DIR / "catalog.db"
    assert config.CONFIG_DIR.parent == config.BASE_DIR


def test_removed_constants_are_gone():
    for name in ("CACHE_DIR", "ENV_PATH", "EPUB_THUMBNAIL_SIZE"):
        assert not hasattr(config, name), f"{name} should have been removed"


def test_ensure_dirs_creates_only_output_and_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "state")
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "state").exists()
    config.ensure_dirs()
    assert (tmp_path / "output").is_dir()
    assert (tmp_path / "state").is_dir()


def test_ensure_dirs_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "state")
    config.ensure_dirs()
    config.ensure_dirs()
    assert (tmp_path / "output").is_dir()


def test_genre_colors_cover_every_real_genre():
    """All 9 corpus genres must resolve; only unknown ones fall back."""
    from ebook_engine.corpus import NICHE_CONTENT

    corpus_genres = {d["genre"] for d in NICHE_CONTENT.values()}
    assert corpus_genres == {
        "Business",
        "Cooking",
        "Creative",
        "Finance",
        "Health",
        "Lifestyle",
        "Self-Help",
        "Technical",
        "Wellness",
    }
    for genre in corpus_genres:
        assert genre.lower() in config.GENRE_COLORS, genre
    assert "fiction" in config.GENRE_COLORS  # fallback


def test_pricing_has_three_tiers():
    assert set(config.PRICING) == {"basic", "standard", "premium"}
    for tier in config.PRICING.values():
        assert tier["price_inr"] > 0
        assert tier["price_usd"] > 0
