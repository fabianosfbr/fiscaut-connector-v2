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

    def toggle_sincronizacao_empresa(
        self, codi_emp: int, habilitar: bool
    ) -> Tuple[EmpresaSincronizacao, bool]:
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
            codi_emp=codi_emp, defaults={"habilitada_sincronizacao": habilitar}
        )
        logger.info(
            f"Sincronização para empresa {codi_emp} {'habilitada' if habilitar else 'desabilitada'}. "
            f"Registro {'criado' if created else 'atualizado'}."
        )
        return empresa_sinc, created

    def get_status_sincronizacao_empresas(
        self, codi_emps: List[int]
    ) -> Dict[int, bool]:
        """
        Retorna o status de sincronização para uma lista de códigos de empresa.

        Args:
            codi_emps: Lista de códigos de empresa (codi_emp).

        Returns:
            Dicionário mapeando codi_emp para seu status de sincronização (True se habilitada, False caso contrário).
        """
        status_map = {
            emp.codi_emp: emp.habilitada_sincronizacao
            for emp in EmpresaSincronizacao.objects.filter(codi_emp__in=codi_emps)
        }

        # Para empresas não encontradas em EmpresaSincronizacao, o padrão é False (não habilitada)
        result_map = {cod_emp: status_map.get(cod_emp, False) for cod_emp in codi_emps}
        return result_map

    def list_empresas_com_status_sincronizacao(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 25,
        filtro_sincronizacao: Optional[
            str
        ] = None,  # 'todas', 'habilitada', 'desabilitada'
    ) -> Dict[str, Any]:
        """
        Lista empresas do ODBC e adiciona o status de sincronização do Fiscaut.
        Permite filtrar por status de sincronização de forma eficiente.
        """

        codi_emps_para_filtrar_odbc: Optional[List[int]] = None
        sinc_status_para_enriquecimento: Optional[bool] = None

        if filtro_sincronizacao and filtro_sincronizacao != "todas":
            sinc_habilitada_desejada = filtro_sincronizacao == "habilitada"
            sinc_status_para_enriquecimento = sinc_habilitada_desejada

            codi_emps_para_filtrar_odbc = list(
                EmpresaSincronizacao.objects.filter(
                    habilitada_sincronizacao=sinc_habilitada_desejada
                ).values_list("codi_emp", flat=True)
            )

            if not codi_emps_para_filtrar_odbc:
                # Nenhuma empresa local corresponde a este status de sincronização,
                # então não há nada a buscar no ODBC que corresponderia.
                return {
                    "success": True,
                    "data": [],
                    "total_records": 0,
                    "current_page": page_number,
                    "page_size": page_size,
                    "error": None,
                }

        # Chamar o ODBC manager, passando a lista de codi_emps se o filtro estiver ativo
        empresas_odbc_result = self.odbc_manager.list_empresas(
            filters=filters,
            page_number=page_number,
            page_size=page_size,
            codi_emp_in_list=codi_emps_para_filtrar_odbc,  # Passa a lista aqui
        )

        if not empresas_odbc_result.get("success"):
            return empresas_odbc_result  # Retorna o erro do ODBC

        empresas_data = empresas_odbc_result.get("data", [])

        if not empresas_data:
            return empresas_odbc_result  # Nenhuma empresa do ODBC, retorna como está

        # Enriquecer com o status de sincronização
        if sinc_status_para_enriquecimento is not None:
            # Se filtramos por status, todas as empresas retornadas devem ter esse status
            for emp in empresas_data:
                emp["habilitada_sincronizacao"] = sinc_status_para_enriquecimento
        else:
            # Se o filtro era 'todas', precisamos buscar o status individualmente
            codi_emps_encontrados_odbc = [
                emp.get("codi_emp")
                for emp in empresas_data
                if emp.get("codi_emp") is not None
            ]
            if codi_emps_encontrados_odbc:
                status_sincronizacao_map = self.get_status_sincronizacao_empresas(
                    codi_emps_encontrados_odbc
                )
                for emp in empresas_data:
                    cod_emp = emp.get("codi_emp")
                    if cod_emp is not None:
                        emp["habilitada_sincronizacao"] = status_sincronizacao_map.get(
                            cod_emp, False
                        )
            else:  # Caso raro: empresas_data não vazia, mas sem codi_emp
                for emp in empresas_data:
                    emp["habilitada_sincronizacao"] = False  # Default

        empresas_odbc_result["data"] = empresas_data
        return empresas_odbc_result

    def get_detalhes_empresa(self, codi_emp: int) -> Optional[Dict[str, Any]]:
        """
        Busca os detalhes de uma empresa específica, combinando dados do ODBC e
        o status de sincronização local.

        Args:
            codi_emp: O código da empresa.

        Returns:
            Um dicionário com os detalhes da empresa (codi_emp, razao_emp, cgce_emp,
            habilitada_sincronizacao) se encontrada, None caso contrário.
        """
        logger.debug(f"Buscando detalhes para a empresa com codi_emp: {codi_emp}")

        # 1. Buscar dados básicos da empresa no ODBC
        empresa_odbc_data = self.odbc_manager.get_empresa_by_codi_emp(codi_emp)

        if not empresa_odbc_data:
            logger.info(
                f"Empresa com codi_emp {codi_emp} não encontrada no ODBC. Retornando None."
            )
            return None

        # 2. Buscar o status de sincronização local
        try:
            empresa_sinc_status = EmpresaSincronizacao.objects.get(codi_emp=codi_emp)
            habilitada_sincronizacao = empresa_sinc_status.habilitada_sincronizacao
            logger.debug(
                f"Status de sincronização encontrado para {codi_emp}: {habilitada_sincronizacao}"
            )
        except EmpresaSincronizacao.DoesNotExist:
            habilitada_sincronizacao = False  # Padrão se não houver registro local
            logger.debug(
                f"Nenhum registro de sincronização local para {codi_emp}. Definindo como False."
            )
        except Exception as e:
            logger.error(f"Erro ao buscar status de sincronização para {codi_emp}: {e}")
            # Em caso de erro ao buscar o status, podemos definir um padrão ou propagar o erro.
            # Por segurança e para não impedir a visualização dos dados do ODBC, definimos como False.
            habilitada_sincronizacao = False

        # 3. Combinar os dados
        detalhes_empresa = {
            "codi_emp": empresa_odbc_data.get("codi_emp"),
            "razao_emp": empresa_odbc_data.get("razao_emp"),
            "cgce_emp": empresa_odbc_data.get("cgce_emp"),
            "habilitada_sincronizacao": habilitada_sincronizacao,
        }

        logger.info(f"Detalhes da empresa {codi_emp} recuperados com sucesso.")
        return detalhes_empresa


# Instância singleton para uso em toda a aplicação (se necessário, ou injetar via Django)
empresa_sinc_service = EmpresaSincronizacaoService()
