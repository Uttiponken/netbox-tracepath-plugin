"""
Scoped prints: limit a collected trace to the part that lies in one site, location or rack.

The full path is always the starting point. A scope keeps the blocks that are in it and replaces everything
outside with an *edge marker*: one chevron at each end of a run of kept blocks, naming the equipment just
outside (and its port, site and rack), with the cable that crosses the border drawn between the marker and the
last block inside. A path that leaves the scope and comes back is printed as separate segments, each on its own
page (the layout engine does that, see `TraceDoc.segments`).

A block is in a scope when it sits in that site, location or rack. Circuits and provider networks have no place
of their own, so they are never in a scope: they show up as the edge marker where the path leaves.

Pure Python, no Django. Run it on the full document, before `selection.apply_selection`: the scope has to be
decided on the real places, and the selection then hides the markers' site and rack if those facts are not
printed.
"""

import copy

from .model import Block, Link, PortRow, Segment

KINDS = (("site", "Site"), ("location", "Location"), ("rack", "Rack"))
EDGE_KINDS = ("edge-in", "edge-out")


def key_of(kind, block):
    """The scope value of a block for one kind ('site:Name', 'location:Site|Name', 'rack:Site|Location|Name'),
    or '' if the block has no such place. A location or rack is identified with the places it sits in, since
    names are only unique inside their parent."""
    names = {"site": (block.site,), "location": (block.site, block.location),
             "rack": (block.site, block.location, block.rack)}[kind]
    if block.kind in EDGE_KINDS or not names[-1]:
        return ""
    return f"{kind}:" + "|".join(n.replace("|", "/") for n in names)


def parse(value):
    """'rack:Site|Location|Rack' -> ('rack', ['Site', 'Location', 'Rack']); (None, []) for anything else."""
    kind, _sep, rest = str(value or "").partition(":")
    if kind not in dict(KINDS) or not rest:
        return None, []
    return kind, rest.split("|")


def label_of(value):
    """How a scope is named in the dropdown: 'Rack: Nordfiber Stockholm DC › Telecom Room › STO-TR-01'."""
    kind, names = parse(value)
    return f"{dict(KINDS)[kind]}: " + " › ".join(n for n in names if n) if kind else ""


def scopes_of(doc):
    """The scopes a trace can be limited to, as {'value', 'kind', 'label', 'blocks'} in the order the path
    meets them, sites first, then locations, then racks. A scope that holds every block is no scope at all
    and is left out."""
    total = len(doc.blocks)
    found = {}
    for block in doc.blocks:
        for kind, _label in KINDS:
            value = key_of(kind, block)
            if value:
                found.setdefault((kind, value), 0)
                found[(kind, value)] += 1
    order = {kind: i for i, (kind, _l) in enumerate(KINDS)}
    out = [{"value": value, "kind": kind, "label": label_of(value), "blocks": n}
           for (kind, value), n in found.items() if 0 < n < total]
    return sorted(out, key=lambda s: order[s["kind"]])      # stable: first met stays first


def _edge(direction, kind, name, neighbour):
    """The marker for the equipment just outside the scope. `direction` 'in': the path enters the scope from the
    neighbour (the block before); 'out': it leaves to the neighbour (the block after)."""
    if direction == "in":
        port = neighbour.ports[-1].out_name if neighbour.ports else ""
        caption, row = f"Enters {kind} {name}", PortRow(out_name=port)
    else:
        port = neighbour.ports[0].in_name if neighbour.ports else ""
        caption, row = f"Leaves {kind} {name}", PortRow(in_name=port)
    return Block(title=neighbour.title, subtitle=caption, kind=f"edge-{direction}", ports=[row],
                 site=neighbour.site, location=neighbour.location, rack=neighbour.rack)


def apply_scope(doc, value):
    """A copy of `doc` limited to the scope `value`; `doc` itself if the value is not a scope of this trace."""
    kind, names = parse(value)
    if kind is None:
        return doc
    flags = [key_of(kind, b) == value for b in doc.blocks]
    if not any(flags):
        return doc
    doc = copy.deepcopy(doc)
    total, kind_word, name = len(doc.blocks), kind, names[-1]

    runs, i = [], 0
    while i < total:
        if flags[i]:
            j = i
            while j + 1 < total and flags[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1

    blocks, links, segments = [], [], []
    for a, b in runs:
        seq = []                                    # (block, link to the next block of the segment)
        if a > 0:
            seq.append((_edge("in", kind_word, name, doc.blocks[a - 1]), doc.links[a - 1]))
        for j in range(a, b + 1):
            seq.append((doc.blocks[j], doc.links[j] if j < total - 1 else None))
        if b < total - 1:
            seq.append((_edge("out", kind_word, name, doc.blocks[b + 1]), None))
        if segments:
            links.append(Link([]))                  # nothing connects two segments
        segments.append(Segment(len(blocks), len(blocks) + len(seq) - 1))
        blocks += [blk for blk, _l in seq]
        links += [lk for _blk, lk in seq[:-1]]

    shown_cables = sum(len(lk.cables) for lk in links)
    all_cables = sum(len(lk.cables) for lk in doc.links)
    inside = sum(flags)
    parents = " › ".join(n for n in names[:-1] if n)
    doc.scope = f"Scope: {dict(KINDS)[kind]} {name}"
    line = (doc.scope + (f" in {parents}" if parents else "")
            + f" · {inside} of {total} blocks · {shown_cables} of {all_cables} cables shown"
            + (f" · {len(segments)} segments" if len(segments) > 1 else ""))
    doc.blocks, doc.links, doc.segments = blocks, links, segments
    if doc.summary_items:
        doc.summary_items.insert(1, ("", line))     # no key: the scope is the user's own choice, always printed
        doc.summary = [text for _key, text in doc.summary_items]
    else:
        doc.summary.insert(min(1, len(doc.summary)), line)
    if len(segments) > 1:
        doc.notes.append(f"The path leaves the scope and comes back: it is printed as {len(segments)} segments, "
                         f"each on its own page.")
    return doc
