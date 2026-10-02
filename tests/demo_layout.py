"""Writes the layout demo PDFs to out/. Run: python -m tests.demo_layout"""

from netbox_trace_print.layout import LayoutSpec, render
from tests.sample import long_trace

CASES = [("A4", "landscape", 11), ("A4", "portrait", 11), ("A3", "landscape", 11), ("Letter", "landscape", 11)]

if __name__ == "__main__":
    for paper, orient, n in CASES:
        pdf, report = render(long_trace(n), LayoutSpec(paper=paper, orientation=orient))
        name = f"out/layout-{paper.lower()}-{orient}.pdf"
        open(name, "wb").write(pdf)
        print(name, f"pages={report.pages} columns={report.columns} font={report.font_size} fits={report.fits}")
