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
            # Tenta buscar uma configuração ativa existente para atualizar,
            # ou a mais recente se nenhuma estiver ativa (para evitar duplicatas por DSN/UID/Driver).
            existing_config = (
                ODBCConfiguration.objects.filter(dsn=dsn, uid=uid, driver=driver)
                .order_by("-is_active", "-updated_at")
                .first()
            )

            if existing_config:
                # Atualiza a configuração existente
                # Só atualiza a senha se a nova senha não for o placeholder "********"
                if pwd != "********":
                    existing_config.pwd = pwd
                # Se pwd for "********", a senha existente (existing_config.pwd) é mantida.

                existing_config.is_active = True  # Garante que a configuração sendo salva/atualizada se torne ativa
                existing_config.save()

                logger.info(f"Configuração ODBC atualizada com sucesso para DSN: {dsn}")
            else:
                # Cria uma nova configuração
                # Se uma nova configuração está sendo criada, a senha não deve ser "********".
                # A view deve idealmente impedir isso, mas como uma salvaguarda,
                # poderíamos adicionar uma verificação aqui ou confiar na validação do frontend/view.
                # Por ora, vamos assumir que pwd não será "********" para uma nova configuração.
                if pwd == "********":
                    logger.warning(
                        f"Tentativa de criar nova configuração ODBC para DSN: {dsn} com senha placeholder. Isso não é recomendado."
                    )
                    # Decide-se não criar ou criar com senha vazia? Por ora, vamos permitir, mas logar.
                    # Para maior segurança, poderia retornar False ou levantar um erro.
                    # No entanto, para manter a consistência com o comportamento anterior de 'salvar o que vier',
                    # vamos permitir, mas a view deve ser o ponto de bloqueio primário para isso.

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

    def test_connection(
        self, config_data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Testa a conexão com o banco de dados ODBC.

        Args:
            config_data: Dados da configuração de conexão para testar (opcional).
                         Se None, usa a configuração salva.
                         Se fornecido, pode conter 'pwd' como '********'.

        Returns:
            Dict contendo o resultado do teste, incluindo:
            - success: True/False
            - driver_version: Versão do driver (se sucesso)
            - dbms_version: Versão do DBMS (se sucesso)
            - databases: Lista de bancos de dados disponíveis (se sucesso)
            - error: Mensagem de erro (se falha)
            - error_type: Tipo de erro (ex: 'connection_error', 'config_error')
            - suggestion: Sugestão para o usuário (se aplicável)
        """
        result = {
            "success": False,
            "driver_version": "",
            "dbms_version": "",
            "databases": [],
            "error": "",
            "error_type": "unknown_error",
            "suggestion": "",
        }
        conn: Optional[pyodbc.Connection] = None
        actual_config_to_use: Dict[str, str] = {}

        try:
            if config_data:
                logger.debug(
                    f"Testando conexão ODBC com dados fornecidos: {config_data.get('dsn')}"
                )
                # Trabalha com uma cópia para não modificar o original que pode ser usado em logs
                temp_config = config_data.copy()

                dsn_from_data = temp_config.get("dsn")
                uid_from_data = temp_config.get("uid")
                pwd_from_data = temp_config.get("pwd")

                if not dsn_from_data or not uid_from_data:
                    # Se pwd_from_data for None, pode ser que o usuário apagou o campo e não é "********"
                    # mas DSN e UID são essenciais se config_data é fornecido (não é use_saved)
                    error_msg = "DSN e UID são obrigatórios para testar uma configuração não salva."
                    logger.warning(error_msg)
                    result["error"] = error_msg
                    result["error_type"] = "config_error"
                    result["suggestion"] = (
                        "Certifique-se de que DSN e UID estão preenchidos."
                    )
                    return result

                if pwd_from_data == "********":
                    logger.info(
                        "Senha placeholder '********' detectada nos dados do formulário. Tentando usar senha salva."
                    )
                    saved_config_dict = self.get_connection_config()
                    if (
                        saved_config_dict
                        and saved_config_dict.get("dsn") == dsn_from_data
                        and saved_config_dict.get("uid") == uid_from_data
                    ):
                        logger.info(
                            "Configuração salva correspondente encontrada. Usando senha salva."
                        )
                        temp_config["pwd"] = saved_config_dict[
                            "pwd"
                        ]  # Usa a senha real
                    else:
                        logger.warning(
                            "Nenhuma configuração salva correspondente encontrada para DSN/UID ou nenhuma configuração salva. O teste com '********' provavelmente falhará."
                        )
                        # Mantém pwd como "********", o que provavelmente causará falha na conexão,
                        # mas reflete a intenção de testar com os dados fornecidos.

                actual_config_to_use = temp_config

            else:  # config_data is None, so use saved configuration
                logger.debug("Testando conexão ODBC com configuração salva.")
                saved_config = self.get_connection_config()
                if not saved_config or not saved_config.get("dsn"):
                    result["error"] = (
                        "Nenhuma configuração ODBC ativa encontrada para teste."
                    )
                    result["error_type"] = "config_not_found"
                    result["suggestion"] = "Salve uma configuração ODBC primeiro."
                    logger.warning(result["error"])
                    return result
                actual_config_to_use = saved_config

            if not actual_config_to_use.get("dsn"):
                result["error"] = "DSN não especificado para o teste de conexão."
                result["error_type"] = "config_error"
                logger.warning(result["error"])
                return result

            conn_string = self.build_connection_string(actual_config_to_use)
            logger.info(
                f"String de conexão para teste (senha omitida): {self._build_connection_string(actual_config_to_use.get('dsn'), actual_config_to_use.get('uid'), '***', actual_config_to_use.get('driver'), hide_pwd=True)}"
            )

            conn = pyodbc.connect(conn_string, timeout=self.DEFAULT_TIMEOUT)
            logger.info("Conexão ODBC estabelecida com sucesso para teste.")

            result["success"] = True
            result["message"] = "Conexão ODBC bem-sucedida!"

            # Coletar informações da conexão
            if conn:
                try:
                    result["driver_version"] = conn.getinfo(pyodbc.SQL_DRIVER_VER)
                except pyodbc.Error as info_err:
                    logger.warning(f"Não foi possível obter SQL_DRIVER_VER: {info_err}")
                try:
                    result["dbms_version"] = conn.getinfo(pyodbc.SQL_DBMS_VER)
                except pyodbc.Error as info_err:
                    logger.warning(f"Não foi possível obter SQL_DBMS_VER: {info_err}")

                # Listar bancos de dados (pode não ser suportado por todos os drivers/DBs)
                # try:
                #     cursor = conn.cursor()
                #     # Este comando pode variar ou não ser suportado
                #     # Para SQL Server: cursor.execute("SELECT name FROM sys.databases")
                #     # Para outros, pode ser necessário algo diferente ou pode não funcionar.
                #     # Por enquanto, vamos omitir para evitar erros com drivers variados.
                #     # databases = [row.name for row in cursor.fetchall()]
                #     # result["databases"] = databases
                # except pyodbc.Error as db_list_err:
                #     logger.warning(f"Erro ao listar bancos de dados: {db_list_err}")
                #     result["databases"] = [f"Erro ao listar: {db_list_err}"]

        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            error_message = str(ex)
            logger.error(
                f"Erro de conexão pyodbc (SQLSTATE: {sqlstate}): {error_message}"
            )
            detailed_error = self._extract_detailed_error(error_message)
            result["error"] = detailed_error.get("message", error_message)
            result["error_type"] = "connection_error"
            result["error_details"] = detailed_error
            result["suggestion"] = detailed_error.get(
                "suggestion",
                "Verifique DSN, credenciais, driver e conectividade de rede.",
            )

        except ValueError as ve:
            error_message = str(ve)
            logger.error(
                f"Erro de valor ao preparar teste de conexão ODBC: {error_message}"
            )
            result["error"] = error_message
            result["error_type"] = "config_error"
            result["suggestion"] = "Verifique os parâmetros de configuração fornecidos."

        except Exception as e:
            import traceback

            error_message = str(e)
            logger.error(
                f"Erro inesperado durante o teste de conexão ODBC: {error_message}\n{traceback.format_exc()}"
            )
            result["error"] = f"Erro inesperado: {error_message}"
            result["error_type"] = "unexpected_error"
            result["suggestion"] = "Verifique os logs do servidor para mais detalhes."

        finally:
            if conn:
                conn.close()
                logger.info("Conexão ODBC de teste fechada.")

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

    def get_empresa_by_codi_emp(self, codi_emp: int) -> Optional[Dict[str, Any]]:
        """
        Busca uma empresa pelo código.

        Args:
            codi_emp: Código da empresa.

        Returns:
            Dicionário com os dados da empresa ou None se não encontrada.
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()

            query = """
            SELECT codi_emp, cgce_emp, razao_emp
            FROM bethadba.geempre
            WHERE codi_emp = ?
            """
            cursor.execute(query, codi_emp)
            empresa = cursor.fetchone()

            cursor.close()
            connection.close()

            if empresa:
                return {
                    "codi_emp": empresa[0],
                    "cgce_emp": empresa[1],
                    "razao_emp": empresa[2],
                }
            return None

        except Exception as e:
            logger.error(f"Erro ao buscar empresa por codi_emp: {str(e)}")
            return None

    def _list_data_source(
        self,
        codi_emp: int,
        filters: Optional[Dict[str, Any]],
        page_number: int,
        page_size: int,
        source_table_name: str,
        fields_to_select_str: str,
        default_order_by_field: str,
        id_field_filter_name: str,
        name_field_filter_name: str,
        name_field_db: str,
        cgce_field_filter_name: str,
        cgce_field_db: str,
        log_entity_name: str, # ex: "fornecedores", "clientes"
    ) -> Dict[str, Any]:
        """
        Método genérico para listar dados de uma fonte, com estrutura de retorno padronizada.
        """
        logger.info(
            f"_list_data_source chamada para {log_entity_name}, codi_emp: {codi_emp}, "
            f"filters: {filters}, page: {page_number}, size: {page_size}"
        )

        response = {
            "success": False,
            "data": [],
            "total_records": 0,
            "current_page": page_number,
            "page_size": page_size,
            "total_pages": 0,
            "error": None,
        }

        cnxn = None
        try:
            conn_str = self.build_connection_string()
            cnxn = pyodbc.connect(conn_str, timeout=self.DEFAULT_TIMEOUT)
            cursor = cnxn.cursor()

            primary_filter_condition = "codi_emp = ?"
            params_where = [codi_emp]
            where_clauses_list = []

            if filters:
                if filters.get(id_field_filter_name):
                    where_clauses_list.append(f"{default_order_by_field} = ?")
                    params_where.append(filters.get(id_field_filter_name))
                if filters.get(name_field_filter_name):
                    where_clauses_list.append(f"UPPER({name_field_db}) LIKE ?")
                    params_where.append(f"%{filters.get(name_field_filter_name).upper()}%")
                if filters.get(cgce_field_filter_name):
                    where_clauses_list.append(f"{cgce_field_db} = ?")
                    params_where.append(filters.get(cgce_field_filter_name))

            where_sql_additional = ""
            if where_clauses_list:
                where_sql_additional = " AND " + " AND ".join(where_clauses_list)

            final_query_count = f"SELECT COUNT(*) FROM {source_table_name} WHERE {primary_filter_condition}{where_sql_additional}"
            logger.debug(
                f"Query de contagem {log_entity_name}: {final_query_count}, Params: {params_where}"
            )
            cursor.execute(final_query_count, *params_where)
            count_result = cursor.fetchone()
            if count_result:
                response["total_records"] = count_result[0]

            if response["total_records"] > 0:
                response["total_pages"] = (
                    response["total_records"] + page_size - 1
                ) // page_size

                start_at = ((page_number - 1) * page_size) + 1
                order_by_sql = f" ORDER BY {default_order_by_field} ASC"

                paginated_query_select = (
                    f"SELECT TOP {page_size} START AT {start_at} {fields_to_select_str} "
                    f"FROM {source_table_name} WHERE {primary_filter_condition}{where_sql_additional}{order_by_sql}"
                )
                logger.debug(
                    f"Query de seleção {log_entity_name} (paginada): {paginated_query_select}, Params: {params_where}"
                )
                cursor.execute(paginated_query_select, *params_where)

                rows = cursor.fetchall()
                columns = [column[0] for column in cursor.description]
                response["data"] = [dict(zip(columns, row)) for row in rows]
                response["success"] = True
            else:
                response["success"] = True

            cursor.close()

        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            error_message = str(ex)
            logger.error(
                f"Erro ODBC ao listar {log_entity_name} para empresa {codi_emp}: {sqlstate} - {error_message}"
            )
            response["error"] = f"Erro ODBC: {error_message}"
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Erro inesperado ao listar {log_entity_name} da empresa {codi_emp}: {error_msg}"
            )
            response["error"] = f"Erro inesperado no sistema: {error_msg}"
        finally:
            if cnxn:
                cnxn.close()
        return response

    def list_fornecedores_empresa(
        self,
        codi_emp: int,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Lista fornecedores de uma empresa, com estrutura de retorno padronizada.
        """
        return self._list_data_source(
            codi_emp=codi_emp,
            filters=filters,
            page_number=page_number,
            page_size=page_size,
            source_table_name="bethadba.effornece",
            fields_to_select_str="codi_for, cgce_for, nome_for, codi_cta",
            default_order_by_field="codi_for",
            id_field_filter_name="f_codi_for",
            name_field_filter_name="f_nome_for",
            name_field_db="nome_for",
            cgce_field_filter_name="f_cgce_for",
            cgce_field_db="cgce_for",
            log_entity_name="fornecedores",
        )

    def list_clientes_empresa(
        self,
        codi_emp: int,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Lista clientes de uma empresa, com estrutura de retorno padronizada.
        """
        return self._list_data_source(
            codi_emp=codi_emp,
            filters=filters,
            page_number=page_number,
            page_size=page_size,
            source_table_name="bethadba.efclientes",
            fields_to_select_str="codi_cli, cgce_cli, nome_cli, codi_cta",
            default_order_by_field="codi_cli",
            id_field_filter_name="f_codi_cli",
            name_field_filter_name="f_nome_cli",
            name_field_db="nome_cli",
            cgce_field_filter_name="f_cgce_cli",
            cgce_field_db="cgce_cli",
            log_entity_name="clientes",
        )

    def list_plano_de_contas_empresa(
        self,
        codi_emp: int,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Lista os planos de contas de uma empresa, com estrutura de retorno padronizada.
        """
        return self._list_data_source(
            codi_emp=codi_emp,
            filters=filters,
            page_number=page_number,
            page_size=page_size,
            source_table_name="bethadba.ctcontas",
            fields_to_select_str="codi_cta, clas_cta, nome_cta, tipo_cta",
            default_order_by_field="codi_cta",
            id_field_filter_name="f_codi_cta",
            name_field_filter_name="f_nome_cta",
            name_field_db="nome_cta",
            # Usando clas_cta como terceiro campo de filtro, similar ao cgce_for/cgce_cli
            cgce_field_filter_name="f_clas_cta",
            cgce_field_db="clas_cta",
            log_entity_name="planos_de_contas",
        )

    def list_acumuladores_empresa(
        self,
        codi_emp: int,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Lista os acumuladores de uma empresa, com estrutura de retorno padronizada.
        """
        return self._list_data_source(
            codi_emp=codi_emp,
            filters=filters,
            page_number=page_number,
            page_size=page_size,
            source_table_name="bethadba.efacumuladorese",
            fields_to_select_str="CODI_ACU, NOME_ACU, DESCRICAO_ACU",
            default_order_by_field="CODI_ACU",
            id_field_filter_name="f_codi_acu",
            name_field_filter_name="f_nome_acu",
            name_field_db="NOME_ACU",
            cgce_field_filter_name="f_descricao_acu",
            cgce_field_db="DESCRICAO_ACU",
            log_entity_name="acumuladores",
        )

    def list_empresas(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page_number: int = 1,
        page_size: int = 25,
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

    # Métodos auxiliares que estavam faltando ou foram removidos:
    def _format_error_result(
        self,
        error_message: str,
        error_type: str = "generic_error",
        suggestion: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Formata uma mensagem de erro padrão para os retornos dos métodos."""
        details = {"type": error_type, "message": error_message}
        if suggestion:
            details["suggestion"] = suggestion
        response = {
            "success": False,
            "data": [],  # Adicionando para consistência com outras respostas de lista
            "total_records": 0,
            "error": error_message,
            "error_details": details,
        }
        # Campos como current_page, page_size podem ser adicionados pelos chamadores se relevante
        return response

    def _build_connection_string(self, dsn, uid, pwd, driver, hide_pwd=False):
        """Auxiliar para construir a string de conexão, opcionalmente ocultando a senha."""
        parts = []
        if driver:
            parts.append(f"DRIVER={{{driver}}}")
        if dsn:  # Adicionado para verificar se dsn existe
            parts.append(f"DSN={dsn}")
        if uid is not None:
            parts.append(f"UID={uid}")
        if pwd is not None:
            password_to_use = "********" if hide_pwd else pwd
            parts.append(f"PWD={password_to_use}")
        return ";".join(parts)

    def _extract_detailed_error(self, error_message: str) -> Dict[str, str]:
        """Tenta extrair detalhes de uma mensagem de erro ODBC."""
        details = {
            "type": "odbc_error",
            "message": error_message,
            "code": "N/A",
            "specific_type": "N/A",
            "suggestion": "Verifique a configuração da conexão, credenciais e logs do servidor de banco de dados.",
        }
        try:
            import re

            match = re.search(r"\\[(.*?)\\]", error_message)
            if match:
                details["code"] = match.group(1)

            if "Login failed" in error_message:
                details["specific_type"] = "login_failed"
                details["suggestion"] = "Verifique o nome de usuário e a senha."
            elif (
                "Data source name not found" in error_message
                or "IM002" in details["code"]
            ):
                details["specific_type"] = "dsn_not_found"
                details["suggestion"] = (
                    "Verifique se o DSN está configurado corretamente no sistema."
                )
            elif "Communication link failure" in error_message:
                details["specific_type"] = "communication_link_failure"
                details["suggestion"] = (
                    "Verifique a conectividade de rede com o servidor de banco de dados."
                )

        except Exception as e:
            logger.warning(f"Erro ao tentar extrair detalhes do erro ODBC: {e}")
            details["message"] = error_message

        return details


# Instância singleton para uso em toda a aplicação
odbc_manager = ODBCConnectionManager()
