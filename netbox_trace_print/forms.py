from django import forms
from django.urls import reverse

from utilities.forms.fields import DynamicModelChoiceField
from utilities.forms.rendering import FieldSet
from utilities.forms.widgets import APISelect

from .collect import KINDS, model_for
from .pdf.paper import ORIENTATIONS, PAPER_MM


def pick_form(kind):
    """A form with one object selector for the chosen kind of object.

    Only objects that have a cable are offered: the others have no trace to print. The same filter goes to
    NetBox's API for the dropdown (a cheap check on the cable column) and to the form's own validation.
    """
    from .options import OPTION_KINDS, cable_label, port_label

    model = model_for(kind)
    cabled = kind != "cable"
    widget, label_from = None, None
    if kind in OPTION_KINDS:
        # our own options: 'equipment : port' (and cables with their ends), searchable by either part
        widget = APISelect()
        widget.attrs["data-url"] = reverse("plugins:netbox_trace_print:options", kwargs={"kind": kind})
        label_from = cable_label if kind == "cable" else port_label
    field = DynamicModelChoiceField(
        queryset=model.objects.filter(cable__isnull=False) if cabled else model.objects.all(),
        query_params={} if widget else {"cabled": "true"}, label=KINDS[kind][2], required=True, widget=widget,
        help_text="Only objects with a cable are listed." if cabled else "")
    if label_from:
        field.label_from_instance = label_from
    return type("PickForm", (forms.Form,), {"object": field})


class PrintOptionsForm(forms.Form):
    paper = forms.ChoiceField(choices=[(p, p) for p in PAPER_MM], initial="A4")
    orientation = forms.ChoiceField(choices=[(o, o.capitalize()) for o in ORIENTATIONS], initial="landscape")
    path = forms.ChoiceField(required=False, label="Path")
    profile = forms.ChoiceField(required=False, label="Profile",
                                help_text="Which facts to print. Pick one and press Apply, then adjust below.")
    prepared_for = forms.CharField(required=False, max_length=100, label="Prepared for",
                                   help_text="Optional. Printed under the title.")

    def __init__(self, *args, path_choices=(), path_count=None, path_label="", profile_choices=(), **kwargs):
        """`path_choices` may be grouped ((group, ((value, label), ...)), ...), as for a trunk cable's pairs."""
        super().__init__(*args, **kwargs)
        self.fields["path"].choices = list(path_choices)
        count = path_count if path_count is not None else len(path_choices)
        if path_label:
            self.fields["path"].label = path_label
        if count < 2:
            self.fields["path"].widget = forms.HiddenInput()
        else:
            # shown under the object picker, outside the options form, but submitted with it
            self.fields["path"].widget.attrs["form"] = "options-form"
        self.fields["profile"].choices = [("", "All facts (no profile)")] + list(profile_choices)


# -- print profiles ------------------------------------------------------------------

from . import catalogue  # noqa: E402
from .models import PrintProfile  # noqa: E402


class PrintProfileForm(forms.ModelForm):
    """A profile: a name and which facts it shows, grouped as in the catalogue."""

    class Meta:
        model = PrintProfile
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        chosen = set(self.instance.keys) if self.instance.pk else set()
        groups = catalogue.groups()
        self.fieldsets = (FieldSet("name", "description", name="Profile"),
                          *[FieldSet(f"keys_{g}", name=label) for g, label, _items in groups])
        for group, label, items in groups:
            self.fields[f"keys_{group}"] = forms.MultipleChoiceField(
                label=label, required=False, choices=items, initial=[k for k, _l in items if k in chosen],
                widget=forms.CheckboxSelectMultiple)
        self.group_fields = [f"keys_{g}" for g, _l, _i in groups]

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            profile.set_keys([k for f in self.group_fields for k in self.cleaned_data[f]])
        return profile
