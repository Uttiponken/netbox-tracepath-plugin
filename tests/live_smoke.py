"""
Smoke test of the web pages against the running NetBox. Run inside the container:

  manage.py shell -c "exec(open('/opt/netbox/custom-plugins/netbox-tracepath-plugin/tests/live_smoke.py').read())"

It creates a throw-away restricted user and permissions and removes them again.
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client
import re as _re2

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
fp = FrontPort.objects.get(device__name="sto-patch-mmr-01", name="Port 1")
ct = CircuitTermination.objects.get(circuit__cid="NF-BRG-0001", term_side="Z")

c = Client()
c.force_login(admin)
import re as _re3
import zlib as _zlib


def _chromatic(pdf):
    text = b"".join(_zlib.decompress(m.group(1)) for m in _re3.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, _re3.S)
                    if m.group(1)[:1] == b"x").decode("latin-1")
    return [op for op in _re3.findall(r"(-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+) (?:RG|rg)\b", text) if len(set(op)) > 1]


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
      and _re2.search(r'name="apply"[^>]*\sdisabled', body) and _re2.search(r'data-bs-target="#facts-panel"[^>]*\sdisabled', body)
      and "Manage profiles" in body and 'id="facts-panel"' not in body, r.status_code)
r = c.get("/plugins/tracepath/interface/", HTTP_HOST=HOST)
check("picker address redirects to the start page", r.status_code == 302, r.status_code)
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
      r_c.status_code == r_b.status_code == 200 and _chromatic(r_c.content) and not _chromatic(r_b.content)
      and b"/MediaBox [0 0 841.89 595.276]" in r_b.content, (r_c.status_code, r_b.status_code))
cs_id = PrintProfile.objects.get(name="Customer-safe").pk
check("the colour comes from the paper choice, not from the profile: Customer-safe (no Colour fact) prints in colour on A4 (Color)",
      _chromatic(c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4&profile={cs_id}", HTTP_HOST=HOST).content)
      and not _chromatic(c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4:bw&profile={cs_id}", HTTP_HOST=HOST).content))
check("the same request gives the same colour every time (no race: what is printed depends only on the request)",
      all(bool(_chromatic(c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4", HTTP_HOST=HOST).content)) for _ in range(4)))
r = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=Folio", HTTP_HOST=HOST)
check("invalid paper falls back to the default instead of failing", r.status_code == 200 and b"/MediaBox [0 0 841.89 595.276]" in r.content, r.status_code)
r = c.get(f"/plugins/tracepath/front-port/{fp.pk}/", HTTP_HOST=HOST)
check("front port with two paths offers a path choice", r.status_code == 200 and b"name=\"path\"" in r.content and b"type=\"hidden\"" not in r.content.split(b"name=\"path\"")[0][-200:], r.status_code)
paths = fp.cable and __import__("netbox_tracepath_plugin.collect", fromlist=["x"]).paths_through(fp)
check("front port really has 2 paths", len(paths) == 2, len(paths))
page = c.get(f"/plugins/tracepath/front-port/{fp.pk}/", HTTP_HOST=HOST).content.decode()
check("the two directions are named by equipment and port, in both orders",
      "polaris-sto-sw-01 : Ethernet49 → sto-sw-01 : Ethernet2" in page and "sto-sw-01 : Ethernet2 → polaris-sto-sw-01 : Ethernet49" in page
      and "5 cables" in page, [l for l in page.splitlines() if "→" in l][:3])
r = c.get(f"/plugins/tracepath/front-port/{fp.pk}/pdf/?path={paths[1].pk}", HTTP_HOST=HOST)
check("second path renders", r.status_code == 200 and r.content.startswith(b"%PDF"))
r = c.get(f"/plugins/tracepath/circuit-termination/{ct.pk}/pdf/", HTTP_HOST=HOST)
check("circuit termination renders", r.status_code == 200 and r.content.startswith(b"%PDF"))
check("unknown kind is 404", c.get("/plugins/tracepath/server/", HTTP_HOST=HOST).status_code == 404)
check("unknown object is 404", c.get("/plugins/tracepath/interface/99999999/", HTTP_HOST=HOST).status_code == 404)
unconnected = Interface.objects.filter(cable__isnull=True, mgmt_only=False).first()
r = c.get(f"/plugins/tracepath/interface/{unconnected.pk}/", HTTP_HOST=HOST)
check("object without a path says so and offers no pdf", r.status_code == 200 and b"No cable path" in r.content and b"<object" not in r.content, r.status_code)
check("its pdf url is 404", c.get(f"/plugins/tracepath/interface/{unconnected.pk}/pdf/", HTTP_HOST=HOST).status_code == 404)

print("== choosing what to trace")
from dcim.models import Cable
cable = Cable.objects.get(label="sto-cbl-00016")
r = c.get("/plugins/tracepath/", HTTP_HOST=HOST)
body = r.content.decode()
check("start page has a button for every kind, including Cable and no Rear port", all(k in body for k in ("Cable", "Interface", "Front port", "Circuit termination")) and "Rear port" not in body)
check("one dropdown per kind, below the buttons, on the same page (core kinds plus FMS and WDM)",
      body.count('data-bs-toggle="pill"') == 7 and body.count('class="tab-pane') == 7 and "WDM circuit" in body
      and "Fiber cable (FMS)" in body and "Fiber circuit (FMS)" in body,
      body.count('data-bs-toggle="pill"'))
check("the port and cable dropdowns get their options from the plugin (equipment : port)",
      all(f'data-url="/plugins/tracepath/options/{k}/"' in body for k in ("interface", "front-port", "cable")))
check("the circuit-termination dropdown only asks NetBox for objects that have a cable", body.count("cabled") >= 1)
check("a kind can be opened directly", 'nav-link border active' in c.get("/plugins/tracepath/?kind=front-port", HTTP_HOST=HOST).content.decode())
check("rear ports are no longer a starting point", c.get("/plugins/tracepath/rear-port/", HTTP_HOST=HOST).status_code == 404)
r = c.get(f"/plugins/tracepath/cable/?object={cable.pk}", HTTP_HOST=HOST)
check("a cable can be chosen", r.status_code == 302 and r["Location"].endswith(f"/cable/{cable.pk}/"), (r.status_code, r.get("Location")))
r = c.get(f"/plugins/tracepath/cable/{cable.pk}/", HTTP_HOST=HOST)
check("print page for a cable offers both directions", r.status_code == 200 and b"name=\"path\"" in r.content, r.status_code)
r = c.get(f"/plugins/tracepath/cable/{cable.pk}/pdf/", HTTP_HOST=HOST)
check("a cable's trace is a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
page = c.get(f"/plugins/tracepath/interface/{iface.pk}/", HTTP_HOST=HOST).content.decode()
import re as _re2
check("the selected interface is shown as 'equipment : port'", bool(_re2.search(rf'<option value="{iface.pk}"[^>]*selected[^>]*>\s*polaris-sto-sw-01 : Ethernet49', page)))
check("the print page has the selectors too, with the current object", "pick-interface" in page and f'value="{iface.pk}"' in page and page.count('action="/plugins/tracepath/') >= 4, page.count("<form"))
uncabled_if = Interface.objects.filter(cable__isnull=True, mgmt_only=False).first()
r = c.get(f"/plugins/tracepath/interface/?object={uncabled_if.pk}", HTTP_HOST=HOST)
check("an object without a cable is refused and sent back", r.status_code == 302 and "?kind=interface" in r["Location"], (r.status_code, r.get("Location")))
r = c.get("/plugins/tracepath/interface/", HTTP_HOST=HOST)
check("the old picker address leads back to the start page", r.status_code == 302 and "?kind=interface" in r["Location"])

print("== dropdown options, and trunk cables")
import json as _json
from netbox_tracepath_plugin.collect import paths_through
r = c.get("/plugins/tracepath/options/interface/?q=polaris+sw+49", HTTP_HOST=HOST)
data = _json.loads(r.content)
check("interface options read 'equipment : port' and are found by either part",
      r.status_code == 200 and {x["display"] for x in data["results"]} == {"polaris-sto-sw-01 : Ethernet49", "polaris-got-sw-01 : Ethernet49"}, data)
data = _json.loads(c.get("/plugins/tracepath/options/front-port/?q=sto-patch-mmr+port+1", HTTP_HOST=HOST).content)
check("front-port options name the panel, so 'Port 1' is no longer ambiguous", "sto-patch-mmr-01 : Port 1" in [x["display"] for x in data["results"]], data["results"][:3])
allfp = _json.loads(c.get("/plugins/tracepath/options/front-port/?limit=100", HTTP_HOST=HOST).content)
check("only cabled front ports are offered", allfp["count"] == FrontPort.objects.filter(cable__isnull=False).count()
      and all(" : " in x["display"] for x in allfp["results"]), allfp["count"])
data = _json.loads(c.get("/plugins/tracepath/options/cable/?q=sto-cbl-00007", HTTP_HOST=HOST).content)
check("cable options show the cable's two ends", data["results"][0]["description"] == "sto-mmr-nordfiber-01 : Trunk ↔ sto-patch-mmr-01 : Trunk", data["results"])
check("options for other kinds do not exist", c.get("/plugins/tracepath/options/rear-port/", HTTP_HOST=HOST).status_code == 404)
data = _json.loads(c.get("/plugins/tracepath/options/interface/?limit=3&offset=2", HTTP_HOST=HOST).content)
check("paging works", len(data["results"]) == 3 and data["count"] > 3)

trunk = Cable.objects.get(label="sto-cbl-00007")           # the MeetMe trunk: four pairs in use
page = c.get(f"/plugins/tracepath/cable/{trunk.pk}/", HTTP_HOST=HOST).content.decode()
check("a trunk with several pairs asks which pair first, and shows no preview",
      "trunk with 4 pairs in use" in page and "<object" not in page)
check("the pair and direction choice sits under the cable dropdown in 'What to trace', not in the Paper card",
      page.index('name="path"') > page.index('id="pick-cable"') and page.index('name="path"') > page.index('id="print-bar"')
      and 'form="options-form"' in page and page.count('name="path"') == 1)
check("it has its own button that submits the whole options form", 'type="submit" form="options-form"' in page and 'id="options-form"' in page)
check("the choice is grouped by pair, both directions each",
      all(f'<optgroup label="Pair {n}">' in page for n in (1, 2, 3, 4)) and page.count("→") >= 8 and "Pair and direction" in page)
check("every option names its pair, so it still reads right when the group heading is out of sight",
      all(page.count(f"Pair {n} · ") == 2 for n in (1, 2, 3, 4)), [page.count(f"Pair {n} · ") for n in (1, 2, 3, 4)])
r = c.get(f"/plugins/tracepath/cable/{trunk.pk}/pdf/", HTTP_HOST=HOST)
check("its pdf is refused until a pair is chosen", r.status_code == 400, r.status_code)
tpaths = paths_through(trunk)
r = c.get(f"/plugins/tracepath/cable/{trunk.pk}/pdf/?path={tpaths[0].pk}", HTTP_HOST=HOST)
check("a chosen pair prints", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
check("and the page then shows the preview", b"<object" in c.get(f"/plugins/tracepath/cable/{trunk.pk}/?path={tpaths[0].pk}", HTTP_HOST=HOST).content)
single = Cable.objects.get(label="bb-cbl-00001")           # one pair in use
page = c.get(f"/plugins/tracepath/cable/{single.pk}/", HTTP_HOST=HOST).content.decode()
check("a trunk with one pair in use needs no choice", "<object" in page and "pairs in use" not in page)

print("== print profiles and the choice of facts")
from netbox_tracepath_plugin.fields import ALL_KEYS, PROFILES
from netbox_tracepath_plugin.models import PrintProfile
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
check("profile add form 200 with a checkbox group per catalogue group", r.status_code == 200 and r.content.count(b"keys_") >= 7, r.status_code)
r = c.post("/plugins/tracepath/profiles/add/", {"name": "tp-smoke", "description": "temp", "keys_cable": ["cable.type"],
                                                 "keys_device": ["device.site", "device.serial"]}, HTTP_HOST=HOST)
mine = PrintProfile.objects.filter(name="tp-smoke").first()
check("profile can be created", r.status_code == 302 and mine is not None and set(mine.keys) == {"cable.type", "device.site", "device.serial"},
      (r.status_code, mine and mine.keys))
r = c.post(f"/plugins/tracepath/profiles/{mine.pk}/edit/", {"name": "tp-smoke", "description": "temp 2", "keys_cable": ["cable.length"]},
           HTTP_HOST=HOST)
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
      all(_re2.search(r'<select name="%s"[^>]*class="[^"]*\bno-ts\b' % n, bar_html) or _re2.search(r'<select name="%s"[^>]*\bno-ts\b' % n, bar_html)
          for n in ("profile", "paper", "orientation")))
check("the object selectors get their search box inside the dropdown (TomSelect dropdown_input)", "dropdown_input" in bar_html and "select.api-select" in bar_html)
check("Enter in a text field does a plain Update: the first submit button of the print bar is not Apply profile",
      r.content.index(b'class="visually-hidden"') < r.content.index(b'name="apply"'))
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
from django.urls import reverse as _reverse
profiles_url = _reverse("plugins:netbox_tracepath_plugin:printprofile_list")
for name, where in (("start page", "/plugins/tracepath/"), ("print page", base)):
    html = c.get(where, HTTP_HOST=HOST).content.decode()
    button = _re2.search(r'<a class="([^"]*)" href="([^"]*)">\s*<i class="mdi mdi-cog[^"]*"></i> Manage profiles\s*</a>', html)
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
check("and the print bar shows them", _re2.search(r'<option value="A3"\s+selected', page) and _re2.search(r'<option value="portrait"\s+selected', page)
      and 'value="J. Smith"' in page and _re2.search(r'<option value="%d"\s+selected' % tech.pk, page))
check("a page opened with only some options shows the defaults for the rest (A4, landscape), not the first choice",
      _re2.search(r'<option value="A4"\s+selected', c.get(base + f"?profile={tech.pk}", HTTP_HOST=HOST).content.decode()))
r = c.get("/plugins/tracepath/interface/?object=999999999&paper=A3", HTTP_HOST=HOST)
check("a refused choice goes back to the start page, keeping the settings", r.status_code == 302 and "kind=interface" in r["Location"] and "paper=A3" in r["Location"], r.get("Location"))
check("the selectors carry the settings on with a few lines of script", "form.tp-pick" in c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode()
      and 'class="tp-pick"' in c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode())
mine.delete()
check("profile can be deleted", not PrintProfile.objects.filter(name="tp-smoke").exists())

print("== other plugins: FMS and WDM")
from netbox_tracepath_plugin import catalogue, integrations
from netbox_tracepath_plugin.collect import Collector, paths_through


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
check("a cable shows its fiber-plant record", facts.get("fms.type") == "Corning ALTOS Loose Tube 48F SM" and facts.get("fms.serial", "").startswith("CNG-ALTOS24-")
      and "48 · loose tube" in facts.get("fms.fibers", "") and facts.get("fms.marks", "").startswith("0 – ") and "m" in facts.get("fms.marks", ""), facts)
check("the install date and installer are shown", any(f.key == "fms.installed" and "20" in f.value for f in all_fields(doc)))
check("a muxponder port shows channel, wavelength and service", facts.get("wdm.channel", "").startswith("C22 (") and "Baltic Retail Group Backup" in facts.get("wdm.service", ""), facts)
check("a muxponder block says it is a WDM node", any(f.key == "wdm.node" for b in doc.blocks for f in b.fields))
check("a line port shows its role", "wdm.line" in facts, sorted(facts))

page = c.get(f"/plugins/tracepath/interface/{dcp.pk}/", HTTP_HOST=HOST).content.decode()
check("the print page offers the plugin facts as choices", 'value="fms.serial"' in page and 'value="wdm.channel"' in page)
from netbox_tracepath_plugin.models import PrintProfile as _P
check("the built-in profiles got the plugin facts (customer-safe none)", "fms.type" in _P.objects.get(name="Full information").keys
      and "wdm.service" in _P.objects.get(name="Field technician").keys and not [k for k in _P.objects.get(name="Customer-safe").keys if k.startswith(("fms.", "wdm."))])

integrations.DISABLED.update({"fms", "wdm"})
try:
    doc_off = Collector(admin).trace_doc(paths_through(dcp)[0])
    check("with the integrations switched off nothing from them is printed",
          not [f for f in all_fields(doc_off) if f.key.startswith(("fms.", "wdm."))])
    check("and the catalogue loses their groups", {"fms", "wdm"}.isdisjoint({g for g, _l, _i in catalogue.groups()}))
    r = c.get(f"/plugins/tracepath/interface/{dcp.pk}/pdf/", HTTP_HOST=HOST)
    check("the pdf still renders", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    page_off = c.get(f"/plugins/tracepath/interface/{dcp.pk}/", HTTP_HOST=HOST).content.decode()
    check("a profile that lists the plugin facts still prints (they are ignored)", 'value="fms.serial"' not in page_off)
    r = c.get(f"/plugins/tracepath/profiles/{_P.objects.get(name='Full information').pk}/", HTTP_HOST=HOST)
    check("its profile page names them as unknown instead of failing", r.status_code == 200 and b"no longer knows" in r.content, r.status_code)
finally:
    integrations.DISABLED.clear()

print("== extending a trace")
from netbox_tracepath_plugin.extend import Chain

srv = Interface.objects.get(device__name="baltic-retail-sto-srv-01", name="Gig-E 1")
pid = lambda dev, name: Interface.objects.get(device__name=dev, name=name).pk
chain_after = [("baltic-retail-sto-sw-01", "Ethernet49"), ("sto-sw-01", "Ethernet1"), ("sto-rtr-01", "et-0/0/0"),
               ("mma-rtr-01", "xe-0/1/0"), ("mma-sw-01", "Ethernet2"), ("baltic-retail-mma-sw-01", "Ethernet1")]
base_url = f"/plugins/tracepath/interface/{srv.pk}/"
r = c.get(base_url, HTTP_HOST=HOST)
check("the extension card is there but closed (no cost until asked)", b"Extend the trace" in r.content and b"Show connections to add" in r.content
      and b"after=" not in r.content)
r = c.get(base_url + "?extend=1", HTTP_HOST=HOST)
body = r.content.decode()
check("opened, it lists the other ports on the end equipment, grouped by where they lead",
      "At the end: baltic-retail-sto-sw-01" in body and "sto-sw-01" in body and "after=" in body and "Ethernet49" in body, r.status_code)
check("and the start equipment, which has the iDRAC/management port to the OOB switch", "At the start: baltic-retail-sto-srv-01" in body and "sto-oob-01" in body)
card = body[body.index("Extend the trace"):]
card = card[:card.index("Limit the print to")] if "Limit the print to" in card else card
heads = [m_ for m_ in __import__("re").findall(r'<h3 class="([^"]*)">(At the (?:start|end)[^<]*)</h3>', card)]
check("the At the start / At the end headings are larger than the equipment headings below them, with a line between the two sections",
      len(heads) == 2 and all("fs-5" in cls and "fw-bold" in cls for cls, _t in heads) and 'class="small fw-bold mt-2"' in card
      and card.count('<hr class="my-3">') == 1 and card.index(heads[0][1]) < card.index('<hr class="my-3">') < card.index(heads[1][1]), heads)

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

print("== scoped prints")
from urllib.parse import quote_plus
from netbox_tracepath_plugin.scope import apply_scope as _apply_scope, scopes_of as _scopes_of
from netbox_tracepath_plugin.selection import apply_selection as _select

sth = Interface.objects.get(device__name="sto-rtr-01", name="et-0/0/2")           # Stockholm to Helsinki over NSN
base_url = f"/plugins/tracepath/interface/{sth.pk}/"
full = Collector(admin).trace_doc(paths_through(sth)[0])
found = _scopes_of(full)
labels = [x["label"] for x in found]
check("the scopes are the places the path passes through, sites first",
      [l for l in labels if l.startswith("Site: ")] == ["Site: Nordfiber Stockholm DC", "Site: Nordfiber Helsinki DC"]
      and labels == sorted(labels, key=lambda l: ["Sit", "Loc", "Rac"].index(l[:3])) and any(l.endswith("STO-MM-01") for l in labels), labels)
mm = next(x["value"] for x in found if x["label"].endswith("STO-MM-01"))
d = _apply_scope(full, mm)
inner = [b for b in d.blocks if not b.kind.startswith("edge")]
check("a rack scope keeps that rack's blocks between two edge markers",
      d.blocks[0].kind == "edge-in" and d.blocks[-1].kind == "edge-out" and len(d.segments) == 1 and len(inner) >= 2
      and all(b.rack == "STO-MM-01" for b in inner) and len(d.links) == len(d.blocks) - 1, [(b.kind, b.title) for b in d.blocks])
check("  the markers name the equipment just outside, with its port",
      d.blocks[0].title == full.blocks[full.blocks.index(next(b for b in full.blocks if b.title == inner[0].title)) - 1].title
      and d.blocks[0].subtitle == "Enters rack STO-MM-01" and d.blocks[-1].subtitle == "Leaves rack STO-MM-01"
      and d.blocks[0].ports[0].out_name and d.blocks[-1].ports[0].in_name, [(b.subtitle, b.title) for b in (d.blocks[0], d.blocks[-1])])
site = next(x["value"] for x in found if x["label"] == "Site: Nordfiber Stockholm DC")
d = _apply_scope(full, site)
check("a site scope ends at the border with a marker for the equipment in the other site",
      d.blocks[0].kind != "edge-in" and d.blocks[-1].kind == "edge-out" and d.blocks[-1].site == "Nordfiber Helsinki DC", d.blocks[-1].site)
d = _select(_apply_scope(full, mm), set(PrintProfile.objects.get(name="Customer-safe").keys))
check("a hidden rack is hidden on the markers too (Customer-safe shows the site only), the scope line stays",
      d.blocks[0].rack == "" and bool(d.blocks[0].site) and any(l.startswith("Scope:") for l in d.summary), d.summary)

page = c.get(base_url, HTTP_HOST=HOST).content.decode()
check("the print page offers a Scope card with the places, grouped by kind",
      "Limit the print to" in page and '<optgroup label="Site">' in page and '<optgroup label="Rack">' in page
      and "Whole path" in page and "STO-MM-01" in page)
page = c.get(base_url + "?scope=" + quote_plus(mm), HTTP_HOST=HOST).content.decode()
check("a chosen scope is selected and carried to the pdf address",
      _re2.search(r'<option value="' + _re2.escape(mm) + r'"\s+selected', page) and "scope=rack%3A" in page and "<object" in page)
r = c.get(base_url + "pdf/?scope=" + quote_plus(mm), HTTP_HOST=HOST)
check("it prints as a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
bad = c.get(base_url + "?scope=rack%3Anowhere", HTTP_HOST=HOST).content.decode()
pdf_of = lambda html: (_re2.findall(r'<object data="([^"]*)"', html) or [""])[0]
check("an unknown scope is ignored: the whole path prints", pdf_of(bad) and "scope=" not in pdf_of(bad))
got_if = Interface.objects.get(device__name="polaris-got-sw-01", name="Ethernet49")       # never enters Stockholm
other = c.get(f"/plugins/tracepath/interface/{got_if.pk}/?scope=" + quote_plus(mm), HTTP_HOST=HOST).content.decode()
check("a scope the trace does not pass through is dropped", pdf_of(other) and "scope=" not in pdf_of(other))

print("== WDM circuits and FMS fiber cables as starting points")
from netbox_fms.models import FiberCable
from netbox_wdm.models import WdmCircuit
from netbox_tracepath_plugin.integrations import wdm as _wdm

fjord = WdmCircuit.objects.get(name__startswith="Fjord")
seg1 = WdmCircuit.objects.get(name__startswith="Baltic Retail Group Backup - Segment 1")
r = c.get("/plugins/tracepath/?kind=wdm-circuit", HTTP_HOST=HOST)
check("the WDM circuit dropdown asks NetBox for its circuits", 'nav-link border active' in r.content.decode() and "/api/plugins/wdm/wdm-circuits/" in r.content.decode())
r = c.get(f"/plugins/tracepath/wdm-circuit/?object={fjord.pk}", HTTP_HOST=HOST)
check("choosing a WDM circuit goes to its print page", r.status_code == 302 and r["Location"].endswith(f"/wdm-circuit/{fjord.pk}/"), (r.status_code, r.get("Location")))
page = c.get(f"/plugins/tracepath/wdm-circuit/{fjord.pk}/", HTTP_HOST=HOST).content.decode()
check("its two directions are named by muxponder and channel", "sto-wdm-01 · C21 (" in page and "→ osl-wdm-01 · C21 (" in page and "<object" in page, page.count("→"))
check("no extension card for a wavelength service", "Extend the trace" not in page)
col = Collector(admin)
for circuit, ends in ((fjord, {"sto-wdm-01", "osl-wdm-01"}), (seg1, {"sto-wdm-02", "got-wdm-01"})):
    entry = _wdm.circuit_paths(circuit)[0]
    d = _wdm.trim_doc(col.chain_doc([col.part(entry["path"])]), entry, circuit)
    check(f"{circuit.name[:32]}: from muxponder to muxponder, nothing beyond",
          {d.blocks[0].title, d.blocks[-1].title} == ends and len(d.blocks) == 4 and sum(len(l.cables) for l in d.links) == 3
          and not [b for b in d.blocks if "dcp2" in b.title], [b.title for b in d.blocks])
    check("  titled and summarised as the service", d.title == f"WDM circuit: {circuit.name}" and "wavelength service" in d.summary[1]
          and any("left out" in n for n in d.notes) and not any("joins" in n or "ends at" in n for n in d.notes), (d.title, d.summary, d.notes))
    check("  the muxponders show their channel and service", any(f.key == "wdm.channel" for b in (d.blocks[0], d.blocks[-1]) for row in b.ports for f in row.in_fields + row.out_fields)
          and any(f.key == "wdm.service" for b in (d.blocks[0], d.blocks[-1]) for row in b.ports for f in row.in_fields + row.out_fields))
    check("  the long-haul trunk in the middle carries its fiber record", any(f.key == "fms.serial" for lk in d.links for cb in lk.cables for f in cb.fields))
r = c.get(f"/plugins/tracepath/wdm-circuit/{fjord.pk}/pdf/", HTTP_HOST=HOST)
check("a WDM circuit prints as a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)

fc = FiberCable.objects.get(cable__label="bb-cbl-00001")
r = c.get(f"/plugins/tracepath/fiber-cable/?object={fc.pk}", HTTP_HOST=HOST)
check("choosing an FMS fiber cable goes to its print page", r.status_code == 302 and r["Location"].endswith(f"/fiber-cable/{fc.pk}/"), (r.status_code, r.get("Location")))
page = c.get(f"/plugins/tracepath/fiber-cable/{fc.pk}/", HTTP_HOST=HOST).content.decode()
check("a fiber cable behaves like its cable (one pair in use, no choice needed)", "<object" in page and "Fiber cable (FMS)" in page and "pairs in use" not in page)
fc_mm = FiberCable.objects.filter(cable__label="bb-cbl-00005").first()
check("the long-haul fiber cables print", c.get(f"/plugins/tracepath/fiber-cable/{fc_mm.pk}/pdf/", HTTP_HOST=HOST).status_code == 200)

print("== FMS fiber circuits as starting points, and the strands a link uses")
from netbox_fms.models import FiberCircuit
from netbox_tracepath_plugin.integrations import fms as _fms

fcirc = FiberCircuit.objects.get(cid="NF-FC-0002")
r = c.get("/plugins/tracepath/?kind=fiber-circuit", HTTP_HOST=HOST)
check("the fiber circuit dropdown asks NetBox for its circuits", "/api/plugins/fms/fiber-circuits/" in r.content.decode())
r = c.get(f"/plugins/tracepath/fiber-circuit/?object={fcirc.pk}", HTTP_HOST=HOST)
check("choosing a fiber circuit goes to its print page", r.status_code == 302 and r["Location"].endswith(f"/fiber-circuit/{fcirc.pk}/"), (r.status_code, r.get("Location")))
page = c.get(f"/plugins/tracepath/fiber-circuit/{fcirc.pk}/", HTTP_HOST=HOST).content.decode()
check("its two directions are named by panel port and the circuit previews",
      "sto-patch-osl-01 : Port 1 → osl-patch-sto-01 : Port 1" in page and "osl-patch-sto-01 : Port 1 → sto-patch-osl-01 : Port 1" in page
      and "<object" in page and "Extend the trace" not in page, page.count("→"))
entry = _fms.circuit_paths(fcirc)[0]
d = _fms.trim_doc(col.chain_doc([col.part(entry["path"])]), entry, fcirc)
check("NF-FC-0002 runs panel to panel over the one trunk, nothing beyond",
      [b.title for b in d.blocks] == ["sto-patch-osl-01", "osl-patch-sto-01"] and sum(len(l.cables) for l in d.links) == 1, [b.title for b in d.blocks])
check("  titled, with strands, wavelength and measured loss in the header",
      d.title == "Fiber circuit: NF-FC-0002 · Stockholm - Oslo, pair 1" and d.summary[0] == "From sto-patch-osl-01 : Port 1 to osl-patch-sto-01 : Port 1"
      and "fiber circuit · Active · Nordfiber AB" in d.summary[1] and d.summary[2] == "2 strands · 1550 nm · measured loss 95.52 dB", (d.title, d.summary))
fields = {f.key: f.value for f in d.links[0].cables[0].fields}
check("  the trunk names its strands and the circuit",
      fields.get("fms.strands") == "Tube 1-F1 (red), Tube 1-F2 (green)" and fields.get("fms.circuit") == "NF-FC-0002 · Stockholm - Oslo, pair 1", fields)
nsn = FiberCircuit.objects.get(cid="NF-FC-0004")
entry = _fms.circuit_paths(nsn)[0]
d = _fms.trim_doc(col.chain_doc([col.part(entry["path"])]), entry, nsn)
check("NF-FC-0004 follows the glass through both MeetMe rooms, line panel to line panel",
      d.blocks[0].title == "sto-patch-mmr-01" and d.blocks[-1].title == "hel-patch-mmr-01" and len(d.blocks) == 6
      and sum(len(l.cables) for l in d.links) == 5 and not [b for b in d.blocks if "wdm" in b.title or "rtr" in b.title], [b.title for b in d.blocks])
check("  the NSN trunk in the middle carries pair 1's strands and its fiber record",
      any(f.key == "fms.strands" and f.value == "Tube 1-F1 (red), Tube 1-F2 (green)" for lk in d.links for cb in lk.cables for f in cb.fields)
      and any(f.key == "fms.serial" for lk in d.links for cb in lk.cables for f in cb.fields))
nsn_cable = Cable.objects.get(label="bb-cbl-00005")
for pair, text in ((2, "Tube 1-F3 (blue), Tube 1-F4 (yellow)"), (7, "Tube 2-F1 (red), Tube 2-F2 (green)")):
    got = [f.value for f in _fms.cable_facts(nsn_cable, [FrontPort.objects.get(device__name="sto-mmr-nsn-01", name=f"Port {pair}")])
           if f.key == "fms.strands"]
    check(f"the strands follow the pair: Port {pair} is strands {2 * pair - 1} and {2 * pair}", got == [text], got)
check("without a front port beside the cable there is no strand fact",
      not [f for f in _fms.cable_facts(Cable.objects.get(label="bb-cbl-00005"), []) if f.key in ("fms.strands", "fms.circuit")])
from netbox_tracepath_plugin.selection import apply_selection as _apply
cs = PrintProfile.objects.get(name="Customer-safe")
quiet = _apply(d, cs.keys)
check("a profile without the facts leaves them out (Customer-safe shows no strands, circuit or loss)",
      not [f for lk in quiet.links for cb in lk.cables for f in cb.fields if f.key.startswith("fms.")] and len(quiet.summary) == 2, quiet.summary)
tech_keys = set(PrintProfile.objects.get(name="Field technician").keys)
check("the Field technician profile has the strands and the circuit (migration 0004), not the loss",
      {"fms.strands", "fms.circuit"} <= tech_keys and "fms.optics" not in tech_keys)
r = c.get(f"/plugins/tracepath/fiber-circuit/{fcirc.pk}/pdf/", HTTP_HOST=HOST)
check("a fiber circuit prints as a pdf", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
check("every circuit of the dataset has paths to print",
      all(_fms.circuit_paths(x) for x in FiberCircuit.objects.all()), [x.cid for x in FiberCircuit.objects.all() if not _fms.circuit_paths(x)])

integrations.DISABLED.update({"fms"})
try:
    check("without netbox-fms there is no fiber circuit button and the address is unknown",
          "Fiber circuit (FMS)" not in c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode()
          and c.get(f"/plugins/tracepath/fiber-circuit/{fcirc.pk}/", HTTP_HOST=HOST).status_code == 404)
    check("and a trace still prints, without the strands",
          not [f for lk in col.trace_doc(paths_through(trunk)[0]).links for cb in lk.cables for f in cb.fields if f.key.startswith("fms.")])
finally:
    integrations.DISABLED.clear()

integrations.DISABLED.update({"wdm"})
try:
    check("without netbox-wdm there is no WDM circuit button and the address is unknown",
          "WDM circuit" not in c.get("/plugins/tracepath/", HTTP_HOST=HOST).content.decode()
          and c.get(f"/plugins/tracepath/wdm-circuit/{fjord.pk}/", HTTP_HOST=HOST).status_code == 404)
finally:
    integrations.DISABLED.clear()
check("with it, the kinds are back", "wdm-circuit" in __import__("netbox_tracepath_plugin.collect", fromlist=["x"]).kinds())

print("== the Print trace button on NetBox's own pages")
page_of = lambda obj: c.get(obj.get_absolute_url(), HTTP_HOST=HOST).content.decode()
def button(html, kind, pk):
    return _re2.search(r'<a href="/plugins/tracepath/%s/%d/" class="btn btn-primary" title="Print this trace as a PDF">\s*<i class="mdi mdi-printer"></i> Print trace' % (kind, pk), html)
check("a cable's page has the button, and it opens that cable", button(page_of(cable), "cable", cable.pk))
check("a cabled interface has it", button(page_of(iface), "interface", iface.pk))
check("an interface without a cable has none (there is no trace)", "Print trace" not in page_of(uncabled_if))
check("a cabled front port has it", button(page_of(fp), "front-port", fp.pk))
check("a circuit termination with a cable has it", button(page_of(ct), "circuit-termination", ct.pk))
check("the button leads to a working print page", c.get(f"/plugins/tracepath/cable/{cable.pk}/", HTTP_HOST=HOST).status_code == 200)
check("netbox-fms fiber cables and fiber circuits have it", button(page_of(fc), "fiber-cable", fc.pk) and button(page_of(fcirc), "fiber-circuit", fcirc.pk))
check("netbox-wdm circuits have it", button(page_of(fjord), "wdm-circuit", fjord.pk))
integrations.DISABLED.update({"fms", "wdm"})
try:
    check("without netbox-fms and netbox-wdm their pages have no button, the cable page still has it",
          "Print trace" not in page_of(fc) and "Print trace" not in page_of(fjord) and button(page_of(cable), "cable", cable.pk))
finally:
    integrations.DISABLED.clear()
only_if = User.objects.create(username="tp-iface-only")
perm_i = ObjectPermission.objects.create(name="tp-iface-only", actions=["view"])
perm_i.object_types.set([ContentType.objects.get_for_model(Interface)])
perm_i.users.add(only_if)
try:
    c3 = Client()
    c3.force_login(only_if)
    page = c3.get(iface.get_absolute_url(), HTTP_HOST=HOST)
    check("a user who may view interfaces but not cables sees the page without the button",
          page.status_code == 200 and b"Print trace" not in page.content, page.status_code)
    perm_i.object_types.add(ContentType.objects.get_for_model(Cable))
    check("and with permission to view cables the button appears", b"Print trace" in c3.get(iface.get_absolute_url(), HTTP_HOST=HOST).content)
finally:
    perm_i.delete()
    only_if.delete()

print("== the optional Print trace column in NetBox's own lists")
from circuits.tables.circuits import CircuitTerminationTable
from dcim.tables.cables import CableTable
from dcim.tables.devices import DeviceFrontPortTable, DeviceInterfaceTable, FrontPortTable, InterfaceTable

def link(html, kind, pk):
    return _re2.search(r'href="/plugins/tracepath/%s/%d/" class="btn btn-sm btn-primary" title="Print trace as PDF"' % (kind, pk), html)

lists = [("cables", CableTable, f"/dcim/cables/?id={cable.pk}", "cable", cable.pk),
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
before = admin.config.get(key)
try:
    admin.config.set(key, list(InterfaceTable.Meta.default_columns) + ["print_trace"], commit=True)
    check("an interface without a cable gets no icon", not link(c.get(f"/dcim/interfaces/?id={uncabled_if.pk}", HTTP_HOST=HOST).content.decode(), "interface", uncabled_if.pk))
    viewer = User.objects.create(username="tp-col-viewer")
    perm_v = ObjectPermission.objects.create(name="tp-col-viewer", actions=["view"])
    perm_v.object_types.set([ContentType.objects.get_for_model(Interface)])
    perm_v.users.add(viewer)
    try:
        viewer.config.set(key, list(InterfaceTable.Meta.default_columns) + ["print_trace"], commit=True)
        c4 = Client()
        c4.force_login(viewer)
        check("a user who may not view cables sees no icon", not link(c4.get(f"/dcim/interfaces/?id={iface.pk}", HTTP_HOST=HOST).content.decode(), "interface", iface.pk))
    finally:
        perm_v.delete()
        viewer.delete()
finally:
    if before is None:
        admin.config.clear(key, commit=True)
    else:
        admin.config.set(key, before, commit=True)
from netbox.registry import registry as _registry
check("the column is registered on all six tables", all("print_trace" in _registry["tables"][row[1]] for row in lists), [row[1].__name__ for row in lists])

print("== the equipment's colour as the header background")
role_doc = Collector(admin).trace_doc(paths_through(iface)[0])
devices_on_path = {d.name: d for d in Device.objects.filter(name__in=[b.title for b in role_doc.blocks]).select_related("role")}
check("every block of equipment carries the colour NetBox gives its role",
      role_doc.blocks and all(b.color_hex == devices_on_path[b.title].role.color.lower() and len(b.color_hex) == 6 for b in role_doc.blocks if b.kind == "device"),
      [(b.title, b.color_hex) for b in role_doc.blocks])
check("and blocks that are not equipment (circuits, sites) have none", all(not b.color_hex for b in Collector(admin).trace_doc(paths_through(ct)[0]).blocks if b.kind != "device"))
colour_pdf = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4", HTTP_HOST=HOST).content
bw_pdf = c.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/?paper=A4:bw", HTTP_HOST=HOST).content
check("the print is in colour on A4 (Color) and grey only on A4 (B/W)", _chromatic(colour_pdf) and not _chromatic(bw_pdf))

print("== a user with no permissions")
nobody = User.objects.create(username="tp-nobody")
perm = None
try:
    c2 = Client()
    c2.force_login(nobody)
    check("index is refused", c2.get("/plugins/tracepath/", HTTP_HOST=HOST).status_code in (302, 403))
    check("pdf is refused", c2.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/", HTTP_HOST=HOST).status_code in (302, 403))

    print("== a user who may view cables and interfaces but not devices")
    perm = ObjectPermission.objects.create(name="tp-test", actions=["view"])
    perm.object_types.set([ContentType.objects.get_for_model(m) for m in (Cable, Interface)])
    perm.users.add(nobody)
    r = c2.get(f"/plugins/tracepath/interface/{iface.pk}/pdf/", HTTP_HOST=HOST)
    check("pdf works", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    from netbox_tracepath_plugin.collect import Collector, paths_through
    doc = Collector(nobody).trace_doc(paths_through(iface)[0])
    check("devices are shown by name only", all(b.kind == "restricted" and not b.fields for b in doc.blocks),
          [(b.title, b.kind) for b in doc.blocks])
    check("cables are still described", any(c_.fields for lk in doc.links for c_ in lk.cables))
    check("device names appear but no serial numbers leak",
          all(not any(f.label == "Serial" for f in b.fields) for b in doc.blocks))
    r = c2.get(f"/plugins/tracepath/front-port/{fp.pk}/", HTTP_HOST=HOST)
    check("front ports are refused (no view permission on them)", r.status_code in (302, 403), r.status_code)
finally:
    if perm:
        perm.delete()
    nobody.delete()

print(f"\n{'ALL OK' if not fails else 'FAILED: ' + ', '.join(fails)}")
