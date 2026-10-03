"""Add the facts about strands and fiber circuits (the FMS integration) to the built-in profiles.

Written out literally, like 0002 and 0003: a migration must not change when the catalogue does. A key for a
plugin that is not installed is simply ignored when printing."""

from django.db import migrations

ADD = {
    "Full information": ["fms.strands", "fms.circuit", "fms.optics"],
    "Field technician": ["fms.strands", "fms.circuit"],
    "Network engineer": ["fms.circuit", "fms.optics"],
    "Facility / colo operator": ["fms.strands", "fms.circuit"],
}


def add(apps, schema_editor):
    Profile = apps.get_model("netbox_trace_print", "PrintProfile")
    Field = apps.get_model("netbox_trace_print", "PrintProfileField")
    for name, keys in ADD.items():
        profile = Profile.objects.filter(name=name).first()
        if profile is None:                    # the user renamed or deleted it: leave their choice alone
            continue
        have = set(Field.objects.filter(profile=profile).values_list("key", flat=True))
        Field.objects.bulk_create([Field(profile=profile, key=k) for k in keys if k not in have])


class Migration(migrations.Migration):

    dependencies = [("netbox_trace_print", "0003_plugin_facts_in_profiles")]

    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
