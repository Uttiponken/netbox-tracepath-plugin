import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from netbox.views import generic
from utilities.views import ViewTab  # noqa: F401  (kept for tabs added later)

from . import __version__
from .collect import Collector, describe_path, kinds, model_for, pair_of, paths_through
from .extend import Chain
from . import catalogue
from .forms import PrintOptionsForm, PrintProfileForm, pick_form
from .layout import LayoutSpec, render as render_pdf
from .pdf.paper import parse_choice
from .models import PrintProfile
from .scope import apply_scope, scopes_of
from .selection import apply_selection
from .tables import PrintProfileTable


class KindPermissionMixin(PermissionRequiredMixin):
    """Needs the stock trace permission (view cables) and view permission on the chosen kind of object."""

    def has_permission(self):
        user, kind = self.request.user, self.kwargs.get("kind")
        if kind is not None and kind not in kinds():
            raise Http404
        perms = ["dcim.view_cable"]
        if kind:
            app, name, _label = kinds()[kind]
            perms.append(f"{app}.view_{name}")
        return user.is_authenticated and all(user.has_perm(p) for p in perms)


def _pickers(active=None, current=None):
    """One selector per kind of object, for the buttons and dropdown at the top of the pages.

    `current` is the object being printed: its selector shows it, so you can switch to another one.
    """
    out = []
    for slug, (_a, _m, label) in kinds().items():
        initial = {"object": current.pk} if current is not None and slug == active else None
        out.append({"slug": slug, "label": label, "form": pick_form(slug)(initial=initial), "active": slug == active})
    return out


CARRIED = ("paper", "orientation", "profile", "prepared_for")     # print settings that survive choosing another object


def _carried(request):
    """The print settings in a request, as a query string for the page that follows."""
    kept = [(k, request.GET[k]) for k in CARRIED if request.GET.get(k)]
    return urlencode(kept)


class IndexView(KindPermissionMixin, View):
    def get(self, request):
        # The start page is the print page with nothing chosen yet: one layout, one place to choose. The print
        # bar is there already; its settings are carried to the print page when something is chosen.
        kind = request.GET.get("kind")
        profiles = PrintProfile.objects.restrict(request.user, "view")
        form = PrintOptionsForm(request.GET or None, profile_choices=[(str(p.pk), p.name) for p in profiles])
        return render(request, "netbox_trace_print/print.html", {
            "object": None, "pickers": _pickers(kind if kind in kinds() else None), "form": form})


class OptionsView(KindPermissionMixin, View):
    """JSON for the dropdowns: ports as 'equipment : port', cables with their ends."""

    def get(self, request, kind):
        from .options import OPTION_KINDS, search

        if kind not in OPTION_KINDS:
            raise Http404
        return JsonResponse(search(kind, request.user, request.GET.get("q", ""), request.GET.get("limit"),
                                   request.GET.get("offset")))


class PickView(KindPermissionMixin, View):
    """Where the selectors submit to: on to the print page, or back to the start if nothing valid was chosen."""

    def get(self, request, kind):
        form = pick_form(kind)(request.GET or None)
        carried = _carried(request)
        if form.is_valid():
            url = reverse("plugins:netbox_trace_print:print", kwargs={"kind": kind, "pk": form.cleaned_data["object"].pk})
            return redirect(url + (f"?{carried}" if carried else ""))
        if request.GET.get("object"):
            messages.error(request, "That object has no cable, so there is no trace to print.")
        return redirect(reverse("plugins:netbox_trace_print:index") + f"?kind={kind}" + (f"&{carried}" if carried else ""))


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


SERVICE_KINDS = {"wdm-circuit": "wdm", "fiber-circuit": "fms"}      # starting points that are services, not equipment


def _service(kind):
    """The integration module that finds a service's paths and trims a trace to it, or None for other kinds."""
    from .integrations import MODULES

    return MODULES[SERVICE_KINDS[kind]] if kind in SERVICE_KINDS else None


def _starting_paths(kind, obj):
    """The paths to offer for the chosen object: (paths, labels by path id, cable for the pair choice, service details)."""
    service = _service(kind)
    if service is not None:
        found = service.circuit_paths(obj)
        return [f["path"] for f in found], {f["path"].pk: f["label"] for f in found}, None, {f["path"].pk: f for f in found}
    target = obj.cable if kind == "fiber-cable" else obj
    return paths_through(target), {}, (target if kind in ("cable", "fiber-cable") else None), {}


