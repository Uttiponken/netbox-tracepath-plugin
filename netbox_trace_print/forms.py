from django import forms

from utilities.forms.fields import DynamicModelChoiceField

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

    def __init__(self, *args, path_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["path"].choices = list(path_choices)
        if len(path_choices) < 2:
            self.fields["path"].widget = forms.HiddenInput()
