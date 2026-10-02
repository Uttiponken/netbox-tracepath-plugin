"""The bundled fonts, loaded once per process."""

import os
from functools import lru_cache

from .ttf import TTFont

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

# name -> file. "cond" is the narrower cut that fits more text in a block.
FONT_FILES = {
    "sans": "DejaVuSans.ttf",
    "sans-bold": "DejaVuSans-Bold.ttf",
    "cond": "DejaVuSansCondensed.ttf",
    "cond-bold": "DejaVuSansCondensed-Bold.ttf",
}


@lru_cache(maxsize=None)
def load_font(name):
    with open(os.path.join(FONT_DIR, FONT_FILES[name]), "rb") as f:
        return TTFont(f.read())
