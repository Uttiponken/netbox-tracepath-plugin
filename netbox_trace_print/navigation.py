from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label="Trace Print",
    groups=(
        ("Printing", (
            PluginMenuItem(
                link="plugins:netbox_trace_print:index",
                link_text="Print cable trace",
                permissions=["dcim.view_cable"],
            ),
        )),
        ("Configuration", (
            PluginMenuItem(
                link="plugins:netbox_trace_print:printprofile_list",
                link_text="Print profiles",
                permissions=["netbox_trace_print.view_printprofile"],
                buttons=(
                    PluginMenuButton(
                        link="plugins:netbox_trace_print:printprofile_add",
                        title="Add",
                        icon_class="mdi mdi-plus-thick",
                        permissions=["netbox_trace_print.add_printprofile"],
                    ),
                ),
            ),
        )),
    ),
    icon_class="mdi mdi-printer",
)
