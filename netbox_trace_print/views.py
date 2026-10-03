import re

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from . import __version__
from .collect import KINDS, Collector, describe_path, model_for, paths_through
from .forms import PrintOptionsForm, pick_form
from .layout import LayoutSpec, render as render_pdf


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


class IndexView(KindPermissionMixin, View):
    def get(self, request):
        kinds = [(slug, label) for slug, (_a, _m, label) in KINDS.items()]
        return render(request, "netbox_trace_print/index.html", {"kinds": kinds, "version": __version__})


class PickView(KindPermissionMixin, View):
    def get(self, request, kind):
        form = pick_form(kind)(request.GET or None)
        if form.is_valid():
            return redirect(reverse("plugins:netbox_trace_print:print", kwargs={"kind": kind, "pk": form.cleaned_data["object"].pk}))
        return render(request, "netbox_trace_print/pick.html", {"form": form, "kind": kind, "label": KINDS[kind][2]})


def _object(request, kind, pk):
    return get_object_or_404(model_for(kind).objects.restrict(request.user, "view"), pk=pk)


def _prepare(request, kind, pk):
    """Everything both the print page and the PDF need: object, chosen path, options, the rendered PDF."""
    obj = _object(request, kind, pk)
    paths = paths_through(obj)
    choices = [(str(p.pk), describe_path(p)) for p in paths]
    form = PrintOptionsForm(request.GET or None, path_choices=choices)
    valid = form.is_valid() if request.GET else False
    data = form.cleaned_data if valid else {"paper": "A4", "orientation": "landscape", "path": ""}
    path = next((p for p in paths if str(p.pk) == data.get("path")), paths[0] if paths else None)
    result = None
    if path:
        doc = Collector(request.user).trace_doc(path, origin_label=str(obj))
        pdf, report = render_pdf(doc, LayoutSpec(paper=data["paper"], orientation=data["orientation"]))
        result = {"doc": doc, "pdf": pdf, "report": report}
    return obj, form, data, path, result


class PrintView(KindPermissionMixin, View):
    def get(self, request, kind, pk):
        obj, form, data, path, result = _prepare(request, kind, pk)
        query = request.GET.urlencode()
        pdf_url = reverse("plugins:netbox_trace_print:pdf", kwargs={"kind": kind, "pk": pk}) + (f"?{query}" if query else "")
        return render(request, "netbox_trace_print/print.html", {
            "object": obj, "kind": kind, "label": KINDS[kind][2], "form": form, "path": path,
            "report": result["report"] if result else None, "doc": result["doc"] if result else None,
            "pdf_url": pdf_url, "version": __version__,
        })


class PdfView(KindPermissionMixin, View):
    def get(self, request, kind, pk):
        obj, _form, _data, path, result = _prepare(request, kind, pk)
        if not path:
            raise Http404("No cable path found for this object.")
        if not result["report"].fits:
            return HttpResponse("\n".join(result["report"].warnings), status=422, content_type="text/plain; charset=utf-8")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(obj)).strip("-") or "trace"
        disposition = "attachment" if request.GET.get("download") else "inline"
        response = HttpResponse(result["pdf"], content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="trace-{slug}.pdf"'
        return response
