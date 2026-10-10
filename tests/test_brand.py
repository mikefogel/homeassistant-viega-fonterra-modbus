"""The integration ships its own brand images (spec.md 12)."""

from pathlib import Path

from PIL import Image

BRAND = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "viega_fonterra_modbus"
    / "brand"
)


def test_icons_have_the_required_sizes_and_transparency():
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        image = Image.open(BRAND / name)
        assert image.format == "PNG", name
        assert image.size == (size, size), name
        assert "A" in image.getbands(), name
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0, f"{name}: corner not transparent"


def test_only_supported_brand_files_are_shipped():
    supported = {
        f"{prefix}{kind}{suffix}.png"
        for prefix in ("", "dark_")
        for kind in ("icon", "logo")
        for suffix in ("", "@2x")
    }
    assert {path.name for path in BRAND.iterdir()} <= supported
