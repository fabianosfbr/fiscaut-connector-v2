from django.shortcuts import render

# from django.contrib.auth.models import User # Removida
from django.views.generic import TemplateView
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from sync.services.odbc_connection import odbc_manager
from .services.empresa_sincronizacao_service import empresa_sinc_service
import logging
from django.core.paginator import Paginator
from django.contrib import messages

logger = logging.getLogger(__name__)


# Create your views here.


def config_settings_view(request):
    """Renderiza a página de configurações do sistema para o app sync."""
    context = {"active_page": "settings"}
    return render(request, "sync/settings.html", context)


@require_http_methods(["POST"])
def api_save_odbc_config(request):
    """
    API para salvar configurações de conexão ODBC.

    Espera um JSON com:
    - dsn: Nome da fonte de dados
    - uid: Nome do usuário
    - pwd: Senha
    - driver: (opcional) Driver ODBC
    """
    try:
        data = json.loads(request.body)
        dsn = data.get("dsn")
        uid = data.get("uid")
        pwd = data.get("pwd")
        driver = data.get("driver", "")

        logger.info(f"Tentativa de salvar configuração ODBC para DSN: {dsn}")

        if not dsn or not uid or not pwd:
            missing_fields = []
            if not dsn:
                missing_fields.append("DSN")
            if not uid:
                missing_fields.append("UID")
            if not pwd:
                missing_fields.append("PWD")

            error_msg = f"Dados incompletos. Campo(s) obrigatório(s) ausente(s): {', '.join(missing_fields)}"
            logger.warning(error_msg)

            return JsonResponse(
                {
                    "success": False,
                    "message": error_msg,
                    "missing_fields": missing_fields,
                },
                status=400,
            )

        if len(dsn) > 255 or len(uid) > 255 or len(pwd) > 255 or len(driver) > 255:
            error_msg = "Um ou mais valores excedem o tamanho máximo de 255 caracteres"
            logger.warning(error_msg)
            return JsonResponse(
                {
                    "success": False,
                    "message": error_msg,
                    "error_type": "data_validation",
                },
                status=400,
            )

        success = odbc_manager.save_connection_config(dsn, uid, pwd, driver)

        if success:
            logger.info(f"Configuração ODBC salva com sucesso para DSN: {dsn}")
            return JsonResponse(
                {"success": True, "message": "Configuração salva com sucesso!"}
            )
        else:
            logger.error(
                f"Falha ao salvar configuração ODBC: dsn={dsn}, uid={uid}, driver={driver}"
            )

            try:
                from django.apps import apps
                from sync.models import ODBCConfiguration  # Assegurar que está correto

                model_exists = apps.get_model("sync", "ODBCConfiguration") is not None
                model_registered = "sync" in apps.app_configs and hasattr(
                    apps.app_configs["sync"].models, "odbcconfiguration"
                )

                detail = {
                    "model_exists": model_exists,
                    "model_registered": model_registered,
                    "sync_app_installed": "sync" in apps.app_configs,
                }
                logger.info(f"Detalhes da verificação de modelo: {detail}")
            except Exception as check_error:
                logger.error(
                    f"Erro ao verificar detalhes do modelo: {str(check_error)}"
                )
                detail = {"error": str(check_error)}

            return JsonResponse(
                {
                    "success": False,
                    "message": "Erro ao salvar configuração ODBC no banco de dados. Verifique os logs para mais detalhes.",
                    "error_type": "db_save_failed",
                    "detail": detail,
                },
                status=500,
            )

    except json.JSONDecodeError:
        logger.error("JSON inválido recebido na requisição de salvamento ODBC")
        return JsonResponse(
            {
                "success": False,
                "message": "JSON inválido no corpo da requisição.",
                "error_type": "invalid_json",
            },
            status=400,
        )
    except Exception as e:
        import traceback

        error_traceback = traceback.format_exc()
        logger.error(
            f"Erro não tratado ao salvar configuração ODBC: {str(e)}\n{error_traceback}"
        )

        error_info = {
            "type": type(e).__name__,
            "message": str(e),
            "module": getattr(e, "__module__", "unknown"),
            "traceback_summary": (
                error_traceback.splitlines()[-3:] if error_traceback else []
            ),
        }

        return JsonResponse(
            {
                "success": False,
                "message": f"Erro ao salvar configuração ODBC: {str(e)}",
                "error_type": "unhandled_exception",
                "error_detail": error_info,
            },
            status=500,
        )


@require_http_methods(["GET"])
def api_get_odbc_config(request):
    """API para obter as configurações de conexão ODBC salvas."""
    try:
        config = odbc_manager.get_connection_config()

        if "pwd" in config:
            config["pwd"] = "********"

        return JsonResponse({"success": True, "config": config})

    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "message": f"Erro ao recuperar configuração ODBC: {str(e)}",
            },
            status=500,
        )


