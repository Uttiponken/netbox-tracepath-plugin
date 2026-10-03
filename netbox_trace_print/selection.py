"""Applying a selection of catalogue keys to a collected TraceDoc. Pure Python, no Django."""

import copy

FOOTER_SEPARATOR = "  ·  "


def apply_selection(doc, keys, layout_name="", prepared_for=""):
    """A copy of `doc` showing only the facts whose key is in `keys`.

    Fields without a key (names, ports, cables, titles) always stay. `layout_name` and `prepared_for` are
    printed whenever given.
    """
    keys = set(keys)
    doc = copy.deepcopy(doc)

    def keep(fields):
        return [f for f in fields if not f.key or f.key in keys]

    for block in doc.blocks:
        # where a block is also appears on the chevron markers, so it follows the same selection
        for attr, key in (("site", "device.site"), ("location", "device.location"), ("rack", "device.rack")):
            if key not in keys:
                setattr(block, attr, "")
        block.fields = keep(block.fields)
        if block.subtitle_key and block.subtitle_key not in keys:
            block.subtitle = ""
        for row in block.ports:
            row.in_fields, row.out_fields = keep(row.in_fields), keep(row.out_fields)
    for link in doc.links:
        for cable in link.cables:
            cable.fields = keep(cable.fields)
            if "cable.colour" not in keys:
                cable.color_hex = cable.color_name = ""

    if doc.summary_items:
        doc.summary = [text for key, text in doc.summary_items if key in keys]
    if doc.footer_items:
        parts = [text for key, text in doc.footer_items if key in keys]
        if layout_name:
            parts.append(f"Layout: {layout_name}")
        doc.footer = FOOTER_SEPARATOR.join(parts)
    elif layout_name:
        doc.footer = (doc.footer + FOOTER_SEPARATOR if doc.footer else "") + f"Layout: {layout_name}"
    if prepared_for:
        doc.summary.insert(0, f"Prepared for: {prepared_for}")
    return doc
