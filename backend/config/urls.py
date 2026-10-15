from django.urls import path

from routing.views import analyze, geocode_place

urlpatterns = [
    path('api/geocode/', geocode_place),
    path('api/routes/analyze/', analyze),
]