@require_http_methods(["POST"])
def api_test_odbc_connection(request):
    """
    API para testar uma conexão ODBC.
    Pode usar a configuração salva ou dados temporários enviados na requisição.
    """
    try:
        data = json.loads(request.body)
        use_saved = data.get("use_saved", False)

        if use_saved:
            logger.info("Teste de conexão solicitado usando configuração salva")
            config_data = None
        else:
            dsn = data.get("dsn")
            uid = data.get("uid")
            pwd = data.get("pwd")
            driver = data.get("driver", "")

            logger.info(
                f"Teste de conexão solicitado usando dados temporários: DSN={dsn}"
            )

            if not dsn or not uid or not pwd:
                missing_fields = []
                if not dsn:
                    missing_fields.append("DSN")
                if not uid:
                    missing_fields.append("UID")
                if not pwd:
                    missing_fields.append("PWD")

                error_msg = f"Dados incompletos. Campo(s) obrigatório(s) ausente(s): {', '.join(missing_fields)}"
                logger.warning(error_msg)

                return JsonResponse(
                    {
                        "success": False,
                        "message": error_msg,
                        "missing_fields": missing_fields,
                    },
                    status=400,
                )

            config_data = {"dsn": dsn, "uid": uid, "pwd": pwd, "driver": driver}

        try:
            result = odbc_manager.test_connection(config_data)

            if result["success"]:
                logger.info(
                    f"Teste de conexão bem-sucedido para DSN: {config_data['dsn'] if config_data else 'configuração salva'}"
                )
            else:
                logger.warning(f"Teste de conexão falhou: {result['error']}")

            return JsonResponse({"success": True, "result": result})
        except ValueError as ve:
            logger.error(f"Erro ao testar conexão - valor inválido: {str(ve)}")
            return JsonResponse(
                {"success": False, "message": str(ve), "error_type": "value_error"},
                status=400,
            )

    except json.JSONDecodeError:
        logger.error("JSON inválido recebido na requisição de teste de conexão ODBC")
        return JsonResponse(
            {
                "success": False,
                "message": "JSON inválido no corpo da requisição.",
                "error_type": "invalid_json",
            },
            status=400,
        )
    except Exception as e:
        import traceback

        error_traceback = traceback.format_exc()
        logger.error(
            f"Erro não tratado ao testar conexão ODBC: {str(e)}\n{error_traceback}"
        )

        error_msg_lower = str(e).lower()
        error_type = "unknown"

        if "pyodbc" in error_msg_lower:
            error_type = "pyodbc_error"
            if "driver" in error_msg_lower:
                error_type = "driver_error"
        elif "connection" in error_msg_lower:
            error_type = "connection_error"

        return JsonResponse(
            {
                "success": False,
                "message": f"Erro ao testar conexão ODBC: {str(e)}",
                "error_type": error_type,
                "error_detail": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback_summary": (
                        error_traceback.splitlines()[-3:] if error_traceback else []
                    ),
                },
            },
            status=500,
        )


class DashboardView(TemplateView):
    template_name = "sync/dashboard.html"  # Caminho do template precisa ser verificado

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "dashboard",
                "total_users": 0,  # Valor estático, ou remover completamente
                "total_syncs": 145,  # Dados de exemplo
                "success_rate": 98.5,  # Dados de exemplo
                "connected_systems": 4,  # Dados de exemplo
                "recent_activities": [
                    {
                        "icon": "refresh-cw",
                        "description": "Sincronização concluída com sucesso",
                        "time_ago": "há 2 horas",
                    },
                    {
                        "icon": "user-plus",
                        "description": "Placeholder para atividade futura",  # Ajustado
                        "time_ago": "há 5 horas",
                    },
                    {
                        "icon": "settings",
                        "description": "Configurações do sistema atualizadas",
                        "time_ago": "há 1 dia",
                    },
                ],
            }
        )
        return context


class UsersView(TemplateView):
    template_name = "sync/users.html"  # Caminho do template precisa ser verificado

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "users",
                "users": [],  # Lista vazia, ou remover a página de usuários
            }
        )
        return context


class LogsView(TemplateView):
    template_name = "sync/logs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "logs",
                "logs": [
                    {
                        "level": "info",
                        "message": "Sincronização iniciada",
                        "timestamp": "15/05/2025 16:30:00",
                    },
                    {
                        "level": "success",
                        "message": "Sincronização concluída com sucesso",
                        "timestamp": "15/05/2025 16:42:15",
                    },
                    {
                        "level": "warning",
                        "message": "Conexão com o sistema externo instável",
                        "timestamp": "15/05/2025 15:12:33",
                    },
                    {
                        "level": "error",
                        "message": "Falha na autenticação com o sistema externo",
                        "timestamp": "14/05/2025 10:45:21",
                    },
                ],
            }
        )
        return context


