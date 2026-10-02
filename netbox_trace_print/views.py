from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import render
from django.views import View

from . import __version__


class IndexView(PermissionRequiredMixin, View):
    """Entry page. The trace selection form and PDF output arrive in the next step."""

    permission_required = "dcim.view_cable"

    def get(self, request):
        return render(request, "netbox_trace_print/index.html", {"version": __version__})
