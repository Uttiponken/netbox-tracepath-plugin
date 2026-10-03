import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from netbox.views import generic
from utilities.views import ViewTab  # noqa: F401  (kept for tabs added later)

from . import __version__
from .collect import KINDS, Collector, describe_path, model_for, paths_through
from . import catalogue
from .forms import PrintOptionsForm, PrintProfileForm, pick_form
from .layout import LayoutSpec, render as render_pdf
from .models import PrintProfile
from .selection import apply_selection
from .tables import PrintProfileTable


class KindPermissionMixin(PermissionRequiredMixin):
    """Needs the stock trace permission (view cables) and view permission on the chosen kind of object."""

    def has_permission(self):
        user, kind = self.request.user, self.kwargs.get("kind")
        if kind is not None and kind not in KINDS:
            raise Http404
        perms = ["dcim.view_cable"]
        if kind:
            app, name, _label = KINDS[kind]
            perms.append(f"{app}.view_{name}")
        return user.is_authenticated and all(user.has_perm(p) for p in perms)


def _pickers(active=None, current=None):
    """One selector per kind of object, for the buttons and dropdown at the top of the pages.

    `current` is the object being printed: its selector shows it, so you can switch to another one.
    """
    out = []
    for slug, (_a, _m, label) in KINDS.items():
        initial = {"object": current.pk} if current is not None and slug == active else None
        out.append({"slug": slug, "label": label, "form": pick_form(slug)(initial=initial), "active": slug == active})
    return out


class IndexView(KindPermissionMixin, View):
    def get(self, request):
        # The start page is the print page with nothing chosen yet: one layout, one place to choose.
        kind = request.GET.get("kind")
        return render(request, "netbox_trace_print/print.html", {
            "object": None, "pickers": _pickers(kind if kind in KINDS else None), "version": __version__})


class PickView(KindPermissionMixin, View):
    """Where the selectors submit to: on to the print page, or back to the start if nothing valid was chosen."""

    def get(self, request, kind):
        form = pick_form(kind)(request.GET or None)
        if form.is_valid():
            return redirect(reverse("plugins:netbox_trace_print:print", kwargs={"kind": kind, "pk": form.cleaned_data["object"].pk}))
        if request.GET.get("object"):
            messages.error(request, "That object has no cable, so there is no trace to print.")
        return redirect(reverse("plugins:netbox_trace_print:index") + f"?kind={kind}")


def _object(request, kind, pk):
    return get_object_or_404(model_for(kind).objects.restrict(request.user, "view"), pk=pk)


def _choose_keys(request, profile):
    """The facts to print, and what to call the choice in the footer.

    Pressing Apply, or arriving without having customised anything, takes the profile's facts (all facts
    if there is no profile). Otherwise the ticked boxes win, including none ticked.
    """
    base = set(profile.keys) if profile else set(catalogue.all_keys())
    if request.GET.get("custom") and not request.GET.get("apply"):
        keys = set(request.GET.getlist("fields")) & set(catalogue.all_keys())
    else:
        keys = base & set(catalogue.all_keys())
    if profile:
        name = profile.name if keys == (base & set(catalogue.all_keys())) else f"{profile.name} (adjusted)"
    else:
        name = "All facts" if keys == set(catalogue.all_keys()) else "Custom selection"
    return keys, name


def _options(request, form):
    """Each option on its own: a missing or invalid one falls back to its default instead of spoiling the rest."""
    defaults = {"paper": "A4", "orientation": "landscape", "path": "", "profile": "", "prepared_for": ""}
    data = {}
    for name, default in defaults.items():
        raw = request.GET.get(name, "")
        try:
            data[name] = form.fields[name].clean(raw) if raw else default
        except ValidationError:
            data[name] = default
    return data


