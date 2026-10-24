"""
Smoke test of the web pages against a running NetBox that has this plugin installed. It needs no data and no other
plugin: it seeds a small network of its own (objects named tp-seed-*), tests against it and removes everything again,
also when a check fails. Run it inside the NetBox container by piping it into the Django shell:

  manage.py shell < tests/live_smoke.py          (nothing needs to be copied into the container)

or, with the plugin folder mounted into the container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-tracepath-plugin/tests/live_smoke.py').read())"

Ends with ALL OK or a list of the checks that failed.

The seeded network (three sites, each with a location and a rack):

  sw-a:Ethernet1..3 --- pan-a:Port 1..3 ==(Trunk, 3 pairs in use)== pan-b:Port 1..3 --- sw-b:Ethernet1..3
  sw-b:Ethernet4 --- circuit TP-SEED-0001 (A at site b, Z at site a) --- sw-c:Ethernet1;  sw-c:Ethernet6 has no cable
  sw-d:Ethernet1 --- sw-e:Ethernet1, both in site c: a trace that touches neither site a nor site b
"""
import json
import re
import zlib
from urllib.parse import quote_plus

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from circuits.models import Circuit, CircuitTermination, CircuitType, Provider
from dcim.models import (Cable, Device, DeviceRole, DeviceType, FrontPort, FrontPortTemplate, Interface,
                         InterfaceTemplate, Location, Manufacturer, PortTemplateMapping, Rack, RearPort,
                         RearPortTemplate, Site)
from users.models import ObjectPermission

from netbox_tracepath_plugin import catalogue, integrations
from netbox_tracepath_plugin.collect import Collector, kinds, paths_through
from netbox_tracepath_plugin.extend import Chain
from netbox_tracepath_plugin.fields import ALL_KEYS, PROFILES
from netbox_tracepath_plugin.models import PrintProfile
from netbox_tracepath_plugin.scope import apply_scope, scopes_of
from netbox_tracepath_plugin.selection import apply_selection

User = get_user_model()
HOST = "localhost"
P = "tp-seed"
fails = []


def check(name, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def cleanup():
    """Remove everything this script makes; safe to run when nothing exists (also clears a crashed earlier run)."""
    for cable in Cable.objects.filter(label__startswith=P):
        cable.delete()
    Circuit.objects.filter(cid__startswith="TP-SEED").delete()
    Device.objects.filter(name__startswith=P).delete()
    Rack.objects.filter(name__startswith=P.upper()).delete()
    Location.objects.filter(slug__startswith=P).delete()
    Site.objects.filter(slug__startswith=P).delete()
    DeviceType.objects.filter(slug__startswith=P).delete()
    DeviceRole.objects.filter(slug__startswith=P).delete()
    CircuitType.objects.filter(slug__startswith=P).delete()
    Provider.objects.filter(slug__startswith=P).delete()
    Manufacturer.objects.filter(slug__startswith=P).delete()
    PrintProfile.objects.filter(name__startswith=P).delete()
    ObjectPermission.objects.filter(name__startswith=P).delete()
    User.objects.filter(username__startswith=P).delete()


def seed():
    mfr = Manufacturer.objects.create(name=P, slug=P)
    role = DeviceRole.objects.create(name=P, slug=P, color="ff9800")
    sw_t = DeviceType.objects.create(manufacturer=mfr, model=f"{P}-switch", slug=f"{P}-switch", u_height=1)
    for n in range(1, 7):
        InterfaceTemplate.objects.create(device_type=sw_t, name=f"Ethernet{n}", type="1000base-t")
    pan_t = DeviceType.objects.create(manufacturer=mfr, model=f"{P}-panel", slug=f"{P}-panel", u_height=1)
    rear = RearPortTemplate.objects.create(device_type=pan_t, name="Trunk", type="lc", positions=3)
    for n in range(1, 4):
        front = FrontPortTemplate.objects.create(device_type=pan_t, name=f"Port {n}", type="lc")
        PortTemplateMapping.objects.create(front_port=front, front_port_position=1, rear_port=rear, rear_port_position=n)

    sites, racks = {}, {}
    for key in ("a", "b", "c"):
        sites[key] = Site.objects.create(name=f"{P}-site-{key}", slug=f"{P}-site-{key}", status="active")
        loc = Location.objects.create(name=f"{P}-room-{key}", slug=f"{P}-room-{key}", site=sites[key], status="active")
        racks[key] = Rack.objects.create(name=f"{P.upper()}-RACK-{key.upper()}", site=sites[key], location=loc,
                                         status="active", u_height=42)

    def device(name, dtype, site, position):
        return Device.objects.create(name=f"{P}-{name}", device_type=dtype, role=role, site=sites[site],
                                     rack=racks[site], position=position, face="front", status="active",
                                     location=racks[site].location)

    d = {"sw-a": device("sw-a", sw_t, "a", 1), "pan-a": device("pan-a", pan_t, "a", 3),
         "pan-b": device("pan-b", pan_t, "b", 3), "sw-b": device("sw-b", sw_t, "b", 1),
         "sw-c": device("sw-c", sw_t, "a", 5), "sw-d": device("sw-d", sw_t, "c", 1), "sw-e": device("sw-e", sw_t, "c", 3)}

    def port(dev, kind, name):
        return {"if": Interface, "fp": FrontPort, "rp": RearPort}[kind].objects.get(device=d[dev], name=name)

    def cable(label, a, b, length=2):
        cb = Cable(label=f"{P}-{label}", type="smf-os2", color="ffeb3b", length=length, length_unit="m", status="connected",
                   a_terminations=[a], b_terminations=[b])
        cb.full_clean()
        cb.save()
        return cb

    for n in (1, 2, 3):
        cable(f"a{n}", port("sw-a", "if", f"Ethernet{n}"), port("pan-a", "fp", f"Port {n}"))
        cable(f"b{n}", port("pan-b", "fp", f"Port {n}"), port("sw-b", "if", f"Ethernet{n}"))
    cable("trunk", port("pan-a", "rp", "Trunk"), port("pan-b", "rp", "Trunk"), length=30)

    provider = Provider.objects.create(name=P, slug=P)
    ctype = CircuitType.objects.create(name=P, slug=P)
    circuit = Circuit.objects.create(cid="TP-SEED-0001", provider=provider, type=ctype, status="active")
    term_a = CircuitTermination.objects.create(circuit=circuit, term_side="A", termination=sites["b"])
    term_z = CircuitTermination.objects.create(circuit=circuit, term_side="Z", termination=sites["a"])
    cable("circuit-a", port("sw-b", "if", "Ethernet4"), term_a)
    cable("circuit-z", term_z, port("sw-c", "if", "Ethernet1"))
    cable("c1", port("sw-d", "if", "Ethernet1"), port("sw-e", "if", "Ethernet1"))
    return d, sites, racks, term_a, term_z


def chromatic(pdf):
    text = b"".join(zlib.decompress(m.group(1)) for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)
                    if m.group(1)[:1] == b"x").decode("latin-1")
    return [op for op in re.findall(r"(-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+) (?:RG|rg)\b", text) if len(set(op)) > 1]


