import re
import unittest
import zlib

from netbox_trace_print.layout import Engine, LayoutSpec, render
from netbox_trace_print.pdf.paper import CHOICES, PAPER_MM, parse_choice
from netbox_trace_print.selection import apply_selection
from tests import sample


def content(pdf):
    """All page content of a PDF, decompressed."""
    out = b""
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            out += zlib.decompress(m.group(1))
        except zlib.error:
            pass
    return out.decode("latin-1")


def chromatic(text):
    """Colour operators whose red, green and blue differ, i.e. real colour rather than grey."""
    ops = re.findall(r"(-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+) (?:RG|rg)\b", text)
    return [op for op in ops if len(set(op)) > 1]


class PaperChoiceTests(unittest.TestCase):
    def test_every_paper_comes_in_colour_and_black_and_white(self):
        self.assertEqual(len(CHOICES), 2 * len(PAPER_MM))
        self.assertIn(("A4", "A4 (Color)"), CHOICES)
        self.assertIn(("A4:bw", "A4 (B/W)"), CHOICES)

    def test_a_choice_is_a_paper_and_a_colour_mode(self):
        self.assertEqual(parse_choice("A4"), ("A4", True))
        self.assertEqual(parse_choice("A3:bw"), ("A3", False))
        self.assertEqual(parse_choice("Tabloid:bw"), ("Tabloid", False))
        for value, _label in CHOICES:
            paper, _color = parse_choice(value)
            self.assertIn(paper, PAPER_MM)


class ColourModeTests(unittest.TestCase):
    def test_colour_prints_coloured_cables_and_bw_prints_only_grey(self):
        doc = sample.long_trace(11)
        colour, bw = (content(render(doc, LayoutSpec(color=c))[0]) for c in (True, False))
        self.assertTrue(chromatic(colour))
        self.assertEqual(chromatic(bw), [])
        self.assertRegex(bw, r"[0-9.]+ G\b")                  # the cables are still there, as grey tones

    def test_the_same_page_comes_out_either_way(self):
        doc = sample.long_trace(11)
        (_p1, r1), (_p2, r2) = (render(doc, LayoutSpec(color=c)) for c in (True, False))
        self.assertEqual((r1.pages, r1.columns, r1.font_size), (r2.pages, r2.columns, r2.font_size))
        self.assertEqual(len(r1.block_boxes), len(r2.block_boxes))

    def test_grey_keeps_light_and_dark_cables_apart(self):
        spec = LayoutSpec(color=False)
        tone = lambda hex_value: Engine(sample.tiny_trace(), spec)._tone(hex_value)
        self.assertGreater(tone("ffeb3b"), tone("2196f3"))     # yellow is lighter than blue
        self.assertGreater(tone("ffffff"), tone("111111"))
        self.assertAlmostEqual(tone("ffffff"), 1.0, places=2)
        self.assertAlmostEqual(tone("000000"), 0.0, places=2)

    def test_the_colour_fact_is_only_the_name_the_paper_choice_decides_the_line(self):
        doc = sample.long_trace(11)
        nameless = apply_selection(doc, {"cable.type"})                 # Colour not selected: no "Colour: Yellow"
        text = content(render(nameless, LayoutSpec(color=True))[0])
        self.assertTrue(chromatic(text))                                # the line is still coloured
        self.assertEqual(chromatic(content(render(nameless, LayoutSpec(color=False))[0])), [])


if __name__ == "__main__":
    unittest.main()
