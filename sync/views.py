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
from django.views import View
from django.shortcuts import redirect
from .models import (
    FiscautApiConfig,
    FornecedorStatusSincronizacao,
)  # Adicionado FornecedorStatusSincronizacao
import requests  # Adicionar importação para a biblioteca requests
from .services.fiscaut_api_service import (
    FiscautApiService,
)  # Certifique-se que está importado

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

        if config and config.get("dsn"):
            if config.get("pwd") is not None:
                config["pwd"] = "********" if config["pwd"] else ""
            else:
                config["pwd"] = ""
        else:
            config = {"dsn": "", "uid": "", "pwd": "", "driver": ""}

        return JsonResponse({"success": True, "config": config})

    except Exception as e:
        logger.error(f"Erro ao recuperar configuração ODBC para API: {str(e)}")
        return JsonResponse(
            {
                "success": False,
                "message": f"Erro ao recuperar configuração ODBC: {str(e)}",
                "config": {"dsn": "", "uid": "", "pwd": "", "driver": ""},
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

        config_data_for_service = (
            None  # Será None se use_saved=True, ou o dict se use_saved=False
        )

        if use_saved:
            logger.info("Teste de conexão ODBC solicitado usando configuração salva.")
            # config_data_for_service permanece None, o serviço usará a config global salva.
        else:
            dsn = data.get("dsn")
            uid = data.get("uid")
            pwd_from_form = data.get(
                "pwd"
            )  # Pode ser "", "********", ou uma nova senha
            driver = data.get("driver", "")

            logger.info(
                f"Teste de conexão ODBC solicitado usando dados do formulário: DSN={dsn}"
            )

            # DSN e UID são sempre obrigatórios se não estiver usando a configuração salva.
            if not dsn or not uid:
                missing_fields = []
                if not dsn:
                    missing_fields.append("DSN")
                if not uid:
                    missing_fields.append("UID")

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

            # Monta o config_data para o serviço.
            # O serviço decidirá se usa pwd_from_form ou a senha salva se pwd_from_form for vazio/placeholder.
            config_data_for_service = {
                "dsn": dsn,
                "uid": uid,
                "pwd": pwd_from_form,
                "driver": driver,
            }

        # Chama o serviço de teste de conexão
        # O serviço test_connection agora precisa lidar com config_data_for_service podendo ter pwd vazio/placeholder
        result = odbc_manager.test_connection(config_data_for_service)

        if result.get("success", False):
            logger.info(
                f"Teste de conexão ODBC bem-sucedido (use_saved={use_saved}). Detalhes: {result}"
            )
        else:
            logger.warning(
                f"Teste de conexão ODBC falhou (use_saved={use_saved}). Erro: {result.get('error', 'Desconhecido')}"
            )

        # A view sempre retorna success=True se a chamada à API foi bem-sucedida (sem exceções na view).
        # O resultado real do teste está dentro de result['result'] no frontend ou diretamente em 'result' aqui.
        return JsonResponse({"success": True, "result": result})

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
    except ValueError as ve:  # Erro de validação vindo do serviço, por exemplo.
        logger.error(f"Erro de valor ao testar conexão ODBC: {str(ve)}")
        return JsonResponse(
            {"success": False, "message": str(ve), "error_type": "value_error"},
            status=400,
        )
    except Exception as e:
        import traceback

        error_traceback = traceback.format_exc()
        logger.error(
            f"Erro não tratado ao testar conexão ODBC: {str(e)}\n{error_traceback}"
        )
        return JsonResponse(
            {"success": False, "message": f"Erro interno no servidor: {str(e)}"},
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

        # Definição das classes MockPage e MockPaginator no escopo do método
        class MockPage:
            def __init__(
                self,
                number,
                paginator_instance,
                object_list,
                has_next,
                has_previous,
                start_index,
                end_index,
            ):
                self.number = number
                self.paginator = paginator_instance
                self.object_list = object_list
                self.has_next = has_next
                self.has_previous = has_previous
                self.start_index = start_index
                self.end_index = end_index

        class MockPaginator:
            def __init__(self, count, num_pages, page_range):
                self.count = count
                self.num_pages = num_pages
                self.page_range = page_range

        # Filtros da requisição GET
        current_codi_emp = self.request.GET.get("codi_emp", None)
        current_cgce_emp = self.request.GET.get("cgce_emp", None)
        # Corrigido para razao_emp, conforme formulário e modelo de filtro
        current_nome_empresa = self.request.GET.get("razao_emp", None)
        current_filtro_sincronizacao = self.request.GET.get(
            "filtro_sincronizacao", "todas"
        )

        filters_dict = {}
        if current_codi_emp:
            filters_dict["codi_emp"] = current_codi_emp
        if current_cgce_emp:
            filters_dict["cgce_emp"] = current_cgce_emp
        if current_nome_empresa:
            filters_dict["razao_emp"] = current_nome_empresa

        page_number = self.request.GET.get("page", 1)
        try:
            page_number = int(page_number)
        except ValueError:
            page_number = 1

        logger.debug(
            f"EmpresasListView: page={page_number}, filters={filters_dict}, sync_filter={current_filtro_sincronizacao}"
        )

        # Usar o novo EmpresaSincronizacaoService
        # A paginação agora é tratada dentro do serviço que chama o ODBCManager
        resultado_servico = empresa_sinc_service.list_empresas_com_status_sincronizacao(
            filters=filters_dict,
            page_number=page_number,
            page_size=self.page_size,
            filtro_sincronizacao=current_filtro_sincronizacao,
        )

        empresas_list = []  # Inicializa com lista vazia
        page_obj = None  # Inicializa como None
        error_message = None

        if resultado_servico.get("success", False):
            empresas_raw = resultado_servico.get("data", [])
            total_records = resultado_servico.get("total_records", 0)

            # O serviço agora retorna dados já paginados e com o total correto
            # A Paginator do Django pode ser usada aqui apenas para a interface, se desejado,
            # mas a paginação real da query já ocorreu.
            # Para manter a compatibilidade com o template que espera um page_obj do Django Paginator:
            if total_records > 0 and empresas_raw:
                paginator = Paginator(
                    empresas_raw, self.page_size
                )  # Paginando a lista já retornada
                # Nota: idealmente, o paginator deveria ser usado com uma queryset ou lista completa
                # e ele faria o slice. Aqui, como o serviço já paginou, estamos "re-paginando" um subconjunto.
                # Isso é ok se o `empresas_raw` já é a página correta de dados.
                # Se o serviço retornasse todos os dados e o total, Paginator faria mais sentido.
                # Mas como o serviço já faz a paginação na query ODBC, vamos usar os dados diretos.

                # Ajuste: usar os dados e totais do serviço diretamente para construir algo semelhante ao page_obj
                # ou passar os dados diretos.
                # Por simplicidade, vamos simular um page_obj limitado ou passar os dados.

                # Simplificação: O template espera page_obj com certos atributos.
                # O serviço retorna a lista de empresas para a página atual e os totais.
                empresas_list = empresas_raw

                # Criar um objeto Page simulado ou adaptar o template para usar os dados diretos do serviço
                # Para manter o template como está, podemos construir um Paginator com a lista da página atual
                # e depois pegar a primeira página dele (que será a única página com esses dados)
                # Isso não é eficiente mas mantém a estrutura do template.
                # Uma melhor abordagem seria adaptar o template para `total_records`, `current_page`, `total_pages` do serviço.

                # Tentativa de simular page_obj para compatibilidade:
                # Criar um Paginator com uma lista de objetos que serão "falsos" para além da página atual,
                # mas que permite que o Paginator calcule `num_pages` e `count` corretamente.
                # Isso é complexo. Vamos simplificar e assumir que o template pode ser adaptado ou
                # que o serviço retorna o suficiente para popular os atributos do page_obj que o template usa.

                total_pages_from_service = resultado_servico.get("total_pages", 1)
                current_page_from_service = resultado_servico.get("current_page", 1)

                mock_paginator_instance = MockPaginator(
                    count=total_records,
                    num_pages=total_pages_from_service,
                    page_range=range(1, total_pages_from_service + 1),  # Simples range
                )

                page_obj = MockPage(
                    number=current_page_from_service,
                    paginator_instance=mock_paginator_instance,
                    object_list=empresas_list,
                    has_next=(current_page_from_service < total_pages_from_service),
                    has_previous=(current_page_from_service > 1),
                    start_index=(
                        ((current_page_from_service - 1) * self.page_size) + 1
                        if empresas_list
                        else 0
                    ),
                    end_index=(
                        ((current_page_from_service - 1) * self.page_size)
                        + len(empresas_list)
                        if empresas_list
                        else 0
                    ),
                )

            else:  # total_records == 0 ou empresas_raw vazia
                empresas_list = []
                # page_obj permanece None, ou podemos criar um MockPage vazio
                mock_paginator_instance = MockPaginator(
                    count=0, num_pages=1, page_range=range(1, 2)
                )
                page_obj = MockPage(
                    number=1,
                    paginator_instance=mock_paginator_instance,
                    object_list=[],
                    has_next=False,
                    has_previous=False,
                    start_index=0,
                    end_index=0,
                )

        else:
            error_message = resultado_servico.get("error", "Erro ao carregar empresas.")
            logger.error(f"Erro do serviço ao listar empresas: {error_message}")
            messages.error(self.request, error_message)
            # Cria um page_obj vazio para evitar erros no template
            mock_paginator_instance = MockPaginator(
                count=0, num_pages=1, page_range=range(1, 2)
            )
            page_obj = MockPage(
                number=1,
                paginator_instance=mock_paginator_instance,
                object_list=[],
                has_next=False,
                has_previous=False,
                start_index=0,
                end_index=0,
            )

        context["empresas_list"] = empresas_list
        context["page_obj"] = page_obj
        context["total_records"] = total_records if "total_records" in locals() else 0
        context["error_message"] = error_message

        # Manter os filtros no contexto para preencher o formulário
        context["current_codi_emp"] = current_codi_emp
        context["current_cgce_emp"] = current_cgce_emp
        context["current_nome_empresa"] = current_nome_empresa
        context["current_filtro_sincronizacao"] = current_filtro_sincronizacao

        return context


class EmpresaDetailView(View):
    template_name = "sync/empresa_detalhes.html"

    def get(self, request, codi_emp, *args, **kwargs):
        logger.info(f"Acessando detalhes da empresa com codi_emp: {codi_emp}")

        # Definição das classes MockPage e MockPaginator no escopo do método
        # TODO: Considerar mover para um local mais global se usadas em múltiplas views
        class MockPage:
            def __init__(
                self,
                number,
                paginator_instance,
                object_list,
                has_next,
                has_previous,
                start_index,
                end_index,
            ):
                self.number = number
                self.paginator = paginator_instance
                self.object_list = object_list
                self.has_next = has_next
                self.has_previous = has_previous
                self.start_index = start_index
                self.end_index = end_index

        class MockPaginator:
            def __init__(self, count, num_pages, page_range):
                self.count = count
                self.num_pages = num_pages
                self.page_range = page_range

        empresa_detalhes = empresa_sinc_service.get_detalhes_empresa(codi_emp)

        if not empresa_detalhes:
            logger.warning(f"Empresa com codi_emp {codi_emp} não encontrada.")
            messages.error(request, "Empresa não encontrada.")
            return redirect("sync_empresas_list")

        context = {
            "active_page": "empresas",  # Manter o menu lateral ativo em "empresas"
            "empresa": empresa_detalhes,
        }

        # --- Início da Lógica para Fornecedores ---
        fornecedor_page_size = 50
        current_f_codi_for = request.GET.get("f_codi_for", None)
        current_f_nome_for = request.GET.get("f_nome_for", None)
        current_f_cgce_for = request.GET.get("f_cgce_for", None)
        current_f_status_sinc = request.GET.get(
            "f_status_sinc", "todos"
        )  # Ler o novo filtro
        f_page_number = request.GET.get("f_page", 1)
        try:
            f_page_number = int(f_page_number)
            if f_page_number < 1:
                f_page_number = 1
        except ValueError:
            f_page_number = 1

        fornecedor_filters = {}
        if current_f_codi_for:
            fornecedor_filters["f_codi_for"] = current_f_codi_for
        if current_f_nome_for:
            fornecedor_filters["f_nome_for"] = current_f_nome_for
        if current_f_cgce_for:
            fornecedor_filters["f_cgce_for"] = current_f_cgce_for
        # Não passamos f_status_sinc para odbc_manager.list_fornecedores_empresa
        # pois o filtro de status será aplicado após o enriquecimento.

        logger.debug(
            f"Buscando fornecedores para empresa {codi_emp} com filtros ODBC: {fornecedor_filters}, página: {f_page_number}, filtro status sinc: {current_f_status_sinc}"
        )

        fornecedores_result = odbc_manager.list_fornecedores_empresa(
            codi_emp=codi_emp,
            filters=fornecedor_filters,  # Filtros que vão para o ODBC
            page_number=f_page_number,
            page_size=fornecedor_page_size,
        )

        fornecedores_list_com_status = []  # Inicializa a lista final
        fornecedores_total_records_odbc = (
            0  # Total de registros retornados pelo ODBC para a página atual
        )
        fornecedores_total_pages_odbc = (
            0  # Total de páginas baseado na consulta ODBC original
        )

        if fornecedores_result.get("error"):
            messages.error(
                request, f"Erro ao buscar fornecedores: {fornecedores_result['error']}"
            )
        else:
            fornecedores_raw_odbc = fornecedores_result.get("data", [])
            # Esses são os totais da consulta ODBC original, ANTES do filtro de status local
            fornecedores_total_records_odbc = fornecedores_result.get(
                "total_records", 0
            )
            fornecedores_total_pages_odbc = fornecedores_result.get("total_pages", 0)

            if fornecedores_raw_odbc:
                codi_emp_int = int(codi_emp)
                codi_for_odbc_list = [
                    str(f["codi_for"])
                    for f in fornecedores_raw_odbc
                    if f.get("codi_for") is not None
                ]
                # logger.info(f"DEBUG_VIEW_DETAIL: Empresa {codi_emp_int} - Lista de codi_for_odbc (strings) para busca de status: {codi_for_odbc_list}")

                status_sinc_map = {}
                if codi_for_odbc_list:
                    status_objs = FornecedorStatusSincronizacao.objects.filter(
                        codi_emp_odbc=codi_emp_int, codi_for_odbc__in=codi_for_odbc_list
                    )
                    # logger.info(f"DEBUG_VIEW_DETAIL: Objetos de status encontrados no DB ({status_objs.count()}): {list(status_objs.values('codi_emp_odbc', 'codi_for_odbc', 'status_sincronizacao'))}")
                    for status_obj in status_objs:
                        status_sinc_map[str(status_obj.codi_for_odbc)] = {
                            "status": status_obj.get_status_sincronizacao_display(),
                            "status_raw": status_obj.status_sincronizacao,
                            "ultima_tentativa": status_obj.ultima_tentativa_sinc,
                        }
                # logger.info(f"DEBUG_VIEW_DETAIL: Mapa de status construído (status_sinc_map): {status_sinc_map}")

                temp_list_enriquecida = []
                for forn in fornecedores_raw_odbc:
                    codi_for_do_odbc = forn.get("codi_for")
                    chave_mapa_lookup = (
                        str(codi_for_do_odbc) if codi_for_do_odbc is not None else None
                    )

                    # logger.info(f"DEBUG_VIEW_DETAIL: Processando fornecedor do ODBC: original codi_for={codi_for_do_odbc} (tipo: {type(codi_for_do_odbc)}). Usando chave para mapa: '{chave_mapa_lookup}' (tipo: {type(chave_mapa_lookup)})")

                    status_info = status_sinc_map.get(chave_mapa_lookup)

                    if status_info:
                        # logger.info(f"DEBUG_VIEW_DETAIL: Status ENCONTRADO para chave '{chave_mapa_lookup}': {status_info['status_raw']}")
                        forn["status_sincronizacao"] = status_info["status"]
                        forn["status_sincronizacao_raw"] = status_info["status_raw"]
                        forn["ultima_tentativa_sinc"] = status_info["ultima_tentativa"]
                    else:
                        # logger.info(f"DEBUG_VIEW_DETAIL: Status NÃO ENCONTRADO para chave '{chave_mapa_lookup}'. Definindo como Não Sincronizado.")
                        forn["status_sincronizacao"] = (
                            FornecedorStatusSincronizacao.STATUS_CHOICES[0][1]
                        )
                        forn["status_sincronizacao_raw"] = (
                            FornecedorStatusSincronizacao.STATUS_CHOICES[0][0]
                        )
                        forn["ultima_tentativa_sinc"] = None
                    temp_list_enriquecida.append(forn)

                # Aplicar filtro de status de sincronização SE não for "todos"
                if current_f_status_sinc != "todos":
                    fornecedores_list_com_status = [
                        f
                        for f in temp_list_enriquecida
                        if f.get("status_sincronizacao_raw") == current_f_status_sinc
                    ]
                else:
                    fornecedores_list_com_status = temp_list_enriquecida

        # A paginacao no template ainda será baseada nos totais do ODBC.
        # O número de itens exibidos na PÁGINA ATUAL pode ser menor se o filtro de status for aplicado.
        # Isso é uma simplificação. Para uma paginação "correta" APÓS o filtro de status,
        # precisaríamos buscar TODOS os fornecedores do ODBC, enriquecer TODOS, filtrar TODOS, e DEPOIS paginar a lista filtrada.

        fornecedores_paginator = MockPaginator(
            count=fornecedores_total_records_odbc,  # Paginador reflete o total antes do filtro de status local
            num_pages=fornecedores_total_pages_odbc,
            page_range=range(
                1,
                (
                    fornecedores_total_pages_odbc + 1
                    if fornecedores_total_pages_odbc > 0
                    else 2
                ),
            ),
        )
        fornecedores_page_obj = MockPage(
            number=f_page_number,
            paginator_instance=fornecedores_paginator,
            object_list=fornecedores_list_com_status,  # Lista efetivamente exibida (pode ser menor que page_size)
            has_next=(f_page_number < fornecedores_total_pages_odbc),
            has_previous=(f_page_number > 1),
            start_index=(
                ((f_page_number - 1) * fornecedor_page_size + 1)
                if fornecedores_list_com_status  # Baseado no que é exibido
                else 0
            ),
            end_index=(
                (
                    (f_page_number - 1) * fornecedor_page_size
                    + len(fornecedores_list_com_status)
                )
                if fornecedores_list_com_status  # Baseado no que é exibido
                else 0
            ),
        )

        context["fornecedores_list"] = fornecedores_list_com_status
        context["fornecedores_page_obj"] = fornecedores_page_obj
        context["current_f_codi_for"] = current_f_codi_for
        context["current_f_nome_for"] = current_f_nome_for
        context["current_f_cgce_for"] = current_f_cgce_for
        context["current_f_status_sinc"] = (
            current_f_status_sinc  # Adicionar ao contexto
        )
        # --- Fim da Lógica para Fornecedores ---

        return render(request, self.template_name, context)


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


@require_http_methods(["GET", "POST"])
def api_manage_fiscaut_config(request):
    """Gerencia a configuração da API Fiscaut."""
    if request.method == "GET":
        config = FiscautApiConfig.get_active_config()
        if config:
            return JsonResponse(
                {
                    "success": True,
                    "api_url": config.api_url,
                    "api_key": config.api_key,  # Lembre-se de que a chave está em texto plano
                }
            )
        else:
            return JsonResponse(
                {"success": True, "api_url": "", "api_key": ""}, status=200
            )  # Ou 404 se preferir que não encontrado seja um erro

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            api_url = data.get("apiUrl")
            api_key = data.get("apiKey")

            if not api_url or not api_key:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "URL da API e Chave da API são obrigatórias.",
                    },
                    status=400,
                )

            # Validação simples de URL (pode ser mais robusta)
            if not api_url.startswith("http://") and not api_url.startswith("https://"):
                return JsonResponse(
                    {"success": False, "message": "URL da API inválida."}, status=400
                )

            config, created = FiscautApiConfig.objects.update_or_create(
                # Como queremos uma única config, podemos usar um ID fixo se soubermos que é sempre 1,
                # ou buscar o primeiro objeto e atualizar seus campos, ou criar se não existir.
                # Para update_or_create, precisamos de um campo para buscar. Se não há um, ele sempre cria.
                # Vamos usar a estratégia de pegar o primeiro ou criar.
                defaults={"api_url": api_url, "api_key": api_key}
            )
            # A lógica acima em update_or_create pode não funcionar como esperado sem um lookup field.
            # Simplificando: pegar o primeiro, atualizar. Se não existir, criar.
            existing_config = FiscautApiConfig.objects.first()
            if existing_config:
                existing_config.api_url = api_url
                existing_config.api_key = api_key
                existing_config.save()
                logger.info(f"Configuração da API Fiscaut atualizada: URL={api_url}")
            else:
                FiscautApiConfig.objects.create(api_url=api_url, api_key=api_key)
                logger.info(f"Configuração da API Fiscaut criada: URL={api_url}")

            return JsonResponse(
                {
                    "success": True,
                    "message": "Configuração da API Fiscaut salva com sucesso!",
                    "api_url": api_url,
                }
            )
        except json.JSONDecodeError:
            logger.warning("JSON inválido recebido para salvar config Fiscaut")
            return JsonResponse(
                {"success": False, "message": "JSON inválido."}, status=400
            )
        except Exception as e:
            logger.error(
                f"Erro ao salvar configuração da API Fiscaut: {str(e)}", exc_info=True
            )
            return JsonResponse(
                {"success": False, "message": f"Erro interno do servidor: {str(e)}"},
                status=500,
            )


@require_http_methods(["POST"])
def api_test_fiscaut_config(request):
    """Testa a conexão com a API Fiscaut fazendo uma chamada real."""
    try:
        data = json.loads(request.body)
        api_url = data.get("apiUrl")
        api_key = data.get("apiKey")

        if not api_url or not api_key:
            return JsonResponse(
                {
                    "success": False,
                    "message": "URL da API e Chave da API são obrigatórias para o teste.",
                },
                status=400,
            )

        logger.info(
            f"Testando conexão real com a API Fiscaut: URL={api_url}, Endpoint: /up"
        )

        test_endpoint_url = api_url.rstrip("/") + "/up"  # Alterado para /up

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",  # Adicionado
            "Accept": "application/json",  # Adicionado
        }

        timeout_seconds = 15  # Aumentado ligeiramente, conforme FiscautApiService

        try:
            response = requests.get(
                test_endpoint_url, headers=headers, timeout=timeout_seconds
            )

            if response.status_code == 200:
                try:
                    response_data = response.json()
                    # Verifica se a API retornou sucesso e um status True específico da Fiscaut API
                    if response_data.get("status") is True:
                        logger.info(
                            f"Teste de conexão com API Fiscaut bem-sucedido. Resposta: {response_data}"
                        )
                        return JsonResponse(
                            {
                                "success": True,
                                "message": "Conexão com a API Fiscaut bem-sucedida!",
                            }
                        )
                    else:
                        logger.warning(
                            f"API Fiscaut respondeu, mas indicou um problema. Status: {response.status_code}, Resposta: {response_data}"
                        )
                        return JsonResponse(
                            {
                                "success": False,
                                "message": "API Fiscaut respondeu, mas indicou um problema.",
                                "details": response_data,
                            },
                            status=200,
                        )
                except ValueError:  # Se a resposta não for JSON
                    logger.warning(
                        f"Resposta da API Fiscaut não é JSON válido. Status: {response.status_code}, Resposta: {response.text[:200]}"
                    )
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Resposta da API Fiscaut não é um JSON válido.",
                            "details": response.text,
                        },
                        status=200,
                    )
            else:  # Outros códigos de status (401, 403, 404, 500, etc.)
                error_message = f"Falha no teste de conexão com a API Fiscaut. Status: {response.status_code}"
                details = response.text  # Detalhes como texto cru
                try:
                    # Tenta obter mais detalhes do corpo da resposta, se for JSON (algumas APIs retornam JSON para erros)
                    error_details_json = response.json()
                    error_message += (
                        f" - Detalhes JSON: {json.dumps(error_details_json)}"
                    )
                    details = (
                        error_details_json  # Usa o JSON como detalhe se disponível
                    )
                except ValueError:
                    error_message += f" - Resposta (texto): {response.text[:200]}..."

                logger.warning(error_message)
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"Falha na conexão com a API Fiscaut (HTTP {response.status_code}).",
                        "details": details,
                    },
                    status=200,
                )

        except requests.exceptions.Timeout:
            logger.error(
                f"Timeout ao tentar conectar à API Fiscaut: {test_endpoint_url}"
            )
            return JsonResponse(
                {
                    "success": False,
                    "message": "Tempo limite excedido ao tentar conectar à API Fiscaut.",
                },
                status=200,
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Erro de conexão ao tentar acessar API Fiscaut ({test_endpoint_url}): {str(e)}"
            )
            return JsonResponse(
                {
                    "success": False,
                    "message": "Erro de conexão: Não foi possível conectar à URL da API Fiscaut fornecida.",
                    "details": str(e),
                },
                status=200,
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Erro de requisição geral ao testar API Fiscaut ({test_endpoint_url}): {str(e)}"
            )
            return JsonResponse(
                {
                    "success": False,
                    "message": "Erro na requisição à API Fiscaut.",
                    "details": str(e),
                },
                status=200,
            )

    except json.JSONDecodeError:
        logger.warning(
            "JSON inválido recebido no corpo da requisição para testar config Fiscaut"
        )
        return JsonResponse(
            {"success": False, "message": "JSON inválido no corpo da requisição."},
            status=400,
        )
    except Exception as e:
        logger.error(
            f"Erro não tratado ao testar conexão com API Fiscaut: {str(e)}",
            exc_info=True,
        )
        return JsonResponse(
            {"success": False, "message": f"Erro interno do servidor: {str(e)}"},
            status=500,
        )


