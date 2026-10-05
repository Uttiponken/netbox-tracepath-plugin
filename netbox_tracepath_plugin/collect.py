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

from . import __version__, integrations
from .model import Block, Cable as CableInfo, Field, Link, PortRow, TraceDoc

# kind (URL segment) -> (app label, model name, label shown to people)
CORE_KINDS = {
    "cable": ("dcim", "cable", "Cable"),
    "interface": ("dcim", "interface", "Interface"),
    "front-port": ("dcim", "frontport", "Front port"),
    "circuit-termination": ("circuits", "circuittermination", "Circuit termination"),
}

COLOR_NAMES = {str(k).lower(): str(v) for k, v in ColorChoices.CHOICES}
LENGTH_UNITS = {"m": "m", "km": "km", "cm": "cm", "ft": "ft", "in": "in", "mi": "mi"}


def kinds():
    """The kinds of starting point: the core ones, then those added by installed integrations (netbox-wdm, ...)."""
    out = dict(CORE_KINDS)
    out.update(integrations.kinds())
    return out


def model_for(kind):
    app, name, _label = kinds()[kind]
    return apps.get_model(app, name)


# -- paths ------------------------------------------------------------------

def paths_through(instance):
    """Every CablePath the object takes part in (an endpoint has exactly one of its own)."""
    if isinstance(instance, PathEndpoint):
        return [p for p in [instance.path] if p]
    return list(CablePath.objects.filter(_nodes__contains=instance))


def end_label(term):
    """'equipment : port' for a termination, so two paths through the same cable can be told apart."""
    parent = getattr(term, "parent_object", None) or term
    owner = getattr(parent, "name", None) or getattr(parent, "cid", None) or str(parent)
    return f"{owner} : {port_name(term)}" if hasattr(term, "term_side") or hasattr(term, "name") else str(term)


def describe_path(path, reverse=False):
    """How a path is named in the dropdown: 'equipment : port → equipment : port', and how many cables it has.

    `reverse` names it from its far end instead (used for connections that arrive at the equipment)."""
    steps = steps_of(path)
    origins = ", ".join(end_label(o) for o in path.origins)
    if path.destinations:
        target = ", ".join(end_label(d) for d in path.destinations)
    else:                                       # incomplete: say where it stops
        last = next((far or near for near, _links, far in reversed(steps) if far or near), [])
        target = (", ".join(end_label(t) for t in last) if last else "?") + " (not connected further)"
    cables = sum(1 for _near, links, _far in steps for _l in links)
    left, right = (target.replace(" (not connected further)", ""), origins) if reverse else (origins, target)
    return f"{left} → {right}  ·  {cables} cable{'s' if cables != 1 else ''}"


def pair_of(path, cable):
    """Which pair of a trunk the path uses: the front port next to the trunk's rear port ('Port 3' -> 'Pair 3')."""
    objs = list(path.path_objects)
    for i, group in enumerate(objs):
        if any(type(x).__name__ == "Cable" and x.pk == cable.pk for x in group):
            for j in (i - 2, i + 2):
                for x in objs[j] if 0 <= j < len(objs) else []:
                    if type(x).__name__ == "FrontPort":
                        digits = "".join(ch for ch in x.name.split()[-1] if ch.isdigit())
                        return f"Pair {digits}" if digits else x.name
            return None
    return None


def steps_of(path):
    """The path as (near terminations, links, far terminations) steps, as NetBox's own trace builds them."""
    objs = list(path.path_objects)
    if len(objs) % 3 == 1:          # ends at a pass-through port that is not connected further
        objs.extend(([], []))
    elif len(objs) % 3 == 2:        # ends at a site or provider network: an attachment, not a cable
        objs.insert(-1, [])
    return list(zip(*[iter(objs)] * 3))


# -- small formatting helpers -------------------------------------------------

def _f(label, value, key=""):
    value = "" if value is None else str(value).strip()
    return Field(label, value, key) if value else None


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
        out.append(_f("Type", term.get_type_display(), "port.type"))
    cls = type(term).__name__
    if cls == "Interface":
        out.append(_f("Speed", _speed(term.speed), "port.speed"))
        out.append(_f("Status", "Disabled" if not term.enabled else "", "port.status"))
        out.append(_f("Use", "Management only" if term.mgmt_only else "", "port.use"))
    elif cls == "RearPort":
        out.append(_f("Positions", term.positions if term.positions != 1 else "", "port.positions"))
    elif cls == "CircuitTermination":
        out.append(_f("Port speed", _speed(term.port_speed), "ct.port_speed"))
        out.append(_f("Upstream speed", _speed(term.upstream_speed), "ct.upstream_speed"))
        out.append(_f("Cross-connect", term.xconnect_id, "ct.xconnect"))
        out.append(_f("Patch panel", term.pp_info, "ct.patch_panel"))
        out.append(_f("Termination", _name(term.termination), "ct.termination"))
    if getattr(term, "module", None):
        out.append(_f("Module", term.module, "port.module"))
    out.append(_f("Label", getattr(term, "label", ""), "port.label"))
    out.append(_f("Description", term.description, "port.description"))
    out.append(_f("Marked connected", "Yes" if getattr(term, "mark_connected", False) else "", "port.marked_connected"))
    return _fields(*out) + integrations.port_facts(term)


