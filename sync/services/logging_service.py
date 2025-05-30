import logging
import traceback as tb_module # Para evitar conflito com o parâmetro traceback

class LoggingService:

    def log(self, level: str, message: str, module: str, func_name: str = None, line_no: int = None, traceback: str = None):
        """
        Cria uma entrada de log no banco de dados utilizando o modelo ApplicationLog.

        Args:
            level (str): Nível do log (ex: INFO, ERROR, WARNING).
            message (str): A mensagem de log.
            module (str): Nome do módulo onde o log foi originado.
            func_name (str, optional): Nome da função.
            line_no (int, optional): Número da linha.
            traceback (str, optional): Traceback formatado, se houver erro.
        """
        from ..models import ApplicationLog
        try:
            # Validação básica do nível para garantir que está entre os choices do modelo
            # Isso pode ser expandido ou melhorado conforme necessidade
            valid_levels = [choice[0] for choice in ApplicationLog.LEVEL_CHOICES]
            if level.upper() not in valid_levels:
                # Logar um aviso sobre nível inválido, mas registrar com um nível padrão ou falhar
                logging.warning(f"Nível de log inválido '{level}' fornecido para LoggingService. Usando ERROR como padrão.")
                # Ou poderia simplesmente não registrar, ou levantar um erro
                # Por ora, vamos apenas ajustar para um nível válido conhecido se possível, ou ERROR.
                db_level = 'ERROR' # Default para um nível conhecido se o fornecido for inválido
            else:
                db_level = level.upper()

            ApplicationLog.objects.create(
                level=db_level,
                message=message,
                module=module,
                func_name=func_name,
                line_no=line_no,
                traceback=traceback
            )
        except Exception as e:
            # Se houver um erro ao tentar registrar o log no banco de dados,
            # precisamos logar isso de alguma forma (ex: no logger padrão do Django)
            # para não perder a informação sobre a falha no logging.
            # Evitar um loop infinito se o próprio logging para o DB falhar.
            # Usar o logger padrão do Python/Django que normalmente vai para console/arquivo.
            logger = logging.getLogger(__name__) # Usar um logger específico para o LoggingService
            # Construir uma mensagem de erro mais detalhada
            error_details = f"Falha ao registrar log no banco de dados. Erro original: {str(e)}\n"
            error_details += f"Log original que falhou: Level={level}, Module={module}, Message={message[:200]}...\n"
            if func_name: error_details += f"Function={func_name}\n"
            if line_no: error_details += f"Line={line_no}\n"
            if traceback: error_details += f"Original Traceback (primeiras 200 chars)={traceback[:200]}...\n"
            
            # Adicionar o traceback da falha do LoggingService em si
            current_traceback = tb_module.format_exc()
            error_details += f"Traceback da falha no LoggingService:\n{current_traceback}"

            logger.error(error_details)

# Instância única do serviço para ser usada em outros lugares (opcional, mas comum)
logging_service = LoggingService() 