def _prepare(request, kind, pk):
    """Everything both the print page and the PDF need: object, chosen path, options, facts, the rendered PDF."""
    obj = _object(request, kind, pk)
    paths, labels, cable, service_entries = _starting_paths(kind, obj)
    name = lambda p: labels.get(p.pk) or describe_path(p)
    profiles = list(PrintProfile.objects.restrict(request.user, "view"))
    pairs = {}
    if cable is not None:                          # a trunk carries several pairs: which one is asked for first
        for p in paths:
            pairs.setdefault(pair_of(p, cable) or "", []).append(p)
    if pairs and "" not in pairs:
        choices = [(pair, [(str(p.pk), f"{pair} · {name(p)}") for p in group])
                   for pair, group in sorted(pairs.items(), key=lambda kv: (len(kv[0]), kv[0]))]
        path_label = "Pair and direction"
    else:
        choices, path_label = [(str(p.pk), name(p)) for p in paths], ""
    form = PrintOptionsForm(request.GET or None, path_choices=choices, path_count=len(paths), path_label=path_label,
                            profile_choices=[(str(p.pk), p.name) for p in profiles])
    needs_pair = len(pairs) > 1
    data = _options(request, form)
    path = next((p for p in paths if str(p.pk) == data.get("path")), None)
    if path is None and paths and not (needs_pair and not data.get("path")):
        path = paths[0]
    needs_pair = needs_pair and path is None
    profile = next((p for p in profiles if str(p.pk) == data.get("profile")), None)
    keys, layout_name = _choose_keys(request, profile)
    result = chain = None
    scopes, scope = [], ""
    if path:
        collector = Collector(request.user)
        service = _service(kind)
        if service is not None:                    # a service stops where it ends and is not extended
            doc = service.trim_doc(collector.chain_doc([collector.part(path)], origin_label=str(obj)), service_entries[path.pk], obj)
        else:
            chain = Chain(request.user, path, before=request.GET.getlist("before"), after=request.GET.getlist("after"))
            doc = collector.chain_doc(chain.parts(collector), origin_label=str(obj))
        scopes = scopes_of(doc)                    # decided on the full document, before any fact is hidden
        form.set_scopes(scopes)
        scope = request.GET.get("scope", "")
        scope = scope if scope in {s["value"] for s in scopes} else ""
        if scope:
            doc = apply_scope(doc, scope)
        doc = apply_selection(doc, keys, layout_name=layout_name, prepared_for=data.get("prepared_for", ""))
        paper, color = parse_choice(data["paper"])
        pdf, report = render_pdf(doc, LayoutSpec(paper=paper, orientation=data["orientation"], color=color))
        result = {"doc": doc, "pdf": pdf, "report": report}
    return {"obj": obj, "form": form, "data": data, "path": path, "result": result, "keys": keys,
            "profile": profile, "layout_name": layout_name, "chain": chain, "needs_pair": needs_pair,
            "pair_count": len(pairs), "scopes": scopes, "scope": scope}


def _pdf_query(prep):
    """The query string that reproduces this exact printout."""
    data = prep["data"]
    pairs = [("paper", data["paper"]), ("orientation", data["orientation"])]
    if prep["path"]:
        pairs.append(("path", prep["path"].pk))
    if prep["profile"]:
        pairs.append(("profile", prep["profile"].pk))
    if prep["scope"]:
        pairs.append(("scope", prep["scope"]))
    if data.get("prepared_for"):
        pairs.append(("prepared_for", data["prepared_for"]))
    pairs.append(("custom", 1))
    pairs += [("fields", k) for k in catalogue.all_keys() if k in prep["keys"]]
    if prep["chain"]:
        pairs += [(side, pk) for side, ids in prep["chain"].ids.items() for pk in ids]
    return urlencode(pairs)


def _extension(request, prep):
    """What the 'Extend the trace' card shows: what has been added, and what can be added at each end."""
    chain = prep["chain"]
    if chain is None:
        return None
    opened = bool(request.GET.get("extend"))

    def url(add=None, drop=None, extend=True):
        q = request.GET.copy()
        q.pop("apply", None)
        q.setlist("before", [str(i) for i in chain.ids["before"]])
        q.setlist("after", [str(i) for i in chain.ids["after"]])
        if add:
            q.appendlist(*add)
        if drop:
            q.setlist(drop, q.getlist(drop)[:-1])
        if extend:
            q["extend"] = "1"
        else:
            q.pop("extend", None)
        return "?" + q.urlencode()

    sides = []
    for side, title, added in (("before", "At the start", chain.before), ("after", "At the end", chain.after)):
        entry = {"side": side, "title": title, "added": [], "device": None, "groups": None}
        for i, (port, path) in enumerate(added):
            entry["added"].append({"label": describe_path(path, reverse=(side == "before")).split("  ·  ")[0],
                                   "remove": url(drop=side) if i == len(added) - 1 else None})
        if opened:
            found = chain.candidates(request.user, side)
            if found:
                entry["device"] = found["device"]
                entry["groups"] = [(far, [dict(item, url=url(add=(side, item["id"]))) for item in items])
                                   for far, items in found["groups"]]
        sides.append(entry)
    return {"open": opened, "show_url": url(), "hide_url": url(extend=False), "sides": sides,
            "before": chain.ids["before"], "after": chain.ids["after"], "count": len(chain.before) + len(chain.after)}


class PrintView(KindPermissionMixin, View):
    def get(self, request, kind, pk):
        prep = _prepare(request, kind, pk)
        result = prep["result"]
        pdf_url = reverse("plugins:netbox_trace_print:pdf", kwargs={"kind": kind, "pk": pk}) + "?" + _pdf_query(prep)
        groups = [{"label": label, "items": [(k, l, k in prep["keys"]) for k, l in items]} for _g, label, items in catalogue.groups()]
        return render(request, "netbox_trace_print/print.html", {
            "object": prep["obj"], "kind": kind, "label": kinds()[kind][2], "form": prep["form"], "path": prep["path"],
            "report": result["report"] if result else None, "doc": result["doc"] if result else None,
            "pdf_url": pdf_url, "groups": groups, "layout_name": prep["layout_name"],
            "needs_pair": prep["needs_pair"], "pair_count": prep["pair_count"],
            "selected": len(prep["keys"]), "total": len(catalogue.all_keys()), "pickers": _pickers(kind, prep["obj"]),
            "ext": _extension(request, prep), "has_scopes": bool(prep["scopes"]), "scope": prep["scope"],
        })


class PdfView(KindPermissionMixin, View):
    def get(self, request, kind, pk):
        prep = _prepare(request, kind, pk)
        if prep["needs_pair"]:
            return HttpResponse("This cable is a trunk with several pairs in use: choose which pair to print.",
                                status=400, content_type="text/plain; charset=utf-8")
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
