"""One-off script: draws the Simple-Info app icon and exports every
size/format the platform installers need. Not part of the app itself and
not run automatically — re-run manually if the icon design ever changes.

Usage: venv/bin/python packaging/icons/generate_icon.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).parent
APP_RESOURCES = OUT_DIR.parent.parent / "src" / "simple_info" / "gui" / "resources"
SIZE = 1024

# An information board: a dark panel with rows of coloured entries (like a
# departures board), with the sun and a cloud peeking over its corner, on a
# deep blue tile beside Simple-Cabin's forest green.
TILE_TOP = (36, 74, 140, 255)
TILE_BOTTOM = (16, 30, 70, 255)
PANEL = (14, 18, 30, 255)
PANEL_EDGE = (60, 70, 96, 255)
ROWS = [(255, 196, 60, 255), (110, 180, 255, 255), (96, 214, 140, 255), (240, 110, 100, 255)]
TEXT = (226, 232, 244, 255)
SUN = (255, 200, 60, 255)
CLOUD = (240, 244, 250, 255)


def draw_icon() -> Image.Image:
    tile = Image.new("RGBA", (SIZE, SIZE))
    td = ImageDraw.Draw(tile)
    for y in range(SIZE):
        t = y / SIZE
        td.line([(0, y), (SIZE, y)], fill=tuple(int(TILE_TOP[i] + (TILE_BOTTOM[i] - TILE_TOP[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (SIZE, SIZE), 0)
    margin = SIZE * 0.06
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin], radius=SIZE * 0.22, fill=255)
    img = tile
    s = SIZE / 100

    # the sun, glowing, behind the board's top-right corner
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([56 * s, 8 * s, 92 * s, 44 * s], fill=(255, 200, 80, 150))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(SIZE * 0.035)))
    d = ImageDraw.Draw(img)
    d.ellipse([64 * s, 16 * s, 84 * s, 36 * s], fill=SUN)

    # the board, with a soft shadow
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([17 * s, 33 * s, 85 * s, 85 * s], radius=6 * s, fill=(0, 0, 0, 140))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(SIZE * 0.02)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([15 * s, 30 * s, 85 * s, 82 * s], radius=6 * s, fill=PANEL, outline=PANEL_EDGE, width=int(1.2 * s))
    # a header line, then four rows: a coloured tag and a line of "text"
    d.rounded_rectangle([21 * s, 36 * s, 56 * s, 40 * s], radius=2 * s, fill=TEXT)
    for i, colour in enumerate(ROWS):
        y = 46 + i * 8.5
        d.rounded_rectangle([21 * s, y * s, 29 * s, (y + 5) * s], radius=1.5 * s, fill=colour)
        d.rounded_rectangle([32 * s, (y + 1) * s, (70 - (i % 2) * 10) * s, (y + 4) * s], radius=1.5 * s, fill=(150, 160, 184, 255))
        d.rounded_rectangle([73 * s, (y + 1) * s, 79 * s, (y + 4) * s], radius=1.5 * s, fill=TEXT)

    # a cloud over the sun's lower edge and the board's corner
    cloud = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cloud)
    for x0, y0, x1, y1 in ((60, 29, 74, 41), (68, 24, 84, 40), (78, 30, 90, 42)):
        cd.ellipse([x0 * s, y0 * s, x1 * s, y1 * s], fill=CLOUD)
    cd.rounded_rectangle([62 * s, 34 * s, 88 * s, 42 * s], radius=4 * s, fill=CLOUD)
    img.alpha_composite(cloud)

    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main() -> None:
    icon = draw_icon()
    master_png = OUT_DIR / "icon.png"
    icon.save(master_png)
    print(f"wrote {master_png}")

    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(APP_RESOURCES / "icon.png")
    print(f"wrote {APP_RESOURCES / 'icon.png'}")

    # Windows .ico (multi-resolution)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = OUT_DIR / "icon.ico"
    icon.save(ico_path, sizes=[(s, s) for s in ico_sizes])
    print(f"wrote {ico_path}")

    # Linux: a few common hicolor sizes as plain PNGs.
    for s in (16, 32, 48, 64, 128, 256, 512):
        icon.resize((s, s), Image.LANCZOS).save(OUT_DIR / f"icon_{s}.png")
    print("wrote icon_16..512.png")

    # macOS .icns: iconutil on a Mac; elsewhere Pillow's own ICNS writer is
    # good enough to commit, so CI on macOS always has a file to use.
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = OUT_DIR / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            icon.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            icon.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_DIR / "icon.icns")],
            check=True,
        )
        for f in iconset.iterdir():
            f.unlink()
        iconset.rmdir()
    else:
        icon.save(OUT_DIR / "icon.icns")
    print(f"wrote {OUT_DIR / 'icon.icns'}")


if __name__ == "__main__":
    main()
