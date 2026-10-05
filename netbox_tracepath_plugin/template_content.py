"""
A "Print trace" button on NetBox's own pages for the objects this plugin can print: cables, interfaces, front
ports and circuit terminations, and (when those plugins are installed) netbox-fms fiber cables and fiber circuits
and netbox-wdm circuits. It opens the same object in the print page, so it picks the same cable.

NetBox lets a plugin add buttons to the button row of an object's page, not to the Trace button inside the
page's panels (that is part of NetBox's own template).
"""

from django.urls import reverse

from netbox.plugins import PluginTemplateExtension

from .collect import CORE_KINDS, kinds
from .integrations import fms, wdm

# Objects that only have a trace when a cable is attached to them.
NEEDS_CABLE = ("interface", "front-port", "circuit-termination")


def _label(entry):
    app, model, _name = entry
    return f"{app}.{model}"


class PrintTraceButton(PluginTemplateExtension):
    # Every object type that can ever be printed; whether this plugin's integrations are installed is checked
    # when the button is drawn, so a missing netbox-fms or netbox-wdm never matters here.
    models = [_label(e) for e in {**CORE_KINDS, **fms.KINDS, **wdm.KINDS}.values()]

    def buttons(self):
        obj, request = self.context.get("object"), self.context.get("request")
        if obj is None or request is None or not request.user.has_perm("dcim.view_cable"):
            return ""
        meta = obj._meta
        slug = next((s for s, (app, model, _n) in kinds().items() if (app, model) == (meta.app_label, meta.model_name)), None)
        if slug is None or (slug in NEEDS_CABLE and getattr(obj, "cable", None) is None):
            return ""
        return self.render("netbox_tracepath_plugin/inc/print_button.html", {
            "print_url": reverse("plugins:netbox_tracepath_plugin:print", kwargs={"kind": slug, "pk": obj.pk})})


template_extensions = [PrintTraceButton]
