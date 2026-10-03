from django.urls import path

from . import views

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("<str:kind>/", views.PickView.as_view(), name="pick"),
    path("<str:kind>/<int:pk>/", views.PrintView.as_view(), name="print"),
    path("<str:kind>/<int:pk>/pdf/", views.PdfView.as_view(), name="pdf"),
]
