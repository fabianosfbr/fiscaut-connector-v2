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
        name="sync_api_toggle_empresa_sincronizacao",
    ),
    path(
        "empresas/<int:codi_emp>/detalhes/",
        views.EmpresaDetailView.as_view(),
        name="sync_empresa_detalhes",
    ),
    # APIs para configuração da Fiscaut API
    path(
        "api/fiscaut/config/",
        views.api_manage_fiscaut_config,
        name="sync_api_manage_fiscaut_config",
    ),
    path(
        "api/fiscaut/test_connection/",
        views.api_test_fiscaut_config,
        name="sync_api_test_fiscaut_config",
    ),
    # Nova URL para sincronizar fornecedor de uma empresa específica
    path(
        "api/empresa/sincronizar-fornecedor/",
        views.api_sincronizar_fornecedor_empresa,
        name="sync_api_sincronizar_fornecedor_empresa",
    ),
    path('api/config/odbc/get/', views.GetOdbcConfigView.as_view(), name='sync_api_get_odbc_config'),
    path('api/empresas/sincronizar-lote/', views.SincronizarFornecedoresLoteView.as_view(), name='sync_api_sincronizar_fornecedores_lote'),
]
