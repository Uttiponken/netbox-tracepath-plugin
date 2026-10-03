# Roadmap and design decisions

## Steps

1. **Printable trace.** Done so far: PDF output (standard library only, UTF-8), the "full
   information" layout, real traces from NetBox, picker and print pages, chevron markers where a
   trace continues on another page. To do: choose which fields
   to print depending on who gets the printout (presets), as a selection at print time.
2. **Colour by site / location / rack**, so connection points are easy to find, and still fully
   readable in black and white (tint + pattern + text tag, never colour alone).
3. **Further improvements**, among them scoped prints, bulk prints, cable end labels with QR codes,
   rack elevations with the U highlighted, a work-order mode, saved presets.

## Decisions so far

- Generic NetBox fields only; no custom fields; no other plugin's data; no database model.
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

## Extending a trace (planned)

Add the connections around the equipment at either end of the traced connection. If circuit X runs
A - B - C - D - E, choose an incoming and/or outgoing connection on E (a port with a cable or
circuit) and add its path as well, giving one printout A - B - C - D - E - f - g - h. The joined
equipment (E) is drawn once, with the arriving port as "in" and the chosen port as "out", the same
way a patch panel shows front and rear port. The same can be done at the start (A). The chain model
already supports this: it is a longer list of blocks and links.
