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
check("the start page is the print page with nothing chosen: hint on the left, picker on the right, no options yet",
      b"Choose what to trace in the menu on the right" in r.content and b"<object" not in r.content
      and b'name="paper"' not in r.content and b"order-xl-2" in r.content, r.status_code)
r = c.get("/plugins/trace-print/interface/", HTTP_HOST=HOST)
check("picker address redirects to the start page", r.status_code == 302, r.status_code)
r = c.get(f"/plugins/trace-print/interface/?object={iface.pk}", HTTP_HOST=HOST)
check("picker redirects to the print page", r.status_code == 302 and r["Location"].endswith(f"/interface/{iface.pk}/"), (r.status_code, r.get("Location")))
r = c.get(f"/plugins/trace-print/interface/{iface.pk}/", HTTP_HOST=HOST)
check("print page 200 embeds the pdf", r.status_code == 200 and b"application/pdf" in r.content and b"/pdf/" in r.content, r.status_code)
check("the preview is on the left (first in the page), the options on the right",
      r.content.index(b"<object") < r.content.index(b'name="paper"') and b"order-xl-1" in r.content.split(b"<object")[0][-400:])
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
page = c.get(f"/plugins/trace-print/front-port/{fp.pk}/", HTTP_HOST=HOST).content.decode()
check("the two directions are named by equipment and port, in both orders",
      "polaris-sto-sw-01 : Ethernet49 → sto-sw-01 : Ethernet2" in page and "sto-sw-01 : Ethernet2 → polaris-sto-sw-01 : Ethernet49" in page
      and "5 cables" in page, [l for l in page.splitlines() if "→" in l][:3])
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

