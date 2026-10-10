"""Crop the empty background below a dashboard screenshot."""
import sys

from PIL import Image

for source, target in zip(sys.argv[1::2], sys.argv[2::2]):
    image = Image.open(source).convert("RGB")
    width, height = image.size
    background = image.getpixel((width - 5, height - 5))
    bottom = height
    for y in range(height - 1, 0, -1):
        if any(sum(abs(a - b) for a, b in zip(image.getpixel((x, y)), background)) > 12
               for x in range(0, width, 4)):
            bottom = min(height, y + 24)
            break
    image.crop((0, 0, width, bottom)).save(target, optimize=True)
