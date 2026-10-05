from django.urls import path

from netbox.views.generic import ObjectChangeLogView

from . import views
from .models import PrintProfile

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),

    # print profiles; these come before the <kind> patterns
    path("profiles/", views.PrintProfileListView.as_view(), name="printprofile_list"),
    path("profiles/add/", views.PrintProfileEditView.as_view(), name="printprofile_add"),
    path("profiles/<int:pk>/", views.PrintProfileView.as_view(), name="printprofile"),
    path("profiles/<int:pk>/edit/", views.PrintProfileEditView.as_view(), name="printprofile_edit"),
    path("profiles/<int:pk>/delete/", views.PrintProfileDeleteView.as_view(), name="printprofile_delete"),
    path("profiles/<int:pk>/changelog/", ObjectChangeLogView.as_view(), name="printprofile_changelog",
         kwargs={"model": PrintProfile}),

    path("options/<str:kind>/", views.OptionsView.as_view(), name="options"),

    path("<str:kind>/", views.PickView.as_view(), name="pick"),
    path("<str:kind>/<int:pk>/", views.PrintView.as_view(), name="print"),
    path("<str:kind>/<int:pk>/pdf/", views.PdfView.as_view(), name="pdf"),
]