print("== choosing what to trace")
from dcim.models import Cable
cable = Cable.objects.get(label="sto-cbl-00016")
r = c.get("/plugins/trace-print/", HTTP_HOST=HOST)
body = r.content.decode()
check("start page has a button for every kind, including Cable", all(f">{k}<" in body.replace("\n", "").replace(" ", "") or k in body for k in ("Cable", "Interface", "Front port", "Rear port", "Circuit termination")))
check("one dropdown per kind, below the buttons, on the same page", body.count('data-bs-toggle="pill"') == 5 and body.count('class="tab-pane') == 5, body.count('data-bs-toggle="pill"'))
check("the dropdowns only ask NetBox for objects that have a cable", body.count("cabled") >= 4)
check("a kind can be opened directly", 'nav-link border active' in c.get("/plugins/trace-print/?kind=rear-port", HTTP_HOST=HOST).content.decode())
r = c.get(f"/plugins/trace-print/cable/?object={cable.pk}", HTTP_HOST=HOST)
check("a cable can be chosen", r.status_code == 302 and r["Location"].endswith(f"/cable/{cable.pk}/"), (r.status_code, r.get("Location")))
r = c.get(f"/plugins/trace-print/cable/{cable.pk}/", HTTP_HOST=HOST)
check("print page for a cable offers both directions", r.status_code == 200 and b"name=\"path\"" in r.content, r.status_code)
r = c.get(f"/plugins/trace-print/cable/{cable.pk}/pdf/", HTTP_HOST=HOST)
check("a cable's trace is a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
page = c.get(f"/plugins/trace-print/interface/{iface.pk}/", HTTP_HOST=HOST).content.decode()
check("the print page has the selectors too, with the current object", "pick-interface" in page and f'value="{iface.pk}"' in page and page.count('action="/plugins/trace-print/') >= 5, page.count("<form"))
uncabled_if = Interface.objects.filter(cable__isnull=True, mgmt_only=False).first()
r = c.get(f"/plugins/trace-print/interface/?object={uncabled_if.pk}", HTTP_HOST=HOST)
check("an object without a cable is refused and sent back", r.status_code == 302 and "?kind=interface" in r["Location"], (r.status_code, r.get("Location")))
r = c.get("/plugins/trace-print/interface/", HTTP_HOST=HOST)
check("the old picker address leads back to the start page", r.status_code == 302 and "?kind=interface" in r["Location"])

print("== print profiles and the choice of facts")
from netbox_trace_print.fields import ALL_KEYS, PROFILES
from netbox_trace_print.models import PrintProfile
check("the five built-in profiles were seeded", PrintProfile.objects.count() >= 5
      and {n for n, _d, _k in PROFILES} <= set(PrintProfile.objects.values_list("name", flat=True)))
tech = PrintProfile.objects.get(name="Field technician")
check("a profile's facts are the built-in definition, plus the plugin facts added by migration 0003",
      set(dict((n, k) for n, _d, k in PROFILES)["Field technician"]) <= set(tech.keys)
      and all(k.startswith(("fms.", "wdm.")) for k in set(tech.keys) - set(dict((n, k) for n, _d, k in PROFILES)["Field technician"])))
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

print("== other plugins: FMS and WDM")
from netbox_trace_print import catalogue, integrations
from netbox_trace_print.collect import Collector, paths_through


def all_fields(doc):
    for b in doc.blocks:
        yield from b.fields
        for row in b.ports:
            yield from row.in_fields
            yield from row.out_fields
    for lk in doc.links:
        for cb in lk.cables:
            yield from cb.fields


dcp = Interface.objects.get(device__name="sto-dcp2-01", name="Line/2/1")
doc = Collector(admin).trace_doc(paths_through(dcp)[0])
facts = {f.key: f.value for f in all_fields(doc) if f.key.startswith(("fms.", "wdm."))}
check("both integrations are installed and active here", set(integrations.active()) == {"fms", "wdm"}, integrations.active())
check("the catalogue offers both groups", {"fms", "wdm"} <= {g for g, _l, _i in catalogue.groups()})
check("a cable shows its fiber-plant record", facts.get("fms.type") == "Corning ALTOS Loose Tube 24F SM" and facts.get("fms.serial", "").startswith("CNG-ALTOS24-")
      and "24 · loose tube" in facts.get("fms.fibers", "") and facts.get("fms.marks", "").startswith("0 – ") and "m" in facts.get("fms.marks", ""), facts)
check("the install date and installer are shown", any(f.key == "fms.installed" and "20" in f.value for f in all_fields(doc)))
check("a muxponder port shows channel, wavelength and service", facts.get("wdm.channel", "").startswith("C22 (") and "Baltic Retail Group Backup" in facts.get("wdm.service", ""), facts)
check("a muxponder block says it is a WDM node", any(f.key == "wdm.node" for b in doc.blocks for f in b.fields))
check("a line port shows its role", "wdm.line" in facts, sorted(facts))

page = c.get(f"/plugins/trace-print/interface/{dcp.pk}/", HTTP_HOST=HOST).content.decode()
check("the print page offers the plugin facts as choices", 'value="fms.serial"' in page and 'value="wdm.channel"' in page)
from netbox_trace_print.models import PrintProfile as _P
check("the built-in profiles got the plugin facts (customer-safe none)", "fms.type" in _P.objects.get(name="Full information").keys
      and "wdm.service" in _P.objects.get(name="Field technician").keys and not [k for k in _P.objects.get(name="Customer-safe").keys if k.startswith(("fms.", "wdm."))])

integrations.DISABLED.update({"fms", "wdm"})
try:
    doc_off = Collector(admin).trace_doc(paths_through(dcp)[0])
    check("with the integrations switched off nothing from them is printed",
          not [f for f in all_fields(doc_off) if f.key.startswith(("fms.", "wdm."))])
    check("and the catalogue loses their groups", {"fms", "wdm"}.isdisjoint({g for g, _l, _i in catalogue.groups()}))
    r = c.get(f"/plugins/trace-print/interface/{dcp.pk}/pdf/", HTTP_HOST=HOST)
    check("the pdf still renders", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    page_off = c.get(f"/plugins/trace-print/interface/{dcp.pk}/", HTTP_HOST=HOST).content.decode()
    check("a profile that lists the plugin facts still prints (they are ignored)", 'value="fms.serial"' not in page_off)
    r = c.get(f"/plugins/trace-print/profiles/{_P.objects.get(name='Full information').pk}/", HTTP_HOST=HOST)
    check("its profile page names them as unknown instead of failing", r.status_code == 200 and b"no longer knows" in r.content, r.status_code)
finally:
    integrations.DISABLED.clear()

print("== extending a trace")
from netbox_trace_print.extend import Chain

srv = Interface.objects.get(device__name="baltic-retail-sto-srv-01", name="Gig-E 1")
pid = lambda dev, name: Interface.objects.get(device__name=dev, name=name).pk
chain_after = [("baltic-retail-sto-sw-01", "Ethernet49"), ("sto-sw-01", "Ethernet1"), ("sto-rtr-01", "et-0/0/0"),
               ("mma-rtr-01", "xe-0/1/0"), ("mma-sw-01", "Ethernet2"), ("baltic-retail-mma-sw-01", "Ethernet1")]
base_url = f"/plugins/trace-print/interface/{srv.pk}/"
r = c.get(base_url, HTTP_HOST=HOST)
check("the extension card is there but closed (no cost until asked)", b"Extend the trace" in r.content and b"Show connections to add" in r.content
      and b"after=" not in r.content)
r = c.get(base_url + "?extend=1", HTTP_HOST=HOST)
body = r.content.decode()
check("opened, it lists the other ports on the end equipment, grouped by where they lead",
      "At the end: baltic-retail-sto-sw-01" in body and "sto-sw-01" in body and "after=" in body and "Ethernet49" in body, r.status_code)
check("and the start equipment, which has the iDRAC/management port to the OOB switch", "At the start: baltic-retail-sto-srv-01" in body and "sto-oob-01" in body)

base = paths_through(srv)[0]
user = admin
chain = Chain(user, base, after=[pid(*x) for x in chain_after])
check("all six extensions are accepted", len(chain.after) == 6, len(chain.after))
col = Collector(user)
doc = col.chain_doc(chain.parts(col), origin_label="x")
check("server to server: 17 blocks, 16 cables", len(doc.blocks) == 17 and sum(len(l.cables) for l in doc.links) == 16,
      (len(doc.blocks), sum(len(l.cables) for l in doc.links)))
check("it starts and ends on the two servers", doc.blocks[0].title == "baltic-retail-sto-srv-01" and doc.blocks[-1].title == "baltic-retail-mma-srv-01")
check("the equipment where traces meet is drawn once, arriving on one port and leaving on another",
      [(r_.in_name, r_.out_name) for r_ in doc.blocks[1].ports] == [("Ethernet1", "Ethernet49")]
      and [(r_.in_name, r_.out_name) for r_ in doc.blocks[8].ports] == [("Termination A", "Termination Z")])
check("the summary is for the whole chain", "From baltic-retail-sto-srv-01 : Gig-E 1   to   baltic-retail-mma-srv-01 : Gig-E 1" in doc.summary[0]
      and "16 cables" in doc.summary[1] and "path complete" in doc.summary[1] and "Circuit NF-BRG-0001" in doc.title, doc.summary)
check("it says it joins the traces", any("joins 7 traces" in n for n in doc.notes))
q = "&".join("after=" + str(pid(*x)) for x in chain_after)
r = c.get(base_url + "pdf/?" + q, HTTP_HOST=HOST)
check("the chain prints as a pdf (several pages)", r.status_code == 200 and r.content.startswith(b"%PDF") and r.content.count(b"/Type /Page ") >= 2, r.status_code)
page = c.get(base_url + "?extend=1&" + q, HTTP_HOST=HOST).content.decode()
check("the page keeps the extensions in its pdf link and options form", page.count("after=") >= 6 and page.count('name="after"') == 6 and "remove" in page, page.count('name="after"'))
check("and offers to remove the last one only", page.count(">remove<") == 1)

check("a port that is not on the end equipment is ignored", len(Chain(user, base, after=[pid("sto-rtr-02", "xe-0/1/0")]).after) == 0)
check("nonsense ids are ignored", len(Chain(user, base, after=["99999999", "abc"], before=["x"]).after) == 0)
check("a port that is already part of the trace cannot be added again", len(Chain(user, base, after=[pid("baltic-retail-sto-sw-01", "Ethernet1")]).after) == 0)

ct_base = paths_through(Interface.objects.get(device__name="sto-rtr-01", name="et-0/0/0"))[0]
bchain = Chain(user, ct_base, before=[pid("sto-rtr-01", "xe-0/1/0"), pid("sto-sw-01", "Ethernet3")])
check("extending at the start works too, in two steps", len(bchain.before) == 2, len(bchain.before))
bdoc = col.chain_doc(bchain.parts(col), origin_label="x")
check("turned around: it starts on the Baltic Retail switch and reads towards the circuit",
      [b.title for b in bdoc.blocks][:3] == ["baltic-retail-sto-sw-01", "baltic-retail-sto-tor-01", "sto-mmr-baltic-retail-01"]
      and [b.title for b in bdoc.blocks][-3:] == ["sto-rtr-01", "NF-BRG-0001", "mma-rtr-01"], [b.title for b in bdoc.blocks])
check("with in and out ports the right way round",
      [(r_.in_name, r_.out_name) for r_ in bdoc.blocks[0].ports] == [("", "Ethernet49")]
      and [(r_.in_name, r_.out_name) for r_ in bdoc.blocks[5].ports] == [("Ethernet3", "Ethernet1")]
      and [(r_.in_name, r_.out_name) for r_ in bdoc.blocks[6].ports] == [("xe-0/1/0", "et-0/0/0")], [[(r_.in_name, r_.out_name) for r_ in b.ports] for b in bdoc.blocks])
both = Chain(user, ct_base, before=[pid("sto-rtr-01", "xe-0/1/0")], after=[pid("mma-rtr-01", "xe-0/1/0")])
check("both ends at once", len(both.before) == 1 and len(both.after) == 1)

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
