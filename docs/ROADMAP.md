# Roadmap and design decisions

## Steps

1. **Printable trace.** Done: PDF output (standard library only, UTF-8), the "full information"
   layout, real traces from NetBox, picker and print pages, chevron markers where a trace continues on
   another page, and choosing which facts to print by recipient (print profiles, stored in the
   plugin's own tables). To do: choose which fields
   to print depending on who gets the printout (presets), as a selection at print time.
2. **Colour by site / location / rack**, so connection points are easy to find, and still fully
   readable in black and white (tint + pattern + text tag, never colour alone).
3. **Further improvements**, among them scoped prints, bulk prints, cable end labels with QR codes,
   rack elevations with the U highlighted, a work-order mode, saved presets.

## Decisions so far

- Generic NetBox fields only; no custom fields; no other plugin's data; no database model.
- Print profiles are stored in the plugin's own database tables, keyed to nothing in NetBox. A profile
  could later be tied to NetBox's Contact Roles; that is deliberately not done now.
- A fact that is hidden is hidden everywhere it could appear (blocks, cables, chevron markers, header,
  footer). Names, titles, page numbers and markers are always printed.
- No dependencies. The PDF writer and layout engine are standard library; DejaVu fonts are bundled.
- Landscape is the primary orientation. Paper size and orientation are chosen when printing. All
  information must fit the chosen paper: text wraps (never cut off), a tall row first gets fewer
  columns and then a smaller font down to 7 pt, and anything still too big is reported.
- Layout: blocks on a uniform grid, flowing like text. The cable between the last block of a row and
  the first of the next is drawn as a return line under the row. Every cable's name stands above it,
  its details below. Long traces continue on further pages with "continues on / continued from".
- Title names the connection (cables, and circuits when present). From/to is on the line below.
- Where a trace continues on another page, a chevron marker is a cell of the grid like any block:
  the first cell of a continuing page ("Continued from page N") and the last cell of a page that
  continues ("Continues on page N"). It names the equipment and port on the other side and its
  site and rack. The cable that crosses the break is drawn, and named, on both pages.
- Block = a parent object (device, circuit, provider network, site) with the ports the path uses on
  it, as in NetBox's own trace drawing.

## Scoped prints (planned)

Print the full path first; then allow narrowing to the part of a cable or circuit that passes a
site, location or rack (for example a technician at one data center doing fault analysis). The
title keeps naming the connection; a scope line says what is shown, and every page repeats it.

Where the path leaves the scope, an **edge marker** is drawn: a chevron ("step" shape) pointing in
the direction of travel, in the grid row of the neighbouring block and vertically centred on the
cable, with the cable drawn between them like any other. The marker says where the path continues
from or to (site, device and port). A path that leaves the scope and returns prints as separate
segments ("Segment 1 of 2"). Sketch from the author: a 190 x 50 chevron, a 90-unit gap, then a
120 x 60 block, all on one centre line.

## Extending a trace (done in 0.4.0)

Add the connections around the equipment at either end: if circuit X runs A - B - C - D - E, choose another
cabled port on E and its path is added (A ... E - f - g - h), at the start too, step by step. The joined
equipment is drawn once with the arriving port as "in" and the chosen port as "out". See the README.

## Optional awareness of other plugins

netbox-fms and netbox-wdm facts are printed when those plugins are installed (0.4.0). WDM circuits and FMS
fiber cables are starting points (0.5.0). Planned: FMS fiber circuits as starting points (they need data in the
sample dataset first) and the strand a link uses.
