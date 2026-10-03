"""
Smoke test of the web pages against the running NetBox. Run inside the container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-trace-print/tests/live_smoke.py').read())"

It creates a throw-away restricted user and permissions and removes them again.
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from circuits.models import CircuitTermination
from dcim.models import Cable, Device, FrontPort, Interface
from users.models import ObjectPermission

User = get_user_model()
HOST = "localhost"
fails = []


def check(name, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


admin = User.objects.get(username="demo-loader")
iface = Interface.objects.get(device__name="polaris-sto-sw-01", name="Ethernet49")
fp = FrontPort.objects.get(device__name="sto-patch-01", name="Port 4")
ct = CircuitTermination.objects.get(circuit__cid="NF-BRG-0001", term_side="Z")

c = Client()
c.force_login(admin)
print("== administrator")
r = c.get("/plugins/trace-print/", HTTP_HOST=HOST)
check("index 200", r.status_code == 200 and b"Interface" in r.content and b"Circuit termination" in r.content, r.status_code)
r = c.get("/plugins/trace-print/interface/", HTTP_HOST=HOST)
check("picker 200 with a selector", r.status_code == 200 and b"name=\"object\"" in r.content, r.status_code)
r = c.get(f"/plugins/trace-print/interface/?object={iface.pk}", HTTP_HOST=HOST)
check("picker redirects to the print page", r.status_code == 302 and r["Location"].endswith(f"/interface/{iface.pk}/"), (r.status_code, r.get("Location")))
r = c.get(f"/plugins/trace-print/interface/{iface.pk}/", HTTP_HOST=HOST)
check("print page 200 embeds the pdf", r.status_code == 200 and b"application/pdf" in r.content and b"/pdf/" in r.content, r.status_code)
r = c.get(f"/plugins/trace-print/interface/{iface.pk}/pdf/", HTTP_HOST=HOST)
check("pdf is a pdf, inline", r.status_code == 200 and r.content.startswith(b"%PDF") and r["Content-Type"] == "application/pdf"
      and r["Content-Disposition"].startswith("inline"), (r.status_code, r.get("Content-Disposition")))
r = c.get(f"/plugins/trace-print/interface/{iface.pk}/pdf/?download=1&paper=A3&orientation=portrait", HTTP_HOST=HOST)
check("download as attachment, A3 portrait", r.status_code == 200 and r["Content-Disposition"].startswith("attachment")
      and b"/MediaBox [0 0 841.89 1190.551]" in r.content, r.get("Content-Disposition"))
r = c.get(f"/plugins/trace-print/interface/{iface.pk}/pdf/?paper=Folio", HTTP_HOST=HOST)
check("invalid paper falls back to the default instead of failing", r.status_code == 200 and b"/MediaBox [0 0 841.89 595.276]" in r.content, r.status_code)
r = c.get(f"/plugins/trace-print/front-port/{fp.pk}/", HTTP_HOST=HOST)
check("front port with two paths offers a path choice", r.status_code == 200 and b"name=\"path\"" in r.content and b"type=\"hidden\"" not in r.content.split(b"name=\"path\"")[0][-200:], r.status_code)
paths = fp.cable and __import__("netbox_trace_print.collect", fromlist=["x"]).paths_through(fp)
check("front port really has 2 paths", len(paths) == 2, len(paths))
r = c.get(f"/plugins/trace-print/front-port/{fp.pk}/pdf/?path={paths[1].pk}", HTTP_HOST=HOST)
check("second path renders", r.status_code == 200 and r.content.startswith(b"%PDF"))
r = c.get(f"/plugins/trace-print/circuit-termination/{ct.pk}/pdf/", HTTP_HOST=HOST)
check("circuit termination renders", r.status_code == 200 and r.content.startswith(b"%PDF"))
check("unknown kind is 404", c.get("/plugins/trace-print/server/", HTTP_HOST=HOST).status_code == 404)
check("unknown object is 404", c.get("/plugins/trace-print/interface/99999999/", HTTP_HOST=HOST).status_code == 404)
unconnected = Interface.objects.filter(cable__isnull=True, mgmt_only=False).first()
r = c.get(f"/plugins/trace-print/interface/{unconnected.pk}/", HTTP_HOST=HOST)
check("object without a path says so and offers no pdf", r.status_code == 200 and b"No cable path" in r.content and b"<object" not in r.content, r.status_code)
check("its pdf url is 404", c.get(f"/plugins/trace-print/interface/{unconnected.pk}/pdf/", HTTP_HOST=HOST).status_code == 404)

print("== a user with no permissions")
nobody = User.objects.create(username="tp-nobody")
perm = None
try:
    c2 = Client()
    c2.force_login(nobody)
    check("index is refused", c2.get("/plugins/trace-print/", HTTP_HOST=HOST).status_code in (302, 403))
    check("pdf is refused", c2.get(f"/plugins/trace-print/interface/{iface.pk}/pdf/", HTTP_HOST=HOST).status_code in (302, 403))

    print("== a user who may view cables and interfaces but not devices")
    perm = ObjectPermission.objects.create(name="tp-test", actions=["view"])
    perm.object_types.set([ContentType.objects.get_for_model(m) for m in (Cable, Interface)])
    perm.users.add(nobody)
    r = c2.get(f"/plugins/trace-print/interface/{iface.pk}/pdf/", HTTP_HOST=HOST)
    check("pdf works", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    from netbox_trace_print.collect import Collector, paths_through
    doc = Collector(nobody).trace_doc(paths_through(iface)[0])
    check("devices are shown by name only", all(b.kind == "restricted" and not b.fields for b in doc.blocks),
          [(b.title, b.kind) for b in doc.blocks])
    check("cables are still described", any(c_.fields for lk in doc.links for c_ in lk.cables))
    check("device names appear but no serial numbers leak",
          all(not any(f.label == "Serial" for f in b.fields) for b in doc.blocks))
    r = c2.get(f"/plugins/trace-print/front-port/{fp.pk}/", HTTP_HOST=HOST)
    check("front ports are refused (no view permission on them)", r.status_code in (302, 403), r.status_code)
finally:
    if perm:
        perm.delete()
    nobody.delete()

print(f"\n{'ALL OK' if not fails else 'FAILED: ' + ', '.join(fails)}")
