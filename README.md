# netbox-trace-print

A NetBox plugin that turns a cable trace into a printable **PDF** for technicians
and field engineers. Each device on the path is a block, laid out in a grid that
wraps like text across the page, so a long trace reads A–B–C–D on one row and
continues E–F–G on the next.

**Status: early development (0.1.0).** The plugin installs and adds a menu entry;
trace selection and PDF output are being built.

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
- **No database model.** No migrations.
- UTF-8 text throughout.

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
