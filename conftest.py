"""Shared fixtures for the ebook_engine test suite."""

import sys
from pathlib import Path

import pytest

# The package lives one directory above this file. Add the parent so
# `import ebook_engine.catalog` resolves regardless of where pytest runs.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))


@pytest.fixture()
def temp_catalog(tmp_path, monkeypatch):
    """Point catalog at an isolated throwaway database."""
    import ebook_engine.catalog as catalog
    import ebook_engine.config as config

    monkeypatch.setattr(catalog, "DB_PATH", tmp_path / "catalog.db")
    monkeypatch.setattr(catalog, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "catalog.db")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    return tmp_path / "catalog.db"
