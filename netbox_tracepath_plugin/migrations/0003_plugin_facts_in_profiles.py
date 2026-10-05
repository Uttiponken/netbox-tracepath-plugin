"""Add the facts that the optional FMS and WDM integrations provide to the built-in profiles.

Written out literally, like 0002: a migration must not change when the catalogue does. A key for a plugin
that is not installed is simply ignored when printing."""

from django.db import migrations

ADD = {
    "Full information": ["fms.type", "fms.fibers", "fms.sheath", "fms.serial", "fms.installed", "fms.marks", "fms.notes",
                         "wdm.node", "wdm.channel", "wdm.status", "wdm.service", "wdm.line"],
    "Field technician": ["fms.type", "fms.fibers", "fms.serial", "fms.notes", "wdm.channel", "wdm.service", "wdm.line"],
    "Network engineer": ["fms.type", "wdm.node", "wdm.channel", "wdm.status", "wdm.service"],
    "Facility / colo operator": ["fms.type", "fms.sheath", "fms.serial", "fms.installed", "fms.marks", "wdm.service"],
}


def add(apps, schema_editor):
    Profile = apps.get_model("netbox_tracepath_plugin", "PrintProfile")
    Field = apps.get_model("netbox_tracepath_plugin", "PrintProfileField")
    for name, keys in ADD.items():
        profile = Profile.objects.filter(name=name).first()
        if profile is None:                    # the user renamed or deleted it: leave their choice alone
            continue
        have = set(Field.objects.filter(profile=profile).values_list("key", flat=True))
        Field.objects.bulk_create([Field(profile=profile, key=k) for k in keys if k not in have])


class Migration(migrations.Migration):

    dependencies = [("netbox_tracepath_plugin", "0002_seed_profiles")]

    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
