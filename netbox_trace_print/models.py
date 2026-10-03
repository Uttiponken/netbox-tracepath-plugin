"""
Print profiles: named sets of the facts a printout shows (see fields.py), kept in the plugin's own
tables. Nothing here points at any NetBox object, so a profile is independent of NetBox's data.
"""

from django.db import models
from django.urls import reverse

from netbox.models import ChangeLoggedModel


class PrintProfile(ChangeLoggedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_trace_print:printprofile", args=[self.pk])

    @property
    def keys(self):
        return sorted(row.key for row in self.field_rows.all())

    def set_keys(self, keys):
        """Make the profile show exactly `keys`."""
        keys = set(keys)
        self.field_rows.exclude(key__in=keys).delete()
        have = set(self.field_rows.values_list("key", flat=True))
        PrintProfileField.objects.bulk_create([PrintProfileField(profile=self, key=k) for k in sorted(keys - have)])


class PrintProfileField(models.Model):
    """One catalogue key that a profile shows."""
    profile = models.ForeignKey(PrintProfile, on_delete=models.CASCADE, related_name="field_rows")
    key = models.CharField(max_length=64)

    class Meta:
        ordering = ("key",)
        constraints = [models.UniqueConstraint(fields=("profile", "key"), name="traceprint_profile_key_unique")]

    def __str__(self):
        return f"{self.profile}: {self.key}"
