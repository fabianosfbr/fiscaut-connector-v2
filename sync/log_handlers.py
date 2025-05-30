import logging
import traceback

# Tentar importar o serviço de logging. 
# Se houver um problema aqui (ex: AppRegistryNotReady durante a inicialização do Django antes que os apps estejam carregados),
# pode ser necessário adiar a importação ou o uso do serviço.
try:
    # Tentar importar a INSTÂNCIA logging_service diretamente do seu módulo
    from .services.logging_service import logging_service
except ImportError:
    logging_service = None

class DatabaseLogHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level=level)
        # Não chamar _ensure_service aqui, pois pode ser muito cedo.
        # Deixar que o primeiro emit() tente carregar se necessário.
        self.service_checked_at_init = False
        if logging_service is None: # Apenas para log inicial se falhou de cara
            try:
                # Tentar uma vez no init, mas não falhar criticamente aqui, deixar para o emit.
                from .services.logging_service import logging_service as init_ls
                globals()['logging_service'] = init_ls
                logging.info("DatabaseLogHandler: logging_service carregado na inicialização.")
                self.service_checked_at_init = True
            except Exception as e:
                logging.warning(f"DatabaseLogHandler: Falha inicial ao tentar carregar logging_service: {e}. Tentará novamente no primeiro emit.")

    def _ensure_service(self):
        """Garante que o logging_service esteja carregado."""
        global logging_service
        if logging_service is None:
            try:
                # Importar a INSTÂNCIA logging_service diretamente do seu módulo
                from .services.logging_service import logging_service as service_instance
                logging_service = service_instance # Atualiza a variável global
                logging.info("DatabaseLogHandler: logging_service carregado dinamicamente com sucesso.")
                self.disabled = False # Resetar flag se carregou com sucesso
            except Exception as e:
                # Se ainda falhar, logar um erro crítico para o logger padrão e desabilitar este handler
                # para evitar loops ou falhas contínuas.
                logging.critical(f"DatabaseLogHandler: Falha crítica ao carregar logging_service dinamicamente: {e}. O handler será desabilitado.", exc_info=True)
                # Para "desabilitar", podemos remover este handler do logger raiz ou definir um flag.
                # Por ora, apenas logamos criticamente.
                # Ou poderíamos definir um flag self.disabled = True e verificar no emit.
                self.disabled = True # Flag para indicar que o handler não pode operar
        return not (hasattr(self, 'disabled') and self.disabled)

    def emit(self, record: logging.LogRecord):
        """
        Processa um registro de log e o envia para o LoggingService.
        """
        # Verificar se o handler foi desabilitado devido a falha na carga do serviço
        if hasattr(self, 'disabled') and self.disabled:
            return

        # Garantir que o serviço está disponível (caso a importação inicial tenha falhado)
        if logging_service is None:
            if not self._ensure_service(): # Tenta carregar e verifica se foi desabilitado
                return # Não foi possível carregar o serviço
        
        try:
            # Mapear o levelno do LogRecord para a string de nível esperada pelo serviço/modelo
            level_name = record.levelname.upper()

            # Obter informações do LogRecord
            module_name = record.module
            func_name = record.funcName
            line_no = record.lineno
            message = self.format(record) # Pega a mensagem formatada pelo Formatter do handler
            
            tb = None
            if record.exc_info:
                # Se exc_info está presente, formatar o traceback
                tb = traceback.format_exception(*record.exc_info)
                tb = "".join(tb) # Converter a lista de strings do traceback em uma única string
            elif record.levelno >= logging.ERROR and hasattr(record, 'stack_info') and record.stack_info:
                # Para erros onde exc_info não está, mas stack_info (Python 3.2+) pode estar
                tb = record.stack_info

            # Chamar o serviço de logging
            logging_service.log(
                level=level_name,
                message=message,
                module=module_name,
                func_name=func_name,
                line_no=line_no,
                traceback=tb
            )
        except Exception as e:
            # O que fazer se o logging para o banco de dados falhar aqui?
            # Poderíamos usar logging.warning() para logar no console/arquivo padrão do Django
            # para evitar um loop infinito se o próprio logging_service.log() falhar de forma que caia aqui.
            # O LoggingService já tem um fallback para logar erros internos ao logger padrão, 
            # mas uma falha catastrófica (ex: DB completamente indisponível) pode precisar de atenção aqui.
            
            # Usar o sistema de logging padrão para registrar a falha do handler.
            # É importante não tentar usar o logging_service aqui para evitar recursão infinita.
            log = logging.getLogger("DatabaseLogHandlerInternal") # Usar um logger específico para erros do handler
            log.error(f"Falha no DatabaseLogHandler ao emitir log: {e}", exc_info=True)
            # Também podemos adicionar mais detalhes sobre o record que falhou:
            log.error(f"LogRecord que falhou: Level={record.levelname}, Module={record.module}, Message (raw)={record.getMessage()[:200]}...") 