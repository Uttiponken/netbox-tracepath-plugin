# Changelog

Releases are tagged `vX.Y.Z`; sample PDFs for each are in `samples/X.Y.Z/`.

## 0.5.1

- "Extend the trace": the *At the start* and *At the end* headings are larger, with a line between the two
  sections.
- Documentation: architecture, testing and this changelog; the README and roadmap brought up to date.

## 0.5.0

- New starting points: **WDM circuit** (netbox-wdm), **Fiber cable** and **Fiber circuit** (netbox-fms). A
  service prints from its first to its last equipment and stops there; a fiber circuit is the stretch between
  its origin and destination panels, through every cable and MeetMe jumper, with strands, wavelength and
  measured loss in the header.
- A **trunk cable** carries several pairs, so the page asks for the pair (and direction) first, under the cable
  dropdown; every option starts with its pair (`Pair 3 · …`).
- Trunk cables name the **strands** their link uses (tube, fiber, colour) and the **fiber circuit** they belong
  to. New facts `fms.strands`, `fms.circuit`, `fms.optics`; migration `0004` adds them to the built-in profiles.
- Cable, interface and front-port dropdowns are labelled `equipment : port`.
- Cables are drawn in the colour NetBox stores on them (the sample data now has green and blue trunks).

## 0.4.0

- One page to start and print: the PDF preview on the left, the menu on the right.
- Start from a cable; dropdowns list only cabled objects; named path choices
  (`equipment : port → equipment : port · N cables`).
- **Extend the trace** at either end, step by step, as one printout.
- Optional facts from netbox-fms (fiber cable record) and netbox-wdm (channel, wavelength, service, line port);
  migration `0003` adds them to the built-in profiles.
- The title names the cables; the cable name stands above its line; "What to print" is collapsed by default.

## 0.3.0

- **Print profiles**: choose which facts to print by recipient. Five built-in profiles (Full information, Field
  technician, Network engineer, Facility / colo operator, Customer-safe), stored in the plugin's own tables
  (migrations `0001`, `0002`), managed under Plugins → Trace Print → Print profiles with change log and
  permissions. "Prepared for" line and layout name in the footer.

## 0.2.0

- **Chevron markers** where a trace continues on another page ("Continued from page N", "Continues on
  page N"), naming the equipment, port, site and rack on the other side.

## 0.1.0

- PDF output with the standard library only (TrueType subsetting, bundled DejaVu fonts, UTF-8), paper size and
  orientation chosen at print time, text that wraps and always fits (7 pt at the smallest), the *Full
  information* layout, and real traces read from NetBox.
