"""
Writes the sample PDFs for the current release to samples/<version>/.

    python -m tests.demo_layout

The files are named after the layout they show ("full-information" is the first
layout: every field of every block and cable) so they can be discussed by name.
"""

import os

from netbox_tracepath_plugin import __version__
from netbox_tracepath_plugin.layout import LayoutSpec, render
from tests.sample import long_trace

LAYOUT = "full-information"
CASES = [("A4", "landscape"), ("A4", "portrait"), ("A3", "landscape"), ("Letter", "landscape")]

if __name__ == "__main__":
    out_dir = os.path.join("samples", __version__)
    os.makedirs(out_dir, exist_ok=True)
    for paper, orient in CASES:
        pdf, report = render(long_trace(11), LayoutSpec(paper=paper, orientation=orient))
        path = os.path.join(out_dir, f"{LAYOUT}-{paper.lower()}-{orient}.pdf")
        with open(path, "wb") as f:
            f.write(pdf)
        print(path, f"pages={report.pages} columns={report.columns} font={report.font_size} fits={report.fits}")
