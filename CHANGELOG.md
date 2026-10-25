# Changelog

Releases are tagged `vX.Y.Z`; sample PDFs for each are in `samples/X.Y.Z/`.

## 0.8.0

- **NetBox 4.7.** The plugin now declares NetBox 4.6.0 to 4.7.99 (it was 4.6 only) and was checked on NetBox 4.7.3
  with netbox-fms 0.6.0, netbox-wdm 0.2.2 and netbox-pathways 0.3.0: unit tests, the seeded smoke test and the
  printouts of real traces. No other change was needed for 4.7 itself.
- **netbox-fms 0.6.** That release no longer stores a traced path on each fiber circuit path: it derives fiber paths
  by analysis and assigns one to a circuit. Without a change, every netbox-fms fact in a printout was lost (the
  integration failed on the removed `FiberCircuitNode` and was skipped, as designed) and a fiber circuit could not
  be printed. The integration now reads the ends of the assigned path (`end_a_port`, `end_b_port`) and the strands
  landed on the link's ports to name the fiber circuit, and prints the same pages as before: the printouts of all
  ten fiber circuits of the sample data are identical on netbox-fms 0.4.1 (NetBox 4.6) and 0.6.0 (NetBox 4.7).
  netbox-fms 0.4 and 0.5 still work; the integration picks the model it finds.
- **The repository no longer depends on any sample data.** `tests/live_smoke.py` now seeds a small network of its
  own, tests the pages against it and removes it again (also after a failure), so it runs on any NetBox that has
  the plugin installed and needs no other plugin; on a NetBox without other plugins it takes seconds. The tests that
  used one particular data set (the larger smoke test, the renders of real traces, profiles, scopes, FMS and WDM)
  left this repository for the repository of that data set. The unit-test fixtures use neutral names and the
  documentation no longer points at a data set. No change to the plugin itself.

## 0.7.0

- **Renamed to netbox-tracepath-plugin.** The GitHub repository, the pip package, the Python module
  `netbox_tracepath_plugin` (which is also the Django app label: tables `netbox_tracepath_plugin_*`, permissions
  `netbox_tracepath_plugin.*`), the URL path `/plugins/tracepath/`, the menu label *Tracepath* and the footer text of
  the printouts. GitHub redirects the old repository address. Entries below this one use the old name.
- An existing installation renames its database tables once (README, "Upgrading from netbox-trace-print"); a new
  installation needs nothing. No change in behaviour or printouts.

## 0.6.2

- **Equipment colour.** The header of each block is filled with the colour NetBox gives the equipment (its device
  role), with white text on dark and medium-dark colours (relative luminance below 0.30) and black text on lighter ones.
  In *A4 (B/W)* the colour becomes the grey of the same
  lightness and white text is used only on the darker greys (at least 4.5:1 contrast). Circuits, sites and provider networks keep the light grey header.

## 0.6.1

- An **Authors** section in the README: co-authored by JP and Claude (Claude Sonnet 5.5), and the package author
  metadata says the same. No change to the plugin's behaviour or printouts.

## 0.6.0

**Scoped prints**
- Limit a print to the part of the path in one site, location or rack (a *Scope* card on the print page). Edge
  markers (chevrons) show where the path leaves or enters the scope, with the equipment, port, site and rack on
  the other side and the crossing cable drawn. A path that leaves and returns is printed as segments, one page
  each. The header says what the scope is and every page repeats it. The scope is part of the PDF address
  (`scope=`), so a printout can be reproduced from its link.
- New `scope.py` (pure Python) and layout support for segments and edge markers.

**Colour or black and white**
- Chosen with the paper: *A4 (Color)* and *A4 (B/W)* for every paper size (`paper=A4:bw` in the address). In B/W the
  cable colours print as grey tones of the same lightness.
- The *Colour* fact now only controls the colour's name; whether the line is coloured is the paper choice, so a
  profile without the fact (Network engineer, Customer-safe) no longer turns the printout black and white by
  surprise.

**A print bar at the top of the page**
- Always there, also before anything is chosen: profile, Apply profile, Manage profiles and Choose facts on the
  left; Paper, Orientation, Prepared for and Update anchored to the right (wrapping on a narrow screen). It replaces
  the Paper and What to print cards, so the menu on the right is shorter; the fact choices open as a panel in
  columns. The page-count card and the plugin-version footer are gone.
- The settings are kept when another object is chosen. A page opened with only some options shows the defaults
  (A4, landscape) for the rest. Enter in a text field does a plain Update.
- **Dropdowns that stay put.** The object selectors have their search box inside the list (clicking one opens it
  with an empty search box; the chosen entry stays in the field, with no cursor) and the short lists are plain
  dropdowns, so the menu no longer jumps up and down.

**In NetBox's own pages**
- A **Print trace** button on the pages of cables, interfaces, front ports and circuit terminations (and netbox-fms
  fiber cables and fiber circuits, netbox-wdm circuits): it opens that object in the print page. Shown only to
  users who may view cables, and only when a cable is attached.
- An optional **Print trace** column in NetBox's lists of cables, interfaces, front ports and circuit terminations
  (a printer icon per row). Off until a user adds it with Configure Table.

**Also**
- The README shows an example printout; the documentation is brought up to date.

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
