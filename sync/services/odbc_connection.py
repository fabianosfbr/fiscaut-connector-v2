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

        Args:
            config: Configuração de conexão (opcional, se não fornecido, usa a configuração salva)

        Returns:
            String de conexão ODBC
        """
        if config is None:
            config = self.get_connection_config()
            if not config:
                raise ValueError("Não há configuração de conexão ODBC salva")

        # Construir string de conexão
        conn_parts = [f"DSN={config['dsn']}"]

        if config.get("uid"):
            conn_parts.append(f"UID={config['uid']}")

        if config.get("pwd"):
            conn_parts.append(f"PWD={config['pwd']}")

        if config.get("driver"):
            conn_parts.append(f"DRIVER={config['driver']}")

        return ";".join(conn_parts)

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

        except pyodbc.Error as pe:
            # Erro específico do pyodbc
            error_msg = str(pe)
            result["error"] = error_msg

            # Analisar o erro para fornecer detalhes mais específicos
            error_details = {
                "type": "pyodbc_error",
                "code": getattr(pe, "code", None),
                "state": getattr(pe, "state", None),
                "message": error_msg,
            }

            # Classificação de tipos comuns de erros
            if (
                "data source name" in error_msg.lower()
                and "not found" in error_msg.lower()
            ):
                error_details["specific_type"] = "dsn_not_found"
                error_details["suggestion"] = (
                    "Verifique se o DSN está configurado corretamente no sistema"
                )
            elif (
                "login failed" in error_msg.lower()
                or "password" in error_msg.lower()
                or "autorização" in error_msg.lower()
            ):
                error_details["specific_type"] = "authentication_failed"
                error_details["suggestion"] = "Verifique as credenciais (usuário/senha)"
            elif "driver" in error_msg.lower():
                error_details["specific_type"] = "driver_error"
                error_details["suggestion"] = (
                    "Verifique se o driver ODBC está instalado corretamente"
                )
            elif "timeout" in error_msg.lower():
                error_details["specific_type"] = "connection_timeout"
                error_details["suggestion"] = (
                    "Verifique a conectividade de rede e se o servidor está acessível"
                )

            result["error_details"] = error_details
            logger.error(f"Erro PyODBC no teste de conexão: {error_msg}")

        except Exception as e:
            # Erro genérico
            error_msg = str(e)
            result["error"] = error_msg
            result["error_details"] = {
                "type": "generic_error",
                "exception_type": type(e).__name__,
                "message": error_msg,
            }
            logger.error(f"Erro genérico no teste de conexão ODBC: {error_msg}")

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


# Instância singleton para uso em toda a aplicação
odbc_manager = ODBCConnectionManager()
