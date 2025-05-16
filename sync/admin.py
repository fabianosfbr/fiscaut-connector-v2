from django.contrib import admin
from .models import ODBCConfiguration


@admin.register(ODBCConfiguration)
class ODBCConfigurationAdmin(admin.ModelAdmin):
    """Admin para gerenciar configurações ODBC."""

    list_display = ("dsn", "uid", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("dsn", "uid")
    readonly_fields = ("created_at", "updated_at")

    # Não exibir a senha em texto claro
    def get_fields(self, request, obj=None):
        fields = ["dsn", "uid", "pwd", "driver", "is_active"]
        if obj:  # Se for uma edição
            fields.extend(["created_at", "updated_at"])
        return fields

    def save_model(self, request, obj, form, change):
        """Sobrescreve o método save_model para garantir apenas uma configuração ativa."""
        super().save_model(request, obj, form, change)
