"""netbox-fms: the fiber-plant record of a cable, the strands a link uses, and fiber circuits."""

from django.apps import apps

from ..model import Field

APP = "netbox_fms"
KINDS = {"fiber-cable": (APP, "fibercable", "Fiber cable (FMS)"),
         "fiber-circuit": (APP, "fibercircuit", "Fiber circuit (FMS)")}

# Fiber colour codes (DIN/IEC 60304 and TIA-598), to name the hex colour netbox-fms stores on a strand.
FIBER_COLOURS = [
    ("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)), ("yellow", (255, 255, 0)),
    ("white", (255, 255, 255)), ("grey", (112, 128, 144)), ("brown", (139, 69, 19)), ("violet", (238, 130, 238)),
    ("turquoise", (0, 255, 255)), ("black", (0, 0, 0)), ("orange", (255, 128, 0)), ("pink", (255, 105, 180)),
]


def installed():
    return apps.is_installed(APP)


def _f(label, value, key):
    value = "" if value is None else str(value).strip()
    return Field(label, value, key) if value else None


def _display(obj, name):
    getter = getattr(obj, f"get_{name}_display", None)
    return getter() if getter else getattr(obj, name, "")


def colour_name(hex_value):
    """The fiber colour closest to a hex colour ('ff8000' -> 'orange'); the hex itself if it is not one."""
    value = (hex_value or "").lstrip("#").lower()
    if len(value) != 6:
        return f"#{value}" if value else ""
    try:
        rgb = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return f"#{value}"
    return min(FIBER_COLOURS, key=lambda item: sum((a - b) ** 2 for a, b in zip(item[1], rgb)))[0]


def _number(value):
    return format(value.normalize(), "f")


# -- facts about a cable -------------------------------------------------------------------------------------

def cable_facts(cable, ports=()):
    """Fiber-plant facts of a cable. `ports` are the front ports on either side of it in the trace, which tell
    which strands (and which fiber circuits) this particular link uses."""
    from netbox_fms.models import FiberCable

    if type(cable).__name__ != "Cable":
        return []
    fc = FiberCable.objects.select_related("fiber_cable_type__manufacturer", "installed_by").filter(cable_id=cable.pk).first()
    port_ids = [p.pk for p in ports if type(p).__name__ == "FrontPort"]
    facts = _record_facts(fc) if fc else []
    if fc and port_ids:
        facts.append(_strand_fact(fc, port_ids))
    if port_ids:
        facts.append(_circuit_fact(cable, port_ids))
    return [x for x in facts if x]


def _record_facts(fc):
    t = fc.fiber_cable_type
    sheath = [_display(t, "sheath_material").upper() if t.sheath_material else "",
              f"armoured ({_display(t, 'armor_type').lower()})" if t.is_armored and t.armor_type else
              ("armoured" if t.is_armored else ""),
              t.deployment or "", t.fire_rating or ""]
    installed_text = " by ".join(x for x in (str(fc.install_date) if fc.install_date else "", str(fc.installed_by or "")) if x)
    marks = ""
    if fc.start_mark is not None or fc.end_mark is not None:
        low, high = (_number(v) if v is not None else "?" for v in (fc.start_mark, fc.end_mark))
        marks = f"{low} – {high} {t.mark_unit or ''}".strip()
    return [
        _f("Fiber cable", f"{t.manufacturer.name} {t.model}" if t.manufacturer_id else t.model, "fms.type"),
        _f("Fibers", f"{t.strand_count} · {_display(t, 'construction').lower()}" if t.strand_count else "", "fms.fibers"),
        _f("Sheath", ", ".join(x for x in sheath if x), "fms.sheath"),
        _f("Fiber serial", fc.serial_number, "fms.serial"),
        _f("Installed", installed_text, "fms.installed"),
        _f("Route marks", marks, "fms.marks"),
        _f("Fiber notes", fc.notes, "fms.notes"),
    ]


def strand_text(strands):
    """'Tube 1-F3 (blue), Tube 1-F4 (yellow)': the tube and fiber, and the colour to look for."""
    return ", ".join(f"{s.name} ({colour_name(s.color)})" if s.color else s.name for s in strands)


def _strand_fact(fc, port_ids):
    from netbox_fms.models import FiberStrand

    strands = list(FiberStrand.objects.filter(fiber_cable=fc).landed_on(port_ids).order_by("position"))
    return _f("Strands", strand_text(strands), "fms.strands")


def _circuit_fact(cable, port_ids):
    from netbox_fms.models import FiberCircuit, FiberCircuitNode

    through = FiberCircuitNode.objects.filter(front_port_id__in=port_ids).values("path_id")
    circuits = (FiberCircuit.objects.filter(paths__id__in=through).filter(paths__nodes__cable_id=cable.pk)
                .select_related("tenant").distinct().order_by("cid", "name"))
    return _f("Fiber circuit", "; ".join(f"{c.cid} · {c.name}" if c.cid else c.name for c in circuits), "fms.circuit")


# -- fiber circuits as a starting point ----------------------------------------------------------------------

def _index_in(path, obj):
    for i, group in enumerate(path.path_objects):
        if any(type(x) is type(obj) and x.pk == obj.pk for x in group):
            return i
    return None


def _port_label(port):
    return f"{port.device.name} : {port.name}"


def circuit_paths(circuit):
    """The physical paths a fiber circuit runs on, as dicts with a label and the equipment at either end.

    FMS follows the glass from an origin front port to a destination front port; the cables and equipment on the
    way are NetBox's own cable paths, found as the paths that pass through both ports (one per direction)."""
    from dcim.models import CablePath

    ends, seen = [], set()
    for p in circuit.paths.select_related("origin__device", "destination__device").order_by("position"):
        if p.destination_id is None or (p.origin_id, p.destination_id) in seen:
            continue
        seen.add((p.origin_id, p.destination_id))
        ends.append((p.origin, p.destination))
    out, used = [], set()
    for origin, destination in ends:
        for path in CablePath.objects.filter(_nodes__contains=origin).filter(_nodes__contains=destination):
            io, idest = _index_in(path, origin), _index_in(path, destination)
            if io is None or idest is None or path.pk in used:
                continue
            used.add(path.pk)
            a, b = (origin, destination) if io < idest else (destination, origin)
            out.append({"path": path, "start": a.device.name, "end": b.device.name,
                        "from": _port_label(a), "to": _port_label(b), "label": f"{_port_label(a)} → {_port_label(b)}"})
    return out


def _find(titles, name, last=False):
    """Index of the block that is (or, where the path fans out, includes) the named equipment."""
    hits = [i for i, t in enumerate(titles) if name == t or name in t.split(" + ")]
    return (hits[-1] if last else hits[0]) if hits else None


def optics_text(circuit):
    """'2 strands · 1550 nm · measured loss 179.9 dB' from the circuit's paths."""
    paths = list(circuit.paths.all())
    wavelengths = sorted({p.wavelength_nm for p in paths if p.wavelength_nm})
    losses = sorted({p.actual_loss_db for p in paths if p.actual_loss_db is not None})
    loss = " / ".join(_number(v) for v in losses)
    return " · ".join(x for x in (
        f"{circuit.strand_count} strand{'s' if circuit.strand_count != 1 else ''}" if circuit.strand_count else "",
        ", ".join(f"{w} nm" for w in wavelengths),
        f"measured loss {loss} dB" if loss else "") if x)


def trim_doc(doc, entry, circuit):
    """Cut a collected trace down to the fiber circuit: from the panel where it starts to the one where it ends.

    The cable path continues past the circuit's end ports (to the muxponders, routers and beyond); the circuit
    does not, so the printout stops where the circuit does."""
    titles = [b.title for b in doc.blocks]
    i, j = _find(titles, entry["start"]), _find(titles, entry["end"], last=True)
    cut = i is not None and j is not None and i <= j
    if cut:
        doc.blocks, doc.links = doc.blocks[i:j + 1], doc.links[i:j]
    cables = sum(len(lk.cables) for lk in doc.links)
    doc.title = "Fiber circuit: " + (f"{circuit.cid} · {circuit.name}" if circuit.cid else circuit.name)
    who = " · ".join(x for x in (circuit.get_status_display(), str(circuit.tenant) if circuit.tenant else "") if x)
    doc.summary_items = [("doc.route", f"From {entry['from']} to {entry['to']}"),
                         ("doc.summary", f"{cables} cable{'s' if cables != 1 else ''} · fiber circuit" + (f" · {who}" if who else ""))]
    optics = optics_text(circuit)
    if optics:
        doc.summary_items.append(("fms.optics", optics))
    doc.summary = [text for _key, text in doc.summary_items]
    doc.notes = [n for n in doc.notes if not n.startswith(("The path ends at", "The path is incomplete", "This printout joins"))]
    if cut:
        doc.notes.append(f"Shown from {entry['from']} to {entry['to']}: the equipment beyond the circuit's end ports is left out.")
    return doc
