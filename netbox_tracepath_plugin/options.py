"""
The options behind the start-of-trace dropdowns, in the shape NetBox's own dropdown widget expects
({"count", "results": [{"id", "display", "description"}]}), so a port reads 'equipment : port' instead of a
bare 'Port 1' and can be found by either part. Only objects that have a cable are offered.
"""

from dcim.models import Cable, FrontPort, Interface

OPTION_KINDS = {"interface": Interface, "front-port": FrontPort, "cable": Cable}
DEFAULT_LIMIT, MAX_LIMIT = 50, 100


def port_label(port):
    return f"{port.device.name} : {port.name}"


def cable_label(cable):
    return cable.label or f"#{cable.pk}"


def cable_ends(cable):
    names = []
    for side in (cable.a_terminations, cable.b_terminations):
        names.append(", ".join(sorted({f"{getattr(t, 'device', None) and t.device.name or t.parent_object} : {t}"
                                       if hasattr(t, "device") else str(t) for t in side})))
    return " ↔ ".join(n for n in names if n)


def queryset(kind, user, q=""):
    model = OPTION_KINDS[kind]
    qs = model.objects.restrict(user, "view")
    if kind == "cable":
        qs = qs.prefetch_related("terminations__termination").order_by("label", "pk")
        for token in q.split():
            from django.db.models import Q
            qs = qs.filter(Q(label__icontains=token) | Q(description__icontains=token))
        return qs
    qs = qs.filter(cable__isnull=False).select_related("device", "cable").order_by("device__name", "name")
    for token in q.split():
        from django.db.models import Q
        qs = qs.filter(Q(device__name__icontains=token) | Q(name__icontains=token) | Q(cable__label__icontains=token))
    return qs


def search(kind, user, q="", limit=DEFAULT_LIMIT, offset=0):
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    offset = max(0, int(offset or 0))
    qs = queryset(kind, user, q)
    count = qs.count()
    results = []
    for obj in qs[offset:offset + limit]:
        if kind == "cable":
            results.append({"id": obj.pk, "display": cable_label(obj), "description": cable_ends(obj)})
        else:
            results.append({"id": obj.pk, "display": port_label(obj), "description": f"cable {cable_label(obj.cable)}"})
    return {"count": count, "next": None, "previous": None, "results": results}
