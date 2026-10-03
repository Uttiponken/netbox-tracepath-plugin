import django_tables2 as tables

from netbox.tables import NetBoxTable

from .models import PrintProfile


class PrintProfileTable(NetBoxTable):
    name = tables.Column(linkify=True)
    field_count = tables.Column(verbose_name="Facts shown", orderable=False, empty_values=())

    class Meta(NetBoxTable.Meta):
        model = PrintProfile
        fields = ("pk", "id", "name", "description", "field_count", "created", "last_updated")
        default_columns = ("name", "description", "field_count")

    def render_field_count(self, record):
        return record.field_rows.count()
