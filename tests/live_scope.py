"""
Scoped prints of real traces into samples/<version>/. Run inside the NetBox container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-trace-print/tests/live_scope.py').read())"
"""
import os

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from dcim.models import Interface
from netbox_trace_print import __version__
from netbox_trace_print.collect import Collector, paths_through
from netbox_trace_print.extend import Chain
from netbox_trace_print.layout import LayoutSpec, render
from netbox_trace_print.models import PrintProfile
from netbox_trace_print.scope import apply_scope, scopes_of
from netbox_trace_print.selection import apply_selection

OUT = f"/opt/netbox/custom-plugins/netbox-trace-print/samples/{__version__}"
os.makedirs(OUT, exist_ok=True)
user = get_user_model().objects.get(username="demo-loader")
collector = Collector(user)
profiles = list(PrintProfile.objects.filter(name__in=["Full information", "Field technician"]))


def pick(doc, text):
    return next(s["value"] for s in scopes_of(doc) if s["label"].endswith(text))


sth = Interface.objects.get(device__name="sto-rtr-01", name="et-0/0/2")
nsn = collector.trace_doc(paths_through(sth)[0], origin_label=str(sth))
pid = lambda dev, name: Interface.objects.get(device__name=dev, name=name).pk
first = paths_through(Interface.objects.get(device__name="baltic-retail-sto-srv-01", name="Gig-E 1"))[0]
chain = Chain(user, first, after=[pid(d, n) for d, n in [
    ("baltic-retail-sto-sw-01", "Ethernet49"), ("sto-sw-01", "Ethernet1"), ("sto-rtr-01", "et-0/0/0"),
    ("mma-rtr-01", "xe-0/1/0"), ("mma-sw-01", "Ethernet2"), ("baltic-retail-mma-sw-01", "Ethernet1")]])
brg = collector.chain_doc(chain.parts(collector), origin_label="server to server")
print("scopes:", [x["label"] for x in scopes_of(brg)])

jobs = [("sto-hel-nsn-rack-sto-mm-01", nsn, pick(nsn, "STO-MM-01")),
        ("sto-hel-nsn-site-helsinki", nsn, "site:Nordfiber Helsinki DC"),
        ("sto-hel-nsn-site-stockholm", nsn, "site:Nordfiber Stockholm DC"),
        ("baltic-retail-site-malmo", brg, next(s["value"] for s in scopes_of(brg) if "Malm" in s["label"] and s["kind"] == "site")),
        ("baltic-retail-meetme-room-stockholm", brg, pick(brg, "Stockholm DC › MeetMe Room"))]
for label, doc, scope in jobs:
    scoped = apply_scope(doc, scope)
    for profile in profiles:
        out = apply_selection(scoped, profile.keys, layout_name=profile.name)
        pdf, rep = render(out, LayoutSpec(paper="A4", orientation="landscape"))
        name = f"{slugify(profile.name)}-nordfiber-scope-{label}-a4-landscape.pdf"
        open(os.path.join(OUT, name), "wb").write(pdf)
        print(f"{name:85} pages={rep.pages} segments={len(out.segments)} fits={rep.fits}")
