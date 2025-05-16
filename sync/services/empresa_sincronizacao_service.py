import logging
from typing import Dict, List, Optional, Any, Tuple
from sync.models import EmpresaSincronizacao
from .odbc_connection import ODBCConnectionManager  # Para interagir com list_empresas

logger = logging.getLogger(__name__)

class EmpresaSincronizacaoService:
    """
    Serviço para gerenciar o status de sincronização de empresas com a API Fiscaut.
    """

    def __init__(self):
        self.odbc_manager = ODBCConnectionManager()

    def toggle_sincronizacao_empresa(self, codi_emp: int, habilitar: bool) -> Tuple[EmpresaSincronizacao, bool]:
        """
        Habilita ou desabilita a sincronização para uma empresa específica.

        Args:
            codi_emp: Código da empresa no sistema ODBC.
            habilitar: True para habilitar a sincronização, False para desabilitar.

        Returns:
            Uma tupla contendo a instância de EmpresaSincronizacao e um booleano
            indicando se um novo registro foi criado (True) ou um existente foi atualizado (False).
        """
        empresa_sinc, created = EmpresaSincronizacao.objects.update_or_create(
            codi_emp=codi_emp,
            defaults={'habilitada_sincronizacao': habilitar}
        )
        logger.info(
            f"Sincronização para empresa {codi_emp} {'habilitada' if habilitar else 'desabilitada'}. "
            f"Registro {'criado' if created else 'atualizado'}."
        )
        return empresa_sinc, created

    def get_status_sincronizacao_empresas(self, codi_emps: List[int]) -> Dict[int, bool]:
        """
        Retorna o status de sincronização para uma lista de códigos de empresa.

        Args:
            codi_emps: Lista de códigos de empresa (codi_emp).

        Returns:
            Dicionário mapeando codi_emp para seu status de sincronização (True se habilitada, False caso contrário).
        """
        status_map = {emp.codi_emp: emp.habilitada_sincronizacao
                      for emp in EmpresaSincronizacao.objects.filter(codi_emp__in=codi_emps)}

        # Para empresas não encontradas em EmpresaSincronizacao, o padrão é False (não habilitada)
        result_map = {cod_emp: status_map.get(cod_emp, False) for cod_emp in codi_emps}
        return result_map

    def list_empresas_com_status_sincronizacao(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 50,
        filtro_sincronizacao: Optional[str] = None  # 'todas', 'habilitada', 'desabilitada'
    ) -> Dict[str, Any]:
        """
        Lista empresas do ODBC e adiciona o status de sincronização do Fiscaut.
        Permite filtrar por status de sincronização.

        A filtragem por status de sincronização ('habilitada', 'desabilitada') é aplicada
        EM MEMÓRIA após a busca paginada do ODBC. Isso significa que `total_records`
        reflete a contagem ANTES desse filtro em memória, e a página de dados pode
        conter menos itens que `page_size` se muitos forem filtrados.
        Para uma filtragem e paginação precisas no banco, seria necessário modificar
        o `odbc_manager.list_empresas` para aceitar uma lista de `codi_emp` filtrados.

        Args:
            filters: Filtros para a consulta ODBC (ex: nome da empresa).
            page_number: Número da página.
            page_size: Tamanho da página.
            filtro_sincronizacao: 'todas', 'habilitada', ou 'desabilitada'.

        Returns:
            Dicionário similar ao de odbc_manager.list_empresas, mas com um campo
            'habilitada_sincronizacao' para cada empresa e potencialmente filtrado.
        """

        # NOTA: A lógica de filtro_sincronizacao abaixo tem implicações na paginação.
        # Se um filtro de sincronização ('habilitada'/'desabilitada') é aplicado, ele ocorre
        # APÓS a consulta paginada ao ODBC. Isso é uma simplificação.
        # Uma solução mais robusta passaria os codi_emps filtrados para a consulta ODBC.

        empresas_odbc_result = self.odbc_manager.list_empresas(filters, page_number, page_size)

        if not empresas_odbc_result.get("success"):
            return empresas_odbc_result

        empresas_data = empresas_odbc_result.get("data", [])
        codi_emps_encontrados_odbc = [emp.get('codi_emp') for emp in empresas_data if emp.get('codi_emp') is not None]

        if not codi_emps_encontrados_odbc:
            return empresas_odbc_result # Nenhuma empresa do ODBC, retorna como está

        status_sincronizacao = self.get_status_sincronizacao_empresas(codi_emps_encontrados_odbc)

        empresas_enriquecidas_e_filtradas = []
        for emp in empresas_data:
            cod_emp = emp.get('codi_emp')
            if cod_emp is not None:
                emp['habilitada_sincronizacao'] = status_sincronizacao.get(cod_emp, False)

                if filtro_sincronizacao and filtro_sincronizacao != 'todas':
                    sinc_habilitada_desejada = filtro_sincronizacao == 'habilitada'
                    if emp['habilitada_sincronizacao'] == sinc_habilitada_desejada:
                        empresas_enriquecidas_e_filtradas.append(emp)
                else:  # 'todas' ou sem filtro de sincronização específico
                    empresas_enriquecidas_e_filtradas.append(emp)
        
        empresas_odbc_result['data'] = empresas_enriquecidas_e_filtradas
        # A `total_records` e paginação ainda são as do ODBC antes do filtro em memória.
        # A UI pode mostrar menos itens na página do que `page_size` devido ao filtro em memória.
            
        return empresas_odbc_result

# Instância singleton para uso em toda a aplicação (se necessário, ou injetar via Django)
empresa_sinc_service = EmpresaSincronizacaoService() 