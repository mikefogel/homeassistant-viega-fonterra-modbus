"""Example dashboards (spec.md 5a.3): the YAML in the README is exactly the
YAML in docs/dashboards/ that the screenshots are rendered from."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = sorted((ROOT / "docs" / "dashboards").glob("*.yaml"))


def test_three_example_dashboards_exist():
    assert {path.stem for path in DASHBOARDS} == {"standard", "tiles", "button_card"}


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.stem)
def test_dashboard_yaml_is_valid_and_quoted_in_the_readme(path):
    text = path.read_text(encoding="utf-8").rstrip("\n")
    assert yaml.safe_load(text)["views"]
    assert f"```yaml\n{text}\n```" in (ROOT / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.stem)
def test_screenshot_exists_for_every_dashboard(path):
    image = ROOT / "docs" / f"dashboard-{path.stem.replace('_', '-')}.png"
    assert image.exists()
    assert f"({image.relative_to(ROOT).as_posix()})" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_only_the_button_card_example_uses_custom_cards():
    for path in DASHBOARDS:
        uses_custom = "custom:" in path.read_text(encoding="utf-8")
        assert uses_custom == (path.stem == "button_card"), path.name
