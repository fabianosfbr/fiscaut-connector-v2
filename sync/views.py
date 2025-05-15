from django.shortcuts import render
from django.contrib.auth.models import User
from django.views.generic import TemplateView


# Create your views here.


class DashboardView(TemplateView):
    template_name = "admin/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "dashboard",
                "total_users": User.objects.count(),
                "total_syncs": 145,  # Dados de exemplo
                "success_rate": 98.5,  # Dados de exemplo
                "connected_systems": 4,  # Dados de exemplo
                "recent_activities": [
                    {
                        "icon": "refresh-cw",
                        "description": "Sincronização concluída com sucesso",
                        "user": "Admin",
                        "time_ago": "há 2 horas",
                    },
                    {
                        "icon": "user-plus",
                        "description": "Novo usuário cadastrado",
                        "user": "Sistema",
                        "time_ago": "há 5 horas",
                    },
                    {
                        "icon": "settings",
                        "description": "Configurações do sistema atualizadas",
                        "user": "Admin",
                        "time_ago": "há 1 dia",
                    },
                ],
            }
        )
        return context


class UsersView(TemplateView):
    template_name = "admin/users.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "users",
                "users": User.objects.all(),
            }
        )
        return context


class SettingsView(TemplateView):
    template_name = "admin/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "settings",
            }
        )
        return context


class LogsView(TemplateView):
    template_name = "admin/logs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_page": "logs",
                "logs": [
                    {
                        "level": "info",
                        "message": "Sincronização iniciada",
                        "timestamp": "15/05/2025 16:30:00",
                    },
                    {
                        "level": "success",
                        "message": "Sincronização concluída com sucesso",
                        "timestamp": "15/05/2025 16:42:15",
                    },
                    {
                        "level": "warning",
                        "message": "Conexão com o sistema externo instável",
                        "timestamp": "15/05/2025 15:12:33",
                    },
                    {
                        "level": "error",
                        "message": "Falha na autenticação com o sistema externo",
                        "timestamp": "14/05/2025 10:45:21",
                    },
                ],
            }
        )
        return context