class EmpresasListView(TemplateView):
    template_name = "sync/empresas.html"
    page_size = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_page"] = "empresas"

        page_number = self.request.GET.get("page", 1)
        # Filtros básicos (exemplo: por nome da empresa, etc.)
        # Estes viriam do request.GET, por exemplo:
        search_filters = {}
        nome_empresa_filter = self.request.GET.get("nome_empresa", None)
        if nome_empresa_filter:
            search_filters["razao_emp"] = nome_empresa_filter

        codi_emp_filter = self.request.GET.get("codi_emp", None)
        if codi_emp_filter:
            try:
                search_filters["codi_emp"] = int(codi_emp_filter)
            except ValueError:
                messages.error(self.request, "Código da empresa inválido.")

        cgce_emp_filter = self.request.GET.get("cgce_emp", None)
        if cgce_emp_filter:
            search_filters["cgce_emp"] = cgce_emp_filter

        # Novo filtro para status de sincronização
        filtro_sincronizacao = self.request.GET.get(
            "filtro_sincronizacao", "todas"
        )  # 'todas', 'habilitada', 'desabilitada'
        context["current_filtro_sincronizacao"] = filtro_sincronizacao

        try:
            # Usar o novo serviço para listar empresas com status de sincronização
            empresas_result = (
                empresa_sinc_service.list_empresas_com_status_sincronizacao(
                    filters=search_filters,
                    page_number=int(page_number),
                    page_size=self.page_size,
                    filtro_sincronizacao=filtro_sincronizacao,
                )
            )

            if empresas_result.get("success"):
                empresas_list = empresas_result.get("data", [])
                total_records = empresas_result.get("total_records", 0)

                # A paginação aqui pode ser um pouco enganosa se o filtro de sincronização
                # for 'habilitada' ou 'desabilitada', porque o total_records vem do ODBC
                # antes do filtro em memória. A UI deve estar ciente disso ou
                # a lógica de paginação precisaria de um retrabalho mais complexo.
                paginator = Paginator(
                    range(total_records), self.page_size
                )  # Usar um range para o paginator
                page_obj = paginator.get_page(page_number)

                # Atribuir os dados da página atual (já filtrados em memória pelo serviço se necessário)
                context["empresas_list"] = empresas_list
                context["page_obj"] = page_obj
                context["total_records"] = total_records
                # Adicionar os filtros atuais ao contexto para persistir nos links de paginação/formulário de filtro
                context["current_filters"] = search_filters
                context["current_nome_empresa"] = nome_empresa_filter
                context["current_codi_emp"] = codi_emp_filter
                context["current_cgce_emp"] = cgce_emp_filter

            else:
                messages.error(
                    self.request,
                    f"Erro ao carregar empresas: {empresas_result.get('error', 'Erro desconhecido')}",
                )
                context["empresas_list"] = []
                context["page_obj"] = None
                context["total_records"] = 0
                logger.error(
                    f"Falha ao carregar dados de empresas para a view: {empresas_result.get('error')}"
                )

        except Exception as e:
            messages.error(
                self.request, f"Erro inesperado ao carregar empresas: {str(e)}"
            )
            context["empresas_list"] = []
            context["page_obj"] = None
            context["total_records"] = 0
            logger.exception("Erro inesperado na view EmpresasListView")

        context["page_title"] = "Empresas"
        return context


# Adicionar nova view da API para toggle
@require_http_methods(["POST"])
def api_toggle_empresa_sincronizacao(request):
    """
    API para habilitar ou desabilitar a sincronização de uma empresa.
    Espera um JSON com:
    - codi_emp: int, código da empresa no sistema ODBC
    - habilitar: bool, true para habilitar, false para desabilitar
    """
    try:
        data = json.loads(request.body)
        codi_emp = data.get("codi_emp")
        habilitar = data.get("habilitar")

        if codi_emp is None or not isinstance(codi_emp, int):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Parâmetro 'codi_emp' (inteiro) é obrigatório.",
                },
                status=400,
            )

        if habilitar is None or not isinstance(habilitar, bool):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Parâmetro 'habilitar' (booleano) é obrigatório.",
                },
                status=400,
            )

        logger.info(
            f"API: Trocando status de sincronização para empresa {codi_emp} para {'habilitada' if habilitar else 'desabilitada'}"
        )

        empresa_sinc_obj, created = empresa_sinc_service.toggle_sincronizacao_empresa(
            codi_emp, habilitar
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Sincronização da empresa {codi_emp} {'habilitada' if habilitar else 'desabilitada'} com sucesso.",
                "codi_emp": empresa_sinc_obj.codi_emp,
                "habilitada_sincronizacao": empresa_sinc_obj.habilitada_sincronizacao,
                "created": created,
            }
        )

    except json.JSONDecodeError:
        logger.warning("API: JSON inválido recebido para toggle_empresa_sincronizacao.")
        return JsonResponse(
            {"success": False, "message": "JSON inválido no corpo da requisição."},
            status=400,
        )
    except Exception as e:
        logger.exception(
            f"API: Erro não tratado em api_toggle_empresa_sincronizacao para codi_emp {data.get('codi_emp', 'N/A')}"
        )
        return JsonResponse(
            {"success": False, "message": f"Erro inesperado: {str(e)}"}, status=500
        )
