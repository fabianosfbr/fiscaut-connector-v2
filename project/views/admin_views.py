"""
Views do painel administrativo do Fiscaut Connector.
"""

from django.http import JsonResponse
from django.shortcuts import render
import logging

logger = logging.getLogger(__name__)


def admin_dashboard(request):
    """Renderiza a página de dashboard do painel administrativo."""
    context = {
        "active_page": "dashboard",
        "total_users": 125,  # Exemplo, deve ser obtido do banco de dados
        "total_syncs": 1547,  # Exemplo, deve ser obtido do banco de dados
        "success_rate": 98,  # Exemplo, deve ser obtido do banco de dados
        "connected_systems": 3,  # Exemplo, deve ser obtido do banco de dados
        "recent_activities": [
            {
                "icon": "refresh-cw",
                "description": "Sincronização concluída",
                "user": "Sistema",
                "time_ago": "5 minutos atrás",
            },
            {
                "icon": "user",
                "description": "Usuário atualizado",
                "user": "Admin",
                "time_ago": "2 horas atrás",
            },
            {
                "icon": "alert-triangle",
                "description": "Alerta de sistema",
                "user": "Sistema",
                "time_ago": "1 dia atrás",
            },
        ],
    }
    return render(request, "admin/dashboard.html", context)


def admin_users(request):
    """Renderiza a página de gerenciamento de usuários."""
    context = {
        "active_page": "users",
    }
    return render(request, "admin/users.html", context)


def admin_logs(request):
    """Renderiza a página de logs do sistema."""
    context = {"active_page": "logs"}
    return render(request, "admin/logs.html", context)
