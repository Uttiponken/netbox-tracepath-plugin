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
    EXTREME = {("A5", "landscape", "hostile"), ("A5", "portrait", "hostile")}

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
        rep = self.check("A4", "portrait", "hostile")
        self.assertGreaterEqual(rep.font_size, 7.0)


class ChevronTests(FitTests):
    """The markers where a trace continues on another page."""

    def rep(self, **kw):
        return self.check(kw.pop("paper", "A4"), kw.pop("orientation", "landscape"), kw.pop("trace", "long"), **kw)

    def first_block_on(self, rep, page):
        return sum(1 for p, *_ in rep.block_boxes if p < page)

    def test_a_single_page_has_no_markers(self):
        self.assertEqual(self.rep(paper="A3", trace="tiny").chevron_boxes, [])

    def test_one_marker_each_end_of_every_break(self):
        rep = self.rep()
        self.assertGreater(rep.pages, 1)
        self.assertEqual(len(rep.chevron_boxes), 2 * (rep.pages - 1))
        for p in range(rep.pages):
            kinds = sorted(k for pg, k, *_ in rep.chevron_boxes if pg == p)
            want = (["out"] if p < rep.pages - 1 else []) + (["in"] if p > 0 else [])
            self.assertEqual(kinds, sorted(want), f"page {p}")

    def test_markers_say_which_page_and_which_equipment_they_align_to(self):
        doc = sample.long_trace(11)
        rep = self.rep()
        for page, kind, *_box, text in rep.chevron_boxes:
            k = self.first_block_on(rep, page + 1) if kind == "out" else self.first_block_on(rep, page) - 1
            self.assertIn(doc.blocks[k].title, text)
            self.assertIn(f"page {page + 2}" if kind == "out" else f"page {page}", text)
            self.assertIn("Continues on" if kind == "out" else "Continued from", text)

    def test_the_continued_marker_is_the_first_block_and_the_continues_marker_the_last(self):
        rep = self.rep()
        for page in range(rep.pages):
            cells = [(y0, x0, "block") for p, x0, y0, x1, y1 in rep.block_boxes if p == page]
            cells += [(y0, x0, kind) for p, kind, x0, y0, x1, y1, _t in rep.chevron_boxes if p == page]
            # reading order: rows by their top (a chevron is centred, so compare by row, not exact top)
            rows = sorted({round(y0 / 60) for y0, _x, _k in cells})
            first_row = [c for c in cells if round(c[0] / 60) == rows[0]]
            last_row = [c for c in cells if round(c[0] / 60) == rows[-1]]
            ordered = lambda row: [k for _y, _x, k in sorted(row, key=lambda c: c[1])]
            if page > 0:
                self.assertEqual(ordered(first_row)[0], "in", f"page {page}")
            if page < rep.pages - 1:
                self.assertEqual(ordered(last_row)[-1], "out", f"page {page}")

    def test_marker_text_stays_inside_the_marker(self):
        rep = self.rep()
        for page, _kind, x0, y0, x1, y1, _t in rep.chevron_boxes:
            inside = [b for b in rep.boxes if b[0] == page and x0 <= b[1] and b[3] <= x1 and y0 <= b[2] and b[4] <= y1]
            self.assertGreaterEqual(len(inside), 3)

    def test_markers_work_with_a_single_column_and_on_every_paper(self):
        self.rep(columns=1)
        for paper in ("A4", "A3", "Letter", "Legal", "Tabloid"):
            for orientation in ("landscape", "portrait"):
                with self.subTest(paper=paper, orientation=orientation):
                    self.rep(paper=paper, orientation=orientation, trace="note")


if __name__ == "__main__":
    unittest.main()
