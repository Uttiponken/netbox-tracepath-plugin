from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label="Tracepath",
    groups=(
        ("Printing", (
            PluginMenuItem(
                link="plugins:netbox_tracepath_plugin:index",
                link_text="Print cable trace",
                permissions=["dcim.view_cable"],
            ),
        )),
        ("Configuration", (
            PluginMenuItem(
                link="plugins:netbox_tracepath_plugin:printprofile_list",
                link_text="Print profiles",
                permissions=["netbox_tracepath_plugin.view_printprofile"],
                buttons=(
                    PluginMenuButton(
                        link="plugins:netbox_tracepath_plugin:printprofile_add",
                        title="Add",
                        icon_class="mdi mdi-plus-thick",
                        permissions=["netbox_tracepath_plugin.add_printprofile"],
                    ),
                ),
            ),
        )),
    ),
    icon_class="mdi mdi-printer",
)
