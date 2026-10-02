import unittest

from netbox_trace_print.layout import LayoutSpec, render
from netbox_trace_print.pdf.paper import MM, PAPER_MM, page_size
from tests import sample

TRACES = {
    "single": sample.single_block,
    "tiny": sample.tiny_trace,
    "note": lambda: sample.long_trace(7),
    "long": lambda: sample.long_trace(11),
    "hostile": sample.hostile_trace,
}
EPS = 0.5


def combos():
    for paper in PAPER_MM:
        for orientation in ("landscape", "portrait"):
            for name in TRACES:
                yield paper, orientation, name


class FitTests(unittest.TestCase):
    # The one combination allowed not to fit: a block taller than the whole page at 7 pt.
    # It must say so (rep.fits False and a warning); it may never fail silently.
    EXTREME = {("A5", "landscape", "hostile")}

    def check(self, paper, orientation, name, **spec):
        doc = TRACES[name]()
        pdf, rep = render(doc, LayoutSpec(paper=paper, orientation=orientation, **spec))
        w, h = page_size(paper, orientation)
        margin = 12 * MM
        label = f"{paper} {orientation} {name}"
        self.assertTrue(pdf.startswith(b"%PDF"), label)
        if (paper, orientation, name) in self.EXTREME:
            self.assertTrue(rep.fits or rep.warnings, f"{label}: does not fit and does not say so")
            return rep
        self.assertTrue(rep.fits, f"{label}: {rep.warnings}")
        self.assertGreaterEqual(rep.font_size, 7.0, label)
        # every text run sits inside the page's content area
        for page, x0, y0, x1, y1 in rep.boxes:
            self.assertGreaterEqual(x0, margin - EPS, f"{label}: text left of margin")
            self.assertLessEqual(x1, w - margin + EPS, f"{label}: text right of margin")
            self.assertGreaterEqual(y0, margin - EPS, f"{label}: text above margin")
            self.assertLessEqual(y1, h - margin + EPS, f"{label}: text below margin")
            self.assertLess(page, rep.pages)
        # text that starts inside a block stays inside it
        for page, bx0, by0, bx1, by1 in rep.block_boxes:
            for p, x0, y0, x1, y1 in rep.boxes:
                if p == page and bx0 <= x0 < bx1 and by0 <= y0 < by1:
                    self.assertLessEqual(x1, bx1 + EPS, f"{label}: text leaves its block on the right")
                    self.assertLessEqual(y1, by1 + EPS, f"{label}: text leaves its block at the bottom")
        # blocks are on the page, rows align
        for page, x0, y0, x1, y1 in rep.block_boxes:
            self.assertGreaterEqual(x0, margin - EPS)
            self.assertLessEqual(x1, w - margin + EPS)
            self.assertLessEqual(y1, h - margin + EPS)
        self.assertEqual(len(rep.block_boxes), len(doc.blocks), label)
        return rep

    def test_every_paper_orientation_and_trace_fits(self):
        for paper, orientation, name in combos():
            with self.subTest(paper=paper, orientation=orientation, trace=name):
                self.check(paper, orientation, name)

    def test_landscape_gets_more_columns_than_portrait(self):
        land = self.check("A4", "landscape", "long")
        port = self.check("A4", "portrait", "long")
        self.assertGreater(land.columns, port.columns)

    def test_larger_paper_gets_more_columns_or_fewer_pages(self):
        a4, a3 = self.check("A4", "landscape", "long"), self.check("A3", "landscape", "long")
        self.assertTrue(a3.columns > a4.columns or a3.pages < a4.pages)

    def test_forced_column_count_is_honoured(self):
        self.assertEqual(self.check("A4", "landscape", "long", columns=2).columns, 2)

    def test_long_trace_continues_on_extra_pages_in_order(self):
        rep = self.check("A4", "landscape", "long")
        self.assertGreater(rep.pages, 1)
        pages = [p for p, *_ in rep.block_boxes]
        self.assertEqual(pages, sorted(pages))

    def test_blocks_in_a_row_share_top_and_height(self):
        rep = self.check("A4", "landscape", "long")
        rows = {}
        for page, x0, y0, x1, y1 in rep.block_boxes:
            rows.setdefault((page, round(y0, 1)), set()).add(round(y1 - y0, 1))
        for key, heights in rows.items():
            self.assertEqual(len(heights), 1, f"row {key} has uneven block heights {heights}")

    def test_blocks_are_a_uniform_grid(self):
        rep = self.check("A3", "landscape", "long")
        widths = {round(x1 - x0, 1) for _, x0, _, x1, _ in rep.block_boxes}
        self.assertEqual(len(widths), 1)

    def test_a_block_too_tall_for_the_paper_is_reported_not_clipped_silently(self):
        rep = self.check("A5", "landscape", "hostile")
        self.assertFalse(rep.fits)
        self.assertIn("taller", rep.warnings[0])

    def test_text_never_smaller_than_the_floor(self):
        rep = self.check("A5", "portrait", "hostile")
        self.assertGreaterEqual(rep.font_size, 7.0)


if __name__ == "__main__":
    unittest.main()
