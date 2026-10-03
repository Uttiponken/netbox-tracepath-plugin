"""
NetBox -> TraceDoc.

Reads a cable path the same way NetBox's own trace does (a list of
(near terminations, cables, far terminations) steps), and turns it into the
blocks and links the layout engine draws. Only standard NetBox fields are used:
no custom fields, nothing from other plugins.

Objects the requesting user may not view are shown by name only.
"""

import datetime

from django.apps import apps
from django.conf import settings
from django.utils import timezone

from dcim.models import Cable, CablePath, PathEndpoint
from netbox.choices import ColorChoices

from . import __version__
from .model import Block, Cable as CableInfo, Field, Link, PortRow, TraceDoc

# kind (URL segment) -> (app label, model name, label shown to people)
KINDS = {
    "interface": ("dcim", "interface", "Interface"),
    "front-port": ("dcim", "frontport", "Front port"),
    "rear-port": ("dcim", "rearport", "Rear port"),
    "circuit-termination": ("circuits", "circuittermination", "Circuit termination"),
}

COLOR_NAMES = {str(k).lower(): str(v) for k, v in ColorChoices.CHOICES}
LENGTH_UNITS = {"m": "m", "km": "km", "cm": "cm", "ft": "ft", "in": "in", "mi": "mi"}


def model_for(kind):
    app, name, _label = KINDS[kind]
    return apps.get_model(app, name)


# -- paths ------------------------------------------------------------------

def paths_through(instance):
    """Every CablePath the object takes part in (an endpoint has exactly one of its own)."""
    if isinstance(instance, PathEndpoint):
        return [p for p in [instance.path] if p]
    return list(CablePath.objects.filter(_nodes__contains=instance))


def describe_path(path):
    origins = ", ".join(str(o) for o in path.origins)
    dests = ", ".join(str(d) for d in path.destinations) or "incomplete"
    return f"{origins} → {dests}"


def steps_of(path):
    """The path as (near terminations, links, far terminations) steps, as NetBox's own trace builds them."""
    objs = list(path.path_objects)
    if len(objs) % 3 == 1:          # ends at a pass-through port that is not connected further
        objs.extend(([], []))
    elif len(objs) % 3 == 2:        # ends at a site or provider network: an attachment, not a cable
        objs.insert(-1, [])
    return list(zip(*[iter(objs)] * 3))


# -- small formatting helpers -------------------------------------------------

def _f(label, value):
    value = "" if value is None else str(value).strip()
    return Field(label, value) if value else None


def _fields(*items):
    return [i for i in items if i]


def _name(obj):
    return str(obj) if obj else ""


def _tags(obj):
    return ", ".join(t.name for t in obj.tags.all()) if hasattr(obj, "tags") else ""


def _speed(kbps):
    if not kbps:
        return ""
    for unit, size in (("Tbps", 10 ** 9), ("Gbps", 10 ** 6), ("Mbps", 10 ** 3)):
        if kbps >= size:
            return f"{kbps / size:g} {unit}"
    return f"{kbps} kbps"


def _length(value, unit):
    if not value:
        return ""
    text = format(value.normalize(), "f") if hasattr(value, "normalize") else f"{value:g}"
    return f"{text} {LENGTH_UNITS.get(unit, unit or '')}".strip()


def _path_of(location):
    return " › ".join(n.name for n in location.get_ancestors(include_self=True)) if location else ""


# -- descriptions of NetBox objects ---------------------------------------------

def port_fields(term):
    """Fields shown under a port name inside a block."""
    out = []
    if hasattr(term, "get_type_display") and getattr(term, "type", None):
        out.append(_f("Type", term.get_type_display()))
    cls = type(term).__name__
    if cls == "Interface":
        out.append(_f("Speed", _speed(term.speed)))
        out.append(_f("Status", "Disabled" if not term.enabled else ""))
        out.append(_f("Use", "Management only" if term.mgmt_only else ""))
    elif cls == "RearPort":
        out.append(_f("Positions", term.positions if term.positions != 1 else ""))
    elif cls == "CircuitTermination":
        out.append(_f("Port speed", _speed(term.port_speed)))
        out.append(_f("Upstream speed", _speed(term.upstream_speed)))
        out.append(_f("Cross-connect", term.xconnect_id))
        out.append(_f("Patch panel", term.pp_info))
        out.append(_f("Termination", _name(term.termination)))
    if getattr(term, "module", None):
        out.append(_f("Module", term.module))
    out.append(_f("Label", getattr(term, "label", "")))
    out.append(_f("Description", term.description))
    out.append(_f("Marked connected", "Yes" if getattr(term, "mark_connected", False) else ""))
    return _fields(*out)


