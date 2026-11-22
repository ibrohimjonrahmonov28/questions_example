from django.urls import path

from exam import access, views

urlpatterns = [
    path("", views.index, name="index"),
    path("pics/<str:name>", views.picture, name="picture"),
    path("api/config", views.config, name="config"),
    path("api/claude", views.claude, name="claude"),
    path("api/transcribe", views.transcribe, name="transcribe"),
    path("access", access.access_view, name="access"),
    path("healthz", views.healthz, name="healthz"),
]