cleanup()
try:
    d, sites, racks, term_a, term_z = seed()
    admin = User.objects.create(username=f"{P}-admin", is_superuser=True)
    iface = Interface.objects.get(device=d["sw-a"], name="Ethernet1")
    fp = FrontPort.objects.get(device=d["pan-a"], name="Port 1")
    ct = term_z
    uncabled = Interface.objects.get(device=d["sw-c"], name="Ethernet6")
    cable_obj = Cable.objects.get(label=f"{P}-a1")
    trunk = Cable.objects.get(label=f"{P}-trunk")
    c = Client()
    c.force_login(admin)
    active = integrations.active()

    print("== the seeded network")
    check("the first trace runs sw-a to sw-b over four blocks",
          [b.title for b in Collector(admin).trace_doc(paths_through(iface)[0]).blocks]
          == [f"{P}-sw-a", f"{P}-pan-a", f"{P}-pan-b", f"{P}-sw-b"])

    print("== administrator")
    r = c.get("/plugins/tracepath/", HTTP_HOST=HOST)
    check("index 200", r.status_code == 200 and b"Interface" in r.content and b"Circuit termination" in r.content, r.status_code)
    check("the start page is the print page with nothing chosen: hint on the left, picker on the right",
          b"Choose what to trace in the menu on the right" in r.content and b"<object" not in r.content
          and b"order-xl-2" in r.content, r.status_code)
    body = r.content.decode()
    check("the print bar is there from the start, above both columns, with its buttons switched off until something is chosen",
          'id="print-bar"' in body and body.index('id="print-bar"') < body.index("Choose what to trace")
          and all(f'name="{n}"' in body for n in ("profile", "paper", "orientation", "prepared_for"))
          and re.search(r'name="apply"[^>]*\sdisabled', body) and re.search(r'data-bs-target="#facts-panel"[^>]*\sdisabled', body)
          and "Manage profiles" in body and 'id="facts-panel"' not in body, r.status_code)
    r = c.get("/plugins/tracepath/interface/", HTTP_HOST=HOST)
    check("the old picker address leads back to the start page", r.status_code == 302 and "?kind=interface" in r["Location"])
    r = c.get(f"/plugins/tracepath/interface/?object={iface.pk}", HTTP_HOST=HOST)
    check("picker redirects to the print page", r.status_code == 302 and r["Location"].endswith(f"/interface/{iface.pk}/"), (r.status_code, r.get("Location")))
    r = c.get(f"/plugins/tracepath/interface/{iface.pk}/", HTTP_HOST=HOST)
    check("print page 200 embeds the pdf", r.status_code == 200 and b"application/pdf" in r.content and b"/pdf/" in r.content, r.status_code)
    check("the print bar is at the top, then the preview on the left and the menu on the right",
          r.content.index(b'id="print-bar"') < r.content.index(b"<object") and b"order-xl-1" in r.content.split(b"<object")[0][-400:]
          and r.content.index(b'name="paper"') < r.content.index(b"<object") < r.content.index(b"order-xl-2"))
    r = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/", HTTP_HOST=HOST)
    check("pdf is a pdf, inline", r.status_code == 200 and r.content.startswith(b"%PDF") and r["Content-Type"] == "application/pdf"
          and r["Content-Disposition"].startswith("inline"), (r.status_code, r.get("Content-Disposition")))
    r = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?download=1&paper=A3&orientation=portrait", HTTP_HOST=HOST)
    check("download as attachment, A3 portrait", r.status_code == 200 and r["Content-Disposition"].startswith("attachment")
          and b"/MediaBox [0 0 841.89 1190.551]" in r.content, r.get("Content-Disposition"))

    print("== colour or black and white, chosen with the paper")
    page = c.get(f"/plugins/tracepath/interface/{iface.pk}/", HTTP_HOST=HOST).content.decode()
    check("every paper is offered in colour and in black and white",
          all(f"{p} (Color)" in page and f"{p} (B/W)" in page for p in ("A4", "A3", "Letter", "Tabloid")) and 'value="A4:bw"' in page)
    r_c = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4", HTTP_HOST=HOST)
    r_b = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4:bw", HTTP_HOST=HOST)
    check("A4 (Color) prints coloured cables, A4 (B/W) prints grey tones only, on the same A4 landscape page",
          r_c.status_code == r_b.status_code == 200 and chromatic(r_c.content) and not chromatic(r_b.content)
          and b"/MediaBox [0 0 841.89 595.276]" in r_b.content, (r_c.status_code, r_b.status_code))
    cs_id = PrintProfile.objects.get(name="Customer-safe").pk
    check("the colour comes from the paper choice, not from the profile",
          chromatic(c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4&profile={cs_id}", HTTP_HOST=HOST).content)
          and not chromatic(c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4:bw&profile={cs_id}", HTTP_HOST=HOST).content))
    check("the same request gives the same colour every time",
          all(bool(chromatic(c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4", HTTP_HOST=HOST).content)) for _ in range(4)))
    r = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=Folio", HTTP_HOST=HOST)
    check("invalid paper falls back to the default instead of failing", r.status_code == 200 and b"/MediaBox [0 0 841.89 595.276]" in r.content, r.status_code)

    print("== front ports, circuit terminations, objects without a path")
    r = c.get(f"/plugins/tracepath/front-port/{fp.pk}/", HTTP_HOST=HOST)
    check("front port with two paths offers a path choice", r.status_code == 200 and b'name="path"' in r.content
          and b'type="hidden"' not in r.content.split(b'name="path"')[0][-200:], r.status_code)
    paths = paths_through(fp)
    check("front port really has 2 paths", len(paths) == 2, len(paths))
    page = c.get(f"/plugins/tracepath/front-port/{fp.pk}/", HTTP_HOST=HOST).content.decode()
    check("the two directions are named by equipment and port, in both orders",
          f"{P}-sw-a : Ethernet1 → {P}-sw-b : Ethernet1" in page and f"{P}-sw-b : Ethernet1 → {P}-sw-a : Ethernet1" in page
          and "3 cables" in page, [l for l in page.splitlines() if "→" in l][:3])
    r = c.get(f"/plugins/tracepath/front-port/{fp.pk}/pdf/?path={paths[1].pk}", HTTP_HOST=HOST)
    check("second path renders", r.status_code == 200 and r.content.startswith(b"%PDF"))
    r = c.get(f"/plugins/tracepath/circuit-termination/{ct.pk}/pdf/", HTTP_HOST=HOST)
    check("circuit termination renders", r.status_code == 200 and r.content.startswith(b"%PDF"))
    check("unknown kind is 404", c.get("/plugins/tracepath/server/", HTTP_HOST=HOST).status_code == 404)
    check("unknown object is 404", c.get("/plugins/tracepath/interface/99999999/", HTTP_HOST=HOST).status_code == 404)
    r = c.get(f"/plugins/tracepath/interface/{uncabled.pk}/", HTTP_HOST=HOST)
    check("object without a path says so and offers no pdf", r.status_code == 200 and b"No cable path" in r.content and b"<object" not in r.content, r.status_code)
    check("its pdf url is 404", c.get(f"/plugins/tracepath/interface/{uncabled.pk}/pdf/", HTTP_HOST=HOST).status_code == 404)

    print("== choosing what to trace")
    body = c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode()
    check("start page has a button for every kind, including Cable and no Rear port",
          all(k in body for k in ("Cable", "Interface", "Front port", "Circuit termination")) and "Rear port" not in body)
    pills = 4 + (2 if "fms" in active else 0) + (1 if "wdm" in active else 0)
    check("one dropdown per kind, below the buttons, on the same page (the core kinds plus those of the integrations installed)",
          body.count('data-bs-toggle="pill"') == pills and body.count('class="tab-pane') == pills,
          (body.count('data-bs-toggle="pill"'), pills, active))
    check("the port and cable dropdowns get their options from the plugin (equipment : port)",
          all(f'data-url="/plugins/tracepath/options/{k}/"' in body for k in ("interface", "front-port", "cable")))
    check("a kind can be opened directly", "nav-link border active" in c.get("/plugins/tracepath/?kind=front-port", HTTP_HOST=HOST).content.decode())
    check("rear ports are no longer a starting point", c.get("/plugins/tracepath/rear-port/", HTTP_HOST=HOST).status_code == 404)
    r = c.get(f"/plugins/tracepath/cable/?object={cable_obj.pk}", HTTP_HOST=HOST)
    check("a cable can be chosen", r.status_code == 302 and r["Location"].endswith(f"/cable/{cable_obj.pk}/"), (r.status_code, r.get("Location")))
    r = c.get(f"/plugins/tracepath/cable/{cable_obj.pk}/", HTTP_HOST=HOST)
    check("print page for a cable offers both directions", r.status_code == 200 and b'name="path"' in r.content, r.status_code)
    r = c.get(f"/plugins/tracepath/cable/{cable_obj.pk}/pdf/", HTTP_HOST=HOST)
    check("a cable's trace is a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    page = c.get(f"/plugins/tracepath/interface/{iface.pk}/", HTTP_HOST=HOST).content.decode()
    check("the selected interface is shown as 'equipment : port'",
          bool(re.search(rf'<option value="{iface.pk}"[^>]*selected[^>]*>\s*{P}-sw-a : Ethernet1', page)))
    check("the print page has the selectors too, with the current object",
          "pick-interface" in page and f'value="{iface.pk}"' in page and page.count('action="/plugins/tracepath/') >= 4, page.count("<form"))
    r = c.get(f"/plugins/tracepath/interface/?object={uncabled.pk}", HTTP_HOST=HOST)
    check("an object without a cable is refused and sent back", r.status_code == 302 and "?kind=interface" in r["Location"], (r.status_code, r.get("Location")))

    print("== dropdown options, and trunk cables")
    data = json.loads(c.get(f"/plugins/tracepath/options/interface/?q={P}+sw+a+ethernet1", HTTP_HOST=HOST).content)
    check("interface options read 'equipment : port' and are found by either part",
          {x["display"] for x in data["results"]} == {f"{P}-sw-a : Ethernet1"}, data)
    data = json.loads(c.get(f"/plugins/tracepath/options/front-port/?q={P}+pan+a+port+1", HTTP_HOST=HOST).content)
    check("front-port options name the panel, so 'Port 1' is not ambiguous", f"{P}-pan-a : Port 1" in [x["display"] for x in data["results"]], data["results"][:3])
    allfp = json.loads(c.get("/plugins/tracepath/options/front-port/?limit=100", HTTP_HOST=HOST).content)
    check("only cabled front ports are offered", allfp["count"] == FrontPort.objects.filter(cable__isnull=False).count()
          and all(" : " in x["display"] for x in allfp["results"]), allfp["count"])
    data = json.loads(c.get(f"/plugins/tracepath/options/cable/?q={P}-trunk", HTTP_HOST=HOST).content)
    check("cable options show the cable's two ends", data["results"][0]["description"] == f"{P}-pan-a : Trunk ↔ {P}-pan-b : Trunk", data["results"])
    check("options for other kinds do not exist", c.get("/plugins/tracepath/options/rear-port/", HTTP_HOST=HOST).status_code == 404)
    data = json.loads(c.get("/plugins/tracepath/options/interface/?limit=3&offset=2", HTTP_HOST=HOST).content)
    check("paging works", len(data["results"]) == 3 and data["count"] > 3)

    page = c.get(f"/plugins/tracepath/cable/{trunk.pk}/", HTTP_HOST=HOST).content.decode()
    check("a trunk with several pairs asks which pair first, and shows no preview",
          "trunk with 3 pairs in use" in page and "<object" not in page)
    check("the pair and direction choice sits under the cable dropdown in 'What to trace', not in the Paper card",
          page.index('name="path"') > page.index('id="pick-cable"') and page.index('name="path"') > page.index('id="print-bar"')
          and 'form="options-form"' in page and page.count('name="path"') == 1)
    check("it has its own button that submits the whole options form", 'type="submit" form="options-form"' in page and 'id="options-form"' in page)
    check("the choice is grouped by pair, both directions each",
          all(f'<optgroup label="Pair {n}">' in page for n in (1, 2, 3)) and page.count("→") >= 6 and "Pair and direction" in page)
    check("every option names its pair, so it still reads right when the group heading is out of sight",
          all(page.count(f"Pair {n} · ") == 2 for n in (1, 2, 3)), [page.count(f"Pair {n} · ") for n in (1, 2, 3)])
    r = c.get(f"/plugins/tracepath/cable/{trunk.pk}/pdf/", HTTP_HOST=HOST)
    check("its pdf is refused until a pair is chosen", r.status_code == 400, r.status_code)
    tpaths = paths_through(trunk)
    r = c.get(f"/plugins/tracepath/cable/{trunk.pk}/pdf/?path={tpaths[0].pk}", HTTP_HOST=HOST)
    check("a chosen pair prints", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    check("and the page then shows the preview", b"<object" in c.get(f"/plugins/tracepath/cable/{trunk.pk}/?path={tpaths[0].pk}", HTTP_HOST=HOST).content)
    single = Cable.objects.get(label=f"{P}-circuit-a")
    page = c.get(f"/plugins/tracepath/cable/{single.pk}/", HTTP_HOST=HOST).content.decode()
    check("a cable that is not a trunk needs no choice of pair", "<object" in page and "pairs in use" not in page)

    print("== print profiles and the choice of facts")
    check("the five built-in profiles were seeded", PrintProfile.objects.count() >= 5
          and {n for n, _d, _k in PROFILES} <= set(PrintProfile.objects.values_list("name", flat=True)))
    tech = PrintProfile.objects.get(name="Field technician")
    check("a profile's facts are the built-in definition, plus the plugin facts added by migration 0003",
          set(dict((n, k) for n, _d, k in PROFILES)["Field technician"]) <= set(tech.keys)
          and all(k.startswith(("fms.", "wdm.")) for k in set(tech.keys) - set(dict((n, k) for n, _d, k in PROFILES)["Field technician"])))
    r = c.get("/plugins/tracepath/profiles/", HTTP_HOST=HOST)
    check("profile list 200 and shows the profiles", r.status_code == 200 and b"Field technician" in r.content and b"Customer-safe" in r.content, r.status_code)
    r = c.get(f"/plugins/tracepath/profiles/{tech.pk}/", HTTP_HOST=HOST)
    check("profile detail 200", r.status_code == 200 and b"Serial number" in r.content, r.status_code)
    r = c.get("/plugins/tracepath/profiles/add/", HTTP_HOST=HOST)
    check("profile add form 200 with a checkbox group per catalogue group", r.status_code == 200 and r.content.count(b"keys_") >= 5, r.status_code)
    r = c.post("/plugins/tracepath/profiles/add/", {"name": f"{P}-profile", "description": "temp", "keys_cable": ["cable.type"],
                                                     "keys_device": ["device.site", "device.serial"]}, HTTP_HOST=HOST)
    mine = PrintProfile.objects.filter(name=f"{P}-profile").first()
    check("profile can be created", r.status_code == 302 and mine is not None and set(mine.keys) == {"cable.type", "device.site", "device.serial"},
          (r.status_code, mine and mine.keys))
    r = c.post(f"/plugins/tracepath/profiles/{mine.pk}/edit/", {"name": f"{P}-profile", "description": "temp 2", "keys_cable": ["cable.length"]}, HTTP_HOST=HOST)
    mine.refresh_from_db()
    check("profile can be edited (facts replaced)", r.status_code == 302 and mine.keys == ["cable.length"] and mine.description == "temp 2", (r.status_code, mine.keys))
    r = c.get(f"/plugins/tracepath/profiles/{mine.pk}/changelog/", HTTP_HOST=HOST)
    check("profile changes are logged", r.status_code == 200, r.status_code)

    base = f"/plugins/tracepath/interface/{iface.pk}/"
    r = c.get(base + f"?profile={tech.pk}&apply=1", HTTP_HOST=HOST)
    body = r.content.decode()
    check("choosing a profile ticks exactly its facts", r.status_code == 200 and 'value="device.serial" id="f-device.serial" checked' in body
          and 'value="device.ipv4" id="f-device.ipv4" checked' not in body and "Layout: Field technician" in body, r.status_code)
    r = c.get(base + f"?profile={tech.pk}&custom=1&fields=device.serial", HTTP_HOST=HOST)
    check("an adjusted selection is named as such", b"Field technician (adjusted)" in r.content)
    check("the fact choices are in a panel that is closed by default, opened by a Choose facts button; no summary text",
          b'class="collapse w-100" id="facts-panel"' in r.content and b"collapse w-100 show" not in r.content
          and r.content.index(b'data-bs-target="#facts-panel"') < r.content.index(b'name="fields"')
          and b"Choose facts" in r.content and b"(click to choose the facts)" not in r.content and b"facts \xc2\xb7 printed as" not in r.content)
    bar_html = r.content.decode()
    check("the print bar's buttons run Apply profile, Manage profiles, Choose facts, Update, all as high as the fields",
          [bar_html.index(x) for x in ("Apply profile", "Manage profiles", "Choose facts")] == sorted(bar_html.index(x) for x in ("Apply profile", "Manage profiles", "Choose facts"))
          and "#print-bar .btn { height: 40px;" in bar_html)
    check("the short lists are plain selects: no searchable dropdown, so no cursor in a choice and no height changes",
          all(re.search(r'<select name="%s"[^>]*class="[^"]*\bno-ts\b' % n, bar_html) or re.search(r'<select name="%s"[^>]*\bno-ts\b' % n, bar_html)
              for n in ("profile", "paper", "orientation")))
    check("the object selectors get their search box inside the dropdown (TomSelect dropdown_input)", "dropdown_input" in bar_html and "select.api-select" in bar_html)
    check("Enter in a text field does a plain Update: the first submit button of the print bar is not Apply profile",
          r.content.index(b'class="visually-hidden"') < r.content.index(b'name="apply"'))
    r = c.get(base + "?custom=1", HTTP_HOST=HOST)
    check("ticking nothing is respected", r.status_code == 200 and b"0 of" in r.content and b"Custom selection" in r.content)
    r = c.get(base + "?custom=1&fields=device.serial&fields=not.a.key", HTTP_HOST=HOST)
    check("unknown keys are ignored", r.status_code == 200 and b"1 of" in r.content)

    def pdf_bytes(query):
        resp = c.get(base + "pdf/" + query, HTTP_HOST=HOST)
        assert resp.status_code == 200 and resp.content.startswith(b"%PDF"), resp.status_code
        return resp.content
    full = pdf_bytes("?profile=&custom=1&" + "&".join("fields=" + k for k in ALL_KEYS))
    cust = pdf_bytes(f"?profile={PrintProfile.objects.get(name='Customer-safe').pk}")
    check("customer-safe print is smaller than the full one", len(cust) < len(full), (len(cust), len(full)))
    check("prepared-for is accepted", c.get(base + "pdf/?prepared_for=J.+Smith", HTTP_HOST=HOST).status_code == 200)
    from django.urls import reverse
    profiles_url = reverse("plugins:netbox_tracepath_plugin:printprofile_list")
    for name, where in (("start page", "/plugins/tracepath/"), ("print page", base)):
        html = c.get(where, HTTP_HOST=HOST).content.decode()
        button = re.search(r'<a class="([^"]*)" href="([^"]*)">\s*<i class="mdi mdi-cog[^"]*"></i> Manage profiles\s*</a>', html)
        check(f"the print bar has a Manage profiles button to the profile list ({name})",
              bool(button) and button.group(2) == profiles_url and "btn" in button.group(1), button and button.groups())
        check(f"the What to trace card has no footer with the plugin name and version, and there is no page count card ({name})",
              "netbox-tracepath-plugin 0." not in html and "pt text" not in html and "card-footer" not in html.split('id="print-bar"')[-1].split("What to trace")[-1].split("Extend the trace")[0])
        check(f"no template comment text leaks onto the page ({name})", "{#" not in html and "#}" not in html and "{%" not in html)

    print("== print settings survive choosing another object")
    r = c.get(f"/plugins/tracepath/interface/?object={iface.pk}&paper=A3&orientation=portrait&profile={tech.pk}&prepared_for=J.+Smith&junk=1", HTTP_HOST=HOST)
    loc = r.get("Location", "")
    check("the selectors pass paper, orientation, profile and prepared-for on to the print page, and nothing else",
          r.status_code == 302 and loc.startswith(f"/plugins/tracepath/interface/{iface.pk}/?") and "paper=A3" in loc and "orientation=portrait" in loc
          and f"profile={tech.pk}" in loc and "prepared_for=J." in loc and "junk" not in loc, loc)
    page = c.get(loc, HTTP_HOST=HOST).content.decode()
    check("and the print bar shows them", re.search(r'<option value="A3"\s+selected', page) and re.search(r'<option value="portrait"\s+selected', page)
          and 'value="J. Smith"' in page and re.search(r'<option value="%d"\s+selected' % tech.pk, page))
    check("a page opened with only some options shows the defaults for the rest (A4, landscape), not the first choice",
          re.search(r'<option value="A4"\s+selected', c.get(base + f"?profile={tech.pk}", HTTP_HOST=HOST).content.decode()))
    r = c.get("/plugins/tracepath/interface/?object=999999999&paper=A3", HTTP_HOST=HOST)
    check("a refused choice goes back to the start page, keeping the settings", r.status_code == 302 and "kind=interface" in r["Location"] and "paper=A3" in r["Location"], r.get("Location"))
    start = c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode()
    check("the selectors carry the settings on with a few lines of script", "form.tp-pick" in start and 'class="tp-pick"' in start)
    mine.delete()
    check("profile can be deleted", not PrintProfile.objects.filter(name=f"{P}-profile").exists())

    print("== optional integrations (netbox-fms, netbox-wdm) are switched off cleanly")
    check("the integrations are a subset of the two the plugin knows", set(active) <= {"fms", "wdm"}, active)
    integrations.DISABLED.update({"fms", "wdm"})
    try:
        doc_off = Collector(admin).trace_doc(paths_through(iface)[0])
        check("with the integrations switched off nothing from them is printed", not [
            f for b in doc_off.blocks for f in b.fields if f.key.startswith(("fms.", "wdm."))])
        check("and the catalogue loses their groups", {"fms", "wdm"}.isdisjoint({g for g, _l, _i in catalogue.groups()}))
        check("the pdf still renders", c.get(base + "pdf/", HTTP_HOST=HOST).status_code == 200)
        off_start = c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode()
        check("and the start page offers only the four core kinds", off_start.count('data-bs-toggle="pill"') == 4
              and "Fiber circuit (FMS)" not in off_start and "WDM circuit" not in off_start)
        check("a profile that lists the plugin facts still prints (they are ignored)", 'value="fms.serial"' not in c.get(base, HTTP_HOST=HOST).content.decode())
    finally:
        integrations.DISABLED.clear()
    check("with them back, the kinds are back", set(kinds()) >= {"cable", "interface", "front-port", "circuit-termination"} | {
        k for n in active for k in getattr(integrations.MODULES[n], "KINDS", {})})

    print("== extending a trace")
    base_url = f"/plugins/tracepath/interface/{iface.pk}/"
    r = c.get(base_url, HTTP_HOST=HOST)
    check("the extension card is there but closed (no cost until asked)", b"Extend the trace" in r.content and b"Show connections to add" in r.content
          and b"after=" not in r.content)
    sw_b4 = Interface.objects.get(device=d["sw-b"], name="Ethernet4")
    r = c.get(base_url + "?extend=1", HTTP_HOST=HOST)
    body = r.content.decode()
    check("opened, it lists the other ports on the end equipment, grouped by where they lead",
          f"At the end: {P}-sw-b" in body and f"{P}-sw-c" in body and "after=" in body and "Ethernet4" in body, r.status_code)
    check("and the start equipment", f"At the start: {P}-sw-a" in body)
    card = body[body.index("Extend the trace"):]
    card = card[:card.index("Limit the print to")] if "Limit the print to" in card else card
    heads = re.findall(r'<h3 class="([^"]*)">(At the (?:start|end)[^<]*)</h3>', card)
    check("the At the start / At the end headings are larger than the equipment headings below them, with a line between the two sections",
          len(heads) == 2 and all("fs-5" in cls and "fw-bold" in cls for cls, _t in heads) and 'class="small fw-bold mt-2"' in card
          and card.count('<hr class="my-3">') == 1 and card.index(heads[0][1]) < card.index('<hr class="my-3">') < card.index(heads[1][1]), heads)
    first = paths_through(iface)[0]
    chain = Chain(admin, first, after=[sw_b4.pk])
    check("an extension on the end equipment is accepted", len(chain.after) == 1, len(chain.after))
    col = Collector(admin)
    doc = col.chain_doc(chain.parts(col), origin_label="x")
    titles = [b.title for b in doc.blocks]
    check("the extended trace goes on through the circuit to the far switch",
          titles[0] == f"{P}-sw-a" and titles[-1] == f"{P}-sw-c" and any("TP-SEED-0001" in t for t in titles), titles)
    check("the equipment where traces meet is drawn once, arriving on one port and leaving on another",
          [(r_.in_name, r_.out_name) for r_ in doc.blocks[3].ports] == [("Ethernet1", "Ethernet4")], [(r_.in_name, r_.out_name) for r_ in doc.blocks[3].ports])
    check("it says it joins the traces", any("joins 2 traces" in n for n in doc.notes), doc.notes)
    q = f"after={sw_b4.pk}"
    r = c.get(base_url + "pdf/?" + q, HTTP_HOST=HOST)
    check("the chain prints as a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    page = c.get(base_url + "?extend=1&" + q, HTTP_HOST=HOST).content.decode()
    check("the page keeps the extension in its pdf link and options form, and offers to remove the last one only",
          page.count("after=") >= 2 and page.count('name="after"') == 1 and page.count(">remove<") == 1, page.count('name="after"'))
    check("a port that is not on the end equipment is ignored", len(Chain(admin, first, after=[Interface.objects.get(device=d["sw-c"], name="Ethernet1").pk]).after) == 0)
    check("nonsense ids are ignored", len(Chain(admin, first, after=["99999999", "abc"], before=["x"]).after) == 0)
    check("a port that is already part of the trace cannot be added again", len(Chain(admin, first, after=[Interface.objects.get(device=d["sw-b"], name="Ethernet1").pk]).after) == 0)

    print("== scoped prints")
    base_url = f"/plugins/tracepath/interface/{iface.pk}/"
    full_doc = Collector(admin).trace_doc(paths_through(iface)[0])
    found = scopes_of(full_doc)
    labels = [x["label"] for x in found]
    check("the scopes are the places the path passes through, sites first",
          [l for l in labels if l.startswith("Site: ")] == [f"Site: {P}-site-a", f"Site: {P}-site-b"]
          and labels == sorted(labels, key=lambda l: ["Sit", "Loc", "Rac"].index(l[:3])) and any(l.endswith(f"{P.upper()}-RACK-B") for l in labels), labels)
    rack_b = next(x["value"] for x in found if x["label"].endswith(f"{P.upper()}-RACK-B"))
    dd = apply_scope(full_doc, rack_b)
    inner = [b for b in dd.blocks if not b.kind.startswith("edge")]
    check("a rack scope keeps that rack's blocks and an edge marker where the path comes in",
          dd.blocks[0].kind == "edge-in" and dd.blocks[-1].kind != "edge-out" and len(dd.segments) == 1 and len(inner) == 2
          and all(b.rack == f"{P.upper()}-RACK-B" for b in inner) and len(dd.links) == len(dd.blocks) - 1, [(b.kind, b.title) for b in dd.blocks])
    check("  the marker names the equipment just outside, with its port",
          dd.blocks[0].title == f"{P}-pan-a" and dd.blocks[0].subtitle == f"Enters rack {P.upper()}-RACK-B" and dd.blocks[0].ports[0].out_name,
          [(b.subtitle, b.title) for b in dd.blocks[:1]])
    site_a = next(x["value"] for x in found if x["label"] == f"Site: {P}-site-a")
    dd = apply_scope(full_doc, site_a)
    check("a site scope ends at the border with a marker for the equipment in the other site",
          dd.blocks[0].kind != "edge-in" and dd.blocks[-1].kind == "edge-out" and dd.blocks[-1].site == f"{P}-site-b", dd.blocks[-1].site)
    dd = apply_selection(apply_scope(full_doc, rack_b), set(PrintProfile.objects.get(name="Customer-safe").keys))
    check("a hidden rack is hidden on the markers too (Customer-safe shows the site only), the scope line stays",
          dd.blocks[0].rack == "" and bool(dd.blocks[0].site) and any(l.startswith("Scope:") for l in dd.summary), dd.summary)
    page = c.get(base_url, HTTP_HOST=HOST).content.decode()
    check("the print page offers a Scope card with the places, grouped by kind",
          "Limit the print to" in page and '<optgroup label="Site">' in page and '<optgroup label="Rack">' in page
          and "Whole path" in page and f"{P.upper()}-RACK-B" in page)
    page = c.get(base_url + "?scope=" + quote_plus(rack_b), HTTP_HOST=HOST).content.decode()
    check("a chosen scope is selected and carried to the pdf address",
          re.search(r'<option value="' + re.escape(rack_b) + r'"\s+selected', page) and "scope=rack%3A" in page and "<object" in page)
    check("it prints as a pdf", c.get(base_url + "pdf/?scope=" + quote_plus(rack_b), HTTP_HOST=HOST).status_code == 200)
    pdf_of = lambda html: (re.findall(r'<object data="([^"]*)"', html) or [""])[0]
    bad = c.get(base_url + "?scope=rack%3Anowhere", HTTP_HOST=HOST).content.decode()
    check("an unknown scope is ignored: the whole path prints", pdf_of(bad) and "scope=" not in pdf_of(bad))
    d_if = Interface.objects.get(device=d["sw-d"], name="Ethernet1")
    other = c.get(f"/plugins/tracepath/interface/{d_if.pk}/?scope=" + quote_plus(rack_b), HTTP_HOST=HOST).content.decode()
    check("a scope the trace does not pass through is dropped", pdf_of(other) and "scope=" not in pdf_of(other))

    print("== the Print trace button on NetBox's own pages")
    page_of = lambda obj: c.get(obj.get_absolute_url(), HTTP_HOST=HOST).content.decode()

    def button(html, kind, pk):
        return re.search(r'<a href="/plugins/tracepath/%s/%d/" class="btn btn-primary" title="Print this trace as a PDF">\s*<i class="mdi mdi-printer"></i> Print trace' % (kind, pk), html)
    check("a cable's page has the button, and it opens that cable", button(page_of(cable_obj), "cable", cable_obj.pk))
    check("a cabled interface has it", button(page_of(iface), "interface", iface.pk))
    check("an interface without a cable has none (there is no trace)", "Print trace" not in page_of(uncabled))
    check("a cabled front port has it", button(page_of(fp), "front-port", fp.pk))
    check("a circuit termination with a cable has it", button(page_of(ct), "circuit-termination", ct.pk))
    check("the button leads to a working print page", c.get(f"/plugins/tracepath/cable/{cable_obj.pk}/", HTTP_HOST=HOST).status_code == 200)
    only_if = User.objects.create(username=f"{P}-iface-only")
    perm_i = ObjectPermission.objects.create(name=f"{P}-iface-only", actions=["view"])
    perm_i.object_types.set([ContentType.objects.get_for_model(Interface)])
    perm_i.users.add(only_if)
    c3 = Client()
    c3.force_login(only_if)
    page = c3.get(iface.get_absolute_url(), HTTP_HOST=HOST)
    check("a user who may view interfaces but not cables sees the page without the button",
          page.status_code == 200 and b"Print trace" not in page.content, page.status_code)
    perm_i.object_types.add(ContentType.objects.get_for_model(Cable))
    check("and with permission to view cables the button appears", b"Print trace" in c3.get(iface.get_absolute_url(), HTTP_HOST=HOST).content)

    print("== the optional Print trace column in NetBox's own lists")
    from circuits.tables.circuits import CircuitTerminationTable
    from dcim.tables.cables import CableTable
    from dcim.tables.devices import DeviceFrontPortTable, DeviceInterfaceTable, FrontPortTable, InterfaceTable

    def link(html, kind, pk):
        return re.search(r'href="/plugins/tracepath/%s/%d/" class="btn btn-sm btn-primary" title="Print trace as PDF"' % (kind, pk), html)

    lists = [("cables", CableTable, f"/dcim/cables/?id={cable_obj.pk}", "cable", cable_obj.pk),
             ("interfaces", InterfaceTable, f"/dcim/interfaces/?id={iface.pk}", "interface", iface.pk),
             ("a device's interfaces", DeviceInterfaceTable, f"/dcim/devices/{iface.device_id}/interfaces/?per_page=100", "interface", iface.pk),
             ("front ports", FrontPortTable, f"/dcim/front-ports/?id={fp.pk}", "front-port", fp.pk),
             ("a device's front ports", DeviceFrontPortTable, f"/dcim/devices/{fp.device_id}/front-ports/?per_page=100", "front-port", fp.pk),
             ("circuit terminations", CircuitTerminationTable, f"/circuits/circuit-terminations/?id={ct.pk}", "circuit-termination", ct.pk)]
    for name, table, url, kind, pk in lists:
        key = f"tables.{table.__name__}.columns"
        before = admin.config.get(key)
        try:
            check(f"the column is not shown until a user chooses it ({name})", not link(c.get(url, HTTP_HOST=HOST).content.decode(), kind, pk))
            admin.config.set(key, list(table.Meta.default_columns) + ["print_trace"], commit=True)
            html = c.get(url, HTTP_HOST=HOST).content.decode()
            check(f"chosen under Configure Table, every row has a printer icon that opens it in the print page ({name})", link(html, kind, pk) and "Print trace" in html, url)
        finally:
            if before is None:
                admin.config.clear(key, commit=True)
            else:
                admin.config.set(key, before, commit=True)
    key = "tables.InterfaceTable.columns"
    admin.config.set(key, list(InterfaceTable.Meta.default_columns) + ["print_trace"], commit=True)
    check("an interface without a cable gets no icon", not link(c.get(f"/dcim/interfaces/?id={uncabled.pk}", HTTP_HOST=HOST).content.decode(), "interface", uncabled.pk))
    viewer = User.objects.create(username=f"{P}-col-viewer")
    perm_v = ObjectPermission.objects.create(name=f"{P}-col-viewer", actions=["view"])
    perm_v.object_types.set([ContentType.objects.get_for_model(Interface)])
    perm_v.users.add(viewer)
    viewer.config.set(key, list(InterfaceTable.Meta.default_columns) + ["print_trace"], commit=True)
    c4 = Client()
    c4.force_login(viewer)
    check("a user who may not view cables sees no icon", not link(c4.get(f"/dcim/interfaces/?id={iface.pk}", HTTP_HOST=HOST).content.decode(), "interface", iface.pk))
    from netbox.registry import registry
    check("the column is registered on all six tables", all("print_trace" in registry["tables"][row[1]] for row in lists), [row[1].__name__ for row in lists])

    print("== the equipment's colour as the header background")
    role_doc = Collector(admin).trace_doc(paths_through(iface)[0])
    devices_on_path = {x.name: x for x in Device.objects.filter(name__in=[b.title for b in role_doc.blocks]).select_related("role")}
    check("every block of equipment carries the colour NetBox gives its role",
          role_doc.blocks and all(b.color_hex == devices_on_path[b.title].role.color.lower() and len(b.color_hex) == 6 for b in role_doc.blocks if b.kind == "device"),
          [(b.title, b.color_hex) for b in role_doc.blocks])
    check("and blocks that are not equipment (circuits, sites) have none", all(not b.color_hex for b in Collector(admin).trace_doc(paths_through(ct)[0]).blocks if b.kind != "device"))
    colour_pdf = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4", HTTP_HOST=HOST).content
    bw_pdf = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4:bw", HTTP_HOST=HOST).content
    check("the print is in colour on A4 (Color) and grey only on A4 (B/W)", chromatic(colour_pdf) and not chromatic(bw_pdf))

    print("== a user with no permissions")
    nobody = User.objects.create(username=f"{P}-nobody")
    c2 = Client()
    c2.force_login(nobody)
    check("index is refused", c2.get("/plugins/tracepath/", HTTP_HOST=HOST).status_code in (302, 403))
    check("pdf is refused", c2.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/", HTTP_HOST=HOST).status_code in (302, 403))

    print("== a user who may view cables and interfaces but not devices")
    perm = ObjectPermission.objects.create(name=f"{P}-test", actions=["view"])
    perm.object_types.set([ContentType.objects.get_for_model(m) for m in (Cable, Interface)])
    perm.users.add(nobody)
    r = c2.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/", HTTP_HOST=HOST)
    check("pdf works", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    doc = Collector(nobody).trace_doc(paths_through(iface)[0])
    check("devices are shown by name only", all(b.kind == "restricted" and not b.fields for b in doc.blocks), [(b.title, b.kind) for b in doc.blocks])
    check("cables are still described", any(c_.fields for lk in doc.links for c_ in lk.cables))
    check("device names appear but no serial numbers leak", all(not any(f.label == "Serial" for f in b.fields) for b in doc.blocks))
    r = c2.get(f"/plugins/tracepath/front-port/{fp.pk}/", HTTP_HOST=HOST)
    check("front ports are refused (no view permission on them)", r.status_code in (302, 403), r.status_code)
finally:
    cleanup()

print(f"\n{'ALL OK' if not fails else 'FAILED: ' + ', '.join(fails)}")
