from background_task import background
import logging
from .services.fiscaut_api_service import FiscautApiService
import time

# Se FornecedorStatusSincronizacao ou outros modelos forem diretamente necessários aqui, importe-os.
# Ex: from .models import FornecedorStatusSincronizacao

logger = logging.getLogger(__name__)


@background(schedule=0)  # schedule=0 para executar o mais rápido possível
def processar_sincronizacao_fornecedor_task(
    cnpj_empresa: str,
    nome_fornecedor: str,
    cnpj_fornecedor: str,  # Já virá preenchido, conforme novo requisito
    conta_contabil_fornecedor: str,
    codi_emp_odbc: int,
    codi_for_odbc: str,
):
    """
    Tarefa de background para sincronizar um único fornecedor com a API Fiscaut.
    """
    logger.info(
        f"BG_TASK: Iniciando sincronização para Fornecedor ODBC {codi_for_odbc} "
        f"da Empresa ODBC {codi_emp_odbc} (CNPJ Emp: {cnpj_empresa}, CNPJ Forn: {cnpj_fornecedor})."
    )
    try:
        # Adiciona uma pausa de 1 segundo antes de cada chamada à API
        time.sleep(1)

        api_service = FiscautApiService()
        # A lógica de chamada à API, tratamento de resposta e registro de status
        # (sucesso/erro) já está encapsulada em sincronizar_fornecedor.
        resultado_sinc = api_service.sincronizar_fornecedor(
            cnpj_empresa=cnpj_empresa,
            nome_fornecedor=nome_fornecedor,
            cnpj_fornecedor=cnpj_fornecedor,
            conta_contabil_fornecedor=conta_contabil_fornecedor,
            codi_emp_odbc=codi_emp_odbc,
            codi_for_odbc=codi_for_odbc,
        )

        if resultado_sinc.get("success"):
            logger.info(
                f"BG_TASK: Sincronização bem-sucedida para Forn. ODBC {codi_for_odbc}. "
                f"Msg: {resultado_sinc.get('message')}"
            )
        else:
            logger.warning(
                f"BG_TASK: Falha na sincronização para Forn. ODBC {codi_for_odbc}. "
                f"Msg: {resultado_sinc.get('message')}, Detalhes: {resultado_sinc.get('details')}"
            )

    except Exception as e:
        # O método sincronizar_fornecedor dentro de FiscautApiService já possui
        # um try/except/finally robusto que tentará registrar o status da sincronização
        # mesmo em caso de exceções na comunicação com a API.
        # Este log é para exceções que possam ocorrer na própria task ou ao instanciar o serviço.
        logger.error(
            f"BG_TASK: Erro crítico na tarefa de sincronização para Forn. ODBC {codi_for_odbc} "
            f"da Emp. ODBC {codi_emp_odbc}: {e}",
            exc_info=True,  # Captura o traceback completo
        )
        # Não é necessário um 'raise' aqui, pois a falha já deve ser registrada pelo
        # FiscautApiService. Se o FiscautApiService falhar em registrar,
        # teremos este log da task para diagnóstico.