def port_name(term):
    if type(term).__name__ == "CircuitTermination":
        return f"Termination {term.term_side}"
    return term.name


def cable_info(cable):
    if not isinstance(cable, Cable):                      # a wireless link
        fields = _fields(_f("Status", cable.get_status_display()), _f("SSID", getattr(cable, "ssid", "")),
                         _f("Description", cable.description))
        return CableInfo(title=f"Wireless {cable}", fields=fields)
    color = (cable.color or "").lower()
    return CableInfo(
        title=str(cable),
        color_hex=color,
        color_name=COLOR_NAMES.get(color, f"#{color}" if color else ""),
        fields=_fields(
            _f("Type", cable.get_type_display() if cable.type else ""),
            _f("Length", _length(cable.length, cable.length_unit)),
            _f("Status", cable.get_status_display()),
            _f("Tenant", _name(cable.tenant)),
            _f("Description", cable.description),
            _f("Tags", _tags(cable)),
            _f("Comments", cable.comments),
        ))


def _device_block(dev):
    dt = dev.device_type
    pos = f"U{float(dev.position):g}" + (f" · {dev.get_face_display().lower()}" if dev.face else "") if dev.position else ""
    return Block(
        title=dev.name or f"{dt.model} #{dev.pk}",
        subtitle=" · ".join(x for x in (dev.role.name, f"{dt.manufacturer.name} {dt.model}") if x),
        kind="device",
        fields=_fields(
            _f("Status", dev.get_status_display()),
            _f("Tenant", _name(dev.tenant)),
            _f("Site", dev.site.name),
            _f("Region", _path_of(dev.site.region)),
            _f("Location", _path_of(dev.location)),
            _f("Rack", _name(dev.rack)),
            _f("Position", pos),
            _f("Serial", dev.serial),
            _f("Asset tag", dev.asset_tag),
            _f("Platform", _name(dev.platform)),
            _f("Primary IPv4", dev.primary_ip4),
            _f("Primary IPv6", dev.primary_ip6),
            _f("Description", dev.description),
            _f("Tags", _tags(dev)),
            _f("Comments", dev.comments),
        ),
        site=dev.site.name, location=dev.location.name if dev.location else "", rack=dev.rack.name if dev.rack else "")


def _circuit_block(circuit):
    return Block(
        title=circuit.cid,
        subtitle=" · ".join(x for x in (circuit.provider.name, circuit.type.name) if x),
        kind="circuit",
        fields=_fields(
            _f("Status", circuit.get_status_display()),
            _f("Tenant", _name(circuit.tenant)),
            _f("Provider", circuit.provider.name),
            _f("Commit rate", _speed(circuit.commit_rate)),
            _f("Installed", circuit.install_date),
            _f("Terminates", circuit.termination_date),
            _f("Description", circuit.description),
            _f("Tags", _tags(circuit)),
            _f("Comments", circuit.comments),
        ))


def _site_block(site):
    return Block(
        title=site.name, subtitle="Site", kind="site",
        fields=_fields(_f("Status", site.get_status_display()), _f("Tenant", _name(site.tenant)),
                       _f("Region", _path_of(site.region)), _f("Facility", site.facility),
                       _f("Time zone", site.time_zone), _f("Description", site.description)),
        site=site.name)


def _provider_network_block(pn):
    return Block(title=pn.name, subtitle=f"Provider network · {pn.provider.name}", kind="provider-network",
                 fields=_fields(_f("Provider", pn.provider.name), _f("Description", pn.description)))


def _restricted_block(obj):
    return Block(title=str(obj), subtitle="Details restricted", kind="restricted")


def block_for(obj):
    cls = type(obj).__name__
    if cls == "Device":
        return _device_block(obj)
    if cls == "Circuit":
        return _circuit_block(obj)
    if cls == "Site":
        return _site_block(obj)
    if cls == "ProviderNetwork":
        return _provider_network_block(obj)
    return Block(title=str(obj), subtitle=cls)


# -- the trace itself ---------------------------------------------------------

