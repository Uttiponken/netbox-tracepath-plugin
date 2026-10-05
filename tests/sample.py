"""Synthetic but realistic traces for exercising the layout engine."""

from netbox_tracepath_plugin.model import Block, Cable, Field, Link, PortRow, TraceDoc

YELLOW, GRAY, BLACK = "ffeb3b", "9e9e9e", "111111"


def _device(title, role, dtype, in_port="", out_port="", site="Nordfiber Stockholm DC", rack="STO-TR-01", u="U34",
            loc="Telecom Room", tenant="Nordfiber AB", serial="ARI-STO-0002", asset="NF-STO-00005", port_fields=True):
    pf = lambda t, lab="": [Field("Type", t)] + ([Field("Label", lab)] if lab else []) if port_fields else []
    return Block(
        title=title, subtitle=f"{role} · {dtype}", kind="device",
        ports=[PortRow(in_name=in_port, in_fields=pf("10GBASE-X-SFP+") if in_port else [],
                       out_name=out_port, out_fields=pf("LC/APC") if out_port else [])],
        fields=[Field("Site", site), Field("Location", loc), Field("Rack", f"{rack} · {u} front"),
                Field("Tenant", tenant), Field("Serial", serial), Field("Asset tag", asset)],
        site=site, location=loc, rack=rack)


def _cable(label, ctype="smf-os2", length="2 m", color=YELLOW, cname="Yellow", tenant="Nordfiber AB", status="Connected"):
    return Cable(title=label, color_hex=color, color_name=cname,
                 fields=[Field("Type", ctype), Field("Length", length), Field("Status", status), Field("Tenant", tenant)])


def long_trace(blocks=11):
    """A chain like a colo tenant's path through two MeetMe panels and a patch panel, then onwards."""
    names = [
        ("polaris-sto-sw-01", "Access Switch", "Arista DCS-7010T-48", "", "Ethernet49"),
        ("polaris-sto-tor-01", "Patch Panel", "Generic LC 24-port fiber patch panel", "Port 1", "Port 1"),
        ("sto-mmr-polaris-01", "Patch Panel", "Generic LC 24-port fiber patch panel", "Port 1", "Port 1"),
        ("sto-mmr-nordfiber-01", "Patch Panel", "Generic LC 24-port fiber patch panel", "Port 1", "Port 1"),
        ("sto-patch-01", "Patch Panel", "Generic LC 24-port fiber patch panel", "Port 4", "Port 4"),
        ("sto-sw-01", "Aggregation Switch", "Arista DCS-7050SX3-48YC8-F", "Ethernet2", ""),
    ]
    extra = [("sto-rtr-01", "Core Router", "Juniper MX204", "xe-0/1/0", "xe-0/1/1"),
             ("got-patch-01", "Patch Panel", "Generic LC 24-port fiber patch panel", "Port 1", "Port 1"),
             ("got-wdm-01", "WDM Terminal", "Smartoptics DCP-M40-PAM4-ER", "Line", "922"),
             ("got-wdm-02", "WDM Terminal", "Smartoptics DCP-M40-PAM4-ER", "922", "Line"),
             ("mma-patch-01", "Patch Panel", "Generic LC 24-port fiber patch panel", "Port 2", "Port 2"),
             ("mma-rtr-01", "Core Router", "Juniper MX204", "et-0/0/1", "")]
    allb = (names[:-1] + extra + [names[-1]])[:blocks]
    allb[-1] = allb[-1][:4] + ("",)
    blocks_ = [_device(t, r, d, i, o, rack=f"STO-TR-{k % 3 + 1:02d}", u=f"U{42 - k}") for k, (t, r, d, i, o) in enumerate(allb)]
    links = [Link([_cable(f"sto-cbl-{k + 1:05d}", length=("30 m" if k % 3 == 1 else "2 m"))]) for k in range(len(blocks_) - 1)]
    return TraceDoc(
        title=f"Cable trace: sto-cbl-00001 … sto-cbl-{len(links):05d}",
        summary=["From polaris-sto-sw-01 : Ethernet49   to   mma-rtr-01 : et-0/0/1",
                 f"{len(links)} cables · total length 126 m+ · path complete"],
        blocks=blocks_, links=links,
        notes=["Path is incomplete beyond the last block: the far end is not connected."] if blocks == 7 else [],
        footer="Generated 2026-10-02 by demo-loader · netbox-tracepath-plugin 0.1.0")


def tiny_trace():
    return long_trace(3)


def hostile_trace():
    """Everything that makes layout hard: very long unbreakable values, many fields, UTF-8, empty parts."""
    long_id = "X" * 70
    url = "https://netbox.example.com/dcim/interfaces/12345/trace/?cablepath_id=98765&render=pdf"
    blocks = []
    for k in range(6):
        b = _device(f"hostile-device-with-a-really-long-name-number-{k}", "Röuter · Ålesund Ünïcode Ωmega Привет",
                    "Vendor Model " + "ABCDEFGHIJ" * 4, "Ethernet1/1/" + str(k) * 12, "xe-0/1/" + str(k) * 12)
        b.fields += [Field(f"Extra field {i}", url if i % 2 else long_id) for i in range(6)]
        b.fields.append(Field("A very long label that needs wrapping too", "value"))
        b.fields.append(Field("Comments", "Line one\nLine two with åäö\n" + "word " * 40))
        blocks.append(b)
    blocks.append(Block(title="Circuit NF-BRG-0001", subtitle="Nordfiber AB · Ethernet Private Line", kind="circuit"))
    links = [Link([_cable(f"cable-{long_id[:30]}-{k}", tenant="Ünïcode Tenant Ålesund " * 3)]) for k in range(len(blocks) - 1)]
    links[2] = Link([_cable("fan-a"), _cable("fan-b", color="", cname="")])      # a path that fans out
    return TraceDoc(title="Hostile trace " + long_id, summary=["x " * 80, "y"], blocks=blocks, links=links,
                    notes=["Path is split: " + "node " * 60], footer="f")


def single_block():
    return TraceDoc(title="Single block", blocks=[_device("only-one", "Server", "Dell R650", "", "Gig-E 1")], links=[])
