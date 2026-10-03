"""
The catalogue of facts a printout can show, and the built-in profiles.

A *key* names one kind of fact ("cable.length", "device.serial"). The collector tags every field it
produces with its key; a profile is a set of keys; printing keeps only the selected ones. Names of
equipment, ports and cables, the title, the page numbers and the chevron markers are always printed.

The catalogue lives in code because the collector must know every key. Profiles live in the
database (see models.py) and are seeded from PROFILES the first time the plugin is installed.
Pure Python, no Django.
"""

GROUPS = [
    ("cable", "Cable", [
        ("cable.type", "Type"), ("cable.colour", "Colour (name, swatch and coloured line)"),
        ("cable.length", "Length"), ("cable.status", "Status"), ("cable.tenant", "Tenant"),
        ("cable.description", "Description"), ("cable.tags", "Tags"), ("cable.comments", "Comments"),
    ]),
    ("port", "Port", [
        ("port.type", "Type"), ("port.speed", "Speed"), ("port.status", "Disabled"),
        ("port.use", "Management only"), ("port.positions", "Fiber positions"), ("port.module", "Module"),
        ("port.label", "Label"), ("port.description", "Description"), ("port.marked_connected", "Marked connected"),
    ]),
    ("ct", "Circuit termination", [
        ("ct.port_speed", "Port speed"), ("ct.upstream_speed", "Upstream speed"),
        ("ct.xconnect", "Cross-connect ID"), ("ct.patch_panel", "Patch panel / port"),
        ("ct.termination", "Terminates at"),
    ]),
    ("device", "Equipment", [
        ("device.subtitle", "Role and model"), ("device.status", "Status"), ("device.tenant", "Tenant"),
        ("device.site", "Site"), ("device.region", "Region"), ("device.location", "Location"),
        ("device.rack", "Rack"), ("device.position", "Position in rack"), ("device.serial", "Serial number"),
        ("device.asset_tag", "Asset tag"), ("device.platform", "Platform"), ("device.ipv4", "Primary IPv4"),
        ("device.ipv6", "Primary IPv6"), ("device.description", "Description"), ("device.tags", "Tags"),
        ("device.comments", "Comments"),
    ]),
    ("circuit", "Circuit", [
        ("circuit.subtitle", "Provider and type"), ("circuit.status", "Status"), ("circuit.tenant", "Tenant"),
        ("circuit.provider", "Provider"), ("circuit.commit_rate", "Commit rate"), ("circuit.installed", "Install date"),
        ("circuit.terminates", "Termination date"), ("circuit.description", "Description"),
        ("circuit.tags", "Tags"), ("circuit.comments", "Comments"),
    ]),
    ("site", "Site and provider network", [
        ("site.status", "Site status"), ("site.tenant", "Site tenant"), ("site.region", "Site region"),
        ("site.facility", "Site facility ID"), ("site.timezone", "Site time zone"),
        ("site.description", "Site description"), ("network.provider", "Provider network: provider"),
        ("network.description", "Provider network: description"),
    ]),
    ("doc", "Printout", [
        ("doc.route", "From / to line"), ("doc.summary", "Cable count, length and path state"),
        ("doc.generated", "Footer: when, by whom and versions"),
    ]),
]

ALL_KEYS = [key for _g, _label, items in GROUPS for key, _l in items]
LABELS = {key: label for _g, _gl, items in GROUPS for key, label in items}


def group_of(key):
    for group, _label, items in GROUPS:
        if any(key == k for k, _l in items):
            return group
    return None


# Built-in profiles: (name, description, keys). Seeded into the database; users can change them.
PROFILES = [
    ("Full information", "Everything.", list(ALL_KEYS)),
    ("Field technician",
     "Where things are and what to plug into: site, rack and position, serial and asset tag, port and cable details.",
     ["cable.type", "cable.colour", "cable.length", "cable.status", "cable.description", "cable.comments",
      "port.type", "port.positions", "port.module", "port.label", "port.description",
      "ct.xconnect", "ct.patch_panel", "ct.termination",
      "device.subtitle", "device.site", "device.location", "device.rack", "device.position", "device.serial",
      "device.asset_tag", "device.comments",
      "circuit.subtitle", "circuit.provider", "circuit.description", "circuit.comments",
      "site.facility", "site.description",
      "doc.route", "doc.summary", "doc.generated"]),
    ("Network engineer",
     "Speeds, status, addressing and tenants; no serial numbers, asset tags or rack positions.",
     ["cable.type", "cable.length", "cable.status", "cable.tenant", "cable.description",
      "port.type", "port.speed", "port.status", "port.use", "port.label", "port.description", "port.marked_connected",
      "ct.port_speed", "ct.upstream_speed", "ct.xconnect", "ct.termination",
      "device.subtitle", "device.status", "device.tenant", "device.site", "device.platform", "device.ipv4",
      "device.ipv6", "device.description",
      "circuit.subtitle", "circuit.status", "circuit.tenant", "circuit.provider", "circuit.commit_rate",
      "circuit.installed", "circuit.terminates", "circuit.description",
      "site.status", "site.tenant", "site.region", "network.provider", "network.description",
      "doc.route", "doc.summary", "doc.generated"]),
    ("Facility / colo operator",
     "Site, rack, position, serial, asset tag and tenant; no addresses or comments.",
     ["cable.type", "cable.colour", "cable.length", "cable.status", "cable.tenant",
      "port.type", "port.positions", "port.module", "port.label",
      "ct.xconnect", "ct.patch_panel", "ct.termination",
      "device.subtitle", "device.status", "device.tenant", "device.site", "device.region", "device.location",
      "device.rack", "device.position", "device.serial", "device.asset_tag", "device.description",
      "circuit.subtitle", "circuit.status", "circuit.tenant", "circuit.provider", "circuit.description",
      "site.status", "site.tenant", "site.region", "site.facility", "site.timezone", "site.description",
      "doc.route", "doc.summary", "doc.generated"]),
    ("Customer-safe",
     "Names, site, port type, cable type and length, and circuit status and rate. Nothing internal.",
     ["cable.type", "cable.length", "cable.status", "port.type", "device.site",
      "circuit.subtitle", "circuit.status", "circuit.commit_rate", "ct.port_speed",
      "doc.route", "doc.summary"]),
]
