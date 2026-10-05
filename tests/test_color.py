import re
import unittest
import zlib

from netbox_tracepath_plugin.layout import Engine, HEADER_FILL, LayoutSpec, SOFT, WHITE_BELOW, WHITE_BELOW_BW, _luminance, ink_for, render
from netbox_tracepath_plugin.pdf.paper import CHOICES, PAPER_MM, parse_choice
from netbox_tracepath_plugin.selection import apply_selection
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


NETBOX_COLOURS = ["aa1409", "f44336", "e91e63", "ffe4e1", "ff66ff", "9c27b0", "673ab7", "3f51b5", "2196f3", "03a9f4", "00bcd4",
                  "009688", "00ffff", "2f6a31", "4caf50", "8bc34a", "cddc39", "ffeb3b", "ffc107", "ff9800", "ff5722", "795548",
                  "c0c0c0", "9e9e9e", "607d8b", "111111", "ffffff"]


def rgb(hex_value):
    return tuple(int(hex_value[i:i + 2], 16) / 255 for i in (0, 2, 4))


class HeaderColourTests(unittest.TestCase):
    """The equipment's NetBox colour (its role) as the background of the block header."""

    def coloured(self, colours):
        doc = sample.long_trace(11)
        for link in doc.links:
            for cable in link.cables:
                cable.color_hex = cable.color_name = ""                 # so only the headers carry colour
        for block, colour in zip(doc.blocks, colours * 11):
            block.color_hex = colour
        return doc

    def test_white_text_on_dark_and_medium_dark_backgrounds_black_on_lighter_ones(self):
        self.assertEqual(WHITE_BELOW, 0.30)
        white = {"111111", "aa1409", "673ab7", "3f51b5", "795548", "2f6a31", "9c27b0",      # dark
                 "607d8b", "e91e63", "f44336", "009688", "ff5722", "2196f3"}                  # medium dark
        for colour in NETBOX_COLOURS:
            self.assertEqual(ink_for(rgb(colour)), 1 if colour in white else 0, colour)
        self.assertEqual((ink_for((0, 0, 0)), ink_for((1, 1, 1))), (1, 0))

    def test_black_and_white_uses_the_stricter_limit_on_the_grey_the_header_prints_in(self):
        self.assertEqual(WHITE_BELOW_BW, 0.18)
        grey = lambda colour: sum(w * v for w, v in zip((0.299, 0.587, 0.114), rgb(colour)))
        engine = Engine(sample.tiny_trace(), LayoutSpec(color=False))
        white = set()
        for colour in NETBOX_COLOURS:
            fill, title, sub = engine._header_style(colour)
            self.assertAlmostEqual(fill, grey(colour), places=6)
            self.assertEqual(title, sub)
            y = _luminance((fill, fill, fill))
            ink_y = 1.0 if title else 0.0
            self.assertGreaterEqual((max(y, ink_y) + 0.05) / (min(y, ink_y) + 0.05), 4.5, colour)    # 4.5:1 on every header
            if title:
                white.add(colour)
        self.assertEqual(white, {"111111", "aa1409", "673ab7", "3f51b5", "795548", "2f6a31", "9c27b0", "e91e63", "009688"})
        # the mid-greys that colour mode gives white text keep black text here
        for colour in ("607d8b", "f44336", "ff5722", "2196f3", "4caf50", "03a9f4", "00bcd4"):
            self.assertEqual(engine._header_style(colour)[1], 0, colour)

    def test_the_text_stays_readable_on_every_colour_netbox_offers(self):
        for colour in NETBOX_COLOURS:
            y = _luminance(rgb(colour))
            ink_y = 1.0 if ink_for(rgb(colour)) else 0.0
            ratio = (max(y, ink_y) + 0.05) / (min(y, ink_y) + 0.05)
            self.assertGreaterEqual(ratio, 3.0, colour)           # large-text contrast at the very least

    def test_a_header_without_a_colour_keeps_the_usual_grey(self):
        engine = Engine(sample.tiny_trace(), LayoutSpec())
        self.assertEqual(engine._header_style(""), (HEADER_FILL, 0, SOFT))

    def test_colour_mode_uses_the_colour_and_bw_mode_its_grey(self):
        doc = sample.tiny_trace()
        fill, title, sub = Engine(doc, LayoutSpec(color=True))._header_style("3f51b5")
        self.assertEqual((fill, title, sub), ("3f51b5", 1, 1))
        fill, title, sub = Engine(doc, LayoutSpec(color=False))._header_style("3f51b5")
        self.assertIsInstance(fill, float)
        self.assertAlmostEqual(fill, (0.299 * 0x3f + 0.587 * 0x51 + 0.114 * 0xb5) / 255, places=3)
        self.assertEqual(title, ink_for((fill, fill, fill), WHITE_BELOW_BW))
        light = Engine(doc, LayoutSpec(color=False))._header_style("ffeb3b")
        self.assertGreater(light[0], fill)                   # yellow is a lighter grey than indigo
        self.assertEqual(light[1], 0)

    def test_the_printout_carries_the_header_colour_only_in_colour_mode(self):
        doc = self.coloured(["3f51b5", "ffeb3b", "4caf50"])
        self.assertTrue(chromatic(content(render(doc, LayoutSpec(color=True))[0])))
        self.assertEqual(chromatic(content(render(doc, LayoutSpec(color=False))[0])), [])
        plain = self.coloured([""])
        self.assertEqual(chromatic(content(render(plain, LayoutSpec(color=True))[0])), [])

    def test_a_coloured_header_changes_nothing_about_the_layout(self):
        (_a, r1), (_b, r2) = (render(d, LayoutSpec()) for d in (self.coloured([""]), self.coloured(["3f51b5"])))
        self.assertEqual((r1.pages, r1.columns, r1.font_size, len(r1.block_boxes)), (r2.pages, r2.columns, r2.font_size, len(r2.block_boxes)))


if __name__ == "__main__":
    unittest.main()
