"""netbox-wdm: the channel, wavelength and wavelength service of a muxponder port, and the role of its line port."""

from django.apps import apps
from django.db.models import Q

from ..model import Field

APP = "netbox_wdm"


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
