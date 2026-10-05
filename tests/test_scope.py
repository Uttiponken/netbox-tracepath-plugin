import copy
import unittest

from netbox_tracepath_plugin.fields import ALL_KEYS
from netbox_tracepath_plugin.layout import LayoutSpec, render
from netbox_tracepath_plugin.pdf.paper import MM, page_size
from netbox_tracepath_plugin.scope import apply_scope, label_of, parse, scopes_of
from netbox_tracepath_plugin.selection import apply_selection
from tests import sample

EPS = 0.5
A = "site:Site A"


def trace(sites):
    """The 11-block sample with its blocks put in the given sites (one letter per block)."""
    doc = sample.long_trace(11)
    doc.summary_items = list(zip(("doc.route", "doc.summary"), doc.summary))
    for block, letter in zip(doc.blocks, sites):
        block.site = f"Site {letter}"
        block.location, block.rack = f"Room {letter}", f"RACK-{letter}-{block.rack[-2:]}"
    return doc


# blocks 0-1, 4-5 and 8-10 are in site A; the path leaves it twice and comes back twice
RETURNING = "AABBAACCAAA"


class ScopeFunctionTests(unittest.TestCase):
    def test_a_scope_that_holds_every_block_is_not_offered(self):
        found = scopes_of(sample.long_trace(11))                  # one site, one room, three racks
        self.assertEqual([s["kind"] for s in found], ["rack"] * 3)
        self.assertEqual([s["blocks"] for s in found], [4, 4, 3])
        self.assertEqual(found[0]["label"], "Rack: Nordfiber Stockholm DC › Telecom Room › STO-TR-01")

    def test_sites_come_before_locations_before_racks_in_the_order_the_path_meets_them(self):
        found = scopes_of(trace("AABBAACCAAA"))
        self.assertEqual([s["label"] for s in found if s["kind"] == "site"],
                         ["Site: Site A", "Site: Site B", "Site: Site C"])
        kinds = [s["kind"] for s in found]
        self.assertEqual(kinds, sorted(kinds, key=["site", "location", "rack"].index))

    def test_values_round_trip_and_junk_is_refused(self):
        self.assertEqual(parse("rack:S|L|R"), ("rack", ["S", "L", "R"]))
        self.assertEqual(label_of("location:S|L"), "Location: S › L")
        for junk in ("", None, "site:", "nope:x", "rack"):
            self.assertEqual(parse(junk), (None, []))
        doc = trace(RETURNING)
        self.assertIs(apply_scope(doc, "nope:x"), doc)
        self.assertIs(apply_scope(doc, "site:Somewhere else"), doc)

    def test_a_returning_path_becomes_segments_with_edge_markers(self):
        doc = trace(RETURNING)
        out = apply_scope(doc, A)
        self.assertEqual(len(doc.blocks), 11)                      # the original is not touched
        self.assertEqual(len(out.links), len(out.blocks) - 1)
        self.assertEqual([(s.first, s.last) for s in out.segments], [(0, 2), (3, 6), (7, 10)])
        kinds = [b.kind for b in out.blocks]
        self.assertEqual([i for i, k in enumerate(kinds) if k == "edge-out"], [2, 6])
        self.assertEqual([i for i, k in enumerate(kinds) if k == "edge-in"], [3, 7])
        self.assertEqual(out.scope, "Scope: Site Site A")
        self.assertTrue(any("7 of 11 blocks" in line and "3 segments" in line for line in out.summary), out.summary)
        self.assertTrue(any("3 segments" in n for n in out.notes))

    def test_an_edge_marker_names_the_equipment_just_outside_and_its_port(self):
        doc = trace(RETURNING)
        out = apply_scope(doc, A)
        leave, enter = out.blocks[2], out.blocks[3]
        self.assertEqual((leave.title, leave.subtitle), (doc.blocks[2].title, "Leaves site Site A"))
        self.assertEqual(leave.ports[0].in_name, doc.blocks[2].ports[0].in_name)
        self.assertEqual((enter.title, enter.subtitle), (doc.blocks[3].title, "Enters site Site A"))
        self.assertEqual(enter.ports[0].out_name, doc.blocks[3].ports[-1].out_name)
        self.assertEqual((leave.site, leave.rack), (doc.blocks[2].site, doc.blocks[2].rack))

    def test_the_cable_that_crosses_the_border_stays_and_nothing_joins_two_segments(self):
        doc = trace(RETURNING)
        out = apply_scope(doc, A)
        self.assertEqual(out.links[1].cables[0].title, doc.links[1].cables[0].title)      # block 1 to the marker
        self.assertEqual(out.links[3].cables[0].title, doc.links[3].cables[0].title)      # marker to block 4
        self.assertEqual(out.links[2].cables, [])                                       # between two segments
        self.assertTrue(any("8 of 10 cables shown" in line for line in out.summary), out.summary)

    def test_a_circuit_has_no_place_so_it_is_never_in_a_scope(self):
        doc = sample.hostile_trace()
        out = apply_scope(doc, "site:Nordfiber Stockholm DC")
        self.assertEqual([b.kind for b in out.blocks][-2:], ["device", "edge-out"])
        self.assertEqual(out.blocks[-1].title, "Circuit NF-BRG-0001")
        self.assertEqual(len(out.segments), 1)

    def test_a_scope_that_covers_everything_is_one_segment_without_markers(self):
        out = apply_scope(sample.long_trace(11), "site:Nordfiber Stockholm DC")
        self.assertEqual([(s.first, s.last) for s in out.segments], [(0, 10)])
        self.assertFalse([b for b in out.blocks if b.kind.startswith("edge")])

    def test_a_scope_at_one_end_has_one_marker(self):
        out = apply_scope(trace("AAAAAAAAABB"), A)
        self.assertEqual([b.kind for b in out.blocks].count("edge-out"), 1)
        self.assertEqual([b.kind for b in out.blocks].count("edge-in"), 0)
        out = apply_scope(trace("BBAAAAAAAAA"), A)
        self.assertEqual([b.kind for b in out.blocks].count("edge-in"), 1)


