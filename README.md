# netbox-trace-print

A NetBox plugin that turns a cable trace into a printable **PDF** for technicians
and field engineers. Each device on the path is a block, laid out in a grid that
wraps like text across the page, so a long trace reads A–B–C–D on one row and
continues E–F–G on the next.

**Status: early development (0.3.0).** You can pick an interface, front or rear port or circuit
termination, choose which facts to print (by recipient, using print profiles), see the cable trace as
a PDF in the page, and download it. Colours by site/rack and scoping a print to one site are next.
See `docs/ROADMAP.md`.

## Use

**Plugins → Trace Print → Print cable trace**. One page does it all: the PDF preview is on the left (empty until you
have chosen something) and the menu is on the right. Buttons for the kinds of starting point (Cable,
Interface, Front port, Circuit termination, and with netbox-wdm / netbox-fms also WDM circuit, Fiber cable and Fiber circuit) sit at the top; picking one opens a dropdown
below them on the same page. Only objects that have a cable are listed, since the others have no trace. Ports are listed
as `equipment : port` (and found by either part) so that many `Port 1` can be told apart, and a cable shows the
two ends it connects.
The buttons and dropdown stay at the top of the menu, so you can switch to another object at any time.
Choose paper size and
orientation (A4 landscape by default). A port that several paths run through offers a choice
of path. A **trunk cable** carries several pairs: the page asks which pair (and direction) to print before showing
anything, because a printout always follows one pair at a time. The PDF is shown in the page and can be downloaded. Sample output is in `samples/<version>/`.

**What to print.** Pick a *print profile* and press Apply: the boxes below it tick exactly that
profile's facts. Adjust them for this printout if you like and press Update. Five profiles are
installed: Full information, Field technician, Network engineer, Facility / colo operator and
Customer-safe. Names of equipment, ports and cables, the title, page numbers and the chevron markers
are always printed, and a fact you hide is hidden everywhere (also on the markers). The footer says which
layout was used ("Layout: Field technician", "(adjusted)" if you changed it), and an optional
"Prepared for" line goes under the title.

**Managing profiles.** Plugins → Trace Print → Print profiles: add, edit and delete profiles, with
the usual NetBox change log and permissions (`netbox_trace_print.view/add/change/delete_printprofile`).
Without view permission on profiles you can still tick facts by hand.

You need the stock trace permission (view cables) and view permission on the object type. Objects
you may not view appear by name only.

## Goals

1. Printable traces with the metadata a technician needs, selectable at print time
   depending on who receives the printout.
2. Colour by site, location or rack so connection points are easy to find, while
   staying fully readable in black and white.
3. Further improvements, such as bulk printing, cable end labels and rack
   elevations.

Paper size and orientation are chosen at print time (landscape by default), and all
the information always fits the chosen paper.

## Design constraints

- **No dependencies.** Installs on a vanilla NetBox with no extra packages. The PDF
  writer and layout engine use only the Python standard library; the font is bundled.
- **Generic fields only.** Standard NetBox data (cables, ports, devices, racks,
  locations, sites, tenants, circuits). No custom fields and no data from other
  plugins.
- **Own tables only.** Print profiles live in two tables of the plugin (`netbox_trace_print_printprofile`
  and `..._printprofilefield`). They hold no reference to any NetBox object and the migrations depend on
  nothing in NetBox. Installing runs them like any plugin (`manage.py migrate`, done by NetBox's
  upgrade script and by netbox-docker on start).
- UTF-8 text throughout.

## WDM circuits, fiber cables and fiber circuits as starting points

With **netbox-wdm** installed, *WDM circuit* lists the wavelength services. A service prints from muxponder to
muxponder, through the patch panels and trunks between them, and stops there (the client shelf beyond it and
anything past a regenerator are left out, and the printout says so). It is titled `WDM circuit: <name>`, shows
the channel and wavelength, and the muxponders show their channel, status and the service. A circuit with two
directions offers both. With **netbox-fms** installed, *Fiber cable (FMS)* lists the fiber cables and behaves
like the cable it describes, including the choice of pair for a trunk. *Fiber circuit (FMS)* lists the fiber
circuits. FMS follows a circuit's glass from its origin front port to its destination front port, and the printout
shows that stretch: from the panel where the circuit starts to the panel where it ends, through every cable and
MeetMe jumper between them, and nothing beyond (the printout says so). It is titled
`Fiber circuit: <id> · <name>`, and the header adds the strand count, wavelength and measured loss. A circuit
offers both directions, like a WDM circuit. In the pair dropdown of a trunk cable, every option starts with its pair
(`Pair 3 · …`), so it can be told apart even when the group heading is out of sight.

## Extending a trace

Under **Extend the trace** on the print page, *Show connections to add* lists the other cabled interfaces on
the equipment at the start and at the end of the trace, grouped by where each one leads, for example
`Ethernet49 → sto-sw-01 : Ethernet2 · 5 cables`. Click one and its path is added to the printout. The
equipment where two traces meet is drawn once, arriving on one port and leaving on another. You can keep
adding at either end (server – switch – ... – circuit – ... – switch – server), remove the last addition
again, and the whole chain is one printout with one title, summary, page numbering and set of chevron markers.
The choices live in the page address (`before=` and `after=`), so a printout can be reproduced from its link.

## Other plugins (optional)

If **netbox-fms** is installed, a cable's fiber-plant record is printed on it: fiber cable type, fibers and
construction, sheath, serial number, install date and installer, route marks, notes. If **netbox-wdm** is
installed, a muxponder's block says it is a WDM node, and its ports show channel and wavelength, channel
status, the wavelength service riding on it, and the role of the line port. A trunk cable also says which
**strands** the link uses (`Tube 1-F3 (blue), Tube 1-F4 (yellow)`: the tube and fiber to look for and their
colours, taken from the strands landed on the panel ports beside the cable) and which **fiber circuit** it belongs
to. These facts are choices in the
print profiles like any other. Neither plugin is needed: without them the facts and their choices are
simply absent, and a profile that lists them keeps working. If the other plugin changes in a way this
plugin does not understand, that part is skipped and logged instead of failing the printout.

## Known limits

- Interfaces bridged to another interface are not followed past the bridge.
- Where a path fans out over several objects at one step, they are shown as one block and only the
  first is described in detail (the printout says so).
- A single block taller than a whole page at 7 pt is reported instead of printed.
- Text is UTF-8, but the bundled font covers Latin, Greek and Cyrillic only.

## Development

```bash
./run-tests.sh                      # layout and PDF tests, in a throwaway NetBox container
python -m tests.demo_layout         # regenerate samples/<version>/ (run it in the container)
```

`tests/live_smoke.py` and `tests/live_render.py` run against a live NetBox with data; see their
docstrings.

## Compatibility

NetBox 4.6.x.

## Install

```bash
pip install netbox-trace-print        # or: pip install -e . from a checkout
```

Add to `PLUGINS` in NetBox's `configuration.py` (no `PLUGINS_CONFIG` needed):

```python
PLUGINS = ["netbox_trace_print"]
```

## License

Apache-2.0, the same as NetBox.

## Third-party

The PDF text uses the DejaVu Sans and DejaVu Sans Condensed fonts (regular and bold),
bundled in `netbox_trace_print/fonts/` under the Bitstream Vera / DejaVu licence
(`LICENSE-DejaVu.txt`). They cover Latin, Greek and Cyrillic; other scripts such as
CJK are not covered.
