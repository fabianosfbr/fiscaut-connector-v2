from django.shortcuts import render

# from django.contrib.auth.models import User # Removida
from django.views.generic import TemplateView
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from sync.services.odbc_connection import odbc_manager
import logging

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