class Collector:
    def __init__(self, user):
        self.user = user
        self._visible = {}

    def visible(self, obj):
        key = (type(obj), obj.pk)
        if key not in self._visible:
            manager = type(obj)._default_manager
            self._visible[key] = (not hasattr(manager, "restrict")
                                  or manager.restrict(self.user, "view").filter(pk=obj.pk).exists())
        return self._visible[key]

    def _parent(self, term):
        return getattr(term, "parent_object", None) or term

    def _new_block(self, terms, notes):
        parents, seen = [], set()
        for t in terms:
            p = self._parent(t)
            if (type(p), p.pk) not in seen:
                seen.add((type(p), p.pk))
                parents.append(p)
        blocks = [block_for(p) if self.visible(p) else _restricted_block(p) for p in parents]
        block = blocks[0]
        if len(blocks) > 1:
            block.title = " + ".join(b.title for b in blocks)
            block.subtitle = f"{len(blocks)} objects"
            notes.append(f"The path fans out over {len(blocks)} objects here ({block.title}); only the first is "
                         f"described in detail.")
        return block

    def trace_doc(self, path, origin_label=""):
        notes = []
        steps = steps_of(path)
        blocks, links, io = [], [], {}
        cur = None
        for k, (near, link_objs, far) in enumerate(steps):
            if k == 0:
                cur = self._new_block(near, notes)
                blocks.append(cur)
                io[id(cur)] = {"in": [], "out": []}
            io[id(cur)]["out"] += [t for t in near if self.visible(t)] if k else list(near)
            if far:
                links.append(Link([cable_info(c) for c in link_objs if self.visible(c)]
                                  or [CableInfo(title="Cable (restricted)")] if link_objs else []))
                nxt = self._new_block(far, notes)
                blocks.append(nxt)
                io[id(nxt)] = {"in": list(far), "out": []}
                cur = nxt
            elif not link_objs and k == len(steps) - 1:
                notes.append(f"The path ends at {cur.title}: nothing is connected beyond it.")

        for b in blocks:
            ins, outs = io[id(b)]["in"], io[id(b)]["out"]
            rows = []
            for i in range(max(len(ins), len(outs))):
                a = ins[i] if i < len(ins) else None
                o = outs[i] if i < len(outs) else None
                rows.append(PortRow(in_name=port_name(a) if a else "", in_fields=port_fields(a) if a else [],
                                    out_name=port_name(o) if o else "", out_fields=port_fields(o) if o else []))
            b.ports = rows

        if path.is_split:
            notes.append("The path is split: it diverges across several cables, and only one branch is shown. "
                         "Choose another path to see the others.")
        elif not path.is_complete and not any("ends at" in n for n in notes):
            notes.append("The path is incomplete: it does not reach a far end.")
        if path.is_complete and not path.is_active:
            notes.append("Not every cable on this path has the status Connected.")

        cables = [c for lk in links for c in lk.cables if c.title != "Cable (restricted)"]
        total, definitive = path.get_total_length()
        length = ""
        if total:
            length = f" · total length {_length(total, 'm')}{'' if definitive else '+'}"
        circuits = [b.title for b in blocks if b.kind == "circuit"]
        first, last = (cables[0].title, cables[-1].title) if cables else ("", "")
        label = first if first == last else f"{first} … {last}"
        title = "Cable trace: " + (label or origin_label)
        if circuits:
            title += " · Circuit " + ", ".join(dict.fromkeys(circuits))

        def end(block, side):
            row = (block.ports[0] if block.ports else None)
            port = (row.out_name if side == "out" else row.in_name) if row else ""
            return f"{block.title} : {port}" if port else block.title
        summary = []
        if blocks:
            summary.append(f"From {end(blocks[0], 'out')}   to   {end(blocks[-1], 'in')}")
        state = "complete" if path.is_complete else "incomplete"
        summary.append(f"{len(cables)} cable{'s' if len(cables) != 1 else ''}{length} · path {state}")

        now = timezone.localtime(timezone.now())
        footer = (f"Generated {now:%Y-%m-%d %H:%M} by {self.user.get_username()} · NetBox "
                  f"{settings.RELEASE.full_version} · netbox-trace-print {__version__}")
        return TraceDoc(title=title, summary=summary, blocks=blocks, links=links, notes=notes, footer=footer)
