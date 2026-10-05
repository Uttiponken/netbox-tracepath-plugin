"""
Extending a trace: add the connections around the equipment at either end.

If a trace runs A - B - C - D - E, choose another cabled port on E and its path (E - f - g - h) is added,
giving A - B - C - D - E - f - g - h with E drawn once, arriving on one port and leaving on another.
The same at the start. The choices are kept as lists of port ids: `after` (at the end, in order, each on the
equipment where the previous one ended) and `before` (at the start).
"""

from collections import OrderedDict

from dcim.models import Interface

from .collect import describe_path, paths_through


def _single_interface(terms):
    terms = list(terms)
    return terms[0] if len(terms) == 1 and type(terms[0]).__name__ == "Interface" else None


def _port(user, port_id, device_id, exclude_ids):
    """The cabled interface the user may view, on the given equipment, or None."""
    if not str(port_id).isdigit() or int(port_id) in exclude_ids:
        return None
    return (Interface.objects.restrict(user, "view")
            .filter(pk=int(port_id), device_id=device_id, cable__isnull=False).select_related("device").first())


class Chain:
    """The base path with its extensions at either end."""

    def __init__(self, user, base_path, before=(), after=()):
        self.base = base_path
        self.after, self.before = [], []          # accepted (port, path) pairs, in order
        used = set()
        end = _single_interface(base_path.destinations)
        start = _single_interface(base_path.origins)
        used |= {t.pk for t in (end, start) if t is not None}
        for raw in after:
            port = _port(user, raw, end.device_id, used) if end is not None else None
            path = port.path if port is not None else None
            if path is None:
                break
            self.after.append((port, path))
            used.add(port.pk)
            end = _single_interface(path.destinations)
            if end is not None:
                used.add(end.pk)
        for raw in before:
            port = _port(user, raw, start.device_id, used) if start is not None else None
            path = port.path if port is not None else None
            if path is None:
                break
            self.before.append((port, path))
            used.add(port.pk)
            start = _single_interface(path.destinations)
            if start is not None:
                used.add(start.pk)
        self.end, self.start, self.used = end, start, used

    @property
    def ids(self):
        return {"before": [p.pk for p, _ in self.before], "after": [p.pk for p, _ in self.after]}

    def parts(self, collector):
        """Parts in reading order: the start extensions (turned around), the base, the end extensions."""
        out = [collector.part(path, reverse=True) for _port, path in reversed(self.before)]
        out.append(collector.part(self.base))
        out += [collector.part(path) for _port, path in self.after]
        return out

    def candidates(self, user, side):
        """Other cabled interfaces on the equipment at one end of the chain, grouped by where they lead."""
        term = self.end if side == "after" else self.start
        if term is None:
            return None
        groups = OrderedDict()
        ports = (Interface.objects.restrict(user, "view").filter(device_id=term.device_id, cable__isnull=False)
                 .exclude(pk__in=self.used).order_by("name"))
        for port in ports:
            path = port.path
            if path is None:
                continue
            label, _sep, meta = describe_path(path, reverse=(side == "before")).partition("  ·  ")
            groups.setdefault(_far_group(path), []).append({"id": port.pk, "label": label, "meta": meta})
        return {"device": term.device.name, "groups": list(groups.items())}


def _far_group(path):
    """What a path leads to, as a heading: the equipment (or circuit) at its far end."""
    names = []
    for d in path.destinations:
        parent = getattr(d, "parent_object", None) or d
        names.append(getattr(parent, "name", None) or getattr(parent, "cid", None) or str(parent))
    return ", ".join(dict.fromkeys(names)) or "Not connected further"
