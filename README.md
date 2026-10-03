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
Interface, Front port, Rear port, Circuit termination) sit at the top; picking one opens a dropdown
below them on the same page. Only objects that have a cable are listed, since the others have no trace.
The buttons and dropdown stay at the top of the menu, so you can switch to another object at any time.
Choose paper size and
orientation (A4 landscape by default). A port or cable that several paths run through offers a choice
of path. The PDF is shown in the page and can be downloaded. Sample output is in `samples/<version>/`.

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
