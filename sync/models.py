from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
import json


class ODBCConfiguration(models.Model):
    """
    Armazena as configurações de conexão ODBC no banco de dados.
    Um design com apenas uma configuração ativa, mas o modelo
    suporta múltiplas configurações caso necessário no futuro.
    """

    dsn = models.CharField(_("Nome da Fonte de Dados (DSN)"), max_length=255)
    uid = models.CharField(_("Usuário (UID)"), max_length=255)
    pwd = models.CharField(_("Senha (PWD)"), max_length=255)
    driver = models.CharField(_("Driver ODBC"), max_length=255, blank=True)

    is_active = models.BooleanField(_("Ativo"), default=True)
    created_at = models.DateTimeField(_("Criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("Configuração ODBC")
        verbose_name_plural = _("Configurações ODBC")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"ODBC: {self.dsn} ({self.uid})"

    def save(self, *args, **kwargs):
        """
        Sobrescreve o método save para garantir que apenas uma configuração
        esteja ativa por vez.
        """
        if self.is_active:
            # Desativa todas as outras configurações ativas
            ODBCConfiguration.objects.filter(is_active=True).exclude(pk=self.pk).update(
                is_active=False
            )

        super().save(*args, **kwargs)

    @classmethod
    def get_active_config(cls):
        """
        Retorna a configuração ODBC ativa atual.

        Returns:
            ODBCConfiguration ou None se não houver configuração ativa.
        """
        try:
            return cls.objects.filter(is_active=True).latest("updated_at")
        except cls.DoesNotExist:
            return None


class EmpresaSincronizacao(models.Model):
    """
    Controla quais empresas do sistema ODBC devem ser sincronizadas com a API Fiscaut.
    """

    codi_emp = models.IntegerField(
        _("Código da Empresa no ODBC"),
        unique=True,
        db_index=True,
        help_text=_(
            "Identificador único da empresa no sistema ODBC (ex: geempre.codi_emp)"
        ),
    )
    habilitada_sincronizacao = models.BooleanField(
        _("Sincronização Habilitada"),
        default=False,
        help_text=_(
            "Indica se a sincronização desta empresa com o Fiscaut está ativa."
        ),
    )
    created_at = models.DateTimeField(_("Criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("Empresa para Sincronização")
        verbose_name_plural = _("Empresas para Sincronização")
        ordering = ["codi_emp"]

    def __str__(self):
        status = "Habilitada" if self.habilitada_sincronizacao else "Desabilitada"
        return f"Empresa ODBC {self.codi_emp} - Sincronização: {status}"


class FiscautApiConfig(models.Model):
    """Armazena a configuração para a API Fiscaut."""
    api_url = models.URLField(
        max_length=255, 
        verbose_name="URL da API Fiscaut",
        help_text="A URL base para a API Fiscaut. Ex: https://api.fiscaut.com.br/v1"
    )
    api_key = models.CharField(
        max_length=255, 
        verbose_name="Chave da API Fiscaut",
        help_text="A chave secreta para autenticação com a API Fiscaut."
    ) # TODO: Considerar criptografar este campo em produção.
    last_updated = models.DateTimeField(auto_now=True, verbose_name="Última Atualização")

    def __str__(self):
        return f"Configuração da API Fiscaut ({self.api_url})"

    class Meta:
        verbose_name = "Configuração da API Fiscaut"
        verbose_name_plural = "Configurações da API Fiscaut"

    @classmethod
    def get_active_config(cls):
        """Retorna a primeira configuração encontrada ou None."""
        return cls.objects.first()

    @classmethod
    def create_or_update_config(cls, api_url, api_key):
        """Cria ou atualiza a configuração da API Fiscaut."""
        config, created = cls.objects.update_or_create(
            # Usamos um ID fixo ou um critério para garantir que haja apenas uma entrada,
            # ou simplesmente atualizamos a primeira se existir.
            # Para este exemplo, vamos assumir que sempre haverá no máximo uma configuração.
            # Se você quiser permitir múltiplas e selecionar uma, a lógica de get_active_config mudaria.
            defaults={'api_url': api_url, 'api_key': api_key},
            # Se você quiser garantir que apenas um objeto exista, pode filtrar por um ID fixo
            # ou, se não houver nenhum, criar um. Para update_or_create, você precisa de algo para
            # identificar o objeto a ser atualizado. Se não houver identificador único, ele sempre criará.
            # Uma estratégia comum é ter um campo como `is_active` ou simplesmente pegar o .first().
            # Vamos pegar o primeiro e atualizar, ou criar se não existir.
        )
        if not created and config.pk is not None: # Se não foi criado e existe um pk (significa que estamos atualizando o primeiro)
             # Se não há um identificador único para o update_or_create, precisamos buscar e salvar.
            config_obj = cls.objects.first()
            if config_obj:
                config_obj.api_url = api_url
                config_obj.api_key = api_key
                config_obj.save()
                return config_obj, False
            else:
                return cls.objects.create(api_url=api_url, api_key=api_key), True
        return config, created


# Novo Modelo para Status de Sincronização de Fornecedor
class FornecedorStatusSincronizacao(models.Model):
    STATUS_CHOICES = [
        ('NAO_SINCRONIZADO', _('Não Sincronizado')),
        ('SINCRONIZADO', _('Sincronizado')),
        ('ERRO', _('Erro na Sincronização')),
    ]

    codi_emp_odbc = models.IntegerField(_("Código da Empresa ODBC"))
    # Assumindo que codi_for pode ser alfanumérico ou ter zeros à esquerda, CharField é mais seguro.
    # Se for sempre numérico e sem zeros à esquerda significativos, IntegerField pode ser usado.
    codi_for_odbc = models.CharField(_("Código do Fornecedor ODBC"), max_length=50) 
    
    status_sincronizacao = models.CharField(
        _("Status da Sincronização"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='NAO_SINCRONIZADO'
    )
    ultima_tentativa_sinc = models.DateTimeField(_("Última Tentativa de Sincronização"), null=True, blank=True)
    # Usar TextField para detalhes da resposta, JSONField é melhor se o DB suportar e for sempre JSON.
    detalhes_ultima_resposta = models.TextField(_("Detalhes da Última Resposta da API"), null=True, blank=True)
    # Opcional: ID do fornecedor no sistema Fiscaut, se retornado e útil.
    # fiscaut_fornecedor_id = models.CharField(_("ID do Fornecedor na Fiscaut"), max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = _("Status de Sincronização de Fornecedor")
        verbose_name_plural = _("Status de Sincronização de Fornecedores")
        unique_together = ('codi_emp_odbc', 'codi_for_odbc')
        ordering = ['codi_emp_odbc', 'codi_for_odbc']

    def __str__(self):
        return f"Empresa {self.codi_emp_odbc} - Forn {self.codi_for_odbc}: {self.get_status_sincronizacao_display()}"

    @classmethod
    def registrar_sincronizacao(cls, codi_emp_odbc, codi_for_odbc, sucesso, detalhes_resposta=None, fiscaut_id=None):
        from django.utils import timezone 
        # Importar logger aqui se não estiver global no models.py
        # import logging
        # logger = logging.getLogger(__name__) # Ou use um logger específico
        # Para simplificar, vou usar print para este log específico, assumindo que será visível no console de desenvolvimento.
        # Em produção, um logger configurado seria essencial.
        print(f"DEBUG_MODEL_REG_SINC: Entrando em registrar_sincronizacao. Empresa: {codi_emp_odbc}, Forn: {codi_for_odbc}, Sucesso: {sucesso}")

        status_sinc = 'SINCRONIZADO' if sucesso else 'ERRO'
        
        detalhes_str = None
        if detalhes_resposta is not None:
            if isinstance(detalhes_resposta, (dict, list)):
                try:
                    detalhes_str = json.dumps(detalhes_resposta)
                except TypeError:
                    detalhes_str = str(detalhes_resposta) 
            else:
                detalhes_str = str(detalhes_resposta)
        
        print(f"DEBUG_MODEL_REG_SINC: Detalhes serializados: {detalhes_str[:500] if detalhes_str else 'N/A'}") # Logar apenas parte dos detalhes

        defaults_dict = {
            'status_sincronizacao': status_sinc,
            'ultima_tentativa_sinc': timezone.now(),
            'detalhes_ultima_resposta': detalhes_str,
        }
        
        obj, created = cls.objects.update_or_create(
            codi_emp_odbc=codi_emp_odbc,
            codi_for_odbc=codi_for_odbc,
            defaults=defaults_dict
        )
        print(f"DEBUG_MODEL_REG_SINC: Resultado do update_or_create. Objeto ID: {obj.id if obj else 'N/A'}, Criado: {created}, Status Salvo: {obj.status_sincronizacao if obj else 'N/A'}")
        return obj
