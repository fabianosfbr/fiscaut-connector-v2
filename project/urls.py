"""
Configuração de URLs para o projeto Fiscaut Connector
"""

# from django.contrib import admin
from django.urls import path, include

# from sync.views import DashboardView, UsersView, SettingsView, LogsView
from django.urls import reverse
from django.http import HttpResponseRedirect

urlpatterns = [
    # path("admin_django/", admin.site.urls),
    # URLs do app project (gerais, se houver)
    # Exemplo: path("project_feature/", include("project.urls_project_specific"))
    # URLs do app sync (painel principal e configurações ODBC)
    path("", include("sync.urls")),
    # Mantendo as URLs de Dashboard, Usuários e Logs no raiz por enquanto
    # A view SettingsView original será removida ou redirecionada se não for mais usada
    # path("dashboard/", DashboardView.as_view(), name="dashboard"),
    # path("users/", UsersView.as_view(), name="users"),
    # path("logs/", LogsView.as_view(), name="logs"),
    # APIs ODBC foram movidas para sync.urls
    # path('admin/api/odbc/save-config/', admin_views.api_save_odbc_config, name='api_save_odbc_config'),
    # path('admin/api/odbc/get-config/', admin_views.api_get_odbc_config, name='api_get_odbc_config'),
    # path('admin/api/odbc/test-connection/', admin_views.api_test_odbc_connection, name='api_test_odbc_connection'),
    # Redirecionar para o dashboard por padrão (ajustar se necessário)
    # path('admin/', lambda request: HttpResponseRedirect(reverse('dashboard'))),
    path("", lambda request: HttpResponseRedirect(reverse("sync_dashboard"))),
]
