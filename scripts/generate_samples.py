"""Generate synthetic "handwritten" sample images for the three demo solutions.

Usage (from the repo root):
    backend\\.venv\\Scripts\\python scripts\\generate_samples.py

Writes PNGs into examples/handwritten_samples/. Uses a handwriting-style font
when one is available (Segoe Print on Windows) and adds per-character jitter on
ruled paper. These are stand-ins for real photos; real photos can replace them.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "examples" / "handwritten_samples"

DEMOS = {
    "demo1_correct_linear": ["2x + 5 = 15", "2x = 10", "x = 5"],
    "demo2_first_error": ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"],
    "demo3_lost_root": ["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"],
}

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoepr.ttf",
    "C:/Windows/Fonts/Inkfree.ttf",
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def render_steps(lines: list[str], seed: int = 7, width: int = 1400, line_height: int = 120) -> Image.Image:
    rng = random.Random(seed)
    height = line_height * (len(lines) + 1)
    image = Image.new("RGB", (width, height), (250, 249, 244))
    draw = ImageDraw.Draw(image)
    for y in range(line_height, height, line_height):  # ruled paper
        draw.line([(40, y + 20), (width - 40, y + 20)], fill=(200, 215, 235), width=2)
    font = _font(64)
    ink = (28, 40, 90)
    for row, text in enumerate(lines):
        x = 90 + rng.randint(-10, 10)
        baseline = line_height * (row + 1) - 50
        for ch in text:
            glyph = Image.new("RGBA", (110, 120), (0, 0, 0, 0))
            ImageDraw.Draw(glyph).text((15, 10), ch, font=font, fill=ink)
            glyph = glyph.rotate(rng.uniform(-6, 6), resample=Image.BICUBIC)
            image.paste(glyph, (int(x), baseline + rng.randint(-5, 5) - 20), glyph)
            x += draw.textlength(ch, font=font) * rng.uniform(0.95, 1.08) + (6 if ch == " " else 1)
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, lines) in enumerate(DEMOS.items()):
        path = OUT / f"{name}.png"
        render_steps(lines, seed=i + 1).save(path, optimize=True)
        print(f"wrote {path.relative_to(OUT.parents[1])}")


if __name__ == "__main__":
    main()
