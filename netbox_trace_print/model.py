"""
What a printed trace is made of, as plain data.

The layout engine consumes these and knows nothing about NetBox or Django, so
it can be tested on its own and so the data collection can change (which
fields, which preset) without touching the drawing.

A trace is a chain: block, link, block, link, ... Following NetBox's own trace
drawing, a block is a parent object (a device, a circuit, a provider network,
a site) together with the ports the path uses on it, and a link is the cable
(or cables, when a path fans out) between two blocks.
"""

from dataclasses import dataclass, field


@dataclass
class Field:
    label: str
    value: str
    key: str = ""      # the catalogue key (fields.py) that decides whether it is printed; "" = always


@dataclass
class PortRow:
    """One pass through a block: where the path arrives (in) and where it leaves (out).

    The first block has only `out`, the last only `in`; a patch panel has both
    (front port in, rear port out). Each side has a name and detail fields.
    """
    in_name: str = ""
    in_fields: list = field(default_factory=list)
    out_name: str = ""
    out_fields: list = field(default_factory=list)


@dataclass
class Block:
    title: str
    subtitle: str = ""
    subtitle_key: str = ""                     # catalogue key for the subtitle; "" = always shown
    kind: str = "device"                       # device | circuit | provider-network | site
    ports: list = field(default_factory=list)  # PortRow
    fields: list = field(default_factory=list)  # object details, shown as an aligned label/value grid
    # Where the block is, as plain names. Not drawn by themselves; used to colour by
    # site / location / rack.
    site: str = ""
    location: str = ""
    rack: str = ""


@dataclass
class Cable:
    title: str
    fields: list = field(default_factory=list)
    color_hex: str = ""        # 'rrggbb' or empty
    color_name: str = ""


@dataclass
class Link:
    cables: list = field(default_factory=list)   # more than one when a path fans out


@dataclass
class TraceDoc:
    title: str
    summary: list = field(default_factory=list)   # header lines under the title (strings)
    blocks: list = field(default_factory=list)
    links: list = field(default_factory=list)     # len(blocks) - 1
    notes: list = field(default_factory=list)     # warnings such as "path is split"
    footer: str = ""
    # The same text as `summary` and `footer`, as (catalogue key, text) so a selection can drop parts.
    summary_items: list = field(default_factory=list)
    footer_items: list = field(default_factory=list)
