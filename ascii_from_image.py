#!/usr/bin/env python3
"""Turn a photo into the ASCII art block used on the left of the profile card.

    pip install Pillow
    python3 ascii_from_image.py foto.jpg --width 44 -o ascii_art.txt

Portraits work best when the subject is cropped tight and the background is
plain. Try --invert if the result looks like a photo negative, and --contrast
to push the shading further apart.
"""

import argparse
import sys

try:
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:
    sys.exit("Pillow fehlt. Installieren mit:  pip install Pillow")

# Dark to light. The card draws these in light grey on a dark background, so a
# denser glyph reads as a brighter pixel.
RAMP = " .:-=+*#%@"

# A character cell is roughly twice as tall as it is wide.
CELL_ASPECT = 0.5


def to_ascii(path, width, invert, contrast, ramp):
    image = Image.open(path)

    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        backdrop = Image.new("RGBA", image.size, (0, 0, 0, 255))
        image = Image.alpha_composite(backdrop, image)

    image = image.convert("L")
    image = ImageOps.autocontrast(image, cutoff=2)
    if contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    if invert:
        image = ImageOps.invert(image)

    height = max(1, round(width * image.height / image.width * CELL_ASPECT))
    image = image.resize((width, height), Image.LANCZOS)

    pixels = image.load()
    scale = len(ramp) - 1
    lines = []
    for y in range(height):
        row = "".join(ramp[round(pixels[x, y] / 255 * scale)] for x in range(width))
        lines.append(row.rstrip())

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        sys.exit("Ergebnis ist leer - Bild zu dunkel? Versuch --invert oder --contrast 1.5")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="Pfad zum Foto (jpg, png, ...)")
    parser.add_argument("-w", "--width", type=int, default=44, help="Breite in Zeichen (Standard: 44)")
    parser.add_argument("-o", "--output", default="ascii_art.txt", help="Zieldatei (Standard: ascii_art.txt)")
    parser.add_argument("--invert", action="store_true", help="Helligkeit umkehren")
    parser.add_argument("--contrast", type=float, default=1.0, help="Kontrastfaktor, z.B. 1.4")
    parser.add_argument("--ramp", default=RAMP, help="Zeichen von dunkel nach hell")
    args = parser.parse_args()

    art = to_ascii(args.image, args.width, args.invert, args.contrast, args.ramp)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(art + "\n")

    lines = art.split("\n")
    print(art)
    print(f"\n-> {args.output}: {len(lines)} Zeilen, {max(len(l) for l in lines)} Zeichen breit", file=sys.stderr)


if __name__ == "__main__":
    main()
