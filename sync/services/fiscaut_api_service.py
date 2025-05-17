"""
Serviço para gerenciar a configuração e comunicação com a API Fiscaut.
"""
import requests
import logging
from typing import Dict, Any, Optional, Tuple
from sync.models import FiscautApiConfig
from django.conf import settings

logger = logging.getLogger(__name__)

class FiscautApiService:
    """
    Gerencia o armazenamento da configuração da API Fiscaut e testa a conexão.
    """

    def __init__(self):
        # Opcional: Carregar config aqui se for usada em múltiplos métodos
        # e para evitar múltiplas buscas no DB.
        self.config = self._get_db_config() 

    def _get_db_config(self):
        try:
            return FiscautApiConfig.objects.first()
        except Exception as e:
            logger.error(f"Erro ao buscar FiscautApiConfig do DB: {e}")
            return None

    def save_config(self, api_url: str, api_key: str):
        if not api_url or not api_key:
            return {"success": False, "message": "URL e Chave da API são obrigatórias."}

        if not api_url.startswith('http://') and not api_url.startswith('https://'):
            return {"success": False, "message": "URL da API inválida. Deve começar com http:// ou https://"}

        try:
            config_obj, created = FiscautApiConfig.objects.update_or_create(
                id=FiscautApiConfig.objects.first().id if FiscautApiConfig.objects.exists() else None,
                defaults={'api_url': api_url, 'api_key': api_key}
            )
            if not FiscautApiConfig.objects.exists():
                 config_obj = FiscautApiConfig(api_url=api_url, api_key=api_key)
                 config_obj.save()
                 created = True
            else:
                 current_config = FiscautApiConfig.objects.first()
                 current_config.api_url = api_url
                 current_config.api_key = api_key
                 current_config.save()
                 config_obj = current_config
                 created = False

            self.config = config_obj
            message = "Configuração da API Fiscaut salva com sucesso."
            if created:
                message = "Configuração da API Fiscaut criada com sucesso."
            return {"success": True, "message": message, "api_url": config_obj.api_url}
        except Exception as e:
            logger.error(f"Erro ao salvar configuração da API Fiscaut no DB: {e}")
            return {"success": False, "message": f"Erro interno ao salvar configuração: {e}"}

    def get_config(self):
        if not self.config:
            self.config = self._get_db_config()
        return self.config

    def test_fiscaut_connection(self, api_url_to_test=None, api_key_to_test=None):
        target_url = api_url_to_test
        target_key = api_key_to_test

        if not target_url or not target_key:
            current_config = self.get_config()
            if not current_config:
                return {"success": False, "message": "Configuração da API não encontrada. Salve primeiro."}
            target_url = current_config.api_url
            target_key = current_config.api_key

        if not target_url or not target_key:
            return {"success": False, "message": "URL e Chave da API são obrigatórias para o teste."}
        
        if not target_url.startswith('http://') and not target_url.startswith('https://'):
            return {"success": False, "message": "URL da API inválida para teste. Deve começar com http:// ou https://"}

        test_endpoint = f"{target_url.rstrip('/')}/up"
        headers = {
            "Authorization": f"Bearer {target_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = requests.get(test_endpoint, headers=headers, timeout=15)
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    if response_data.get("status") is True:
                        return {"success": True, "message": "Conexão com a API Fiscaut bem-sucedida!"}
                    else:
                        return {"success": False, "message": "API Fiscaut respondeu, mas indicou um problema.", "details": response_data}
                except ValueError:
                    return {"success": False, "message": "Resposta da API Fiscaut não é um JSON válido.", "details": response.text}
            else:
                return {"success": False, "message": f"Falha na conexão com a API Fiscaut (HTTP {response.status_code}).", "details": response.text}
        
        except requests.exceptions.Timeout:
            logger.error(f"Timeout ao testar conexão com API Fiscaut: {test_endpoint}")
            return {"success": False, "message": "Tempo limite excedido ao tentar conectar à API Fiscaut."}
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de requisição ao testar API Fiscaut: {e}")
            return {"success": False, "message": f"Erro ao conectar à API Fiscaut: {e}"}
        except Exception as e:
            logger.error(f"Erro inesperado ao testar API Fiscaut: {e}")
            return {"success": False, "message": f"Ocorreu um erro inesperado durante o teste: {e}"}

    def sincronizar_fornecedor(self, cnpj_empresa: str, nome_fornecedor: str, cnpj_fornecedor: str, conta_contabil_fornecedor: str) -> Dict[str, Any]:
        """
        Envia os dados de um fornecedor para a API Fiscaut para sincronização.

        Args:
            cnpj_empresa: CNPJ da empresa à qual o fornecedor pertence.
            nome_fornecedor: Nome do fornecedor.
            cnpj_fornecedor: CNPJ do fornecedor.
            conta_contabil_fornecedor: Código da conta contábil do fornecedor.

        Returns:
            Um dicionário com o status da operação e dados/mensagens.
        """
        current_config = self.get_config()
        if not current_config:
            return {"success": False, "message": "Configuração da API Fiscaut não encontrada. Por favor, configure-a primeiro."}

        target_url = current_config.api_url
        target_key = current_config.api_key

        if not target_url or not target_key:
            return {"success": False, "message": "URL da API ou Chave da API não configuradas."}

        endpoint = f"{target_url.rstrip('/')}/contabil/fornecedores"
        
        payload = {
            "cnpj_empresa": cnpj_empresa,
            "nome_fornecedor": nome_fornecedor,
            "cnpj_fornecedor": cnpj_fornecedor,
            "conta_contabil_fornecedor": conta_contabil_fornecedor,
        }

        headers = {
            "Authorization": f"Bearer {target_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        logger.info(f"Sincronizando fornecedor: CNPJ Empresa={cnpj_empresa}, Fornecedor={cnpj_fornecedor} para endpoint {endpoint}")
        logger.debug(f"Payload da sincronização do fornecedor: {payload}")

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30) # Timeout de 30s para POST

            # Se a API retornar 200 OK ou 201 Created, consideramos sucesso parcial (API respondeu)
            # A lógica de "sucesso total" pode depender do corpo da resposta da API Fiscaut
            if response.status_code == 200 or response.status_code == 201:
                try:
                    response_data = response.json()
                    logger.info(f"Resposta da sincronização do fornecedor ({response.status_code}): {response_data}")
                    # Assumindo que a API Fiscaut pode retornar um "success": false em um 200 OK.
                    # Adapte esta lógica conforme a API Fiscaut real.
                    if isinstance(response_data, dict) and response_data.get("success") is False:
                        return {
                            "success": False,
                            "message": response_data.get("message", "API Fiscaut indicou uma falha na sincronização."),
                            "details": response_data,
                            "status_code": response.status_code
                        }
                    return {
                        "success": True, 
                        "message": "Dados do fornecedor enviados para sincronização com sucesso.", 
                        "details": response_data,
                        "status_code": response.status_code
                    }
                except ValueError: # Se a resposta não for JSON
                    logger.warning(f"Resposta da sincronização do fornecedor ({response.status_code}) não é JSON: {response.text[:200]}")
                    return {
                        "success": True, # Sucesso na chamada, mas resposta inesperada
                        "message": f"Fornecedor enviado, mas a resposta da API não foi JSON (Status: {response.status_code}).",
                        "details": response.text,
                        "status_code": response.status_code
                    }
            else: # Erros HTTP (4xx, 5xx)
                error_message = f"Falha ao enviar dados do fornecedor para API Fiscaut (HTTP {response.status_code})."
                details = response.text
                try:
                    error_details_json = response.json()
                    error_message_api = error_details_json.get("message", "Erro não especificado pela API.")
                    details_api = error_details_json.get("errors", error_details_json)
                    logger.warning(f"{error_message} Detalhes da API: {details_api}")
                    return {
                        "success": False, 
                        "message": f"API Fiscaut retornou erro {response.status_code}: {error_message_api}",
                        "details": details_api,
                        "status_code": response.status_code
                    }
                except ValueError:
                    logger.warning(f"{error_message} Resposta: {response.text[:200]}")
                    return {
                        "success": False,
                        "message": error_message,
                        "details": response.text,
                        "status_code": response.status_code
                    }

        except requests.exceptions.Timeout:
            logger.error(f"Timeout ao enviar dados do fornecedor para API Fiscaut: {endpoint}")
            return {"success": False, "message": "Tempo limite excedido ao tentar enviar dados para a API Fiscaut."}
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de requisição ao enviar dados do fornecedor para API Fiscaut: {e}")
            return {"success": False, "message": f"Erro ao conectar à API Fiscaut para enviar dados: {e}"}
        except Exception as e: # Outros erros inesperados
            logger.error(f"Erro inesperado ao enviar dados do fornecedor: {e}", exc_info=True)
            return {"success": False, "message": f"Ocorreu um erro inesperado ao enviar dados do fornecedor: {e}"} 