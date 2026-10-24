import unittest

from netbox_tracepath_plugin.fields import ALL_KEYS, GROUPS, LABELS, PROFILES, group_of
from netbox_tracepath_plugin.layout import LayoutSpec, render
from netbox_tracepath_plugin.model import Block, Cable, Field, Link, PortRow, TraceDoc
from netbox_tracepath_plugin.selection import apply_selection


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
        d.blocks[0].site, d.blocks[0].location, d.blocks[0].rack = "Stockholm", "Colo Hall", "DC1-CH-01"
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

    def test_unselected_colour_hides_the_name_but_not_the_line(self):
        # whether the line and swatch are coloured is the paper choice (colour or B/W), not a fact
        out = apply_selection(doc(), {"cable.type"})
        self.assertEqual((out.links[0].cables[0].color_name, out.links[0].cables[0].color_hex), ("", "ffeb3b"))
        kept = apply_selection(doc(), {"cable.colour"}).links[0].cables[0]
        self.assertEqual((kept.color_name, kept.color_hex), ("Yellow", "ffeb3b"))

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


class PluginGroupTests(unittest.TestCase):
    def test_plugin_groups_are_only_added_when_asked_for(self):
        from netbox_tracepath_plugin.fields import GROUPS as CORE, PLUGIN_GROUPS, PLUGIN_KEYS, groups
        self.assertEqual(groups(), CORE)
        self.assertEqual([g[0] for g in groups(("fms", "wdm"))][-2:], ["fms", "wdm"])
        self.assertEqual(groups(("nope",)), CORE)
        self.assertFalse(set(PLUGIN_KEYS) & set(ALL_KEYS))
        self.assertEqual(len(PLUGIN_KEYS), len(set(PLUGIN_KEYS)))
        for name, (group, label, items) in PLUGIN_GROUPS.items():
            self.assertTrue(all(k.startswith(group + ".") for k, _l in items), name)

    def test_the_keys_the_migrations_add_all_exist_in_the_catalogue(self):
        import importlib.util
        from netbox_tracepath_plugin.fields import PLUGIN_KEYS
        added = set()
        for number, file in (("m3", "0003_plugin_facts_in_profiles"), ("m4", "0004_strand_and_circuit_facts")):
            spec = importlib.util.spec_from_file_location(number, f"netbox_tracepath_plugin/migrations/{file}.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name, keys in module.ADD.items():
                self.assertFalse(set(keys) - set(PLUGIN_KEYS), f"{name}: {set(keys) - set(PLUGIN_KEYS)}")
            self.assertNotIn("Customer-safe", module.ADD)
            added |= set(module.ADD["Full information"])
        self.assertEqual(added, set(PLUGIN_KEYS))      # "Full information" has every plugin fact


class FiberColourTests(unittest.TestCase):
    def test_strand_colours_get_their_fiber_colour_names(self):
        from netbox_tracepath_plugin.integrations.fms import colour_name
        din = {"ff0000": "red", "00ff00": "green", "0000ff": "blue", "ffff00": "yellow", "ffffff": "white",
               "708090": "grey", "8b4513": "brown", "ee82ee": "violet", "00ffff": "turquoise", "000000": "black",
               "ff8000": "orange", "ff69b4": "pink"}
        for value, name in din.items():
            self.assertEqual(colour_name(value), name)
        self.assertEqual(colour_name("#FF0000"), "red")
        self.assertEqual(colour_name("fe0101"), "red")          # the nearest fiber colour
        self.assertEqual(colour_name(""), "")
        self.assertEqual(colour_name("xyz"), "#xyz")

    def test_strands_are_listed_with_tube_fiber_and_colour(self):
        from types import SimpleNamespace as S
        from netbox_tracepath_plugin.integrations.fms import strand_text
        self.assertEqual(strand_text([S(name="Tube 1-F3", color="0000ff"), S(name="Tube 1-F4", color="ffff00")]),
                         "Tube 1-F3 (blue), Tube 1-F4 (yellow)")
        self.assertEqual(strand_text([S(name="Tube 2-F1", color="")]), "Tube 2-F1")
        self.assertEqual(strand_text([]), "")