class ScopeLayoutTests(unittest.TestCase):
    def render(self, sites=RETURNING, paper="A4", orientation="landscape", **spec):
        doc = apply_scope(trace(sites), A)
        pdf, rep = render(doc, LayoutSpec(paper=paper, orientation=orientation, **spec))
        self.assertTrue(pdf.startswith(b"%PDF"))
        return doc, rep

    def test_every_segment_starts_on_a_new_page(self):
        _doc, rep = self.render()
        self.assertEqual(rep.pages, 3)
        self.assertEqual(rep.page_segments, [(1, 3), (2, 3), (3, 3)])
        self.assertTrue(rep.fits, rep.warnings)

    def test_the_edge_markers_are_the_ends_of_their_segments(self):
        _doc, rep = self.render()
        got = sorted((page, kind) for page, kind, *_ in rep.chevron_boxes)
        self.assertEqual(got, [(0, "edge-out"), (1, "edge-in"), (1, "edge-out"), (2, "edge-in")])
        for page, kind, x0, y0, x1, y1, text in rep.chevron_boxes:
            self.assertIn("Leaves site Site A" if kind == "edge-out" else "Enters site Site A", text)
            self.assertIn("to " if kind == "edge-out" else "from ", text)

    def test_markers_are_the_first_and_last_cell_of_a_segment(self):
        _doc, rep = self.render()
        for page in range(rep.pages):
            cells = [(round(y0 / 60), x0, "block") for p, x0, y0, x1, y1 in rep.block_boxes if p == page]
            cells += [(round(y0 / 60), x0, kind) for p, kind, x0, y0, x1, y1, _t in rep.chevron_boxes if p == page]
            order = [k for _row, _x, k in sorted(cells)]
            if page > 0:
                self.assertEqual(order[0], "edge-in")
            if page < rep.pages - 1:
                self.assertEqual(order[-1], "edge-out")

    def test_only_blocks_of_the_scope_are_drawn(self):
        doc, rep = self.render()
        self.assertEqual(len(rep.block_boxes), 7)
        self.assertEqual(sum(1 for b in doc.blocks if not b.kind.startswith("edge")), 7)

    def test_everything_stays_on_the_page_and_markers_hold_their_text(self):
        for paper, orientation in (("A4", "landscape"), ("A4", "portrait"), ("A5", "portrait"), ("A3", "landscape")):
            with self.subTest(paper=paper, orientation=orientation):
                _doc, rep = self.render(paper=paper, orientation=orientation)
                w, h = page_size(paper, orientation)
                margin = 12 * MM
                self.assertTrue(rep.fits, rep.warnings)
                for page, x0, y0, x1, y1 in rep.boxes:
                    self.assertGreaterEqual(x0, margin - EPS)
                    self.assertLessEqual(x1, w - margin + EPS)
                    self.assertGreaterEqual(y0, margin - EPS)
                    self.assertLessEqual(y1, h - margin + EPS)
                for page, _kind, x0, y0, x1, y1, _t in rep.chevron_boxes:
                    inside = [b for b in rep.boxes if b[0] == page and x0 <= b[1] and b[3] <= x1 and y0 <= b[2] and b[4] <= y1]
                    self.assertGreaterEqual(len(inside), 3)

    def test_a_long_segment_still_breaks_across_pages_and_ends_with_its_marker(self):
        _doc, rep = self.render(sites="AAAAAAAAAAB", paper="A5", orientation="portrait")
        self.assertGreater(rep.pages, 1)
        self.assertEqual({s for s in rep.page_segments}, {(1, 1)})
        kinds = [k for _p, k, *_ in rep.chevron_boxes]
        self.assertEqual(kinds.count("edge-out"), 1)
        self.assertEqual(kinds.count("in"), rep.pages - 1)             # the page breaks inside the segment
        last_page = [k for p, k, *_ in rep.chevron_boxes if p == rep.pages - 1]
        self.assertIn("edge-out", last_page)

    def test_a_scoped_print_with_one_segment_uses_one_page_per_fit(self):
        doc = apply_scope(trace("BBBAAAABBBB"), A)
        _pdf, rep = render(doc, LayoutSpec())
        self.assertEqual((rep.pages, rep.page_segments), (1, [(1, 1)]))
        self.assertEqual(sorted(k for _p, k, *_ in rep.chevron_boxes), ["edge-in", "edge-out"])

    def test_a_whole_path_print_is_unchanged(self):
        _pdf, rep = render(sample.long_trace(11), LayoutSpec())
        self.assertEqual(set(rep.page_segments), {(1, 1)})
        self.assertFalse([k for _p, k, *_ in rep.chevron_boxes if k.startswith("edge")])


