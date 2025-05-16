"""
Serviço para gerenciar conexões ODBC no Fiscaut Connector.
"""

import os
import json
import logging
from typing import Dict, List, Tuple, Any, Optional
import pyodbc
from django.conf import settings
from sync.models import ODBCConfiguration

logger = logging.getLogger(__name__)


class ODBCConnectionManager:
    """
    Gerencia conexões ODBC para o sistema Fiscaut Connector.

    Funcionalidades:
    - Salvar e recuperar configurações de conexão
    - Testar conexões
    - Estabelecer conexões com bancos de dados ODBC
    - Executar consultas e comandos SQL
    """

    def __init__(self):
        """Inicializa o gerenciador de conexões ODBC."""
        self.DEFAULT_TIMEOUT = 10  # Timeout padrão para conexões em segundos
        pass

    def save_connection_config(
        self, dsn: str, uid: str, pwd: str, driver: str = ""
    ) -> bool:
        """
        Salva a configuração de conexão ODBC no banco de dados.

        Args:
            dsn: Nome da fonte de dados ODBC
            uid: Nome de usuário para autenticação
            pwd: Senha para autenticação
            driver: Driver ODBC específico (opcional)

        Returns:
            bool: True se a configuração foi salva com sucesso, False caso contrário
        """
        try:
            # Verificar se já existe uma configuração com esses dados
            existing_config = ODBCConfiguration.objects.filter(
                dsn=dsn, uid=uid, driver=driver
            ).first()

            if existing_config:
                # Atualiza a configuração existente
                existing_config.pwd = pwd
                existing_config.is_active = True
                existing_config.save()

                logger.info(f"Configuração ODBC atualizada com sucesso para DSN: {dsn}")
            else:
                # Cria uma nova configuração
                ODBCConfiguration.objects.create(
                    dsn=dsn, uid=uid, pwd=pwd, driver=driver, is_active=True
                )

                logger.info(
                    f"Nova configuração ODBC criada com sucesso para DSN: {dsn}"
                )

            return True

        except Exception as e:
            import traceback
            from django.db import IntegrityError, OperationalError, DataError
            from django.core.exceptions import ValidationError

            error_message = str(e)
            error_traceback = traceback.format_exc()

            logger.error(f"Erro ao salvar configuração ODBC: {error_message}")
            logger.error(f"Traceback completo: {error_traceback}")

            # Verificar tipos específicos de erros
            if isinstance(e, IntegrityError):
                logger.error(f"Erro de integridade do banco de dados: {error_message}")
            elif isinstance(e, OperationalError):
                logger.error(
                    f"Erro operacional do banco de dados - possível problema de conexão: {error_message}"
                )
            elif isinstance(e, ValidationError):
                logger.error(f"Erro de validação do modelo: {error_message}")
            elif isinstance(e, DataError):
                logger.error(
                    f"Erro de dados - possível problema com tamanho de campo: {error_message}"
                )

            # Verificar se o modelo existe - problema comum em migrações
            try:
                from django.apps import apps

                if not apps.get_model("sync", "ODBCConfiguration"):
                    logger.error(
                        "Modelo 'ODBCConfiguration' não está registrado corretamente!"
                    )
            except Exception as model_check_error:
                logger.error(
                    f"Erro ao verificar disponibilidade do modelo: {str(model_check_error)}"
                )

            return False

    def get_connection_config(self) -> Dict[str, str]:
        """
        Recupera a configuração de conexão ODBC ativa do banco de dados.

        Returns:
            Dict contendo as configurações de conexão ou dict vazio se não existir
        """
        try:
            # Verificar se o modelo está disponível antes de prosseguir
            try:
                from django.apps import apps

                if not apps.get_model("sync", "ODBCConfiguration"):
                    logger.error(
                        "Modelo 'ODBCConfiguration' não está registrado ou não existe"
                    )
                    return {}
            except Exception as model_check_error:
                logger.error(
                    f"Erro ao verificar disponibilidade do modelo: {str(model_check_error)}"
                )
                return {}

            config = ODBCConfiguration.get_active_config()

            if config:
                return {
                    "dsn": config.dsn,
                    "uid": config.uid,
                    "pwd": config.pwd,
                    "driver": config.driver,
                }
            else:
                logger.info("Nenhuma configuração ODBC ativa encontrada")
                return {}

        except Exception as e:
            import traceback

            error_traceback = traceback.format_exc()
            logger.error(f"Erro ao recuperar configuração ODBC: {str(e)}")
            logger.error(f"Traceback completo: {error_traceback}")

            # Verificação detalhada do erro
            if "no such table" in str(e).lower():
                logger.error(
                    "Tabela ODBCConfiguration não existe - verifique se as migrações foram aplicadas"
                )
            elif "relation" in str(e).lower() and "does not exist" in str(e).lower():
                logger.error(
                    "Relação da tabela ODBCConfiguration não existe - verifique as migrações"
                )

            return {}

    def build_connection_string(self, config: Dict[str, str] = None) -> str:
        """
        Constrói a string de conexão ODBC a partir da configuração.
        O formato será DRIVER={...};DSN=...;UID=...;PWD=...

        Args:
            config: Configuração de conexão (opcional, se não fornecido, usa a configuração salva)

        Returns:
            String de conexão ODBC

        Raises:
            ValueError: Se DSN estiver ausente ou a configuração não puder ser carregada.
        """
        if config is None:
            config = self.get_connection_config()
            if not config:
                raise ValueError("Não há configuração de conexão ODBC salva ou ativa.")

        dsn = config.get("dsn")
        uid = config.get("uid")
        pwd = config.get("pwd")  # A senha pode ser uma string vazia
        driver = config.get("driver")

        if not dsn:
            raise ValueError(
                "DSN (Nome da Fonte de Dados) é obrigatório na configuração ODBC."
            )

        parts = []
        if driver:
            # Adicionar chaves {} é uma prática comum para nomes de driver que podem conter espaços.
            parts.append(f"DRIVER={{{driver}}}")

        parts.append(f"DSN={dsn}")

        # UID e PWD são opcionais na string de conexão dependendo do DSN/Driver.
        # Se estiverem presentes no config (mesmo que string vazia para PWD), devem ser incluídos.
        if (
            uid is not None
        ):  # uid pode ser uma string vazia ou um valor. Se None, não incluir.
            parts.append(f"UID={uid}")
        if pwd is not None:  # pwd pode ser uma string vazia. Se None, não incluir.
            parts.append(f"PWD={pwd}")

        return ";".join(parts)

    def connect(self, config: Dict[str, str] = None) -> pyodbc.Connection:
        """
        Estabelece uma conexão com o banco de dados ODBC.

        Args:
            config: Configuração de conexão (opcional, usa a configuração salva se não fornecida)

        Returns:
            Objeto de conexão pyodbc

        Raises:
            pyodbc.Error: Se ocorrer erro ao conectar
        """
        conn_string = self.build_connection_string(config)
        return pyodbc.connect(conn_string)

    def test_connection(self, config: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Testa a conexão com o banco de dados ODBC.

        Args:
            config: Configuração de conexão para testar (opcional)

        Returns:
            Dict contendo o resultado do teste, incluindo:
            - success: True/False
            - driver_version: Versão do driver (se sucesso)
            - dbms_version: Versão do DBMS (se sucesso)
            - databases: Lista de bancos de dados disponíveis (se sucesso)
            - error: Mensagem de erro (se falha)
        """
        result = {
            "success": False,
            "driver_version": "",
            "dbms_version": "",
            "databases": [],
            "error": "",
            "connection_string": "",  # String de conexão (parcial, sem senha)
            "error_details": {},  # Detalhes adicionais sobre o erro
        }

        try:
            # Preparar a string de conexão para debug (sem a senha)
            if config is None:
                config = self.get_connection_config()
                if not config:
                    error_msg = "Não há configuração ODBC salva"
                    logger.error(error_msg)
                    result["error"] = error_msg
                    return result

            # Criar versão segura da string de conexão para logging
            safe_conn_parts = []
            if config.get("dsn"):
                safe_conn_parts.append(f"DSN={config['dsn']}")
            if config.get("uid"):
                safe_conn_parts.append(f"UID={config['uid']}")
            if config.get("pwd"):
                safe_conn_parts.append("PWD=******")
            if config.get("driver"):
                safe_conn_parts.append(f"DRIVER={config['driver']}")

            safe_conn_string = ";".join(safe_conn_parts)
            result["connection_string"] = safe_conn_string

            logger.info(f"Testando conexão ODBC com: {safe_conn_string}")

            # Tentar estabelecer conexão
            connection = self.connect(config)

            # Obter informações do driver e DBMS
            cursor = connection.cursor()

            # Versão do driver e DBMS
            try:
                result["driver_version"] = (
                    connection.getinfo(pyodbc.SQL_DRIVER_NAME)
                    + " "
                    + connection.getinfo(pyodbc.SQL_DRIVER_VER)
                )
                result["dbms_version"] = (
                    connection.getinfo(pyodbc.SQL_DBMS_NAME)
                    + " "
                    + connection.getinfo(pyodbc.SQL_DBMS_VER)
                )
            except Exception as info_error:
                logger.warning(
                    f"Erro ao obter informações do driver/DBMS: {str(info_error)}"
                )
                result["driver_version"] = "Não disponível"
                result["dbms_version"] = "Não disponível"

            # Listar bancos de dados disponíveis (funciona principalmente para SQL Server)
            try:
                cursor.execute("SELECT name FROM sys.databases ORDER BY name")
                result["databases"] = [row[0] for row in cursor.fetchall()]
            except Exception as db_list_error:
                # Em caso de erro, tentar outro método ou ignorar
                logger.warning(
                    f"Não foi possível listar bancos de dados: {str(db_list_error)}"
                )

                # Tenta obter pelo menos o nome do banco de dados atual
                try:
                    cursor.execute("SELECT DB_NAME()")
                    db_name = cursor.fetchone()
                    if db_name and db_name[0]:
                        result["databases"] = [db_name[0]]
                except Exception:
                    pass

            cursor.close()
            connection.close()

            result["success"] = True
            logger.info("Teste de conexão ODBC bem-sucedido")

        except ValueError as ve:
            # Erro de valores inválidos (ex: configuração ausente)
            error_msg = str(ve)
            result["error"] = error_msg
            result["error_details"] = {"type": "value_error", "message": error_msg}
            logger.error(f"Erro de valor no teste de conexão ODBC: {error_msg}")

        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            error_message = str(ex)
            logger.error(
                f"Erro de conexão ODBC (test_connection): {sqlstate} - {error_message}"
            )
            # Tentar extrair informações mais detalhadas se disponíveis
            detailed_error = self._extract_detailed_error(error_message)
            return {
                "success": False,
                "error": f"Erro ODBC: {detailed_error['message']}",
                "driver_version": result["driver_version"],
                "dbms_version": result["dbms_version"],
                "databases": result["databases"],
                "connection_string": result["connection_string"],
                "error_details": detailed_error,
            }
        except Exception as e:
            logger.error(f"Erro inesperado em test_connection: {str(e)}")
            return {
                "success": False,
                "error": f"Erro inesperado: {str(e)}",
                "driver_version": "",
                "dbms_version": "",
                "databases": [],
                "connection_string": result["connection_string"],
                "error_details": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "suggestion": "Verifique os logs do servidor.",
                },
            }
        finally:
            if "connection" in locals() and connection:
                connection.close()

        return result

    def execute_query(
        self, query: str, params: tuple = None
    ) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """
        Executa uma consulta SQL e retorna os resultados.

        Args:
            query: Consulta SQL a ser executada
            params: Parâmetros para a consulta (opcional)

        Returns:
            Tupla contendo:
            - bool: True se a consulta foi bem-sucedida, False caso contrário
            - list: Lista de dicionários com os resultados (vazia se falha)
            - str: Mensagem de erro (None se sucesso)
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Verificar se a consulta retorna resultados
            if cursor.description:
                # Converter resultado para lista de dicionários
                columns = [column[0] for column in cursor.description]
                results = []

                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
            else:
                # Consulta sem resultados (ex: INSERT, UPDATE)
                results = []

            connection.commit()
            cursor.close()
            connection.close()

            return True, results, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erro ao executar consulta SQL: {error_msg}")
            return False, [], error_msg

    def execute_command(
        self, command: str, params: tuple = None
    ) -> Tuple[bool, int, Optional[str]]:
        """
        Executa um comando SQL que não retorna resultados (INSERT, UPDATE, DELETE).

        Args:
            command: Comando SQL a ser executado
            params: Parâmetros para o comando (opcional)

        Returns:
            Tupla contendo:
            - bool: True se o comando foi bem-sucedido, False caso contrário
            - int: Número de linhas afetadas (0 se falha)
            - str: Mensagem de erro (None se sucesso)
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()

            if params:
                cursor.execute(command, params)
            else:
                cursor.execute(command)

            # Obter número de linhas afetadas
            row_count = cursor.rowcount

            connection.commit()
            cursor.close()
            connection.close()

            return True, row_count, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erro ao executar comando SQL: {error_msg}")
            return False, 0, error_msg

    def list_empresas(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 50,
        codi_emp_in_list: Optional[List[int]] = None,  # Novo parâmetro
    ) -> Dict[str, Any]:
        """
        Lista empresas da tabela bethadba.geempre com filtros e paginação.

        Args:
            filters (dict, optional): Dicionário com filtros.
                                      Ex: {'razao_emp': 'nome', 'codi_emp': 1, 'cgce_emp': 'cnpj'}
            page_number (int, optional): Número da página solicitada. Default é 1.
            page_size (int, optional): Quantidade de registros por página. Default é 50.
            codi_emp_in_list (List[int], optional): Lista de codi_emp para filtrar com cláusula IN.

        Returns:
            dict: Contendo 'success' (bool), 'data' (list), 'total_records' (int),
                  'current_page' (int), 'page_size' (int), e 'error' (str, se houver falha).
        """
        logger.info(
            f"list_empresas chamado com filters: {filters}, page: {page_number}, size: {page_size}, "
            f"codi_emp_in_list: count={len(codi_emp_in_list) if codi_emp_in_list else 0}"
        )

        config = self.get_connection_config()
        if not config or not config.get("dsn"):
            logger.error(
                "Configuração ODBC não encontrada ou incompleta para list_empresas."
            )
            return {
                "success": False,
                "data": [],
                "total_records": 0,
                "current_page": page_number,
                "page_size": page_size,
                "error": "Configuração ODBC não encontrada. Por favor, configure a conexão primeiro.",
            }

        dsn = config.get("dsn")
        uid = config.get("uid")
        pwd = config.get("pwd")
        driver = config.get("driver", None)

        conn_str = self.build_connection_string(config)

        cnxn = None
        try:
            logger.debug(
                f"Tentando conectar via ODBC para list_empresas com string: {conn_str[:conn_str.find('PWD=') if 'PWD=' in conn_str else len(conn_str)]}..."
            )  # Log sem senha
            cnxn = pyodbc.connect(conn_str, timeout=self.DEFAULT_TIMEOUT)
            logger.info(
                f"Conexão ODBC estabelecida com sucesso para list_empresas (DSN: {dsn})."
            )

            cursor = cnxn.cursor()

            # Query base para buscar os dados das empresas
            base_query_select = (
                "SELECT codi_emp, cgce_emp, razao_emp FROM bethadba.geempre"
            )

            # Query base para contagem total de registros (para paginação)
            base_query_count = "SELECT COUNT(*) FROM bethadba.geempre"

            # Lista para armazenar os parâmetros da query (para filtros)
            params = []

            # String para armazenar as cláusulas WHERE
            where_clauses = []

            if filters:  # Filtros básicos
                if filters.get("codi_emp"):
                    where_clauses.append("codi_emp = ?")
                    params.append(filters["codi_emp"])

                if filters.get("cgce_emp"):
                    where_clauses.append("cgce_emp = ?")
                    params.append(filters["cgce_emp"])

                if filters.get("razao_emp"):
                    where_clauses.append("UPPER(razao_emp) LIKE ?")
                    params.append(f"%{filters['razao_emp'].upper()}%")

            # Adicionar filtro por lista de codi_emp se fornecido
            if codi_emp_in_list:
                if (
                    not codi_emp_in_list
                ):  # Se a lista for vazia, nenhuma empresa corresponderá
                    # Podemos otimizar retornando um resultado vazio aqui para evitar consulta desnecessária
                    # No entanto, a lógica de contagem ainda pode precisar ser executada ou ajustada
                    # Por ora, uma lista vazia de IDs resultará em `codi_emp IN ()` que pode falhar ou não retornar nada.
                    # Melhor tratar como um caso onde a query não retorna nada.
                    # Para SQL Anywhere, uma lista vazia em IN é um erro de sintaxe.
                    # Portanto, se a lista for explicitamente vazia, não adicionamos a cláusula ou retornamos vazio.
                    # Se o serviço que chama garante que não vai passar lista vazia, melhor.
                    # Assumindo que se `codi_emp_in_list` for fornecido, ele não é vazio.
                    # Se ele *puder* ser vazio, o serviço chamador (EmpresaSincronizacaoService) deve
                    # lidar com isso e não chamar list_empresas ou esperar um resultado vazio.
                    # Para segurança, se for uma lista vazia, não adicionamos a cláusula, efetivamente não filtrando por ela aqui.
                    # No entanto, a intenção é que se for passada, é para filtrar. Se vazia, o chamador já deve ter retornado.
                    pass  # O serviço chamador deve garantir que a lista não seja vazia se o filtro for ativo.

                # Criar placeholders para a cláusula IN: (?, ?, ...)
                # E adicionar os codi_emps aos parâmetros
                # Cuidado: SQL Anywhere (e outros) podem ter limites no número de itens em uma cláusula IN.
                # Para um número muito grande, seriam necessárias outras estratégias (tabela temporária, etc.)
                # Para esta implementação, assumimos que a lista não é excessivamente grande.
                if (
                    codi_emp_in_list
                ):  # Re-verificando para ter certeza que não é None e não é vazia implicitamente
                    placeholders = ", ".join(["?" for _ in codi_emp_in_list])
                    where_clauses.append(f"codi_emp IN ({placeholders})")
                    params.extend(codi_emp_in_list)

            # Montar a cláusula WHERE final
            where_sql = ""
            if where_clauses:
                where_sql = " WHERE " + " AND ".join(where_clauses)

            # Anexar cláusulas WHERE às queries base
            final_query_select = base_query_select + where_sql
            final_query_count = base_query_count + where_sql

            # Adicionar ordenação para paginação consistente
            order_by_sql = " ORDER BY codi_emp ASC"
            final_query_select += order_by_sql

            logger.debug(f"Query de contagem: {final_query_count}, Params: {params}")
            logger.debug(
                f"Query de seleção (com ordenação, antes da paginação): {final_query_select}, Params: {params}"
            )

            # Lógica de Paginação para SQL Anywhere
            # SQL Anywhere usa TOP N START AT M, onde M é 1-indexed.
            # page_number é 1-indexed vindo da view.
            start_at = ((page_number - 1) * page_size) + 1

            # Modificar a query de seleção para incluir a paginação
            # Ex: SELECT TOP 50 START AT 1 codi_emp, ... FROM ... ORDER BY ...
            # Precisamos inserir TOP e START AT no lugar certo.
            # A forma mais robusta é reconstruir a select part.
            select_clause = f"SELECT TOP {page_size} START AT {start_at} codi_emp, cgce_emp, razao_emp"
            from_where_order_clauses = final_query_select.split("FROM", 1)[
                1
            ]  # Pega tudo a partir de FROM
            final_query_select_paginated = (
                f"{select_clause} FROM {from_where_order_clauses}"
            )

            logger.debug(
                f"Query de seleção final (paginada): {final_query_select_paginated}, Params: {params}"
            )

            total_records = 0
            empresas_data = []

            # Executar query de contagem
            try:
                cursor.execute(final_query_count, *params)
                count_result = cursor.fetchone()
                if count_result:
                    total_records = count_result[0]
                logger.info(f"Total de registros encontrados: {total_records}")
            except pyodbc.Error as ex:
                sqlstate_count = ex.args[0]
                error_message_count = str(ex)
                logger.error(
                    f"Erro ao executar query de contagem (DSN: {dsn}): {sqlstate_count} - {error_message_count} | Query: {final_query_count} | Params: {params}"
                )
                # Continuar para tentar buscar dados, mas total_records será 0 ou o que foi antes do erro.
                # Ou podemos decidir retornar erro aqui mesmo.
                # Por ora, vamos permitir que a busca de dados prossiga, mas o erro será logado.
                # Se a contagem é crucial para a paginação da UI e falha, talvez seja melhor retornar erro.
                # Para simplificar, vamos assumir que se a contagem falhar, a listagem pode prosseguir com contagem 0 e a UI lida com isso.
                pass  # Erro já logado.

            # Executar query de seleção de dados (somente se total_records > 0 ou se a paginação permitir offset 0)
            # E se a página solicitada faz sentido (start_at <= total_records ou total_records=0 para a primeira página)
            if total_records > 0 and start_at <= total_records:
                try:
                    cursor.execute(
                        final_query_select_paginated, *params
                    )  # Mesmos params da contagem
                    rows = cursor.fetchall()
                    empresas_data = [
                        dict(zip([column[0] for column in cursor.description], row))
                        for row in rows
                    ]
                    logger.info(
                        f"{len(empresas_data)} empresas carregadas para a página {page_number}."
                    )
                except pyodbc.Error as ex:
                    sqlstate_select = ex.args[0]
                    error_message_select = str(ex)
                    logger.error(
                        f"Erro ao executar query de seleção (DSN: {dsn}): {sqlstate_select} - {error_message_select} | Query: {final_query_select_paginated} | Params: {params}"
                    )
                    # Retornar erro aqui é mais crítico, pois não teremos dados.
                    raise  # Repassar a exceção para o bloco catch principal de list_empresas
            elif (
                total_records == 0 and page_number == 1
            ):  # Se não há registros, mas é a primeira página
                logger.info("Nenhum registro encontrado para os filtros aplicados.")
                empresas_data = []  # Garante que seja uma lista vazia
            elif (
                start_at > total_records and total_records > 0
            ):  # Página solicitada está além do total de registros
                logger.info(
                    f"Página {page_number} solicitada está fora do alcance. Total de registros: {total_records}."
                )
                empresas_data = (
                    []
                )  # Garante que seja uma lista vazia, a UI não deve permitir isso idealmente.

            return {
                "success": True,
                "data": empresas_data,
                "total_records": total_records,
                "current_page": page_number,
                "page_size": page_size,
                "error": None,
            }

        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            error_message = str(ex)
            logger.error(
                f"Erro de conexão ODBC em list_empresas (DSN: {dsn}): {sqlstate} - {error_message}"
            )
            detailed_error = self._extract_detailed_error(error_message)
            return {
                "success": False,
                "data": [],
                "total_records": 0,
                "current_page": page_number,
                "page_size": page_size,
                "error": f"Erro ODBC ao conectar: {detailed_error.get('message', 'Erro desconhecido')}",
            }
        except Exception as e:
            logger.error(f"Erro inesperado em list_empresas (DSN: {dsn}): {str(e)}")
            return {
                "success": False,
                "data": [],
                "total_records": 0,
                "current_page": page_number,
                "page_size": page_size,
                "error": f"Erro inesperado no sistema: {str(e)}",
            }
        finally:
            if cnxn:
                logger.debug(f"Fechando conexão ODBC para list_empresas (DSN: {dsn}).")
                cnxn.close()


# Instância singleton para uso em toda a aplicação
odbc_manager = ODBCConnectionManager()