def _prepare(request, kind, pk):
    """Everything both the print page and the PDF need: object, chosen path, options, facts, the rendered PDF."""
    obj = _object(request, kind, pk)
    paths = paths_through(obj)
    profiles = list(PrintProfile.objects.restrict(request.user, "view"))
    form = PrintOptionsForm(request.GET or None, path_choices=[(str(p.pk), describe_path(p)) for p in paths],
                            profile_choices=[(str(p.pk), p.name) for p in profiles])
    data = _options(request, form)
    path = next((p for p in paths if str(p.pk) == data.get("path")), paths[0] if paths else None)
    profile = next((p for p in profiles if str(p.pk) == data.get("profile")), None)
    keys, layout_name = _choose_keys(request, profile)
    result = None
    if path:
        doc = Collector(request.user).trace_doc(path, origin_label=str(obj))
        doc = apply_selection(doc, keys, layout_name=layout_name, prepared_for=data.get("prepared_for", ""))
        pdf, report = render_pdf(doc, LayoutSpec(paper=data["paper"], orientation=data["orientation"]))
        result = {"doc": doc, "pdf": pdf, "report": report}
    return {"obj": obj, "form": form, "data": data, "path": path, "result": result, "keys": keys,
            "profile": profile, "layout_name": layout_name}


def _pdf_query(prep):
    """The query string that reproduces this exact printout."""
    data = prep["data"]
    pairs = [("paper", data["paper"]), ("orientation", data["orientation"])]
    if prep["path"]:
        pairs.append(("path", prep["path"].pk))
    if prep["profile"]:
        pairs.append(("profile", prep["profile"].pk))
    if data.get("prepared_for"):
        pairs.append(("prepared_for", data["prepared_for"]))
    pairs.append(("custom", 1))
    pairs += [("fields", k) for k in catalogue.all_keys() if k in prep["keys"]]
    return urlencode(pairs)


class PrintView(KindPermissionMixin, View):
    def get(self, request, kind, pk):
        prep = _prepare(request, kind, pk)
        result = prep["result"]
        pdf_url = reverse("plugins:netbox_trace_print:pdf", kwargs={"kind": kind, "pk": pk}) + "?" + _pdf_query(prep)
        groups = [{"label": label, "items": [(k, l, k in prep["keys"]) for k, l in items]} for _g, label, items in catalogue.groups()]
        return render(request, "netbox_trace_print/print.html", {
            "object": prep["obj"], "kind": kind, "label": KINDS[kind][2], "form": prep["form"], "path": prep["path"],
            "report": result["report"] if result else None, "doc": result["doc"] if result else None,
            "pdf_url": pdf_url, "version": __version__, "groups": groups, "layout_name": prep["layout_name"],
            "selected": len(prep["keys"]), "total": len(catalogue.all_keys()), "pickers": _pickers(kind, prep["obj"]),
        })


class PdfView(KindPermissionMixin, View):
    def get(self, request, kind, pk):
        prep = _prepare(request, kind, pk)
        if not prep["path"]:
            raise Http404("No cable path found for this object.")
        result = prep["result"]
        if not result["report"].fits:
            return HttpResponse("\n".join(result["report"].warnings), status=422, content_type="text/plain; charset=utf-8")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(prep["obj"])).strip("-") or "trace"
        disposition = "attachment" if request.GET.get("download") else "inline"
        response = HttpResponse(result["pdf"], content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="trace-{slug}.pdf"'
        return response


# -- print profiles (NetBox's generic object views) ------------------------------------------

class PrintProfileListView(generic.ObjectListView):
    queryset = PrintProfile.objects.all()
    table = PrintProfileTable


class PrintProfileView(generic.ObjectView):
    queryset = PrintProfile.objects.all()

    def get_extra_context(self, request, instance):
        chosen = set(instance.keys)
        known = [{"label": label, "items": [(l, k in chosen) for k, l in items]} for _g, label, items in catalogue.groups()]
        keys = set(catalogue.all_keys())
        return {"groups": known, "stale": sorted(chosen - keys), "selected": len(chosen & keys), "total": len(keys)}


class PrintProfileEditView(generic.ObjectEditView):
    queryset = PrintProfile.objects.all()
    form = PrintProfileForm


class PrintProfileDeleteView(generic.ObjectDeleteView):
    queryset = PrintProfile.objects.all()
