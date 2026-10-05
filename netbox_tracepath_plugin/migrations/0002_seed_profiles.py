"""Seed the five built-in print profiles, once. Written out literally on purpose: a migration must not
change when the catalogue in fields.py does."""

from django.db import migrations

PROFILES = [('Full information', 'Everything.',
  ['cable.type', 'cable.colour', 'cable.length', 'cable.status', 'cable.tenant', 'cable.description',
   'cable.tags', 'cable.comments', 'port.type', 'port.speed', 'port.status', 'port.use', 'port.positions',
   'port.module', 'port.label', 'port.description', 'port.marked_connected', 'ct.port_speed',
   'ct.upstream_speed', 'ct.xconnect', 'ct.patch_panel', 'ct.termination', 'device.subtitle', 'device.status',
   'device.tenant', 'device.site', 'device.region', 'device.location', 'device.rack', 'device.position',
   'device.serial', 'device.asset_tag', 'device.platform', 'device.ipv4', 'device.ipv6', 'device.description',
   'device.tags', 'device.comments', 'circuit.subtitle', 'circuit.status', 'circuit.tenant',
   'circuit.provider', 'circuit.commit_rate', 'circuit.installed', 'circuit.terminates',
   'circuit.description', 'circuit.tags', 'circuit.comments', 'site.status', 'site.tenant', 'site.region',
   'site.facility', 'site.timezone', 'site.description', 'network.provider', 'network.description',
   'doc.route', 'doc.summary', 'doc.generated']),
 ('Field technician',
  'Where things are and what to plug into: site, rack and position, serial and asset tag, port and cable '
  'details.',
  ['cable.type', 'cable.colour', 'cable.length', 'cable.status', 'cable.description', 'cable.comments',
   'port.type', 'port.positions', 'port.module', 'port.label', 'port.description', 'ct.xconnect',
   'ct.patch_panel', 'ct.termination', 'device.subtitle', 'device.site', 'device.location', 'device.rack',
   'device.position', 'device.serial', 'device.asset_tag', 'device.comments', 'circuit.subtitle',
   'circuit.provider', 'circuit.description', 'circuit.comments', 'site.facility', 'site.description',
   'doc.route', 'doc.summary', 'doc.generated']),
 ('Network engineer',
  'Speeds, status, addressing and tenants; no serial numbers, asset tags or rack positions.',
  ['cable.type', 'cable.length', 'cable.status', 'cable.tenant', 'cable.description', 'port.type',
   'port.speed', 'port.status', 'port.use', 'port.label', 'port.description', 'port.marked_connected',
   'ct.port_speed', 'ct.upstream_speed', 'ct.xconnect', 'ct.termination', 'device.subtitle', 'device.status',
   'device.tenant', 'device.site', 'device.platform', 'device.ipv4', 'device.ipv6', 'device.description',
   'circuit.subtitle', 'circuit.status', 'circuit.tenant', 'circuit.provider', 'circuit.commit_rate',
   'circuit.installed', 'circuit.terminates', 'circuit.description', 'site.status', 'site.tenant',
   'site.region', 'network.provider', 'network.description', 'doc.route', 'doc.summary', 'doc.generated']),
 ('Facility / colo operator', 'Site, rack, position, serial, asset tag and tenant; no addresses or comments.',
  ['cable.type', 'cable.colour', 'cable.length', 'cable.status', 'cable.tenant', 'port.type',
   'port.positions', 'port.module', 'port.label', 'ct.xconnect', 'ct.patch_panel', 'ct.termination',
   'device.subtitle', 'device.status', 'device.tenant', 'device.site', 'device.region', 'device.location',
   'device.rack', 'device.position', 'device.serial', 'device.asset_tag', 'device.description',
   'circuit.subtitle', 'circuit.status', 'circuit.tenant', 'circuit.provider', 'circuit.description',
   'site.status', 'site.tenant', 'site.region', 'site.facility', 'site.timezone', 'site.description',
   'doc.route', 'doc.summary', 'doc.generated']),
 ('Customer-safe',
  'Names, site, port type, cable type and length, and circuit status and rate. Nothing internal.',
  ['cable.type', 'cable.length', 'cable.status', 'port.type', 'device.site', 'circuit.subtitle',
   'circuit.status', 'circuit.commit_rate', 'ct.port_speed', 'doc.route', 'doc.summary'])]


def seed(apps, schema_editor):
    Profile = apps.get_model("netbox_tracepath_plugin", "PrintProfile")
    Field = apps.get_model("netbox_tracepath_plugin", "PrintProfileField")
    if Profile.objects.exists():          # someone already has profiles: leave them alone
        return
    for name, description, keys in PROFILES:
        profile = Profile.objects.create(name=name, description=description)
        Field.objects.bulk_create([Field(profile=profile, key=k) for k in keys])


class Migration(migrations.Migration):

    dependencies = [("netbox_tracepath_plugin", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
