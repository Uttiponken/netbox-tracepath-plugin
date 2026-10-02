"""Paper sizes. All geometry in the PDF code is in points (1/72 inch)."""

MM = 72.0 / 25.4

# name -> (short side, long side) in millimetres
PAPER_MM = {
    "A5": (148.0, 210.0),
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
}

ORIENTATIONS = ("landscape", "portrait")


def page_size(paper="A4", orientation="landscape"):
    """(width, height) in points for a named paper and orientation."""
    short, long_ = PAPER_MM[paper]
    if orientation == "landscape":
        return long_ * MM, short * MM
    if orientation == "portrait":
        return short * MM, long_ * MM
    raise ValueError(f"unknown orientation {orientation!r}")
