from django.urls import path
from . import views

urlpatterns = [
    path("config/settings/", views.config_settings_view, name="sync_config_settings"),
    path(
        "api/odbc/save/", views.api_save_odbc_config, name="sync_api_save_odbc_config"
    ),
    path("api/odbc/get/", views.api_get_odbc_config, name="sync_api_get_odbc_config"),
    path(
        "api/odbc/test/",
        views.api_test_odbc_connection,
        name="sync_api_test_odbc_connection",
    ),
    # URLs das páginas principais
    path("dashboard/", views.DashboardView.as_view(), name="sync_dashboard"),
    path("users/", views.UsersView.as_view(), name="sync_users"),
    path("logs/", views.LogsView.as_view(), name="sync_logs"),
    path("empresas/", views.EmpresasListView.as_view(), name="sync_empresas_list"),
    # Adicionar outras URLs do app sync aqui conforme necessário
    path(
        "api/odbc/empresas/toggle-sync/", 
        views.api_toggle_empresa_sincronizacao, 
        name="sync_api_toggle_empresa_sincronizacao"
    ),
]
