import unittest

from netbox_trace_print.fields import ALL_KEYS, GROUPS, LABELS, PROFILES, group_of
from netbox_trace_print.layout import LayoutSpec, render
from netbox_trace_print.model import Block, Cable, Field, Link, PortRow, TraceDoc
from netbox_trace_print.selection import apply_selection


def doc():
    block = Block(title="sw-01", subtitle="Switch · Arista", subtitle_key="device.subtitle",
                  ports=[PortRow(in_name="Eth1", in_fields=[Field("Type", "SFP+", "port.type"),
                                                            Field("Label", "uplink", "port.label")])],
                  fields=[Field("Site", "Stockholm", "device.site"), Field("Serial", "X123", "device.serial"),
                          Field("Anonymous", "always", "")])
    cable = Cable(title="cbl-1", color_hex="ffeb3b", color_name="Yellow",
                  fields=[Field("Type", "smf-os2", "cable.type"), Field("Tenant", "Acme", "cable.tenant")])
    return TraceDoc(title="t", blocks=[block, Block(title="sw-02")], links=[Link([cable])],
                    summary=["From a to b", "1 cable"], summary_items=[("doc.route", "From a to b"), ("doc.summary", "1 cable")],
                    footer="Generated x", footer_items=[("doc.generated", "Generated x")])


class CatalogueTests(unittest.TestCase):
    def test_keys_are_unique_and_labelled(self):
        self.assertEqual(len(ALL_KEYS), len(set(ALL_KEYS)))
        self.assertTrue(all(LABELS[k] for k in ALL_KEYS))
        self.assertEqual(group_of("cable.type"), "cable")
        self.assertIsNone(group_of("nope"))

    def test_every_key_sits_under_a_group_named_by_its_prefix(self):
        for group, _label, items in GROUPS:
            for key, _l in items:
                self.assertTrue(key.startswith(group + ".") or (group == "site" and key.startswith(("site.", "network."))),
                                key)

    def test_builtin_profiles_use_only_known_keys_and_the_first_is_everything(self):
        for name, description, keys in PROFILES:
            self.assertTrue(name and description, name)
            self.assertEqual(len(keys), len(set(keys)), f"{name} lists a key twice")
            self.assertFalse(set(keys) - set(ALL_KEYS), f"{name}: unknown {set(keys) - set(ALL_KEYS)}")
        self.assertEqual(PROFILES[0][0], "Full information")
        self.assertEqual(set(PROFILES[0][2]), set(ALL_KEYS))

    def test_customer_safe_hides_the_internal_things(self):
        keys = dict((n, set(k)) for n, _d, k in PROFILES)["Customer-safe"]
        for hidden in ("device.serial", "device.asset_tag", "device.ipv4", "device.rack", "device.position",
                       "device.tenant", "device.comments", "cable.comments", "cable.tenant", "cable.tags",
                       "port.description", "device.description", "doc.generated"):
            self.assertNotIn(hidden, keys)


class SelectionTests(unittest.TestCase):
    def texts(self, d):
        out = [d.title, *d.summary, d.footer]
        for b in d.blocks:
            out += [b.title, b.subtitle] + [f"{f.label}={f.value}" for f in b.fields]
            for r in b.ports:
                out += [r.in_name, r.out_name] + [f.label for f in r.in_fields + r.out_fields]
        for lk in d.links:
            for c in lk.cables:
                out += [c.title, c.color_name] + [f"{f.label}={f.value}" for f in c.fields]
        return " | ".join(out)

    def test_everything_selected_changes_nothing_but_the_footer_label(self):
        d = doc()
        out = apply_selection(d, ALL_KEYS)
        self.assertEqual(out.blocks, d.blocks)
        self.assertEqual(out.summary, d.summary)

    def test_unselected_facts_are_dropped_and_names_always_stay(self):
        out = apply_selection(doc(), {"device.site", "cable.type"})
        text = self.texts(out)
        for gone in ("X123", "uplink", "SFP+", "Acme", "Switch · Arista", "Yellow", "From a to b", "Generated x"):
            self.assertNotIn(gone, text)
        for stays in ("sw-01", "sw-02", "Eth1", "cbl-1", "Stockholm", "smf-os2", "Anonymous=always"):
            self.assertIn(stays, text)

    def test_where_a_block_is_follows_the_selection_so_chevron_markers_cannot_leak_it(self):
        d = doc()
        d.blocks[0].site, d.blocks[0].location, d.blocks[0].rack = "Stockholm", "Colo Hall", "STO-CH-01"
        out = apply_selection(d, {"device.site"}).blocks[0]
        self.assertEqual((out.site, out.location, out.rack), ("Stockholm", "", ""))
        out = apply_selection(d, set()).blocks[0]
        self.assertEqual((out.site, out.location, out.rack), ("", "", ""))

    def test_a_chevron_never_shows_a_rack_that_the_selection_hides(self):
        from tests.sample import long_trace
        d = long_trace(11)
        for b in d.blocks:
            b.site, b.rack = "SITE-X", "RACK-SECRET"
        rep = render(apply_selection(d, {"device.site"}), LayoutSpec(paper="A4", orientation="landscape"))[1]
        self.assertTrue(rep.chevron_boxes)
        for *_head, text in rep.chevron_boxes:
            self.assertIn("SITE-X", text)
            self.assertNotIn("RACK-SECRET", text)

    def test_unselected_colour_also_removes_the_coloured_line(self):
        out = apply_selection(doc(), {"cable.type"})
        self.assertEqual(out.links[0].cables[0].color_hex, "")
        self.assertEqual(apply_selection(doc(), {"cable.colour"}).links[0].cables[0].color_hex, "ffeb3b")

    def test_original_is_not_modified(self):
        d = doc()
        apply_selection(d, set())
        self.assertEqual(len(d.blocks[0].fields), 3)
        self.assertEqual(d.summary, ["From a to b", "1 cable"])

    def test_prepared_for_and_layout_name_are_printed_when_given(self):
        out = apply_selection(doc(), {"doc.generated"}, layout_name="Field technician", prepared_for="J. Smith")
        self.assertEqual(out.summary[0], "Prepared for: J. Smith")
        self.assertIn("Layout: Field technician", out.footer)
        self.assertIn("Generated x", out.footer)

    def test_a_trace_without_footer_items_still_gets_the_layout_label(self):
        d = doc()
        d.footer_items = []
        self.assertIn("Layout: X", apply_selection(d, set(), layout_name="X").footer)

    def test_fewer_fields_make_a_shorter_print(self):
        from tests.sample import long_trace
        d = long_trace(11)
        full = render(d, LayoutSpec())[1]
        for b in d.blocks:                       # the sample's fields carry no keys, so key them like the collector
            for f in b.fields:
                f.key = {"Site": "device.site", "Location": "device.location", "Rack": "device.rack",
                         "Tenant": "device.tenant", "Serial": "device.serial", "Asset tag": "device.asset_tag"}[f.label]
        small = render(apply_selection(d, {"device.site"}), LayoutSpec())[1]
        self.assertLessEqual(small.pages, full.pages)
        self.assertGreaterEqual(small.columns, full.columns)


if __name__ == "__main__":
    unittest.main()
