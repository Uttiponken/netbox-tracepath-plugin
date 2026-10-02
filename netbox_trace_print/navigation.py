from netbox.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_trace_print:index",
        link_text="Print cable trace",
        permissions=["dcim.view_cable"],
    ),
)
