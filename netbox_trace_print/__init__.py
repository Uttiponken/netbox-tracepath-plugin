from netbox.plugins import PluginConfig

__version__ = "0.5.0"


class TraceprintConfig(PluginConfig):
    name = "netbox_trace_print"
    verbose_name = "Trace Print"
    description = "Printable PDF cable traces for technicians and field engineers."
    author = "Jean-Pierre"
    version = __version__
    base_url = "trace-print"
    min_version = "4.6.0"
    max_version = "4.6.99"
    # No settings yet. Every option (paper, orientation, fields) is chosen when printing.
    default_settings = {}


config = TraceprintConfig
