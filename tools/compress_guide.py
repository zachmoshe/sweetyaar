#!/usr/bin/env python3
"""
Shrink the parents' guide PDF for publishing. It stays an ordinary PDF; only the
images inside are re-encoded:

  - anything above 320 dpi is downsampled to 300 dpi (a 0.5 inch icon stored at
    1,970 dpi becomes 156 px instead of 1,024 px);
  - large images are re-encoded as JPEG at quality 85;
  - small PNGs (under 100 KB) are kept exactly as they are, since re-encoding
    them as JPEG made them blurry;
  - text and layout are untouched.

The 19.7 MB guide becomes about 6.3 MB. PyMuPDF is not a project dependency:

    uv run --no-project --with pymupdf python tools/compress_guide.py \\
        app/public/parents_user_guide.pdf            # in place
    uv run --no-project --with pymupdf python tools/compress_guide.py in.pdf out.pdf
"""

import os
import sys

import pymupdf

DPI_THRESHOLD, DPI_TARGET, QUALITY = 320, 300, 85
KEEP_PNG_BELOW = 100_000  # bytes


def position(page_number: int, info: dict) -> tuple:
    """Images keep their page and place, while their object numbers change."""
    return page_number, tuple(round(value) for value in info["bbox"])


def compress(source: str, target: str) -> None:
    original = pymupdf.open(source)
    small = {}
    for number, page in enumerate(original):
        for info in page.get_image_info(xrefs=True):
            image = original.extract_image(info["xref"])
            if image["ext"] == "png" and len(image["image"]) < KEEP_PNG_BELOW:
                small[position(number, info)] = image["image"]

    document = pymupdf.open(source)
    document.rewrite_images(dpi_threshold=DPI_THRESHOLD, dpi_target=DPI_TARGET, quality=QUALITY)
    for number, page in enumerate(document):
        for info in page.get_image_info(xrefs=True):
            key = position(number, info)
            if key in small:
                page.replace_image(info["xref"], stream=small[key])
    temporary = target + ".tmp"
    document.save(temporary, garbage=4, deflate=True, clean=True)
    document.close()
    os.replace(temporary, target)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2
    source = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) == 3 else source
    before = os.path.getsize(source)
    compress(source, target)
    print(f"{source}: {before / 1e6:.2f} MB -> {target}: {os.path.getsize(target) / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
