from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


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
        help_text=_("Identificador único da empresa no sistema ODBC (ex: geempre.codi_emp)"),
    )
    habilitada_sincronizacao = models.BooleanField(
        _("Sincronização Habilitada"),
        default=False,
        help_text=_("Indica se a sincronização desta empresa com o Fiscaut está ativa."),
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
