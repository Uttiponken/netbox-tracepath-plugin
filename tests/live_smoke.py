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

print("== print profiles and the choice of facts")
from netbox_trace_print.fields import ALL_KEYS, PROFILES
from netbox_trace_print.models import PrintProfile
check("the five built-in profiles were seeded", PrintProfile.objects.count() >= 5
      and {n for n, _d, _k in PROFILES} <= set(PrintProfile.objects.values_list("name", flat=True)))
tech = PrintProfile.objects.get(name="Field technician")
check("a profile's facts match the built-in definition", set(tech.keys) == set(dict((n, k) for n, _d, k in PROFILES)["Field technician"]))
r = c.get("/plugins/trace-print/profiles/", HTTP_HOST=HOST)
check("profile list 200 and shows the profiles", r.status_code == 200 and b"Field technician" in r.content and b"Customer-safe" in r.content, r.status_code)
r = c.get(f"/plugins/trace-print/profiles/{tech.pk}/", HTTP_HOST=HOST)
check("profile detail 200", r.status_code == 200 and b"Serial number" in r.content, r.status_code)
r = c.get("/plugins/trace-print/profiles/add/", HTTP_HOST=HOST)
check("profile add form 200 with a checkbox group per catalogue group", r.status_code == 200 and r.content.count(b"keys_") >= 7, r.status_code)
r = c.post("/plugins/trace-print/profiles/add/", {"name": "tp-smoke", "description": "temp", "keys_cable": ["cable.type"],
                                                 "keys_device": ["device.site", "device.serial"]}, HTTP_HOST=HOST)
mine = PrintProfile.objects.filter(name="tp-smoke").first()
check("profile can be created", r.status_code == 302 and mine is not None and set(mine.keys) == {"cable.type", "device.site", "device.serial"},
      (r.status_code, mine and mine.keys))
r = c.post(f"/plugins/trace-print/profiles/{mine.pk}/edit/", {"name": "tp-smoke", "description": "temp 2", "keys_cable": ["cable.length"]},
           HTTP_HOST=HOST)
mine.refresh_from_db()
check("profile can be edited (facts replaced)", r.status_code == 302 and mine.keys == ["cable.length"] and mine.description == "temp 2", (r.status_code, mine.keys))
r = c.get(f"/plugins/trace-print/profiles/{mine.pk}/changelog/", HTTP_HOST=HOST)
check("profile changes are logged", r.status_code == 200, r.status_code)

base = f"/plugins/trace-print/interface/{iface.pk}/"
r = c.get(base + f"?profile={tech.pk}&apply=1", HTTP_HOST=HOST)
body = r.content.decode()
check("choosing a profile ticks exactly its facts", r.status_code == 200 and 'value="device.serial" id="f-device.serial" checked' in body
      and 'value="device.ipv4" id="f-device.ipv4" checked' not in body and "Layout: Field technician" in body, r.status_code)
r = c.get(base + f"?profile={tech.pk}&custom=1&fields=device.serial", HTTP_HOST=HOST)
check("an adjusted selection is named as such", b"Field technician (adjusted)" in r.content)
r = c.get(base + "?custom=1", HTTP_HOST=HOST)
check("ticking nothing is respected", r.status_code == 200 and b"0 of" in r.content and b"Custom selection" in r.content)
r = c.get(base + "?custom=1&fields=device.serial&fields=not.a.key", HTTP_HOST=HOST)
check("unknown keys are ignored", r.status_code == 200 and b"1 of" in r.content)

import re as _re
def pdf_text(query):
    resp = c.get(base + "pdf/" + query, HTTP_HOST=HOST)
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF"), resp.status_code
    return resp.content
full = pdf_text("?profile=&custom=1&" + "&".join("fields=" + k for k in ALL_KEYS))
cust = pdf_text(f"?profile={PrintProfile.objects.get(name='Customer-safe').pk}")
check("customer-safe print is smaller than the full one", len(cust) < len(full), (len(cust), len(full)))
r = c.get(base + "pdf/?prepared_for=" + "J.+Smith", HTTP_HOST=HOST)
check("prepared-for is accepted", r.status_code == 200)
check("print page links to the profiles", b"Print profiles" in c.get("/plugins/trace-print/", HTTP_HOST=HOST).content)
mine.delete()
check("profile can be deleted", not PrintProfile.objects.filter(name="tp-smoke").exists())

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
