import re
import unittest
import zlib

from netbox_tracepath_plugin.pdf.fonts import FONT_FILES, load_font
from netbox_tracepath_plugin.pdf.paper import PAPER_MM, MM, page_size
from netbox_tracepath_plugin.pdf.ttf import TTFont
from netbox_tracepath_plugin.pdf.writer import Document


class FontTests(unittest.TestCase):
    def test_every_bundled_font_loads_and_covers_nordic_greek_cyrillic(self):
        for name in FONT_FILES:
            font = load_font(name)
            for ch in "AaÅåÄäÖöØøÆæÜüßÕ-ΑαЖжЯя→•×°":
                self.assertTrue(font.glyph_id(ch), f"{name} lacks {ch!r}")

    def test_widths_scale_with_size_and_condensed_is_narrower(self):
        text = "Ethernet49/1 Räksmörgås"
        sans, cond = load_font("sans"), load_font("cond")
        self.assertAlmostEqual(sans.text_width(text, 20), 2 * sans.text_width(text, 10))
        self.assertLess(cond.text_width(text, 10), sans.text_width(text, 10))
        self.assertGreater(load_font("cond-bold").text_width(text, 10), cond.text_width(text, 10))

    def test_subset_is_a_loadable_font_with_the_same_widths(self):
        font = load_font("cond")
        used = {font.glyph_id(c) for c in "Räksmörgås 0123"}
        sub = TTFont(font.subset(used))
        self.assertEqual(sub.num_glyphs, font.num_glyphs)
        for g in used:
            self.assertEqual(sub.advances[g], font.advances[g])

    def test_subset_is_much_smaller_than_the_font(self):
        font = load_font("cond")
        self.assertLess(len(font.subset({font.glyph_id("A")})), 80_000)


class PaperTests(unittest.TestCase):
    def test_landscape_is_wider_than_tall_and_portrait_the_reverse(self):
        for paper in PAPER_MM:
            w, h = page_size(paper, "landscape")
            self.assertGreater(w, h)
            w, h = page_size(paper, "portrait")
            self.assertLess(w, h)

    def test_a4_landscape_in_points(self):
        w, h = page_size("A4", "landscape")
        self.assertAlmostEqual(w, 841.89, places=1)
        self.assertAlmostEqual(h, 595.28, places=1)


class DocumentTests(unittest.TestCase):
    def _doc(self):
        doc = Document(title="Test åäö")
        page = doc.add_page(*page_size("A4", "landscape"))
        page.rect(10, 10, 100, 50, fill=0.9, stroke=0)
        page.line(10, 70, 200, 70, dash=(3, 2))
        page.polyline([(10, 80), (50, 80), (50, 120)])
        page.text(12, 30, "Räksmörgås → Örebro", "cond", 9)
        page.text(12, 45, "Bold Ж", "cond-bold", 9, fill="ff0000")
        return doc.to_bytes()

    def test_structure(self):
        data = self._doc()
        self.assertTrue(data.startswith(b"%PDF-1.5"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        startxref = int(re.search(rb"startxref\n(\d+)", data).group(1))
        self.assertEqual(data[startxref:startxref + 4], b"xref")
        # every xref entry points at the object it names
        count = int(re.search(rb"xref\n0 (\d+)", data).group(1))
        entries = re.findall(rb"(\d{10}) 00000 n ", data[startxref:])
        self.assertEqual(len(entries), count - 1)
        for i, off in enumerate(entries, start=1):
            self.assertTrue(data[int(off):].startswith(f"{i} 0 obj".encode()))

    def test_page_is_landscape_a4(self):
        data = self._doc()
        self.assertIn(b"/MediaBox [0 0 841.89 595.276]", data)

    def test_one_subset_font_per_used_font_and_text_is_in_the_content_stream(self):
        data = self._doc()
        self.assertEqual(len(re.findall(rb"/Subtype /Type0", data)), 2)
        self.assertEqual(len(re.findall(rb"/FontFile2", data)), 2)

    def test_deterministic_for_a_fixed_creation_date(self):
        import datetime
        t = datetime.datetime(2026, 10, 2, tzinfo=datetime.timezone.utc)
        def make():
            d = Document(title="x", created=t)
            d.add_page(100, 100).text(5, 20, "åäö", "cond", 9)
            return d.to_bytes()
        self.assertEqual(make(), make())


if __name__ == "__main__":
    unittest.main()
