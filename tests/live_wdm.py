"""
Real WDM circuits (and the Polaris colo trace, to show the green trunks) printed into samples/<version>/.
Run inside the NetBox container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-trace-print/tests/live_wdm.py').read())"
"""
import os

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from dcim.models import Interface
from netbox_wdm.models import WdmCircuit
from netbox_trace_print import __version__
from netbox_trace_print.collect import Collector, paths_through
from netbox_trace_print.integrations import wdm
from netbox_trace_print.layout import LayoutSpec, render
from netbox_trace_print.models import PrintProfile
from netbox_trace_print.selection import apply_selection

OUT = f"/opt/netbox/custom-plugins/netbox-trace-print/samples/{__version__}"
os.makedirs(OUT, exist_ok=True)
user = get_user_model().objects.get(username="demo-loader")
collector = Collector(user)
profiles = list(PrintProfile.objects.filter(name__in=["Full information", "Field technician"]))

jobs = []
for name, label in (("Fjord", "fjord"), ("Baltic Retail Group Backup - Segment 1", "brg-segment-1")):
    circuit = WdmCircuit.objects.get(name__startswith=name)
    entry = wdm.circuit_paths(circuit)[0]
    doc = wdm.trim_doc(collector.chain_doc([collector.part(entry["path"])]), entry, circuit)
    jobs.append((f"wdm-circuit-{label}", doc))
iface = Interface.objects.get(device__name="polaris-sto-sw-01", name="Ethernet49")
jobs.append(("colo-tenant", collector.trace_doc(paths_through(iface)[0], origin_label=str(iface))))

for label, doc in jobs:
    for profile in profiles:
        out = apply_selection(doc, profile.keys, layout_name=profile.name)
        pdf, rep = render(out, LayoutSpec(paper="A4", orientation="landscape"))
        name = f"{slugify(profile.name)}-nordfiber-{label}-a4-landscape.pdf"
        open(os.path.join(OUT, name), "wb").write(pdf)
        print(f"{name:75} pages={rep.pages} fits={rep.fits}")
