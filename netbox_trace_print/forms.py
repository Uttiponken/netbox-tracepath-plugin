from django import forms

from utilities.forms.fields import DynamicModelChoiceField
from utilities.forms.rendering import FieldSet

from .collect import KINDS, model_for
from .pdf.paper import ORIENTATIONS, PAPER_MM


def pick_form(kind):
    """A form with one object selector for the chosen kind of object."""
    model = model_for(kind)
    return type("PickForm", (forms.Form,), {
        "object": DynamicModelChoiceField(queryset=model.objects.all(), label=KINDS[kind][2], required=True),
    })


class PrintOptionsForm(forms.Form):
    paper = forms.ChoiceField(choices=[(p, p) for p in PAPER_MM], initial="A4")
    orientation = forms.ChoiceField(choices=[(o, o.capitalize()) for o in ORIENTATIONS], initial="landscape")
    path = forms.ChoiceField(required=False, label="Path")
    profile = forms.ChoiceField(required=False, label="Profile",
                                help_text="Which facts to print. Pick one and press Apply, then adjust below.")
    prepared_for = forms.CharField(required=False, max_length=100, label="Prepared for",
                                   help_text="Optional. Printed under the title.")

    def __init__(self, *args, path_choices=(), profile_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["path"].choices = list(path_choices)
        if len(path_choices) < 2:
            self.fields["path"].widget = forms.HiddenInput()
        self.fields["profile"].choices = [("", "All facts (no profile)")] + list(profile_choices)


# -- print profiles ------------------------------------------------------------------

from .fields import GROUPS  # noqa: E402
from .models import PrintProfile  # noqa: E402


class PrintProfileForm(forms.ModelForm):
    """A profile: a name and which facts it shows, grouped as in the catalogue."""

    fieldsets = (FieldSet("name", "description", name="Profile"),
                 *[FieldSet(f"keys_{g}", name=label) for g, label, _items in GROUPS])

    class Meta:
        model = PrintProfile
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        chosen = set(self.instance.keys) if self.instance.pk else set()
        for group, label, items in GROUPS:
            self.fields[f"keys_{group}"] = forms.MultipleChoiceField(
                label=label, required=False, choices=items, initial=[k for k, _l in items if k in chosen],
                widget=forms.CheckboxSelectMultiple)
        self.group_fields = [f"keys_{g}" for g, _l, _i in GROUPS]

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            profile.set_keys([k for f in self.group_fields for k in self.cleaned_data[f]])
        return profile
