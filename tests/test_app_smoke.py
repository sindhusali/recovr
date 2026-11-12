"""Headless click-through: the page renders with sample data and no exception."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    not (ROOT / "data" / "sample_ledger.csv").exists(),
    reason="run scripts/make_sample_data.py first",
)


def test_app_renders_without_error():
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    assert not at.exception
    assert any("Chase these customers first" in s.value for s in at.subheader)


def test_theme_and_assets_exist():
    assert (ROOT / ".streamlit" / "config.toml").exists()
    assert (ROOT / "app" / "static" / "logo.png").exists()
    assert len(list((ROOT / "app" / "static").glob("*.woff2"))) == 3