class ScopeSelectionTests(unittest.TestCase):
    def test_the_scope_line_is_always_printed_and_the_other_lines_follow_the_selection(self):
        doc = apply_scope(trace(RETURNING), A)
        none = apply_selection(doc, set())
        self.assertEqual(len(none.summary), 1)
        self.assertTrue(none.summary[0].startswith("Scope: Site Site A"))
        full = apply_selection(doc, set(ALL_KEYS))
        self.assertEqual(len(full.summary), 3)
        self.assertEqual(full.scope, "Scope: Site Site A")
        self.assertEqual(len(full.segments), 3)

    def test_a_hidden_site_or_rack_is_hidden_on_the_edge_markers_too(self):
        doc = apply_scope(trace(RETURNING), A)
        hidden = apply_selection(doc, set(ALL_KEYS) - {"device.site", "device.rack"})
        for block in hidden.blocks:
            self.assertEqual((block.site, block.rack), ("", ""))
        _pdf, rep = render(hidden, LayoutSpec())
        for *_head, text in rep.chevron_boxes:
            self.assertNotIn("Site B", text)
            self.assertNotIn("RACK-", text)
        shown = apply_selection(doc, set(ALL_KEYS))
        _pdf, rep = render(shown, LayoutSpec())
        self.assertTrue(any("Site B" in text for *_head, text in rep.chevron_boxes))

    def test_the_selection_does_not_change_the_scope_of_the_original(self):
        doc = apply_scope(trace(RETURNING), A)
        before = copy.deepcopy(doc)
        apply_selection(doc, set())
        self.assertEqual(doc, before)


if __name__ == "__main__":
    unittest.main()
