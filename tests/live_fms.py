"""
Real FMS fiber circuits and a trunk's pair printed into samples/<version>/. Run inside the NetBox container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-trace-print/tests/live_fms.py').read())"
"""
import os

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from dcim.models import Cable
from netbox_fms.models import FiberCircuit
from netbox_trace_print import __version__
from netbox_trace_print.collect import Collector, pair_of, paths_through
from netbox_trace_print.integrations import fms
from netbox_trace_print.layout import LayoutSpec, render
from netbox_trace_print.models import PrintProfile
from netbox_trace_print.selection import apply_selection

OUT = f"/opt/netbox/custom-plugins/netbox-trace-print/samples/{__version__}"
os.makedirs(OUT, exist_ok=True)
user = get_user_model().objects.get(username="demo-loader")
collector = Collector(user)
profiles = list(PrintProfile.objects.filter(name__in=["Full information", "Field technician"]))

jobs = []
for cid, label in (("NF-FC-0002", "fiber-circuit-sto-osl"), ("NF-FC-0004", "fiber-circuit-sto-hel-nsn")):
    circuit = FiberCircuit.objects.get(cid=cid)
    entry = fms.circuit_paths(circuit)[0]
    doc = fms.trim_doc(collector.chain_doc([collector.part(entry["path"])], origin_label=str(circuit)), entry, circuit)
    jobs.append((label, doc))
trunk = Cable.objects.get(label="bb-cbl-00003")
path = next(p for p in paths_through(trunk) if pair_of(p, trunk) == "Pair 1")
jobs.append(("trunk-pair-1-sto-osl", collector.trace_doc(path, origin_label=str(trunk))))

for label, doc in jobs:
    for profile in profiles:
        out = apply_selection(doc, profile.keys, layout_name=profile.name)
        pdf, rep = render(out, LayoutSpec(paper="A4", orientation="landscape"))
        name = f"{slugify(profile.name)}-nordfiber-{label}-a4-landscape.pdf"
        open(os.path.join(OUT, name), "wb").write(pdf)
        print(f"{name:80} pages={rep.pages} fits={rep.fits}")
    print("   ", out.title, "|", out.summary)
    for lk in out.links:
        for c in lk.cables:
            print("      ", c.title, [(f.label, f.value) for f in c.fields if f.key.startswith("fms.") and f.key not in ("fms.type", "fms.fibers", "fms.sheath", "fms.serial", "fms.installed", "fms.marks", "fms.notes")])
