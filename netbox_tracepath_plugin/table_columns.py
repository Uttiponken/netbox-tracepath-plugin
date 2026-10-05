"""
An optional "Print trace" column for NetBox's own lists of cables, interfaces, front ports and circuit
terminations: a printer icon on every row that opens that object in the print page.

The column is registered here but not shown by default. A user turns it on with Configure Table above a list
(it is listed under the available columns as "Print trace"), and NetBox remembers it for that user.
"""

from django.utils.translation import gettext_lazy as _

from circuits.tables.circuits import CircuitTerminationTable
from dcim.tables.cables import CableTable
from dcim.tables.devices import DeviceFrontPortTable, DeviceInterfaceTable, FrontPortTable, InterfaceTable
from netbox.tables import columns
from utilities.tables import register_table_column

NAME = "print_trace"

# (table, print page kind, whether a row only has a trace when a cable is attached)
TABLES = (
    (CableTable, "cable", False),
    (InterfaceTable, "interface", True),
    (DeviceInterfaceTable, "interface", True),
    (FrontPortTable, "front-port", True),
    (DeviceFrontPortTable, "front-port", True),
    (CircuitTerminationTable, "circuit-termination", True),
)

CODE = """{% if perms.dcim.view_cable %}{% if CABLE_CHECK %}<a href="{% url 'plugins:netbox_tracepath_plugin:print' kind='KIND' pk=record.pk %}" class="btn btn-sm btn-primary" title="Print trace as PDF"><i class="mdi mdi-printer"></i></a>{% endif %}{% endif %}"""


def _column(kind, needs_cable):
    code = CODE.replace("KIND", kind).replace("CABLE_CHECK", "record.cable" if needs_cable else "True")
    return columns.TemplateColumn(template_code=code, verbose_name=_("Print trace"), orderable=False,
                                  exclude_from_export=True)


def register():
    for table, kind, needs_cable in TABLES:
        try:
            register_table_column(_column(kind, needs_cable), NAME, table)
        except ValueError:                       # already registered (the app was set up twice)
            pass
