"""netbox-fms: the fiber-plant record of a cable (type, construction, serial, installation, route marks)."""

from django.apps import apps

from ..model import Field

APP = "netbox_fms"
KINDS = {"fiber-cable": (APP, "fibercable", "Fiber cable (FMS)")}


def installed():
    return apps.is_installed(APP)


def _f(label, value, key):
    value = "" if value is None else str(value).strip()
    return Field(label, value, key) if value else None


def _display(obj, name):
    getter = getattr(obj, f"get_{name}_display", None)
    return getter() if getter else getattr(obj, name, "")


def cable_facts(cable):
    from netbox_fms.models import FiberCable

    if type(cable).__name__ != "Cable":
        return []
    fc = FiberCable.objects.select_related("fiber_cable_type__manufacturer", "installed_by").filter(cable_id=cable.pk).first()
    if fc is None:
        return []
    t = fc.fiber_cable_type
    sheath = [_display(t, "sheath_material").upper() if t.sheath_material else "",
              f"armoured ({_display(t, 'armor_type').lower()})" if t.is_armored and t.armor_type else
              ("armoured" if t.is_armored else ""),
              t.deployment or "", t.fire_rating or ""]
    installed_text = " by ".join(x for x in (str(fc.install_date) if fc.install_date else "", str(fc.installed_by or "")) if x)
    marks = ""
    if fc.start_mark is not None or fc.end_mark is not None:
        low, high = (format(v.normalize(), "f") if v is not None else "?" for v in (fc.start_mark, fc.end_mark))
        marks = f"{low} – {high} {t.mark_unit or ''}".strip()
    return [x for x in (
        _f("Fiber cable", f"{t.manufacturer.name} {t.model}" if t.manufacturer_id else t.model, "fms.type"),
        _f("Fibers", f"{t.strand_count} · {_display(t, 'construction').lower()}" if t.strand_count else "", "fms.fibers"),
        _f("Sheath", ", ".join(x for x in sheath if x), "fms.sheath"),
        _f("Fiber serial", fc.serial_number, "fms.serial"),
        _f("Installed", installed_text, "fms.installed"),
        _f("Route marks", marks, "fms.marks"),
        _f("Fiber notes", fc.notes, "fms.notes"),
    ) if x]