def port_name(term):
    if type(term).__name__ == "CircuitTermination":
        return f"Termination {term.term_side}"
    return term.name


def cable_info(cable, ports=()):
    """`ports`: the front ports on either side of the cable in this trace, for facts that depend on the pair it carries."""
    if not isinstance(cable, Cable):                      # a wireless link
        fields = _fields(_f("Status", cable.get_status_display(), "cable.status"),
                         _f("SSID", getattr(cable, "ssid", ""), "cable.type"),
                         _f("Description", cable.description, "cable.description"))
        return CableInfo(title=f"Wireless {cable}", fields=fields)
    color = (cable.color or "").lower()
    return CableInfo(
        title=str(cable),
        color_hex=color,
        color_name=COLOR_NAMES.get(color, f"#{color}" if color else ""),
        fields=_fields(
            _f("Type", cable.get_type_display() if cable.type else "", "cable.type"),
            _f("Length", _length(cable.length, cable.length_unit), "cable.length"),
            _f("Status", cable.get_status_display(), "cable.status"),
            _f("Tenant", _name(cable.tenant), "cable.tenant"),
            _f("Description", cable.description, "cable.description"),
            _f("Tags", _tags(cable), "cable.tags"),
            _f("Comments", cable.comments, "cable.comments"),
        ) + integrations.cable_facts(cable, ports))


def _device_block(dev):
    dt = dev.device_type
    pos = f"U{float(dev.position):g}" + (f" · {dev.get_face_display().lower()}" if dev.face else "") if dev.position else ""
    return Block(
        title=dev.name or f"{dt.model} #{dev.pk}",
        subtitle=" · ".join(x for x in (dev.role.name, f"{dt.manufacturer.name} {dt.model}") if x),
        subtitle_key="device.subtitle",
        kind="device",
        fields=_fields(
            _f("Status", dev.get_status_display(), "device.status"),
            _f("Tenant", _name(dev.tenant), "device.tenant"),
            _f("Site", dev.site.name, "device.site"),
            _f("Region", _path_of(dev.site.region), "device.region"),
            _f("Location", _path_of(dev.location), "device.location"),
            _f("Rack", _name(dev.rack), "device.rack"),
            _f("Position", pos, "device.position"),
            _f("Serial", dev.serial, "device.serial"),
            _f("Asset tag", dev.asset_tag, "device.asset_tag"),
            _f("Platform", _name(dev.platform), "device.platform"),
            _f("Primary IPv4", dev.primary_ip4, "device.ipv4"),
            _f("Primary IPv6", dev.primary_ip6, "device.ipv6"),
            _f("Description", dev.description, "device.description"),
            _f("Tags", _tags(dev), "device.tags"),
            _f("Comments", dev.comments, "device.comments"),
        ) + integrations.device_facts(dev),
        site=dev.site.name, location=dev.location.name if dev.location else "", rack=dev.rack.name if dev.rack else "",
        color_hex=(dev.role.color or "").lower().lstrip("#"))


def _circuit_block(circuit):
    return Block(
        title=circuit.cid,
        subtitle=" · ".join(x for x in (circuit.provider.name, circuit.type.name) if x),
        subtitle_key="circuit.subtitle",
        kind="circuit",
        fields=_fields(
            _f("Status", circuit.get_status_display(), "circuit.status"),
            _f("Tenant", _name(circuit.tenant), "circuit.tenant"),
            _f("Provider", circuit.provider.name, "circuit.provider"),
            _f("Commit rate", _speed(circuit.commit_rate), "circuit.commit_rate"),
            _f("Installed", circuit.install_date, "circuit.installed"),
            _f("Terminates", circuit.termination_date, "circuit.terminates"),
            _f("Description", circuit.description, "circuit.description"),
            _f("Tags", _tags(circuit), "circuit.tags"),
            _f("Comments", circuit.comments, "circuit.comments"),
        ))


def _site_block(site):
    return Block(
        title=site.name, subtitle="Site", kind="site",
        fields=_fields(_f("Status", site.get_status_display(), "site.status"), _f("Tenant", _name(site.tenant), "site.tenant"),
                       _f("Region", _path_of(site.region), "site.region"), _f("Facility", site.facility, "site.facility"),
                       _f("Time zone", site.time_zone, "site.timezone"), _f("Description", site.description, "site.description")),
        site=site.name)