@require_http_methods(["POST"])
def api_sincronizar_fornecedor_empresa(request):
    """
    Endpoint da API para acionar a sincronização de um fornecedor específico
    de uma empresa com a API Fiscaut.
    """
    try:
        data = json.loads(request.body)
        cnpj_empresa = data.get("cnpj_empresa")
        codi_emp_odbc = data.get("codi_emp")  # Capturar codi_emp vindo do JS
        codi_for_odbc = data.get("codi_for")  # Capturar codi_for vindo do JS
        nome_fornecedor = data.get("nome_fornecedor")
        cnpj_fornecedor = data.get("cnpj_fornecedor")
        conta_contabil_fornecedor = data.get("conta_contabil_fornecedor")

        # Validação básica dos dados recebidos
        required_fields = {
            "cnpj_empresa": cnpj_empresa,
            "codi_emp_odbc": codi_emp_odbc,  # Adicionado à validação
            "codi_for_odbc": codi_for_odbc,  # Adicionado à validação
            "nome_fornecedor": nome_fornecedor,
            "cnpj_fornecedor": cnpj_fornecedor,
        }
        missing_fields = [key for key, value in required_fields.items() if not value]
        if missing_fields:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Campos obrigatórios ausentes: {', '.join(missing_fields)}",
                },
                status=400,
            )

        # Converter codi_emp_odbc para int, se necessário e apropriado
        try:
            codi_emp_odbc = int(codi_emp_odbc)
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "codi_emp deve ser um inteiro válido."},
                status=400,
            )

        # codi_for_odbc já é string, o que é esperado pelo serviço e modelo

        conta_contabil_fornecedor = (
            conta_contabil_fornecedor if conta_contabil_fornecedor else ""
        )

        logger.info(
            f"API: Req para sinc fornecedor. CNPJ Emp: {cnpj_empresa}, CodiEmp: {codi_emp_odbc}, CodiFor: {codi_for_odbc}, "
            f"Nome Forn: {nome_fornecedor}, CNPJ Forn: {cnpj_fornecedor}, Conta: {conta_contabil_fornecedor}"
        )

        fiscaut_service = FiscautApiService()
        resultado_sinc = fiscaut_service.sincronizar_fornecedor(
            cnpj_empresa=cnpj_empresa,
            nome_fornecedor=nome_fornecedor,
            cnpj_fornecedor=cnpj_fornecedor,
            conta_contabil_fornecedor=conta_contabil_fornecedor,
            codi_emp_odbc=codi_emp_odbc,  # Passando para o serviço
            codi_for_odbc=codi_for_odbc,  # Passando para o serviço
        )

        # A função sincronizar_fornecedor já retorna um dict com 'success', 'message', etc.
        if resultado_sinc.get("success"):
            logger.info(
                f"Sincronização do fornecedor {cnpj_fornecedor} para empresa {cnpj_empresa} bem-sucedida (via API Fiscaut)."
            )
            return JsonResponse(resultado_sinc, status=200)
        else:
            logger.warning(
                f"Falha na sincronização do fornecedor {cnpj_fornecedor} para empresa {cnpj_empresa} (via API Fiscaut). "
                f"Mensagem: {resultado_sinc.get('message')}, Detalhes: {resultado_sinc.get('details')}"
            )
            # Retorna o status code que veio da chamada ao serviço, se houver, ou 200 (com success:false)
            # ou 500 se for um erro interno do serviço não relacionado à chamada HTTP em si.
            status_code = resultado_sinc.get(
                "status_code", 200
            )  # Default to 200 if not specified by service error
            if (
                not isinstance(status_code, int)
                or status_code < 100
                or status_code > 599
            ):
                status_code = (
                    500
                    if resultado_sinc.get("message", "").startswith("Erro interno")
                    else 200
                )

            return JsonResponse(resultado_sinc, status=status_code)

    except json.JSONDecodeError:
        logger.warning("API sincronizar_fornecedor: JSON inválido recebido.")
        return JsonResponse(
            {"success": False, "message": "JSON inválido no corpo da requisição."},
            status=400,
        )
    except Exception as e:
        logger.error(
            f"API sincronizar_fornecedor: Erro não tratado: {str(e)}", exc_info=True
        )
        return JsonResponse(
            {"success": False, "message": f"Erro interno no servidor: {str(e)}"},
            status=500,
        )
