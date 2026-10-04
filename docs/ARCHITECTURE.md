# Architecture

A printout goes through these steps. Each hands plain data to the next, so the middle of the plugin
(everything but the first step) is ordinary Python that can be tested without a database.

```
NetBox objects ──collect──▶ TraceDoc ──scope──▶ TraceDoc ──selection──▶ TraceDoc ──layout──▶ PDF bytes
 (CablePath, devices,      (blocks, links,    (optional: only      (only the facts      (pages, columns,
  cables, ports,            notes, header)     one site, location   that were chosen)    fonts, chevrons)
  other plugins' data)                         or rack)
```

| Step | Module | Needs Django? |
|---|---|---|
| Choose what to trace, paths, options, the web pages | `views.py`, `forms.py`, `options.py`, `extend.py`, `urls.py`, `templates/` | yes |
| Read NetBox into a `TraceDoc` | `collect.py` (+ `integrations/`) | yes |
| Limit to a site, location or rack | `scope.py` | no |
| Keep only the chosen facts | `selection.py`, `fields.py` (the catalogue and the built-in profiles) | no |
| Draw it | `layout.py`, `model.py`, `pdf/` | no |
| A "Print trace" button on NetBox's own pages | `template_content.py`, `templates/.../inc/print_button.html` | yes |
| An optional "Print trace" column in NetBox's lists | `table_columns.py` (registered in `ready()`) | yes |
| Print profiles in the database | `models.py`, `tables.py`, `migrations/` | yes |

## The data (`model.py`)

`TraceDoc` has a title, header lines, a list of `Block`s and the `Link`s between them, notes and a footer.
A `Block` is one parent object on the path (a device, circuit, provider network or site) with the ports the
path uses on it (`PortRow`: an in port and an out port, each with its own fields). A `Link` is the cable or
cables between two blocks (`Cable`: title, colour, fields). A `Field` is `label`, `value` and a catalogue
`key` such as `cable.length`. Everything printed that is not a name, a port or a title is a keyed `Field`;
that is what makes "choose which facts to print" work, and why a hidden fact is hidden everywhere.

## Collecting (`collect.py`)

`Collector.part(path)` turns one NetBox `CablePath` into blocks and links, the same way NetBox's own trace
view groups it (near terminations, cables, far terminations; ports are grouped under their parent object).
`Collector.chain_doc(parts)` joins several parts end to end into one `TraceDoc`; the equipment where two parts
meet becomes one block with an in port and an out port. That is how "extend the trace" works (`extend.py`
chooses the parts).

Objects the user may not view appear by name only (`Details restricted`). Cable colours are not decided here:
a cable is drawn in the colour NetBox stores on it, named from NetBox's own colour list.

## Scoped prints (`scope.py`)

`scope.apply_scope(doc, value)` keeps the blocks that are in one site, location or rack and replaces the
neighbours outside with *edge markers*: blocks of kind `edge-in` / `edge-out` that carry the neighbour's name,
port, site and rack. The document gets `segments` (runs of blocks, each printed on its own pages) and a `scope`
line; between two segments an empty `Link` keeps `len(links) == len(blocks) - 1`. It runs on the full
document, before `selection`, because the scope must be decided on the real places and the selection then hides
a marker's site and rack if those facts are not printed. The layout draws an edge marker as a chevron cell and
starts every segment on a new page.

## Facts and profiles (`fields.py`, `selection.py`, `models.py`)

`fields.GROUPS` is the catalogue of core facts, `fields.PLUGIN_GROUPS` those that other plugins provide.
`selection.apply_selection(doc, keys)` returns a copy of the document that shows only the selected keys.
A *print profile* is a named set of keys. Profiles live in two tables of this plugin and refer to nothing in
NetBox; the five built-in ones are put there by migrations, which spell the keys out **literally** (a
migration must not change when the catalogue does; a later migration adds the keys of new facts).

## Drawing (`layout.py`, `pdf/`)

`layout.render(doc, LayoutSpec)` returns `(pdf bytes, LayoutReport)`. The engine measures every text with the
real font, wraps it inside its block (nothing is cut off), lays the blocks on a uniform grid that flows like
text, and takes as many rows as fit on each page. If a row does not fit it first uses fewer, wider columns and
only then a smaller font (7 pt at the smallest); anything that still cannot fit is reported in
`LayoutReport.warnings`. Where a trace continues on another page, chevron markers are cells of the grid.
A block's header is filled with `Block.color_hex` (the device role's colour, set by `collect.py`), with white text on
dark and medium-dark backgrounds and black on lighter ones (`ink_for`, limit `WHITE_BELOW` = 0.30; `WHITE_BELOW_BW` = 0.18 on the grey of a black and white printout). `LayoutSpec.color` is the colour or black and white choice: with `color=False` every cable colour is drawn as the
grey of the same lightness (`Engine._tone`); the paper choice `A4:bw` means A4 with `color=False`.
`pdf/` is a standard-library PDF writer: a TrueType subsetter (`ttf.py`), the bundled DejaVu fonts, paper sizes
and a small canvas. There are no runtime dependencies.

## The web pages (`views.py`)

`PrintView` renders the print page and `PdfView` the PDF; both go through `_prepare()`, which resolves the
object, the starting paths, the chosen path, the options and the facts, and renders the PDF once. The page and
the PDF therefore always agree, and the PDF address (`_pdf_query`) reproduces a printout exactly.

The *kinds* of starting point are the core ones (`CORE_KINDS` in `collect.py`: cable, interface, front port,
circuit termination) plus those that installed integrations add. Cable, interface and front-port dropdowns get
their options from `options.py` (cabled objects only, labelled `equipment : port`); the others use NetBox's own
API. A cable that is a trunk carries several paths (one per pair and direction), so the page asks for the pair
first (`pair_of`).

## Other plugins (`integrations/`)

An integration is a module with `installed()` and any of:

- `cable_facts(cable, ports)`, `port_facts(port)`, `device_facts(device)`: lists of `Field`s with catalogue keys.
  `ports` are the front ports on either side of the cable in this trace, for facts that depend on which pair
  or strand the link carries.
- `KINDS`: extra starting points, `{slug: (app label, model name, label)}`.
- for a *service* starting point (a WDM or fiber circuit), `circuit_paths(obj)` finds the cable paths it runs
  on and `trim_doc(doc, entry, obj)` cuts a trace down to the service.

`integrations/__init__.py` calls them all, skips an integration that is not installed, and logs and skips one
that fails, so another plugin changing its models never breaks a printout. `integrations.DISABLED` switches an
integration off (the tests use it to prove the plugin works without them).

## Adding things

- **A fact:** produce a `Field(label, value, key)` where the data is read, add the key to `fields.GROUPS` (or
  `PLUGIN_GROUPS`), and add it to the built-in profiles it belongs in with a *new* migration.
- **Another plugin's facts:** a new module in `integrations/` and an entry in `MODULES`; a `PLUGIN_GROUPS`
  entry for its keys.
- **A starting point:** an entry in `KINDS`; if it is a service, add it to `SERVICE_KINDS` in `views.py`.
