from django.contrib import admin
from django.urls import path
from sync.views import DashboardView, UsersView, SettingsView, LogsView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", DashboardView.as_view(), name="admin_dashboard"),
    path("usuarios/", UsersView.as_view(), name="admin_users"),
    path("configuracoes/", SettingsView.as_view(), name="admin_settings"),
    path("logs/", LogsView.as_view(), name="admin_logs"),
]
