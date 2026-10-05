"""
One real trace printed with every print profile, into samples/<version>/. Run inside the NetBox container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-tracepath-plugin/tests/live_profiles.py').read())"
"""
import os

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from dcim.models import Interface
from netbox_tracepath_plugin import __version__
from netbox_tracepath_plugin.collect import Collector, paths_through
from netbox_tracepath_plugin.layout import LayoutSpec, render
from netbox_tracepath_plugin.models import PrintProfile
from netbox_tracepath_plugin.selection import apply_selection

OUT = f"/opt/netbox/custom-plugins/netbox-tracepath-plugin/samples/{__version__}"
os.makedirs(OUT, exist_ok=True)
user = get_user_model().objects.get(username="demo-loader")

TRACES = {
    "colo-tenant": lambda: Interface.objects.get(device__name="polaris-sto-sw-01", name="Ethernet49"),
    "helsinki-link": lambda: Interface.objects.get(device__name="hel-rtr-01", name="et-0/0/2"),
    "brg-protect-path": lambda: Interface.objects.get(device__name="sto-dcp2-01", name="Line/2/1"),
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


# A trace extended at the end, step by step, from one Baltic Retail server to the other.
from netbox_tracepath_plugin.extend import Chain

pid = lambda dev, name: Interface.objects.get(device__name=dev, name=name).pk
base = paths_through(Interface.objects.get(device__name="baltic-retail-sto-srv-01", name="Gig-E 1"))[0]
chain = Chain(user, base, after=[pid(d, n) for d, n in [
    ("baltic-retail-sto-sw-01", "Ethernet49"), ("sto-sw-01", "Ethernet1"), ("sto-rtr-01", "et-0/0/0"),
    ("mma-rtr-01", "xe-0/1/0"), ("mma-sw-01", "Ethernet2"), ("baltic-retail-mma-sw-01", "Ethernet1")]])
collector = Collector(user)
doc = collector.chain_doc(chain.parts(collector), origin_label="server to server")
for profile in PrintProfile.objects.filter(name__in=["Full information", "Field technician"]):
    out = apply_selection(doc, profile.keys, layout_name=profile.name, prepared_for=RECIPIENT.get(profile.name, ""))
    pdf, rep = render(out, LayoutSpec(paper="A4", orientation="landscape"))
    name = f"{slugify(profile.name)}-nordfiber-server-to-server-extended-a4-landscape.pdf"
    open(os.path.join(OUT, name), "wb").write(pdf)
    print(f"{name:75} pages={rep.pages} cols={rep.columns} fits={rep.fits} blocks={len(doc.blocks)}")
