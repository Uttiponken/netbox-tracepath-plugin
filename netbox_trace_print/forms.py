from django import forms
from django.urls import reverse

from utilities.forms.fields import DynamicModelChoiceField
from utilities.forms.rendering import FieldSet
from utilities.forms.widgets import APISelect

from .collect import kinds, model_for
from .pdf.paper import CHOICES as PAPER_CHOICES, ORIENTATIONS
from .scope import KINDS


def pick_form(kind):
    """A form with one object selector for the chosen kind of object.

    Only objects that have a cable are offered: the others have no trace to print. The same filter goes to
    NetBox's API for the dropdown (a cheap check on the cable column) and to the form's own validation.
    """
    from .options import OPTION_KINDS, cable_label, port_label

    model = model_for(kind)
    cabled = kind in ("interface", "front-port", "circuit-termination")
    widget, label_from = None, None
    if kind in OPTION_KINDS:
        # our own options: 'equipment : port' (and cables with their ends), searchable by either part
        widget = APISelect()
        widget.attrs["data-url"] = reverse("plugins:netbox_trace_print:options", kwargs={"kind": kind})
        label_from = cable_label if kind == "cable" else port_label
    field = DynamicModelChoiceField(
        queryset=model.objects.filter(cable__isnull=False) if cabled else model.objects.all(),
        query_params={} if widget else {"cabled": "true"}, label=kinds()[kind][2], required=True, widget=widget,
        help_text="Only objects with a cable are listed." if cabled else "")
    if label_from:
        field.label_from_instance = label_from
    return type("PickForm", (forms.Form,), {"object": field})


class PrintOptionsForm(forms.Form):
    paper = forms.ChoiceField(choices=PAPER_CHOICES, initial="A4", label="Paper")
    orientation = forms.ChoiceField(choices=[(o, o.capitalize()) for o in ORIENTATIONS], initial="landscape")
    path = forms.ChoiceField(required=False, label="Path")
    profile = forms.ChoiceField(required=False, label="Profile",
                                help_text="Which facts to print. Pick one and press Apply, then adjust below.")
    prepared_for = forms.CharField(required=False, max_length=100, label="Prepared for",
                                   help_text="Optional. Printed under the title.")
    scope = forms.ChoiceField(required=False, label="Limit the print to",
                              help_text="Print only the part of the path in one site, location or rack. Where the path "
                                        "leaves it, a marker says where it continues.")

    def __init__(self, *args, path_choices=(), path_count=None, path_label="", profile_choices=(), **kwargs):
        """`path_choices` may be grouped ((group, ((value, label), ...)), ...), as for a trunk cable's pairs."""
        super().__init__(*args, **kwargs)
        if self.is_bound:                          # a page opened with some options still shows the defaults for the rest
            self.data = self.data.copy()
            self.data.setdefault("paper", "A4")
            self.data.setdefault("orientation", "landscape")
        # The print bar is laid out by hand, so its widgets get their look here. The short lists are plain selects
        # (class no-ts keeps NetBox's searchable dropdown off them): no cursor in a choice, no height changes.
        for name in ("profile", "paper", "orientation", "path", "scope"):
            self.fields[name].widget.attrs["class"] = "form-select no-ts"
        self.fields["prepared_for"].widget.attrs.update({"class": "form-control", "placeholder": "Optional, printed under the title"})
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
        self.fields["scope"].choices = [("", "Whole path")]

    def set_scopes(self, scopes):
        """Offer the scopes the trace passes through (scope.scopes_of), grouped by kind."""
        groups = []
        for kind, title in KINDS:
            items = [(s["value"], s["label"].split(": ", 1)[1]) for s in scopes if s["kind"] == kind]
            if items:
                groups.append((title, items))
        self.fields["scope"].choices = [("", "Whole path")] + groups
        self.fields["scope"].widget.attrs["form"] = "options-form"        # the form is the print bar at the top


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
