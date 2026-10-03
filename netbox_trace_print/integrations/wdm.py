"""netbox-wdm: the channel, wavelength and wavelength service of a muxponder port, and the role of its line port."""

from django.apps import apps
from django.db.models import Q

from ..model import Field

APP = "netbox_wdm"
KINDS = {"wdm-circuit": (APP, "wdmcircuit", "WDM circuit")}


def installed():
    return apps.is_installed(APP)


def _f(label, value, key):
    value = "" if value is None else str(value).strip()
    return Field(label, value, key) if value else None


def device_facts(device):
    from netbox_wdm.models import WdmNode

    node = WdmNode.objects.filter(device_id=device.pk).first()
    if node is None:
        return []
    text = " · ".join(x for x in (node.get_node_type_display(), node.get_grid_display()) if x)
    return [x for x in (_f("WDM node", text, "wdm.node"),) if x]


def port_facts(term):
    from netbox_wdm.models import WdmChannel, WdmCircuit, WdmLinePort

    cls = type(term).__name__
    if cls == "FrontPort":
        channel = (WdmChannel.objects.filter(Q(mux_front_port_id=term.pk) | Q(demux_front_port_id=term.pk))
                   .select_related("wdm_node").first())
        if channel is None:
            return []
        services = (WdmCircuit.objects.filter(wavelength_paths__path_channels__channel=channel)
                    .select_related("tenant").distinct())
        service = "; ".join(c.name + (f" · {c.tenant}" if c.tenant else "") for c in services)
        return [x for x in (
            _f("Channel", channel, "wdm.channel"),
            _f("Channel status", channel.get_status_display(), "wdm.status"),
            _f("Service", service, "wdm.service"),
        ) if x]
    if cls == "RearPort":
        line = WdmLinePort.objects.filter(rear_port_id=term.pk).first()
        if line is None:
            return []
        text = " · ".join(x for x in (line.get_role_display(), line.get_direction_display()) if x)
        return [x for x in (_f("Line port", text, "wdm.line"),) if x]
    return []


# -- WDM circuits as a starting point ------------------------------------------------------------------------

def _index_in(path, obj):
    for i, group in enumerate(path.path_objects):
        if any(type(x) is type(obj) and x.pk == obj.pk for x in group):
            return i
    return None


def circuit_paths(circuit):
    """The physical paths a wavelength service runs on, as dicts with a label and the two muxponders.

    A WdmCircuit lists channels on muxponders; the cables between them are NetBox's own cable paths, found as the
    paths that pass through both end channels' front ports (one per direction).
    """
    from dcim.models import CablePath

    out = []
    for wp in circuit.wavelength_paths.all():
        entries = list(wp.path_channels.select_related("channel__wdm_node__device", "channel__mux_front_port",
                                                       "channel__demux_front_port").order_by("sequence"))
        if len(entries) < 2:
            continue
        first, last = entries[0].channel, entries[-1].channel
        port_a, port_b = (first.mux_front_port or first.demux_front_port), (last.mux_front_port or last.demux_front_port)
        if not (port_a and port_b):
            continue
        for path in CablePath.objects.filter(_nodes__contains=port_a).filter(_nodes__contains=port_b):
            ia, ib = _index_in(path, port_a), _index_in(path, port_b)
            if ia is None or ib is None:
                continue
            a, b = (first, last) if ia < ib else (last, first)
            start, end = a.wdm_node.device.name, b.wdm_node.device.name
            out.append({"path": path, "start": start, "end": end, "channel": str(a),
                        "label": f"{start} · {a} → {end} · {b}"})
    return out


def trim_doc(doc, entry, circuit):
    """Cut a collected trace down to the wavelength service: from one muxponder to the other.

    The cable path continues past the muxponders (to the client shelf, or on through a regenerator); the service
    does not, so the printout stops where the service does.
    """
    titles = [b.title for b in doc.blocks]
    i = titles.index(entry["start"])
    j = len(titles) - 1 - titles[::-1].index(entry["end"])
    doc.blocks, doc.links = doc.blocks[i:j + 1], doc.links[i:j]
    cables = sum(len(lk.cables) for lk in doc.links)
    doc.title = f"WDM circuit: {circuit.name}"
    who = " · ".join(x for x in (circuit.get_status_display(), str(circuit.tenant) if circuit.tenant else "") if x)
    doc.summary_items = [("doc.route", f"From {entry['start']} to {entry['end']}  ·  {entry['channel']}"),
                         ("doc.summary", f"{cables} cable{'s' if cables != 1 else ''} · wavelength service" + (f" · {who}" if who else ""))]
    doc.summary = [text for _key, text in doc.summary_items]
    doc.notes = [n for n in doc.notes if not n.startswith(("The path ends at", "The path is incomplete", "This printout joins"))]
    doc.notes.append(f"Shown from {entry['start']} to {entry['end']}: the equipment beyond the muxponders is left out.")
    return doc