def _provider_network_block(pn):
    return Block(title=pn.name, subtitle=f"Provider network · {pn.provider.name}", kind="provider-network",
                 fields=_fields(_f("Provider", pn.provider.name, "network.provider"),
                                _f("Description", pn.description, "network.description")))


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

    def part(self, path, reverse=False):
        """One path as blocks and links, ready to be joined with others. `reverse` turns it around."""
        notes = []                                   # (where it applies, text)
        steps = steps_of(path)
        blocks, links, io = [], [], {}
        cur = None
        for k, (near, link_objs, far) in enumerate(steps):
            if k == 0:
                cur = self._new_block(near, [])
                blocks.append(cur)
                io[id(cur)] = {"in": [], "out": []}
            io[id(cur)]["out"] += [t for t in near if self.visible(t)] if k else list(near)
            if far:
                around = (list(steps[k - 1][2]) if k else []) + (list(steps[k + 1][0]) if k + 1 < len(steps) else [])
                links.append(Link([cable_info(c, around) for c in link_objs if self.visible(c)]
                                  or [CableInfo(title="Cable (restricted)")] if link_objs else []))
                nxt = self._new_block(far, [])
                blocks.append(nxt)
                io[id(nxt)] = {"in": list(far), "out": []}
                cur = nxt
            elif not link_objs and k == len(steps) - 1:
                notes.append(("end", f"The path ends at {cur.title}: nothing is connected beyond it."))

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
            notes.append(("general", "The path is split: it diverges across several cables, and only one branch is shown. "
                                     "Choose another path to see the others."))
        elif not path.is_complete and not notes:
            notes.append(("end", "The path is incomplete: it does not reach a far end."))
        if path.is_complete and not path.is_active:
            notes.append(("general", "Not every cable on this path has the status Connected."))
        if reverse:
            blocks, links = reverse_chain(blocks, links)
        return {"blocks": blocks, "links": links, "notes": notes, "path": path}

    def trace_doc(self, path, origin_label=""):
        return self.chain_doc([self.part(path)], origin_label)

    def chain_doc(self, parts, origin_label=""):
        """Join parts end to end into one TraceDoc: the equipment where two parts meet becomes one block."""
        blocks, links = list(parts[0]["blocks"]), list(parts[0]["links"])
        for p in parts[1:]:
            joint, first = blocks[-1], p["blocks"][0]
            if not joint.ports:
                joint.ports = first.ports
            else:
                for i, row in enumerate(first.ports):
                    if i < len(joint.ports):
                        joint.ports[i].out_name, joint.ports[i].out_fields = row.out_name, row.out_fields
                    else:
                        joint.ports.append(row)
            blocks += p["blocks"][1:]
            links += p["links"]

        # a note about where a path stops only means something at the ends of the whole chain
        notes = []
        for i, p in enumerate(parts):
            for where, text in p["notes"]:
                if (where == "general" or i in (0, len(parts) - 1)) and text not in notes:
                    notes.append(text)
        if len(parts) > 1:
            notes.insert(0, f"This printout joins {len(parts)} traces at the equipment where they meet.")

        cables = [c for lk in links for c in lk.cables if c.title != "Cable (restricted)"]
        total, definitive = 0, True
        for p in parts:
            t, d = p["path"].get_total_length()
            total += t or 0
            definitive = definitive and d
        length = f" · total length {_length(total, 'm')}{'' if definitive else '+'}" if total else ""
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
        items = []
        if blocks:
            items.append(("doc.route", f"From {end(blocks[0], 'out')}   to   {end(blocks[-1], 'in')}"))
        state = "complete" if all(p["path"].is_complete for p in parts) else "incomplete"
        items.append(("doc.summary", f"{len(cables)} cable{'s' if len(cables) != 1 else ''}{length} · path {state}"))
        summary = [text for _key, text in items]

        now = timezone.localtime(timezone.now())
        footer = (f"Generated {now:%Y-%m-%d %H:%M} by {self.user.get_username()} · NetBox "
                  f"{settings.RELEASE.full_version} · netbox-tracepath-plugin {__version__}")
        return TraceDoc(title=title, summary=summary, blocks=blocks, links=links, notes=notes, footer=footer,
                        summary_items=items, footer_items=[("doc.generated", footer)])


def reverse_chain(blocks, links):
    """The same chain read from the other end: blocks and links in reverse order, in and out ports swapped."""
    for b in blocks:
        for row in b.ports:
            row.in_name, row.out_name = row.out_name, row.in_name
            row.in_fields, row.out_fields = row.out_fields, row.in_fields
    return list(reversed(blocks)), list(reversed(links))
