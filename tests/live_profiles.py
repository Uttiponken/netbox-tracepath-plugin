"""
One real trace printed with every print profile, into samples/<version>/. Run inside the NetBox container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-trace-print/tests/live_profiles.py').read())"
"""
import os

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from dcim.models import Interface
from netbox_trace_print import __version__
from netbox_trace_print.collect import Collector, paths_through
from netbox_trace_print.layout import LayoutSpec, render
from netbox_trace_print.models import PrintProfile
from netbox_trace_print.selection import apply_selection

OUT = f"/opt/netbox/custom-plugins/netbox-trace-print/samples/{__version__}"
os.makedirs(OUT, exist_ok=True)
user = get_user_model().objects.get(username="demo-loader")

TRACES = {
    "colo-tenant": lambda: Interface.objects.get(device__name="polaris-sto-sw-01", name="Ethernet49"),
    "helsinki-link": lambda: Interface.objects.get(device__name="hel-rtr-01", name="et-0/0/2"),
}
RECIPIENT = {"Field technician": "Field engineer, Stockholm DC", "Customer-safe": "Polaris Cloud Services"}

for trace, get in TRACES.items():
    obj = get()
    doc = Collector(user).trace_doc(paths_through(obj)[0], origin_label=str(obj))
    for profile in PrintProfile.objects.order_by("id"):
        out = apply_selection(doc, profile.keys, layout_name=profile.name, prepared_for=RECIPIENT.get(profile.name, ""))
        pdf, rep = render(out, LayoutSpec(paper="A4", orientation="landscape"))
        name = f"{slugify(profile.name)}-nordfiber-{trace}-a4-landscape.pdf"
        open(os.path.join(OUT, name), "wb").write(pdf)
        print(f"{name:70} pages={rep.pages} cols={rep.columns} fits={rep.fits} facts={len(profile.keys)}")
