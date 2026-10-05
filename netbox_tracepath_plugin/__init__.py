from netbox.plugins import PluginConfig

__version__ = "0.7.0"


class TracepathConfig(PluginConfig):
    name = "netbox_tracepath_plugin"
    verbose_name = "Tracepath"
    description = "Printable PDF cable traces for technicians and field engineers."
    author = "JP, co-authored with Claude Sonnet 5.5"
    version = __version__
    base_url = "tracepath"
    min_version = "4.6.0"
    max_version = "4.6.99"
    # No settings yet. Every option (paper, orientation, fields) is chosen when printing.
    default_settings = {}

    def ready(self):
        super().ready()
        from .table_columns import register
        register()


config = TracepathConfig
